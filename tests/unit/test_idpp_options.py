"""Public configuration and CLI coverage for IDPP optimization choices."""
from atst_tools.utils.config import ConfigLoader
from pathlib import Path
import numpy as np
import pytest
from ase.io import read
from ase.geometry import find_mic
from atst_tools.utils.idpp import generate


def test_neb_make_optimizer_and_distribution_options():
    config = ConfigLoader.normalize({
        'calculation': {'type': 'neb', 'make': {
            'init_structure': 'start.traj', 'final_structure': 'end.traj',
            'n_images': 7, 'ts_guess': 'ts.traj',
            'idpp_optimizer': 'legacy', 'image_distribution': 'equal'}},
        'calculator': {'name': 'dp', 'dp': {'model': 'model.pt'}},
    })
    make = config['calculation']['make']
    assert make['idpp_optimizer'] == 'legacy'
    assert make['image_distribution'] == 'equal'


def test_neb_make_cli_forwards_optimization_options(monkeypatch):
    from atst_tools.scripts import cli, cli_impl
    calls = []
    monkeypatch.setattr(cli_impl, 'generate', lambda **kw: calls.append(kw))
    cli.main(['neb', 'make', 'start.traj', 'end.traj', '7', '--ts', 'ts.traj',
              '--idpp-optimizer', 'legacy', '--image-distribution', 'equal'])
    assert calls[0]['idpp_optimizer'] == 'legacy'
    assert calls[0]['image_distribution'] == 'equal'


def test_generation_length_allocation_and_ts_policy(tmp_path):
    import numpy as np
    from ase import Atoms
    from ase.constraints import FixAtoms
    from ase.io import read, write
    from atst_tools.utils.idpp import generate
    paths = []
    for name, pos in [('start', [2., 0., 0.]), ('ts', [2., 1., 0.]), ('end', [2., 6., 0.])]:
        atoms = Atoms('H2', positions=[[0, 0, 0], pos])
        atoms.set_constraint(FixAtoms(indices=[0]))
        path = tmp_path / (name + '.traj'); write(path, atoms); paths.append(path)
    output = tmp_path / 'band.traj'
    generate('IDPP', 7, str(paths[0]), str(paths[2]), str(output), None,
             ts_file=str(paths[1]), no_align=True, image_distribution='length')
    band = read(output, ':')
    assert len(band) == 10
    np.testing.assert_array_equal(band[2].positions, read(paths[1]).positions)
    np.testing.assert_array_equal(band[0].positions, read(paths[0]).positions)
    np.testing.assert_array_equal(band[-1].positions, read(paths[2]).positions)
    for frame in band:
        np.testing.assert_array_equal(frame.positions[0], [0, 0, 0])


@pytest.mark.parametrize('with_ts', [False, True])
def test_pd_default_generation_spacing_and_anchor(tmp_path, capsys, with_ts):
    fixture = Path(__file__).resolve().parents[1] / 'data' / 'idpp_pd_flat_fs'
    output = tmp_path / 'pd.traj'
    ts = {'ts_file': str(fixture / 'ts_guess.extxyz')} if with_ts else {}
    generate('IDPP', 7, str(fixture / 'init.extxyz'), str(fixture / 'final.extxyz'),
             str(output), None, no_align=True, **ts)
    assert 'Failed' not in capsys.readouterr().out
    band = read(output, ':')
    assert len(band) == (10 if with_ts else 9)
    lengths = [np.linalg.norm(find_mic(b.positions - a.positions, a.cell, a.pbc)[0])
               for a, b in zip(band[:-1], band[1:])]
    assert max(lengths) / min(lengths) < 1.15
    if with_ts:
        np.testing.assert_array_equal(band[2].positions, read(fixture / 'ts_guess.extxyz').positions)
    initial = read(fixture / 'init.extxyz')
    np.testing.assert_array_equal(band[0].positions, initial.positions)
    np.testing.assert_array_equal(band[-1].positions, read(fixture / 'final.extxyz').positions)
    fixed = initial.constraints[0].get_indices()
    for frame in band[1:-1]:
        np.testing.assert_array_equal(frame.positions[fixed], initial.positions[fixed])
