"""Stable public Python API for ATST-Tools.

The package body stays import-light (PEP 562): heavy modules are resolved on
first attribute access so the runtime layer can bind devices before the
scientific stack is imported.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "CCQNOptions",
    "RunOptions",
    "WorkflowResult",
    "validate_config",
    "run_workflow",
    "run_ccqn",
    "neb_energy_profile",
    "sella_energy_curve",
    "ccqn_energy_curve",
    "build_config_from_abacus_dir",
    "RuntimeBindingError",
]

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "CCQNOptions": ("atst_tools.api.models", "CCQNOptions"),
    "RunOptions": ("atst_tools.api.models", "RunOptions"),
    "WorkflowResult": ("atst_tools.api.models", "WorkflowResult"),
    "validate_config": ("atst_tools.api.services", "validate_config"),
    "run_workflow": ("atst_tools.api.services", "run_workflow"),
    "run_ccqn": ("atst_tools.api.services", "run_ccqn"),
    "neb_energy_profile": ("atst_tools.utils.plot", "neb_energy_profile"),
    "sella_energy_curve": ("atst_tools.utils.plot", "sella_energy_curve"),
    "ccqn_energy_curve": ("atst_tools.utils.plot", "ccqn_energy_curve"),
    "build_config_from_abacus_dir": (
        "atst_tools.utils.reverse_config",
        "build_config_from_abacus_dir",
    ),
    "RuntimeBindingError": ("atst_tools.runtime.errors", "RuntimeBindingError"),
}


def __getattr__(name: str) -> Any:
    """Resolve one public API attribute lazily and cache it on the module."""
    try:
        module_name, attribute = _LAZY_ATTRS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(importlib.import_module(module_name), attribute)
    globals()[name] = value
    return value
