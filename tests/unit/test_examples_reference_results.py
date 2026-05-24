import json
from pathlib import Path


def test_reference_results_cover_current_examples():
    root = Path(__file__).resolve().parents[2]
    examples_dir = root / "examples"
    reference_file = examples_dir / "reference_results.json"

    data = json.loads(reference_file.read_text(encoding="utf-8"))
    expected = {
        path.name
        for path in examples_dir.iterdir()
        if path.is_dir() and path.name[:2].isdigit()
    }

    assert set(data["cases"]) == expected


def test_reference_results_record_ts_artifacts_for_barrier_cases():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "examples" / "reference_results.json").read_text(encoding="utf-8"))

    for case_name in ("01_neb_Li-Si", "02_neb_H2-Au", "03_autoneb_Cy-Pt", "08_d2s_Cy-Pt"):
        case = data["cases"][case_name]
        assert case["reference_type"] == "barrier"
        assert case["transition_state_index"] is not None
        assert case["forward_barrier_eV"] > 0
        assert (root / case["transition_state_structure"]).is_file()
