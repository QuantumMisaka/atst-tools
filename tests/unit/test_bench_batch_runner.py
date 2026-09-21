"""Tests for the finite-case batch runner (P3) with a stand-in worker."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

from atst_tools.bench import batch_runner, batch_worker
from atst_tools.runtime import launch as runtime_launch
from atst_tools.runtime.errors import RuntimeBindingError

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
    "telemetry": os.environ.get("ATST_TELEMETRY_ENABLED"),
    "pid": os.getpid(),
}
(workdir / "env.json").write_text(json.dumps(facts))
log = Path(os.environ["BATCH_RUNNER_LOG"])


def note(text):
    with log.open("a", encoding="utf-8") as handle:
        handle.write(text + "\\n")
        handle.flush()


note("start %s" % os.getpid())
if mode == "sleep":
    child = subprocess.Popen(["sleep", "120"])
    (workdir / "child.pid").write_text(str(child.pid))
    time.sleep(120)
elif mode == "stubborn":
    # A child that ignores SIGTERM and outlives its group leader: the batch runner
    # must still reclaim the whole group.
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time\\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n"
            "time.sleep(120)\\n",
        ]
    )
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


SHARED_STANDIN_SOURCE = """\
import argparse, json, os, signal, sys, time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--jobs", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args()
mode = os.environ.get("SHARED_STANDIN_MODE", "ok")
log = Path(os.environ["BATCH_RUNNER_LOG"])
out_dir = Path(args.out)
jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))


def note(text):
    with log.open("a", encoding="utf-8") as handle:
        handle.write(text + "\\n")
        handle.flush()


note("start %s" % os.getpid())
# Dump the bound-process facts the runner must publish, and fail loudly when
# they are missing: a shared worker without them cannot run a case config that
# declares a runtime: section.
bound = {
    key: os.environ[key]
    for key in sorted(os.environ)
    if key.startswith("ATST_") or key == "CUDA_VISIBLE_DEVICES"
}
(out_dir / "bound_env.json").write_text(json.dumps(bound, indent=2, sort_keys=True))
if bound.get("ATST_RUNTIME_BOUND") != "1":
    sys.stderr.write("stand-in: missing bound runtime facts\\n")
    sys.exit(7)
note(
    "env cuda=%s threads=%s attempt=%s cache=%s"
    % (
        os.environ.get("CUDA_VISIBLE_DEVICES"),
        os.environ.get("OMP_NUM_THREADS"),
        os.environ.get("ATST_ATTEMPT"),
        os.environ.get("NUMBA_CACHE_DIR"),
    )
)
for index, job in enumerate(jobs):
    case_id = job["case_id"]
    workdir = Path(job["workdir"])
    workdir.mkdir(parents=True, exist_ok=True)
    os.chdir(workdir)
    note("case %s" % case_id)
    if mode == "one_error_slow" and index == 2:
        # Leave the parent time to notice the failure of the previous case.
        time.sleep(2.0)
    if mode in ("one_error", "one_error_slow") and index == 1:
        status = "error"
        document = {
            "schema": "atst-api-result-v1",
            "status": "error",
            "workflow": "relax",
            "error": {
                "type": "StandinError",
                "message": "stand-in case failed",
                "workflow": "relax",
                "context": {},
                "cause": None,
            },
        }
    elif mode == "die_on_second" and index == 1:
        note("die %s" % os.getpid())
        os.kill(os.getpid(), signal.SIGKILL)
    elif mode == "sleep_on_second" and index == 1:
        time.sleep(120)
        status = "success"
        document = {"schema": "atst-api-result-v1", "status": "success"}
    else:
        status = "success"
        document = {"schema": "atst-api-result-v1", "status": "success"}
    case_dir = out_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "atst_api_result.json").write_text(json.dumps(document))
    # The literal format the parent parses; spelled here so the stand-in stays
    # independent of the package under test in this child process.
    print(
        "[batch_worker] case=%s status=%s wall_s=%.3f" % (case_id, status, 0.01),
        flush=True,
    )
