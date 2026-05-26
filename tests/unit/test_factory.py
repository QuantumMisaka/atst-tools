import os
import sys
import types

import pytest

from atst_tools.calculators import factory


class FakeProfile:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeAbacus:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_abacus_factory_flattens_config(monkeypatch):
    monkeypatch.setattr(factory, "ATSTAbacusProfile", FakeProfile)
    monkeypatch.setattr(factory, "Abacus", FakeAbacus)

    config = {
        "calculator": {
            "name": "abacus",
            "abacus": {
                "command": "abacus",
                "mpi": 4,
                "omp": 2,
                "directory": "ignored",
                "kpts": [1, 2, 3],
                "parameters": {
                    "basis_type": "lcao",
                    "ks_solver": "cusolver",
                    "pseudo_dir": "../data",
                    "orbital_dir": "../data",
                    "pp": {"H": "H.upf"},
                    "basis": {"H": "H.orb"},
                },
            },
        }
    }

    calc = factory.CalculatorFactory.get_calculator("abacus", config, directory="run")

    assert calc.kwargs["directory"] == "run"
    assert calc.kwargs["profile"].kwargs["command"] == "mpirun -np 4 abacus"
    assert calc.kwargs["profile"].kwargs["version_command"] is None
    assert calc.kwargs["profile"].kwargs["omp_num_threads"] == 2
    assert calc.kwargs["pseudopotentials"] == {"H": "H.upf"}
    assert calc.kwargs["basissets"] == {"H": "H.orb"}
    assert calc.kwargs["kpts"]["mode"] == "mp-sampling"
    assert calc.kwargs["ks_solver"] == "cusolver"


def test_abacus_factory_uses_explicit_version_command(monkeypatch):
    monkeypatch.setattr(factory, "ATSTAbacusProfile", FakeProfile)
    monkeypatch.setattr(factory, "Abacus", FakeAbacus)

    config = {
        "calculator": {
            "name": "abacus",
            "abacus": {
                "command": "abacus",
                "mpi": 4,
                "version_command": "abacus --version",
                "parameters": {"calculation": "scf"},
            },
        }
    }

    calc = factory.CalculatorFactory.get_calculator("abacus", config)

    profile_kwargs = calc.kwargs["profile"].kwargs
    assert profile_kwargs["command"] == "mpirun -np 4 abacus"
    assert profile_kwargs["version_command"] == "abacus --version"
    assert "version_command" not in calc.kwargs


def test_dp_factory_uses_deepmd_calculator(monkeypatch):
    class FakeDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    deepmd = types.ModuleType("deepmd")
    calculator = types.ModuleType("deepmd.calculator")
    calculator.DP = FakeDP
    monkeypatch.setitem(sys.modules, "deepmd", deepmd)
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator)
    factory.DeepPotentialFactory._instances.clear()

    config = {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}}
    calc = factory.CalculatorFactory.get_calculator("dp", config)

    assert calc.kwargs["model"] == "model.pb"


def test_dp_factory_passes_head_and_type_dict(monkeypatch):
    class FakeDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    calculator = types.ModuleType("deepmd.calculator")
    calculator.DP = FakeDP
    monkeypatch.setitem(sys.modules, "deepmd", types.ModuleType("deepmd"))
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator)
    factory.DeepPotentialFactory._instances.clear()

    config = {
        "calculator": {
            "name": "dp",
            "dp": {
                "model": "model.pt",
                "head": "Omat24",
                "type_map": ["H", "Li", "Si"],
            },
        }
    }
    calc = factory.CalculatorFactory.get_calculator("dp", config)

    assert calc.kwargs["model"] == "model.pt"
    assert calc.kwargs["head"] == "Omat24"
    assert calc.kwargs["type_dict"] == {"H": 0, "Li": 1, "Si": 2}
    assert "type_map" not in calc.kwargs


def test_dp_factory_rejects_type_map_and_type_dict_conflict(monkeypatch):
    class FakeDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    calculator = types.ModuleType("deepmd.calculator")
    calculator.DP = FakeDP
    monkeypatch.setitem(sys.modules, "deepmd", types.ModuleType("deepmd"))
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator)
    factory.DeepPotentialFactory._instances.clear()

    config = {
        "calculator": {
            "name": "dp",
            "dp": {
                "model": "model.pt",
                "type_map": ["H"],
                "type_dict": {"H": 0},
            },
        }
    }

    with pytest.raises(ValueError, match="type_map.*type_dict"):
        factory.CalculatorFactory.get_calculator("dp", config)


def test_dp_factory_sets_omp_threads(monkeypatch):
    class FakeDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    calculator = types.ModuleType("deepmd.calculator")
    calculator.DP = FakeDP
    monkeypatch.setitem(sys.modules, "deepmd", types.ModuleType("deepmd"))
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator)
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    factory.DeepPotentialFactory._instances.clear()

    config = {"calculator": {"name": "dp", "dp": {"model": "model.pt", "omp": 4}}}
    factory.CalculatorFactory.get_calculator("dp", config)

    assert os.environ["OMP_NUM_THREADS"] == "4"


def test_dp_factory_cache_key_includes_head(monkeypatch):
    class FakeDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    calculator = types.ModuleType("deepmd.calculator")
    calculator.DP = FakeDP
    monkeypatch.setitem(sys.modules, "deepmd", types.ModuleType("deepmd"))
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator)
    factory.DeepPotentialFactory._instances.clear()

    first = {"calculator": {"name": "dp", "dp": {"model": "model.pt", "head": "A"}}}
    second = {"calculator": {"name": "dp", "dp": {"model": "model.pt", "head": "B"}}}

    calc_a1 = factory.CalculatorFactory.get_calculator("dp", first)
    calc_a2 = factory.CalculatorFactory.get_calculator("dp", first)
    calc_b = factory.CalculatorFactory.get_calculator("dp", second)

    assert calc_a1 is calc_a2
    assert calc_a1 is not calc_b


def test_dp_factory_respects_share_calculator_false(monkeypatch):
    class FakeDP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    calculator = types.ModuleType("deepmd.calculator")
    calculator.DP = FakeDP
    monkeypatch.setitem(sys.modules, "deepmd", types.ModuleType("deepmd"))
    monkeypatch.setitem(sys.modules, "deepmd.calculator", calculator)
    factory.DeepPotentialFactory._instances.clear()

    config = {
        "calculator": {
            "name": "dp",
            "dp": {"model": "model.pt", "share_calculator": False},
        }
    }
    calc_a = factory.CalculatorFactory.get_calculator("dp", config)
    calc_b = factory.CalculatorFactory.get_calculator("dp", config)

    assert calc_a is not calc_b


def test_invalid_calculator_name_raises():
    with pytest.raises(ValueError, match="Unsupported calculator"):
        factory.CalculatorFactory.get_calculator("vasp", {})


def test_abacus_backend_source_logs_once(monkeypatch, caplog):
    monkeypatch.setattr(factory, "ATSTAbacusProfile", FakeProfile)
    monkeypatch.setattr(factory, "Abacus", FakeAbacus)
    monkeypatch.setattr(factory, "_ABACUS_BACKEND_LOGGED", False)
    caplog.set_level("INFO")

    config = {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}}
    factory.CalculatorFactory.get_calculator("abacus", config)
    factory.CalculatorFactory.get_calculator("abacus", config)

    assert caplog.text.count("abacuslite backend") == 1
