"""SCF results follow the current STRU; native relaxation and MD use the final frame."""
import inspect
import re
import shutil
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.units import Bohr

from atst_tools.external.ASE_interface.abacuslite.core import (
    AbacusTemplate,
    _select_scf_frame_for_structure,
)
from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru
from atst_tools.external.ASE_interface.abacuslite.io.legacyio import read_abacus_out
from atst_tools.external.ASE_interface.abacuslite import core as abacus_core


TESTFILES = (
    Path(__file__).resolve().parents[2]
    / "src/atst_tools/external/ASE_interface/abacuslite/io/testfiles"
)
GOLD = TESTFILES / "multiframe_scf_trial_last"
LOG = GOLD / "running_scf.log"

# Distinct force tables identify the current STRU and the final trial frame.
STRU_FRAME_FORCES = np.array(
    [[-0.5, -0.01, 0.0], [0.5, 0.01, 0.0], [0.0, 0.0, 0.0]]
)
LAST_FRAME_FORCES = np.array(
    [[-0.45, -0.014, 0.0], [0.45, 0.014, 0.0], [0.0, 0.0, 0.0]]
)

# Final recorded forces: the legacy log has one MD step; MD_dump has two.
MD_LEGACY_FORCES = np.array(
    [[1.0712942948, 2.1781413019, 1.2152201133],
     [-1.0712942948, -2.1781413019, -1.2152201133]]
)
MD_LATEST_FORCES = np.array(
    [[0.1191299488, 0.2678988387, 1.5033416041],
     [-0.1191299488, -0.2678988387, -1.5033416041]]
)
MD_LEGACY_ENERGY = -1940.5509086572
MD_LATEST_ENERGY = -1940.6311063727


@pytest.fixture(autouse=True)
def _pin_legacyio_backend():
    """Isolate the default reader from backend changes in other test modules."""
    original = abacus_core.__LEGACYIO__
    abacus_core.__LEGACYIO__ = True
    yield
    abacus_core.__LEGACYIO__ = original

# The first three numbers in each taud_ atom record are direct coordinates.
_COORD_LINE = re.compile(r"^(taud_\S+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)(.*)$")


def _stru_positions_cartesian(stru, cell):
    """Convert the fixture's direct STRU coordinates with its logged cell."""
    frac = np.array(
        [a["coord"] for sp in stru["species"] for a in sp["atom"]], dtype=float
    )
    return frac @ np.asarray(cell)


def _cartesian_stru_text():
    """Express the fixture's H/H/Au positions in a 10 Angstrom Cartesian cell."""
    return (
        (GOLD / "STRU")
        .read_text()
        .replace("Direct", "Cartesian")
        .replace("0.4000000000 0.5000000000 0.5000000000",
                 "4.0000000000 5.0000000000 5.0000000000")
        .replace("0.6000000000 0.5000000000 0.5000000000",
                 "6.0000000000 5.0000000000 5.0000000000")
        .replace("0.5000000000 0.5000000000 0.1000000000",
                 "5.0000000000 5.0000000000 1.0000000000")
    )


def _cartesian_log_text():
    """Convert only the fixture's direct-coordinate records to Cartesian Angstrom."""
    lines = []
    for line in (GOLD / "running_scf.log").read_text().splitlines(keepends=True):
        if re.match(r"^DIRECT COORDINATES\s*$", line.rstrip("\n")):
            lines.append("CARTESIAN COORDINATES\n")
            continue
        m = _COORD_LINE.match(line.rstrip("\n"))
        if m:
            x, y, z = (float(m.group(i)) * 10.0 for i in (2, 3, 4))
            lines.append(f"{m.group(1)} {x:20.10f} {y:20.10f} {z:20.10f}{m.group(5)}\n")
            continue
        lines.append(line)
    return "".join(lines)


def _log_with_extra_atom_per_frame():
    """Corrupt the raw parser stream without changing its force tables."""
    lines = []
    for line in (GOLD / "running_scf.log").read_text().splitlines():
        if "TOTAL ATOM NUMBER = 3" in line:
            line = line.replace("TOTAL ATOM NUMBER = 3", "TOTAL ATOM NUMBER = 4")
        lines.append(line)
        if line.lstrip().startswith("taud_Au1"):
            lines.append(
                "taud_X1            0.2000000000        0.3000000000        "
                "0.4000000000  0.0000        0.0000000000        "
                "0.0000000000        0.0000000000"
            )
    return "\n".join(lines) + "\n"


