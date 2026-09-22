"""Tests for the benchmark record builder (P5 self-describing evidence)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from atst_tools.bench import record


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_record_captures_provenance_inputs_results_and_operator_slots(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": [{"case_id": "a", "config": "a.yaml"}]})
    fixture = tmp_path / "model.pt"
    fixture.write_bytes(b"weights")
    sweep_dir = tmp_path / "sweep"
    _write_json(
        sweep_dir / "sweep_summary.json",
        {
            "schema": "atst-bench-sweep-v1",
            "repeats": 3,
            "slots_variants": [1, 2],
            "variants": {
                "1": {
                    "makespan_s": {"median": 10.0},
                    "succeeded": {"total": 2},
                    "cases_total": {"total": 2},
                },
                "2": {
                    "makespan_s": {"median": 7.0},
                    "succeeded": {"total": 2},
                    "cases_total": {"total": 2},
                },
            },
        },
    )
    single_dir = tmp_path / "single"
    _write_json(
        single_dir / "batch_summary.json",
        {
            "schema": "atst-bench-harness-v1",
            "cases_total": 2,
            "succeeded": 2,
            "failed": 0,
            "wall_s": 11.5,
        },
    )

    payload = record.build_record(
        manifest=manifest,
        run_dirs=[sweep_dir, single_dir, tmp_path / "missing"],
        fixtures=[fixture],
        operator={"job_id": "123456", "partition": "4V100"},
        notes=["local smoke"],
    )

    assert payload["schema"] == record.RECORD_SCHEMA
    record_time = payload["atst"]["record_time"]
    assert len(record_time["head"]) == 40
    assert record_time["dirty"] in (True, False)
    assert payload["atst"]["run_time"] == []
    assert payload["atst"]["run_time_consistent"] is None
    assert payload["environment"]["interpreter"]
    assert "atst_tools_version" in payload["environment"]
    assert set(payload["environment"]["packages"]) >= {"numpy", "ase"}
    assert payload["host"]["cpu_count"] >= 1
    assert (
        payload["inputs"]["manifest"]["sha256"]
        == hashlib.sha256(manifest.read_bytes()).hexdigest()
    )
    assert (
        payload["inputs"]["fixtures"][0]["sha256"]
        == hashlib.sha256(b"weights").hexdigest()
    )

    runs = payload["results"]
    assert runs[0]["schema"] == "atst-bench-sweep-v1"
    assert runs[0]["variants"]["2"]["makespan_s_median"] == 7.0
    assert runs[0]["tree"]["file_count"] == 1
    assert len(runs[0]["tree"]["tree_sha256"]) == 64
    assert runs[1]["schema"] == "atst-bench-harness-v1"
    assert runs[1]["succeeded"] == 2
    assert runs[2]["exists"] is False
    assert any("run directory is missing" in item for item in payload["warnings"])

    operator = payload["operator"]
    assert operator["job_id"] == "123456"
    assert operator["partition"] == "4V100"
    for missing in ("qos", "allocated_gpu_hours", "sacct_excerpt", "approved_by"):
        assert missing in operator and operator[missing] is None
    assert payload["notes"] == ["local smoke"]


def test_record_writes_atomically_and_round_trips(tmp_path: Path) -> None:
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    payload = record.build_record(manifest=manifest)
    out = record.write_record(payload, tmp_path / "nested" / "record.json")
    assert out.is_file()
    assert not (tmp_path / "nested" / ".record.json.tmp").exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["schema"] == record.RECORD_SCHEMA
    assert written["results"] == []


def test_record_copies_run_time_revisions_and_flags_mismatch(tmp_path: Path) -> None:
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    head = "a" * 40
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "batch_summary.json",
        {
            "schema": "atst-bench-harness-v1",
            "cases_total": 1,
            "succeeded": 1,
            "failed": 0,
            "wall_s": 1.0,
            "revision": {"head": head, "branch": "feature/x", "dirty": False},
        },
    )
    payload = record.build_record(manifest=manifest, run_dirs=[run_dir])
    assert payload["atst"]["run_time"][0]["revision"]["head"] == head
    assert payload["atst"]["run_time_consistent"] is True
    assert payload["results"][0]["revision"]["head"] == head
    assert payload["warnings"] == []


def test_record_summarizes_a_new_tree_from_batch_summary_json(tmp_path: Path) -> None:
    """A run staged after the rename is summarized from ``batch_summary.json``."""
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "batch_summary.json",
        {
            "schema": "atst-bench-harness-v1",
            "cases_total": 3,
            "succeeded": 2,
            "failed": 1,
            "wall_s": 4.5,
        },
    )
    payload = record.build_record(manifest=manifest, run_dirs=[run_dir])
    run = payload["results"][0]
    assert Path(run["summary"]).name == "batch_summary.json"
    assert run["schema"] == "atst-bench-harness-v1"
    assert run["cases_total"] == 3
    assert run["succeeded"] == 2
    assert run["failed"] == 1
    assert run["wall_s"] == 4.5
    assert run["tree"]["file_count"] == 1
    assert payload["warnings"] == []


def test_record_still_reads_a_legacy_harness_summary_json(tmp_path: Path) -> None:
    """A tree that only carries the legacy summary keeps summarizing.

    The archived evidence under ``docs/reports/data/**`` was staged before the
    ``harness`` -> ``batch_runner`` rename, so a record built over those trees
    must not report them as empty run directories.
    """
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    head = "b" * 40
    run_dir = tmp_path / "legacy-run"
    _write_json(
        run_dir / "harness_summary.json",
        {
            "schema": "atst-bench-harness-v1",
            "cases_total": 2,
            "succeeded": 1,
            "failed": 1,
            "wall_s": 9.0,
            "revision": {"head": head, "branch": "feature/x", "dirty": False},
        },
    )
    payload = record.build_record(manifest=manifest, run_dirs=[run_dir])
    run = payload["results"][0]
    assert Path(run["summary"]).name == "harness_summary.json"
    assert run["schema"] == "atst-bench-harness-v1"
    assert run["cases_total"] == 2
    assert run["succeeded"] == 1
    assert run["revision"]["head"] == head
    assert payload["atst"]["run_time"][0]["revision"]["head"] == head
    assert payload["warnings"] == []


def test_record_prefers_the_current_summary_over_a_legacy_copy(
    tmp_path: Path,
) -> None:
    """A directory holding both documents reports the current one."""
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    run_dir = tmp_path / "rerun"
    legacy = {
        "schema": "atst-bench-harness-v1",
        "cases_total": 1,
        "succeeded": 0,
        "failed": 1,
        "wall_s": 30.0,
    }
    current = dict(legacy, cases_total=4, succeeded=4, failed=0, wall_s=12.0)
    _write_json(run_dir / "harness_summary.json", legacy)
    _write_json(run_dir / "batch_summary.json", current)
    payload = record.build_record(manifest=manifest, run_dirs=[run_dir])
    run = payload["results"][0]
    assert Path(run["summary"]).name == "batch_summary.json"
    assert run["cases_total"] == 4
    assert run["succeeded"] == 4
    assert run["wall_s"] == 12.0
    assert run["tree"]["file_count"] == 2


def test_record_reports_gpu_inventory_failure_instead_of_guessing(monkeypatch):
    """A missing nvidia-smi is recorded as an explicit error, not as 'no GPU'."""

    def missing(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(record.subprocess, "run", missing)
    facts = record._host_facts()
    assert facts["gpu_inventory"] == []
    assert "could not be executed" in facts["gpu_inventory_error"]

    def failing(*args, **kwargs):
        return type("Result", (), {"returncode": 9, "stdout": ""})()

    monkeypatch.setattr(record.subprocess, "run", failing)
    facts = record._host_facts()
    assert facts["gpu_inventory"] == []
    assert "status 9" in facts["gpu_inventory_error"]


def test_record_keeps_the_unlabeled_fixture_entry_shape(tmp_path: Path) -> None:
    """``--fixture`` keeps its exact pre-label entry shape and warning wording."""
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    fixture = tmp_path / "model.pt"
    fixture.write_bytes(b"weights")
    missing = tmp_path / "absent.pt"
    out = tmp_path / "record.json"

    assert (
        record.main(
            [
                "--manifest",
                str(manifest),
                "--out",
                str(out),
                "--fixture",
                str(fixture),
                "--fixture",
                str(missing),
            ]
        )
        == 1
    )

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["inputs"]["fixtures"] == [
        {
            "path": str(fixture.resolve()),
            "exists": True,
            "sha256": hashlib.sha256(b"weights").hexdigest(),
        },
        {"path": str(missing.resolve()), "exists": False, "sha256": None},
    ]
    assert f"fixture is missing: {missing}" in written["warnings"]


def test_record_labels_fixtures_per_channel_in_cli_order(tmp_path: Path) -> None:
    """Labels name the benchmark channel and never disturb the given order."""
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    model = tmp_path / "model.ckpt.pt"
    model.write_bytes(b"weights")
    abacus_inputs = tmp_path / "abacus_input"
    abacus_inputs.mkdir()
    (abacus_inputs / "INPUT").write_text("ks_solver cusolver\n", encoding="utf-8")
    out = tmp_path / "record.json"

    assert (
        record.main(
            [
                "--manifest",
                str(manifest),
                "--out",
                str(out),
                "--fixture-labeled",
                f"dp_model={model}",
                "--fixture",
                str(model),
                "--fixture-labeled",
                f"abacus_inputs={abacus_inputs}",
            ]
        )
        == 0
    )

    entries = json.loads(out.read_text(encoding="utf-8"))["inputs"]["fixtures"]
    assert [entry.get("label") for entry in entries] == [
        "dp_model",
        None,
        "abacus_inputs",
    ]
    assert entries[0] == {
        "path": str(model.resolve()),
        "exists": True,
        "sha256": hashlib.sha256(b"weights").hexdigest(),
        "label": "dp_model",
    }
    assert entries[2]["exists"] is True
    assert entries[2]["file_count"] == 1


def test_record_hashes_a_directory_fixture_as_a_tree(tmp_path: Path) -> None:
    """A directory fixture records its file count and content digest."""
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    inputs_dir = tmp_path / "abacus_input"
    inputs_dir.mkdir()
    (inputs_dir / "INPUT").write_text("ks_solver cusolver\n", encoding="utf-8")
    nested = inputs_dir / "STRU"
    nested.write_text("ATOMIC_SPECIES\n", encoding="utf-8")

    payload = record.build_record(
        manifest=manifest,
        fixtures=[record.FixtureSpec(path=inputs_dir, label="abacus_inputs")],
    )
    entry = payload["inputs"]["fixtures"][0]
    assert entry["path"] == str(inputs_dir.resolve())
    assert entry["exists"] is True
    assert entry["sha256"] is None
    assert entry["label"] == "abacus_inputs"
    assert entry["file_count"] == 2
    assert entry["tree_sha256"] == record._tree_digest(inputs_dir)["tree_sha256"]
    assert len(entry["tree_sha256"]) == 64
    assert payload["warnings"] == []

    # The digest is content-addressed: touching the tree must change it.
    nested.write_text("ATOMIC_SPECIES\nLATTICE_CONSTANT 10.0\n", encoding="utf-8")
    retouched = record.build_record(
        manifest=manifest,
        fixtures=[record.FixtureSpec(path=inputs_dir, label="abacus_inputs")],
    )["inputs"]["fixtures"][0]
    assert retouched["file_count"] == 2
    assert retouched["tree_sha256"] != entry["tree_sha256"]


def test_record_warns_for_missing_fixtures_of_both_forms(tmp_path: Path) -> None:
    """A missing labeled path warns exactly like a missing ``--fixture``."""
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    missing_file = tmp_path / "absent.pt"
    missing_dir = tmp_path / "absent_input"
    out = tmp_path / "record.json"

    assert (
        record.main(
            [
                "--manifest",
                str(manifest),
                "--out",
                str(out),
                "--fixture-labeled",
                f"dp_model={missing_file}",
                "--fixture-labeled",
                f"abacus_inputs={missing_dir}",
            ]
        )
        == 1
    )

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["warnings"] == [
        f"fixture is missing: {missing_file}",
        f"fixture is missing: {missing_dir}",
    ]
    for entry in written["inputs"]["fixtures"]:
        assert entry["exists"] is False
        assert entry["sha256"] is None
        assert "file_count" not in entry and "tree_sha256" not in entry


def test_record_rejects_a_labeled_fixture_without_a_label(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--fixture-labeled`` refuses an unusable ``LABEL=PATH`` instead of guessing."""
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    base = [
        "--manifest",
        str(manifest),
        "--out",
        str(tmp_path / "record.json"),
        "--fixture-labeled",
    ]
    for malformed in ("dp_model", "=model.pt", "dp_model="):
        with pytest.raises(SystemExit) as excinfo:
            record.main([*base, malformed])
        assert excinfo.value.code == 2
        assert "expects LABEL=PATH" in capsys.readouterr().err

    # Only the first '=' separates the label, so paths may contain '='.
    odd = tmp_path / "model=tuned.pt"
    odd.write_bytes(b"weights")
    assert record.main([*base, f"dp_model={odd}"]) == 0
    entry = json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))
    entry = entry["inputs"]["fixtures"][0]
    assert entry["label"] == "dp_model"
    assert entry["path"] == str(odd.resolve())
