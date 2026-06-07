import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from atst_tools.utils.io import read_structure


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
        "final_energy_eV": -239255.127237,
        "main_final_energy_eV": -239255.122160,
        "energy_delta_eV": -0.005077,
        "transition_state_fmax_eV_per_A": 0.035438,
        "transition_state_rmsd_to_main_A": 0.007952,
        "initial_rmsd_to_reference_A": 0.000101,
        "trajectory_frames": 9,
        "transition_state_structure": "examples/reference_structures/05_sella_H2-Au_final_ts.extxyz",
    },
    "12_ccqn_H2-Au": {
        "reference_type": "single_ended_ts",
        "final_energy_eV": -239255.123188,
        "matched_sella_case": "05_sella_H2-Au",
        "energy_delta_to_sella_eV": 0.004049,
        "transition_state_fmax_eV_per_A": 0.046243,
        "fmax_delta_to_sella_eV_per_A": 0.010805,
        "transition_state_rmsd_to_sella_A": 0.007682,
        "transition_state_rmsd_to_reference_A": 0.000334,
        "initial_rmsd_to_reference_A": 0.000101,
        "trajectory_frames": 14,
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


def test_ccqn_h2_au_reference_matches_sella_result():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "examples" / "reference_results.json").read_text(encoding="utf-8"))

    ccqn = data["cases"]["12_ccqn_H2-Au"]
    sella = data["cases"]["05_sella_H2-Au"]

    assert ccqn["matched_sella_case"] == "05_sella_H2-Au"
    assert ccqn["energy_delta_to_sella_eV"] == pytest.approx(
        abs(ccqn["final_energy_eV"] - sella["final_energy_eV"]),
        abs=1e-6,
    )
    assert ccqn["energy_delta_to_sella_eV"] <= 0.01
    assert ccqn["transition_state_rmsd_to_sella_A"] <= 0.02
    assert sella["transition_state_fmax_eV_per_A"] <= 0.05
    assert ccqn["transition_state_fmax_eV_per_A"] <= 0.05
    assert sella["trajectory_frames"] >= 3
    assert ccqn["trajectory_frames"] >= 3
    assert ccqn["transition_state_structure"] == sella["transition_state_structure"]


def test_h2_au_sella_and_ccqn_examples_use_perturbed_inputs():
    root = Path(__file__).resolve().parents[2]
    reference = read_structure(root / "examples" / "reference_structures" / "05_sella_H2-Au_final_ts.extxyz")
    sella_input = read_structure(root / "examples" / "05_sella_H2-Au" / "inputs" / "sella_init.stru")
    ccqn_input = read_structure(root / "examples" / "12_ccqn_H2-Au" / "inputs" / "ccqn_init.stru")
    config = yaml.safe_load((root / "examples" / "12_ccqn_H2-Au" / "config.yaml").read_text(encoding="utf-8"))
    smoke_config = yaml.safe_load(
        (root / "examples" / "12_ccqn_H2-Au" / "config_smoke.yaml").read_text(encoding="utf-8")
    )

    def rmsd(atoms_a, atoms_b):
        delta = atoms_a.get_positions() - atoms_b.get_positions()
        return float(np.sqrt((delta * delta).mean()))

    assert rmsd(sella_input, reference) > 5e-5
    assert rmsd(sella_input, reference) < 0.005
    assert rmsd(ccqn_input, reference) == pytest.approx(rmsd(sella_input, reference), abs=1e-9)
    assert rmsd(ccqn_input, sella_input) == pytest.approx(0.0, abs=1e-12)

    for loaded_config in (config, smoke_config):
        calculation = loaded_config["calculation"]
        assert calculation["init_structure"] == "inputs/ccqn_init.stru"
        assert calculation["accept_initial_converged"] is False


def test_new_p0_p1_examples_exercise_new_yaml_interfaces():
    root = Path(__file__).resolve().parents[2]

    def load_example(relative_path):
        return yaml.safe_load((root / "examples" / relative_path).read_text(encoding="utf-8"))

    neb_01 = load_example("01_neb_Li-Si/config.yaml")["calculation"]
    neb_01_dp = load_example("01_neb_Li-Si/config_dp.yaml")["calculation"]
    neb_02_main = load_example("02_neb_H2-Au/config.yaml")["calculation"]
    neb_02_dp = load_example("02_neb_H2-Au/config_dp.yaml")["calculation"]
    neb_13 = load_example("13_neb_parallel_Cy-Pt/config.yaml")["calculation"]
    for calculation in (neb_01, neb_01_dp, neb_02_main, neb_02_dp, neb_13):
        assert calculation["two_stage"] is True
        assert calculation["stage1_steps"] == 20
        assert calculation["stage1_fmax"] == pytest.approx(0.20)

    neb = load_example("02_neb_H2-Au/config_two_stage.yaml")["calculation"]
    neb_dp = load_example("02_neb_H2-Au/config_two_stage_dp.yaml")["calculation"]
    assert neb["type"] == "neb"
    assert neb["two_stage"] is True
    assert neb["stage1_steps"] == 1
    assert neb["stage1_fmax"] == pytest.approx(0.10)
    assert neb_dp["two_stage"] is True
    assert neb_dp["stage1_steps"] == 3

    irc = load_example("10_irc_H2/config_descent.yaml")["calculation"]
    irc_dp = load_example("10_irc_H2/config_descent_dp.yaml")["calculation"]
    assert irc["type"] == "irc"
    assert irc["backend"] == "descent"
    assert irc["mode_vector"] == "inputs/descent_mode.npy"
    assert irc_dp["backend"] == "descent"

    ccqn = load_example("12_ccqn_H2-Au/config_auto_modes.yaml")["calculation"]
    ccqn_dp = load_example("12_ccqn_H2-Au/config_auto_modes_dp.yaml")["calculation"]
    for calculation in (ccqn, ccqn_dp):
        assert calculation["type"] == "ccqn"
        assert calculation["e_vector_method"] == "ic"
        assert "reactive_bonds" not in calculation
        assert calculation["auto_reactive_bonds"]["enabled"] is True
        assert calculation["auto_reactive_bonds"]["molecule_indices"] == "1-2"
        assert calculation["mode_manifest"].endswith("mode_manifest.json")


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
