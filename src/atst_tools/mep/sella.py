# AbacusSella implementation
# part of ATST-Tools
#
# References:
#     Sella transition-state search algorithm:
#     Ásgeirsson, V.; Birgisson, B. O.; Bjornsson, R.; Becker, U.; Neese, F.;
#     Jónsson, H. Sella, an Open-Source Chemical Kinetics Environment.
#     J. Chem. Theory Comput. 18 (8), 4914-4930 (2022).
#     https://doi.org/10.1021/acs.jctc.2c00395

from __future__ import annotations

import inspect
from collections.abc import Mapping
from numbers import Integral

from ase.io import Trajectory
from sella import Sella

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.convergence import (
    StageRecord,
    as_finite_float,
    as_step_count,
    emit_unconverged_advisory,
)
from atst_tools.utils.sella_events import (
    SellaEventRecorder,
    event_path_for_trajectory,
    trajectory_sha256,
)


def _supports_parameter(callable_obj, name: str) -> bool:
    """Return whether a callable exposes a named, explicit parameter."""

    try:
        return name in inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False


def _frame_index(dyn) -> int | None:
    """Read Sella's trajectory ID without deriving one from frame counts."""

    pes = getattr(dyn, "pes", None)
    current = getattr(pes, "curr", None)
    if isinstance(current, Mapping):
        value = current.get("traj_id")
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, Integral):
            return None
        return int(value)
    return None


def _convergence_signal(value) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _trajectory_frames(traj) -> int | None:
    try:
        return int(len(traj))
    except (TypeError, AttributeError):
        return None