def _log_with_translated_first_frame():
    """Translate each raw first-frame atom by a different integer direct vector."""
    shifts = {
        "taud_H1": np.array([1, -2, 0]),
        "taud_H2": np.array([-1, 0, 3]),
        "taud_Au1": np.array([0, 1, -1]),
    }
    lines = []
    in_first_frame = False
    translated = 0
    for line in (GOLD / "running_scf.log").read_text().splitlines():
        if line.strip() == "DIRECT COORDINATES" and not in_first_frame:
            in_first_frame = True
        match = _COORD_LINE.match(line)
        if in_first_frame and match and match.group(1) in shifts:
            coordinates = np.array(
                [float(match.group(index)) for index in (2, 3, 4)]
            ) + shifts[match.group(1)]
            line = (
                f"{match.group(1)} {coordinates[0]:20.10f} "
                f"{coordinates[1]:20.10f} {coordinates[2]:20.10f}{match.group(5)}"
            )
            translated += 1
            if translated == 3:
                in_first_frame = False
        lines.append(line)
    return "\n".join(lines) + "\n"


def _template(calc="scf", atomorder=None):
    """Construct the read_results fields without invoking an engine."""
    template = AbacusTemplate()
    template.suffix = "ABACUS"
    template.calculation = calc
    template.atomorder = [0, 1, 2] if atomorder is None else atomorder
    return template


def _read_results_fixture(tmp_path, calc="scf", stru_text=None, log_text=None):
    """Stage STRU and a running log, optionally changing its structure or records."""
    (tmp_path / "STRU").write_text(
        stru_text if stru_text is not None else (GOLD / "STRU").read_text(),
        encoding="utf-8",
    )
    out = tmp_path / "OUT.ABACUS"
    out.mkdir()
    (out / f"running_{calc}.log").write_text(
        log_text if log_text is not None else (GOLD / "running_scf.log").read_text(),
        encoding="utf-8",
    )
    return tmp_path


def _md_fixture_legacy(tmp_path):
    """Stage a native legacy MD log without STRU: MD does not match SCF structures."""
    out = tmp_path / "OUT.ABACUS"
    out.mkdir()
    shutil.copy(TESTFILES / "multiframe_md_legacy" / "running_md.log", out / "running_md.log")
    return tmp_path


def _md_fixture_latest(tmp_path):
    """Stage the latest reader's native MD log, MD_dump and eig_occ.txt."""
    out = tmp_path / "OUT.ABACUS"
    out.mkdir()
    for name in ("running_md.log", "MD_dump", "eig_occ.txt"):
        shutil.copy(TESTFILES / "multiframe_md_latest" / name, out / name)
    return tmp_path


class _SyntheticFrame:
    """Small parser-shaped frame used to exercise fail-closed validation paths."""

    def __init__(self, symbols, positions, cell):
        self._symbols = list(symbols)
        self.positions = np.asarray(positions)
        self.cell = np.asarray(cell)

    def get_chemical_symbols(self):
        return list(self._symbols)


def _synthetic_stru_text(symbols, coordinates, cell, coordinate_type="Direct"):
    """Build a minimal valid STRU fixture with a hand-selected cell and positions."""
    symbols = list(symbols)
    coordinates = np.asarray(coordinates, dtype=float)
    cell = np.asarray(cell, dtype=float)
    species = list(dict.fromkeys(symbols))
    lines = [
        "ATOMIC_SPECIES",
        *[f"{symbol} 1.0 {symbol}.upf" for symbol in species],
        "",
        "LATTICE_CONSTANT",
        f"{1.0 / Bohr:.16g}",
        "",
        "LATTICE_VECTORS",
        *[" ".join(f"{value:.16g}" for value in vector) for vector in cell],
        "",
        "ATOMIC_POSITIONS",
        coordinate_type,
        "",
    ]
    for symbol in species:
        lines.extend([symbol, "0.0"])
        indices = [index for index, value in enumerate(symbols) if value == symbol]
        lines.append(str(len(indices)))
        for index in indices:
            lines.append(
                " ".join(f"{value:.16g}" for value in coordinates[index])
                + " m 1 1 1"
            )
    return "\n".join(lines) + "\n"


