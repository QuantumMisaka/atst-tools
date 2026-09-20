"""Diagnostic residual screens must not imply scientific acceptance."""
import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[2] / 'examples/19_constant_potential_Pt/analyze_scan.py'
spec = importlib.util.spec_from_file_location('cp_scan_diagnostic', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_step_evidence_has_no_implicit_acceptance_threshold():
    facts = module.derivative_diagnostics([.05, .1], [.0002, .0008])
    assert facts['scientific_acceptance'] == 'not_assessed'
    assert facts['diagnostic_criterion'] is None
    assert 'passed' not in facts
    assert facts['richardson_residual_ev'] == pytest.approx(0)
    assert facts['coarse_to_fine_residual_ratio'] == pytest.approx(4)


def test_explicit_screen_requires_rationale_and_does_not_certify_science():
    with pytest.raises(ValueError, match='source/reason'):
        module.derivative_diagnostics([.05, .1], [.001, .004], .02)
    facts = module.derivative_diagnostics([.05, .1], [.001, .004], .02, 'historical engineering screen')
    assert facts['diagnostic_criterion']['within_tolerance'] is True
    assert facts['scientific_acceptance'] == 'not_assessed'


def test_adsorbate_fixture_preserves_substrate_and_fixes_only_pt(tmp_path, monkeypatch):
    import numpy as np
    from atst_tools.utils.io import read_structure

    monkeypatch.syspath_prepend(str(path.parent))
    from materialize_adsorbate import materialize_endpoints

    reference = read_structure(path.parent/'inputs/STRU')
    endpoints = materialize_endpoints(tmp_path/'endpoints')
    for name in ('initial', 'final'):
        atoms = read_structure(endpoints/name/'STRU')
        assert atoms.get_chemical_formula() == 'HPt12'
        np.testing.assert_array_equal(atoms.positions[:12], reference.positions)
        assert len(atoms.constraints) == 1
        assert list(atoms.constraints[0].get_indices()) == list(range(12))
        assert min(atoms.get_distances(12, range(12), mic=True)) > 1.9
