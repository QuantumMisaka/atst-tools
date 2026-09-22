"""DeepMD-kit ASE calculator adapter."""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Hashable

from ase.calculators.calculator import Calculator

from atst_tools.runtime import counters as runtime_counters
from atst_tools.runtime import launch as runtime_launch

#: Raw DeepMD-kit PT checkpoint (``dp --pt train`` output).
DP_KIND_PT_CHECKPOINT = "pt_checkpoint"
#: Frozen DeepMD-kit PT archive (``dp --pt freeze`` output, TorchScript).
DP_KIND_FROZEN_ARCHIVE = "frozen_archive"
#: Frozen DeepMD-kit TF graph.
DP_KIND_TF_GRAPH = "tf_graph"
#: An artifact with no known DeepMD-kit suffix.
DP_KIND_UNKNOWN = "unknown"

#: Backend that owns each artifact kind; ``None`` when the kind is unknown.
DP_BACKEND_BY_KIND: Dict[str, str | None] = {
    DP_KIND_PT_CHECKPOINT: "pt",
    DP_KIND_FROZEN_ARCHIVE: "pt",
    DP_KIND_TF_GRAPH: "tf",
    DP_KIND_UNKNOWN: None,
}

_KIND_BY_SUFFIX = {
    ".pt": DP_KIND_PT_CHECKPOINT,
    ".pth": DP_KIND_FROZEN_ARCHIVE,
    ".pb": DP_KIND_TF_GRAPH,
    ".pbtxt": DP_KIND_TF_GRAPH,
}

#: Artifact kinds whose operator signatures are pinned to a deepmd-kit build.
_PT_ARTIFACT_KINDS = (DP_KIND_PT_CHECKPOINT, DP_KIND_FROZEN_ARCHIVE)

#: TorchScript messages that mean "this artifact was built elsewhere".
_OPERATOR_MISMATCH_MARKERS = (
    "unknown keyword argument",
    "unknown builtin op",
    "unknown operator",
)

_HEADS_PATTERN = re.compile(r"Available heads are:\s*(\[[^\]]*\])")
_MISSING_HEAD_MARKERS = ("head must be set for multitask model",)
_UNKNOWN_HEAD_MARKERS = ("no head or alias named",)
_BRANCH_COMMAND = "dp --pt show"


class DeepPotentialError(RuntimeError):
    """Actionable DeepMD-kit artifact or evaluation failure of the DP adapter."""


def dp_model_kind(model: str | os.PathLike[str] | None) -> str:
    """Return the DeepMD-kit artifact kind implied by the artifact itself.

    Args:
        model: Path of the artifact, or ``None`` when no model was resolved.

    Returns:
        One of :data:`DP_KIND_PT_CHECKPOINT`, :data:`DP_KIND_FROZEN_ARCHIVE`,
        :data:`DP_KIND_TF_GRAPH` or :data:`DP_KIND_UNKNOWN`.  The check is a
        pure suffix test: it never touches the file system.
    """
    if model is None:
        return DP_KIND_UNKNOWN
    suffix = Path(str(model)).suffix.lower()
    return _KIND_BY_SUFFIX.get(suffix, DP_KIND_UNKNOWN)


def dp_available_heads_from_message(message: str) -> list[str] | None:
    """Extract the model branch list DeepMD-kit prints in its head errors.

    Args:
        message: Text of a DeepMD-kit error, typically the multi-task
            ``AssertionError`` of ``deepmd.infer.DeepPot``.

    Returns:
        The branch names in message order, or ``None`` when the text carries no
        parseable list, so callers fall back to the ``dp --pt show`` command.
    """
    match = _HEADS_PATTERN.search(message or "")
    if match is None:
        return None
    try:
        parsed = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return None
    if not isinstance(parsed, (list, tuple)):
        return None
    heads = [str(name).strip() for name in parsed if str(name).strip()]
    return heads or None


