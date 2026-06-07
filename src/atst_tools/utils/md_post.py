"""Molecular dynamics trajectory post-processing helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from ase.io import read, write

from atst_tools.utils.summary import max_force, energy, write_summary_json


def _temperature(atoms) -> float:
    if not atoms.has("momenta"):
        return float("nan")
    try:
        return float(atoms.get_temperature())
    except Exception:
        return float("nan")


def _selected_frames(frames: list, *, frame: int | None = None, stride: int = 1) -> list:
    if stride <= 0:
        raise ValueError("stride must be a positive integer")
    if frame is not None:
        try:
            return [frames[frame]]
        except IndexError as exc:
            raise IndexError(f"frame index out of range: {frame}") from exc
    return frames[::stride]


def _write_md_summary(summary: dict[str, Any], output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    write_summary_json(summary, output)


def summarize_md_trajectory(
    traj_file: str | Path,
    *,
    tail: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read and summarize an MD trajectory."""
    frames = read(str(traj_file), index=":")
    frame_summaries = [
        {
            "step": index,
            "energy_eV": energy(atoms),
            "temperature_K": _temperature(atoms),
            "max_force_eV_per_A": max_force(atoms),
        }
        for index, atoms in enumerate(frames)
    ]
    selected = frame_summaries[-tail:] if tail and tail > 0 else frame_summaries
    latest = dict(frame_summaries[-1]) if frame_summaries else {}
    return {
        "schema_version": "atst-md-post-v1",
        "workflow": "md",
        "source": str(traj_file),
        "status": {"n_frames": len(frames), "complete": bool(frames)},
        "latest": latest,
        "frames": selected,
        "metadata": dict(metadata or {}),
    }


def post_md_trajectory(
    traj_file: str | Path,
    *,
    output_prefix: str | Path = "md_post",
    output_format: str = "extxyz",
    summary_output: str | Path | None = "md_post_summary.json",
    tail: int | None = None,
    frame: int | None = None,
    stride: int = 1,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write MD summary and convert trajectory frames to another ASE format."""
    frames = read(str(traj_file), index=":")
    selected = _selected_frames(list(frames), frame=frame, stride=stride)
    summary = summarize_md_trajectory(traj_file, tail=tail, metadata=metadata)
    if summary_output:
        _write_md_summary(summary, summary_output)

    output_prefix = Path(output_prefix)
    if output_format in {"traj", "extxyz", "xyz"}:
        output = output_prefix.with_suffix(f".{output_format}")
        output.parent.mkdir(parents=True, exist_ok=True)
        write(str(output), selected, format=output_format)
        converted = {"path": str(output), "format": output_format, "frames": len(selected)}
    else:
        output_prefix.mkdir(parents=True, exist_ok=True)
        for index, atoms in enumerate(selected):
            output = output_prefix / f"{index:04d}.{output_format}"
            write(str(output), atoms, format=output_format)
        converted = {"path": str(output_prefix), "format": output_format, "frames": len(selected)}

    return {"summary": summary, "converted": converted}


def run_md_workflow_postprocess(
    calc_config: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run configured post-processing after an MD workflow completes."""
    postprocess = calc_config.get("postprocess") or {}
    summary_config = postprocess.get("summary") or {}
    convert_config = postprocess.get("convert") or {}
    artifacts: list[dict[str, Any]] = []
    result: dict[str, Any] = {"artifacts": artifacts}

    if summary_config.get("enabled", True):
        output = summary_config.get("output", "md_post_summary.json")
        summary = summarize_md_trajectory(
            calc_config["trajectory"],
            tail=summary_config.get("tail"),
            metadata=metadata,
        )
        _write_md_summary(summary, output)
        artifacts.append({"role": "postprocess_summary", "path": output})
        result["summary"] = summary

    if convert_config.get("enabled", False):
        post_result = post_md_trajectory(
            calc_config["trajectory"],
            output_prefix=convert_config.get("output_prefix", "md_post"),
            output_format=convert_config.get("format", "extxyz"),
            summary_output=summary_config.get("output", "md_post_summary.json")
            if summary_config.get("enabled", True)
            else None,
            tail=summary_config.get("tail"),
            frame=convert_config.get("frame"),
            stride=convert_config.get("stride", 1),
            metadata=metadata,
        )
        artifacts.append({"role": "postprocess_conversion", "path": post_result["converted"]["path"]})
        result["conversion"] = post_result["converted"]
        result.setdefault("summary", post_result["summary"])

    return result
