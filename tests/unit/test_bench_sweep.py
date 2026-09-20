"""Tests for the variant sweep driver (P5 measurement matrix support)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
import threading

from atst_tools.bench import harness, sweep

STANDIN_SOURCE = """\
import json, os, time
from pathlib import Path

workdir = Path.cwd()
(workdir / "env.json").write_text(
    json.dumps({"cuda": os.environ.get("CUDA_VISIBLE_DEVICES")})
)
time.sleep(float(os.environ.get("STANDIN_SLEEP", "0.05")))
(workdir / "atst_api_result.json").write_text("{}")
"""


def _factory(tmp_path: Path):
    script = tmp_path / "standin.py"
    script.write_text(STANDIN_SOURCE, encoding="utf-8")

    def build(case, workdir, devices):
        del case, workdir, devices
        return [sys.executable, str(script)]

    return build


def _manifest() -> dict:
    return {
        "cases": [
            {"case_id": "a", "config": "a.yaml", "workdir": "a"},
            {"case_id": "b", "config": "b.yaml", "workdir": "b"},
        ]
    }


def test_sweep_runs_every_variant_with_alternating_order(tmp_path):
    summary = sweep.run_sweep(
        _manifest(),
        sweep.SweepOptions(
            devices=("0",),
            output_dir=tmp_path / "sweep",
            slots=(1, 2),
            repeats=2,
            worker_factory=_factory(tmp_path),
            telemetry=False,
        ),
    )
    assert summary["schema"] == sweep.SWEEP_SCHEMA
    order = [(row["slots"], row["repeat"]) for row in summary["runs"]]
    assert order == [(1, 1), (2, 1), (2, 2), (1, 2)]
    for slots in (1, 2):
        for repeat in (1, 2):
            run_dir = tmp_path / "sweep" / f"slots-{slots}" / f"repeat-{repeat}"
            assert (run_dir / harness.SUMMARY_REPORT).is_file()
    assert set(summary["variants"]) == {"1", "2"}
    for aggregate in summary["variants"].values():
        assert aggregate["runs"] == 2
        assert aggregate["succeeded"]["total"] == 4
        assert aggregate["cases_total"]["total"] == 4
        assert aggregate["makespan_s"]["median"] is not None
        assert len(aggregate["makespan_s"]["values"]) == 2
    written = json.loads(
        (tmp_path / "sweep" / sweep.SWEEP_SUMMARY).read_text(encoding="utf-8")
    )
    assert written["repeats"] == 2
    assert any("alternating repeats" in note for note in written["notes"])


def test_sweep_keeps_failures_in_the_denominator(tmp_path):
    script = tmp_path / "failing.py"
    script.write_text("import sys; sys.exit(3)", encoding="utf-8")

    def factory(case, workdir, devices):
        del case, workdir, devices
        return [sys.executable, str(script)]

    summary = sweep.run_sweep(
        _manifest(),
        sweep.SweepOptions(
            devices=("0",),
            output_dir=tmp_path / "sweep",
            slots=(1,),
            repeats=1,
            worker_factory=factory,
            telemetry=False,
        ),
    )
    aggregate = summary["variants"]["1"]
    assert aggregate["succeeded"]["total"] == 0
    assert aggregate["cases_total"]["total"] == 2
    assert summary["runs"][0]["failed"] == 2


def test_sweep_rejects_invalid_variants(tmp_path):
    with pytest.raises(ValueError):
        sweep.run_sweep(
            _manifest(),
            sweep.SweepOptions(devices=("0",), output_dir=tmp_path, slots=()),
        )
    with pytest.raises(ValueError):
        sweep.run_sweep(
            _manifest(),
            sweep.SweepOptions(devices=("0",), output_dir=tmp_path, slots=(0,)),
        )


def test_sweep_stops_when_the_stop_event_is_already_set(tmp_path):
    """A cancelled sweep writes its summary without launching any run (review F1)."""
    stop = threading.Event()
    stop.set()
    summary = sweep.run_sweep(
        _manifest(),
        sweep.SweepOptions(
            devices=("0",),
            output_dir=tmp_path / "sweep",
            slots=(1, 2),
            repeats=2,
            telemetry=False,
            stop_event=stop,
        ),
    )
    assert summary["status"] == "cancelled"
    assert summary["runs"] == []
    assert (tmp_path / "sweep" / sweep.SWEEP_SUMMARY).is_file()


def test_sweep_aggregate_survives_zero_wall_rows():
    """A zero makespan (all cases spawned and failed instantly) must not crash."""
    aggregate = sweep._aggregate(
        [
            {
                "wall_s": 0.0,
                "gpu_seconds_total": 0.0,
                "succeeded": 0,
                "cases_total": 2,
            }
        ]
    )
    assert aggregate["makespan_s"]["median"] == 0.0
    assert aggregate["successful_cases_per_hour"]["median"] is None
    assert aggregate["successful_cases_per_hour"]["values"] == [None]


def test_sweep_defaults_to_no_per_case_telemetry():
    """Timing sweeps must not add per-case samplers unless asked (review F9)."""
    assert sweep.SweepOptions(devices=("0",), output_dir=Path("x")).case_telemetry is False