note("end %s" % os.getpid())
"""


def _shared_standin(tmp_path: Path) -> Path:
    path = tmp_path / "standin_shared_worker.py"
    path.write_text(SHARED_STANDIN_SOURCE, encoding="utf-8")
    return path


def _shared_factory(script: Path):
    def build(jobs_path, out_dir):
        return [
            sys.executable,
            str(script),
            "--jobs",
            str(jobs_path),
            "--out",
            str(out_dir),
        ]

    return build


def _plain_case(case_id: str, **extra) -> dict:
    """One case without a per-case environment (shared mode sets it once)."""
    row = {"case_id": case_id, "config": f"{case_id}.yaml", "workdir": case_id}
    row.update(extra)
    return row


def _run_shared(tmp_path, monkeypatch, cases, mode=None, **overrides):
    script = _shared_standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    if mode is not None:
        monkeypatch.setenv("SHARED_STANDIN_MODE", mode)
    options = {
        "devices": ("1",),
        "output_dir": tmp_path / "out",
        "share_worker": True,
        "shared_worker_factory": _shared_factory(script),
        "telemetry": False,
    }
    options.update(overrides)
    return batch_runner.run_manifest(
        {"cases": cases}, batch_runner.BatchOptions(**options)
    )


def _statuses(summary) -> dict:
    return {row["case_id"]: row["status"] for row in summary["cases"]}


def test_default_workdir_is_the_configuration_directory(tmp_path, monkeypatch):
    """Cases run where their config lives, like a user-typed `atst run`."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    config_dir = tmp_path / "source_case"
    config_dir.mkdir()
    config = config_dir / "config.yaml"
    config.write_text("calculation: {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    summary = batch_runner.run_manifest(
        {"cases": [{"case_id": "inplace", "config": str(config)}]},
        batch_runner.BatchOptions(
            devices=("0",),
            output_dir=Path("out"),
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )
    assert summary["succeeded"] == 1
    assert (config_dir / "env.json").is_file()
    report = json.loads(
        (tmp_path / "out" / "inplace" / batch_runner.CASE_REPORT).read_text(
            encoding="utf-8"
        )
    )
    assert report["workdir"] == str(config_dir)
    assert (tmp_path / "out" / "inplace" / "worker.out").is_file()


def test_new_runs_write_the_current_artifact_names(tmp_path, monkeypatch):
    """A fresh batch writes ``case_report.json``/``batch_summary.json``/``worker.*``.

    Legacy trees keep ``harness_case.json``, ``harness_summary.json`` and
    ``harness_worker.*``; ``bench record`` still summarizes those (see
    ``tests/unit/test_bench_record.py``).
    """
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    summary = batch_runner.run_manifest(
        {"cases": [_case("artifacts")]},
        batch_runner.BatchOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )
    assert summary["succeeded"] == 1
    case_dir = tmp_path / "out" / "artifacts"
    assert (case_dir / "case_report.json").is_file()
    assert (case_dir / "worker.out").is_file()
    assert (case_dir / "worker.err").is_file()
    assert (tmp_path / "out" / "batch_summary.json").is_file()
    written = {path.name for path in (tmp_path / "out").rglob("*") if path.is_file()}
    assert not [name for name in written if "harness" in name]
    report = json.loads((case_dir / "case_report.json").read_text(encoding="utf-8"))
    assert report["stdout"].endswith("worker.out")
    assert report["stderr"].endswith("worker.err")


def test_cases_run_in_slots_with_isolated_dirs_and_reports(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    log = tmp_path / "log.txt"
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(log))
    summary = batch_runner.run_manifest(
        {"cases": [_case("alpha"), _case("beta")]},
        batch_runner.BatchOptions(
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
            (workdir / batch_runner.CASE_REPORT).read_text(encoding="utf-8")
        )
        assert report["status"] == "succeeded"
        assert report["result_json"] is not None
    events = [line.split()[0] for line in log.read_text(encoding="utf-8").splitlines()]
    assert events == ["start", "end", "start", "end"]


def test_relative_output_dir_is_resolved_before_launching_workers(
    tmp_path, monkeypatch
):
    """A relative --out must not leak into worker paths (nested-dir regression)."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    monkeypatch.chdir(tmp_path)
    summary = batch_runner.run_manifest(
        {"cases": [_case("rel")]},
        batch_runner.BatchOptions(
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
        (tmp_path / "out" / "rel" / batch_runner.CASE_REPORT).read_text(
            encoding="utf-8"
        )
    )
    assert Path(report["workdir"]).is_absolute()


def test_sequential_cases_do_not_trigger_the_no_progress_guard(tmp_path, monkeypatch):
    """A finishing case must not be mistaken for a stalled scheduler."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    cases = [_case("first", "sleep"), _case("second")]
    cases[0]["timeout_s"] = 1.0
    summary = batch_runner.run_manifest(
        {"cases": cases},
        batch_runner.BatchOptions(
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
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    case = _case("too-big")
    case["slots"] = 2
    with pytest.raises(RuntimeError) as caught:
        batch_runner.run_manifest(
            {"cases": [case]},
            batch_runner.BatchOptions(
                devices=("0",),
                output_dir=tmp_path / "out",
                worker_factory=_factory(script),
                telemetry=False,
            ),
        )
    assert "too-big" in str(caught.value)


def test_failure_keeps_evidence_and_stop_on_failure_skips_the_rest(
    tmp_path, monkeypatch
):
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    summary = batch_runner.run_manifest(
        {"cases": [_case("ok"), _case("bad", "fail_oom"), _case("later")]},
        batch_runner.BatchOptions(
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
        (tmp_path / "out" / "bad" / batch_runner.CASE_REPORT).read_text(
            encoding="utf-8"
        )
    )
    assert bad["classification"] == "oom"
    assert bad["exit_code"] == 3
    later = json.loads(
        (tmp_path / "out" / "later" / batch_runner.CASE_REPORT).read_text(
            encoding="utf-8"
        )
    )
    assert later["status"] == "skipped"
    assert later["classification"] == "stopped_after_failure"
    ids = {row["case_id"] for row in summary["cases"]}
    assert ids == {"ok", "bad", "later"}


def test_timeout_terminates_the_whole_worker_group(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    case = _case("slow", "sleep")
    case["timeout_s"] = 0.4
    summary = batch_runner.run_manifest(
        {"cases": [case]},
        batch_runner.BatchOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )

    assert summary["timed_out"] == 1
    report = json.loads(
        (tmp_path / "out" / "slow" / batch_runner.CASE_REPORT).read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "timeout"
    assert report["wall_s"] < 10
    child_pid = int((tmp_path / "out" / "slow" / "child.pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_termination_reclaims_children_that_ignore_sigterm(tmp_path, monkeypatch):
    """A SIGTERM-ignoring child must not survive the group cleanup."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    case = _case("stubborn", "stubborn")
    case["timeout_s"] = 0.5
    summary = batch_runner.run_manifest(
        {"cases": [case]},
        batch_runner.BatchOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )

    assert summary["timed_out"] == 1
    child_pid = int((tmp_path / "out" / "stubborn" / "child.pid").read_text())
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(child_pid, signal.SIGKILL)
        raise AssertionError("stubborn child survived the group cleanup")


def test_cancel_marks_remaining_cases_and_writes_the_summary(tmp_path, monkeypatch):
    script = _standin(tmp_path)
    log = tmp_path / "log.txt"
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(log))
    stop_event = threading.Event()
    results: list[dict] = []
    failures: list[BaseException] = []

    def run():
        try:
            results.append(
                batch_runner.run_manifest(
                    {"cases": [_case("slow-1", "sleep"), _case("slow-2", "sleep")]},
                    batch_runner.BatchOptions(
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
        (tmp_path / "out" / batch_runner.SUMMARY_REPORT).read_text(encoding="utf-8")
    )
    assert summary["status"] == "cancelled"
    statuses = {row["case_id"]: row["status"] for row in summary["cases"]}
    assert set(statuses) == {"slow-1", "slow-2"}
    assert statuses["slow-2"] in {"skipped", "timeout", "failed"}
    assert summary["succeeded"] == 0


def test_manifest_validation_rejects_bad_rows(tmp_path):
    options = batch_runner.BatchOptions(devices=("0",), output_dir=tmp_path)
    with pytest.raises(ValueError):
        batch_runner.load_cases({"cases": []}, options)
    with pytest.raises(ValueError):
        batch_runner.load_cases(
            {"cases": [{"case_id": "", "config": "x.yaml"}]}, options
        )
    with pytest.raises(ValueError):
        batch_runner.load_cases({"cases": [_case("a"), _case("a")]}, options)


def test_manifest_rejects_shared_case_workdirs(tmp_path):
    """Cases that would run in the same directory are rejected."""
    options = batch_runner.BatchOptions(devices=("0",), output_dir=tmp_path)
    shared = [dict(_case("a"), workdir="work"), dict(_case("b"), workdir="work")]
    with pytest.raises(ValueError, match="distinct directories"):
        batch_runner.load_cases({"cases": shared}, options)
    distinct = [dict(_case("a"), workdir="work-a"), dict(_case("b"), workdir="work-b")]
    assert [
        case.workdir for case in batch_runner.load_cases({"cases": distinct}, options)
    ] == [
        "work-a",
        "work-b",
    ]


def test_manifest_rejects_implicit_config_directory_collisions(tmp_path):
    """Without workdirs, two cases in one configuration directory collide."""
    options = batch_runner.BatchOptions(devices=("0",), output_dir=tmp_path)
    same_dir = [
        {"case_id": "a", "config": "shared/config-a.yaml"},
        {"case_id": "b", "config": "shared/config-b.yaml"},
    ]
    with pytest.raises(ValueError, match="distinct directories"):
        batch_runner.load_cases({"cases": same_dir}, options)

    separate = [
        {"case_id": "a", "config": "dir-a/config.yaml"},
        {"case_id": "b", "config": "dir-b/config.yaml"},
    ]
    cases = batch_runner.load_cases({"cases": separate}, options)
    assert [case.workdir for case in cases] == [None, None]


def test_case_environment_merges_case_specific_values(tmp_path):
    case = batch_runner.CaseSpec.from_mapping(
        {
            "case_id": "case",
            "config": "config.yaml",
            "threads": 4,
            "env": {"MY_FLAG": "1"},
        }
    )
    env = batch_runner.case_environment(
        case, ("3",), base={"PATH": "/usr/bin"}, attempt=2, workdir=tmp_path
    )
    assert env["CUDA_VISIBLE_DEVICES"] == "3"
    assert env["OMP_NUM_THREADS"] == "4"
    assert env["ATST_THREADS_SOURCE"] == "harness"
    assert env["ATST_ATTEMPT"] == "2"
    assert env["MY_FLAG"] == "1"


def test_manifest_thread_budget_reaches_the_abacus_factory(tmp_path, monkeypatch):
    """The per-case manifest budget must survive the calculator's OMP rules.

    P5 measured ABACUS with a single thread even though the manifest asked for
    four, because the batch runner (then ``harness``) wrote the thread keys
    without marking them as a caller budget (see the GPU node tuning review
    map).
    """
    from atst_tools.calculators.factory import _effective_omp

    case = batch_runner.CaseSpec.from_mapping(
        {"case_id": "case", "config": "config.yaml", "threads": 4}
    )
    env = batch_runner.case_environment(
        case, ("0",), base={}, attempt=1, workdir=tmp_path
    )
    monkeypatch.setenv("OMP_NUM_THREADS", env["OMP_NUM_THREADS"])
    monkeypatch.setenv("ATST_THREADS_SOURCE", env["ATST_THREADS_SOURCE"])
    assert _effective_omp({}, None) == 4
    assert os.environ["OMP_NUM_THREADS"] == "4"


def test_case_environment_requests_per_case_evidence_by_default(tmp_path):
    case = batch_runner.CaseSpec.from_mapping({"case_id": "c", "config": "c.yaml"})
    env = batch_runner.case_environment(
        case, ("0",), base={}, attempt=1, workdir=tmp_path
    )
    assert env["ATST_TELEMETRY_ENABLED"] == "1"
    quiet = batch_runner.case_environment(
        case, ("0",), base={}, attempt=1, workdir=tmp_path, case_telemetry=False
    )
    assert "ATST_TELEMETRY_ENABLED" not in quiet


def test_run_manifest_forwards_case_telemetry_to_workers(tmp_path, monkeypatch):
    """`case_telemetry=False` must reach the worker environment."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))

    for case_telemetry, expected in ((False, None), (True, "1")):
        out = tmp_path / f"out-{case_telemetry}"
        batch_runner.run_manifest(
            {"cases": [_case("only")]},
            batch_runner.BatchOptions(
                devices=("0",),
                output_dir=out,
                worker_factory=_factory(script),
                telemetry=False,
                case_telemetry=case_telemetry,
            ),
        )
        facts = json.loads((out / "only" / "env.json").read_text(encoding="utf-8"))
        assert facts["telemetry"] == expected


def test_slot_pool_hands_out_distinct_devices_for_multi_slot_cases():
    pool = batch_runner._SlotPool(("0", "1"), 2)
    assert pool.acquire("multi", 2) == ("0", "1")
    pool.release("multi")
    single_device = batch_runner._SlotPool(("0",), 2)
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
        batch_runner.run_manifest(
            {"cases": [case]},
            batch_runner.BatchOptions(
                devices=("0",),
                output_dir=tmp_path / "out",
                telemetry=True,
                sampler_interval_s=0.1,
            ),
        )
    assert stopped == [True]


def test_unexpected_errors_terminate_surviving_workers(monkeypatch, tmp_path):
    """Any exit path must terminate worker groups (review F1)."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    original_sleep = batch_runner.time.sleep
    ticks = {"count": 0}

    def exploding_sleep(seconds):
        ticks["count"] += 1
        if ticks["count"] >= 3:
            raise RuntimeError("simulated scheduler failure")
        return original_sleep(seconds)

    monkeypatch.setattr(batch_runner.time, "sleep", exploding_sleep)
    case = _case("slow", "sleep")
    case["timeout_s"] = 60
    with pytest.raises(RuntimeError):
        batch_runner.run_manifest(
            {"cases": [case]},
            batch_runner.BatchOptions(
                devices=("0",),
                output_dir=tmp_path / "out",
                worker_factory=_factory(script),
                telemetry=False,
            ),
        )
    pid_path = tmp_path / "out" / "slow" / "child.pid"
    assert pid_path.is_file()
    child_pid = int(pid_path.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        original_sleep(0.1)
    else:
        raise AssertionError(f"worker group survived the failed batch: {child_pid}")


def test_launcher_rank_multiplier_counts_against_the_cpu_budget(tmp_path, monkeypatch):
    """`mpiexec -n 4` with threads=4 must not fit a budget of 8 (review F8)."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    case = _case("mpi")
    case["launcher"] = ["mpiexec", "-n", "4"]
    case["threads"] = 4
    with pytest.raises(RuntimeError) as caught:
        batch_runner.run_manifest(
            {"cases": [case]},
            batch_runner.BatchOptions(
                devices=("0",),
                output_dir=tmp_path / "out",
                cpu_budget=8,
                worker_factory=_factory(script),
                telemetry=False,
            ),
        )
    assert "mpi" in str(caught.value)


def test_ranks_resolution_prefers_declared_then_parsed_then_assumed():
    parsed = batch_runner.CaseSpec.from_mapping(
        {"case_id": "a", "config": "a.yaml", "launcher": ["mpiexec", "-n", "3"]}
    )
    assert batch_runner.resolve_case_ranks(parsed) == (3, "parsed")
    declared = batch_runner.CaseSpec.from_mapping(
        {
            "case_id": "b",
            "config": "b.yaml",
            "launcher": ["mpiexec", "-n", "3"],
            "ranks": 2,
        }
    )
    assert batch_runner.resolve_case_ranks(declared) == (2, "declared")
    assumed = batch_runner.CaseSpec.from_mapping(
        {"case_id": "c", "config": "c.yaml", "launcher": ["srun"]}
    )
    assert batch_runner.resolve_case_ranks(assumed) == (1, "assumed-1")
    serial = batch_runner.CaseSpec.from_mapping({"case_id": "d", "config": "d.yaml"})
    assert batch_runner.resolve_case_ranks(serial) == (1, "serial")
    assert batch_runner.case_thread_cost(parsed) == 3 * parsed.threads
    with pytest.raises(ValueError):
        batch_runner.CaseSpec.from_mapping(
            {"case_id": "e", "config": "e.yaml", "ranks": 0}
        )


def test_case_launcher_and_extra_args_prefix_the_worker(tmp_path):
    case = batch_runner.CaseSpec.from_mapping(
        {
            "case_id": "mpi",
            "config": "config.yaml",
            "launcher": "mpiexec -n 3",
            "args": ["--dry-run"],
        }
    )
    assert case.launcher == ("mpiexec", "-n", "3")
    command = batch_runner.worker_command(
        case, tmp_path, ("0",), result_json=tmp_path / "r.json"
    )
    assert command[:3] == ["mpiexec", "-n", "3"]
    assert command[-1] == "--dry-run"
    assert str(tmp_path / "r.json") in command

    listed = batch_runner.CaseSpec.from_mapping(
        {"case_id": "list", "config": "c.yaml", "launcher": ["mpiexec", "-n", "2"]}
    )
    assert listed.launcher == ("mpiexec", "-n", "2")
    with pytest.raises(ValueError):
        batch_runner.CaseSpec.from_mapping(
            {"case_id": "bad", "config": "c.yaml", "launcher": [1, 2]}
        )


def test_missing_worker_binary_fails_the_case_without_killing_the_batch(
    tmp_path, monkeypatch
):
    """A spawn error is recorded evidence, not a batch crash."""
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))

    def missing_binary(case, workdir, devices):
        del workdir, devices
        return ["/nonexistent/atst-worker"]

    summary = batch_runner.run_manifest(
        {"cases": [_case("broken")]},
        batch_runner.BatchOptions(
            devices=("0",),
            output_dir=tmp_path / "out",
            worker_factory=missing_binary,
            telemetry=False,
        ),
    )
    assert summary["failed"] == 1
    report = json.loads(
        (tmp_path / "out" / "broken" / batch_runner.CASE_REPORT).read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "failed"
    assert report["classification"].startswith("spawn_error")


def test_share_worker_runs_the_whole_batch_in_one_process(tmp_path, monkeypatch):
    """One child carries all cases and the report layout stays the same."""
    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [_plain_case("alpha"), _plain_case("beta"), _plain_case("gamma")],
    )

    lines = (tmp_path / "log.txt").read_text(encoding="utf-8").splitlines()
    assert [line.split()[0] for line in lines] == [
        "start",
        "env",
        "case",
        "case",
        "case",
        "end",
    ]
    environment = dict(part.split("=") for part in lines[1].split()[1:])
    assert environment["cuda"] == "1"
    assert environment["threads"] == "1"
    assert environment["attempt"] == "1"
    assert Path(environment["cache"]).is_dir()

    assert summary["status"] == "complete"
    assert summary["cases_total"] == 3
    assert summary["succeeded"] == 3
    assert summary["failed"] == 0
    assert summary["devices"] == ["1"]
    assert summary["shared_worker"]["enabled"] is True
    assert summary["shared_worker"]["devices"] == ["1"]
    assert summary["shared_worker"]["threads"] == 1
    assert summary["shared_worker"]["exit_code"] == 0
    assert summary["shared_worker"]["pid"] is not None

    for case_id in ("alpha", "beta", "gamma"):
        case_dir = tmp_path / "out" / case_id
        report = json.loads((case_dir / batch_runner.CASE_REPORT).read_text("utf-8"))
        assert report["status"] == "succeeded"
        assert report["shared_worker"] is True
        assert report["wall_s"] > 0
        assert report["result_json"] == str(case_dir / "atst_api_result.json")
        assert report["stdout"] == str(tmp_path / "out" / "worker.out")
        assert report["stderr"] == str(tmp_path / "out" / "worker.err")


def test_share_worker_publishes_the_bound_runtime_facts(tmp_path, monkeypatch):
    """The shared worker is a *bound* worker, so `runtime:` configs are accepted.

    Regression for the controller's blocking finding: every DP/ABACUS/CCQN case
    config declares a ``runtime:`` section, and an unbound shared worker refuses
    the whole config with "embedding API cannot rebind devices".
    """
    config = tmp_path / "configs" / "bound.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "runtime:\n  devices: [0]\n\ncalculation:\n  type: md\n", encoding="utf-8"
    )
    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [{"case_id": "bound", "config": str(config), "workdir": "bound"}],
    )
    assert summary["succeeded"] == 1

    # The facts are read back from the child's own environment, not from the
    # parent that built them.
    child_env = json.loads(
        (tmp_path / "out" / "bound_env.json").read_text(encoding="utf-8")
    )
    assert child_env["ATST_RUNTIME_BOUND"] == "1"
    assert child_env["ATST_INHERITED_DEVICES"] == "1"
    assert child_env["ATST_EFFECTIVE_DEVICES"] == "1"
    assert child_env["ATST_BINDING"] == "inherit"
    assert child_env["CUDA_VISIBLE_DEVICES"] == "1"
    # No requested-device record: each case is verified against the published
    # binding, which is what keeps a contradicting request a loud failure.
    assert "ATST_REQUESTED_DEVICES" not in child_env
    assert "ATST_REQUESTED_SOURCE" not in child_env

    # The config's own runtime request passes the real runtime contract ...
    from atst_tools.runtime.cli_dispatch import read_runtime_section

    declared = read_runtime_section(config)
    assert declared == {"devices": [0]}
    runtime_launch.ensure_runtime_contract({"runtime": declared}, environ=child_env)
    runtime_launch.ensure_runtime_contract({}, environ=child_env)
    # ... while a request outside the bound slot is still refused per case.
    with pytest.raises(RuntimeBindingError, match="outside the inherited"):
        runtime_launch.ensure_runtime_contract(
            {"runtime": {"devices": [1]}}, environ=child_env
        )


def test_share_worker_bound_facts_unblock_a_runtime_section_config(
    tmp_path, monkeypatch
):
    """End-to-end regression through the real worker and the real API."""
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "case" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "runtime:\n  devices: [0]\n\n"
        "calculation:\n  type: relax\n  init_structure: missing.traj\n"
        "calculator:\n  name: abacus\n  abacus:\n    parameters: {}\n",
        encoding="utf-8",
    )
    job = batch_worker.Job(
        case_id="rt", config=str(config), workdir=str(tmp_path / "case")
    )
    for key in (
        "ATST_RUNTIME_BOUND",
        "ATST_INHERITED_DEVICES",
        "ATST_EFFECTIVE_DEVICES",
        "ATST_BINDING",
        "ATST_REQUESTED_DEVICES",
        "ATST_REQUESTED_SOURCE",
    ):
        monkeypatch.delenv(key, raising=False)

    # Without the published facts the embedded API refuses the config outright.
    assert batch_worker.run_job(job, tmp_path / "unbound") == batch_worker.STATUS_ERROR
    unbound = json.loads(
        (tmp_path / "unbound" / "rt" / batch_worker.RESULT_JSON).read_text("utf-8")
    )
    assert unbound["error"]["type"] == "RuntimeBindingError"
    assert "rebind devices" in unbound["error"]["message"]

    # With them the same case passes the runtime contract and fails only for its
    # own reason, which proves the config ran as written.
    options = batch_runner.BatchOptions(
        devices=("0",),
        output_dir=tmp_path / "batch",
        share_worker=True,
        telemetry=False,
        case_telemetry=False,
    )
    cases = batch_runner.load_cases(
        {"cases": [{"case_id": "rt", "config": str(config), "workdir": "rt"}]}, options
    )
    plan = batch_runner.shared_batch_plan(
        cases, options, output_dir=tmp_path / "batch", cpu_limit=options.cpu_limit()
    )
    for key, value in plan.env.items():
        monkeypatch.setenv(key, value)

    assert batch_worker.run_job(job, tmp_path / "bound") == batch_worker.STATUS_ERROR
    bound = json.loads(
        (tmp_path / "bound" / "rt" / batch_worker.RESULT_JSON).read_text("utf-8")
    )
    assert bound["error"]["type"] == "WorkflowExecutionError"
    assert "missing.traj" in bound["error"]["message"]


def test_share_worker_case_reports_match_the_per_case_schema(tmp_path, monkeypatch):
    """A shared case report is the per-case document plus the mode marker."""
    script = _standin(tmp_path)
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(tmp_path / "log.txt"))
    batch_runner.run_manifest(
        {"cases": [_case("solo")]},
        batch_runner.BatchOptions(
            devices=("1",),
            output_dir=tmp_path / "out-single",
            worker_factory=_factory(script),
            telemetry=False,
        ),
    )
    _run_shared(
        tmp_path, monkeypatch, [_plain_case("alpha")], output_dir=tmp_path / "out"
    )

    single = json.loads(
        (tmp_path / "out-single" / "solo" / batch_runner.CASE_REPORT).read_text("utf-8")
    )
    shared = json.loads(
        (tmp_path / "out" / "alpha" / batch_runner.CASE_REPORT).read_text("utf-8")
    )
    assert set(shared) == set(single) | {"shared_worker"}
    assert shared["schema"] == single["schema"]
    summary = json.loads(
        (tmp_path / "out" / batch_runner.SUMMARY_REPORT).read_text("utf-8")
    )
    assert set(summary) == set(
        json.loads(
            (tmp_path / "out-single" / batch_runner.SUMMARY_REPORT).read_text("utf-8")
        )
    ) | {"shared_worker"}


def test_share_worker_records_a_failing_case_and_keeps_going(tmp_path, monkeypatch):
    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [_plain_case("alpha"), _plain_case("beta"), _plain_case("gamma")],
        mode="one_error",
    )

    assert _statuses(summary) == {
        "alpha": "succeeded",
        "beta": "failed",
        "gamma": "succeeded",
    }
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1
    assert summary["shared_worker"]["exit_code"] == 0
    beta = json.loads(
        (tmp_path / "out" / "beta" / batch_runner.CASE_REPORT).read_text("utf-8")
    )
    assert beta["classification"].startswith("case_error: StandinError")
    assert beta["result_json"] is not None
    events = (tmp_path / "log.txt").read_text(encoding="utf-8").splitlines()
    assert len([line for line in events if line.startswith("start")]) == 1
    assert len([line for line in events if line.startswith("case")]) == 3


def test_share_worker_death_fails_the_running_and_remaining_cases(
    tmp_path, monkeypatch
):
    """A dead shared worker is never a silent skip (review requirement)."""
    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [_plain_case("alpha"), _plain_case("beta"), _plain_case("gamma")],
        mode="die_on_second",
    )

    assert _statuses(summary) == {
        "alpha": "succeeded",
        "beta": "failed",
        "gamma": "failed",
    }
    assert summary["succeeded"] == 1
    assert summary["failed"] == 2
    assert summary["shared_worker"]["exit_code"] == -signal.SIGKILL
    for case_id in ("beta", "gamma"):
        report = json.loads(
            (tmp_path / "out" / case_id / batch_runner.CASE_REPORT).read_text("utf-8")
        )
        assert report["classification"] == "shared worker exited"
        assert report["exit_code"] == -signal.SIGKILL
    gamma = json.loads(
        (tmp_path / "out" / "gamma" / batch_runner.CASE_REPORT).read_text("utf-8")
    )
    assert gamma["wall_s"] == 0.0
    events = (tmp_path / "log.txt").read_text(encoding="utf-8").splitlines()
    assert len([line for line in events if line.startswith("start")]) == 1
    assert not [line for line in events if line.startswith("end")]


def test_share_worker_timeout_stops_the_worker_and_reports_the_rest(
    tmp_path, monkeypatch
):
    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [
            _plain_case("alpha"),
            _plain_case("beta", timeout_s=0.5),
            _plain_case("gamma"),
        ],
        mode="sleep_on_second",
    )

    assert _statuses(summary) == {
        "alpha": "succeeded",
        "beta": "timeout",
        "gamma": "failed",
    }
    assert summary["timed_out"] == 1
    gamma = json.loads(
        (tmp_path / "out" / "gamma" / batch_runner.CASE_REPORT).read_text("utf-8")
    )
    assert gamma["classification"] == "shared worker exited"


