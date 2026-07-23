from pathlib import Path
import json

from ruamel.yaml import YAML
from ase.io import read

from atst_tools.utils.config import ConfigLoader


def test_all_example_configs_parse_and_validate():
    yaml = YAML(typ="safe")
    example_configs = sorted(Path("examples").glob("*/config*.yaml"))

    assert example_configs
    for config_file in example_configs:
        with config_file.open(encoding="utf-8") as handle:
            config = yaml.load(handle)
        assert ConfigLoader.validate(config) is True, config_file
        normalized = ConfigLoader.normalize(config)
        assert "config_version" not in normalized, config_file


def test_abacus_examples_use_sai_gpu_solver():
    yaml = YAML(typ="safe")

    for config_file in sorted(Path("examples").glob("*/config.yaml")):
        with config_file.open(encoding="utf-8") as handle:
            config = yaml.load(handle)
        assert config["calculator"]["name"] == "abacus"
        assert config["calculator"]["abacus"]["parameters"]["ks_solver"] == "cusolver"


def test_example_input_paths_exist():
    yaml = YAML(typ="safe")
    input_fields = {
        "init_chain",
        "init_structure",
        "init_file",
        "final_file",
        "displacement_vector",
        "mode_vector",
    }

    for config_file in sorted(Path("examples").glob("*/config*.yaml")):
        with config_file.open(encoding="utf-8") as handle:
            config = yaml.load(handle)

        calculation = config["calculation"]
        for field in input_fields & calculation.keys():
            value = calculation[field]
            if isinstance(value, str):
                assert (config_file.parent / value).exists(), f"{config_file}: {field}={value}"
        make = calculation.get("make") or {}
        for field in input_fields & make.keys():
            value = make[field]
            if isinstance(value, str):
                assert (config_file.parent / value).exists(), f"{config_file}: calculation.make.{field}={value}"


def test_md_example_uses_01_neb_li_si_initial_structure():
    yaml = YAML(typ="safe")
    md_dir = Path("examples/15_md_Li-Si")
    source = Path("examples/01_neb_Li-Si/inputs/init_neb_chain.traj")

    assert md_dir.is_dir()
    assert not Path("examples/15_md_H2").exists()

    reference = read(source, index=0)
    md_initial = read(md_dir / "inputs" / "init.traj")
    assert md_initial.get_chemical_formula() == reference.get_chemical_formula()
    assert len(md_initial) == len(reference)
    assert md_initial.cell.cellpar().tolist() == reference.cell.cellpar().tolist()
    assert md_initial.positions.tolist() == reference.positions.tolist()

    configs = {
        "config_ase_dp.yaml": ("ase", "dp"),
        "config_ase_abacus.yaml": ("ase", "abacus"),
        "config_abacus_native.yaml": ("abacus_native", "abacus"),
    }
    for filename, (driver, calculator) in configs.items():
        config = yaml.load(md_dir / filename)
        assert config["calculation"]["type"] == "md"
        assert config["calculation"]["driver"] == driver
        assert config["calculation"]["init_structure"] == "inputs/init.traj"
        assert config["calculator"]["name"] == calculator
        assert ConfigLoader.validate(config) is True


def test_cy_pt_parallel_neb_nested_mpi_example_is_sai_sized():
    yaml = YAML(typ="safe")
    config_file = Path("examples/13_neb_parallel_Cy-Pt/config.yaml")
    config = yaml.load(config_file)

    calculation = config["calculation"]
    abacus = config["calculator"]["abacus"]
    command = abacus["command"]

    assert calculation["type"] == "neb"
    assert calculation["parallel"] is True
    assert calculation["init_chain"] == "inputs/cy_pt_neb_5_images.traj"
    assert calculation["two_stage"] is True
    assert calculation["stage1_steps"] == 20
    assert calculation["stage1_fmax"] == 0.20
    assert calculation["fmax"] == 0.12
    assert abacus["mpi"] == 4
    assert abacus["omp"] == 8
    assert abacus["version_command"] == "abacus --version"
    assert "mpirun -np {mpi}" in command
    assert "--host localhost:{mpi}" in command
    assert "-mca ras ^slurm" in command
    assert "-mca plm isolated" in command
    assert "OMPI_COMM_WORLD_SIZE" in command
    assert ConfigLoader.validate(config) is True


