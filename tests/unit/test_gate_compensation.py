"""Check compensation derivatives against the explicit ABACUS energy terms."""
import numpy as np
import pytest

from atst_tools.utils.gate_compensation import compensation_terms, gate_shape, saw_shape, read_gate_compensation


@pytest.mark.parametrize('dipole', [False, True])
def test_explicit_density_and_gate_energy_derivative(dipole):
    cell = np.diag([30., 12., 10.])
    frac = np.array([[.2, .2, .3], [.35, .4, .5]])
    charges = np.array([2., 2.])
    shape = (120, 2, 2)
    x = np.arange(shape[0])/shape[0]
    profile = np.exp(-((x-.28)/.065)**2)
    rho = np.broadcast_to(profile[:, None, None], shape).copy()
    volume = abs(np.linalg.det(cell))
    rho *= 4.7 / (rho.sum()*volume/rho.size)
    n = 4.7
    result = compensation_terms(rho, cell, frac, charges, n, axis=0,
                                zgate=.7, dipole=dipole, dipole_max=.8,
                                dipole_width=.1)
    ry = 13.605698
    k = 4*np.pi*30/120
    ion = charges @ gate_shape(frac[:, 0], .7)
    electron = np.sum(rho*gate_shape(x, .7)[:, None, None])*volume/rho.size
    # V_gate is included in the electronic band energy; E_gate alone is not
    # the complete electron-number-dependent energy functional.
    def explicit_energy(number):
        d = number-charges.sum()
        energy = k*d*(ion-electron+d/12)
        if dipole:
            moment = charges @ saw_shape(frac[:, 0], .8, .1)
            moment += d*saw_shape(np.array(.7), .8, .1)
            moment -= np.sum(rho*saw_shape(x, .8, .1)[:, None, None])*volume/rho.size
            total = 4*np.pi*30/volume*moment
            energy += total**2*volume/(4*np.pi)
        return energy*ry
    h = 1e-5
    derivative = (explicit_energy(n+h)-explicit_energy(n-h))/(2*h)
    assert result['compensation_derivative_ev'] == pytest.approx(derivative, abs=1e-7)
    assert result['integrated_electrons'] == pytest.approx(n)


def test_density_identity_cannot_be_repaired_by_normalization():
    with pytest.raises(ValueError, match='electron count'):
        compensation_terms(np.ones((4, 4, 4)), np.eye(3)*10,
                           np.array([[.2, .2, .2]]), np.array([1.]), 1.,
                           axis=0, zgate=.7)


@pytest.fixture
def evaluation(tmp_path):
    (tmp_path/'INPUT').write_text('INPUT_PARAMETERS\ngate_flag 1\nnelec 1.1\nnspin 1\nout_chg 1 12\nefield_dir 0\nzgate .7\n')
    (tmp_path/'STRU').write_text('ATOMIC_SPECIES\nH 1 H.upf\nLATTICE_CONSTANT\n1\nLATTICE_VECTORS\n10 0 0\n0 10 0\n0 0 10\nATOMIC_POSITIONS\nDirect\nH\n0\n1\n.2 .2 .2 1 1 1\n')
    out = tmp_path/'OUT.ABACUS'
    out.mkdir()
    (out/'SPIN1_CHG.cube').write_text('density\n1 spin\n1 0 0 0\n4 2.5 0 0\n4 0 2.5 0\n4 0 0 2.5\n1 1 2 2 2\n'+' '.join(['0.0011']*64)+'\n')
    return tmp_path


def test_reader_uses_same_run_density_and_actual_pp_valence(evaluation):
    result = read_gate_compensation(evaluation, 1.1, 1.)
    assert result['integrated_electrons'] == pytest.approx(1.1)
    with pytest.raises(ValueError, match='PP total valence'):
        read_gate_compensation(evaluation, 1.1, 2.)


@pytest.mark.parametrize('old,new,error', [
    ('nelec 1.1', '', 'electron number'),
    ('nelec 1.1', 'nelec nan', 'electron number'),
    ('nspin 1', 'nspin 2\nnupdown 0', 'common-Fermi'),
    ('out_chg 1 12', 'out_chg 1', 'precision'),
    ('gate_flag 1', 'gate_flag 1\nefield_flag 1\ndip_cor_flag 1', 'Explicit fixed dipole'),
    ('gate_flag 1', 'gate_flag 1\nefield_flag 1\ndip_cor_flag 1\nefield_pos_max -1\nefield_pos_dec .1', 'Explicit fixed dipole'),
])
def test_reader_rejects_ambiguous_evaluation(evaluation, old, new, error):
    p = evaluation/'INPUT'
    p.write_text(p.read_text().replace(old,new))
    with pytest.raises(ValueError, match=error):
        read_gate_compensation(evaluation,1.1,1.)


def test_reader_rejects_nonfinite_neutral_reference(evaluation):
    with pytest.raises(ValueError, match='electron number'):
        read_gate_compensation(evaluation,1.1,float('nan'))
