"""Resolve the ABACUS ASE backend used by ATST-Tools."""

from __future__ import annotations

from typing import Literal


BackendSource = Literal["external", "vendored"]


def _load_abacuslite_backend():
    try:
        from abacuslite import Abacus, AbacusProfile

        return Abacus, AbacusProfile, "external"
    except ImportError:
        from atst_tools.external.ASE_interface.abacuslite import Abacus, AbacusProfile

        return Abacus, AbacusProfile, "vendored"


Abacus, AbacusProfile, BACKEND_SOURCE = _load_abacuslite_backend()

__all__ = ["Abacus", "AbacusProfile", "BACKEND_SOURCE", "BackendSource"]
