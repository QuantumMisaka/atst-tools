"""Tests for the stable process runner around the public ATST API."""

from __future__ import annotations

import io
import json
from pathlib import Path

from helpers import FakeWorld, make_atoms

def _workflow_result(*, is_root: bool):
    from atst_tools.api import WorkflowResult

    return WorkflowResult(
        workflow="sella",
        status="complete",
        is_root=is_root,
        artifact_manifest="atst_artifacts.json",
        artifacts=({"path": "sella.traj", "kind": "trajectory"},),
        metadata={"backend_source": "abacuslite"},
    )


def test_runner_writes_success_document_and_restores_cwd(monkeypatch, tmp_path):
    """A serial runner publishes a host-readable result only from its workdir."""
    from atst_tools.api import runner

    workdir = tmp_path / "run"
    config = tmp_path / "atst_sella.yaml"
    result_path = workdir / "atst_api_result.json"
    observed = {}

    def fake_run_workflow(source, options):
        observed["source"] = source
        observed["options"] = options
        observed["cwd"] = Path.cwd()
        return _workflow_result(is_root=True)

    monkeypatch.setattr(runner, "_process_rank", lambda: 0)
    monkeypatch.setattr(runner, "run_workflow", fake_run_workflow)
    starting_directory = Path.cwd()

    code = runner.main(
        [
            "--config",
            str(config),
            "--workdir",
            str(workdir),
            "--result-json",
            result_path.name,
            "--restart",
            "--check-input-timeout",
            "45",
            "--abacus-executable",
            "abacus-custom",
        ]
    )

    assert code == 0
    assert Path.cwd() == starting_directory
    assert observed["source"] == config.resolve()
    assert observed["cwd"] == workdir.resolve()
    assert observed["options"].restart is True
    assert observed["options"].check_input_timeout == 45
    assert observed["options"].abacus_executable == "abacus-custom"
    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "schema": "atst-api-result-v1",
        "status": "success",
        "workflow": "sella",
        "is_root": True,
        "workdir": str(workdir.resolve()),
        "artifact_manifest": str((workdir / "atst_artifacts.json").resolve()),
        "artifacts": [{"path": "sella.traj", "kind": "trajectory"}],
        "metadata": {"backend_source": "abacuslite"},
    }


def test_runner_resolves_relative_config_before_entering_workdir(monkeypatch, tmp_path):
    """A documented relative config path is anchored at the caller directory."""
    from atst_tools.api import runner

    config = tmp_path / "config.yaml"
    config.write_text("calculation: {}\n", encoding="utf-8")
    workdir = tmp_path / "run"
    observed = {}

    def fake_run_workflow(source, options):
        observed["source"] = source
        observed["cwd"] = Path.cwd()
        return _workflow_result(is_root=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "_process_rank", lambda: 0)
    monkeypatch.setattr(runner, "run_workflow", fake_run_workflow)

    assert runner.main(["--config", "config.yaml", "--workdir", str(workdir)]) == 0
    assert observed == {"source": config.resolve(), "cwd": workdir.resolve()}


def test_runner_writes_typed_api_error_document(monkeypatch, tmp_path):
    """Public API errors produce stable nonzero diagnostics for an external host."""
    from atst_tools.api import runner
    from atst_tools.api.models import WorkflowExecutionError

    workdir = tmp_path / "run"
    error = WorkflowExecutionError(
        "Sella did not converge.", workflow="sella", context={"step": 12}
    )
    error.__cause__ = RuntimeError("optimizer failure")
    monkeypatch.setattr(runner, "_process_rank", lambda: 0)
    monkeypatch.setattr(
        runner,
        "run_workflow",
        lambda source, options: (_ for _ in ()).throw(error),
    )

    code = runner.main(
        [
            "--config",
            str(tmp_path / "atst_sella.yaml"),
            "--workdir",
            str(workdir),
            "--result-json",
            "atst_api_result.json",
        ]
    )

    assert code == 2
    assert json.loads((workdir / "atst_api_result.json").read_text(encoding="utf-8")) == {
        "schema": "atst-api-result-v1",
        "status": "error",
        "workflow": "sella",
        "error": {
            "type": "WorkflowExecutionError",
            "message": "Sella did not converge.",
            "workflow": "sella",
            "context": {"step": 12},
            "cause": {"type": "RuntimeError", "message": "optimizer failure"},
        },
    }


def test_runner_non_root_does_not_publish_result(monkeypatch, tmp_path):
    """An externally launched image rank never races root JSON publication."""
    from atst_tools.api import runner

    workdir = tmp_path / "run"
    monkeypatch.setattr(runner, "_process_rank", lambda: 1)
    monkeypatch.setattr(
        runner,
        "run_workflow",
        lambda source, options: _workflow_result(is_root=False),
    )

    code = runner.main(
        [
            "--config",
            str(tmp_path / "atst_neb.yaml"),
            "--workdir",
            str(workdir),
            "--result-json",
            "atst_api_result.json",
        ]
    )

    assert code == 0
    assert not (workdir / "atst_api_result.json").exists()


def _neb_band(energies):
    """Return a NEB-style band of single-point images shared with the API tests."""
    return [make_atoms("H", energy=energy) for energy in energies]


def _events_without_ts(events):
    """Return the progress events with the run-local timestamp stripped."""
    return [
        {key: value for key, value in event.items() if key != "ts"} for event in events
    ]


def test_runner_progress_emits_same_ndjson_events_as_python_api(
    monkeypatch, tmp_path, capsys
):
    """CLI --progress and the Python API produce the same NDJSON event set."""
    from atst_tools.api import RunOptions, run_workflow
    from atst_tools.api import runner, services

    workdir = tmp_path / "run"
    config = tmp_path / "atst_neb.yaml"
    config.write_text(
        "calculation:\n  type: neb\n  init_chain: chain.traj\n"
        "calculator:\n  name: abacus\n  abacus:\n    parameters: {}\n",
        encoding="utf-8",
    )
    band = _neb_band((0.0, 1.5, 3.2))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(services, "_dispatch_normalized", lambda config, options: band)
    monkeypatch.setattr(services, "get_ase_world", lambda: FakeWorld())
    monkeypatch.setattr(runner, "_process_rank", lambda: 0)

    api_stream = io.StringIO()
    run_workflow(
        {
            "calculation": {"type": "neb", "init_chain": "chain.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        RunOptions(progress=True, progress_stream=api_stream, world=FakeWorld()),
    )

    code = runner.main(
        ["--config", str(config), "--workdir", str(workdir), "--progress"]
    )

    assert code == 0
    captured = capsys.readouterr()
    api_events = [json.loads(line) for line in api_stream.getvalue().splitlines()]
    cli_events = [json.loads(line) for line in captured.out.splitlines()]
    assert cli_events
    assert [event["event"] for event in cli_events] == [
        "workflow_start",
        "image_step",
        "image_step",
        "image_step",
    ]
    assert _events_without_ts(cli_events) == _events_without_ts(api_events)
    assert all(isinstance(event["ts"], str) for event in cli_events)
