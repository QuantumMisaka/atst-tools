"""Tests for the shared batch worker (``--share-worker`` mode)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atst_tools.api.models import ConfigValidationError, WorkflowResult
from atst_tools.bench import batch_worker


def _workflow_result() -> WorkflowResult:
    return WorkflowResult(
        workflow="relax",
        status="success",
        is_root=True,
        artifact_manifest="atst_artifacts.json",
        artifacts=({"path": "atst_artifacts.json"},),
        metadata={"engine": "standin"},
    )


@pytest.fixture
def fake_api(monkeypatch):
    """Replace the public API with a stand-in and record one entry per case."""
    import atst_tools.api as api

    calls: list[tuple[str, Path]] = []

    def fake_run_workflow(config_source, options=None):
        del options
        path = Path(config_source)
        calls.append((path.name, Path.cwd()))
        (Path.cwd() / "atst_artifacts.json").write_text("{}\n", encoding="utf-8")
        if path.name.startswith("boom"):
            raise ConfigValidationError(
                "bad configuration", workflow="relax", context={"key": "value"}
            )
        if path.name.startswith("crash"):
            raise ValueError("unexpected stand-in failure")
        return _workflow_result()

    monkeypatch.setattr(api, "run_workflow", fake_run_workflow)
    return calls


def _jobs_file(tmp_path: Path, names: list[tuple[str, str]]) -> Path:
    """Write a job list; every row is ``(case_id, config file name)``."""
    rows = [
        {
            "case_id": case_id,
            "config": str(tmp_path / "configs" / name),
            "workdir": str(tmp_path / "cases" / case_id),
        }
        for case_id, name in names
    ]
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return path


def _progress_lines(capsys) -> list[tuple[str, str, float]]:
    parsed = [
        batch_worker.parse_progress_line(line)
        for line in capsys.readouterr().out.splitlines()
    ]
    return [item for item in parsed if item is not None]


def test_the_progress_format_is_the_documented_literal():
    """The parent parses this exact line; keep the spelling frozen."""
    assert (
        batch_worker.format_progress_line("case-a", "success", 1.0)
        == "[batch_worker] case=case-a status=success wall_s=1.000"
    )


def test_progress_parsing_round_trips_and_rejects_foreign_lines():
    line = batch_worker.format_progress_line("case a", "error", 2.5)
    assert batch_worker.parse_progress_line(line) == ("case", "error", 2.5)
    assert batch_worker.parse_progress_line("relax: 12 steps") is None
    assert batch_worker.parse_progress_line("[batch_worker] case=only") is None
    assert (
        batch_worker.parse_progress_line("[batch_worker] case=x status=y z=1") is None
    )
    assert (
        batch_worker.parse_progress_line("[batch_worker] case=x status=y wall_s=?")
        is None
    )


def test_load_jobs_reads_rows_and_rejects_malformed_lists(tmp_path):
    path = _jobs_file(tmp_path, [("alpha", "alpha.yaml")])
    jobs = batch_worker.load_jobs(path)
    assert [(job.case_id, job.config, job.workdir) for job in jobs] == [
        (
            "alpha",
            str(tmp_path / "configs" / "alpha.yaml"),
            str(tmp_path / "cases" / "alpha"),
        )
    ]
    with pytest.raises(ValueError, match="cannot be read"):
        batch_worker.load_jobs(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        batch_worker.load_jobs(broken)
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty JSON array"):
        batch_worker.load_jobs(empty)
    bad_row = tmp_path / "bad-row.json"
    bad_row.write_text(
        json.dumps([{"case_id": "a", "config": "a.yaml"}]), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="'workdir'"):
        batch_worker.load_jobs(bad_row)
    not_a_mapping = tmp_path / "not-a-mapping.json"
    not_a_mapping.write_text(json.dumps(["a.yaml"]), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        batch_worker.load_jobs(not_a_mapping)


def test_main_runs_every_job_and_writes_api_result_documents(
    tmp_path, monkeypatch, capsys, fake_api
):
    monkeypatch.chdir(tmp_path)
    jobs_path = _jobs_file(tmp_path, [("alpha", "alpha.yaml"), ("beta", "beta.yaml")])
    out_dir = tmp_path / "out"

    assert batch_worker.main(["--jobs", str(jobs_path), "--out", str(out_dir)]) == 0

    for case_id in ("alpha", "beta"):
        workdir = (tmp_path / "cases" / case_id).resolve()
        assert workdir.is_dir()
        document = json.loads(
            (out_dir / case_id / batch_worker.RESULT_JSON).read_text(encoding="utf-8")
        )
        assert document["schema"] == "atst-api-result-v1"
        assert document["status"] == "success"
        assert document["workflow"] == "relax"
        assert document["workdir"] == str(workdir)
        assert document["artifact_manifest"] == str(workdir / "atst_artifacts.json")
        assert document["metadata"] == {"engine": "standin"}
    assert [name for name, _ in fake_api] == ["alpha.yaml", "beta.yaml"]
    assert [cwd for _, cwd in fake_api] == [
        (tmp_path / "cases" / "alpha").resolve(),
        (tmp_path / "cases" / "beta").resolve(),
    ]
    assert [status for _, status, _ in _progress_lines(capsys)] == [
        "success",
        "success",
    ]


def test_main_continues_after_a_case_error(tmp_path, monkeypatch, capsys, fake_api):
    monkeypatch.chdir(tmp_path)
    jobs_path = _jobs_file(
        tmp_path, [("bad", "boom.yaml"), ("good", "good.yaml"), ("last", "last.yaml")]
    )
    out_dir = tmp_path / "out"

    assert batch_worker.main(["--jobs", str(jobs_path), "--out", str(out_dir)]) == 0

    lines = _progress_lines(capsys)
    assert [(case_id, status) for case_id, status, _ in lines] == [
        ("bad", "error"),
        ("good", "success"),
        ("last", "success"),
    ]
    error = json.loads(
        (out_dir / "bad" / batch_worker.RESULT_JSON).read_text(encoding="utf-8")
    )
    assert error["schema"] == "atst-api-result-v1"
    assert error["status"] == "error"
    assert error["workflow"] == "relax"
    assert error["error"]["type"] == "ConfigValidationError"
    assert error["error"]["message"] == "bad configuration"
    assert error["error"]["context"] == {"key": "value"}
    assert (out_dir / "good" / batch_worker.RESULT_JSON).is_file()
    assert [name for name, _ in fake_api] == ["boom.yaml", "good.yaml", "last.yaml"]


def test_main_wraps_unexpected_exceptions_in_the_error_document(
    tmp_path, monkeypatch, capsys, fake_api
):
    monkeypatch.chdir(tmp_path)
    jobs_path = _jobs_file(tmp_path, [("crash", "crash.yaml")])
    out_dir = tmp_path / "out"

    assert batch_worker.main(["--jobs", str(jobs_path), "--out", str(out_dir)]) == 0

    document = json.loads(
        (out_dir / "crash" / batch_worker.RESULT_JSON).read_text(encoding="utf-8")
    )
    assert document["status"] == "error"
    assert document["error"]["type"] == "WorkflowExecutionError"
    assert document["error"]["message"] == "ValueError: unexpected stand-in failure"
    assert document["error"]["cause"] == {
        "type": "ValueError",
        "message": "unexpected stand-in failure",
    }
    assert [status for _, status, _ in _progress_lines(capsys)] == ["error"]


def test_main_reports_a_setup_failure_before_any_case(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "out"
    status = batch_worker.main(
        ["--jobs", str(tmp_path / "missing.json"), "--out", str(out_dir)]
    )
    assert status == batch_worker.SETUP_FAILURE_EXIT
    captured = capsys.readouterr()
    assert "setup failure" in captured.err
    assert captured.out == ""
    assert not out_dir.exists()


def test_a_result_document_that_cannot_be_written_is_an_error_case(
    tmp_path, monkeypatch, capsys, fake_api
):
    """A failed handoff must not end the batch either."""
    monkeypatch.chdir(tmp_path)
    jobs_path = _jobs_file(tmp_path, [("alpha", "alpha.yaml"), ("beta", "beta.yaml")])
    out_dir = tmp_path / "out"

    def exploding_write(path, payload):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(batch_worker._runner, "_write_json_atomic", exploding_write)
    assert batch_worker.main(["--jobs", str(jobs_path), "--out", str(out_dir)]) == 0

    captured = capsys.readouterr()
    statuses = [
        parsed[1]
        for parsed in (
            batch_worker.parse_progress_line(line) for line in captured.out.splitlines()
        )
        if parsed is not None
    ]
    assert statuses == ["error", "error"]
    assert "cannot write" in captured.err


def test_run_job_returns_error_for_an_unusable_workdir(tmp_path, fake_api):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    job = batch_worker.Job(
        case_id="alpha", config=str(tmp_path / "alpha.yaml"), workdir=str(blocked)
    )
    assert batch_worker.run_job(job, tmp_path / "out") == batch_worker.STATUS_ERROR
    document = json.loads(
        (tmp_path / "out" / "alpha" / batch_worker.RESULT_JSON).read_text(
            encoding="utf-8"
        )
    )
    assert document["status"] == "error"
