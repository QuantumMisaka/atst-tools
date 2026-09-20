"""Explicit electron-number derivatives of ABACUS 3.10.1 gate compensation.

The gate charge changes with the electronic charge. Consequently the raw
energy's conjugate chemical potential is EF + S_gate + S_dipole, not EF alone
or EF minus an arbitrary vacuum plateau. Formulae follow gatefield.cpp and
efield.cpp. No electrostatic-potential gauge or fitted energy correction is
used here. Geometry is in bohr, density in electrons/bohr**3, outputs in eV.
"""
from __future__ import annotations

import numpy as np
from pathlib import Path

ABACUS_RY_EV = 13.605698


def _read_density_cube(path):
    """Read the ABACUS periodic cube without lossy geometry unit conversion."""
    with Path(path).open() as stream:
        stream.readline()
        stream.readline()
        origin_row = stream.readline().split()
        nat = int(origin_row[0])
        origin = np.asarray(origin_row[1:4], float)
        grid = np.asarray([stream.readline().split() for _ in range(3)], float)
        if nat <= 0 or grid.shape != (3, 4) or np.any(grid[:, 0] <= 0):
            raise ValueError('Expected an ABACUS density cube in bohr')
        shape = tuple(int(n) for n in grid[:, 0])
        if not np.array_equal(grid[:, 0], shape):
            raise ValueError('Invalid cube grid dimensions')
        atoms = np.asarray([stream.readline().split() for _ in range(nat)], float)
        values = np.fromstring(stream.read(), sep=' ')
    if origin.shape != (3,) or np.any(origin != 0) or atoms.shape != (nat, 5):
        raise ValueError('Unsupported cube origin or atom records')
    if values.size != int(np.prod(shape)) or not np.isfinite(values).all():
        raise ValueError('Truncated or non-finite density cube')
    return values.reshape(shape), grid[:, 1:]*np.asarray(shape)[:, None], atoms


