"""Tests for the finite-case batch harness (P3) with a stand-in worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from atst_tools.bench import harness

STANDIN_SOURCE = """\
import json, os, subprocess, sys, time
from pathlib import Path

mode = os.environ.get("STANDIN_MODE", "ok")
workdir = Path.cwd()
facts = {
    "cuda": os.environ.get("CUDA_VISIBLE_DEVICES"),
    "attempt": os.environ.get("ATST_ATTEMPT"),
    "threads": os.environ.get("OMP_NUM_THREADS"),
    "cache": os.environ.get("NUMBA_CACHE_DIR"),
    "pid": os.getpid(),
}
(workdir / "env.json").write_text(json.dumps(facts))
log = Path(os.environ["HARNESS_LOG"])


def note(text):
    with log.open("a", encoding="utf-8") as handle:
        handle.write(text + "\\n")
        handle.flush()


note("start %s" % os.getpid())
if mode == "sleep":
    child = subprocess.Popen(["sleep", "120"])
    (workdir / "child.pid").write_text(str(child.pid))
    time.sleep(120)
elif mode == "fail_oom":
    sys.stderr.write("CUDA out of memory. Tried to allocate 2.00 GiB")
    sys.stderr.flush()
    time.sleep(0.05)
    note("end %s" % os.getpid())
    sys.exit(3)
elif mode == "fail":
    time.sleep(0.02)
    note("end %s" % os.getpid())
    sys.exit(4)
else:
    (workdir / "atst_api_result.json").write_text("{}")
    note("end %s" % os.getpid())
    sys.exit(0)
