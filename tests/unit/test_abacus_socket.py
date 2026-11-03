import os
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.calculators.socketio import bind_unixsocket

from atst_tools.calculators import factory
from atst_tools.calculators.constant_potential import _backend_log_paths, _backend_scf_converged
from atst_tools.api.services import validate_config
from atst_tools.utils.abacus_io import prepare_abacus_input_from_config
from atst_tools.utils.config_schema import ABACUS_CONTROL_KEYS, ATSTConfig
from atst_tools.workflows.md import _ScfValidatedCalculator


class FakeProfile:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeAbacus:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeSocketIO:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = 0
        FakeSocketIO.instances.append(self)

    def close(self):
        self.closed += 1


@pytest.fixture
def fakes(monkeypatch):
    FakeSocketIO.instances = []
    monkeypatch.setattr(factory, "ATSTAbacusProfile", FakeProfile)
    monkeypatch.setattr(factory, "Abacus", FakeAbacus)
    monkeypatch.setattr(factory, "AbacusSocketIO", FakeSocketIO)


def _config(socket, workflow="relax", **calculation):
    return {
        "calculation": {"type": workflow, **calculation},
        "calculator": {
            "name": "abacus",
            "abacus": {
                "mpi": 2,
                "socket": socket,
                "parameters": {"calculation": "scf", "cal_force": 1, "ecutwfc": 50},
            },
        },
    }


def test_socket_disabled_builds_fileio_calculator(fakes):
    calc = factory.CalculatorFactory.get_calculator("abacus", _config(False), directory="run")

    assert isinstance(calc, FakeAbacus)
    assert "socket" not in calc.kwargs


def test_socket_true_builds_socketio_with_unique_unix_names(fakes):
    first = factory.CalculatorFactory.get_calculator("abacus", _config(True), directory="a")
    second = factory.CalculatorFactory.get_calculator("abacus", _config(True), directory="b")

    assert isinstance(first, FakeSocketIO)
    assert first.kwargs["inp"] == {"calculation": "scf", "cal_force": 1}
    assert first.kwargs["ecutwfc"] == 50
    assert "port" not in first.kwargs
    assert first.kwargs["unixsocket"].startswith("atst_")
    assert first.kwargs["unixsocket"] != second.kwargs["unixsocket"]
    assert first.kwargs["profile"].kwargs["command"] == "mpirun -np 2 abacus"


def test_socket_mapping_passes_port_and_timeout(fakes):
    calc = factory.CalculatorFactory.get_calculator(
        "abacus", _config({"port": 31500, "timeout": 30.0}), directory="run"
    )

    assert calc.kwargs["port"] == 31500
    assert calc.kwargs["timeout"] == 30.0
    assert "unixsocket" not in calc.kwargs


def test_socket_mapping_disabled_falls_back_to_fileio(fakes):
    calc = factory.CalculatorFactory.get_calculator(
        "abacus", _config({"enabled": False}), directory="run"
    )

    assert isinstance(calc, FakeAbacus)


def test_socket_session_closes_only_clients_it_created(fakes):
    outside = factory.CalculatorFactory.get_calculator("abacus", _config(True), directory="a")
    with factory.socket_session() as owned:
        inside = factory.CalculatorFactory.get_calculator("abacus", _config(True), directory="b")
        assert owned == [inside]

    assert inside.closed == 1
    assert outside.closed == 0


def test_socket_session_closes_on_error_and_nests(fakes):
    with pytest.raises(RuntimeError, match="boom"):
        with factory.socket_session():
            outer = factory.CalculatorFactory.get_calculator("abacus", _config(True), directory="a")
            with factory.socket_session():
                inner = factory.CalculatorFactory.get_calculator("abacus", _config(True), directory="b")
            assert (inner.closed, outer.closed) == (1, 0)
            raise RuntimeError("boom")

    assert outer.closed == 1


