"""Time the CCQN CPU-side wall with a stand-in calculator (no DP, no GPU)."""

from __future__ import annotations

import json
import sys
import time

import numpy as np
from ase.calculators.calculator import Calculator, all_changes

from atst_tools.calculators import factory


class StandIn(Calculator):
    implemented_properties = ["energy", "forces"]
    calls = 0

    def calculate(self, atoms=None, properties=("energy", "forces"), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        StandIn.calls += 1
        positions = atoms.get_positions()
        self.results["energy"] = float(np.sum(positions * positions) * 1e-2)
        self.results["forces"] = (-2e-2 * positions).astype(float)


def fake_get_calculator(name, config, **kwargs):
    return StandIn()


factory.CalculatorFactory.get_calculator = staticmethod(fake_get_calculator)

from atst_tools.api import RunOptions, run_workflow  # noqa: E402
from atst_tools.utils.config import ConfigLoader  # noqa: E402

config = ConfigLoader.load(sys.argv[1])
started = time.monotonic()
result = run_workflow(config, RunOptions())
wall = time.monotonic() - started
print(json.dumps({
    "mode": "stand_in",
    "wall_s": round(wall, 3),
    "force_calls": StandIn.calls,
    "per_call_s": round(wall / StandIn.calls, 4) if StandIn.calls else None,
    "status": result.status,
}))
