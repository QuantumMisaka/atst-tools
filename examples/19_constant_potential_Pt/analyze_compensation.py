"""Validate the gate-compensated energy derivative using same-run densities."""
import argparse
import json
from pathlib import Path

import numpy as np

from analyze_scan import read_point, derivative_diagnostics
from atst_tools.utils.gate_compensation import read_gate_compensation


def analyze(directories, tolerance=None, tolerance_reason=None):
    points = []
    for directory in directories:
        p = read_point(directory)
        p.update(read_gate_compensation(directory, p['electrons'], p['reference_electrons']))
        p['mu_conjugate_ev'] = p['E_Fermi']+p['compensation_derivative_ev']
        points.append(p)
    points.sort(key=lambda p:p['electrons'])
    n = np.asarray([p['electrons'] for p in points])
    if len(points) != 5 or not np.allclose(np.diff(n), n[1]-n[0]) or n[1] <= n[0]:
        raise ValueError('Five equally spaced distinct electron numbers are required')
    target = points[2]['mu_conjugate_ev']
    for p in points:
        p['omega_ev'] = p['E_KohnSham']-target*(p['electrons']-p['reference_electrons'])
    derivatives = []
    for offset in (1,2):
        left,right = points[2-offset],points[2+offset]
        h = (right['electrons']-left['electrons'])/2
        derivative = (right['E_KohnSham']-left['E_KohnSham'])/(2*h)
        derivatives.append({'step_electrons':h, 'energy_derivative_ev':derivative,
                            'stationarity_residual_ev':derivative-target})
    diagnostics = derivative_diagnostics([p['step_electrons'] for p in derivatives],
                                        [p['stationarity_residual_ev'] for p in derivatives],
                                        tolerance, tolerance_reason)
    return {'boundary':'compensated_gate', 'target_mu_ev':target,
            'points':points, 'derivatives':derivatives, **diagnostics,
            'limitation':'Energy derivative only; fixed-N and fixed-target forces need separate validation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', nargs=5, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tolerance-ev', type=float)
    parser.add_argument('--tolerance-reason')
    args=parser.parse_args()
    result=analyze(args.directories, args.tolerance_ev, args.tolerance_reason)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('scientific_acceptance','target_mu_ev','derivatives','richardson_residual_ev','diagnostic_criterion')},indent=2))
