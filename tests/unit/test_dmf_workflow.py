import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.calculator import Calculator, all_changes
from ase.io import read, write


class ConstantCalc(Calculator):
    implemented_properties = ["energy", "forces"]

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        self.results["energy"] = float(np.sum(atoms.get_positions()))
        self.results["forces"] = np.zeros((len(atoms), 3))


class FakeDMF:
    def __init__(self, ref_images, **kwargs):
        self.ref_images = ref_images
        self.kwargs = kwargs
        self.images = [image.copy() for image in ref_images]
        mid = ref_images[0].copy()
        mid.positions = (ref_images[0].positions + ref_images[-1].positions) / 2.0
        self.images.insert(1, mid)
        self.history = types.SimpleNamespace(tmax=[], images_tmax=[])
        self.ipopt_options = {}
        self.coefs = np.zeros((2, len(ref_images[0]), 3))

    def add_ipopt_options(self, options):
        self.ipopt_options.update(options)

    def solve(self, tol=None):
        self.history.tmax.append(0.5)
        self.history.images_tmax.append(self.images[1].copy())
        return np.zeros(1), {"status": 0, "status_msg": "ok"}


def _install_fake_pydmf(monkeypatch, direct_max_flux=FakeDMF, interpolate=None):
    module = types.SimpleNamespace(DirectMaxFlux=direct_max_flux)
    module.interpolate_fbenm = interpolate or (lambda ref_images, **kwargs: FakeDMF(ref_images))
    monkeypatch.setitem(sys.modules, "atst_tools.external.pydmf.dmf", module)


def _config(tmp_path, **calculation):
    init = tmp_path / "init.xyz"
    final = tmp_path / "final.xyz"
    write(init, Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.7, 0.0, 0.0]]))
    write(final, Atoms("H2", positions=[[0.0, 0.0, 0.1], [0.7, 0.0, 0.2]]))
    calc = {
        "type": "dmf",
        "init_file": str(init),
        "final_file": str(final),
        "trajectory": str(tmp_path / "dmf_path.traj"),
        "tmax_trajectory": str(tmp_path / "dmf_tmax.traj"),
        "summary_file": str(tmp_path / "dmf_summary.json"),
        "artifact_manifest": str(tmp_path / "atst_artifacts.json"),
        **calculation,
    }
    return {
        "calculation": calc,
        "calculator": {"name": "dp", "dp": {"model": "model.pb"}},
    }


def test_dmf_workflow_writes_summary_manifest_and_trajectories(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    _install_fake_pydmf(monkeypatch)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, initial_path="linear")

    DMFWorkflow(config, "dp", config["calculation"]).run()

    summary = json.loads(Path(config["calculation"]["summary_file"]).read_text(encoding="utf-8"))
    assert summary["workflow"] == "dmf"
    assert summary["experimental"] is True
    assert summary["result_type"] == "ts_candidate"
    assert summary["validated_ts"] is False
    assert summary["pbc_mode"] == "reject"
    assert len(read(config["calculation"]["trajectory"], index=":")) == 3
    assert len(read(config["calculation"]["tmax_trajectory"], index=":")) == 1

    manifest = json.loads(Path(config["calculation"]["artifact_manifest"]).read_text(encoding="utf-8"))
    assert manifest["workflow"] == "dmf"
    assert {item["role"] for item in manifest["artifacts"]} >= {
        "evaluation_path",
        "tmax_candidate",
        "summary",
    }


