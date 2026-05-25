import json
from pathlib import Path

import pytest


REFERENCE_CASES = {
    "01_neb_Li-Si": {
        "reference_type": "barrier",
        "forward_barrier_eV": 0.618346,
        "main_forward_barrier_eV": 0.618327,
        "barrier_delta_eV": 0.000019,
        "transition_state_index": 2,
        "transition_state_fmax_eV_per_A": 0.048031,
        "transition_state_rmsd_to_main_A": 0.000142,
        "transition_state_structure": "examples/reference_structures/01_neb_Li-Si_ts.extxyz",
    },
    "02_neb_H2-Au": {
        "reference_type": "barrier",
        "forward_barrier_eV": 1.124752,
        "main_forward_barrier_eV": 1.120780,
        "barrier_delta_eV": 0.003972,
        "transition_state_index": 4,
        "transition_state_fmax_eV_per_A": 0.020535,
        "transition_state_rmsd_to_main_A": 0.004172,
        "transition_state_structure": "examples/reference_structures/02_neb_H2-Au_ts.extxyz",
    },
    "03_autoneb_Cy-Pt": {
        "reference_type": "barrier",
        "forward_barrier_eV": 1.330070,
        "main_forward_barrier_eV": 1.327886,
        "barrier_delta_eV": 0.002184,
        "transition_state_index": 5,
        "transition_state_fmax_eV_per_A": 0.041272,
        "transition_state_rmsd_to_main_A": 0.004433,
        "transition_state_structure": "examples/reference_structures/03_autoneb_Cy-Pt_ts.extxyz",
    },
    "04_dimer_CO-Pt": {
        "reference_type": "single_ended_ts",
        "final_energy_eV": -211834.954565,
        "main_final_energy_eV": -211834.952698,
        "energy_delta_eV": -0.001867,
        "transition_state_fmax_eV_per_A": 0.033976,
        "transition_state_rmsd_to_main_A": 0.002209,
        "transition_state_structure": "examples/reference_structures/04_dimer_CO-Pt_final_ts.extxyz",
    },
    "05_sella_H2-Au": {
        "reference_type": "single_ended_ts",
        "final_energy_eV": -239255.122869,
        "main_final_energy_eV": -239255.122160,
        "energy_delta_eV": -0.000709,
        "transition_state_fmax_eV_per_A": 0.048256,
        "transition_state_rmsd_to_main_A": 0.000007,
        "transition_state_structure": "examples/reference_structures/05_sella_H2-Au_final_ts.extxyz",
    },
    "08_d2s_Cy-Pt": {
        "reference_type": "barrier",
        "forward_barrier_eV": 2.678812,
        "main_forward_barrier_eV": 2.678795,
        "barrier_delta_eV": 0.000017,
        "transition_state_index": 6,
        "transition_state_fmax_eV_per_A": 3.531348,
        "transition_state_structure": "examples/reference_structures/08_d2s_Cy-Pt_rough_ts.extxyz",
        "last_rough_barrier_eV": 1.714806,
        "last_rough_barrier_delta_eV": -0.000876,
        "last_rough_ts_index": 6,
        "last_rough_ts_fmax_eV_per_A": 0.874700,
        "sella_final_energy_eV": -11865.557601,
        "sella_final_fmax_eV_per_A": 0.039662,
        "sella_final_structure": "examples/reference_structures/08_d2s_Cy-Pt_sella_final_ts.extxyz",
    },
}


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


@pytest.mark.integration
@pytest.mark.parametrize("case_name, expected", REFERENCE_CASES.items())
def test_reference_results_pin_reproduction_values(case_name, expected):
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "examples" / "reference_results.json").read_text(encoding="utf-8"))
    case = data["cases"][case_name]

    for key, value in expected.items():
        if key.endswith("_structure"):
            assert case[key] == value
            assert (root / value).is_file()
        elif isinstance(value, float):
            assert case[key] == pytest.approx(value, abs=1e-9)
        else:
            assert case[key] == value