def _close_trajectory(traj) -> None:
    close = getattr(traj, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            # A cleanup error must not replace the original calculation
            # exception or turn telemetry into a new runtime failure.
            pass

class AbacusSella:
    """
    Customize Sella calculation workflow by using ABACUS.

    This class manages the setup and execution of the Sella method for finding
    saddle points (Transition States) using ABACUS as the force calculator.

    Attributes:
        init_Atoms (Atoms): Initial structure (guess for TS).
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
        traj_file (str): Output trajectory file.
        sella_eta (float): Sella eta parameter.
        fmax (float): Force convergence criterion.

    References:
        Ásgeirsson, V.; Birgisson, B. O.; Bjornsson, R.; Becker, U.; Neese, F.;
        Jónsson, H. Sella, an Open-Source Chemical Kinetics Environment.
        J. Chem. Theory Comput. 18 (8), 4914-4930 (2022).
        https://doi.org/10.1021/acs.jctc.2c00395
    """
    
    def __init__(self, init_Atoms, config, calc_name, calc_config,
                 traj_file='run_sella.traj',
                 sella_eta=0.005,
                 fmax=0.05,
                 order=1,
                 record_events=None,
                 hessian_progress=None):
        """
        Initialize Sella method by using ASE-ABACUS.

        Args:
            init_Atoms (Atoms): Initial Atoms object.
            config (dict): Global configuration dictionary.
            calc_name (str): Name of the calculator.
            calc_config (dict): Calculation configuration dictionary.
            traj_file (str): Path to output trajectory file.
            sella_eta (float): Sella eta parameter.
            fmax (float): Force convergence criterion.
            order (int): Saddle-point order.
            record_events (bool, optional): Write the optimizer/Hessian JSONL
                sidecar. ``None`` reads the calculation setting, defaulting
                to ``True``.
            hessian_progress (bool, optional): Enable Sella's native textual
                Hessian progress callback. ``None`` reads the calculation
                setting, defaulting to ``False``.
        """
        self.init_Atoms = init_Atoms
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.traj_file = traj_file
        self.sella_eta = sella_eta
        self.fmax = fmax
        self.order = order
        self.max_steps = calc_config.get('max_steps')
        self.record_events = (
            bool(calc_config.get("record_events", True))
            if record_events is None else bool(record_events)
        )
        self.hessian_progress = (
            bool(calc_config.get("hessian_progress", False))
            if hessian_progress is None else bool(hessian_progress)
        )
        self.events_file = event_path_for_trajectory(self.traj_file)
        self.last_events_file = str(self.events_file) if self.record_events else None
        
    def set_calculator(self):
        """
        Set calculators using Factory.

        Returns:
            Calculator: Configured calculator instance.
        """
        directory = self.calc_config.get('directory', 'sella_run')
        if 'abacus' in self.config:
             directory = self.config['abacus'].get('directory', directory)
        
        return CalculatorFactory.get_calculator(
            self.calc_name, 
            self.config, 
            directory=directory
        )
    
    def run(self, fmax=None):
        """Run Sella and persist its durable convergence record.

        Args:
            fmax (float, optional): Force convergence criterion.

        Returns:
            Atoms: The optimized transition state structure.  The optimizer's
            ``run()`` return value (or the final value yielded by ``irun()``)
            is the authoritative convergence signal: a known ``False`` prints
            one shared English advisory and is recorded in the manifest without
            changing the returned structure. The record is also exposed as
            ``last_stage_record`` for nesting workflows, and an explicit
            programmatic ``artifact_manifest=None`` (internal contract used by
            nested D2S; not a YAML field) disables the manifest write so only
            the owning workflow (D2S) writes one. When event recording is
            enabled, ``last_events_file`` identifies the JSONL sidecar; its
            ``run_end`` record carries the trajectory hash and frame count.
        """
        if fmax is None:
            fmax = self.fmax

        supports_hessian_progress = _supports_parameter(Sella, "hessian_progress")
        if self.hessian_progress and not supports_hessian_progress:
            raise RuntimeError(
                "Sella hessian_progress=True was requested, but the installed "
                "Sella constructor does not expose hessian_progress"
            )

        ts_atoms = self.init_Atoms
        ts_atoms.calc = self.set_calculator()
        
        # Setup Sella constraints if any
        # Sella handles constraints internally but we can also use ase constraints
        # cons = Constraints(ts_atoms) 
        # For now, we rely on Sella's default handling of ASE constraints
        
        traj = Trajectory(self.traj_file, 'w', ts_atoms)

        recorder = SellaEventRecorder(self.events_file, enabled=self.record_events)
        sella_kwargs = {
            "trajectory": traj,
            "eta": self.sella_eta,
            "order": self.order,
        }
        if supports_hessian_progress:
            sella_kwargs["hessian_progress"] = self.hessian_progress
        try:
            dyn = Sella(ts_atoms, **sella_kwargs)
            diag = getattr(getattr(dyn, "pes", None), "diag", None)
            diagkwargs = getattr(dyn, "diagkwargs", None)
            supports_progress = (
                callable(diag)
                and _supports_parameter(diag, "progress")
                and isinstance(diagkwargs, dict)
                and "progress" in diagkwargs
            )
            if self.hessian_progress and not supports_progress:
                raise RuntimeError(
                    "Sella hessian_progress=True was requested, but the "
                    "optimizer PES does not expose diag(progress=...) and "
                    "diagkwargs['progress']"
                )

            current_state = getattr(getattr(dyn, "pes", None), "curr", None)
            frame_capability = isinstance(current_state, Mapping) and "traj_id" in current_state
            irun = getattr(dyn, "irun", None)
            capabilities = {
                "events": recorder.available,
                "hessian_progress": supports_progress,
                "trajectory_frame_id": frame_capability,
                "optimizer_checkpoints": callable(irun),
            }
            native_progress = diagkwargs.get("progress") if supports_progress else None
            if self.record_events and supports_progress:
                def progress(event, evaluations):
                    # The native callback remains first so its exception and
                    # ordering semantics are unchanged for callers that opted
                    # into human-readable Hessian progress.
                    if native_progress is not None:
                        native_progress(event, evaluations)
                    current_step = int(getattr(dyn, "nsteps", 0))
                    pes = getattr(dyn, "pes", None)
                    frame_index = getattr(pes, "_last_eval_traj_id", None)
                    recorder.hessian(
                        event,
                        optimizer_step=current_step,
                        evaluations=int(evaluations),
                        frame_index=frame_index if event == "evaluation" else None,
                    )

                diagkwargs["progress"] = progress

            recorder.run_start(trajectory=self.traj_file, capabilities=capabilities)
            converged_signal = None
            last_converged = None
            if self.record_events and callable(irun):
                yielded = False
                run_kwargs = {"fmax": fmax}
                if self.max_steps is not None:
                    run_kwargs["steps"] = self.max_steps
                for signal in irun(**run_kwargs):
                    yielded = True
                    converged_signal = _convergence_signal(signal)
                    last_converged = converged_signal
                    event_name = "initial_state" if int(getattr(dyn, "nsteps", 0)) == 0 else "optimizer_step"
                    recorder.state(
                        event_name,
                        optimizer_step=int(getattr(dyn, "nsteps", 0)),
                        frame_index=_frame_index(dyn),
                        converged=converged_signal,
                    )
                if not yielded:
                    converged_signal = None
            else:
                # Keep the original run path when event recording is disabled
                # or an older Sella API has no public irun() generator.
                run_kwargs = {"fmax": fmax}
                if self.max_steps is not None:
                    run_kwargs["steps"] = self.max_steps
                converged_signal = _convergence_signal(dyn.run(**run_kwargs))
                last_converged = converged_signal
        except Exception as exc:
            recorder.run_failed(
                actual_steps=int(getattr(locals().get("dyn", None), "nsteps", 0)),
                converged=locals().get("last_converged"),
                error=exc,
            )
            _close_trajectory(traj)
            recorder.close()
            raise

        frames = _trajectory_frames(traj) if self.record_events else None
        _close_trajectory(traj)
        recorder.run_end(
            actual_steps=int(getattr(dyn, "nsteps", 0)),
            converged=converged_signal,
            trajectory_digest=(trajectory_sha256(self.traj_file) if self.record_events else None),
            trajectory_frames=frames,
        )
        recorder.close()
        record = StageRecord(
            name="sella",
            role="final",
            criterion="sella_projected_force+constraint",
            converged=converged_signal,
            fmax=as_finite_float(fmax),
            steps=as_step_count(self.max_steps),
            actual_steps=as_step_count(getattr(dyn, "nsteps", None)),
        )
        emit_unconverged_advisory(record, workflow="sella")
        # Expose the same record to callers (e.g. nested D2S refinement) so the
        # owning workflow can persist the facts without re-deriving them.
        self.last_stage_record = record
        # An explicit ``None`` disables the manifest, which lets a nesting
        # workflow (D2S) stay the only writer of the top-level manifest.
        manifest_path = self.calc_config.get("artifact_manifest", "atst_artifacts.json")
        if manifest_path is not None:
            artifacts = [{"role": "trajectory", "path": self.traj_file}]
            if self.record_events:
                artifacts.append({"role": "optimizer_events", "path": str(self.events_file)})
            write_artifact_manifest(
                manifest_path,
                workflow="sella",
                artifacts=artifacts,
                stages=[record.to_manifest()],
            )
        return ts_atoms
