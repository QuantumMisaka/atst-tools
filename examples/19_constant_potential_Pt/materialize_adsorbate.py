"""Materialize two H/Pt endpoints for bounded CP relax/NEB integration checks.

The Pt substrate is fixed. These small Gamma-point fixtures exercise the
workflow; they do not provide a converged physical diffusion barrier.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from materialize import materialize


def materialize_endpoints(destination):
    destination.mkdir(parents=True, exist_ok=False)
    assets = Path(__file__).resolve().parent.parent / 'data'
    for name, y in [('initial', 1.3871108), ('final', 4.1613325)]:
        root = destination / name
        materialize(root, 'lcao', 217.1, dipole=True, block_height=2.)
        pp, orb = 'H_ONCV_PBE-1.0.upf', 'H_gga_6au_100Ry_2s1p.orb'
        for asset in (pp, orb):
            shutil.copy2(assets / asset, root / asset)
        stru = (root/'STRU').read_text()
        stru = stru.replace('Pt 195.078 Pt_ONCV_PBE-1.0.upf',
                            f'Pt 195.078 Pt_ONCV_PBE-1.0.upf\nH 1.008 {pp}')
        stru = stru.replace('Pt_gga_7au_100Ry_4s2p2d1f.orb',
                            f'Pt_gga_7au_100Ry_4s2p2d1f.orb\n{orb}')
        stru = re.sub(r'(?m)\s1\s+1\s+1[ \t]*$', ' 0 0 0', stru)
        stru += f'\nH\n0.0\n1\n10.7302848 {y:.7f} 2.4025463 1 1 1\n'
        (root/'STRU').write_text(stru)
        inp = (root/'INPUT').read_text().replace('nbands 130', 'nbands 136')
        inp += '\nntype 2\n'
        (root/'INPUT').write_text(inp)
        record = json.loads((root/'fixture.json').read_text())
        record.update(neutral_electrons=217, fixed_atom_indices_1based=list(range(1,13)),
                      mobile_atom_indices_1based=[13], endpoint=name)
        record['changes'] += ['Add one H at a top-layer triangle center, 1.2 Angstrom nominal height',
                              'Fix all 12 Pt atoms; only H moves; second endpoint translated by one surface lattice spacing',
                              'H PP/ORB from ATST examples/data; ntype=2 and nbands=136']
        record['sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in root.iterdir() if p.is_file() and p.name != 'fixture.json'}
        (root/'fixture.json').write_text(json.dumps(record,indent=2)+'\n')
    return destination


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    print(materialize_endpoints(parser.parse_args().destination))
