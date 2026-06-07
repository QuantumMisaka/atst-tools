from pathlib import Path

import pytest
from ruamel.yaml import YAML
from atst_tools.utils.config import ConfigLoader
from atst_tools.utils.config_schema import json_schema


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
        "ccqn": {"init_structure": "ccqn_init.traj", "reactive_bonds": "1-2"},
        "d2s": {"init_file": "init.stru", "final_file": "final.stru"},
        "relax": {"init_structure": "init.stru"},
        "vibration": {"init_structure": "ts_opt.stru"},
        "irc": {"init_structure": "ts_opt.stru"},
        "md": {"init_structure": "init.stru"},
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


def test_validate_accepts_neb_make_input():
    assert ConfigLoader.validate(
        {
            "calculation": {
                "type": "neb",
                "make": {
                    "init_structure": "init.stru",
                    "final_structure": "final.stru",
                    "n_images": 5,
                },
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    ) is True


def test_validate_accepts_neb_two_stage_and_endpoint_optimization():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "neb",
                "init_chain": "init_neb_chain.traj",
                "two_stage": True,
                "stage1_steps": 5,
                "stage1_fmax": 0.1,
                "endpoint_optimization": {"enabled": True, "fmax": 0.03, "max_steps": 8},
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["two_stage"] is True
    assert config["calculation"]["endpoint_optimization"]["max_steps"] == 8


def test_validate_neb_two_stage_defaults_and_unbounded_stage1_steps():
    from atst_tools.utils.config_schema import apply_calculation_defaults

    default_config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "neb",
                "init_chain": "init_neb_chain.traj",
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )
    null_config = {
        "calculation": {
            "type": "neb",
            "init_chain": "init_neb_chain.traj",
            "two_stage": True,
            "stage1_steps": None,
        },
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    assert ConfigLoader.validate(null_config) is True
    assert apply_calculation_defaults(null_config["calculation"])["stage1_steps"] is None
    assert default_config["calculation"]["stage1_steps"] == 20
    assert default_config["calculation"]["stage1_fmax"] == pytest.approx(0.20)


def test_normalize_omits_null_neb_stage1_steps():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "neb",
                "init_chain": "init_neb_chain.traj",
                "two_stage": True,
                "stage1_steps": None,
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert "stage1_steps" not in config["calculation"]


def test_validate_rejects_zero_neb_stage1_steps():
    with pytest.raises(ValueError, match="stage1_steps"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "neb",
                    "init_chain": "init_neb_chain.traj",
                    "two_stage": True,
                    "stage1_steps": 0,
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_accepts_ase_md_defaults():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "md",
                "driver": "ase",
                "init_structure": "init.stru",
                "steps": 5,
                "temperature_K": 300.0,
            },
            "calculator": {"name": "dp", "dp": {"model": "model.pb"}},
        }
    )

    assert config["calculation"]["driver"] == "ase"
    assert config["calculation"]["ensemble"] == "nvt"
    assert config["calculation"]["algorithm"] == "bussi"
    assert config["calculation"]["trajectory"] == "md.traj"


def test_validate_accepts_abacus_native_md_only_with_abacus():
    config = {
        "calculation": {
            "type": "md",
            "driver": "abacus_native",
            "init_structure": "init.stru",
            "steps": 2,
        },
        "calculator": {
            "name": "abacus",
            "abacus": {
                "parameters": {
                    "calculation": "md",
                    "basis_type": "lcao",
                }
            },
        },
    }

    assert ConfigLoader.validate(config) is True


def test_validate_rejects_abacus_native_md_with_dp():
    with pytest.raises(ValueError, match="abacus_native"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "md",
                    "driver": "abacus_native",
                    "init_structure": "init.stru",
                    "steps": 2,
                },
                "calculator": {"name": "dp", "dp": {"model": "model.pb"}},
            }
        )


def test_validate_rejects_incompatible_md_algorithm():
    with pytest.raises(ValueError, match="algorithm"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "md",
                    "driver": "ase",
                    "ensemble": "nve",
                    "algorithm": "bussi",
                    "init_structure": "init.stru",
                    "steps": 2,
                },
                "calculator": {"name": "dp", "dp": {"model": "model.pb"}},
            }
        )


def test_validate_accepts_ccqn_auto_reactive_bonds_without_explicit_bonds():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "ccqn",
                "init_structure": "ccqn_init.traj",
                "e_vector_method": "ic",
                "auto_reactive_bonds": {"enabled": True, "molecule_indices": [1]},
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["auto_reactive_bonds"]["enabled"] is True


