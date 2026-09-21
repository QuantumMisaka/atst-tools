"""Locate the layer that forces an explicit OMP budget during CP evaluation.

Diagnostic only: patches the two OMP entry points, prints the caller chain, and
then runs the ordinary API runner so the real workflow executes unchanged.
"""

from __future__ import annotations

import os
import sys
import traceback

from atst_tools.calculators import factory
from atst_tools.runtime import launch

_orig_factory = factory.AbacusFactory.get_calculator
_orig_apply = launch.apply_explicit_omp


def traced_factory(cls, config, **kwargs):
    """Print the OMP inputs of every ABACUS calculator construction."""
    section = factory._abacus_section(config)
    parameters = section.get("parameters") or {}
    print(
        "[probe] AbacusFactory.get_calculator omp_kwarg=%r section_omp=%r "
        "parameters_omp=%r kwargs=%s"
        % (kwargs.get("omp"), section.get("omp"), parameters.get("omp"), sorted(kwargs)),
        flush=True,
    )
    return _orig_factory(cls, config, **kwargs)


def traced_apply(value, **kwargs):
    """Print the caller chain of every explicit OMP application."""
    print(
        "[probe] apply_explicit_omp(value=%r) inherited=%r"
        % (value, os.environ.get("OMP_NUM_THREADS")),
        flush=True,
    )
    for frame in traceback.extract_stack():
        if "atst_tools" in frame.filename:
            print(
                "    %s:%d in %s"
                % (frame.filename.split("atst_tools/")[-1], frame.lineno, frame.name),
                flush=True,
            )
    return _orig_apply(value, **kwargs)


factory.AbacusFactory.get_calculator = staticmethod(traced_factory)
launch.apply_explicit_omp = traced_apply
launch.resolve_calculator_omp.__globals__["apply_explicit_omp"] = traced_apply

from atst_tools.api.runner import main  # noqa: E402

sys.exit(main())