def test_cy_pt_parallel_autoneb_single_gpu_example_is_sai_sized():
    yaml = YAML(typ="safe")
    config_file = Path("examples/14_autoneb_parallel_Cy-Pt/config.yaml")
    config = yaml.load(config_file)

    calculation = config["calculation"]
    abacus = config["calculator"]["abacus"]

    assert calculation["type"] == "autoneb"
    assert calculation["parallel"] is True
    assert calculation["n_simul"] == 4
    assert calculation["init_chain"] == "inputs/cy_pt_endpoints.traj"
    assert calculation["fmax"] == [0.20, 0.20]
    assert abacus["command"] == "abacus"
    assert abacus["mpi"] == 1
    assert abacus["omp"] == 8
    assert ConfigLoader.validate(config) is True


def test_cy_pt_parallel_sbatch_examples_encode_sai_launchers():
    neb_script = Path("examples/13_neb_parallel_Cy-Pt/submit_huge_gpu.sbatch")
    autoneb_script = Path("examples/14_autoneb_parallel_Cy-Pt/submit_rush_gpu.sbatch")

    neb = neb_script.read_text(encoding="utf-8")
    autoneb = autoneb_script.read_text(encoding="utf-8")

    assert "#SBATCH --qos=huge-gpu" in neb
    assert "#SBATCH --partition=8V100V0" in neb
    assert "#SBATCH --nodes=5" in neb
    assert "#SBATCH --ntasks=20" in neb
    assert "#SBATCH --gpus-per-node=4" in neb
    assert "mpirun -np 5 --map-by ppr:1:node atst run config.yaml" in neb

    assert "#SBATCH --qos=rush-gpu" in autoneb
    assert "#SBATCH --partition=4V100" in autoneb
    assert "#SBATCH --nodes=1" in autoneb
    assert "#SBATCH --ntasks=4" in autoneb
    assert "#SBATCH --gpus-per-node=4" in autoneb
    assert "mpirun -np 4 --map-by $MAP_OPT atst run config.yaml" in autoneb


def test_p0_p1_examples_include_curated_validation_outputs():
    neb_dir = Path("examples/02_neb_H2-Au/outputs")
    irc_dir = Path("examples/10_irc_H2/outputs")
    ccqn_dir = Path("examples/12_ccqn_H2-Au/outputs")

    for path in (
        neb_dir / "README.md",
        neb_dir / "neb_two_stage_abacus_smoke.traj",
        neb_dir / "neb_two_stage_dp.traj",
        neb_dir / "slurm-atst_neb2stage-461313.out",
        irc_dir / "README.md",
        irc_dir / "irc_descent.traj",
        irc_dir / "norm_irc_descent.traj",
        irc_dir / "irc_descent_dp.traj",
        irc_dir / "norm_irc_descent_dp.traj",
        irc_dir / "slurm-atst_ircdesc-461256.out",
        ccqn_dir / "README.md",
        ccqn_dir / "ccqn_auto_modes.traj",
        ccqn_dir / "ccqn_auto_modes_dp.traj",
        ccqn_dir / "ccqn_auto_modes_mode_manifest.json",
        ccqn_dir / "ccqn_auto_modes_dp_mode_manifest.json",
        ccqn_dir / "slurm-atst_ccqnauto-461254.out",
    ):
        assert path.exists(), path

    neb_manifest = json.loads((neb_dir / "atst_artifacts_two_stage_abacus_smoke.json").read_text(encoding="utf-8"))
    irc_manifest = json.loads((irc_dir / "atst_artifacts_descent.json").read_text(encoding="utf-8"))
    mode_manifest = json.loads((ccqn_dir / "ccqn_auto_modes_mode_manifest.json").read_text(encoding="utf-8"))

    assert neb_manifest["workflow"] == "neb"
    assert irc_manifest["workflow"] == "irc"
    assert mode_manifest["selected_mode"]["reactive_bonds_1based"] == [[2, 61]]


