from pathlib import Path

import numpy as np
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import write


def _atoms(energy=0.0, x=0.0):
    atoms = Atoms("H", positions=[[x, 0.0, 0.0]])
    atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=np.zeros((1, 3)))
    return atoms


def test_only_git_style_console_script_is_exposed():
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'atst = "atst_tools.scripts.cli:main"' in text
    assert "atst-run" not in text
    assert "atst-neb-make" not in text
    assert "atst-neb-post" not in text


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
        "calculation": {"type": "d2s"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(run_cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(run_cli, "D2SWorkflow", FakeD2SWorkflow)

    cli.main(["run", "config.yaml"])

    assert calls == [("init", "abacus", "d2s"), ("run",)]


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


def test_atst_run_show_template_prints_yaml(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--show-template", "neb", "--calculator", "abacus"])

    output = capsys.readouterr().out
    assert "calculation:" in output
    assert "type: neb" in output
    assert "calculator:" in output


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
            "no_align": False,
        }
    ]


def test_neb_post_runs_barrier_ts_and_vibration_analysis(monkeypatch, capsys):
    from atst_tools.scripts import cli

    calls = []

    class FakeNEBPost:
        def __init__(self, images, n_max=0):
            self.neb_chain = images
            calls.append(("init", n_max))

        def get_barrier(self):
            calls.append(("barrier",))

        def get_TS_stru(self):
            calls.append(("ts",))

        def plot_neb_bands(self):
            calls.append(("plot",))

        def view_neb_bands(self):
            calls.append(("view",))

    monkeypatch.setattr(cli, "read", lambda filename, index=None: [_atoms(0.0), _atoms(1.0), _atoms(0.2)])
    monkeypatch.setattr(cli, "NEBPost", FakeNEBPost)
    monkeypatch.setattr(
        cli,
        "get_displacement_analysis",
        lambda chain, thr=0.10: (1, [0], np.array([1.0])),
    )

    cli.main(["neb", "post", "neb.traj", "--n-max", "1", "--plot", "--vib-analysis"])

    assert calls == [("init", 1), ("barrier",), ("ts",), ("plot",)]
    assert "Suggested Vibration Indices" in capsys.readouterr().out


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
            "temperature": 300.0,
        },
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(cli, "read_structure", lambda path: _atoms())
    monkeypatch.setattr(cli, "Vibrations", FakeVibrations)

    cli.main(["vibration", "post", "config.yaml"])

    assert Path("vibration_results.json").exists()