def _synthetic_direct_case(tmp_path, symbols=("H", "He")):
    """Return a small non-orthogonal direct-coordinate matcher fixture."""
    cell = np.array(
        [[4.0, 0.0, 0.0], [1.0, 3.0, 0.0], [0.2, 0.4, 5.0]],
        dtype=float,
    )
    frac = np.array([[0.1, 0.2, 0.3], [0.65, 0.7, 0.8]], dtype=float)
    stru = tmp_path / "STRU"
    stru.write_text(_synthetic_stru_text(symbols, frac, cell), encoding="utf-8")
    return stru, cell, frac, list(symbols)


def test_golden_last_frame_differs_from_current_structure():
    """The final trial frame differs from the current STRU."""
    frames = read_abacus_out(LOG, sort_atoms_with=None)
    stru = read_stru(GOLD / "STRU")
    last_cart = frames[-1].positions @ np.asarray(frames[-1].cell)
    current_cart = _stru_positions_cartesian(stru, frames[-1].cell)
    assert not np.allclose(last_cart, current_cart, atol=1e-4)


def test_golden_first_frame_is_current_structure():
    """The first recorded SCF frame matches the current STRU."""
    frames = read_abacus_out(LOG, sort_atoms_with=None)
    stru = read_stru(GOLD / "STRU")
    first_cart = frames[0].positions @ np.asarray(frames[0].cell)
    current_cart = _stru_positions_cartesian(stru, frames[0].cell)
    assert np.allclose(first_cart, current_cart, atol=1e-4)


def test_multiframe_scf_read_results_returns_current_structure_force(tmp_path):
    """Return forces for the current STRU even when a different trial frame is last."""
    directory = _read_results_fixture(tmp_path)
    results = _template().read_results(directory)

    assert not np.allclose(STRU_FRAME_FORCES, LAST_FRAME_FORCES)
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)


def test_scf_read_results_preserves_backend_neutral_efermi(tmp_path):
    """Preserve the selected frame's Fermi value under both result aliases."""
    directory = _read_results_fixture(tmp_path)
    results = _template().read_results(directory)

    # This nspin=1 fixture records one Fermi value, -2.04 eV.
    assert results["efermi"] == pytest.approx(-2.04)
    assert results["fermi_level"] == pytest.approx(results["efermi"])


def test_scf_read_results_fails_closed_when_no_frame_matches(tmp_path):
    """Reject unrelated results instead of returning another structure's forces."""
    stru_text = (
        (GOLD / "STRU")
        .read_text()
        .replace("0.4000000000 0.5000000000 0.5000000000",
                 "0.4300000000 0.5000000000 0.5000000000")
        .replace("0.6000000000 0.5000000000 0.5000000000",
                 "0.5700000000 0.5000000000 0.5000000000")
    )
    directory = _read_results_fixture(tmp_path, stru_text=stru_text)
    with pytest.raises(RuntimeError) as excinfo:
        _template().read_results(directory)
    msg = str(excinfo.value)
    assert "running_scf.log" in msg


def test_native_relax_multiframe_keeps_last_frame_semantics(tmp_path):
    """Native relaxation returns the final frame without SCF structure matching."""
    directory = _read_results_fixture(tmp_path, calc="relax")
    results = _template(calc="relax").read_results(directory)

    assert not np.allclose(STRU_FRAME_FORCES, LAST_FRAME_FORCES)
    assert np.allclose(results["forces"], LAST_FRAME_FORCES, atol=1e-12)


def test_frame_selection_tolerance_both_sides(tmp_path):
    """Accept matching geometry, reject a displacement, and accept it with a looser bound."""
    directory = _read_results_fixture(tmp_path)
    log = directory / "OUT.ABACUS" / "running_scf.log"
    frames = read_abacus_out(log, sort_atoms_with=[0, 1, 2])
    expected = _stru_positions_cartesian(read_stru(directory / "STRU"), frames[0].cell)

    # The matching frame remains selectable at the strict bound.
    selected = _select_scf_frame_for_structure(frames, log, directory, [0, 1, 2], atol=1e-4)
    assert selected is frames[0]
    assert np.allclose(selected.positions @ np.asarray(selected.cell), expected, atol=1e-4)

    # The displaced frame alone must not yield another structure's result.
    with pytest.raises(RuntimeError) as excinfo:
        _select_scf_frame_for_structure([frames[1]], log, directory, [0, 1, 2], atol=1e-4)
    msg = str(excinfo.value)
    assert "running_scf.log" in msg

    # The same frame becomes acceptable when the permitted residual is larger.
    loose = _select_scf_frame_for_structure([frames[1]], log, directory, [0, 1, 2], atol=0.5)
    assert loose is frames[1]


