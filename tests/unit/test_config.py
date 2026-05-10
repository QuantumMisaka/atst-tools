from pathlib import Path

import pytest

from atst_tools.utils.config import ConfigLoader


def test_load_reads_yaml(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
calculation:
  type: relax
  init_structure: init.stru
calculator:
  name: abacus
  abacus:
    parameters: {}
""",
        encoding="utf-8",
    )

    config = ConfigLoader.load(str(config_file))

    assert config["calculation"]["type"] == "relax"
    assert ConfigLoader.validate(config) is True


def test_load_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ConfigLoader.load(str(tmp_path / "missing.yaml"))


def test_validate_rejects_missing_calculation():
    with pytest.raises(ValueError, match="calculation"):
        ConfigLoader.validate({"calculator": {"name": "abacus"}})


def test_validate_accepts_supported_calculation_types():
    required_fields = {
        "neb": {"init_chain": "init_neb_chain.traj"},
        "autoneb": {"init_chain": "init_neb_chain.traj"},
        "dimer": {"init_structure": "dimer_init.traj"},
        "sella": {"init_structure": "sella_init.stru"},
        "d2s": {"init_file": "init.stru", "final_file": "final.stru"},
        "relax": {"init_structure": "init.stru"},
        "vibration": {"init_structure": "ts_opt.stru"},
    }
    for calc_type, fields in required_fields.items():
        config = {
            "calculation": {"type": calc_type, **fields},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
        assert ConfigLoader.validate(config) is True


def test_validate_rejects_unknown_calculation_type():
    with pytest.raises(ValueError, match="Unsupported"):
        ConfigLoader.validate(
            {
                "calculation": {"type": "unknown"},
                "calculator": {"name": "abacus"},
            }
        )


def test_validate_requires_workflow_inputs():
    with pytest.raises(ValueError, match="init_chain"):
        ConfigLoader.validate(
            {
                "calculation": {"type": "neb"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_requires_matching_calculator_section():
    with pytest.raises(ValueError, match="calculator.abacus"):
        ConfigLoader.validate(
            {
                "calculation": {"type": "relax", "init_structure": "init.stru"},
                "calculator": {"name": "abacus"},
            }
        )


def test_validate_requires_dp_model():
    with pytest.raises(ValueError, match="calculator.dp.model"):
        ConfigLoader.validate(
            {
                "calculation": {"type": "relax", "init_structure": "init.stru"},
                "calculator": {"name": "dp", "dp": {}},
            }
        )
