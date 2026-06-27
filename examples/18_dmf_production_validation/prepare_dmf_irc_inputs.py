#!/usr/bin/env python
"""Prepare descent-IRC TS structures and mode vectors from DMF-D2S outputs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from ase.io import read, write


ROOT = Path(__file__).resolve().parent

CASES = [
    {
        "name": "07_Li-Si_d2s_dmf_irc",
        "source": ROOT / "runs" / "05_Li-Si_d2s_dmf_vib",
        "target": ROOT / "runs" / "07_Li-Si_d2s_dmf_irc",
    },
    {
        "name": "08_H2-Au_d2s_dmf_irc",
        "source": ROOT / "runs" / "06_H2-Au_d2s_dmf_vib",
        "target": ROOT / "runs" / "08_H2-Au_d2s_dmf_irc",
    },
]


def prepare_case(case: dict) -> dict:
    """Write the final Sella TS and local DMF-path mode vector for one case."""
    source = case["source"]
    target = case["target"]
    target.mkdir(parents=True, exist_ok=True)

    ts = read(source / "sella.traj", index=-1)
    write(target / "ts.extxyz", ts)

    vibration = json.loads((source / "d2s_vibration_results.json").read_text(encoding="utf-8"))
    indices = [int(index) for index in vibration["indices"]]
    dmf_summary = json.loads((source / "dmf_summary.json").read_text(encoding="utf-8"))
    dmf_path = read(source / "dmf_path.traj", index=":")
    candidate_index = int(round(float(dmf_summary["tmax"]) * max(len(dmf_path) - 1, 0)))
    candidate_index = min(max(candidate_index, 0), len(dmf_path) - 1)
    before = max(0, candidate_index - 1)
    after = min(len(dmf_path) - 1, candidate_index + 1)
    mode = np.zeros((len(ts), 3), dtype=float)
    mode[indices] = dmf_path[after].positions[indices] - dmf_path[before].positions[indices]
    norm = float(np.linalg.norm(mode))
    if norm <= 1e-12:
        raise ValueError(f"{case['name']} produced a zero-length IRC mode")
    mode /= norm
    np.save(target / "mode.npy", mode)

    summary = {
        "case": case["name"],
        "source": str(source.relative_to(ROOT)),
        "ts": str((target / "ts.extxyz").relative_to(ROOT)),
        "mode": str((target / "mode.npy").relative_to(ROOT)),
        "indices": indices,
        "dmf_tmax": dmf_summary["tmax"],
        "dmf_candidate_index": candidate_index,
        "mode_norm_before_normalization": norm,
    }
    (target / "irc_input_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    """Prepare all staged DMF IRC inputs."""
    summaries = [prepare_case(case) for case in CASES]
    print(json.dumps({"prepared": summaries}, indent=2))


if __name__ == "__main__":
    main()