def dp_error_from_exception(
    exc: BaseException,
    *,
    model: str | os.PathLike[str] | None,
    head: str | None = None,
) -> DeepPotentialError | None:
    """Translate a DeepMD-kit failure into an actionable ATST-Tools error.

    Two DeepMD-kit failure modes have an action attached and are translated:
    a multi-task PT model used without a usable branch, which DeepMD-kit raises
    as a bare ``AssertionError``, and an operator mismatch of an artifact whose
    operators are pinned to another deepmd-kit build, which only shows up at the
    first evaluation of a frozen archive.

    Args:
        exc: Exception raised by DeepMD-kit.
        model: Path of the artifact that was being loaded or evaluated.
        head: Branch requested for the artifact, when one was configured.

    Returns:
        The actionable :class:`DeepPotentialError`, or ``None`` when the failure
        carries no ATST-Tools action and must stay untouched.
    """
    message = str(exc)
    lowered = message.lower()
    artifact = str(model) if model is not None else "<model>"

    if any(marker in lowered for marker in _MISSING_HEAD_MARKERS):
        heads = dp_available_heads_from_message(message)
        return DeepPotentialError(
            f"DeepMD-kit multi-task model {artifact} needs a model branch: set "
            f"calculator.dp.head (or pass head=) to one of "
            f"{heads if heads else 'its branches'}. List the branches with "
            f"`{_BRANCH_COMMAND} {artifact} model-branch`."
        )

    if any(marker in lowered for marker in _UNKNOWN_HEAD_MARKERS):
        heads = dp_available_heads_from_message(message)
        return DeepPotentialError(
            f"DeepMD-kit model {artifact} has no branch named {head!r}: "
            f"available heads are {heads if heads else 'not reported by deepmd-kit'}. "
            f"Set calculator.dp.head to one of them; list the branches with "
            f"`{_BRANCH_COMMAND} {artifact} model-branch`."
        )

    kind = dp_model_kind(model)
    if any(marker in lowered for marker in _OPERATOR_MISMATCH_MARKERS) and (
        kind in _PT_ARTIFACT_KINDS
    ):
        if kind == DP_KIND_FROZEN_ARCHIVE:
            return DeepPotentialError(
                f"The frozen DeepMD-kit archive {artifact} was produced by another "
                f"deepmd-kit build and cannot run here ({message}). A frozen archive "
                f"pins the operator signatures of the build that created it: "
                f"re-freeze the checkpoint for this build "
                f"(`dp --pt freeze -c <checkpoint> -o <archive> [--head <branch>]`), "
                f"use the original checkpoint model (*.pt) instead, or install the "
                f"deepmd-kit build that matches the archive."
            )
        return DeepPotentialError(
            f"The DeepMD-kit checkpoint {artifact} needs operators that this "
            f"deepmd-kit build does not provide ({message}). Use a deepmd-kit "
            f"build matching the checkpoint, or a frozen archive (*.pth) "
            f"produced for this build."
        )
    return None


def _dp_artifact_path(model: str | os.PathLike[str]) -> Path:
    """Return the resolved, readable artifact path or fail closed."""
    path = Path(os.path.expanduser(str(model))).resolve()
    if not path.is_file():
        raise DeepPotentialError(f"DeepMD-kit model artifact not found: {path}")
    if path.stat().st_size == 0:
        raise DeepPotentialError(f"DeepMD-kit model artifact is empty: {path}")
    try:
        with path.open("rb") as handle:
            handle.read(1)
    except OSError as exc:
        raise DeepPotentialError(
            f"DeepMD-kit model artifact is not readable: {path} ({exc})"
        ) from exc
    return path


