from pathlib import Path

from ruamel.yaml import YAML

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
        assert "config_version" in normalized, config_file


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


def test_cy_pt_parallel_neb_nested_mpi_example_is_sai_sized():
    yaml = YAML(typ="safe")
    config_file = Path("examples/13_neb_parallel_Cy-Pt/config.yaml")
    config = yaml.load(config_file)

    calculation = config["calculation"]
    abacus = config["calculator"]["abacus"]
    command = abacus["command"]

    assert calculation["type"] == "neb"
    assert calculation["parallel"] is True
    assert calculation["make"]["n_images"] == 5
    assert calculation["make"]["init_structure"] == "inputs/cy_pt_initial.traj"
    assert calculation["make"]["final_structure"] == "inputs/cy_pt_final.traj"
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
    assert "#SBATCH --nodes=5" in neb
    assert "#SBATCH --ntasks=20" in neb
    assert "#SBATCH --gpus-per-node=4" in neb
    assert "mpirun -np 5 --map-by ppr:1:node atst run config.yaml" in neb

    assert "#SBATCH --qos=rush-gpu" in autoneb
    assert "#SBATCH --nodes=1" in autoneb
    assert "#SBATCH --ntasks=4" in autoneb
    assert "#SBATCH --gpus-per-node=4" in autoneb
    assert "mpirun -np 4 --map-by $MAP_OPT atst run config.yaml" in autoneb


def test_base_cy_pt_autoneb_example_keeps_parallel_cases_split_out():
    case_dir = Path("examples/03_autoneb_Cy-Pt")

    assert not (case_dir / "config_parallel_neb_nested_mpi.yaml").exists()
    assert not (case_dir / "config_parallel_autoneb_single_gpu.yaml").exists()
    assert not (case_dir / "submit_neb_parallel_huge_gpu.sbatch").exists()
    assert not (case_dir / "submit_autoneb_parallel_rush_gpu.sbatch").exists()
    assert not (case_dir / "inputs" / "cy_pt_initial.traj").exists()
    assert not (case_dir / "inputs" / "cy_pt_final.traj").exists()
    assert not (case_dir / "inputs" / "cy_pt_endpoints.traj").exists()