def test_validate_accepts_descent_irc_backend():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "irc",
                "backend": "descent",
                "init_structure": "ts.traj",
                "mode_vector": "mode.npy",
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["backend"] == "descent"


def test_validate_rejects_invalid_endpoint_singlepoint_policy():
    with pytest.raises(ValueError, match="endpoint_singlepoint"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "neb",
                    "init_chain": "init_neb_chain.traj",
                    "endpoint_singlepoint": "maybe",
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_rejects_non_mapping_d2s_endpoint_optimization():
    with pytest.raises(ValueError, match="endpoint_optimization"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "d2s",
                    "init_file": "init.stru",
                    "final_file": "final.stru",
                    "endpoint_optimization": False,
                },
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


def test_validate_rejects_dp_type_map_and_type_dict_conflict():
    with pytest.raises(ValueError, match="type_map.*type_dict"):
        ConfigLoader.validate(
            {
                "calculation": {"type": "relax", "init_structure": "init.stru"},
                "calculator": {
                    "name": "dp",
                    "dp": {
                        "model": "model.pt",
                        "type_map": ["H"],
                        "type_dict": {"H": 0},
                    },
                },
            }
        )


def test_validate_rejects_invalid_irc_direction():
    with pytest.raises(ValueError, match="direction"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "irc",
                    "init_structure": "ts_opt.stru",
                    "direction": "sideways",
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_rejects_invalid_vibration_thermochemistry_model():
    with pytest.raises(ValueError, match="thermochemistry.model"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "vibration",
                    "init_structure": "ts_opt.stru",
                    "thermochemistry": {"model": "unknown"},
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_accepts_vibration_thermochemistry_energy_threshold():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "vibration",
                "init_structure": "ts_opt.stru",
                "thermochemistry": {"energy_threshold": 1.0e-6},
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["thermochemistry"]["energy_threshold"] == 1.0e-6


def test_validate_rejects_negative_vibration_thermochemistry_energy_threshold():
    with pytest.raises(ValueError, match="energy_threshold"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "vibration",
                    "init_structure": "ts_opt.stru",
                    "thermochemistry": {"energy_threshold": -1.0},
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_rejects_redundant_yaml_aliases():
    base_calculator = {"name": "abacus", "abacus": {"parameters": {}}}
    invalid_configs = [
        {
            "calculation": {
                "type": "d2s",
                "init_file": "init.stru",
                "final_file": "final.stru",
                "endpoint_max_steps": 1,
            },
            "calculator": base_calculator,
        },
        {
            "calculation": {
                "type": "neb",
                "make": {
                    "init_structure": "init.stru",
                    "final_structure": "final.stru",
                    "n_images": 5,
                    "mag": {"Fe": 2.0},
                },
            },
            "calculator": base_calculator,
        },
        {
            "calculation": {
                "type": "vibration",
                "init_structure": "ts_opt.stru",
                "temperature": 300.0,
            },
            "calculator": base_calculator,
        },
    ]

    for config in invalid_configs:
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            ConfigLoader.validate(config)


def test_normalize_populates_defaults_for_relax_dp():
    config = ConfigLoader.normalize(
        {
            "calculation": {"type": "relax", "init_structure": "init.stru"},
            "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
        }
    )

    assert "config_version" not in config
    assert config["calculation"]["fmax"] == 0.05
    assert config["calculation"]["max_steps"] == 200
    assert config["calculation"]["trajectory"] == "relax.traj"
    assert config["calculator"]["dp"]["share_calculator"] is True


def test_validate_rejects_unknown_top_level_config_version():
    with pytest.raises(ValueError, match="config_version"):
        ConfigLoader.validate(
            {
                "config_version": "1.0.0",
                "calculation": {"type": "relax", "init_structure": "init.stru"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_autoneb_optimizer_kwargs_are_governed_and_default_empty():
    config = ConfigLoader.normalize(
        {
            "calculation": {"type": "autoneb", "init_chain": "chain.traj"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["optimizer_kwargs"] == {}


def test_validate_accepts_autoneb_optimizer_kwargs():
    config = {
        "calculation": {
            "type": "autoneb",
            "init_chain": "chain.traj",
            "optimizer_kwargs": {"downhill_check": True, "maxstep": 0.05},
        },
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    assert ConfigLoader.validate(config) is True


def test_validate_accepts_neb_optimizer_kwargs():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "neb",
                "init_chain": "chain.traj",
                "optimizer_kwargs": {"downhill_check": True, "maxstep": 0.05},
            },
            "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
        }
    )

    assert config["calculation"]["optimizer_kwargs"] == {
        "downhill_check": True,
        "maxstep": 0.05,
    }


def test_validate_accepts_neb_backend_selector():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "neb",
                "init_chain": "chain.traj",
                "neb_backend": "ase",
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["neb_backend"] == "ase"


def test_validate_accepts_abacus_version_command():
    config = ConfigLoader.normalize(
        {
            "calculation": {"type": "relax", "init_structure": "init.stru"},
            "calculator": {
                "name": "abacus",
                "abacus": {
                    "version_command": "abacus --version",
                    "parameters": {},
                },
            },
        }
    )

    assert config["calculator"]["abacus"]["version_command"] == "abacus --version"


def test_validate_accepts_autoneb_backend_selector():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "autoneb",
                "init_chain": "chain.traj",
                "neb_backend": "ase",
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["neb_backend"] == "ase"


def test_validate_rejects_non_positive_autoneb_n_simul():
    with pytest.raises(ValueError, match="n_simul"):
        ConfigLoader.normalize(
            {
                "calculation": {
                    "type": "autoneb",
                    "init_chain": "chain.traj",
                    "n_simul": 0,
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_rejects_unknown_neb_backend():
    with pytest.raises(ValueError, match="neb_backend"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "neb",
                    "init_chain": "chain.traj",
                    "neb_backend": "custom",
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_accepts_d2s_neb_optimizer_kwargs():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "d2s",
                "init_file": "init.traj",
                "final_file": "final.traj",
                "neb": {"optimizer_kwargs": {"downhill_check": True, "maxstep": 0.05}},
            },
            "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
        }
    )

    assert config["calculation"]["neb"]["optimizer_kwargs"] == {
        "downhill_check": True,
        "maxstep": 0.05,
    }


def test_validate_accepts_d2s_neb_scale_fmax():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "d2s",
                "init_file": "init.traj",
                "final_file": "final.traj",
                "neb": {"scale_fmax": 1.0},
            },
            "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
        }
    )

    assert config["calculation"]["neb"]["scale_fmax"] == 1.0


def test_validate_accepts_d2s_neb_idpp_controls():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "d2s",
                "init_file": "init.traj",
                "final_file": "final.traj",
                "neb": {"idpp_maxiter": 5000, "idpp_tol": 1e-3},
            },
            "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
        }
    )

    assert config["calculation"]["neb"]["idpp_maxiter"] == 5000
    assert config["calculation"]["neb"]["idpp_tol"] == 1e-3


def test_validate_accepts_d2s_ccqn_method():
    config = ConfigLoader.normalize(
        {
            "calculation": {
                "type": "d2s",
                "method": "ccqn",
                "init_file": "init.traj",
                "final_file": "final.traj",
            },
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        }
    )

    assert config["calculation"]["method"] == "ccqn"
    assert config["calculation"]["ccqn"]["e_vector_method"] == "interp"


def test_normalize_legacy_root_abacus_section():
    config = ConfigLoader.normalize(
        {
            "calculation": {"type": "relax", "init_structure": "init.stru"},
            "abacus": {"parameters": {"calculation": "scf"}},
        }
    )

    assert config["calculator"]["name"] == "abacus"
    assert config["calculator"]["abacus"]["parameters"]["calculation"] == "scf"


def test_validate_rejects_invalid_numeric_range():
    with pytest.raises(ValueError, match="fmax"):
        ConfigLoader.validate(
            {
                "calculation": {"type": "relax", "init_structure": "init.stru", "fmax": -0.1},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_validate_rejects_unknown_calculation_field():
    with pytest.raises(ValueError, match="unknown_field"):
        ConfigLoader.validate(
            {
                "calculation": {
                    "type": "relax",
                    "init_structure": "init.stru",
                    "unknown_field": True,
                },
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            }
        )


def test_run_templates_validate_against_schema():
    from atst_tools.scripts.main import _template

    yaml = YAML(typ="safe")
    for calc_type in ("neb", "autoneb", "dimer", "sella", "ccqn", "d2s", "relax", "vibration", "irc"):
        for calculator in ("abacus", "dp"):
            config = yaml.load(_template(calc_type, calculator))
            assert ConfigLoader.validate(config) is True


def test_json_schema_can_be_generated():
    schema = json_schema()

    assert schema["type"] == "object"
    assert "calculation" in schema["properties"]
    assert "config_version" not in schema["properties"]