def test_share_worker_stops_the_batch_after_the_first_failure_when_asked(
    tmp_path, monkeypatch
):
    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [_plain_case("alpha"), _plain_case("beta"), _plain_case("gamma")],
        mode="one_error_slow",
        continue_on_failure=False,
    )

    assert _statuses(summary) == {
        "alpha": "succeeded",
        "beta": "failed",
        "gamma": "skipped",
    }
    gamma = json.loads(
        (tmp_path / "out" / "gamma" / batch_runner.CASE_REPORT).read_text("utf-8")
    )
    assert gamma["classification"] == "stopped_after_failure"


def test_share_worker_spawn_failure_records_every_case(tmp_path, monkeypatch):
    def missing_binary(jobs_path, out_dir):
        del jobs_path, out_dir
        return ["/nonexistent/atst-shared-worker"]

    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [_plain_case("alpha"), _plain_case("beta")],
        shared_worker_factory=missing_binary,
    )

    assert _statuses(summary) == {"alpha": "failed", "beta": "failed"}
    for case_id in ("alpha", "beta"):
        report = json.loads(
            (tmp_path / "out" / case_id / batch_runner.CASE_REPORT).read_text("utf-8")
        )
        assert report["classification"].startswith("spawn_error")


def test_share_worker_cancel_terminates_the_child_and_marks_the_rest(
    tmp_path, monkeypatch
):
    """A cancelled batch must not leave the shared worker running."""
    script = _shared_standin(tmp_path)
    log = tmp_path / "log.txt"
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(log))
    monkeypatch.setenv("SHARED_STANDIN_MODE", "sleep_on_second")
    stop_event = threading.Event()
    results: list[dict] = []
    failures: list[BaseException] = []

    def run():
        try:
            results.append(
                batch_runner.run_manifest(
                    {"cases": [_plain_case("alpha"), _plain_case("beta")]},
                    batch_runner.BatchOptions(
                        devices=("1",),
                        output_dir=tmp_path / "out",
                        share_worker=True,
                        shared_worker_factory=_shared_factory(script),
                        telemetry=False,
                        stop_event=stop_event,
                    ),
                )
            )
        except BaseException as exc:  # SystemExit("batch cancelled")
            failures.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if log.exists() and "case beta" in log.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    stop_event.set()
    worker.join(timeout=30)

    assert not worker.is_alive()
    assert results == [] and failures
    summary = json.loads(
        (tmp_path / "out" / batch_runner.SUMMARY_REPORT).read_text(encoding="utf-8")
    )
    assert summary["status"] == "cancelled"
    assert _statuses(summary) == {"alpha": "succeeded", "beta": "skipped"}
    beta = json.loads(
        (tmp_path / "out" / "beta" / batch_runner.CASE_REPORT).read_text("utf-8")
    )
    assert beta["classification"] == "cancelled"