"""


def _standin(tmp_path: Path) -> Path:
    path = tmp_path / "standin_worker.py"
    path.write_text(STANDIN_SOURCE, encoding="utf-8")
    return path


def _factory(script: Path):
    def build(case, workdir, devices):
        del workdir, devices
        return [sys.executable, str(script)]

    return build


def _case(case_id: str, mode: str = "ok") -> dict:
    return {
        "case_id": case_id,
        "config": f"{case_id}.yaml",
        "workdir": case_id,
        "env": {"STANDIN_MODE": mode},
    }


def test_default_workdir_is_the_configuration_directory(tmp_path, monkeypatch):
    """Cases run where their config lives, like a user-typed `atst run`."""
    script = _standin(tmp_path)
    monkeypatch.setenv("HARNESS_LOG", str(tmp_path / "log.txt"))
    config_dir = tmp_path / "source_case"
    config_dir.mkdir()
    config = config_dir / "config.yaml"
    config.write_text("calculation: {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    summary = harness.run_manifest(
        {"cases": [{"case_id": "inplace", "config": str(config)}]},
        harness.HarnessOptions(
            devices=("0",),
            output_dir=Path("out"),
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )
    assert summary["succeeded"] == 1
    assert (config_dir / "env.json").is_file()
    report = json.loads(
        (tmp_path / "out" / "inplace" / harness.CASE_REPORT).read_text(encoding="utf-8")
    )
    assert report["workdir"] == str(config_dir)
    assert (tmp_path / "out" / "inplace" / "harness_worker.out").is_file()


def test_cases_run_in_slots_with_isolated_dirs_and_reports(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    log = tmp_path / "log.txt"
    monkeypatch.setenv("HARNESS_LOG", str(log))
    summary = harness.run_manifest(
        {"cases": [_case("alpha"), _case("beta")]},
        harness.HarnessOptions(
            devices=("2",),
            output_dir=tmp_path / "out",
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )

    assert summary["status"] == "complete"
    assert summary["cases_total"] == 2
    assert summary["succeeded"] == 2
    assert summary["gpu_seconds_total"] > 0
    for case_id in ("alpha", "beta"):
        workdir = tmp_path / "out" / case_id
        facts = json.loads((workdir / "env.json").read_text(encoding="utf-8"))
        assert facts["cuda"] == "2"
        assert facts["attempt"] == "1"
        assert Path(facts["cache"]).is_dir()
        report = json.loads(
            (workdir / harness.CASE_REPORT).read_text(encoding="utf-8")
        )
        assert report["status"] == "succeeded"
        assert report["result_json"] is not None
    events = [line.split()[0] for line in log.read_text(encoding="utf-8").splitlines()]
    assert events == ["start", "end", "start", "end"]


def test_relative_output_dir_is_resolved_before_launching_workers(tmp_path, monkeypatch):
    """A relative --out must not leak into worker paths (nested-dir regression)."""
    script = _standin(tmp_path)
    monkeypatch.setenv("HARNESS_LOG", str(tmp_path / "log.txt"))
    monkeypatch.chdir(tmp_path)
    summary = harness.run_manifest(
        {"cases": [_case("rel")]},
        harness.HarnessOptions(
            devices=("0",),
            output_dir=Path("out"),
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )
    assert summary["succeeded"] == 1
    assert (tmp_path / "out" / "rel" / "env.json").is_file()
    assert not (tmp_path / "out" / "rel" / "out").exists()
    report = json.loads(
        (tmp_path / "out" / "rel" / harness.CASE_REPORT).read_text(encoding="utf-8")
    )
    assert Path(report["workdir"]).is_absolute()


def test_sequential_cases_do_not_trigger_the_no_progress_guard(tmp_path, monkeypatch):
    """A finishing case must not be mistaken for a stalled scheduler."""
    script = _standin(tmp_path)
    monkeypatch.setenv("HARNESS_LOG", str(tmp_path / "log.txt"))
    cases = [_case("first", "sleep"), _case("second")]
    cases[0]["timeout_s"] = 1.0
    summary = harness.run_manifest(
        {"cases": cases},
        harness.HarnessOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )
    statuses = {row["case_id"]: row["status"] for row in summary["cases"]}
    assert statuses == {"first": "timeout", "second": "succeeded"}
    assert summary["succeeded"] == 1
    assert summary["timed_out"] == 1


def test_unsatisfiable_case_reports_an_explicit_error(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    monkeypatch.setenv("HARNESS_LOG", str(tmp_path / "log.txt"))
    case = _case("too-big")
    case["slots"] = 2
    with pytest.raises(RuntimeError) as caught:
        harness.run_manifest(
            {"cases": [case]},
            harness.HarnessOptions(
                devices=("0",),
                output_dir=tmp_path / "out",
                worker_factory=_factory(script),
                telemetry=False,
            ),
        )
    assert "too-big" in str(caught.value)


def test_failure_keeps_evidence_and_stop_on_failure_skips_the_rest(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    monkeypatch.setenv("HARNESS_LOG", str(tmp_path / "log.txt"))
    summary = harness.run_manifest(
        {"cases": [_case("ok"), _case("bad", "fail_oom"), _case("later")]},
        harness.HarnessOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=_factory(script),
            telemetry=False,
            continue_on_failure=False,
        ),
    )

    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    bad = json.loads(
        (tmp_path / "out" / "bad" / harness.CASE_REPORT).read_text(encoding="utf-8")
    )
    assert bad["classification"] == "oom"
    assert bad["exit_code"] == 3
    later = json.loads(
        (tmp_path / "out" / "later" / harness.CASE_REPORT).read_text(encoding="utf-8")
    )
    assert later["status"] == "skipped"
    assert later["classification"] == "stopped_after_failure"
    ids = {row["case_id"] for row in summary["cases"]}
    assert ids == {"ok", "bad", "later"}


def test_timeout_terminates_the_whole_worker_group(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    monkeypatch.setenv("HARNESS_LOG", str(tmp_path / "log.txt"))
    case = _case("slow", "sleep")
    case["timeout_s"] = 0.4
    summary = harness.run_manifest(
        {"cases": [case]},
        harness.HarnessOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )

    assert summary["timed_out"] == 1
    report = json.loads(
        (tmp_path / "out" / "slow" / harness.CASE_REPORT).read_text(encoding="utf-8")
    )
    assert report["status"] == "timeout"
    assert report["wall_s"] < 10
    child_pid = int((tmp_path / "out" / "slow" / "child.pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_cancel_marks_remaining_cases_and_writes_the_summary(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    log = tmp_path / "log.txt"
    monkeypatch.setenv("HARNESS_LOG", str(log))
    stop_event = threading.Event()
    results: list[dict] = []
    failures: list[BaseException] = []

    def run():
        try:
            results.append(
                harness.run_manifest(
                    {"cases": [_case("slow-1", "sleep"), _case("slow-2", "sleep")]},
                    harness.HarnessOptions(
                        devices=("0",),
                        output_dir=tmp_path / "out",
                        worker_factory=_factory(script),
                        telemetry=False,
                        stop_event=stop_event,
                    ),
                )
            )
        except BaseException as exc:  # SystemExit("batch cancelled")
            failures.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if log.exists() and "start" in log.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    stop_event.set()
    worker.join(timeout=30)

    assert not worker.is_alive()
    assert results == [] and failures
    summary = json.loads(
        (tmp_path / "out" / harness.SUMMARY_REPORT).read_text(encoding="utf-8")
    )
    assert summary["status"] == "cancelled"
    statuses = {row["case_id"]: row["status"] for row in summary["cases"]}
    assert set(statuses) == {"slow-1", "slow-2"}
    assert statuses["slow-2"] in {"skipped", "timeout", "failed"}
    assert summary["succeeded"] == 0


def test_manifest_validation_rejects_bad_rows(tmp_path):
    options = harness.HarnessOptions(devices=("0",), output_dir=tmp_path)
    with pytest.raises(ValueError):
        harness.load_cases({"cases": []}, options)
    with pytest.raises(ValueError):
        harness.load_cases({"cases": [{"case_id": "", "config": "x.yaml"}]}, options)
    with pytest.raises(ValueError):
        harness.load_cases(
            {"cases": [_case("a"), _case("a")]}, options
        )


def test_case_environment_merges_case_specific_values(tmp_path):
    case = harness.CaseSpec.from_mapping(
        {
            "case_id": "case",
            "config": "config.yaml",
            "threads": 4,
            "env": {"MY_FLAG": "1"},
        }
    )
    env = harness.case_environment(
        case, ("3",), base={"PATH": "/usr/bin"}, attempt=2, workdir=tmp_path
    )
    assert env["CUDA_VISIBLE_DEVICES"] == "3"
    assert env["OMP_NUM_THREADS"] == "4"
    assert env["ATST_ATTEMPT"] == "2"
    assert env["MY_FLAG"] == "1"


def test_case_environment_requests_per_case_evidence_by_default(tmp_path):
    case = harness.CaseSpec.from_mapping({"case_id": "c", "config": "c.yaml"})
    env = harness.case_environment(
        case, ("0",), base={}, attempt=1, workdir=tmp_path
    )
    assert env["ATST_TELEMETRY_ENABLED"] == "1"
    quiet = harness.case_environment(
        case, ("0",), base={}, attempt=1, workdir=tmp_path, case_telemetry=False
    )
    assert "ATST_TELEMETRY_ENABLED" not in quiet


def test_slot_pool_hands_out_distinct_devices_for_multi_slot_cases():
    pool = harness._SlotPool(("0", "1"), 2)
    assert pool.acquire("multi", 2) == ("0", "1")
    pool.release("multi")
    single_device = harness._SlotPool(("0",), 2)
    assert single_device.acquire("multi", 2) is None
    assert single_device.acquire("one", 1) == ("0",)


def test_stalled_batch_stops_the_sampler_before_raising(monkeypatch, tmp_path):
    from atst_tools.runtime import evidence as runtime_evidence

    stopped: list[bool] = []
    original_stop = runtime_evidence.HostSampler.stop

    def recording_stop(self):
        stopped.append(True)
        return original_stop(self)

    monkeypatch.setattr(runtime_evidence.HostSampler, "stop", recording_stop)
    case = _case("too-big")
    case["slots"] = 2
    with pytest.raises(RuntimeError):
        harness.run_manifest(
            {"cases": [case]},
            harness.HarnessOptions(
                devices=("0",),
                output_dir=tmp_path / "out",
                telemetry=True,
                sampler_interval_s=0.1,
            ),
        )
    assert stopped == [True]


def test_case_launcher_and_extra_args_prefix_the_worker(tmp_path):
    case = harness.CaseSpec.from_mapping(
        {
            "case_id": "mpi",
            "config": "config.yaml",
            "launcher": "mpiexec -n 3",
            "args": ["--dry-run"],
        }
    )
    assert case.launcher == ("mpiexec", "-n", "3")
    command = harness.worker_command(case, tmp_path, ("0",), result_json=tmp_path / "r.json")
    assert command[:3] == ["mpiexec", "-n", "3"]
    assert command[-1] == "--dry-run"
    assert str(tmp_path / "r.json") in command

    listed = harness.CaseSpec.from_mapping(
        {"case_id": "list", "config": "c.yaml", "launcher": ["mpiexec", "-n", "2"]}
    )
    assert listed.launcher == ("mpiexec", "-n", "2")
    with pytest.raises(ValueError):
        harness.CaseSpec.from_mapping(
            {"case_id": "bad", "config": "c.yaml", "launcher": [1, 2]}
        )


def test_missing_worker_binary_fails_the_case_without_killing_the_batch(
    tmp_path, monkeypatch
):
    """A spawn error is recorded evidence, not a batch crash."""
    monkeypatch.setenv("HARNESS_LOG", str(tmp_path / "log.txt"))

    def missing_binary(case, workdir, devices):
        del workdir, devices
        return ["/nonexistent/atst-worker"]

    summary = harness.run_manifest(
        {"cases": [_case("broken")]},
        harness.HarnessOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=missing_binary,
            telemetry=False,
        ),
    )
    assert summary["failed"] == 1
    report = json.loads(
        (tmp_path / "out" / "broken" / harness.CASE_REPORT).read_text(encoding="utf-8")
    )
    assert report["status"] == "failed"
    assert report["classification"].startswith("spawn_error")