def test_native_md_legacy_keeps_last_frame_semantics_real_gold(tmp_path):
    """Native legacy MD returns final forces and energy without requiring STRU."""
    directory = _md_fixture_legacy(tmp_path)
    results = _template(calc="md", atomorder=[0, 1]).read_results(directory)
    assert np.allclose(results["forces"], MD_LEGACY_FORCES, atol=1e-12)
    assert results["energy"] == pytest.approx(MD_LEGACY_ENERGY)


def test_native_md_latestio_md_dump_keeps_last_frame_semantics(tmp_path, monkeypatch):
    """Native latest-format MD returns the final MD_dump frame without requiring STRU."""
    from atst_tools.external.ASE_interface.abacuslite import core as abacus_core

    monkeypatch.setattr(abacus_core, "__LEGACYIO__", False)
    directory = _md_fixture_latest(tmp_path)
    results = _template(calc="md", atomorder=[0, 1]).read_results(directory)
    assert np.allclose(results["forces"], MD_LATEST_FORCES, atol=1e-12)
    assert results["energy"] == pytest.approx(MD_LATEST_ENERGY)


def test_latestio_md_dump_cell_is_physical_and_periodic(tmp_path):
    from atst_tools.external.ASE_interface.abacuslite.io.latestio import (
        read_abacus_out as read_latest_out,
        read_traj_from_md_dump,
    )

    directory = _md_fixture_latest(tmp_path)
    out = directory / "OUT.ABACUS"
    raw = read_traj_from_md_dump(out / "MD_dump")
    frames = read_latest_out(out / "running_md.log")
    assert len(frames) == len(raw) == 2
    for atoms, frame in zip(frames, raw):
        expected = np.asarray(frame["cell"]) * frame["alat_in_angstrom"]
        assert np.allclose(atoms.cell.array, expected, atol=1e-10)
        assert atoms.pbc.all()
    assert frames[-1].cell.volume == pytest.approx(45.17906195, abs=1e-5)


def test_latestio_md_eig_occ_remains_available_for_repeated_reads(tmp_path, monkeypatch):
    """The installed reader preserves raw eig_occ data across repeated reads."""
    from atst_tools.external.ASE_interface.abacuslite import core as abacus_core

    monkeypatch.setattr(abacus_core, "__LEGACYIO__", False)
    directory = _md_fixture_latest(tmp_path)
    eig_occ = directory / "OUT.ABACUS" / "eig_occ.txt"
    gold_eig_occ = eig_occ.read_bytes()

    results = _template(calc="md", atomorder=[0, 1]).read_results(directory)
    assert eig_occ.read_bytes() == gold_eig_occ
    results2 = _template(calc="md", atomorder=[0, 1]).read_results(directory)
    assert eig_occ.read_bytes() == gold_eig_occ
    assert np.allclose(results["forces"], MD_LATEST_FORCES, atol=1e-12)
    assert np.allclose(results2["forces"], MD_LATEST_FORCES, atol=1e-12)


def test_scf_frame_selection_respects_atomorder_revmap(tmp_path):
    """Apply the species-to-ASE permutation consistently to matching and forces."""
    directory = _read_results_fixture(tmp_path)
    # Map species order [H, H, Au] to ASE order [H, Au, H].
    results = _template(atomorder=[0, 2, 1]).read_results(directory)

    assert np.allclose(results["forces"][1], 0.0, atol=1e-12)  # The middle ASE atom is Au.
    assert np.allclose(results["forces"][0], [-0.5, -0.01, 0.0], atol=1e-12)
    assert np.allclose(results["forces"][2], [0.5, 0.01, 0.0], atol=1e-12)


def test_scf_frame_selection_uses_log_coordinate_system_not_stru(tmp_path):
    """Read direct log coordinates correctly even when STRU uses Cartesian coordinates."""
    directory = _read_results_fixture(tmp_path, stru_text=_cartesian_stru_text())
    results = _template().read_results(directory)
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)


def test_scf_frame_selection_cartesian_log_branch(tmp_path):
    """Read Cartesian log coordinates without applying the cell twice."""
    directory = _read_results_fixture(tmp_path, log_text=_cartesian_log_text())
    results = _template().read_results(directory)
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)


