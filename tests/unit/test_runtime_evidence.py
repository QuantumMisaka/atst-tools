"""Tests for the runtime evidence sidecar and its host sampler."""

from __future__ import annotations

import json
from pathlib import Path
import types

import pytest

from atst_tools.runtime import devices as runtime_devices
from atst_tools.runtime import evidence as runtime_evidence
from atst_tools.runtime import launch as runtime_launch

UUID_A = "GPU-12345678-1234-1234-1234-123456789abc"
UUID_B = "GPU-abcdefab-cdef-abcd-efab-cdefabcdefab"


def _observed_sample():
    return {
        "status": runtime_evidence.STATUS_OBSERVED,
        "reason": None,
        "source": "nvidia-smi",
        "sampled_at": "2026-09-21T00:00:00+00:00",
        "devices": [
            {
                "uuid": UUID_A,
                "utilization_gpu_pct": 42.0,
                "memory_used_mib": 512.0,
                "memory_total_mib": 32768.0,
            }
        ],
    }


def test_sample_gpus_parses_rows_and_reports_unavailable(monkeypatch):
    def ok_run(*args, **kwargs):
        return types.SimpleNamespace(
            returncode=0,
            stdout=f"{UUID_A}, 42, 512, 32768\n",
        )

    monkeypatch.setattr(runtime_evidence.subprocess, "run", ok_run)
    observed = runtime_evidence.sample_gpus()
    assert observed["status"] == "observed"
    assert observed["devices"][0]["utilization_gpu_pct"] == 42.0
    assert observed["devices"][0]["memory_used_mib"] == 512.0

    def missing_run(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", missing_run)
    unavailable = runtime_evidence.sample_gpus()
    assert unavailable["status"] == "unavailable"
    assert "could not be executed" in unavailable["reason"]
    assert unavailable["devices"] == []

    def failing_run(*args, **kwargs):
        return types.SimpleNamespace(returncode=9, stdout="")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", failing_run)
    assert runtime_evidence.sample_gpus()["status"] == "unavailable"


def test_environment_and_device_facts_use_the_recorded_values():
    environ = {
        runtime_devices.RUNTIME_BOUND_ENV: "1",
        runtime_devices.INHERITED_DEVICES_ENV: "2,3",
        runtime_devices.EFFECTIVE_DEVICES_ENV: "2",
        runtime_devices.CUDA_VISIBLE_DEVICES: "2",
        "OMP_NUM_THREADS": "6",
    }
    facts = runtime_evidence.environment_facts(environ)
    assert facts["python"]
    assert facts["threads"]["OMP_NUM_THREADS"] == "6"
    assert "numpy" in facts["packages"]
    assert facts["cpu_affinity_count"] >= 1
    assert facts["threads_source"] is None

    devices = runtime_evidence.device_facts({"devices": [0], "binding": "inherit"}, environ)
    assert devices["bound"] is True
    assert devices["requested"] == ["0"]
    assert devices["inherited"] == ["2", "3"]
    assert devices["effective"] == ["2"]
    assert devices["allocation_identity"] == "unverified"

    coordinator_facts = dict(
        environ,
        **{
            runtime_devices.REQUESTED_DEVICES_ENV: "1",
            runtime_devices.REQUESTED_SOURCE_ENV: "--devices",
        },
    )
    from_coordinator = runtime_evidence.device_facts(None, coordinator_facts)
    assert from_coordinator["requested"] == ["1"]
    assert from_coordinator["requested_source"] == "--devices"
    assert from_coordinator["threads"] == 6

    counted = runtime_evidence.device_facts(
        None, {runtime_devices.ALLOCATION_DEVICES_ENV: "count=4"}
    )
    assert counted["allocation_identity"] == "unverified"
    listed = runtime_evidence.device_facts(
        None, {runtime_devices.ALLOCATION_DEVICES_ENV: f"{UUID_A},{UUID_B}"}
    )
    assert listed["allocation_identity"] == "verified"


def test_compute_process_sampling_reports_rows_and_permission_failures(monkeypatch):
    def ok_run(*args, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout="4242, 1024, GPU-abc\n")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", ok_run)
    observed = runtime_evidence.sample_compute_processes()
    assert observed["status"] == "observed"
    assert observed["processes"][0]["pid"] == 4242
    assert observed["processes"][0]["used_memory_mib"] == 1024.0
    assert observed["processes"][0]["attribution"] == "reported"

    def no_rows(*args, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", no_rows)
    empty = runtime_evidence.sample_compute_processes()
    assert empty["status"] == "unavailable"
    assert "no compute process" in empty["reason"]

    def denied(*args, **kwargs):
        return types.SimpleNamespace(returncode=6, stdout="")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", denied)
    refused = runtime_evidence.sample_compute_processes()
    assert refused["status"] == "unavailable"
    assert "status 6" in refused["reason"]


def test_session_writes_once_and_marks_partial_failures(tmp_path):
    session = runtime_evidence.EvidenceSession(
        workflow_dir=tmp_path,
        workflow="relax",
        attempt=2,
        environ={},
        config_runtime={"telemetry": {"enabled": False}},
        telemetry_enabled=False,
        telemetry_interval_s=1.0,
    )
    assert session.finish("partial", reason="boom") == "runtime_evidence.json"
    payload = json.loads((tmp_path / "runtime_evidence.json").read_text(encoding="utf-8"))
    assert payload["status"] == "partial"
    assert payload["reason"] == "boom"
    assert payload["attempt"] == 2
    assert payload["telemetry"]["sampler"]["status"] == "disabled"
    assert session.finish("complete") == "runtime_evidence.json"
    assert (
        json.loads((tmp_path / "runtime_evidence.json").read_text(encoding="utf-8"))[
            "status"
        ]
        == "partial"
    )


def test_start_session_respects_rank_and_request_gating(tmp_path):
    assert (
        runtime_evidence.start_session(
            workflow_dir=tmp_path, workflow="relax", config_runtime=None, rank=1
        )
        is None
    )
    assert (
        runtime_evidence.start_session(
            workflow_dir=tmp_path, workflow="relax", config_runtime=None, rank=0
        )
        is None
    )
    session = runtime_evidence.start_session(
        workflow_dir=tmp_path,
        workflow="relax",
        config_runtime={"telemetry": {"enabled": True, "interval_s": 0.05}},
        rank=0,
    )
    assert session is not None
    session.finish("complete")
    payload = json.loads((tmp_path / "runtime_evidence.json").read_text(encoding="utf-8"))
    assert payload["telemetry"]["enabled"] is True


def test_sampler_collects_host_samples(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_evidence, "sample_gpus", lambda timeout=5.0: _observed_sample())
    session = runtime_evidence.start_session(
        workflow_dir=tmp_path,
        workflow="relax",
        config_runtime={"telemetry": {"enabled": True, "interval_s": 0.05}},
        rank=0,
    )
    assert session is not None
    session.finish("complete")
    payload = json.loads((tmp_path / "runtime_evidence.json").read_text(encoding="utf-8"))
    sampler = payload["telemetry"]["sampler"]
    assert sampler["status"] == "observed"
    assert sampler["sample_count"] >= 1
    assert sampler["samples"][0]["devices"][0]["uuid"] == UUID_A


def _relax_config(**runtime):
    config = {
        "calculation": {"type": "relax", "init_structure": "x.traj"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }
    if runtime:
        config["runtime"] = runtime
    return config


def test_run_workflow_writes_evidence_and_links_the_manifest(monkeypatch, tmp_path):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda config, options: None)
    monkeypatch.setattr(
        runtime_evidence, "sample_gpus", lambda timeout=5.0: _observed_sample()
    )
    (tmp_path / "atst_artifacts.json").write_text(
        json.dumps({"workflow": "relax", "artifacts": [], "metadata": {}, "stages": []}),
        encoding="utf-8",
    )

    result = run_workflow(
        _relax_config(telemetry={"enabled": True, "interval_s": 0.05}), RunOptions()
    )

    assert result.status == "complete"
    evidence_path = tmp_path / runtime_evidence.EVIDENCE_FILENAME
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["schema"] == runtime_evidence.EVIDENCE_SCHEMA
    assert payload["status"] == "complete"
    assert payload["workflow"] == "relax"
    assert payload["telemetry"]["sampler"]["sample_count"] >= 1
    manifest = json.loads((tmp_path / "atst_artifacts.json").read_text(encoding="utf-8"))
    assert (
        manifest["metadata"][runtime_evidence.EVIDENCE_MANIFEST_KEY]
        == runtime_evidence.EVIDENCE_FILENAME
    )
    assert (
        result.metadata[runtime_evidence.EVIDENCE_MANIFEST_KEY]
        == runtime_evidence.EVIDENCE_FILENAME
    )


def test_run_workflow_keeps_partial_evidence_when_the_workflow_fails(monkeypatch, tmp_path):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services
    from atst_tools.api.models import WorkflowExecutionError

    monkeypatch.chdir(tmp_path)

    def boom(config, options):
        raise RuntimeError("force evaluation exploded")

    monkeypatch.setattr(services, "_dispatch_normalized", boom)

    with pytest.raises(WorkflowExecutionError):
        run_workflow(_relax_config(telemetry=True), RunOptions())

    payload = json.loads(
        (tmp_path / runtime_evidence.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["status"] == "partial"
    assert "exploded" in payload["reason"]


def test_measurement_failures_do_not_mask_the_workflow(monkeypatch, tmp_path):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda config, options: None)

    def broken_write(path, payload):
        raise OSError("disk full")

    monkeypatch.setattr(runtime_evidence, "_write_json_atomic", broken_write)
    (tmp_path / "atst_artifacts.json").write_text(
        json.dumps({"workflow": "relax", "artifacts": [], "metadata": {}, "stages": []}),
        encoding="utf-8",
    )

    result = run_workflow(_relax_config(telemetry=True), RunOptions())

    assert result.status == "complete"
    assert not (tmp_path / runtime_evidence.EVIDENCE_FILENAME).exists()
    manifest = json.loads((tmp_path / "atst_artifacts.json").read_text(encoding="utf-8"))
    assert runtime_evidence.EVIDENCE_MANIFEST_KEY not in manifest.get("metadata", {})


def test_start_session_failure_does_not_break_the_workflow(monkeypatch, tmp_path, capsys):
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import services

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda config, options: None)

    def broken_start(**kwargs):
        raise RuntimeError("sampler unavailable")

    monkeypatch.setattr(runtime_evidence, "start_session", broken_start)
    (tmp_path / "atst_artifacts.json").write_text(
        json.dumps({"workflow": "relax", "artifacts": [], "metadata": {}, "stages": []}),
        encoding="utf-8",
    )

    result = run_workflow(_relax_config(telemetry=True), RunOptions())

    assert result.status == "complete"
    assert "runtime evidence unavailable" in capsys.readouterr().err


class _FakeCalculator:
    """Minimal ASE-like calculator used to exercise the counter wrapper."""

    def calculate(self, atoms=None, properties=None, system_changes=None):
        return "energy"


def test_counters_track_builds_and_force_calls_only_when_enabled():
    from atst_tools.runtime import counters

    counters.reset()
    counters.set_enabled(False)


def test_gauges_record_live_instances_in_the_sidecar(tmp_path):
    from atst_tools.runtime import counters

    counters.reset()
    counters.set_gauge("dp.cached_instances", 2)
    assert counters.gauge_snapshot() == {"dp.cached_instances": 2.0}
    session = runtime_evidence.start_session(
        workflow_dir=tmp_path,
        workflow="relax",
        config_runtime={"telemetry": {"enabled": False}},
        environ={},
        rank=0,
    )
    assert session is not None
    session.finish("complete")
    payload = json.loads(
        (tmp_path / runtime_evidence.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["gauges"]["dp.cached_instances"] == 2.0
    counters.reset()
    counters.set_enabled(False)
    instrumented = counters.instrument_calculator(
        _FakeCalculator(),
        build_key="dp.calculator_built",
        call_key="dp.force_calls",
    )
    instrumented.calculate()
    assert counters.snapshot() == {}

    counters.set_enabled(True)
    instrumented = counters.instrument_calculator(
        _FakeCalculator(),
        build_key="dp.calculator_built",
        call_key="dp.force_calls",
    )
    instrumented.calculate()
    instrumented.calculate()
    assert counters.snapshot() == {"dp.calculator_built": 1, "dp.force_calls": 2}
    counters.reset()
    counters.set_enabled(False)


def test_evidence_payload_includes_process_counters(tmp_path):
    from atst_tools.runtime import counters

    counters.reset()
    session = runtime_evidence.start_session(
        workflow_dir=tmp_path,
        workflow="relax",
        config_runtime={"telemetry": {"enabled": False}},
        environ={},
        rank=0,
    )
    assert session is not None
    assert counters.is_enabled() is True
    counters.instrument_calculator(
        _FakeCalculator(),
        build_key="abacus.calculator_built",
        call_key="abacus.force_calls",
    ).calculate()
    session.finish("complete")
    payload = json.loads(
        (tmp_path / runtime_evidence.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["counters"] == {
        "abacus.calculator_built": 1,
        "abacus.force_calls": 1,
    }
    assert payload["counters_scope"] == "process"
    counters.reset()
    counters.set_enabled(False)
