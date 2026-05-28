import json
import math
from pathlib import Path


EXPECTED_MODEL_SHA256 = "86dd3a804d78ca5d203ebf98747e8f16dff9713ba8950097ceb760b161e19907"


def _walk_floats(value):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_floats(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_floats(nested)
    elif isinstance(value, float):
        yield value


def _walk_structure_paths(case):
    if "structure" in case:
        yield case["structure"]["path"]
    if "structures" in case:
        for structure in case["structures"].values():
            yield structure["path"]


def test_dp_reference_results_cover_dp_examples():
    root = Path(__file__).resolve().parents[2]
    examples_dir = root / "examples"
    data = json.loads((examples_dir / "dp_reference_results.json").read_text(encoding="utf-8"))

    expected = {
        path.name
        for path in examples_dir.iterdir()
        if path.is_dir() and (path / "config_dp.yaml").is_file()
    }

    assert set(data["cases"]) == expected


def test_dp_reference_results_pin_model_and_artifacts():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "examples" / "dp_reference_results.json").read_text(encoding="utf-8"))

    assert data["validation_run"]["model_path"] == "temp_repos/dp_model/DPA-3.1-3M.pt"
    assert data["validation_run"]["model_sha256"] == EXPECTED_MODEL_SHA256
    assert data["model_recommendation"]["decision"] == "keep_as_external_validation_asset"

    for case in data["cases"].values():
        assert case["status"] in {"green", "yellow"}
        assert all(math.isfinite(value) for value in _walk_floats(case))
        for path in _walk_structure_paths(case):
            assert (root / "examples" / path).is_file()


def test_dp_reference_barrier_cases_have_abacus_comparisons():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "examples" / "dp_reference_results.json").read_text(encoding="utf-8"))

    for case_name in ("01_neb_Li-Si", "02_neb_H2-Au", "03_autoneb_Cy-Pt"):
        case = data["cases"][case_name]
        assert case["metrics"]["barrier_eV"] > 0
        assert case["comparison"]["abacus_barrier_eV"] > 0
        assert abs(case["comparison"]["delta_vs_abacus_eV"]) < 0.5
        assert case["comparison"]["ts_rmsd_to_abacus_ang"] < 0.2

    d2s = data["cases"]["08_d2s_Cy-Pt"]
    assert d2s["metrics"]["complete"] is True
    assert d2s["comparison"]["abacus_rough_barrier_eV"] > 0
    assert abs(d2s["comparison"]["rough_delta_vs_abacus_eV"]) < 1.0