def test_explicit_socket_endpoint_is_passed_to_backend_unchecked(fakes):
    config = _config({"unixsocket": "h2au"})
    first = factory.CalculatorFactory.get_calculator("abacus", config, directory="a")
    second = factory.CalculatorFactory.get_calculator("abacus", config, directory="b")

    # ATST keeps no endpoint registry; the backend bind decides conflicts.
    assert first.kwargs["unixsocket"] == second.kwargs["unixsocket"] == "h2au"


def test_backend_bind_rejects_an_occupied_unix_socket():
    path = f"/tmp/ipi_atst_unit_{os.getpid()}"
    with bind_unixsocket(path):
        with pytest.raises(OSError, match="in use"):
            with bind_unixsocket(path):
                pass
        assert os.path.exists(path)
    assert not os.path.exists(path)


def _prepared_input(tmp_path, socket, parameters=None):
    structure = tmp_path / "init.xyz"
    structure.write_text("1\nfixture\nH 0 0 0\n", encoding="utf-8")
    abacus = {
        "pseudopotentials": {"H": "H.upf"},
        "basissets": {"H": "H.orb"},
        "parameters": parameters or {"ecutwfc": 50},
    }
    if socket != "omitted":
        abacus["socket"] = socket
    config = validate_config({
        "calculation": {"type": "relax", "init_structure": str(structure)},
        "calculator": {"name": "abacus", "abacus": abacus},
    })
    prepare_abacus_input_from_config(config, str(structure), str(tmp_path / "prepared"))
    return (tmp_path / "prepared" / "INPUT").read_text(encoding="utf-8")


def _input_values(text):
    return dict(line.split(maxsplit=1) for line in text.splitlines()[1:] if len(line.split()) == 2)


@pytest.mark.parametrize("socket", ["omitted", False, {"enabled": False}])
def test_disabled_socket_input_has_no_socket_keys(tmp_path, socket):
    input_text = _prepared_input(tmp_path, socket)

    assert "ecutwfc" in input_text
    assert "socket" not in input_text


@pytest.mark.parametrize("socket", [True, {"unixsocket": "h2au"}])
def test_enabled_socket_input_matches_backend_semantics(tmp_path, socket):
    values = _input_values(_prepared_input(tmp_path, socket, {"ecutwfc": 50, "cal_force": "true"}))

    assert values["socket_driver"] == "1"
    assert values["calculation"] == "scf"
    assert values["cal_force"] == "1"
    assert "socket" not in values


def test_enabled_socket_input_rejects_contradictory_calculation(tmp_path):
    with pytest.raises(ValueError, match="calculation"):
        _prepared_input(tmp_path, True, {"calculation": "relax"})


def test_every_input_writer_shares_the_control_keys():
    from atst_tools.calculators import constant_potential
    from atst_tools.utils import abacus_io

    assert "socket" in ABACUS_CONTROL_KEYS
    assert factory._ABACUS_CONTROL_KEYS is ABACUS_CONTROL_KEYS
    assert constant_potential._ABACUS_CONTROL_KEYS is ABACUS_CONTROL_KEYS
    assert abacus_io._ABACUS_META_KEYS is ABACUS_CONTROL_KEYS


@pytest.mark.parametrize("workflow", ["neb", "autoneb", "irc", "dmf"])
def test_socket_rejects_multi_calculator_workflows(fakes, workflow):
    with pytest.raises(ValueError, match="calculator.abacus.socket is supported only"):
        factory.CalculatorFactory.get_calculator("abacus", _config(True, workflow), directory="run")


def test_socket_rejects_native_md_driver(fakes):
    with pytest.raises(ValueError, match="driver=ase"):
        factory.CalculatorFactory.get_calculator(
            "abacus", _config(True, "md", driver="abacus_native"), directory="run"
        )


def test_socket_rejects_port_and_unixsocket_together(fakes):
    with pytest.raises(ValueError, match="either port or unixsocket"):
        factory.CalculatorFactory.get_calculator(
            "abacus", _config({"port": 1, "unixsocket": "x"}), directory="run"
        )


def _schema_config(socket, workflow="relax", **calculation):
    calc = {"type": workflow, "init_structure": "init.stru", **calculation}
    return {
        "calculation": calc,
        "calculator": {"name": "abacus", "abacus": {"socket": socket}},
    }


