"""Run opt-in real fixed-target gate CP evaluations for a nuclear force check.

Run inside an allocated ABACUS environment. This script does not submit jobs
or start an MPI launcher; use the site's existing execution environment.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.units import Bohr

from atst_tools.calculators.abacuslite_backend import Abacus, ATSTAbacusProfile
from atst_tools.calculators.constant_potential import ConstantPotentialCalculator
from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_input, read_stru, read_kpt


def run(source, output, target, displacements, initial=217., tolerance=1e-4, surface='back'):
    source = source.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stru = read_stru(str(source/'STRU'))
    cell = np.asarray(stru['lat']['vec'])*stru['lat']['const']*Bohr
    symbols = [s['symbol'] for s in stru['species'] for _ in s['atom']]
    positions = np.asarray([a['coord'] for s in stru['species'] for a in s['atom']])
    if stru['coord_type'].lower() != 'cartesian':
        raise ValueError('The reference Pt fixture uses Cartesian coordinates')
    atoms = Atoms(symbols, positions=positions*stru['lat']['const']*Bohr, cell=cell, pbc=True)
    atom_index = int(np.argmax(atoms.positions[:,0]) if surface == 'gate' else np.argmin(atoms.positions[:,0]))
    params = read_input(str(source/'INPUT'))
    params.update(out_chg='1 12',cal_force=1,scf_thr=1e-9)
    params.pop('pseudo_dir',None)
    params.pop('orbital_dir',None)
    profile = ATSTAbacusProfile(command='abacus',pseudo_dir=str(source),orbital_dir=str(source),omp_num_threads=8)
    def inner(nelec,directory):
        return Abacus(profile=profile,directory=directory,
                      pseudopotentials={s['symbol']:s['pp_file'] for s in stru['species']},
                      basissets={s['symbol']:s['orb_file'] for s in stru['species'] if 'orb_file' in s} or None,
                      kpts=read_kpt(str(source/'KPT')), **(params|{'nelec':nelec}))
    rows=[]
    for shift in displacements:
        probe=atoms.copy()
        probe.positions[atom_index,0]+=shift
        calc=ConstantPotentialCalculator(inner_factory=inner,potential_v=None,
              reference_electrons=216,initial_electrons=initial,
              energy_boundary='compensated_gate',target_mu_ev=target,
              reference_electrode='custom',potential_tolerance_v=tolerance,
              capacitance_initial=.05,capacitance_unit='e/V',max_iterations=12,
              nelec_min=initial-.5,nelec_max=initial+.5,nelec_step_max=.1,vacuum_axis=0,
              directory=output/f'x{shift:+.3f}')
        probe.calc=calc
        energy=float(probe.get_potential_energy(force_consistent=True))
        forces=probe.get_forces()
        row={'atom_index_1based':atom_index+1,'displacement_angstrom':shift,'omega_ev':energy,'force_ev_ang':float(forces[atom_index,0]),
             'results':calc.results}
        rows.append(row)
        text=json.dumps(rows,indent=2,default=lambda a:a.tolist(),allow_nan=False)+'\n'
        (output/'force_evaluations.json').write_text(text)
        print(json.dumps({k:row[k] for k in ('displacement_angstrom','omega_ev','force_ev_ang')}),flush=True)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--target-mu',type=float,required=True)
    parser.add_argument('--displacements',type=float,nargs='+',default=[0.,-.02,-.01,.01,.02])
    parser.add_argument('--tolerance',type=float,default=1e-4)
    parser.add_argument('--initial-electrons',type=float,default=217.)
    parser.add_argument('--surface',choices=['back','gate'],default='back')
    args=parser.parse_args()
    run(args.source,args.output,args.target_mu,args.displacements,initial=args.initial_electrons,
        tolerance=args.tolerance,surface=args.surface)
