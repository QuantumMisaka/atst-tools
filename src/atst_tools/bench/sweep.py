"""Variant sweep driver for the batch harness (GPU tuning P5 matrix).

The frozen benchmark matrix asks for repeated, alternating comparisons of the
same case list (for example per-device concurrency 1/2/3 with at least three
repeats).  This driver runs the harness once per (variant, repeat) pair into a
separate directory, alternates the variant order between repeats, and writes
one ``sweep_summary.json`` with per-variant makespan/throughput aggregates so a
reviewer can see the raw rows and the derived numbers side by side.

Usage::

    python -m atst_tools.bench.sweep --manifest cases.json --out runs \\
        --devices 0,1 --slots 1,2,3 --repeats 3
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
import sys
import time
from typing import Any, Callable, Mapping, Sequence

from atst_tools.bench import harness

SWEEP_SCHEMA = "atst-bench-sweep-v1"
SWEEP_SUMMARY = "sweep_summary.json"
MIN_MEANINGFUL_REPEATS = 3


@dataclass
class SweepOptions:
    """Sweep-level controls; harness options are derived per variant."""

    devices: tuple[str, ...]
    output_dir: Path
    slots: tuple[int, ...] = (1,)
    repeats: int = 1
    cpu_budget: int | None = None
    default_threads: int = 1
    default_timeout_s: float | None = None
    continue_on_failure: bool = True
    sampler_interval_s: float = 1.0
    telemetry: bool = True
    case_telemetry: bool = True
    worker_factory: (
        Callable[[harness.CaseSpec, Path, tuple[str, ...]], Sequence[str]] | None
    ) = None


def _variant_dir(output_dir: Path, slots: int, repeat: int) -> Path:
    return output_dir / f"slots-{slots}" / f"repeat-{repeat}"


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    makespans = [float(row["wall_s"]) for row in rows]
    gpu_seconds = [float(row["gpu_seconds_total"]) for row in rows]
    succeeded = [int(row["succeeded"]) for row in rows]
    cases_total = [int(row["cases_total"]) for row in rows]
    return {
        "runs": len(rows),
        "makespan_s": {
            "values": [round(value, 3) for value in makespans],
            "median": round(median(makespans), 3) if makespans else None,
            "min": round(min(makespans), 3) if makespans else None,
            "max": round(max(makespans), 3) if makespans else None,
        },
        "gpu_seconds_total": {
            "values": [round(value, 3) for value in gpu_seconds],
            "median": round(median(gpu_seconds), 3) if gpu_seconds else None,
        },
        "succeeded": {
            "values": succeeded,
            "total": sum(succeeded),
        },
        "cases_total": {
            "values": cases_total,
            "total": sum(cases_total),
        },
        "successful_cases_per_hour": {
            "values": [
                round(3600.0 * ok / wall, 2) if wall else None
                for ok, wall in zip(succeeded, makespans)
            ],
            "median": (
                round(
                    median(
                        [
                            3600.0 * ok / wall
                            for ok, wall in zip(succeeded, makespans)
                            if wall
                        ]
                    ),
                    2,
                )
                if makespans
                else None
            ),
        },
    }


def run_sweep(
    manifest: Mapping[str, Any], options: SweepOptions
) -> dict[str, Any]:
    """Run every (slots, repeat) pair and return the sweep summary.

    Variants alternate their order between repeats so systematic drift (queue
    pressure, thermal state, cache warmth) does not silently favour one
    variant.
    """
    variants = tuple(dict.fromkeys(int(slots) for slots in options.slots))
    if not variants:
        raise ValueError("the sweep requires at least one slots variant")
    if any(slots < 1 for slots in variants):
        raise ValueError("slots variants must be positive")
    repeats = max(int(options.repeats), 1)

    output_dir = Path(options.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    started_monotonic = time.monotonic()

    per_variant: dict[str, list[dict[str, Any]]] = {
        str(slots): [] for slots in variants
    }
    repeat_rows: list[dict[str, Any]] = []

    for repeat in range(1, repeats + 1):
        order = variants if repeat % 2 == 1 else tuple(reversed(variants))
        for slots in order:
            run_dir = _variant_dir(output_dir, slots, repeat)
            run_dir.mkdir(parents=True, exist_ok=True)
            summary = harness.run_manifest(
                manifest,
                harness.HarnessOptions(
                    devices=options.devices,
                    output_dir=run_dir,
                    slots_per_device=slots,
                    cpu_budget=options.cpu_budget,
                    default_threads=options.default_threads,
                    default_timeout_s=options.default_timeout_s,
                    continue_on_failure=options.continue_on_failure,
                    sampler_interval_s=options.sampler_interval_s,
                    telemetry=options.telemetry,
                    case_telemetry=options.case_telemetry,
                    worker_factory=options.worker_factory,
                ),
            )
            row = {
                "slots": slots,
                "repeat": repeat,
                "run_dir": str(run_dir),
                "summary": str(run_dir / harness.SUMMARY_REPORT),
                "status": summary["status"],
                "wall_s": summary["wall_s"],
                "gpu_seconds_total": summary["gpu_seconds_total"],
                "cases_total": summary["cases_total"],
                "succeeded": summary["succeeded"],
                "failed": summary["failed"],
                "timed_out": summary["timed_out"],
                "skipped": summary["skipped"],
            }
            per_variant[str(slots)].append(row)
            repeat_rows.append(row)

    summary_payload = {
        "schema": SWEEP_SCHEMA,
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "wall_s": round(time.monotonic() - started_monotonic, 3),
        "devices": list(options.devices),
        "slots_variants": list(variants),
        "repeats": repeats,
        "cpu_budget": options.cpu_budget,
        "runs": repeat_rows,
        "variants": {
            slots: _aggregate(rows) for slots, rows in per_variant.items()
        },
        "notes": [
            "Aggregates are descriptive statistics over "
            f"{repeats} repeat(s); the frozen matrix asks for at least "
            f"{MIN_MEANINGFUL_REPEATS} alternating repeats before drawing "
            "performance conclusions.",
            "Per-variant directories keep the raw harness summaries; no case "
            "is removed from the denominator on failure.",
        ],
    }
    (output_dir / SWEEP_SUMMARY).write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_payload


def main(argv: Sequence[str] | None = None) -> int:
    """Run one sweep and print the compact variant table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Case manifest JSON path")
    parser.add_argument("--out", required=True, help="Sweep output directory")
    parser.add_argument("--devices", required=True, help="Comma-separated device pool")
    parser.add_argument(
        "--slots",
        default="1",
        help="Comma-separated per-device concurrency variants (default: 1)",
    )
    parser.add_argument("--repeats", type=int, default=1, help="Repeat count")
    parser.add_argument("--cpu-budget", type=int, default=None)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--no-telemetry", action="store_true")
    parser.add_argument("--no-case-telemetry", action="store_true")
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    try:
        slots = tuple(
            int(part.strip())
            for part in args.slots.split(",")
            if part.strip()
        )
    except ValueError as exc:
        raise SystemExit(f"invalid --slots value: {exc}") from None
    summary = run_sweep(
        manifest,
        SweepOptions(
            devices=tuple(
                part.strip() for part in args.devices.split(",") if part.strip()
            ),
            output_dir=Path(args.out),
            slots=slots,
            repeats=args.repeats,
            cpu_budget=args.cpu_budget,
            default_threads=args.threads,
            default_timeout_s=args.timeout,
            continue_on_failure=not args.stop_on_failure,
            telemetry=not args.no_telemetry,
            case_telemetry=not args.no_case_telemetry,
        ),
    )
    for slots, aggregate in sorted(
        summary["variants"].items(), key=lambda item: int(item[0])
    ):
        print(
            f"slots={slots}: makespan median={aggregate['makespan_s']['median']}s "
            f"ok={aggregate['succeeded']['total']}/"
            f"{aggregate['cases_total']['total']} "
            f"gpu_s median={aggregate['gpu_seconds_total']['median']}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution entry
    raise SystemExit(main())
