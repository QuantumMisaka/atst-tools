"""Tests for the dual-entry visualization module ``atst_tools.utils.plot``.

Covers the NEB/AutoNEB energy profile and the Sella/CCQN convergence curve
helpers, the module CLI (``python -m atst_tools.utils.plot``), and the
guarantee that the CLI and the Python API render identical figures from the
same implementation.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

import atst_tools.utils.plot as plot
from ase import Atoms
from ase.io import Trajectory
from helpers import make_atoms

ROOT = Path(__file__).resolve().parents[2]
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class _RecordingAxes:
    """Record the drawing calls made through the matplotlib axes surface."""

    def __init__(self):
        self.plot_calls = []
        self.annotate_calls = []
        self.xlabel = None
        self.ylabel = None
        self.title = None

    def plot(self, *args, **kwargs):
        self.plot_calls.append((args, kwargs))
        return []

    def annotate(self, *args, **kwargs):
        self.annotate_calls.append((args, kwargs))

    def set_xlabel(self, value):
        self.xlabel = value

    def set_ylabel(self, value):
        self.ylabel = value

    def set_title(self, value):
        self.title = value

    def grid(self, *args, **kwargs):
        return None


class _RecordingFigure:
    def __init__(self):
        self.axes = _RecordingAxes()
        self.savefig_calls = []
        self.closed = False

    def savefig(self, *args, **kwargs):
        self.savefig_calls.append((args, kwargs))

    def close(self):
        self.closed = True


class _RecordingPyplot:
    def __init__(self):
        self.figures = []

    def subplots(self):
        figure = _RecordingFigure()
        self.figures.append(figure)
        return figure, figure.axes

    def close(self, figure):
        figure.closed = True


@pytest.fixture
def recording_pyplot(monkeypatch):
    fake = _RecordingPyplot()
    monkeypatch.setattr(plot, "_pyplot", lambda: fake)
    return fake


def _chain(energies):
    return [make_atoms(symbols="H", energy=energy) for energy in energies]


def _write_trajectory(path, energies):
    frames = _chain(energies)
    with Trajectory(path, "w") as traj:
        for frame in frames:
            traj.write(frame)
    return frames


def _valid_png(path):
    data = Path(path).read_bytes()
    return data.startswith(PNG_MAGIC) and len(data) > 1000


def _png_identical(first, second):
    import matplotlib.image as mpimg

    return np.array_equal(
        np.asarray(mpimg.imread(first)), np.asarray(mpimg.imread(second))
    )


def test_neb_energy_profile_plots_relative_energies_and_barrier(
    recording_pyplot, tmp_path
):
    output = tmp_path / "profile.png"

    result = plot.neb_energy_profile(_chain([0.0, 1.0, 3.0, 1.0]), output, dpi=120)

    assert result == Path(output)
    figure = recording_pyplot.figures[0]
    axes = figure.axes
    assert axes.plot_calls[0][0][0] == [0, 1, 2, 3]
    assert axes.plot_calls[0][0][1] == [0.0, 1.0, 3.0, 1.0]
    text = axes.annotate_calls[0][0][0]
    assert "3.000" in text
    assert "barrier" in text.lower()
    assert axes.xlabel == "NEB image index"
    assert axes.ylabel == "Relative energy (eV)"
    assert figure.savefig_calls[0][0] == (output,)
    assert figure.savefig_calls[0][1]["dpi"] == 120
    assert figure.closed is True


def test_neb_energy_profile_skips_barrier_annotation_when_disabled(
    recording_pyplot, tmp_path
):
    output = tmp_path / "profile.png"

    plot.neb_energy_profile(_chain([0.0, 1.0, 3.0]), output, barrier=False)

    assert recording_pyplot.figures[0].axes.annotate_calls == []


def test_sella_energy_curve_plots_energy_vs_step(recording_pyplot, tmp_path):
    traj = tmp_path / "sella.traj"
    _write_trajectory(traj, [0.5, 0.3, 0.2, 0.15])
    output = tmp_path / "sella.png"

    result = plot.sella_energy_curve(traj, output, dpi=100)

    assert result == Path(output)
    axes = recording_pyplot.figures[0].axes
    assert axes.plot_calls[0][0][0] == [0, 1, 2, 3]
    assert axes.plot_calls[0][0][1] == [0.5, 0.3, 0.2, 0.15]
    assert axes.xlabel == "Step"
    assert axes.ylabel == "Energy (eV)"
    assert axes.title == "Sella convergence (E vs step)"
    assert recording_pyplot.figures[0].savefig_calls[0][1]["dpi"] == 100


def test_ccqn_energy_curve_plots_energy_vs_step(recording_pyplot, tmp_path):
    traj = tmp_path / "ccqn.traj"
    _write_trajectory(traj, [0.8, 0.6, 0.55, 0.52])
    output = tmp_path / "ccqn.png"

    result = plot.ccqn_energy_curve(traj, output, dpi=100)

    assert result == Path(output)
    axes = recording_pyplot.figures[0].axes
    assert axes.plot_calls[0][0][0] == [0, 1, 2, 3]
    assert axes.plot_calls[0][0][1] == [0.8, 0.6, 0.55, 0.52]
    assert axes.xlabel == "Step"
    assert axes.title == "CCQN convergence (E vs step)"


def test_neb_energies_match_input_without_new_calculation():
    energies = [0.0, 0.5, 1.0, 0.4]
    assert plot._neb_energies(_chain(energies)) == energies


def test_trajectory_energies_follow_frame_order(tmp_path):
    traj = tmp_path / "curve.traj"
    _write_trajectory(traj, [0.5, 0.3, 0.2, 0.15])
    assert plot._trajectory_energies(traj) == [0.5, 0.3, 0.2, 0.15]


def test_energy_falls_back_to_info_when_calculator_absent(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    atoms.info["energy"] = -2.5
    assert plot._neb_energies([atoms]) == [-2.5]


def test_missing_energy_raises_clear_value_error(tmp_path):
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="image 0"):
        plot.neb_energy_profile([atoms], tmp_path / "x.png")


def test_png_outputs_are_valid_images(tmp_path):
    import matplotlib.image as mpimg

    neb_png = tmp_path / "neb.png"
    plot.neb_energy_profile(_chain([0.0, 1.0, 3.0, 1.0]), neb_png)
    assert _valid_png(neb_png)
    assert np.asarray(mpimg.imread(neb_png)).ndim == 3

    traj = tmp_path / "curve.traj"
    _write_trajectory(traj, [0.5, 0.3, 0.2, 0.15])
    for function in (plot.sella_energy_curve, plot.ccqn_energy_curve):
        curve_png = tmp_path / f"{function.__name__}.png"
        function(traj, curve_png)
        assert _valid_png(curve_png)


def test_cli_and_api_neb_produce_identical_png(tmp_path):
    chain_path = tmp_path / "chain.traj"
    _write_trajectory(chain_path, [0.0, 0.5, 1.0, 0.4])
    cli_png = tmp_path / "cli.png"
    api_png = tmp_path / "api.png"

    assert (
        plot.main(
            [
                "neb",
                "--chain",
                str(chain_path),
                "--output-png",
                str(cli_png),
                "--dpi",
                "120",
            ]
        )
        == 0
    )
    plot.neb_energy_profile(_chain([0.0, 0.5, 1.0, 0.4]), api_png, dpi=120)

    assert _png_identical(cli_png, api_png)


@pytest.mark.parametrize(
    "kind,function",
    [("sella", plot.sella_energy_curve), ("ccqn", plot.ccqn_energy_curve)],
)
def test_cli_and_api_curve_produce_identical_png(tmp_path, kind, function):
    traj = tmp_path / f"{kind}.traj"
    _write_trajectory(traj, [0.5, 0.3, 0.2, 0.15])
    cli_png = tmp_path / f"cli_{kind}.png"
    api_png = tmp_path / f"api_{kind}.png"

    assert (
        plot.main(
            [
                kind,
                "--traj",
                str(traj),
                "--output-png",
                str(cli_png),
                "--dpi",
                "120",
            ]
        )
        == 0
    )
    function(traj, api_png, dpi=120)

    assert _png_identical(cli_png, api_png)


def test_cli_flags_map_one_to_one_to_api_parameters(recording_pyplot, tmp_path):
    chain_path = tmp_path / "chain.traj"
    _write_trajectory(chain_path, [0.0, 1.0, 3.0, 1.0])
    output = tmp_path / "mapped.png"

    code = plot.main(
        [
            "neb",
            "--chain",
            str(chain_path),
            "--output-png",
            str(output),
            "--title",
            "custom title",
            "--dpi",
            "90",
            "--no-barrier",
        ]
    )

    assert code == 0
    axes = recording_pyplot.figures[0].axes
    assert axes.title == "custom title"
    assert axes.annotate_calls == []
    assert recording_pyplot.figures[0].savefig_calls[0][1]["dpi"] == 90


def test_cli_uses_kind_specific_default_output(monkeypatch, tmp_path):
    chain_path = tmp_path / "chain.traj"
    _write_trajectory(chain_path, [0.0, 1.0])
    monkeypatch.chdir(tmp_path)

    assert plot.main(["neb", "--chain", str(chain_path)]) == 0
    assert (tmp_path / "neb_energy_profile.png").exists()


def test_python_dash_m_plot_entrypoint_writes_png(tmp_path):
    chain_path = tmp_path / "chain.traj"
    _write_trajectory(chain_path, [0.0, 1.0, 2.0, 1.0])
    output = tmp_path / "module.png"
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "atst_tools.utils.plot",
            "neb",
            "--chain",
            str(chain_path),
            "--output-png",
            str(output),
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert str(output) in completed.stdout
    assert _valid_png(output)


def test_api_raises_clear_error_when_matplotlib_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "matplotlib", None)

    with pytest.raises(ImportError, match="matplotlib"):
        plot.neb_energy_profile(_chain([0.0, 1.0]), tmp_path / "x.png")


def test_cli_reports_missing_matplotlib_gracefully(monkeypatch, tmp_path, capsys):
    chain_path = tmp_path / "chain.traj"
    _write_trajectory(chain_path, [0.0, 1.0])
    monkeypatch.setitem(sys.modules, "matplotlib", None)

    code = plot.main(
        ["neb", "--chain", str(chain_path), "--output-png", str(tmp_path / "x.png")]
    )

    assert code == 1
    assert "matplotlib" in capsys.readouterr().err


def test_importing_public_api_does_not_require_matplotlib(monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)

    import atst_tools.api as api

    assert api.neb_energy_profile is plot.neb_energy_profile
    assert api.sella_energy_curve is plot.sella_energy_curve
    assert api.ccqn_energy_curve is plot.ccqn_energy_curve
    for name in ("neb_energy_profile", "sella_energy_curve", "ccqn_energy_curve"):
        assert name in api.__all__


def test_neb_chain_must_be_atoms_sequence_not_path(tmp_path):
    with pytest.raises(TypeError, match="sequence of ASE Atoms"):
        plot.neb_energy_profile(str(tmp_path / "chain.traj"), tmp_path / "x.png")
