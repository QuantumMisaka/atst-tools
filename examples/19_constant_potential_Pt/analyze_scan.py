"""Compare the reference grand-energy stationarity with the potential root."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import numpy as np

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"


def read_point(directory: Path) -> dict:
    """Read final scientific quantities from one completed ABACUS SCF log."""
    manifest = json.loads((directory / "fixture.json").read_text())
    log = directory / "OUT.CP/running_scf.log"
    text = log.read_text()
    if "charge density convergence is achieved" not in text:
        raise ValueError(f"SCF convergence not established: {log}")
    values = {}
    for key in ("E_KohnSham", "E_Fermi", "E_KS(sigma->0)", "E_entropy(-TS)", "E_gatefield"):
        rows = re.findall(r"^\s*" + re.escape(key) + r"\s+(" + NUMBER + r")\s+(" + NUMBER + r")", text, re.M)
        if not rows:
            raise ValueError(f"Missing {key}: {log}")
        values[key] = float(rows[-1][1].replace("D", "E"))
    vacuum = re.findall(r"The vacuum level is\s+(" + NUMBER + r")\s+eV", text)
    if not vacuum:
        raise ValueError(f"Missing vacuum reference: {log}")
    values["vacuum_ev"] = float(vacuum[-1].replace("D", "E").replace("d", "e"))
    values["mu_ev"] = values["E_Fermi"] - values["vacuum_ev"]
    values["electrons"] = manifest["electrons"]
    values["reference_electrons"] = manifest["neutral_electrons"]
    values["source"] = str(log)
    if not all(np.isfinite(v) for v in values.values() if isinstance(v, (float, int))):
        raise ValueError(f"Non-finite scientific quantity: {log}")
    return values


def derivative_diagnostics(steps, residuals, tolerance_ev=None, tolerance_reason=None):
    """Report numerical evidence; an optional user criterion is only a screen."""
    h = np.asarray(steps, dtype=float)
    r = np.asarray(residuals, dtype=float)
    if h.shape != (2,) or r.shape != (2,) or not np.isfinite([h, r]).all():
        raise ValueError('Two finite derivative steps and residuals are required')
    if h[0] <= 0 or not np.isclose(h[1], 2*h[0], rtol=1e-8, atol=1e-12):
        raise ValueError('Expected steps h and 2h')
    if tolerance_ev is not None:
        if not np.isfinite(tolerance_ev) or tolerance_ev <= 0 or not str(tolerance_reason or '').strip():
            raise ValueError('An explicit positive tolerance needs its source/reason')
    elif tolerance_reason is not None:
        raise ValueError('A tolerance reason requires a tolerance')
    return {
        'coarse_to_fine_residual_ratio': float(abs(r[1]/r[0])) if r[0] else None,
        'richardson_residual_ev': float((4*r[0]-r[1])/3),
        'fine_step_truncation_estimate_ev': float(abs(r[0]-r[1])/3),
        'extrapolation_assumption': 'Centered differences in the smooth O(h^2) regime; SCF noise is not estimated here.',
        'diagnostic_criterion': None if tolerance_ev is None else {
            'tolerance_ev': tolerance_ev, 'source_or_reason': tolerance_reason,
            'within_tolerance': bool(np.all(np.abs(r) <= tolerance_ev)),
        },
        'scientific_acceptance': 'not_assessed',
    }


def analyze(points: list[dict], tolerance_ev=None, tolerance_reason=None) -> dict:
    """Check centered derivatives at two step sizes, without fitting a new model."""
    points = sorted(points, key=lambda point: point["electrons"])
    if len(points) != 5:
        raise ValueError("Exactly five equally spaced fixed-geometry points are required")
    n = np.array([p["electrons"] for p in points])
    if not np.allclose(np.diff(n), n[1] - n[0]) or n[1] <= n[0]:
        raise ValueError("Electron numbers must be distinct and equally spaced")
    mu_target = points[2]["mu_ev"]
    for p in points:
        p["potential_residual_ev"] = p["mu_ev"] - mu_target
        p["omega_candidate_ev"] = p["E_KohnSham"] + (-p["vacuum_ev"] - mu_target) * (p["electrons"] - p["reference_electrons"])
    derivatives = []
    for offset in (1, 2):
        left, right = points[2 - offset], points[2 + offset]
        denominator = right["electrons"] - left["electrons"]
        derivative = (right["omega_candidate_ev"] - left["omega_candidate_ev"]) / denominator
        derivatives.append({"step_electrons": denominator / 2, "domega_dne_ev": derivative})
    minimum_at_root = points[2]["omega_candidate_ev"] == min(p["omega_candidate_ev"] for p in points)
    diagnostics = derivative_diagnostics([p['step_electrons'] for p in derivatives],
                                        [p['domega_dne_ev'] for p in derivatives],
                                        tolerance_ev, tolerance_reason)
    return {"energy_definition": "reference_fcp_candidate", "mu_target_ev": mu_target, "minimum_at_sampled_potential_root": minimum_at_root, "derivatives": derivatives, **diagnostics, "points": points, "limitation": "Historical formula diagnostic only; no scientific acceptance from a sampled minimum or a tolerance screen."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", type=Path, nargs=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-ev", type=float)
    parser.add_argument("--tolerance-reason")
    args = parser.parse_args()
    result = analyze([read_point(p) for p in args.directories], args.tolerance_ev, args.tolerance_reason)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("scientific_acceptance", "derivatives", "diagnostic_criterion", "richardson_residual_ev")}, indent=2))