def test_scf_read_results_without_atomorder_uses_identity(tmp_path):
    """Direct result reading without write_input preserves the default atom order."""
    directory = _read_results_fixture(tmp_path)
    template = _template()
    template.atomorder = None
    results = template.read_results(directory)
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)


def test_scf_selector_accepts_independent_integer_lattice_translations_and_latest_match(tmp_path):
    """PBC identity accepts independent lattice translations and selects the latest match."""
    stru, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    shifts = np.array([[1, -2, 0], [-1, 0, 3]], dtype=float)
    latest_shifts = np.array([[-2, 1, 1], [3, -1, -2]], dtype=float)
    frames = [
        Atoms(symbols=symbols, positions=frac, cell=cell, pbc=True),
        Atoms(symbols=symbols, positions=frac + shifts, cell=cell, pbc=True),
        Atoms(symbols=symbols, positions=frac + latest_shifts, cell=cell, pbc=True),
    ]

    selected = _select_scf_frame_for_structure(
        frames, LOG, tmp_path, [0, 1], atol=1e-10
    )

    assert selected is frames[-1]


def test_scf_selector_accepts_cartesian_integer_lattice_translations(tmp_path):
    """Cartesian running logs use the same fractional residual test after unit normalization."""
    _, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    cart = frac @ cell
    stru = tmp_path / "STRU"
    stru.write_text(
        _synthetic_stru_text(symbols, cart, cell, coordinate_type="Cartesian"),
        encoding="utf-8",
    )
    log = tmp_path / "running_cartesian.log"
    log.write_text(_cartesian_log_text(), encoding="utf-8")
    shifts = np.array([[1, -2, 0], [-1, 0, 3]], dtype=float)
    frame = Atoms(
        symbols=symbols,
        positions=cart + shifts @ cell,
        cell=cell,
        pbc=True,
    )

    assert _select_scf_frame_for_structure(
        [frame], log, tmp_path, [0, 1], atol=1e-10
    ) is frame


_BACKEND_DEFAULT_ATOL = inspect.signature(
    _select_scf_frame_for_structure
).parameters["atol"].default


@pytest.mark.skipif(
    _BACKEND_DEFAULT_ATOL < 1e-4,
    reason=(
        "installed abacuslite still declares the pre-print-resolution default "
        f"({_BACKEND_DEFAULT_ATOL:g} A)"
    ),
)
@pytest.mark.parametrize("delta", [9e-6, 11e-6, 5e-5])
@pytest.mark.parametrize("field", ["cell", "positions"])
def test_scf_default_tolerance_covers_log_print_resolution(tmp_path, delta, field):
    """Accept small absolute rounding differences in a moderate-size cell.

    The fixed tolerance is not a general printing-error bound for arbitrarily
    large or skewed cells.
    """
    _, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    frame_cell = cell.copy()
    frame_frac = frac.copy()
    if field == "cell":
        frame_cell[0, 0] += delta
    else:
        frame_frac[0] += np.array([delta, 0, 0]) @ np.linalg.inv(cell)
    frame = Atoms(symbols=symbols, positions=frame_frac, cell=frame_cell, pbc=True)
    assert _select_scf_frame_for_structure([frame], LOG, tmp_path, [0, 1]) is frame


@pytest.mark.skipif(
    _BACKEND_DEFAULT_ATOL < 1e-4,
    reason=(
        "installed abacuslite still declares the pre-print-resolution default "
        f"({_BACKEND_DEFAULT_ATOL:g} A)"
    ),
)
@pytest.mark.parametrize("field", ["cell", "positions"])
def test_scf_default_tolerance_rejects_beyond_print_resolution(tmp_path, field):
    """Reject an absolute difference beyond the supported geometry tolerance."""
    delta = 2e-4
    _, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    frame_cell = cell.copy()
    frame_frac = frac.copy()
    if field == "cell":
        frame_cell[0, 0] += delta
    else:
        frame_frac[0] += np.array([delta, 0, 0]) @ np.linalg.inv(cell)
    frame = Atoms(symbols=symbols, positions=frame_frac, cell=frame_cell, pbc=True)
    with pytest.raises(RuntimeError):
        _select_scf_frame_for_structure([frame], LOG, tmp_path, [0, 1])


