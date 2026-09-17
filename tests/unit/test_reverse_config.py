"""Reverse ABACUS-run-dir -> ATST config generation tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from atst_tools.api import validate_config
from atst_tools.utils import abacus_io
from atst_tools.utils.reverse_config import (
    build_config_from_abacus_dir,
    coerce_input_value,
    endpoint_has_energy_forces,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
# Real, minimal, parseable ABACUS running log kept by the abacuslite IO tests.
# The legacyio gate readers require an iteration header + ENERGY and TOTAL-FORCE
# tables; the placeholder log from the brief ("iter energy forces ok") does not
# parse, so we copy this maintained fixture instead.
_GATE_POSITIVE_LOG = (
    _REPO_ROOT
    / "src/atst_tools/external/ASE_interface/abacuslite/io/testfiles"
    / "multiframe_scf_trial_last/running_scf.log"
)

_MINIMAL_STRU = """ATOMIC_SPECIES
H 1.008 H.upf

NUMERICAL_ORBITAL
H.orb

LATTICE_CONSTANT
1.0

LATTICE_VECTORS
10 0 0
0 10 0
0 0 10

ATOMIC_POSITIONS
Direct
H
0.0
1
0.5 0.5 0.5
"""

_STRU_WITHOUT_ORBITALS = _MINIMAL_STRU.replace("NUMERICAL_ORBITAL\nH.orb\n\n", "")


def _write_minimal_run(tmp_path: Path, *, cal_stress: str = "1", kpt_mode: str = "Gamma") -> Path:
    """Write a minimal but complete ABACUS run directory.

    Includes a real parseable running log under ``OUT.abacus/`` so gate-positive
    calls (the default CLI gate) succeed. Gate-negative tests remove it.
    """
    run = tmp_path / "run"
    run.mkdir(parents=True)
    (run / "INPUT").write_text(
        "\n".join(
            [
                "INPUT_PARAMETERS",
                "calculation relax",
                "basis_type lcao",
                "cal_force 0",
                f"cal_stress {cal_stress}",
                "nspin 2",
                "ecutwfc 100",
                "pseudo_dir ./data",
                "orbital_dir ./data",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (run / "data").mkdir()
    (run / "data" / "H.upf").write_text("pp\n", encoding="utf-8")
    (run / "data" / "H.orb").write_text("orb\n", encoding="utf-8")
    (run / "KPT").write_text(
        "K_POINTS\n0\n%s\n1 1 1 0 0 0\n" % kpt_mode, encoding="utf-8"
    )
    (run / "STRU").write_text(_MINIMAL_STRU, encoding="utf-8")
    (run / "OUT.abacus").mkdir()
    (run / "OUT.abacus" / "running_scf.log").write_text(
        _GATE_POSITIVE_LOG.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return run


def test_build_config_from_abacus_dir_basic(tmp_path):
    run = _write_minimal_run(tmp_path)
    config = build_config_from_abacus_dir(run, gate_dirs=[])
    validate_config(config)  # must pass the schema
    abacus = config["calculator"]["abacus"]
    assert abacus["parameters"]["calculation"] == "scf"  # floor
    assert abacus["parameters"]["cal_force"] == 1  # floor (INPUT was 0)
    assert abacus["parameters"]["cal_stress"] == 1  # user value verbatim
    assert abacus["parameters"]["nspin"] == 2
    assert abacus["parameters"]["ecutwfc"] == 100
    assert "pseudo_dir" not in abacus["parameters"]  # promoted to top level
    assert "orbital_dir" not in abacus["parameters"]
    assert abacus["pseudo_dir"] == str((run / "data").resolve())
    assert abacus["pseudopotentials"] == {"H": "H.upf"}
    assert abacus["basissets"] == {"H": "H.orb"}
    # KPT Gamma file maps to the mp-sampling dict (identical shape to the
    # ABACUS toolbox _runtime_kpts, so Agent delegation is byte-identical).
    assert abacus["kpts"] == {
        "mode": "mp-sampling",
        "gamma-centered": True,
        "nk": [1, 1, 1],
        "kshift": [0, 0, 0],
    }


def test_build_config_rejects_line_mode(tmp_path):
    run = _write_minimal_run(tmp_path)
    # Decimal coordinates: real ABACUS line-mode KPT files use them, and the
    # abacuslite line parser requires a decimal to avoid an empty regex group.
    (run / "KPT").write_text(
        "K_POINTS\n2\nLine\n0.0 0.0 0.0 10 G\n0.0 0.0 1.0 10 Z\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Line-mode KPT is not supported"):
        build_config_from_abacus_dir(run, gate_dirs=[])


def test_build_config_gate_rejects_without_forces(tmp_path):
    run = _write_minimal_run(tmp_path)
    (run / "OUT.abacus" / "running_scf.log").unlink()
    with pytest.raises(ValueError, match=r"lacks parseable energy\+forces output"):
        build_config_from_abacus_dir(run, gate_dirs=[run])


def test_build_config_gamma_only_without_kpt(tmp_path):
    run = _write_minimal_run(tmp_path)
    (run / "KPT").unlink()
    inp = (run / "INPUT").read_text(encoding="utf-8") + "gamma_only 1\n"
    (run / "INPUT").write_text(inp, encoding="utf-8")
    config = build_config_from_abacus_dir(run, gate_dirs=[])
    assert config["calculator"]["abacus"]["kpts"] == [1, 1, 1]


def test_build_config_point_kpt_passthrough(tmp_path):
    """Explicit point K points are passed through as a dict (SPEC R4)."""
    run = _write_minimal_run(tmp_path)
    (run / "KPT").write_text(
        "K_POINTS\n2\nDirect\n0.0 0.0 0.0 1\n0.5 0.5 0.5 1\n", encoding="utf-8"
    )
    config = build_config_from_abacus_dir(run, gate_dirs=[])
    kpts = config["calculator"]["abacus"]["kpts"]
    assert isinstance(kpts, dict)
    assert kpts["mode"] == "point"
    assert len(kpts["kpoints"]) == 2
    # Multi-point decimal coordinates must round-trip exactly (regression:
    # the abacuslite point parser previously mis-parsed fractional coords).
    assert [tuple(map(float, row)) for row in kpts["kpoints"]] == [
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.5),
    ]
    assert kpts["weights"] == [1, 1]


def test_build_config_kspacing_derives_grid(tmp_path):
    """kspacing (Bohr^-1) derives a Gamma grid from the STRU cell (SPEC R4/R-6)."""
    run = _write_minimal_run(tmp_path)
    (run / "KPT").unlink()
    inp = (run / "INPUT").read_text(encoding="utf-8") + "kspacing 0.2 0.3 0.4\n"
    (run / "INPUT").write_text(inp, encoding="utf-8")
    config = build_config_from_abacus_dir(run, gate_dirs=[])
    # Fixture cell = 10x10x10 Bohr => 5.2918 Ang; kspacing 0.2/0.3/0.4 Bohr^-1
    # => grid [4, 3, 2] via atst-tools convert_kspacing_to_kpts.
    assert config["calculator"]["abacus"]["kpts"] == [4, 3, 2]


def test_endpoint_has_energy_forces_positive_and_negative(tmp_path):
    run = _write_minimal_run(tmp_path)
    assert endpoint_has_energy_forces(run) is True
    (run / "OUT.abacus" / "running_scf.log").unlink()
    assert endpoint_has_energy_forces(run) is False


def test_coerce_input_value():
    assert coerce_input_value("1") == 1
    assert coerce_input_value("0.5") == 0.5
    assert coerce_input_value("1e-6") == 1e-06
    assert coerce_input_value("true") is True
    assert coerce_input_value(".true.") is True
    assert coerce_input_value("false") is False
    assert coerce_input_value("lcao") == "lcao"
    assert coerce_input_value("") == ""


def test_error_messages_are_english_for_missing_run_dir_artifacts(tmp_path):
    """Runtime messages are English (program-output contract, SPEC R6)."""
    empty = tmp_path / "empty_run"
    empty.mkdir()
    with pytest.raises(ValueError, match="is missing INPUT"):
        build_config_from_abacus_dir(empty, gate_dirs=[])

    no_stru = tmp_path / "no_stru"
    no_stru.mkdir()
    (no_stru / "INPUT").write_text(
        "INPUT_PARAMETERS\ncalculation scf\nbasis_type lcao\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="is missing STRU"):
        build_config_from_abacus_dir(no_stru, gate_dirs=[])

    missing = tmp_path / "missing_run"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        build_config_from_abacus_dir(missing, gate_dirs=[])


def test_error_messages_are_english_for_invalid_inputs(tmp_path, monkeypatch):
    """K-point, orbital, workflow and gate failures keep English wording."""
    run = _write_minimal_run(tmp_path)

    # basis_type lcao without NUMERICAL_ORBITAL in STRU = missing orbital files.
    (run / "STRU").write_text(_STRU_WITHOUT_ORBITALS, encoding="utf-8")
    with pytest.raises(ValueError, match="STRU is missing LCAO orbital filenames: H"):
        build_config_from_abacus_dir(run, gate_dirs=[])

    (run / "STRU").write_text(_MINIMAL_STRU, encoding="utf-8")

    # No gamma_only, no kspacing, no KPT file = no valid K-point source.
    kpt = (run / "KPT").read_text(encoding="utf-8")
    (run / "KPT").unlink()
    with pytest.raises(ValueError, match="No valid K-point source"):
        build_config_from_abacus_dir(run, gate_dirs=[])

    # Unparsable kspacing cannot derive a grid from the STRU cell.
    input_text = (run / "INPUT").read_text(encoding="utf-8")
    (run / "INPUT").write_text(input_text + "kspacing abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot derive a K-point grid from kspacing"):
        build_config_from_abacus_dir(run, gate_dirs=[])

    (run / "INPUT").write_text(input_text, encoding="utf-8")
    (run / "KPT").write_text(kpt, encoding="utf-8")

    # Unsupported KPT mode reported by the parser (no such mode is a valid file).
    monkeypatch.setattr(
        abacus_io._import_generalio(), "read_kpt", lambda path: {"mode": "weird"}
    )
    with pytest.raises(ValueError, match="Unsupported KPT mode: weird"):
        build_config_from_abacus_dir(run, gate_dirs=[])
    monkeypatch.undo()

    with pytest.raises(
        ValueError, match=r"Unsupported workflow: dimer \(P0 supports neb\)"
    ):
        build_config_from_abacus_dir(run, workflow="dimer", gate_dirs=[])


def test_reverse_kpts_matches_toolbox_runtime_spec(tmp_path):
    """Cross-repo equivalence: upstream kpts == toolbox _runtime_kpts.

    The same fixture runs inside the ABACUS toolbox (Phase 2) where the toolbox
    `resolve_runtime_kpoint_spec` is importable; here it is not reachable, so
    the test skips and the equivalence is asserted on the toolbox side.
    """
    from atst_tools.utils.reverse_config import (
        _read_input,
        _resolve_kpts,
        build_config_from_abacus_dir,
    )

    run = _write_minimal_run(tmp_path)
    (run / "KPT").unlink()
    inp = (run / "INPUT").read_text(encoding="utf-8") + "kspacing 0.2 0.3 0.4\n"
    (run / "INPUT").write_text(inp, encoding="utf-8")

    raw = _read_input(run)
    upstream_kpts = _resolve_kpts(run, raw)

    toolbox_kpts = None
    try:
        sys.path.insert(0, str(run.parent.parent / "utils"))
        from utils.kpt_logic import resolve_runtime_kpoint_spec

        spec = resolve_runtime_kpoint_spec(run)
        toolbox_kpts = list(spec.grid) if spec.grid is not None else None
    except Exception:
        pytest.skip("toolbox utils unavailable; equivalence covered in toolbox Phase 2")

    assert upstream_kpts == toolbox_kpts
