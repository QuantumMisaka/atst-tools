import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.io import read, write


class DummyCalc(Calculator):
    implemented_properties = ["energy", "forces", "stress"]

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.results["energy"] = 1.5
        self.results["forces"] = np.zeros((len(atoms), 3))
        self.results["stress"] = np.zeros(6)


def test_ase_md_workflow_writes_trajectory_summary_and_manifest(monkeypatch, tmp_path):
    from atst_tools.workflows import md

    monkeypatch.chdir(tmp_path)
    write("init.traj", Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.75, 0.0, 0.0]], cell=[8, 8, 8], pbc=True))
    monkeypatch.setattr(md.CalculatorFactory, "get_calculator", lambda *args, **kwargs: DummyCalc())

    workflow = md.MDWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {
            "type": "md",
            "driver": "ase",
            "ensemble": "nve",
            "algorithm": "velocityverlet",
            "init_structure": "init.traj",
            "steps": 3,
            "temperature_K": 300.0,
            "seed": 7,
            "trajectory": "md.traj",
            "logfile": "md.log",
            "summary_file": "md_summary.json",
            "artifact_manifest": "atst_artifacts.json",
        },
    )
    workflow.run()

    frames = read("md.traj", index=":")
    summary = json.loads(Path("md_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path("atst_artifacts.json").read_text(encoding="utf-8"))

    assert len(frames) >= 1
    assert summary["workflow"] == "md"
    assert summary["driver"] == "ase"
    assert summary["algorithm"] == "velocityverlet"
    assert summary["steps"] == 3
    assert summary["final_energy_eV"] == pytest.approx(1.5)
    assert Path("md_post_summary.json").exists()
    assert manifest["workflow"] == "md"
    assert {artifact["role"] for artifact in manifest["artifacts"]} >= {"trajectory", "summary", "postprocess_summary"}


def test_abacus_native_md_rejects_non_abacus_calculator(tmp_path):
    from atst_tools.workflows.md import MDWorkflow

    workflow = MDWorkflow(
        {"calculator": {"name": "dp", "dp": {"model": "model.pb"}}},
        "dp",
        {
            "type": "md",
            "driver": "abacus_native",
            "init_structure": str(tmp_path / "init.traj"),
            "steps": 2,
        },
    )

    with pytest.raises(ValueError, match="abacus_native"):
        workflow.run()


def test_abacus_native_md_prepares_inputs_runs_process_and_collects(monkeypatch, tmp_path):
    from atst_tools.workflows import md

    init = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[5, 5, 5], pbc=True)
    write(tmp_path / "init.traj", init)
    fixture_dir = Path("src/atst_tools/external/ASE_interface/abacuslite/io/testfiles").resolve()
    popen_calls = []

    class FakeProcess:
        returncode = None

        def __init__(self):
            self.polls = 0

        def poll(self):
            if self.polls == 0:
                self.polls += 1
                return None
            self.returncode = 0
            return self.returncode

        def communicate(self, timeout=None):
            run_dir = tmp_path / "native"
            shutil.copy2(fixture_dir / "pw-symm0-nspin4-gamma-md", run_dir / "running_md.log")
            shutil.copy2(fixture_dir / "nspin4-gamma-mddump", run_dir / "MD_dump")
            shutil.copy2(fixture_dir / "nspin4-gamma-eigocc", run_dir / "eig_occ.txt")
            return "", ""

    def fake_popen(command, cwd=None, stdout=None, stderr=None, text=None):
        popen_calls.append((command, cwd, stdout.name, stderr.name, text))
        return FakeProcess()

    monkeypatch.setattr(md.subprocess, "Popen", fake_popen)

    workflow = md.MDWorkflow(
        {
            "calculator": {
                "name": "abacus",
                "abacus": {
                    "command": "abacus",
                    "mpi": 1,
                    "directory": str(tmp_path / "native"),
                    "kpts": [1, 1, 1],
                    "parameters": {
                        "calculation": "md",
                        "basis_type": "lcao",
                        "pseudo_dir": ".",
                        "orbital_dir": ".",
                        "pseudopotentials": {"H": "H.upf"},
                        "basissets": {"H": "H.orb"},
                    },
                },
            }
        },
        "abacus",
        {
            "type": "md",
            "driver": "abacus_native",
            "init_structure": str(tmp_path / "init.traj"),
            "steps": 2,
            "directory": str(tmp_path / "native"),
            "trajectory": str(tmp_path / "native" / "native_md.traj"),
            "summary_file": str(tmp_path / "native" / "md_summary.json"),
            "artifact_manifest": str(tmp_path / "native" / "atst_artifacts.json"),
            "poll_interval_seconds": 0.0,
            "postprocess": {
                "summary": {"enabled": True, "output": str(tmp_path / "native" / "md_post_summary.json")},
                "convert": {"enabled": True, "format": "extxyz", "output_prefix": str(tmp_path / "native" / "md_post")},
            },
        },
    )
    workflow.run()

    run_dir = tmp_path / "native"
    summary = json.loads((run_dir / "md_summary.json").read_text(encoding="utf-8"))
    progress = json.loads((run_dir / "md_progress.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "atst_artifacts.json").read_text(encoding="utf-8"))
    frames = read(run_dir / "native_md.traj", index=":")

    assert (run_dir / "INPUT").exists()
    assert (run_dir / "KPT").exists()
    assert (run_dir / "STRU").exists()
    assert popen_calls and popen_calls[0][1] == str(run_dir)
    assert summary["driver"] == "abacus_native"
    assert summary["returncode"] == 0
    assert summary["frames"] == 2
    assert progress["frames"] == 2
    assert progress["returncode"] == 0
    assert manifest["stages"][0]["status"] == "complete"
    assert {artifact["role"] for artifact in manifest["artifacts"]} >= {
        "progress",
        "abacus_stdout",
        "postprocess_summary",
        "postprocess_conversion",
    }
    assert (run_dir / "md_post_summary.json").exists()
    assert (run_dir / "md_post.extxyz").exists()
    assert len(frames) == 2


def test_abacus_native_md_records_failed_process(monkeypatch, tmp_path):
    from atst_tools.workflows import md

    write(tmp_path / "init.traj", Atoms("H", positions=[[0, 0, 0]], cell=[5, 5, 5], pbc=True))

    class FakeProcess:
        returncode = 9

        def communicate(self, timeout=None):
            return "", ""

    monkeypatch.setattr(md.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    workflow = md.MDWorkflow(
        {
            "calculator": {
                "name": "abacus",
                "abacus": {
                    "command": "abacus",
                    "parameters": {"calculation": "md", "pseudopotentials": {"H": "H.upf"}, "basissets": {"H": "H.orb"}},
                },
            }
        },
        "abacus",
        {
            "type": "md",
            "driver": "abacus_native",
            "init_structure": str(tmp_path / "init.traj"),
            "steps": 1,
            "directory": str(tmp_path / "native_fail"),
            "summary_file": str(tmp_path / "native_fail" / "md_summary.json"),
            "artifact_manifest": str(tmp_path / "native_fail" / "atst_artifacts.json"),
            "poll_interval_seconds": 0.0,
        },
    )

    with pytest.raises(RuntimeError, match="ABACUS native MD failed"):
        workflow.run()

    summary = json.loads((tmp_path / "native_fail" / "md_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "native_fail" / "atst_artifacts.json").read_text(encoding="utf-8"))
    assert summary["returncode"] == 9
    assert manifest["stages"][0]["status"] == "failed"