def test_latest_coordinate_parser_uses_periodic_matcher(tmp_path, monkeypatch):
    """The latest running-log parser's Direct header feeds the same matcher contract."""
    from atst_tools.external.ASE_interface.abacuslite.io.latestio import (
        read_traj_from_running_log,
    )

    monkeypatch.setattr(abacus_core, "__LEGACYIO__", False)
    log = TESTFILES / "lcao-symm1-nspin1-multik-scf_"
    trajectory = read_traj_from_running_log(log)
    data = trajectory[0]
    cell = np.asarray(data["cell"], dtype=float)
    frac = np.asarray(data["coords"], dtype=float)
    symbols = ["Zn", "O"]
    (tmp_path / "STRU").write_text(
        _synthetic_stru_text(symbols, frac, cell), encoding="utf-8"
    )
    frame = Atoms(
        symbols=symbols,
        positions=frac + np.array([[1, 0, -2], [-1, 2, 1]], dtype=float),
        cell=cell,
        pbc=True,
    )

    assert _select_scf_frame_for_structure(
        [frame], log, tmp_path, [0, 1], atol=1e-8
    ) is frame


def test_scf_selector_uses_fractional_residual_for_triclinic_cell(tmp_path):
    """A triclinic cell must compare lattice coordinates, not Cartesian-axis modulo."""
    stru, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    shift = np.array([[1, -1, 2], [-2, 3, -1]], dtype=float)
    frame = Atoms(symbols=symbols, positions=frac + shift, cell=cell, pbc=True)

    assert _select_scf_frame_for_structure(
        [frame], LOG, stru.parent, [0, 1], atol=1e-10
    ) is frame


def test_scf_selector_skips_valid_position_and_cell_mismatches(tmp_path):
    """Finite valid trial frames may mismatch while an earlier valid frame remains selectable."""
    _, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    matching = Atoms(symbols=symbols, positions=frac, cell=cell, pbc=True)
    different_cell = cell.copy()
    different_cell[0, 0] += 0.25
    valid_mismatch = Atoms(
        symbols=symbols,
        positions=frac + np.array([[0.17, 0.0, 0.0], [0.0, -0.23, 0.0]]),
        cell=different_cell,
        pbc=True,
    )

    assert _select_scf_frame_for_structure(
        [matching, valid_mismatch], LOG, tmp_path, [0, 1], atol=1e-8
    ) is matching


@pytest.mark.parametrize(
    "kind",
    [
        "positions-shape",
        "positions-finite",
        "cell-shape",
        "cell-finite",
        "cell-singular",
        "atom-count",
        "symbols",
    ],
)
def test_scf_selector_rejects_corrupt_frame_even_after_earlier_match(
    tmp_path, kind
):
    """A corrupt later frame must fail the whole SCF instead of hiding behind an earlier match."""
    _, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    matching = Atoms(symbols=symbols, positions=frac, cell=cell, pbc=True)
    corrupt_positions = frac.copy()
    corrupt_cell = cell.copy()
    corrupt_symbols = symbols
    if kind == "positions-shape":
        corrupt_positions = np.zeros((2, 2))
    elif kind == "positions-finite":
        corrupt_positions[0, 0] = np.nan
    elif kind == "cell-shape":
        corrupt_cell = np.zeros((3, 2))
    elif kind == "cell-finite":
        corrupt_cell[1, 1] = np.inf
    elif kind == "cell-singular":
        corrupt_cell[1] = corrupt_cell[0]
    elif kind == "atom-count":
        corrupt_positions = np.vstack([frac, [[0.2, 0.3, 0.4]]])
        corrupt_symbols = [*symbols, "H"]
    elif kind == "symbols":
        corrupt_symbols = ["H", "H"]
    corrupt = _SyntheticFrame(corrupt_symbols, corrupt_positions, corrupt_cell)

    assert _select_scf_frame_for_structure(
        [matching], LOG, tmp_path, [0, 1], atol=1e-8
    ) is matching
    with pytest.raises(RuntimeError):
        _select_scf_frame_for_structure(
            [matching, corrupt], LOG, tmp_path, [0, 1], atol=1e-8
        )