def _read_backend_fact(backend: Any, name: str) -> Any:
    """Read one optional backend fact, returning ``None`` when unavailable."""
    method = getattr(backend, name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:  # pragma: no cover - backend specific metadata
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def _call_or_none(target: Any, name: str) -> Any:
    """Call one optional backend method, returning ``None`` on any failure."""
    method = getattr(target, name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:  # pragma: no cover - backend specific metadata
        return None


def _branch_facts(
    deep_pot: Any,
) -> tuple[bool | None, list[str] | None, list[str] | None]:
    """Return the multi-task flag, the branch names and the full type map."""
    script = _call_or_none(deep_pot, "get_model_def_script")
    script = script if isinstance(script, dict) else {}
    model_dict = script.get("model_dict")
    shared_dict = script.get("shared_dict")

    deep_eval = getattr(deep_pot, "deep_eval", None)
    multi_task = getattr(deep_eval, "multi_task", None)
    multi_task = multi_task if isinstance(multi_task, bool) else None
    if multi_task is None and isinstance(model_dict, dict):
        multi_task = True

    heads: list[str] | None = None
    if multi_task:
        if isinstance(model_dict, dict) and model_dict:
            heads = sorted(str(name) for name in model_dict)
        else:
            branches = _call_or_none(deep_eval, "get_model_branch")
            if (
                isinstance(branches, tuple)
                and branches
                and isinstance(branches[0], dict)
            ):
                heads = sorted(str(name) for name in branches[0])

    type_map_all = (
        shared_dict.get("type_map_all") if isinstance(shared_dict, dict) else None
    )
    if isinstance(type_map_all, list):
        type_map_all = [str(name) for name in type_map_all]
    else:
        type_map_all = None
    return multi_task, heads, type_map_all


def _deepmd_version() -> str | None:
    """Return the installed deepmd-kit version, or ``None`` when unavailable."""
    try:
        import deepmd
    except Exception:  # pragma: no cover - defensive
        return None
    version = getattr(deepmd, "__version__", None)
    return str(version) if version else None


def dp_model_identity(
    model: str | os.PathLike[str], head: str | None = None
) -> Dict[str, Any]:
    """Read the facts ATST-Tools can learn from a DP artifact without evaluating it.

    The artifact is loaded through the public ``deepmd.infer.DeepPot`` metadata
    API only: no energy, force or virial evaluation happens here, so the result
    is cheap to record as evidence.  Failures ATST-Tools can act on fail closed,
    every other backend failure is reported as ``metadata_error`` so the
    artifact-level facts (kind, backend, size) survive.

    Args:
        model: Path of the DeepMD-kit artifact.
        head: Multi-task branch, matching ``calculator.dp.head``.

    Returns:
        Artifact facts: ``kind``, ``backend``, ``head``, ``size_bytes``, the
        ``ntypes``/``rcut``/``type_map`` fingerprint, the multi-task branch list
        and the deepmd-kit version that read them.

    Raises:
        DeepPotentialError: The artifact is missing, empty, unreadable, or it
            cannot be used as requested (for example a multi-task PT model
            without a branch).
        ImportError: deepmd-kit is not installed.
    """
    path = _dp_artifact_path(model)
    kind = dp_model_kind(path)
    facts: Dict[str, Any] = {
        "model": str(path),
        "kind": kind,
        "backend": DP_BACKEND_BY_KIND.get(kind),
        "head": head,
        "size_bytes": path.stat().st_size,
        "deepmd_version": _deepmd_version(),
        "metadata_available": False,
        "available_heads": None,
        "type_map_all": None,
        "multi_task": None,
    }
    try:
        from deepmd.infer import DeepPot
    except ImportError as exc:
        raise ImportError(
            "deepmd-kit is not installed. Install it to inspect DeepMD-kit artifacts."
        ) from exc

    try:
        deep_pot = DeepPot(str(path), head=head)
    except Exception as exc:
        translated = dp_error_from_exception(exc, model=path, head=head)
        if translated is not None:
            raise translated from exc
        facts["metadata_error"] = f"{type(exc).__name__}: {exc}".splitlines()[0]
        return facts

    facts.update(
        {
            "metadata_available": True,
            "ntypes": _read_backend_fact(deep_pot, "get_ntypes"),
            "rcut": _read_backend_fact(deep_pot, "get_rcut"),
            "type_map": _read_backend_fact(deep_pot, "get_type_map"),
            "sel_type": _read_backend_fact(deep_pot, "get_sel_type"),
            "dim_fparam": _read_backend_fact(deep_pot, "get_dim_fparam"),
            "dim_aparam": _read_backend_fact(deep_pot, "get_dim_aparam"),
        }
    )
    multi_task, heads, type_map_all = _branch_facts(deep_pot)
    facts["multi_task"] = multi_task
    facts["available_heads"] = heads
    facts["type_map_all"] = type_map_all
    return facts


class _DPEvaluationGuard:
    """Mixin translating version-locked PT artifact failures at evaluation time."""

    atst_model: str | None = None
    atst_model_kind: str | None = None
    atst_model_backend: str | None = None
    atst_model_head: str | None = None

    def calculate(self, *args: Any, **kwargs: Any) -> Any:
        """Evaluate through the DeepMD-kit backend with translated failures."""
        try:
            return super().calculate(*args, **kwargs)
        except Exception as exc:
            translated = dp_error_from_exception(
                exc, model=self.atst_model, head=self.atst_model_head
            )
            if translated is None:
                raise
            raise translated from exc


_GUARDED_DP_CLASSES: Dict[type, type] = {}


def _guarded_dp_class(DP: type) -> type:
    """Return the evaluation-guarded subclass of one backend calculator class."""
    guarded = _GUARDED_DP_CLASSES.get(DP)
    if guarded is not None:
        return guarded
    try:
        guarded = type(
            f"ATST{DP.__name__}Guard",
            (_DPEvaluationGuard, DP),
            {
                "__doc__": f"ATST-Tools guarded {DP.__name__} DeepMD-kit calculator.",
                "__module__": __name__,
            },
        )
    except TypeError:  # pragma: no cover - backend is not a class
        guarded = DP
    _GUARDED_DP_CLASSES[DP] = guarded
    return guarded


def _record_artifact_facts(
    calculator: Calculator,
    *,
    model_path: str,
    kind: str,
    head: str | None,
) -> None:
    """Attach the artifact facts read by the guard and by the evidence layer."""
    facts = {
        "atst_model": model_path,
        "atst_model_kind": kind,
        "atst_model_backend": DP_BACKEND_BY_KIND.get(kind),
        "atst_model_head": head,
    }
    for name, value in facts.items():
        try:
            setattr(calculator, name, value)
        except Exception:  # pragma: no cover - recording must never break a build
            return


def is_dp_calculator(name: str) -> bool:
    """Return whether a calculator name refers to the DeepMD-kit adapter."""
    return name.lower() in {"dp", "deepmd"}


def dp_section(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return DeepMD-kit settings from supported config layouts."""
    calculator = config.get("calculator", {})
    if isinstance(calculator, dict):
        if "dp" in calculator:
            return dict(calculator.get("dp") or {})
        if calculator.get("name") == "deepmd":
            return dict(calculator.get("deepmd") or {})
    if "parameters" in config:
        return dict(config["parameters"])
    return {}


def dp_share_calculator(config: Dict[str, Any], default: bool = True) -> bool:
    """Return the configured DP calculator sharing policy."""
    return bool(dp_section(config).get("share_calculator", default))


def should_share_calculator(name: str, config: Dict[str, Any], parallel: bool = False) -> bool:
    """Return whether workflow images should share a single calculator instance."""
    return is_dp_calculator(name) and not parallel and dp_share_calculator(config)


def _normalize_type_dict(dp_params: Dict[str, Any]) -> dict[str, int] | None:
    type_map = dp_params.pop("type_map", None)
    type_dict = dp_params.pop("type_dict", None)
    if type_map is not None and type_dict is not None:
        raise ValueError("calculator.dp.type_map and calculator.dp.type_dict are mutually exclusive")
    if type_dict is not None:
        return {str(symbol): int(index) for symbol, index in dict(type_dict).items()}
    if type_map is None:
        return None
    return {str(symbol): index for index, symbol in enumerate(type_map)}


def _cache_key(model: str, params: Dict[str, Any]) -> tuple[Hashable, ...]:
    serializable = json.dumps(params, sort_keys=True, default=str)
    return (os.path.abspath(os.path.expanduser(model)), serializable)


class DeepPotentialFactory:
    """Factory for creating DeepMD-kit ASE calculators with optional sharing."""

    _instances: Dict[tuple[Hashable, ...], Calculator] = {}

    @staticmethod
    def get_calculator(
        config: Dict[str, Any],
        shared: bool | None = None,
        **kwargs: Any,
    ) -> Calculator:
        """Create a DeepMD-kit ASE calculator.

        The artifact decides the model kind (raw PT checkpoint, frozen PT
        archive, TF graph or unknown) before the backend is built, multi-task
        branch failures fail closed here, and the recorded facts are attached
        to the returned calculator as ``atst_model*`` attributes.

        Args:
            config: ATST-Tools configuration dictionary.
            shared: Override the configured calculator sharing policy.
            **kwargs: Workflow-local calculator construction hints.

        Returns:
            Configured ``deepmd.calculator.DP`` instance, guarded so that an
            operator mismatch of a version-locked PT artifact is reported as an
            actionable error instead of a raw TorchScript failure.

        Raises:
            ImportError: deepmd-kit is not installed.
            ValueError: The DP section is not a usable configuration.
            DeepPotentialError: The artifact cannot be used as requested.
        """
        try:
            from deepmd.calculator import DP
        except ImportError as exc:
            raise ImportError(
                "deepmd-kit is not installed. Install it to use the DP calculator."
            ) from exc

        dp_params = dp_section(config)
        dp_params.update(kwargs)

        model_file = dp_params.pop("model", None)
        if not model_file:
            raise ValueError("Missing required field calculator.dp.model")

        omp = dp_params.pop("omp", None)
        if omp is not None:
            runtime_launch.apply_explicit_omp(omp)

        share = dp_share_calculator(config) if shared is None else bool(shared)
        dp_params.pop("share_calculator", None)
        dp_params.pop("directory", None)

        type_dict = _normalize_type_dict(dp_params)
        constructor_params: Dict[str, Any] = dict(dp_params)
        if type_dict is not None:
            constructor_params["type_dict"] = type_dict

        key = _cache_key(model_file, constructor_params)
        if share and key in DeepPotentialFactory._instances:
            runtime_counters.increment("dp.calculator_reused")
            runtime_counters.set_gauge(
                "dp.cached_instances", len(DeepPotentialFactory._instances)
            )
            return DeepPotentialFactory._instances[key]

        # The artifact itself decides the kind; a multi-task PT model without a
        # usable branch fails closed here instead of leaking the bare
        # DeepMD-kit AssertionError to the workflow.
        model_path = os.path.abspath(os.path.expanduser(str(model_file)))
        kind = dp_model_kind(model_path)
        try:
            calc = _guarded_dp_class(DP)(model=model_file, **constructor_params)
        except Exception as exc:
            translated = dp_error_from_exception(
                exc, model=model_path, head=constructor_params.get("head")
            )
            if translated is not None:
                raise translated from exc
            raise
        _record_artifact_facts(
            calc,
            model_path=model_path,
            kind=kind,
            head=constructor_params.get("head"),
        )
        runtime_counters.instrument_calculator(
            calc,
            build_key="dp.calculator_built",
            call_key="dp.force_calls",
        )
        if share:
            DeepPotentialFactory._instances[key] = calc
        runtime_counters.set_gauge(
            "dp.cached_instances", len(DeepPotentialFactory._instances)
        )
        return calc