def test_dmf_workflow_creates_parent_directories_for_nested_outputs(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    _install_fake_pydmf(monkeypatch)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(
        tmp_path,
        initial_path="linear",
        trajectory=str(tmp_path / "outputs" / "paths" / "dmf_path.traj"),
        tmax_trajectory=str(tmp_path / "outputs" / "candidates" / "dmf_tmax.traj"),
        summary_file=str(tmp_path / "outputs" / "summaries" / "dmf_summary.json"),
        artifact_manifest=str(tmp_path / "outputs" / "manifests" / "atst_artifacts.json"),
    )

    DMFWorkflow(config, "dp", config["calculation"]).run()

    assert Path(config["calculation"]["trajectory"]).is_file()
    assert Path(config["calculation"]["tmax_trajectory"]).is_file()
    assert Path(config["calculation"]["summary_file"]).is_file()
    assert Path(config["calculation"]["artifact_manifest"]).is_file()


def test_dmf_workflow_writes_evaluated_tmax_candidate(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    _install_fake_pydmf(monkeypatch)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, initial_path="linear")

    summary = DMFWorkflow(config, "dp", config["calculation"]).run()

    candidate = read(config["calculation"]["tmax_trajectory"])
    assert candidate.get_potential_energy() == pytest.approx(0.85)
    assert candidate.get_forces().shape == (2, 3)
    assert summary["tmax_candidate"]["energy"] == pytest.approx(0.85)
    assert summary["tmax_candidate"]["fmax"] == pytest.approx(0.0)


def test_dmf_workflow_forwards_ipopt_options(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    seen = {}

    class CapturingDMF(FakeDMF):
        def add_ipopt_options(self, options):
            super().add_ipopt_options(options)
            seen.update(options)

    _install_fake_pydmf(monkeypatch, direct_max_flux=CapturingDMF)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, initial_path="linear", ipopt_options={"max_iter": 7, "print_level": 0})

    DMFWorkflow(config, "dp", config["calculation"]).run()

    assert seen["max_iter"] == 7
    assert seen["print_level"] == 0


def test_dmf_workflow_forwards_ipopt_options_to_fbenm(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    seen = {}

    def interpolate(ref_images, **kwargs):
        seen.update(kwargs["ipopt_options"])
        return FakeDMF(ref_images)

    _install_fake_pydmf(monkeypatch, interpolate=interpolate)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, ipopt_options={"max_iter": 7, "print_level": 0})

    DMFWorkflow(config, "dp", config["calculation"]).run()

    assert seen["max_iter"] == 7
    assert seen["print_level"] == 0


def test_dmf_workflow_forwards_nmove_to_direct_maxflux_linear(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    seen = {}

    class CapturingDMF(FakeDMF):
        def __init__(self, ref_images, **kwargs):
            seen.update(kwargs)
            super().__init__(ref_images, **kwargs)

    _install_fake_pydmf(monkeypatch, direct_max_flux=CapturingDMF)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, initial_path="linear", nmove=12)

    DMFWorkflow(config, "dp", config["calculation"]).run()

    assert seen["nmove"] == 12


def test_dmf_workflow_forwards_nmove_to_final_dmf_after_fbenm(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    seen = {"interpolate": None, "direct": None}

    class CapturingDMF(FakeDMF):
        def __init__(self, ref_images, **kwargs):
            seen["direct"] = kwargs.get("nmove")
            super().__init__(ref_images, **kwargs)

    def interpolate(ref_images, **kwargs):
        seen["interpolate"] = kwargs.get("nmove")
        return FakeDMF(ref_images)

    _install_fake_pydmf(monkeypatch, direct_max_flux=CapturingDMF, interpolate=interpolate)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, initial_path="fbenm", nmove=9)

    DMFWorkflow(config, "dp", config["calculation"]).run()

    assert seen == {"interpolate": 9, "direct": 9}


def test_dmf_workflow_records_final_t_eval_in_summary(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    class TEridDMF(FakeDMF):
        def __init__(self, ref_images, **kwargs):
            super().__init__(ref_images, **kwargs)
            self.t_eval = np.array([0.0, 0.1, 0.35, 0.6, 1.0])
            self.images = [ref_images[0].copy() for _ in self.t_eval]

        def solve(self, tol=None):
            self.history.tmax.append(0.6)
            self.history.images_tmax.append(self.images[3].copy())
            return np.zeros(1), {"status": 0, "status_msg": "ok"}

    _install_fake_pydmf(monkeypatch, direct_max_flux=TEridDMF)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, initial_path="linear", nmove=3)

    summary = DMFWorkflow(config, "dp", config["calculation"]).run()
    written = json.loads(Path(config["calculation"]["summary_file"]).read_text(encoding="utf-8"))

    assert summary["nmove"] == 3
    assert summary["n_images"] == 5
    assert summary["t_eval"] == pytest.approx([0.0, 0.1, 0.35, 0.6, 1.0])
    assert written["nmove"] == 3
    assert written["t_eval"] == pytest.approx([0.0, 0.1, 0.35, 0.6, 1.0])


def test_dmf_workflow_writes_numpy_ipopt_info_as_json(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    class NumpyInfoDMF(FakeDMF):
        def solve(self, tol=None):
            self.history.tmax.append(0.5)
            self.history.images_tmax.append(self.images[1].copy())
            return np.zeros(1), {"status": 0, "x": np.array([1.0, 2.0]), "status_msg": b"ok"}

    _install_fake_pydmf(monkeypatch, direct_max_flux=NumpyInfoDMF)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    config = _config(tmp_path, initial_path="linear")

    DMFWorkflow(config, "dp", config["calculation"]).run()

    summary = json.loads(Path(config["calculation"]["summary_file"]).read_text(encoding="utf-8"))
    assert summary["ipopt_status"]["x"] == [1.0, 2.0]
    assert summary["ipopt_status"]["status_msg"] == "ok"


def test_dmf_workflow_rejects_pbc_by_default(tmp_path):
    from atst_tools.workflows.dmf import DMFWorkflow

    init = tmp_path / "init.xyz"
    final = tmp_path / "final.xyz"
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[5, 5, 5], pbc=True)
    write(init, atoms)
    write(final, atoms)
    config = {
        "calculation": {"type": "dmf", "init_file": str(init), "final_file": str(final)},
        "calculator": {"name": "dp", "dp": {"model": "model.pb"}},
    }

    with pytest.raises(ValueError, match="pbc_mode=reject"):
        DMFWorkflow(config, "dp", config["calculation"]).run()


def test_dmf_workflow_accepts_confirmed_cartesian_unwrapped_pbc(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    _install_fake_pydmf(monkeypatch)
    monkeypatch.setattr(
        "atst_tools.workflows.dmf.CalculatorFactory.get_calculator",
        lambda *args, **kwargs: ConstantCalc(),
    )
    init = tmp_path / "init.traj"
    final = tmp_path / "final.traj"
    atoms = Atoms("H", positions=[[0.0, 0.0, 0.0]], cell=[5, 5, 5], pbc=True)
    write(init, atoms)
    write(final, atoms)
    config = _config(
        tmp_path,
        init_file=str(init),
        final_file=str(final),
        pbc_mode="cartesian_unwrapped",
        confirm_pbc_risk=True,
        remove_rotation_and_translation=False,
        initial_path="linear",
    )

    DMFWorkflow(config, "dp", config["calculation"]).run()

    summary = json.loads(Path(config["calculation"]["summary_file"]).read_text(encoding="utf-8"))
    assert summary["pbc_mode"] == "cartesian_unwrapped"


def test_dmf_workflow_reports_missing_cyipopt_actionably(tmp_path, monkeypatch):
    from atst_tools.workflows.dmf import DMFWorkflow

    def missing_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "atst_tools.external.pydmf.dmf":
            raise ModuleNotFoundError("No module named 'cyipopt'", name="cyipopt")
        return original_import(name, globals, locals, fromlist, level)

    import builtins

    original_import = builtins.__import__
    monkeypatch.setitem(sys.modules, "atst_tools.external.pydmf.dmf", None)
    monkeypatch.setattr("builtins.__import__", missing_import)
    config = _config(tmp_path, initial_path="linear")

    with pytest.raises(RuntimeError, match="cyipopt"):
        DMFWorkflow(config, "dp", config["calculation"]).run()


def test_vendored_pydmf_metadata_is_preserved():
    root = Path("src/atst_tools/external/pydmf")

    assert (root / "LICENSE").exists()
    assert "ed7ed53623e8eaa2e8f57d040b3564a731a67e46" in (root / "UPSTREAM.md").read_text(
        encoding="utf-8"
    )
    assert (root / "dmf" / "dmf.py").exists()
    assert (root / "dmf" / "interpolate.py").exists()
    assert (root / "dmf" / "torch" / "__init__.py").exists()
    assert (root / "dmf" / "torch" / "dmf.py").exists()