def read_gate_compensation(directory, nelec, reference_electrons):
    """Read the compensation derivative from a completed ABACUS evaluation.

    Uses the exact input STRU geometry and high-precision density samples.
    Cube valences are the pseudopotential charges printed by this ABACUS run;
    they must reproduce the declared neutral reference. The caller establishes
    SCF convergence and evaluation-directory identity before invoking this.
    """
    from ase.data import atomic_numbers
    from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_input, read_stru

    root = Path(directory)
    params = read_input(str(root/'INPUT'))
    def flag(key):
        value = str(params.get(key, '0')).lower()
        if value in ('1', 'true', '.true.'): return True
        if value in ('0', 'false', '.false.'): return False
        raise ValueError(f'Invalid boolean {key}: {value}')
    if not flag('gate_flag') or flag('imp_sol'):
        raise ValueError('compensated_gate requires gate_flag and no implicit solvent')
    dipole = flag('dip_cor_flag')
    if flag('efield_flag') != dipole or float(params.get('efield_amp', 0)) != 0:
        raise ValueError('Only zero external field with paired dipole flags is supported')
    declared_nelec = float(params.get('nelec', 'nan'))
    if (not np.isfinite(declared_nelec) or not np.isfinite(nelec)
            or not np.isfinite(reference_electrons)
            or abs(declared_nelec-nelec) > 1e-9):
        raise ValueError('INPUT electron number differs from the evaluated state')
    if dipole and any(key not in params or not np.isfinite(float(params[key]))
                       or float(params[key]) < 0
                       for key in ('efield_pos_max', 'efield_pos_dec')):
        raise ValueError('Explicit fixed dipole position and width are required')
    precision = str(params.get('out_chg', '')).split()
    if len(precision) != 2 or int(precision[0]) != 1 or int(precision[1]) < 10:
        raise ValueError('compensated_gate requires out_chg 1 10 or higher precision')
    stru = read_stru(str(root/params.get('stru_file', 'STRU')))
    cell = np.asarray(stru['lat']['vec'], float)*float(stru['lat']['const'])
    coordinates = np.asarray([a['coord'] for s in stru['species'] for a in s['atom']], float)
    kind = stru['coord_type'].lower()
    if kind == 'direct':
        frac = coordinates
    elif kind == 'cartesian':
        frac = coordinates*float(stru['lat']['const']) @ np.linalg.inv(cell)
    elif kind == 'cartesian_angstrom':
        frac = coordinates/.5291770 @ np.linalg.inv(cell)
    else:
        raise ValueError(f'Unsupported STRU coordinates for compensation: {kind}')
    numbers = np.asarray([atomic_numbers[s['symbol']] for s in stru['species'] for _ in s['atom']])
    out = root/f"OUT.{params.get('suffix', 'ABACUS')}"
    spin = int(params.get('nspin', 1))
    if spin not in (1, 2) or 'nupdown' in params or flag('two_fermi'):
        raise ValueError('Compensation supports nspin 1 or common-Fermi nspin 2')
    rho = None
    valences = None
    for index in range(1, spin+1):
        data, cube_cell, atoms = _read_density_cube(out/f'SPIN{index}_CHG.cube')
        # Cube grid vectors and atom positions are serialized to six decimals.
        grid_tolerance = max(data.shape)*.51e-6
        if not np.allclose(cube_cell, cell, rtol=0, atol=grid_tolerance):
            raise ValueError('Density cube cell differs from STRU')
        if len(atoms) != len(numbers) or not np.array_equal(atoms[:, 0], numbers):
            raise ValueError('Density cube atomic identity differs from STRU')
        diff = atoms[:, 2:] @ np.linalg.inv(cell)-frac
        diff -= np.rint(diff)
        if not np.allclose(diff @ cell, 0, rtol=0, atol=2e-6):
            raise ValueError('Density cube atomic positions differ from STRU')
        if valences is not None and not np.array_equal(valences, atoms[:, 1]):
            raise ValueError('Spin density valences differ')
        valences = atoms[:, 1]
        if rho is None:
            rho = data
        elif rho.shape == data.shape:
            rho += data
        else:
            raise ValueError('Spin density grids differ')
    if abs(float(np.sum(valences))-reference_electrons) > 1e-6:
        raise ValueError('reference_electrons differs from actual PP total valence')
    # Scientific notation with p digits after the decimal has a relative
    # rounding bound 0.5*10**(-p). Add a conservative floating-sum bound;
    # this is a serialization/identity check, not a physical SCF tolerance.
    absolute_charge = float(np.sum(np.abs(rho))*abs(np.linalg.det(cell))/rho.size)
    eps = np.finfo(float).eps
    gamma = rho.size*eps/(1-rho.size*eps)
    electron_tolerance = (.5*10.**(-int(precision[1]))+gamma+8*eps)*absolute_charge
    result = compensation_terms(rho, cell, frac, valences, nelec,
                              axis=int(params.get('efield_dir', 2)),
                              zgate=float(params.get('zgate', .5)), dipole=dipole,
                              dipole_max=float(params.get('efield_pos_max', .5)),
                              dipole_width=float(params.get('efield_pos_dec', .1)),
                              electron_tolerance=electron_tolerance)
    result['density_precision'] = int(precision[1])
    result['density_electron_tolerance'] = electron_tolerance
    return result


def gate_shape(x, zgate):
    """Periodic gate Green function, matching Gatefield::mopopla."""
    s = (np.asarray(x)-zgate+.5) % 1-.5
    return 1/6-np.abs(s)+s*s


def saw_shape(x, maximum, width):
    """Unit sawtooth matching Efield::saw_function, including its offset."""
    x = np.asarray(x) % 1
    return np.where(x <= maximum, x-maximum+.5*(1-width),
                    np.where(x > maximum+width,
                             x-maximum-1+.5*(1-width),
                             .5*(1-width)-(1-width)*(x-maximum)/width))


