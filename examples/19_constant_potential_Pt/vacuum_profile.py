"""Reproduce ABACUS's density-minimum vacuum estimator from saved cubes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from ase.io.cube import read_cube
from ase.units import Ry


def profile(directory: Path, axis: int) -> dict:
    """Return planar profiles and the seven-point density-minimum estimator."""
    with (directory / "ElecStaticPot.cube").open() as stream:
        potential = read_cube(stream)
    with (directory / "SPIN1_CHG.cube").open() as stream:
        charge = read_cube(stream)
    rho = charge["data"]
    if (directory / "SPIN2_CHG.cube").exists():
        with (directory / "SPIN2_CHG.cube").open() as stream:
            rho = rho + read_cube(stream)["data"]
    axes = tuple(i for i in range(3) if i != axis)
    density = np.mean(np.abs(rho), axis=axes)
    voltage = np.mean(potential["data"], axis=axes) * Ry
    smooth = sum(weight * np.roll(density, 3 - offset) for offset, weight in enumerate((.1, .2, .3, .4, .3, .2, .1)))
    index = int(np.argmin(smooth))
    coordinate = np.arange(len(density)) / len(density) * np.linalg.norm(potential["atoms"].cell[axis])
    return {"axis": axis, "grid_points": len(density), "selected_index": index, "selected_coordinate_angstrom": float(coordinate[index]), "vacuum_ev_from_cube": float(voltage[index]), "position_angstrom": coordinate.tolist(), "density": density.tolist(), "electrostatic_potential_ev": voltage.tolist(), "definition": "ABACUS v3.10.1 seven-point smoothed minimum absolute density; cube precision may differ from log"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--axis", type=int, choices=(0, 1, 2), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = profile(args.directory, args.axis)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("selected_index", "selected_coordinate_angstrom", "vacuum_ev_from_cube")}))
