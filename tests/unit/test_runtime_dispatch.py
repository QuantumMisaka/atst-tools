"""Tests for the light argv planner behind `atst` and the API runner."""

from __future__ import annotations

import argparse
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
    assert cli_dispatch.plan_runtime_launch(["run", "--dry-run", str(config)]) is None
    assert (
        cli_dispatch.plan_runtime_launch(
            ["run", "--mystery-flag", str(config)],
            environ={"CUDA_VISIBLE_DEVICES": "2,3"},
        )
        is None
    )


def test_unknown_options_with_runtime_requests_fail_closed(tmp_path, monkeypatch):
    """An option the isolation path cannot forward must not be dropped."""
    import pytest

    from atst_tools.runtime.errors import RuntimeConfigError

    config = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeConfigError) as caught:
        cli_dispatch.plan_runtime_launch(
            ["run", "--mystery-flag", str(config), "--devices", "0"],
            environ={"CUDA_VISIBLE_DEVICES": "2,3"},
        )
    assert "--mystery-flag" in str(caught.value)

    with pytest.raises(RuntimeConfigError):
        cli_dispatch.plan_runner_launch(
            ["--config", str(config), "--mystery-flag", "--devices", "0"],
            environ={"CUDA_VISIBLE_DEVICES": "2,3"},
        )


def test_cli_plan_binds_explicit_devices_for_the_worker(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = cli_dispatch.plan_runtime_launch(
        [
            "run",
            str(config),
            "--devices",
            "0",
            "--threads",
            "6",
            "--log-level",
            "WARNING",
        ],
        environ={"CUDA_VISIBLE_DEVICES": "2,3", "PATH": "/usr/bin"},
    )
    assert plan is not None
    assert plan.environment["CUDA_VISIBLE_DEVICES"] == "2"
    assert plan.environment[runtime_devices.RUNTIME_BOUND_ENV] == "1"
    assert plan.environment[runtime_devices.INHERITED_DEVICES_ENV] == "2,3"
    assert plan.environment[runtime_launch.THREAD_ENV_KEYS[0]] == "6"
    assert plan.environment[runtime_launch.LOG_LEVEL_ENV] == "WARNING"
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
            ["--config", str(config), "--dry-run"], environ={}
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


def test_runner_plan_uses_absolute_paths_for_the_reexec(tmp_path, monkeypatch):
    """The worker replaces the process image, so paths must not stay relative."""
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text("runtime:\n  devices: [0]\n", encoding="utf-8")
    plan = cli_dispatch.plan_runner_launch(
        ["--config", "config.yaml", "--workdir", "runs/one", "--devices", "0"],
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )
    assert plan is not None
    assert str(config) in plan.command
    assert str((tmp_path / "runs" / "one").resolve()) in plan.command
    assert "config.yaml" not in plan.command


def test_dry_run_with_runtime_options_still_binds_and_validates(tmp_path, monkeypatch):
    """`--dry-run` must not silently drop runtime options (argparse trap)."""
    config = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    plan = cli_dispatch.plan_runtime_launch(
        ["run", str(config), "--dry-run", "--devices", "0"],
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )
    assert plan is not None
    assert "--dry-run" in plan.command
    assert plan.environment["CUDA_VISIBLE_DEVICES"] == "2"

    runner_plan = cli_dispatch.plan_runner_launch(
        ["--config", str(config), "--dry-run", "--devices", "1"],
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )
    assert runner_plan is not None
    assert "--dry-run" in runner_plan.command
    assert runner_plan.environment["CUDA_VISIBLE_DEVICES"] == "3"


def _option_strings(parser: argparse.ArgumentParser) -> set[str]:
    return {option for action in parser._actions for option in action.option_strings}


def test_mirror_parsers_know_every_real_option():
    """The isolation planners must not drift behind the real CLI surfaces.

    A new `atst run` or runner option that the mirror does not know would make
    runtime-requested invocations fail closed as "unsupported option", so the
    mirrors are checked structurally here.
    """
    from atst_tools.api import runner as api_runner
    from atst_tools.scripts import cli_impl

    cli_parser = cli_impl.build_parser()
    subparsers = next(
        action
        for action in cli_parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    run_options = _option_strings(subparsers.choices["run"])
    mirror_options = _option_strings(cli_dispatch._cli_parser())
    missing_cli = run_options - mirror_options - {"-h", "--help"}
    assert (
        not missing_cli
    ), f"atst run options missing from the mirror: {sorted(missing_cli)}"

    runner_options = _option_strings(api_runner.build_parser())
    runner_mirror = _option_strings(cli_dispatch._runner_parser())
    missing_runner = runner_options - runner_mirror - {"-h", "--help"}
    assert (
        not missing_runner
    ), f"runner options missing from the mirror: {sorted(missing_runner)}"
