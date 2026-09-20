"""Tests for the benchmark record builder (P5 self-describing evidence)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
                "1": {"makespan_s": {"median": 10.0}, "succeeded": {"total": 2}, "cases_total": {"total": 2}},
                "2": {"makespan_s": {"median": 7.0}, "succeeded": {"total": 2}, "cases_total": {"total": 2}},
            },
        },
    )
    harness_dir = tmp_path / "single"
    _write_json(
        harness_dir / "harness_summary.json",
        {"schema": "atst-bench-harness-v1", "cases_total": 2, "succeeded": 2, "failed": 0, "wall_s": 11.5},
    )

    payload = record.build_record(
        manifest=manifest,
        run_dirs=[sweep_dir, harness_dir, tmp_path / "missing"],
        fixtures=[fixture],
        repo_root=Path(__file__).resolve().parents[2],
        operator={"job_id": "123456", "partition": "4V100"},
        notes=["local smoke"],
    )

    assert payload["schema"] == record.RECORD_SCHEMA
    assert len(payload["atst"]["head"]) == 40
    assert payload["atst"]["dirty"] in (True, False)
    assert payload["environment"]["interpreter"]
    assert "atst_tools_version" in payload["environment"]
    assert set(payload["environment"]["packages"]) >= {"numpy", "ase"}
    assert payload["host"]["cpu_count"] >= 1
    assert payload["inputs"]["manifest"]["sha256"] == hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()
    assert payload["inputs"]["fixtures"][0]["sha256"] == hashlib.sha256(b"weights").hexdigest()

    runs = payload["results"]
    assert runs[0]["schema"] == "atst-bench-sweep-v1"
    assert runs[0]["variants"]["2"]["makespan_s_median"] == 7.0
    assert runs[1]["schema"] == "atst-bench-harness-v1"
    assert runs[1]["succeeded"] == 2
    assert runs[2]["summary"] is None

    operator = payload["operator"]
    assert operator["job_id"] == "123456"
    assert operator["partition"] == "4V100"
    for missing in ("qos", "allocated_gpu_hours", "sacct_excerpt", "approved_by"):
        assert missing in operator and operator[missing] is None
    assert payload["notes"] == ["local smoke"]


def test_record_writes_atomically_and_round_trips(tmp_path: Path) -> None:
    manifest = tmp_path / "cases.json"
    _write_json(manifest, {"cases": []})
    payload = record.build_record(
        manifest=manifest,
        repo_root=Path(__file__).resolve().parents[2],
    )
    out = record.write_record(payload, tmp_path / "nested" / "record.json")
    assert out.is_file()
    assert not (tmp_path / "nested" / ".record.json.tmp").exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["schema"] == record.RECORD_SCHEMA
    assert written["results"] == []
