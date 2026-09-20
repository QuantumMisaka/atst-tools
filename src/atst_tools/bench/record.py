"""Benchmark record builder for the GPU tuning measurement stage (P5).

Every benchmark row must be self-describing: which atst revision ran, in which
interpreter and environment, on which hardware, over which manifest and
fixtures, with which result directories, and which operator-owned fields (job
identifier, partition, QOS, allocated GPU-hours) are still to be filled in.
This module writes that record next to the results and hashes every referenced
artifact so a later review can verify nothing changed.

Usage::

    python -m atst_tools.bench.record --manifest cases.json --out record.json \\
        --sweep-dir runs/sweep --harness-dir runs/single
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping, Sequence

from atst_tools.runtime.evidence import environment_facts

RECORD_SCHEMA = "atst-bench-record-v1"

OPERATOR_FIELDS: tuple[str, ...] = (
    "job_id",
    "partition",
    "qos",
    "allocated_gpu_hours",
    "sacct_excerpt",
    "approved_by",
)


def _sha256(path: Path) -> str | None:
    """Return the file hash, or ``None`` when the file is missing."""
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_facts(root: Path) -> dict[str, Any]:
    """Return the revision facts of the checkout that ran the benchmark."""
    facts: dict[str, Any] = {"head": None, "branch": None, "dirty": None}
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return facts
    if head.returncode == 0:
        facts["head"] = head.stdout.strip() or None
    if branch.returncode == 0:
        facts["branch"] = branch.stdout.strip() or None
    if status.returncode == 0:
        facts["dirty"] = bool(status.stdout.strip())
    return facts


def _host_facts() -> dict[str, Any]:
    """Return the host identity, including the GPU inventory when available."""
    inventory: list[str] = []
    inventory_error: str | None = None
    try:
        completed = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode == 0:
            inventory = [
                line.strip() for line in completed.stdout.splitlines() if line.strip()
            ]
        else:
            inventory_error = f"nvidia-smi exited with status {completed.returncode}"
    except (OSError, subprocess.SubprocessError) as exc:
        inventory_error = f"nvidia-smi could not be executed ({type(exc).__name__})"
    return {
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "gpu_inventory": inventory,
        "gpu_inventory_error": inventory_error,
    }


def _artifact(path: Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    return {
        "path": str(resolved),
        "exists": resolved.exists(),
        "sha256": _sha256(resolved) if resolved.is_file() else None,
    }


def _summarize_run_dir(run_dir: Path) -> dict[str, Any]:
    """Summarize one harness or sweep directory by its summary document."""
    candidates = (
        run_dir / "sweep_summary.json",
        run_dir / "harness_summary.json",
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        entry: dict[str, Any] = {
            "dir": str(run_dir.resolve()),
            "summary": str(candidate.resolve()),
            "summary_sha256": _sha256(candidate),
            "schema": payload.get("schema"),
        }
        if payload.get("schema") == "atst-bench-sweep-v1":
            entry["repeats"] = payload.get("repeats")
            entry["slots_variants"] = payload.get("slots_variants")
            entry["variants"] = {
                slots: {
                    "makespan_s_median": aggregate.get("makespan_s", {}).get("median"),
                    "succeeded_total": aggregate.get("succeeded", {}).get("total"),
                    "cases_total": aggregate.get("cases_total", {}).get("total"),
                }
                for slots, aggregate in (payload.get("variants") or {}).items()
            }
        else:
            entry["cases_total"] = payload.get("cases_total")
            entry["succeeded"] = payload.get("succeeded")
            entry["failed"] = payload.get("failed")
            entry["wall_s"] = payload.get("wall_s")
        return entry
    return {
        "dir": str(run_dir.resolve()),
        "summary": None,
        "summary_sha256": None,
        "schema": None,
    }


def build_record(
    *,
    manifest: Path,
    run_dirs: Sequence[Path] = (),
    fixtures: Sequence[Path] = (),
    repo_root: Path | None = None,
    operator: Mapping[str, Any] | None = None,
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one benchmark record document (no file writes)."""
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    operator_payload: dict[str, Any] = {}
    provided = dict(operator or {})
    for key in OPERATOR_FIELDS:
        operator_payload[key] = provided.get(key)
    for key, value in provided.items():
        if key not in operator_payload:
            operator_payload[key] = value
    return {
        "schema": RECORD_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "atst": _git_facts(root),
        "environment": environment_facts(os.environ),
        "host": _host_facts(),
        "inputs": {
            "manifest": _artifact(manifest),
            "fixtures": [_artifact(path) for path in fixtures],
        },
        "results": [_summarize_run_dir(Path(run_dir)) for run_dir in run_dirs],
        "operator": operator_payload,
        "notes": list(notes),
    }


def write_record(payload: Mapping[str, Any], out_path: Path) -> Path:
    """Write the record atomically and return the resolved path."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path.resolve()


def main(argv: Sequence[str] | None = None) -> int:
    """Build one benchmark record from the given directories."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--run-dir",
        action="append",
        default=[],
        help="Harness or sweep output directory (repeatable)",
    )
    parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        help="Fixture file to hash into the record (repeatable)",
    )
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--partition", default=None)
    parser.add_argument("--qos", default=None)
    parser.add_argument("--allocated-gpu-hours", default=None, type=float)
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Free-form note stored with the record (repeatable)",
    )
    args = parser.parse_args(argv)

    payload = build_record(
        manifest=Path(args.manifest),
        run_dirs=[Path(path) for path in args.run_dir],
        fixtures=[Path(path) for path in args.fixture],
        operator={
            "job_id": args.job_id,
            "partition": args.partition,
            "qos": args.qos,
            "allocated_gpu_hours": args.allocated_gpu_hours,
        },
        notes=args.note,
    )
    written = write_record(payload, Path(args.out))
    print(f"wrote benchmark record: {written}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution entry
    raise SystemExit(main())
