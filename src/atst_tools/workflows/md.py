"""Molecular dynamics workflows."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms, units
from ase.io import read, write
from ase.md import Bussi, Langevin, VelocityVerlet
from ase.md.nptberendsen import NPTBerendsen
from ase.md.nvtberendsen import NVTBerendsen
from ase.md.velocitydistribution import MaxwellBoltzmannDistribution, Stationary, ZeroRotation

from atst_tools.calculators.factory import CalculatorFactory, _build_abacus_command
from atst_tools.utils.abacus_io import _as_mp_kpts, _input_parameters, _merged_abacus_parameters
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.io import read_structure
from atst_tools.utils.restart_helpers import get_last_frame


def _import_generalio():
    try:
        from abacuslite.io import generalio
    except ImportError:
        from atst_tools.external.ASE_interface.abacuslite.io import generalio
    return generalio


def _import_latestio():
    try:
        from abacuslite.io.latestio import read_abacus_out
    except ImportError:
        from atst_tools.external.ASE_interface.abacuslite.io.latestio import read_abacus_out
    return read_abacus_out


def _import_legacyio():
    try:
        from abacuslite.io.legacyio import read_traj_from_md_dump
    except ImportError:
        from atst_tools.external.ASE_interface.abacuslite.io.legacyio import read_traj_from_md_dump
    return read_traj_from_md_dump


def _abacus_section(config: dict[str, Any]) -> dict[str, Any]:
    if "calculator" in config:
        return dict(config.get("calculator", {}).get("abacus", {}) or {})
    return dict(config.get("abacus", {}) or {})


def _json_write(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


class MDWorkflow:
    """Run ASE-driven or ABACUS-native molecular dynamics."""

    def __init__(self, config: dict[str, Any], calc_name: str, calc_config: dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = apply_calculation_defaults(calc_config)

    def run(self) -> None:
        """Execute the configured MD workflow."""
        driver = self.calc_config.get("driver", "ase")
        if driver == "ase":
            AseMDRunner(self.config, self.calc_name, self.calc_config).run()
            return
        if driver == "abacus_native":
            AbacusNativeMDRunner(self.config, self.calc_name, self.calc_config).run()
            return
        raise ValueError(f"Unsupported MD driver: {driver}")


class AseMDRunner:
    """ASE molecular-dynamics driver using ATST calculator factories."""

    def __init__(self, config: dict[str, Any], calc_name: str, calc_config: dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config

    def _read_atoms(self) -> Atoms:
        if self.calc_config.get("restart"):
            return get_last_frame(self.calc_config["trajectory"])
        return read_structure(self.calc_config["init_structure"])

    def _initialize_velocities(self, atoms: Atoms) -> None:
        if atoms.has("momenta") and np.linalg.norm(atoms.get_momenta()) > 0:
            return
        seed = self.calc_config.get("seed")
        rng = np.random.RandomState(seed) if seed is not None else None
        MaxwellBoltzmannDistribution(
            atoms,
            temperature_K=self.calc_config["temperature_K"],
            force_temp=self.calc_config.get("force_temperature", False),
            rng=rng,
        )
        if self.calc_config.get("stationary", True):
            Stationary(atoms)
        if self.calc_config.get("zero_rotation", False):
            ZeroRotation(atoms)

    def _build_dynamics(self, atoms: Atoms):
        timestep = self.calc_config["timestep_fs"] * units.fs
        common = {
            "trajectory": self.calc_config["trajectory"],
            "logfile": self.calc_config["logfile"],
            "loginterval": self.calc_config["loginterval"],
        }
        algorithm = self.calc_config["algorithm"].lower()
        if algorithm == "velocityverlet":
            return VelocityVerlet(atoms, timestep=timestep, **common)
        if algorithm == "bussi":
            return Bussi(
                atoms,
                timestep=timestep,
                temperature_K=self.calc_config["temperature_K"],
                taut=self.calc_config["taut_fs"] * units.fs,
                **common,
            )
        if algorithm == "langevin":
            return Langevin(
                atoms,
                timestep=timestep,
                temperature_K=self.calc_config["temperature_K"],
                friction=self.calc_config["friction_fs_inv"] / units.fs,
                fixcm=False,
                **common,
            )
        if algorithm == "nvtberendsen":
            return NVTBerendsen(
                atoms,
                timestep=timestep,
                temperature_K=self.calc_config["temperature_K"],
                taut=self.calc_config["taut_fs"] * units.fs,
                fixcm=False,
                **common,
            )
        if algorithm == "nptberendsen":
            compressibility = self.calc_config.get("compressibility_bar_inv")
            compressibility_au = None
            if compressibility is not None:
                compressibility_au = compressibility / (1e5 * units.Pascal)
            return NPTBerendsen(
                atoms,
                timestep=timestep,
                temperature_K=self.calc_config["temperature_K"],
                pressure_au=self.calc_config["pressure_bar"] * units.bar,
                taut=self.calc_config["taut_fs"] * units.fs,
                taup=self.calc_config["taup_fs"] * units.fs,
                compressibility_au=compressibility_au,
                fixcm=False,
                **common,
            )
        raise ValueError(f"Unsupported ASE MD algorithm: {self.calc_config['algorithm']}")

    def _summary(self, atoms: Atoms) -> dict[str, Any]:
        try:
            energy = float(atoms.get_potential_energy())
        except Exception:
            energy = None
        try:
            temperature = float(atoms.get_temperature())
        except Exception:
            temperature = None
        return {
            "workflow": "md",
            "driver": "ase",
            "ensemble": self.calc_config["ensemble"],
            "algorithm": self.calc_config["algorithm"],
            "steps": self.calc_config["steps"],
            "final_energy_eV": energy,
            "final_temperature_K": temperature,
            "trajectory": self.calc_config["trajectory"],
            "final_structure": self.calc_config["final_structure"],
        }

    def run(self) -> None:
        atoms = self._read_atoms()
        atoms.calc = CalculatorFactory.get_calculator(
            self.calc_name,
            self.config,
            directory=self.calc_config["directory"],
        )
        self._initialize_velocities(atoms)
        dynamics = self._build_dynamics(atoms)
        dynamics.run(self.calc_config["steps"])
        write(self.calc_config["final_structure"], atoms)
        summary = self._summary(atoms)
        _json_write(self.calc_config["summary_file"], summary)
        write_artifact_manifest(
            self.calc_config["artifact_manifest"],
            workflow="md",
            artifacts=[
                {"role": "trajectory", "path": self.calc_config["trajectory"]},
                {"role": "log", "path": self.calc_config["logfile"]},
                {"role": "summary", "path": self.calc_config["summary_file"]},
                {"role": "final_structure", "path": self.calc_config["final_structure"]},
            ],
            stages=[{"name": "ase_md", "status": "complete", "steps": self.calc_config["steps"]}],
            metadata=summary,
        )


class AbacusNativeMDRunner:
    """ABACUS-native MD driver with ATST input preparation and output collection."""

    def __init__(self, config: dict[str, Any], calc_name: str, calc_config: dict[str, Any]):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.run_dir = Path(calc_config["directory"]).resolve()

    def _validate(self) -> None:
        if self.calc_name != "abacus":
            raise ValueError("calculation.driver=abacus_native requires calculator.name=abacus")
        parameters = _merged_abacus_parameters(_abacus_section(self.config))
        if str(parameters.get("calculation", "")).lower() != "md":
            raise ValueError("ABACUS native MD requires calculator.abacus.parameters.calculation: md")

    def _prepare_inputs(self) -> None:
        if self.calc_config.get("restart"):
            return
        targets = [self.run_dir / "INPUT", self.run_dir / "KPT", self.run_dir / "STRU"]
        existing = [path.name for path in targets if path.exists()]
        if existing:
            raise FileExistsError(
                "Refusing to overwrite existing ABACUS native MD input file(s): "
                + ", ".join(existing)
            )
        self.run_dir.mkdir(parents=True, exist_ok=True)
        abacus = _abacus_section(self.config)
        parameters = _merged_abacus_parameters(abacus)
        atoms = read_structure(self.calc_config["init_structure"])
        generalio = _import_generalio()
        kpts = _as_mp_kpts(parameters.get("kpts", abacus.get("kpts", [1, 1, 1])))
        generalio.write_input(_input_parameters(parameters), str(self.run_dir / "INPUT"))
        generalio.write_kpt(kpts, str(self.run_dir / "KPT"))
        generalio.write_stru(
            atoms,
            str(self.run_dir),
            parameters.get("pseudopotentials"),
            parameters.get("basissets"),
            "STRU",
        )

    def _command(self) -> list[str]:
        abacus = _abacus_section(self.config)
        command = _build_abacus_command(abacus.get("command", "abacus"), int(abacus.get("mpi", 1)))
        return shlex.split(command)

    def _start_process(self):
        abacus = _abacus_section(self.config)
        os.environ["OMP_NUM_THREADS"] = str(int(abacus.get("omp", 1)))
        stdout_path = self.run_dir / "atst_abacus_native_md.out"
        stderr_path = self.run_dir / "atst_abacus_native_md.err"
        stdout = stdout_path.open("w", encoding="utf-8")
        stderr = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                self._command(),
                cwd=str(self.run_dir),
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
        finally:
            stdout.close()
            stderr.close()
        return process

    def _read_frames_from_md_dump(self) -> list[Atoms]:
        dump = self.run_dir / "MD_dump"
        if not dump.exists():
            return []
        read_traj_from_md_dump = _import_legacyio()
        frames = []
        for frame in read_traj_from_md_dump(dump):
            atoms = Atoms(
                symbols=frame["elem"],
                positions=frame["coords"],
                cell=frame["cell"],
                pbc=True,
            )
            frames.append(atoms)
        return frames

    def _collect_frames(self) -> list[Atoms]:
        log = self.run_dir / "running_md.log"
        dump = self.run_dir / "MD_dump"
        eig = self.run_dir / "eig_occ.txt"
        if log.exists() and dump.exists() and eig.exists():
            read_abacus_out = _import_latestio()
            with tempfile.TemporaryDirectory() as tmp:
                tmpdir = Path(tmp)
                shutil.copy2(log, tmpdir / "running_md.log")
                shutil.copy2(dump, tmpdir / "MD_dump")
                shutil.copy2(eig, tmpdir / "eig_occ.txt")
                parsed = read_abacus_out(tmpdir / "running_md.log")
            return parsed if isinstance(parsed, list) else [parsed]
        return self._read_frames_from_md_dump()

    def _stderr_tail(self) -> str:
        path = self.run_dir / "atst_abacus_native_md.err"
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-20:])

    def _write_progress(self, *, returncode: int | None = None) -> None:
        frames = self._read_frames_from_md_dump()
        _json_write(
            self.run_dir / "md_progress.json",
            {
                "workflow": "md",
                "driver": "abacus_native",
                "run_dir": str(self.run_dir),
                "frames": len(frames),
                "returncode": returncode,
            },
        )

    def _communicate_with_monitor(self, process) -> None:
        poll = getattr(process, "poll", None)
        if poll is None:
            process.communicate(timeout=self.calc_config.get("timeout_seconds"))
            return

        timeout = self.calc_config.get("timeout_seconds")
        deadline = time.monotonic() + timeout if timeout is not None else None
        poll_interval = float(self.calc_config["poll_interval_seconds"])
        while poll() is None:
            self._write_progress(returncode=None)
            if deadline is not None and time.monotonic() >= deadline:
                process.kill()
                process.communicate()
                self._write_progress(returncode=process.returncode)
                raise TimeoutError(
                    f"ABACUS native MD exceeded timeout_seconds={timeout}. "
                    f"Run directory: {self.run_dir}"
                )
            time.sleep(poll_interval)
        process.communicate()
        self._write_progress(returncode=process.returncode)

    def _write_summary(self, *, returncode: int | None, frames: list[Atoms], error: str | None = None) -> dict[str, Any]:
        summary = {
            "workflow": "md",
            "driver": "abacus_native",
            "run_dir": str(self.run_dir),
            "returncode": returncode,
            "frames": len(frames),
            "trajectory": self.calc_config["trajectory"],
            "final_structure": self.calc_config["final_structure"],
            "error": error,
            "stderr_tail": self._stderr_tail(),
        }
        _json_write(self.calc_config["summary_file"], summary)
        return summary

    def _write_manifest(self, summary: dict[str, Any], *, status: str) -> None:
        write_artifact_manifest(
            self.calc_config["artifact_manifest"],
            workflow="md",
            artifacts=[
                {"role": "trajectory", "path": self.calc_config["trajectory"]},
                {"role": "summary", "path": self.calc_config["summary_file"]},
                {"role": "final_structure", "path": self.calc_config["final_structure"]},
                {"role": "progress", "path": str(self.run_dir / "md_progress.json")},
                {"role": "abacus_stdout", "path": str(self.run_dir / "atst_abacus_native_md.out")},
                {"role": "abacus_stderr", "path": str(self.run_dir / "atst_abacus_native_md.err")},
            ],
            stages=[
                {
                    "name": "abacus_native_md",
                    "status": status,
                    "returncode": summary.get("returncode"),
                }
            ],
            metadata=summary,
        )

    def run(self) -> None:
        self._validate()
        self._prepare_inputs()
        process = self._start_process()
        self._communicate_with_monitor(process)
        frames = self._collect_frames()
        if frames:
            write(self.calc_config["trajectory"], frames)
            write(self.calc_config["final_structure"], frames[-1])
        summary = self._write_summary(returncode=process.returncode, frames=frames)
        self._write_manifest(summary, status="failed" if process.returncode else "complete")
        if process.returncode:
            raise RuntimeError(
                f"ABACUS native MD failed with return code {process.returncode}. "
                f"Run directory: {self.run_dir}. Stderr tail: {self._stderr_tail()}"
            )