def test_scf_selector_does_not_mutate_candidate_atoms_or_stru(tmp_path):
    """Normalization must leave positions, cell, forces, and STRU bytes untouched."""
    _, cell, frac, symbols = _synthetic_direct_case(tmp_path)
    frame = Atoms(symbols=symbols, positions=frac, cell=cell, pbc=True)
    forces = np.array([[1.2, -0.3, 0.7], [-1.2, 0.3, -0.7]])
    frame.calc = SinglePointCalculator(frame, energy=-2.0, forces=forces)
    positions_before = frame.positions.copy()
    cell_before = np.asarray(frame.cell).copy()
    forces_before = frame.calc.results["forces"].copy()
    stru_before = (tmp_path / "STRU").read_bytes()

    assert _select_scf_frame_for_structure(
        [frame], LOG, tmp_path, [0, 1], atol=1e-10
    ) is frame
    np.testing.assert_array_equal(frame.positions, positions_before)
    np.testing.assert_array_equal(np.asarray(frame.cell), cell_before)
    np.testing.assert_array_equal(frame.calc.results["forces"], forces_before)
    assert (tmp_path / "STRU").read_bytes() == stru_before


def test_scf_read_results_rejects_invalid_atomorder_before_parser_reorder(tmp_path):
    """Out-of-range atomorder is a bounded RuntimeError, never a parser IndexError."""
    directory = _read_results_fixture(tmp_path)
    template = _template(atomorder=[0, 1, 99])

    with pytest.raises(RuntimeError) as excinfo:
        template.read_results(directory)
    message = str(excinfo.value)
    assert "atomorder" in message
    assert "STRU" in message
    assert "99" in message


def test_scf_read_results_rejects_raw_extra_atom_before_parser_reorder(tmp_path):
    """Parser sorting must not discard an extra raw atom before SCF validation."""
    directory = _read_results_fixture(tmp_path, log_text=_log_with_extra_atom_per_frame())

    with pytest.raises(RuntimeError) as excinfo:
        _template().read_results(directory)
    message = str(excinfo.value)
    assert "running_scf.log" in message


def test_scf_read_results_rejects_stru_declared_atom_count_mismatch(tmp_path):
    """A STRU species declaration must agree with its actual atom records."""
    stru_text = (GOLD / "STRU").read_text(encoding="utf-8").replace(
        "Au\n0.0\n1\n0.5000000000 0.5000000000 0.1000000000",
        "Au\n0.0\n2\n0.5000000000 0.5000000000 0.1000000000",
        1,
    )
    directory = _read_results_fixture(tmp_path, stru_text=stru_text)

    with pytest.raises(RuntimeError) as excinfo:
        _template().read_results(directory)
    message = str(excinfo.value).lower()
    assert "stru" in message


def test_scf_read_results_accepts_translated_real_parser_frame(tmp_path):
    """The real legacy parser and atom reorder preserve a periodic translated SCF frame."""
    directory = _read_results_fixture(tmp_path, log_text=_log_with_translated_first_frame())
    results = _template(atomorder=[0, 2, 1]).read_results(directory)

    np.testing.assert_allclose(
        results["forces"], STRU_FRAME_FORCES[[0, 2, 1]], atol=1e-12
    )


def test_write_input_tracks_custom_stru_file_for_scf_selection(tmp_path):
    """write_input's non-default STRU name is the file consumed by SCF identity checks."""
    atoms = Atoms(
        symbols=["H", "Au", "H"],
        positions=[[4.0, 5.0, 5.0], [5.0, 5.0, 1.0], [6.0, 5.0, 5.0]],
        cell=[10.0, 10.0, 10.0],
        pbc=True,
    )
    template = AbacusTemplate()
    template.write_input(
        SimpleNamespace(pseudo_dir=None, orbital_dir=None),
        tmp_path,
        atoms,
        parameters={"calculation": "scf", "stru_file": "CURRENT.STRU"},
        properties=["energy", "forces"],
    )
    out = tmp_path / "OUT.ABACUS"
    out.mkdir()
    shutil.copy(GOLD / "running_scf.log", out / "running_scf.log")
    # A misleading default STRU proves read_results did not hard-code its filename.
    (tmp_path / "STRU").write_text(
        (GOLD / "STRU").read_text().replace(
            "0.4000000000 0.5000000000 0.5000000000",
            "0.4300000000 0.5000000000 0.5000000000",
        ),
        encoding="utf-8",
    )

    assert template.stru_file == "CURRENT.STRU"
    results = template.read_results(tmp_path)
    np.testing.assert_allclose(
        results["forces"], STRU_FRAME_FORCES[[0, 2, 1]], atol=1e-12
    )
