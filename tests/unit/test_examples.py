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
