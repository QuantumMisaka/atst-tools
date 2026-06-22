from pathlib import Path
import json
import re

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write

from atst_tools.external.ASE_interface.abacuslite.io.generalio import write_stru


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


def test_legacy_neb_script_modules_are_not_packaged_entries():
    script_dir = Path("src/atst_tools/scripts")

    assert not (script_dir / "neb_make.py").exists()
    assert not (script_dir / "neb_post.py").exists()


def test_active_docs_do_not_present_legacy_neb_modules_as_current_entrypoints():
    active_docs = [
        *Path("docs/user").glob("*.md"),
        *Path("docs/developer").glob("*.md"),
        Path("README.md"),
        Path("docs/index.md"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in active_docs)

    assert "python src/atst_tools/scripts/neb_make.py" not in text
    assert "python src/atst_tools/scripts/neb_post.py" not in text
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


def test_d2s_rough_method_dmf_is_constructible():
    from atst_tools.workflows.d2s import D2SWorkflow

    config = {
        "calculation": {
            "type": "d2s",
            "rough_method": "dmf",
            "init_file": "init.stru",
            "final_file": "final.stru",
        },
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    workflow = D2SWorkflow(config, "abacus", config["calculation"])

    assert workflow.rough_method == "dmf"


def test_atst_run_dispatches_dmf(monkeypatch):
    from atst_tools.scripts import main as run_cli
    from atst_tools.scripts import cli

    calls = []

    class FakeDMFWorkflow:
        def __init__(self, config, calc_name, calc_config):
            calls.append(("init", calc_name, calc_config["type"]))

        def run(self):
            calls.append(("run",))

    config = {
        "calculation": {"type": "dmf", "init_file": "init.xyz", "final_file": "final.xyz"},
        "calculator": {"name": "dp", "dp": {"model": "model.pb"}},
    }

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(run_cli.ConfigLoader, "normalize", lambda config: config)
    monkeypatch.setattr(run_cli, "DMFWorkflow", FakeDMFWorkflow)

    cli.main(["run", "config.yaml"])

    assert calls == [("init", "dp", "dmf"), ("run",)]


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


def test_atst_run_dry_run_check_input_calls_abacus_preflight(monkeypatch, caplog):
    from atst_tools.scripts import main as run_cli
    from atst_tools.scripts import cli

    caplog.set_level("INFO")
    config = {
        "calculation": {"type": "relax", "init_structure": "init.stru"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }
    calls = []

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(
        run_cli,
        "run_abacus_check_input_dry_run",
        lambda config, config_path, timeout_sec=120, abacus_executable="abacus": calls.append(
            (config, config_path, timeout_sec, abacus_executable)
        )
        or {"checked": 1, "workdirs": ["tmp"]},
    )

    cli.main(
        [
            "run",
            "--dry-run",
            "--check-input",
            "--check-input-timeout",
            "7",
            "--abacus-executable",
            "abacus-lts",
            "config.yaml",
        ]
    )

    assert len(calls) == 1
    called_config, called_path, called_timeout, called_executable = calls[0]
    assert called_config["calculation"]["type"] == "relax"
    assert called_config["calculation"]["init_structure"] == "init.stru"
    assert called_config["calculator"]["name"] == "abacus"
    assert called_path == "config.yaml"
    assert called_timeout == 7
    assert called_executable == "abacus-lts"
    assert "ABACUS check-input preflight passed" in caplog.text


def test_atst_run_check_input_requires_dry_run(monkeypatch):
    from atst_tools.scripts import cli

    with pytest.raises(SystemExit, match="--check-input requires --dry-run"):
        cli.main(["run", "--check-input", "config.yaml"])


def test_atst_run_dry_run_check_input_skips_non_abacus(monkeypatch, caplog):
    from atst_tools.scripts import main as run_cli
    from atst_tools.scripts import cli

    caplog.set_level("INFO")
    config = {
        "calculation": {"type": "relax", "init_structure": "init.stru"},
        "calculator": {"name": "dp", "dp": {"model": "model.pt"}},
    }

    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(
        run_cli,
        "run_abacus_check_input_dry_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DP dry-run must not call ABACUS preflight")),
    )

    cli.main(["run", "--dry-run", "--check-input", "config.yaml"])

    assert "skipped" in caplog.text


def test_atst_run_list_types_prints_supported_types(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--list-types"])

    output = capsys.readouterr().out
    assert "neb" in output
    assert "vibration" in output
    assert "irc" in output
    assert "md" in output
    assert "dmf" in output


def test_atst_run_show_template_prints_yaml(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--show-template", "neb", "--calculator", "abacus"])

    output = capsys.readouterr().out
    assert "calculation:" in output
    assert "type: neb" in output
    assert "make:" in output
    assert "two_stage: true" in output
    assert "stage1_steps: 20" in output
    assert "stage1_fmax: 0.2" in output
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


def test_atst_run_show_md_template_prints_yaml(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--show-template", "md", "--calculator", "abacus"])

    output = capsys.readouterr().out
    assert "type: md" in output
    assert "driver: ase" in output
    assert "algorithm: bussi" in output
    assert "driver: abacus_native" in output


def test_atst_run_show_dmf_template_prints_experimental_pbc_warning(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--show-template", "dmf", "--calculator", "dp"])

    output = capsys.readouterr().out
    assert "type: dmf" in output
    assert "experimental" in output
    assert "pbc_mode: reject" in output
    assert "cartesian_unwrapped" in output


def test_atst_md_summary_prints_trajectory_summary(tmp_path, capsys):
    from ase import Atoms
    from ase.calculators.singlepoint import SinglePointCalculator
    from ase.io import write
    from atst_tools.scripts import cli

    atoms = Atoms("H", positions=[[0, 0, 0]], cell=[5, 5, 5], pbc=True)
    atoms.calc = SinglePointCalculator(atoms, energy=-1.0, forces=[[0.1, 0.0, 0.0]])
    traj = tmp_path / "md.traj"
    write(traj, [atoms])

    cli.main(["md", "summary", str(traj), "--format", "json"])

    output = capsys.readouterr().out
    assert '"workflow": "md"' in output
    assert '"n_frames": 1' in output


def test_atst_md_post_writes_summary_and_converted_trajectory(tmp_path):
    from ase import Atoms
    from ase.io import read, write
    from atst_tools.scripts import cli

    traj = tmp_path / "md.traj"
    write(traj, [Atoms("H", positions=[[0, 0, 0]])])

    cli.main(
        [
            "md",
            "post",
            str(traj),
            "--output-prefix",
            str(tmp_path / "converted"),
            "--summary-output",
            str(tmp_path / "summary.json"),
        ]
    )

    assert (tmp_path / "summary.json").exists()
    assert len(read(tmp_path / "converted.extxyz", index=":")) == 1


def test_atst_run_show_ccqn_template_prints_yaml(capsys):
    from atst_tools.scripts import cli

    cli.main(["run", "--show-template", "ccqn", "--calculator", "abacus"])

    output = capsys.readouterr().out
    assert "type: ccqn" in output
    assert "e_vector_method: ic" in output
    assert "reactive_bonds" in output


def test_config_validate_prints_normalized_yaml(tmp_path, capsys):
    from atst_tools.scripts import cli

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
calculation:
  type: relax
  init_structure: init.stru
calculator:
  name: abacus
  abacus:
    parameters:
      calculation: scf
""",
        encoding="utf-8",
    )

    cli.main(["config", "validate", str(config_file), "--print-normalized"])

    output = capsys.readouterr().out
    assert "config_version" not in output
    assert "trajectory: relax.traj" in output


def test_abacus_prepare_writes_input_kpt_and_stru(tmp_path, capsys):
    from atst_tools.scripts import cli

    structure = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[8.0, 8.0, 8.0], pbc=True)
    structure_file = tmp_path / "h.xyz"
    write(structure_file, structure)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
calculation:
  type: relax
  init_structure: h.xyz
calculator:
  name: abacus
  abacus:
    kpts: [1, 1, 1]
    parameters:
      calculation: scf
      basis_type: lcao
      pseudo_dir: ./data
      orbital_dir: ./data
      pseudopotentials:
        H: H.upf
      basissets:
        H: H.orb
""",
        encoding="utf-8",
    )
    output_dir = tmp_path / "abacus_input"

    cli.main(["abacus", "prepare", str(config_file), "--structure", str(structure_file), "--output-dir", str(output_dir)])

    assert (output_dir / "INPUT").read_text(encoding="utf-8").startswith("INPUT_PARAMETERS")
    assert "calculation scf" in (output_dir / "INPUT").read_text(encoding="utf-8")
    assert "K_POINTS" in (output_dir / "KPT").read_text(encoding="utf-8")
    assert "ATOMIC_SPECIES" in (output_dir / "STRU").read_text(encoding="utf-8")
    assert "Wrote ABACUS input files" in capsys.readouterr().out


def test_abacus_collect_writes_read_only_summary(tmp_path):
    from atst_tools.scripts import cli

    run_dir = tmp_path / "run"
    out_dir = run_dir / "OUT.ABACUS"
    out_dir.mkdir(parents=True)
    (run_dir / "INPUT").write_text("INPUT_PARAMETERS\ncalculation scf\n", encoding="utf-8")
    (run_dir / "KPT").write_text("K_POINTS\n", encoding="utf-8")
    (run_dir / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")
    (out_dir / "running_scf.log").write_text("mock log\n", encoding="utf-8")
    output = tmp_path / "summary.json"

    cli.main(["abacus", "collect", str(run_dir), "--output", str(output)])

    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["parsed"] is False
    assert summary["files"]["INPUT"] is True
    assert summary["logs"] == ["OUT.ABACUS/running_scf.log"]


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


def test_neb_make_accepts_stru_input_with_fix_and_mag(tmp_path):
    from atst_tools.scripts import cli

    start = Atoms(
        ["H", "He"],
        scaled_positions=[[0.0, 0.0, 0.1], [0.0, 0.0, 0.8]],
        cell=[5.0, 5.0, 5.0],
        pbc=True,
    )
    end = start.copy()
    end.positions += [[0.5, 0.0, 0.0], [0.0, 0.5, 0.0]]
    init_stru = tmp_path / "init.stru"
    final_stru = tmp_path / "final.stru"
    output = tmp_path / "chain.traj"
    pp_files = {"H": "H.upf", "He": "He.upf"}
    orb_files = {"H": "H.orb", "He": "He.orb"}
    write_stru(start, str(tmp_path), pp_files, orb_files, fname=init_stru.name)
    write_stru(end, str(tmp_path), pp_files, orb_files, fname=final_stru.name)

    cli.main(
        [
            "neb",
            "make",
            str(init_stru),
            str(final_stru),
            "1",
            "--method",
            "linear",
            "--fix",
            "0.25:2",
            "--mag",
            "H:1.0",
            "-o",
            str(output),
        ]
    )

    frames = read(output, index=":")
    assert len(frames) == 3
    assert frames[1].constraints
    np.testing.assert_allclose(frames[1].get_initial_magnetic_moments(), [1.0, 0.0])


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

        def plot_neb_bands(self, label="nebplots_chain"):
            calls.append(("plot", label))

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

    assert calls == [("init", 0), ("barrier",), ("ts", "TS_get"), ("plot", "nebplots_chain")]
    assert "Suggested Vibration Indices" in capsys.readouterr().out


def test_neb_post_prints_energy_profile_and_uses_plot_label(monkeypatch, capsys):
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

        def plot_neb_bands(self, label="nebplots_chain"):
            calls.append(("plot", label))

        def energy_profile(self):
            calls.append(("energy_profile",))
            return [
                {"image": 0, "energy_eV": 2.0, "rel_energy_eV": 0.0, "max_force_eV_per_A": 0.0},
                {"image": 1, "energy_eV": 3.0, "rel_energy_eV": 1.0, "max_force_eV_per_A": 0.2},
            ]

    monkeypatch.setattr(cli, "read", lambda filename, index=None: [_atoms(0.0), _atoms(1.0)])
    monkeypatch.setattr(cli, "NEBPost", FakeNEBPost)

    cli.main([
        "neb",
        "post",
        "neb.traj",
        "--n-max",
        "0",
        "--plot",
        "--plot-label",
        "custom_nebplot",
        "--energy-profile",
    ])

    output = capsys.readouterr().out
    assert calls == [
        ("init", 0),
        ("barrier",),
        ("ts", "TS_get"),
        ("plot", "custom_nebplot"),
        ("energy_profile",),
    ]
    assert "=== NEB Energy Profile ===" in output
    assert "image energy_eV rel_energy_eV max_force_eV_per_A" in output
    assert "   1     3.000000     1.000000           0.200000" in output


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


def test_neb_post_plot_all_handles_equal_endpoint_band(tmp_path, monkeypatch, capsys):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("neb.traj", [_atoms(0.0, 0.0), _atoms(1.0, 1.0), _atoms(0.0, 2.0)])
    monkeypatch.setattr(cli.NEBPost, "get_TS_stru", lambda self, name="TS_get": None)

    cli.main(["neb", "post", "neb.traj", "--plot-all"])

    output = capsys.readouterr().out
    assert "Reaction Barrier and Energy Difference" in output
    assert "Warning: Failed to plot all bands" not in output


def test_neb_summary_prints_table_and_writes_json(tmp_path, monkeypatch, capsys):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("neb.traj", [_atoms(0.0), _atoms(1.0), _atoms(0.0), _atoms(0.0), _atoms(0.4), _atoms(0.1)])

    cli.main(["neb", "summary", "neb.traj", "--n-max", "1", "--output", "summary.json"])

    output = capsys.readouterr().out
    assert "NEB trajectory summary" in output
    assert "max_force_image" in output
    data = json.loads(Path("summary.json").read_text(encoding="utf-8"))
    assert data["workflow"] == "neb"
    assert data["latest"]["barrier_eV"] == pytest.approx(0.4)


def test_neb_summary_supports_json_stdout(tmp_path, monkeypatch, capsys):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("neb.traj", [_atoms(0.0), _atoms(1.0), _atoms(0.0)])

    cli.main(["neb", "summary", "neb.traj", "--n-max", "1", "--format", "json"])

    data = json.loads(capsys.readouterr().out)
    assert data["status"]["complete_steps"] == 1


def test_relax_summary_prints_latest_frame(tmp_path, monkeypatch, capsys):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("relax.traj", [_atoms(-1.0), _atoms(-2.0)])

    cli.main(["relax", "summary", "relax.traj"])

    output = capsys.readouterr().out
    assert "relax trajectory summary" in output
    assert "latest_energy_eV" in output


def test_dimer_sella_ccqn_summary_share_trajectory_summary(tmp_path, monkeypatch, capsys):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("ts.traj", [_atoms(-1.0), _atoms(-1.2)])

    for command in ("dimer", "sella", "ccqn"):
        cli.main([command, "summary", "ts.traj", "--tail", "1"])
        assert f"{command} trajectory summary" in capsys.readouterr().out


def test_vibration_summary_reports_invalid_cache(tmp_path, monkeypatch, capsys):
    from atst_tools.scripts import cli

    monkeypatch.chdir(tmp_path)
    write("init.traj", _atoms())
    Path("vib").mkdir()
    Path("vib/cache.eq.json").write_text("{}", encoding="utf-8")
    Path("vib/cache.0x+.json").write_text("{bad json", encoding="utf-8")
    Path("config.yaml").write_text(
        """
calculation:
  type: vibration
  init_structure: init.traj
  name: vib
calculator:
  name: abacus
  abacus:
    parameters: {}
""",
        encoding="utf-8",
    )

    cli.main(["vibration", "summary", "config.yaml"])

    output = capsys.readouterr().out
    assert "vibration summary" in output
    assert "invalid_cache_files" in output


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
