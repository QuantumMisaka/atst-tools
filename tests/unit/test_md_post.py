import json
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import read, write


def _atoms(energy=None, force=0.0, momenta=False):
    atoms = Atoms("H2", positions=[[0, 0, 0], [0.75, 0, 0]], cell=[8, 8, 8], pbc=True)
    if momenta:
        atoms.set_momenta([[0.1, 0.0, 0.0], [-0.1, 0.0, 0.0]])
    if energy is not None:
        atoms.calc = SinglePointCalculator(
            atoms,
            energy=energy,
            forces=np.full((len(atoms), 3), force),
        )
    return atoms


def test_summarize_md_trajectory_reports_energy_temperature_force_and_tail(tmp_path):
    from atst_tools.utils.md_post import summarize_md_trajectory

    traj = tmp_path / "md.traj"
    write(traj, [_atoms(-1.0, 0.1, momenta=True), _atoms(-1.5, 0.2, momenta=True)])

    summary = summarize_md_trajectory(traj, tail=1, metadata={"driver": "ase"})

    assert summary["workflow"] == "md"
    assert summary["status"]["n_frames"] == 2
    assert summary["latest"]["step"] == 1
    assert summary["latest"]["energy_eV"] == pytest.approx(-1.5)
    assert summary["latest"]["max_force_eV_per_A"] == pytest.approx(np.linalg.norm([0.2, 0.2, 0.2]))
    assert summary["latest"]["temperature_K"] > 0
    assert summary["metadata"]["driver"] == "ase"
    assert [frame["step"] for frame in summary["frames"]] == [1]


def test_summarize_md_trajectory_handles_missing_results(tmp_path):
    from atst_tools.utils.md_post import summarize_md_trajectory

    traj = tmp_path / "md.traj"
    write(traj, [_atoms()])

    summary = summarize_md_trajectory(traj)
    latest = summary["latest"]

    assert np.isnan(latest["energy_eV"])
    assert np.isnan(latest["max_force_eV_per_A"])
    assert np.isnan(latest["temperature_K"])


def test_post_md_trajectory_writes_summary_and_default_extxyz(tmp_path):
    from atst_tools.utils.md_post import post_md_trajectory

    traj = tmp_path / "md.traj"
    write(traj, [_atoms(-1.0, 0.1), _atoms(-1.5, 0.2)])

    result = post_md_trajectory(
        traj,
        output_prefix=tmp_path / "md_post",
        summary_output=tmp_path / "md_post_summary.json",
    )

    assert (tmp_path / "md_post.extxyz").exists()
    assert len(read(tmp_path / "md_post.extxyz", index=":")) == 2
    summary = json.loads((tmp_path / "md_post_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow"] == "md"
    assert result["converted"]["path"] == str(tmp_path / "md_post.extxyz")


def test_post_md_trajectory_supports_frame_and_stride(tmp_path):
    from atst_tools.utils.md_post import post_md_trajectory

    traj = tmp_path / "md.traj"
    write(traj, [_atoms(-1.0), _atoms(-1.1), _atoms(-1.2), _atoms(-1.3)])

    frame_result = post_md_trajectory(
        traj,
        output_prefix=tmp_path / "last",
        output_format="xyz",
        summary_output=tmp_path / "last_summary.json",
        frame=-1,
    )
    stride_result = post_md_trajectory(
        traj,
        output_prefix=tmp_path / "stride",
        output_format="extxyz",
        summary_output=tmp_path / "stride_summary.json",
        stride=2,
    )

    assert len(read(frame_result["converted"]["path"], index=":")) == 1
    assert len(read(stride_result["converted"]["path"], index=":")) == 2
    assert (tmp_path / "last_summary.json").exists()
    assert (tmp_path / "stride_summary.json").exists()
    assert not Path("md_post_summary.json").exists()