def test_ccqn_api_example_has_a_lightweight_verification_record():
    reference = json.loads(Path("examples/reference_results.json").read_text(encoding="utf-8"))
    api_example = reference["cases"]["12_ccqn_H2-Au"]["api_example"]

    assert api_example["path"] == "examples/12_ccqn_H2-Au/ccqn_api_auto_modes.py"
    assert api_example["calculator"] == "ase.calculators.emt.EMT"
    assert api_example["validation_status"].startswith("structurally executable")


def test_cy_pt_parallel_examples_include_completed_validation_outputs():
    reference = json.loads(Path("examples/reference_results.json").read_text(encoding="utf-8"))
    neb_reference = reference["cases"]["13_neb_parallel_Cy-Pt"]
    autoneb_reference = reference["cases"]["14_autoneb_parallel_Cy-Pt"]

    neb_dir = Path("examples/13_neb_parallel_Cy-Pt/outputs")
    autoneb_dir = Path("examples/14_autoneb_parallel_Cy-Pt/outputs")

    neb_summary_path = neb_dir / "summary_13_neb_parallel_8v100_fmax012.json"
    autoneb_summary_path = autoneb_dir / "summary_14_autoneb_parallel.json"

    assert (neb_dir / "README.md").exists()
    assert (neb_dir / "neb_parallel_nested_mpi.traj").exists()
    assert (neb_dir / "slurm-461967.out").exists()
    assert neb_summary_path.exists()

    assert (autoneb_dir / "README.md").exists()
    assert (autoneb_dir / "slurm-462244.out").exists()
    assert autoneb_summary_path.exists()
    assert len(sorted(autoneb_dir.glob("run_autoneb_parallel_single_gpu*.traj"))) == 10

    neb_summary = json.loads(neb_summary_path.read_text(encoding="utf-8"))
    autoneb_summary = json.loads(autoneb_summary_path.read_text(encoding="utf-8"))

    assert neb_summary["status"]["complete"] is True
    assert round(neb_summary["latest"]["barrier_eV"], 6) == neb_reference["forward_barrier_eV"]
    assert neb_summary["latest"]["ts_image"] == neb_reference["transition_state_index"]
    assert round(neb_summary["latest"]["projected_neb_fmax_eV_per_A"], 6) == neb_reference["projected_neb_fmax_eV_per_A"]

    assert autoneb_summary["status"]["complete"] is True
    assert round(autoneb_summary["latest"]["barrier_eV"], 6) == autoneb_reference["forward_barrier_eV"]
    assert autoneb_summary["latest"]["ts_image"] == autoneb_reference["transition_state_index"]
    assert round(autoneb_summary["latest"]["projected_neb_fmax_eV_per_A"], 6) == autoneb_reference["projected_neb_fmax_eV_per_A"]


def test_base_cy_pt_autoneb_example_keeps_parallel_cases_split_out():
    case_dir = Path("examples/03_autoneb_Cy-Pt")

    assert not (case_dir / "config_parallel_neb_nested_mpi.yaml").exists()
    assert not (case_dir / "config_parallel_autoneb_single_gpu.yaml").exists()
    assert not (case_dir / "submit_neb_parallel_huge_gpu.sbatch").exists()
    assert not (case_dir / "submit_autoneb_parallel_rush_gpu.sbatch").exists()
    assert not (case_dir / "inputs" / "cy_pt_initial.traj").exists()
    assert not (case_dir / "inputs" / "cy_pt_final.traj").exists()
    assert not (case_dir / "inputs" / "cy_pt_endpoints.traj").exists()
