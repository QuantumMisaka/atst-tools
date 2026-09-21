"""Measure the DP per-call warm-up shape on the site GPU torch."""

from __future__ import annotations

import json
import time
from pathlib import Path

from ase.io import read

import torch
from deepmd.pt.utils import env as deepmd_env

from atst_tools.calculators.factory import CalculatorFactory

HOME = Path.home()
model = HOME / "atst-p5-20260921/models/model.ckpt-100000.pt"
structure = HOME / "atst-ccqn-20260921/cases/ccqn-h2au/ccqn_init.extxyz"

print(json.dumps({
    "torch": torch.__version__,
    "torch_cuda": torch.cuda.is_available(),
    "deepmd_device": str(getattr(deepmd_env, "DEVICE", None)),
    "torch_threads": torch.get_num_threads(),
}), flush=True)

started = time.monotonic()
config = {
    "calculator": {
        "name": "dp",
        "dp": {"model": str(model), "share_calculator": True},
    }
}
calculator = CalculatorFactory.get_calculator("dp", config)
constructed = time.monotonic()

atoms = read(str(structure))
atoms.calc = calculator
walls = []
for _ in range(5):
    atoms.rattle(0.02)
    tick = time.monotonic()
    atoms.get_potential_energy()
    atoms.get_forces()
    walls.append(round(time.monotonic() - tick, 3))

print(json.dumps({
    "construct_s": round(constructed - started, 3),
    "calls_s": walls,
    "natoms": len(atoms),
}), flush=True)