def test_schema_accepts_socket_bool_and_mapping():
    assert ATSTConfig.model_validate(_schema_config(True)).calculator.abacus.socket_enabled()
    mapped = ATSTConfig.model_validate(_schema_config({"unixsocket": "h2au", "timeout": 60}))
    assert mapped.calculator.abacus.socket.unixsocket == "h2au"
    assert not ATSTConfig.model_validate(_schema_config(False)).calculator.abacus.socket_enabled()


def test_schema_rejects_socket_for_unsupported_workflow():
    config = _schema_config(True, "vibration")
    ATSTConfig.model_validate(config)
    config["calculation"] = {"type": "irc", "init_structure": "ts.stru"}
    with pytest.raises(ValueError, match="calculator.abacus.socket is supported only"):
        ATSTConfig.model_validate(config)


def test_schema_rejects_unknown_socket_key():
    with pytest.raises(ValueError):
        ATSTConfig.model_validate(_schema_config({"host": "node1"}))


def test_socket_rejects_variable_cell_md_ensemble(fakes):
    with pytest.raises(ValueError, match="fixed-cell md ensemble"):
        factory.CalculatorFactory.get_calculator(
            "abacus", _config(True, "md", ensemble="npt"), directory="run"
        )


def test_socket_accepts_fixed_cell_md(fakes):
    calc = factory.CalculatorFactory.get_calculator(
        "abacus", _config(True, "md", ensemble="nve"), directory="run"
    )

    assert isinstance(calc, FakeSocketIO)


def test_schema_rejects_socket_for_npt_md():
    config = _schema_config(True, "md", ensemble="nvt", algorithm="bussi")
    ATSTConfig.model_validate(config)
    config["calculation"].update(ensemble="npt", algorithm="nptberendsen")
    with pytest.raises(ValueError, match="fixed-cell md ensemble"):
        ATSTConfig.model_validate(config)


class _SocketLikeBackend(Calculator):
    """Socket-shaped backend: SCF state is an attribute, ABACUS runs in ``abacus``."""

    implemented_properties = ["energy", "forces"]

    def __init__(self, converged, abacus_directory="."):
        super().__init__()
        self.converged = converged
        self.abacus = SimpleNamespace(directory=abacus_directory, parameters={})

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.last_scf_converged = self.converged
        self.results = {"energy": -1.0, "forces": np.zeros((len(atoms), 3))}


@pytest.mark.parametrize("converged", [True, False])
def test_scf_evidence_reads_socket_attribute(converged):
    backend = _SocketLikeBackend(converged)
    backend.last_scf_converged = converged

    assert _backend_scf_converged(backend, {"energy": -1.0}) is converged


def test_scf_log_paths_follow_wrapped_abacus_directory(tmp_path):
    backend = _SocketLikeBackend(None, abacus_directory=str(tmp_path / "md_run"))

    assert _backend_log_paths(backend) == (tmp_path / "md_run" / "OUT.ABACUS" / "running_scf.log",)


def test_md_scf_guard_accepts_converged_socket_and_rejects_unconverged():
    atoms = Atoms("H2", positions=[[0, 0, 0], [0, 0, 0.74]], cell=[5, 5, 5], pbc=True)

    atoms.calc = _ScfValidatedCalculator(_SocketLikeBackend(True))
    assert atoms.get_forces().shape == (2, 3)

    atoms.calc = _ScfValidatedCalculator(_SocketLikeBackend(False))
    with pytest.raises(RuntimeError, match="SCF not converged"):
        atoms.get_forces()


def test_socket_accepts_ccqn(fakes):
    calc = factory.CalculatorFactory.get_calculator("abacus", _config(True, "ccqn"), directory="run")

    assert isinstance(calc, FakeSocketIO)


def test_schema_accepts_socket_for_ccqn():
    config = _schema_config(True, "ccqn", reactive_bonds="1-2")

    assert ATSTConfig.model_validate(config).calculator.abacus.socket_enabled()