def test_unexpected_errors_terminate_the_shared_worker(monkeypatch, tmp_path):
    """Any exit path must terminate the one shared worker group (review F1)."""
    log = tmp_path / "log.txt"
    monkeypatch.setenv("BATCH_RUNNER_LOG", str(log))
    monkeypatch.setenv("SHARED_STANDIN_MODE", "sleep_on_second")
    original_sleep = batch_runner.time.sleep
    state = {"ticks": 0, "exploded": False}

    def second_case_started() -> bool:
        return log.exists() and "case beta" in log.read_text(encoding="utf-8")

    def exploding_sleep(seconds):
        state["ticks"] += 1
        if not state["exploded"] and state["ticks"] >= 3 and second_case_started():
            state["exploded"] = True
            raise RuntimeError("simulated scheduler failure")
        return original_sleep(seconds)

    monkeypatch.setattr(batch_runner.time, "sleep", exploding_sleep)
    with pytest.raises(RuntimeError):
        _run_shared(tmp_path, monkeypatch, [_plain_case("alpha"), _plain_case("beta")])

    pid = int(log.read_text(encoding="utf-8").splitlines()[0].split()[1])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        original_sleep(0.1)
    else:
        raise AssertionError(f"shared worker survived the failed batch: {pid}")


def test_share_worker_rejects_more_than_one_slot(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="--slots 1"):
        _run_shared(
            tmp_path,
            monkeypatch,
            [_plain_case("alpha")],
            slots_per_device=2,
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": [_plain_case("alpha")]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="--slots 1"):
        batch_runner.main(
            [
                "--manifest",
                str(manifest),
                "--out",
                str(tmp_path / "out"),
                "--devices",
                "0",
                "--slots",
                "2",
                "--share-worker",
                "--no-telemetry",
            ]
        )


def test_share_worker_rejects_a_case_launcher(tmp_path, monkeypatch):
    """A per-case launcher cannot be honoured by one process; never drop it."""
    with pytest.raises(RuntimeError, match="launcher"):
        _run_shared(
            tmp_path,
            monkeypatch,
            [_plain_case("alpha", launcher=["mpiexec", "-n", "2"])],
        )


def test_share_worker_rejects_conflicting_case_environments(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="same env mapping"):
        _run_shared(
            tmp_path,
            monkeypatch,
            [_case("alpha", "ok"), _case("beta", "fail")],
        )


def test_share_worker_uses_the_largest_case_thread_cost_once(tmp_path, monkeypatch):
    summary = _run_shared(
        tmp_path,
        monkeypatch,
        [_plain_case("alpha", threads=2), _plain_case("beta", threads=4)],
    )

    lines = (tmp_path / "log.txt").read_text(encoding="utf-8").splitlines()
    environment = dict(part.split("=") for part in lines[1].split()[1:])
    assert environment["threads"] == "4"
    assert summary["shared_worker"]["threads"] == 4
    assert {row["threads"] for row in summary["cases"]} == {4}


def test_share_worker_rejects_a_thread_budget_the_batch_cannot_hold(
    tmp_path, monkeypatch
):
    with pytest.raises(RuntimeError, match="CPU budget"):
        _run_shared(
            tmp_path,
            monkeypatch,
            [_plain_case("alpha", threads=4)],
            cpu_budget=2,
        )


def test_cli_help_documents_share_worker(capsys):
    with pytest.raises(SystemExit):
        batch_runner.main(["--help"])
    assert "--share-worker" in capsys.readouterr().out
