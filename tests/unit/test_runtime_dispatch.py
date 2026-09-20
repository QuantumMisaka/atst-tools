"""Tests for the light argv planner behind `atst` and the API runner."""

from __future__ import annotations

from pathlib import Path

from atst_tools.runtime import cli_dispatch
from atst_tools.runtime import devices as runtime_devices
from atst_tools.runtime import launch as runtime_launch


def _write_config(tmp_path: Path, body: str = "") -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        "calculation:\n  type: relax\n"
        "calculator:\n  name: dp\n  dp:\n    model: model.pt\n" + body,
        encoding="utf-8",
    )
    return path


def test_cli_plan_is_none_for_legacy_invocations(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cli_dispatch.plan_runtime_launch(["banner"]) is None
    assert cli_dispatch.plan_runtime_launch(["run", str(config)]) is None
    assert (
        cli_dispatch.plan_runtime_launch(
            ["run", "--dry-run", str(config), "--devices", "0"], environ={}
        )
        is None
    )
    assert (
        cli_dispatch.plan_runtime_launch(
            ["run", "--mystery-flag", str(config)], environ={"CUDA_VISIBLE_DEVICES": "2,3"}
        )
        is None
    )


def test_cli_plan_binds_explicit_devices_for_the_worker(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = cli_dispatch.plan_runtime_launch(
        ["run", str(config), "--devices", "0", "--threads", "6"],
        environ={"CUDA_VISIBLE_DEVICES": "2,3", "PATH": "/usr/bin"},
    )
    assert plan is not None
    assert plan.environment["CUDA_VISIBLE_DEVICES"] == "2"
    assert plan.environment[runtime_devices.RUNTIME_BOUND_ENV] == "1"
    assert plan.environment[runtime_devices.INHERITED_DEVICES_ENV] == "2,3"
    assert plan.environment[runtime_launch.THREAD_ENV_KEYS[0]] == "6"
    assert plan.command[1:3] == ["-m", runtime_launch.WORKER_MODULE]
    assert str(config) in plan.command
    assert plan.resolution.effective == ("2",)


def test_cli_plan_honours_yaml_and_environment_requests(tmp_path, monkeypatch):
    yaml_config = _write_config(tmp_path, body="runtime:\n  devices: [1]\n")
    monkeypatch.chdir(tmp_path)
    yaml_plan = cli_dispatch.plan_runtime_launch(
        ["run", str(yaml_config)], environ={"CUDA_VISIBLE_DEVICES": "2,3"}
    )
    assert yaml_plan is not None
    assert yaml_plan.environment["CUDA_VISIBLE_DEVICES"] == "3"

    env_plan = cli_dispatch.plan_runtime_launch(
        ["run", str(yaml_config)],
        environ={"CUDA_VISIBLE_DEVICES": "2,3", "ATST_VISIBLE_DEVICES": "0"},
    )
    assert env_plan is not None
    assert env_plan.request.devices_source == "runtime.devices"

    env_only_config = _write_config(tmp_path)
    env_only_plan = cli_dispatch.plan_runtime_launch(
        ["run", str(env_only_config)],
        environ={"CUDA_VISIBLE_DEVICES": "2,3", "ATST_VISIBLE_DEVICES": "1"},
    )
    assert env_only_plan is not None
    assert env_only_plan.request.devices_source == "ATST_VISIBLE_DEVICES"
    assert env_only_plan.environment["CUDA_VISIBLE_DEVICES"] == "3"


def test_runner_plan_rebinds_only_when_unbound(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    bound = {
        runtime_devices.RUNTIME_BOUND_ENV: "1",
        "CUDA_VISIBLE_DEVICES": "2,3",
    }
    assert (
        cli_dispatch.plan_runner_launch(
            ["--config", str(config), "--devices", "0"], environ=bound
        )
        is None
    )
    assert (
        cli_dispatch.plan_runner_launch(["--config", str(config)], environ={}) is None
    )
    assert (
        cli_dispatch.plan_runner_launch(
            ["--config", str(config), "--dry-run", "--devices", "0"], environ={}
        )
        is None
    )

    plan = cli_dispatch.plan_runner_launch(
        ["--config", str(config), "--devices", "0", "--result-json", "handoff.json"],
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )
    assert plan is not None
    assert plan.environment["CUDA_VISIBLE_DEVICES"] == "2"
    assert plan.command[1:3] == ["-m", runtime_launch.WORKER_MODULE]
    assert "--result-json" in plan.command
    assert "handoff.json" in plan.command
    assert "--devices" not in plan.command
