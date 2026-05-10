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
    monkeypatch.setattr(factory, "AbacusProfile", FakeProfile)
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
    assert calc.kwargs["profile"].kwargs["omp_num_threads"] == 2
    assert calc.kwargs["pseudopotentials"] == {"H": "H.upf"}
    assert calc.kwargs["basissets"] == {"H": "H.orb"}
    assert calc.kwargs["kpts"]["mode"] == "mp-sampling"
    assert calc.kwargs["ks_solver"] == "cusolver"


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


def test_invalid_calculator_name_raises():
    with pytest.raises(ValueError, match="Unsupported calculator"):
        factory.CalculatorFactory.get_calculator("vasp", {})


def test_abacus_backend_source_logs_once(monkeypatch, caplog):
    monkeypatch.setattr(factory, "AbacusProfile", FakeProfile)
    monkeypatch.setattr(factory, "Abacus", FakeAbacus)
    monkeypatch.setattr(factory, "_ABACUS_BACKEND_LOGGED", False)
    caplog.set_level("INFO")

    config = {"calculator": {"name": "abacus", "abacus": {"parameters": {}}}}
    factory.CalculatorFactory.get_calculator("abacus", config)
    factory.CalculatorFactory.get_calculator("abacus", config)

    assert caplog.text.count("abacuslite backend") == 1