def compensation_terms(density, cell_bohr, fractional_positions, valences,
                       nelec, *, axis, zgate, dipole=False, dipole_max=.5,
                       dipole_width=.1, electron_tolerance=None):
    """Integrate explicit gate/dipole derivatives from a same-run density.

    Supports the fixed-cell, zero-applied-field compensating-gate boundary.
    The caller must bind the arrays to one converged SCF evaluation and check
    its INPUT/PP identities. Density is never silently renormalized.
    """
    rho = np.asarray(density, dtype=float)
    cell = np.asarray(cell_bohr, dtype=float)
    frac = np.asarray(fractional_positions, dtype=float)
    charges = np.asarray(valences, dtype=float)
    if (rho.ndim != 3 or min(rho.shape) < 1 or cell.shape != (3, 3)
            or frac.shape != (len(charges), 3) or charges.ndim != 1
            or not all(np.isfinite(v).all() for v in (rho, cell, frac, charges))
            or not np.isfinite(nelec) or nelec <= 0):
        raise ValueError('Invalid finite density, geometry or electron number')
    if axis not in (0, 1, 2) or not np.isfinite(zgate) or not 0 <= zgate < 1:
        raise ValueError('Invalid gate axis or fractional position')
    if np.any(charges <= 0):
        raise ValueError('Positive valences are required')
    volume = abs(float(np.linalg.det(cell)))
    other = [i for i in range(3) if i != axis]
    area = np.linalg.norm(np.cross(cell[other[0]], cell[other[1]]))
    if volume <= 0 or area <= 0:
        raise ValueError('Compensated gate requires a nondegenerate periodic cell')
    height = volume/area
    # First supported geometry has a normal axis; in-plane skew is allowed.
    if any(abs(np.dot(cell[axis], cell[j])) > 1e-8*np.linalg.norm(cell[axis])*np.linalg.norm(cell[j]) for j in other):
        raise ValueError('Gate axis must be normal to the slab plane')
    weight = volume/rho.size
    if electron_tolerance is None:
        eps = np.finfo(float).eps
        gamma = rho.size*eps/(1-rho.size*eps)
        electron_tolerance = (gamma+8*eps)*float(np.sum(np.abs(rho))*weight)
    if not np.isfinite(electron_tolerance) or electron_tolerance <= 0:
        raise ValueError('A positive finite electron tolerance is required')
    integrated = float(np.sum(rho)*weight)
    if abs(integrated-nelec) > electron_tolerance:
        raise ValueError(f'Density electron count {integrated:.12g} differs from {nelec:.12g}')
    positions = frac[:, axis] % 1
    if np.any(np.abs((positions-zgate+.5) % 1-.5) < 1e-8):
        raise ValueError('An ion lies on the gate plane')
    x = np.arange(rho.shape[axis], dtype=float)/rho.shape[axis]
    planar = np.sum(rho, axis=tuple(other))
    d = float(nelec-np.sum(charges))
    ion = float(charges @ gate_shape(positions, zgate))
    electron = float(planar @ gate_shape(x, zgate)*weight)
    sg = 4*np.pi*height/area*(ion-electron+d/6)*ABACUS_RY_EV
    sd = 0.
    total_dipole = 0.
    if dipole:
        if (not np.isfinite(dipole_max) or not np.isfinite(dipole_width)
                or not 0 < dipole_width < 1 or not 0 <= dipole_max
                or dipole_max+dipole_width > 1):
            raise ValueError('Invalid dipole sawtooth interval')
        if np.any((positions >= dipole_max) & (positions <= dipole_max+dipole_width)):
            raise ValueError('Ions in the dipole return region have unsupported forces')
        moment = float(charges @ saw_shape(positions, dipole_max, dipole_width))
        moment += d*float(saw_shape(zgate, dipole_max, dipole_width))
        moment -= float(planar @ saw_shape(x, dipole_max, dipole_width)*weight)
        total_dipole = 4*np.pi*height/volume*moment
        sd = 2*total_dipole*height*float(saw_shape(zgate, dipole_max, dipole_width))*ABACUS_RY_EV
    return {'gate_derivative_ev': float(sg), 'dipole_derivative_ev': float(sd),
            'compensation_derivative_ev': float(sg+sd),
            'integrated_electrons': integrated,
            'density_electron_error': integrated-float(nelec),
            'ionic_valence_electrons': float(np.sum(charges)),
            'total_dipole_ry_au': float(total_dipole),
            'boundary': 'compensated_gate'}
