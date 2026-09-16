"""Intrinsic reaction coordinate workflow based on Sella."""

from __future__ import annotations

from pathlib import Path
import traceback
from typing import Any, Dict

import numpy as np
from ase.io import read, write
from ase.io.trajectory import Trajectory
from ase.optimize import FIRE

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.io import read_structure
from atst_tools.utils.restart_helpers import get_last_frame


def _irc_step_count(irc_object: Any) -> int | None:
    """Read the IRC optimizer's cumulative step count, or None when unavailable.

    ASE ``Dynamics.irun`` never resets ``nsteps`` (it sets ``max_steps = nsteps +
    steps``), so one reused IRC object accumulates steps across directions and the
    caller must difference two readings to report per-direction steps.
    """
    getter = getattr(irc_object, "get_number_of_steps", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            return None
    value = getattr(irc_object, "nsteps", None)
    return value if isinstance(value, int) else None


class IRCBoundaryError(RuntimeError):
    """Known Sella IRC boundary that ATST-Tools reports as a controlled error."""


class IRCWorkflow:
    """Run forward, reverse, or combined IRC calculations from a TS structure."""

    def __init__(self, config: Dict[str, Any], calc_name: str, calc_config: Dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = apply_calculation_defaults(calc_config)
        calc_config = self.calc_config
        self.init_structure = calc_config["init_structure"]
        self.traj_file = calc_config["trajectory"]
        self.normalized_traj_file = calc_config.get(
            "normalized_trajectory", f"norm_{Path(self.traj_file).name}"
        )
        self.direction = calc_config["direction"]
        self.restart = calc_config["restart"]
        self.backend = calc_config.get("backend", "sella")

    def _set_calculator(self, atoms):
        directory = self.calc_config["directory"]
        if "abacus" in self.config:
            directory = self.config["abacus"].get("directory", directory)
        atoms.calc = CalculatorFactory.get_calculator(self.calc_name, self.config, directory=directory)
        return atoms

    def _directions(self) -> list[str]:
        if self.direction == "both":
            return ["forward", "reverse"]
        if self.direction in {"forward", "reverse"}:
            return [self.direction]
        raise ValueError("IRC direction must be 'both', 'forward', or 'reverse'")

    def _normalize_trajectory(self) -> None:
        if self.direction != "both":
            return
        frames = read(self.traj_file, index=":")
        normalized = []
        ene_last = -float("inf")
        for atoms in frames[::-1]:
            energy = atoms.get_potential_energy()
            if energy > ene_last:
                normalized.append(atoms)
                ene_last = energy
            else:
                break
        ene_last = float("inf")
        for atoms in frames:
            energy = atoms.get_potential_energy()
            if energy < ene_last:
                normalized.append(atoms)
                ene_last = energy
            else:
                break
        write(self.normalized_traj_file, normalized, format="traj")

    def _trajectory_frame_count(self) -> int:
        path = Path(self.traj_file)
        if not path.exists():
            return 0
        try:
            return len(read(path, index=":"))
        except Exception:
            return -1

    def _boundary_message(self, direction: str, cause: BaseException) -> str:
        frame_count = self._trajectory_frame_count()
        if frame_count < 0:
            frame_text = "unknown"
        else:
            frame_text = str(frame_count)
        return "\n".join(
            [
                "IRC calculation stopped at the current supported boundary.",
                "",
                "Sella IRC could not continue after an inner-loop or flat-endpoint condition.",
                f"Direction: {direction}",
                f"Trajectory: {self.traj_file} (frames written: {frame_text})",
                f"Original error: {type(cause).__name__}: {cause}",
                "",
                "Current boundary:",
                "- ATST-Tools delegates IRC integration to Sella and does not yet provide automatic endpoint recovery.",
                "- A partially written trajectory can be inspected, but this run is not considered complete.",
                "- For direction=both, normalized_trajectory is only written after both directions complete.",
                "",
                "Suggested actions:",
                "- Inspect the partial IRC trajectory before using it scientifically.",
                "- Try a smaller calculation.dx or run direction=forward and direction=reverse as separate jobs.",
                "- Treat this as a failed IRC regression until a full rerun completes without this message.",
            ]
        )

    @staticmethod
    def _is_sella_restricted_step_assertion(exc: AssertionError) -> bool:
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename.endswith("sella/optimize/restricted_step.py") and frame.name == "get_s":
                return True
        return False

    @staticmethod
    def _is_sella_runtime_boundary(exc: RuntimeError) -> bool:
        for frame in traceback.extract_tb(exc.__traceback__):
            if "/sella/" in frame.filename or frame.filename.startswith("sella/"):
                return True
        return False

    def run(self):
        """Execute the configured IRC calculation."""
        if self.backend == "descent":
            return self._run_descent()
        try:
            from sella import IRC
            from sella.optimize.irc import IRCInnerLoopConvergenceFailure
        except ImportError as exc:
            raise ImportError("sella is required for calculation.type=irc. Install it with `pip install sella`.") from exc

        atoms = get_last_frame(self.traj_file) if self.restart else read_structure(self.init_structure)
        atoms = self._set_calculator(atoms)
        traj_mode = "a" if self.restart else "w"
        irc_traj = Trajectory(self.traj_file, traj_mode, atoms)
        irc = IRC(
            atoms,
            trajectory=irc_traj,
            dx=self.calc_config["dx"],
            eta=self.calc_config["eta"],
            gamma=self.calc_config["gamma"],
            irctol=self.calc_config["irctol"],
            keep_going=self.calc_config["keep_going"],
        )
        for direction in self._directions():
            steps_before = _irc_step_count(irc)
            try:
                converged_signal = irc.run(
                    self.calc_config["fmax"],
                    steps=self.calc_config["max_steps"],
                    direction=direction,
                )
            except IRCInnerLoopConvergenceFailure as exc:
                raise IRCBoundaryError(self._boundary_message(direction, exc)) from exc
            except AssertionError as exc:
                if self._is_sella_restricted_step_assertion(exc):
                    raise IRCBoundaryError(self._boundary_message(direction, exc)) from exc
                raise
            except RuntimeError as exc:
                if self._is_sella_runtime_boundary(exc):
                    raise IRCBoundaryError(self._boundary_message(direction, exc)) from exc
                raise
            self._warn_if_unconverged(
                irc, direction, converged_signal, self.calc_config["fmax"], steps_before
            )
        self._normalize_trajectory()
        artifacts = [{"role": "irc_trajectory", "path": self.traj_file}]
        if self.direction == "both" and self.normalized_traj_file:
            artifacts.append({"role": "normalized_irc_trajectory", "path": self.normalized_traj_file})
        write_artifact_manifest(
            self.calc_config.get("artifact_manifest", "atst_artifacts.json"),
            workflow="irc",
            artifacts=artifacts,
            stages=[{"name": "sella_irc", "status": "complete"}],
        )

    @staticmethod
    def _warn_if_unconverged(irc_object, direction: str, converged_signal, fmax: float,
                             steps_before: int | None) -> None:
        """IRC 方向结束但确定性收敛信号为 False 时输出中性 advisory warning（不改变返回语义）。

        只信任 Sella ``IRC.run()`` 返回的确定性收敛信号（其判据为力达阈值且 Hessian 最小
        本征值为正，即到达端点盆地）；信号不可得（非 bool）时保持安静，不臆测未收敛，也不
        额外调用 ``converged()``。warning 只陈述客观事实（方向、配置阈值、本方向实际步数），
        不预判科学原因。返回码、workflow 状态与 artifact manifest 均不受影响。
        """
        if not isinstance(converged_signal, (bool, np.bool_)) or bool(converged_signal):
            return
        steps_after = _irc_step_count(irc_object)
        nsteps = steps_after if steps_before is None or steps_after is None else steps_after - steps_before
        print(
            f"Warning: IRC {direction} 方向结束时确定性收敛信号为 False"
            f"（workflow=irc, direction={direction}, threshold_fmax={fmax}, nsteps={nsteps}）；"
            "未确认到达端点盆地（IRC 判据为力达阈值且 Hessian 最小本征值为正）。"
            "完成只代表计算任务正常结束，不代表科学收敛；"
            "请结合轨迹、原子约束、restart/input 选择与计算成本复核。"
        )

    def _load_mode_vector(self, atoms) -> np.ndarray:
        mode_file = self.calc_config.get("mode_vector")
        if not mode_file:
            raise ValueError("mode_vector is required for backend=descent")
        mode = np.asarray(np.load(mode_file), dtype=float).reshape(len(atoms), 3)
        norm = float(np.linalg.norm(mode))
        if norm <= 1e-12:
            raise ValueError("mode_vector must have non-zero norm")
        return mode / norm

    def _run_descent(self):
        atoms = read_structure(self.init_structure)
        mode = self._load_mode_vector(atoms)
        frames = []
        for direction in self._directions():
            sign = 1.0 if direction == "forward" else -1.0
            branch = atoms.copy()
            branch.set_positions(branch.get_positions() + sign * self.calc_config["descent_delta"] * mode)
            branch = self._set_calculator(branch)
            branch_traj = f"{Path(self.traj_file).stem}_{direction}.traj"
            opt = FIRE(branch, trajectory=branch_traj)
            opt.run(fmax=self.calc_config["fmax"], steps=self.calc_config["max_steps"])
            frames.append(branch.copy())
        write(self.traj_file, frames, format="traj")
        if self.direction == "both" and self.normalized_traj_file:
            write(self.normalized_traj_file, list(reversed(frames[:1])) + frames[1:], format="traj")
        artifacts = [{"role": "irc_trajectory", "path": self.traj_file}]
        if self.direction == "both" and self.normalized_traj_file:
            artifacts.append({"role": "normalized_irc_trajectory", "path": self.normalized_traj_file})
        write_artifact_manifest(
            self.calc_config.get("artifact_manifest", "atst_artifacts.json"),
            workflow="irc",
            artifacts=artifacts,
            stages=[{"name": "descent_irc", "status": "complete"}],
        )
        return frames
