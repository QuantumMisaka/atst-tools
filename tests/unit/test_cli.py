from pathlib import Path
import json
import re

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write


def _atoms(energy=0.0, x=0.0):
    atoms = Atoms("H", positions=[[x, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


class DummyCalc(Calculator):
    implemented_properties = ["energy", "forces", "stress"]

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.results["energy"] = 4.0
        self.results["forces"] = np.ones((len(atoms), 3)) * 0.1
        self.results["stress"] = np.zeros(6)


def test_only_git_style_console_script_is_exposed():
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'atst = "atst_tools.scripts.cli:main"' in text
    assert "atst-run" not in text
    assert "atst-neb-make" not in text
    assert "atst-neb-post" not in text


def test_atst_version_uses_governed_package_version(capsys):
    from atst_tools import package_version
    from atst_tools.scripts import cli

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    expected = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE).group(1)

    assert package_version() == expected

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"atst {package_version()}"


def test_atst_run_dispatches_d2s(monkeypatch):
    from atst_tools.scripts import main as run_cli
    from atst_tools.scripts import cli

    calls = []

    class FakeD2SWorkflow:
        def __init__(self, config, calc_name, calc_config):
            calls.append(("init", calc_name, calc_config["type"]))

        def run(self):
            calls.append(("run",))

    config = {
        "calculation": {"type": "d2s", "init_file": "init.stru", "final_file": "final.stru"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(run_cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(run_cli, "D2SWorkflow", FakeD2SWorkflow)

    cli.main(["run", "config.yaml"])

    assert calls == [("init", "abacus", "d2s"), ("run",)]


def test_atst_run_reports_irc_boundary_without_traceback(monkeypatch):
    from atst_tools.scripts import main as run_cli
    from atst_tools.scripts import cli

    class FakeIRCWorkflow:
        def __init__(self, config, calc_name, calc_config):
            return None

        def run(self):
            raise run_cli.IRCBoundaryError("IRC calculation stopped at the current supported boundary.")

    config = {
        "calculation": {"type": "irc", "init_structure": "ts.stru"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(run_cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(run_cli, "IRCWorkflow", FakeIRCWorkflow)

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["run", "config.yaml"])

    assert str(excinfo.value) == "IRC calculation stopped at the current supported boundary."


def test_atst_run_restart_overrides_config(monkeypatch):
    from atst_tools.scripts import main as run_cli
    from atst_tools.scripts import cli

    seen = {}
    config = {
        "calculation": {"type": "relax", "init_structure": "init.stru"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    class FakeRelaxWorkflow:
        def __init__(self, config, calc_name, calc_config):
            seen["restart"] = calc_config["restart"]

        def run(self):
            return None

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(run_cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(run_cli, "RelaxWorkflow", FakeRelaxWorkflow)

    cli.main(["run", "--restart", "config.yaml"])

    assert seen["restart"] is True


def test_atst_run_dry_run_validates_without_dispatch(monkeypatch, caplog):
    from atst_tools.scripts import main as run_cli
    from atst_tools.scripts import cli

    caplog.set_level("INFO")
    config = {
        "calculation": {"type": "relax", "init_structure": "init.stru"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(run_cli.ConfigLoader, "validate", lambda config: True)

    cli.main(["run", "--dry-run", "config.yaml"])

    assert "Configuration is valid" in caplog.text


def test_atst_run_list_types_prints_supported_types(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--list-types"])

    output = capsys.readouterr().out
    assert "neb" in output
    assert "vibration" in output
    assert "irc" in output


def test_atst_run_show_template_prints_yaml(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--show-template", "neb", "--calculator", "abacus"])

    output = capsys.readouterr().out
    assert "calculation:" in output
    assert "type: neb" in output
    assert "make:" in output
    assert "calculator:" in output


def test_atst_run_neb_make_and_init_chain_are_exclusive(monkeypatch):
    from atst_tools.scripts import cli

    config = {
        "calculation": {
            "type": "neb",
            "init_chain": "chain.traj",
            "make": {"init_structure": "i.traj", "final_structure": "f.traj", "n_images": 1},
        },
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.setattr(cli.run_cli.ConfigLoader, "load", lambda path: config)

    with pytest.raises(ValueError, match="exactly one"):
        cli.main(["run", "config.yaml"])


def test_run_neb_repairs_placeholder_endpoints_before_neb_construction(tmp_path, monkeypatch):
    from atst_tools.scripts import main as run_cli
    from atst_tools.utils.neb_endpoints import ENDPOINT_PLACEHOLDER, mark_endpoint_result

    monkeypatch.chdir(tmp_path)
    chain = [_atoms(0.0, 0.0), _atoms(1.0, 1.0), _atoms(0.0, 2.0)]
    mark_endpoint_result(chain[0], ENDPOINT_PLACEHOLDER)
    mark_endpoint_result(chain[-1], ENDPOINT_PLACEHOLDER)
    write("chain.traj", chain)
    captured = {}

    class FakeNEB:
        def __init__(self, images, **kwargs):
            captured["energies"] = [images[0].get_potential_energy(), images[-1].get_potential_energy()]

    class FakeOptimizer:
        def __init__(self, neb, trajectory=None):
            return None

        def run(self, fmax=None, steps=None):
            return None

    monkeypatch.setattr(run_cli.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc())
    monkeypatch.setattr(run_cli, "AbacusNEB", FakeNEB)
    monkeypatch.setattr(run_cli, "get_optimizer", lambda name: FakeOptimizer)

    config = {
        "calculation": {"type": "neb", "init_chain": "chain.traj", "parallel": False},
        "calculator": {"name": "abacus", "abacus": {"directory": "run_neb", "parameters": {}}},
    }
    run_cli.run_neb(config, "abacus", config["calculation"])

    assert captured["energies"] == [4.0, 4.0]


def test_atst_run_show_irc_template_prints_yaml(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--show-template", "irc", "--calculator", "abacus"])

    output = capsys.readouterr().out
    assert "type: irc" in output
    assert "direction: both" in output


def test_neb_make_delegates_to_generate(monkeypatch):
    from atst_tools.scripts import cli

    calls = []
    monkeypatch.setattr(cli, "generate", lambda **kwargs: calls.append(kwargs))

    cli.main(["neb", "make", "init.stru", "final.stru", "8", "-o", "chain.traj", "--method", "linear"])

    assert calls == [
        {
            "method": "linear",
            "n_images": 8,
            "is_file": "init.stru",
            "fs_file": "final.stru",
            "output_file": "chain.traj",
            "format": None,
            "fix_height": None,
            "fix_dir": None,
            "mag_ele": None,
            "mag_num": None,
            "no_align": False,
            "ts_file": None,
        }
    ]


def test_neb_make_from_chain_writes_last_band(tmp_path, monkeypatch):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("guess.traj", [_atoms(float(i), float(i)) for i in range(5)])

    cli.main(["neb", "make", "init.stru", "final.stru", "1", "--from-chain", "guess.traj", "-o", "chain.traj"])

    frames = read("chain.traj", index=":")
    assert [atoms.get_potential_energy() for atoms in frames] == [2.0, 3.0, 4.0]


def test_neb_post_runs_barrier_ts_and_vibration_analysis(monkeypatch, capsys):
    from atst_tools.scripts import cli

    calls = []

    class FakeNEBPost:
        def __init__(self, images, n_max=0):
            self.neb_chain = images
            calls.append(("init", n_max))

        def get_barrier(self):
            calls.append(("barrier",))

        def get_TS_stru(self, name="TS_get"):
            calls.append(("ts", name))

        def plot_neb_bands(self):
            calls.append(("plot",))

        def write_latest_bands(self, outname="neb_latest"):
            calls.append(("latest", outname))

        def view_neb_bands(self, traj_file="neb.traj"):
            calls.append(("view", traj_file))

    monkeypatch.setattr(cli, "read", lambda filename, index=None: [_atoms(0.0), _atoms(1.0), _atoms(0.2)])
    monkeypatch.setattr(cli, "NEBPost", FakeNEBPost)
    monkeypatch.setattr(
        cli,
        "get_displacement_analysis",
        lambda chain, thr=0.10: (1, [0], np.array([1.0])),
    )

    cli.main(["neb", "post", "neb.traj", "--n-max", "1", "--plot", "--vib-analysis"])

    assert calls == [("init", 0), ("barrier",), ("ts", "TS_get"), ("plot",)]
    assert "Suggested Vibration Indices" in capsys.readouterr().out


def test_neb_post_writes_latest_and_init_chain(tmp_path, monkeypatch):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("neb.traj", [_atoms(0.0), _atoms(1.0), _atoms(0.2), _atoms(0.1), _atoms(2.0), _atoms(0.3)])
    monkeypatch.setattr(cli.NEBPost, "get_barrier", lambda self: None)
    monkeypatch.setattr(cli.NEBPost, "get_TS_stru", lambda self, name="TS_get": None)

    cli.main([
        "neb",
        "post",
        "neb.traj",
        "--n-max",
        "1",
        "--write-latest",
        "neb_latest",
        "--write-neb-init-chain",
        "restart.traj",
    ])

    assert Path("neb_latest.traj").exists()
    assert Path("neb_latest.extxyz").exists()
    assert len(read("restart.traj", index=":")) == 3


def test_traj_collect_and_transform_roundtrip(tmp_path, monkeypatch):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("a.traj", _atoms(0.0))
    write("b.traj", _atoms(1.0))

    cli.main(["traj", "collect", "b.traj", "a.traj", "-o", "collection.traj"])
    cli.main(["traj", "transform", "collection.traj", "--format", "extxyz", "--output-prefix", "converted"])

    assert [atoms.get_potential_energy() for atoms in read("collection.traj", index=":")] == [0.0, 1.0]
    assert Path("converted.extxyz").exists()


def test_dimer_make_from_neb_writes_ts_and_vector(tmp_path, monkeypatch):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    images = [_atoms(0.0, 0.0), _atoms(2.0, 0.5), _atoms(0.5, 2.0)]
    write("neb.traj", images)

    cli.main(["dimer", "make-from-neb", "neb.traj"])

    assert Path("dimer_init.traj").exists()
    vector = np.load("displacement_vector.npy")
    assert vector.shape == (1, 3)
    assert np.isclose(np.linalg.norm(vector), 0.01)


def test_dimer_make_from_neb_accepts_output_traj(tmp_path, monkeypatch):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    images = [_atoms(0.0, 0.0), _atoms(2.0, 0.5), _atoms(0.5, 2.0)]
    write("neb.traj", images)

    cli.main(["dimer", "make-from-neb", "neb.traj", "--output-traj", "ts_guess.traj"])

    assert Path("ts_guess.traj").exists()


def test_relax_post_writes_selected_frame(tmp_path, monkeypatch, capsys):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("relax.traj", [_atoms(0.0), _atoms(1.0)])

    cli.main(["relax", "post", "relax.traj", "--output-format", "traj", "--output", "restart.traj"])

    assert Path("restart.traj").exists()
    assert read("restart.traj").get_potential_energy() == 1.0
    output = capsys.readouterr().out
    assert "Energy:" in output
    assert "Max force:" in output


def test_relax_post_help_mentions_ts_restart(capsys):
    from atst_tools.scripts import cli

    try:
        cli.main(["relax", "post", "--help"])
    except SystemExit:
        pass

    assert "TS relax / Single-End Methods restart" in capsys.readouterr().out


def test_vibration_post_writes_results(monkeypatch, tmp_path):
    from atst_tools.scripts import cli

    class FakeVibrations:
        def __init__(self, atoms, indices=None, delta=None, nfree=None, name=None):
            return None

        def summary(self):
            return None

        def write_mode(self):
            return None

        def get_energies(self):
            return np.array([0.1, 0.2])

        def get_frequencies(self):
            return np.array([100.0, 200.0])

        def get_zero_point_energy(self):
            return 0.15

    config = {
        "calculation": {
            "type": "vibration",
            "init_structure": "ts.traj",
            "thermochemistry": {"temperature": 300.0},
        },
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(cli, "read_structure", lambda path: _atoms())
    monkeypatch.setattr(cli, "Vibrations", FakeVibrations)

    cli.main(["vibration", "post", "config.yaml"])

    results = json.loads(Path("vibration_results.json").read_text(encoding="utf-8"))
    assert results["thermo"]["model"] == "harmonic"
    assert results["thermo"]["zpe"] == 0.15


def test_vibration_post_rejects_invalid_cache(monkeypatch, tmp_path):
    from atst_tools.scripts import cli

    config = {
        "calculation": {
            "type": "vibration",
            "init_structure": "ts.traj",
            "name": "vib",
        },
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.chdir(tmp_path)
    Path("vib").mkdir()
    Path("vib/cache.0x+.json").touch()
    monkeypatch.setattr(cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(cli.ConfigLoader, "validate", lambda config: True)

    try:
        cli.main(["vibration", "post", "config.yaml"])
    except RuntimeError as exc:
        assert "Invalid vibration cache" in str(exc)
    else:
        raise AssertionError("expected invalid cache to raise")
