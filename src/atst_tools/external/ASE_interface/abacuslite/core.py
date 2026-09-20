# fmt: off

'''
here the ase-abacus implementation is pasted and modified. 
Source:
https://gitlab.com/1041176461/ase-abacus/-/blob/master/ase/calculators/abacus.py

This module defines an ASE interface to ABACUS.
Created on Fri Jun  8 16:33:38 2018

ABACUS (Atomic-orbital Based Ab-initio Computation at UStc) is an open-source 
package based on density functional theory (DFT). The package utilizes both plane 
wave and numerical atomic basis sets with the usage of pseudopotentials to describe 
the interactions between nuclear ions and valence electrons. ABACUS supports LDA, 
GGA, meta-GGA, and hybrid functionals. Apart from single-point calculations, 
the package allows geometry optimizations and ab-initio molecular dynamics with 
various ensembles. The package also provides a variety of advanced functionalities 
for simulating materials, including the DFT+U, VdW corrections, and implicit solvation
model, etc. In addition, ABACUS strives to provide a general infrastructure to 
facilitate the developments and applications of novel machine-learning-assisted 
DFT methods (DeePKS, DP-GEN, DeepH, DeePTB etc.) in molecular and material simulations.

Modified on Wed Jun 20 15:00:00 2018
@author: Shen Zhen-Xiong

Modified on Wed Jun 03 23:00:00 2022
@author: Ji Yu-yang

Refactored from Sun Dec 07 21:41 2025
@author: Huang Yi-ke
'''

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional, List

import numpy as np
from ase.calculators.genericfileio import (
    BaseProfile,
    CalculatorTemplate,
    GenericFileIOCalculator,
    read_stdout
)
from ase.atoms import Atoms
from ase.dft.kpoints import BandPath
from ase.io import read

from .io.generalio import (
    file_safe_backup,
    read_input,
    read_stru,
    read_kpt,
    species_group_indices,
    write_input,
    write_stru,
    write_kpt
)

__LEGACYIO__ = True
def switch_io_backend_version(version: str) -> bool:
    '''determine if the i/o is in legacy format by the version number,
    for detailed discussion, see issue #7260
    '''
    global __LEGACYIO__
    m = re.match(r'^v(\d+)\.(\d+)\.(\d+)(\.\d+|\-(alpha|beta|rc)\.\d+|\-(alpha|beta|rc)\d+)?$', version)
    assert m, f'Invalid format of version number, please check file version.h'
    assert int(m.group(1)) >= 3, f'ABACUS v2.x is not supported'
    if int(m.group(2)) >= 11:
        __LEGACYIO__ = False
    elif int(m.group(2)) == 9:
        if m.group(4) is not None:
            # it is also possible to divide the version more carefully,
            # but because 3.9.0.x are all on the develop branch, up to
            # now, there is no user submit issue to request such a careful
            # division
            __LEGACYIO__ = False
    else:
        __LEGACYIO__ = True
    return __LEGACYIO__

class AbacusProfile(BaseProfile):
    '''AbacusProfile for interacting the ASE with ABACUS that installed in
    the practical system'''
    configvars = {'pseudo_dir', 'orbital_dir'}

    def __init__(self, 
                 command: str, 
                 pseudo_dir: Optional[str | Path] = None, 
                 orbital_dir: Optional[str | Path] = None, 
                 omp_num_threads: Optional[int] = None,
                 **kwargs):
        '''Initialize ABACUS profile.
        
        Parameters
        ----------
        command : str
            The command to run ABACUS. NOTE: there may be the case for some
            sophisticated ABACUS user they call ABACUS with command like
            `OMP_NUM_THREADS=1 mpirun -np X abacus`. Here please do not set
            the number of omp threads in `command`, instead, use `nomp=1`.
        pseudo_dir : str or Path, optional
            The directory containing pseudopotential files.
        orbital_dir : str or Path, optional
            The directory containing orbital basis files. This is only necessary
            for an ABACUS-LCAO calculation
        omp_num_threads : int, optional
            The number of omp threads to use.
        '''
        assert isinstance(command, str)
        # further validation on the command will be in the __init__ of
        # the base class
        super().__init__(command, **kwargs)
        self.pseudo_dir  = pseudo_dir
        self.orbital_dir = orbital_dir

        if omp_num_threads is not None:
            # set the number of omp threads for the present process
            assert isinstance(omp_num_threads, int)
            os.environ['OMP_NUM_THREADS'] = str(omp_num_threads)

    @staticmethod
    def parse_version(stdout) -> str:
        # up to the ABACUS version v3.9.0.17, the run of command
        # `abacus --version` would returns the information organized
        # in the following way:
        # ABACUS version v3.9.0.17
        return re.match(r'ABACUS version (\S+)', stdout).group(1)

    def get_calculator_command(self, inputfile) -> List[str]:
        # because ABACUS run in the folder where there are INPUT files, so the
        # additional inputfile argument is not used.
        return []

    def version(self) -> str:
        '''get the abacus version information'''
        cmd_ = [*self._split_command, '--version']
        return AbacusProfile.parse_version(read_stdout(cmd_))


def _validate_atomorder(atomorder, natoms, stru_path):
    """Validate the species-to-ASE permutation before handing it to a parser."""
    if atomorder is None:
        return list(range(natoms))

    try:
        values = list(atomorder)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"scf atomorder 无法解析（STRU: {stru_path}；期望 {natoms} 个整数索引；"
            f"fail-closed）"
        ) from exc

    valid_integer = all(
        isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))
        for value in values
    )
    if (
        len(values) != natoms
        or not valid_integer
        or sorted(values) != list(range(natoms))
    ):
        raise RuntimeError(
            f"scf atomorder 非法（STRU: {stru_path}；收到 {values!r}，"
            f"期望 {natoms} 个从 0 到 {max(natoms - 1, 0)} 的唯一索引；fail-closed）"
        )
    return [int(value) for value in values]


def _invert_cell(cell, context):
    """Return a cell inverse or raise a diagnostic validation error."""
    try:
        return np.linalg.solve(cell, np.eye(3, dtype=float))
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"singular cell in {context}") from exc


def _read_stru_reference(directory, stru_file, atomorder, log_path=None):
    """Normalize STRU coordinates, cell, symbols, and mapping for SCF matching."""
    from ase.units import Bohr
    from .io.generalio import read_stru

    stru_path = Path(directory) / (stru_file or 'STRU')
    try:
        stru = read_stru(stru_path)
        species = stru['species']
        lat = stru['lat']
        coord_type = str(stru['coord_type']).lower()
        raw_symbols = []
        raw_coords = []
        for species_entry in species:
            symbol = species_entry['symbol']
            atoms = species_entry['atom']
            declared_natoms = species_entry['natom']
            if declared_natoms != len(atoms):
                raise ValueError(
                    f"STRU species {symbol!r} declared natom={declared_natoms}, "
                    f"but contains {len(atoms)} atom records"
                )
            for atom in atoms:
                raw_symbols.append(str(symbol))
                raw_coords.append(atom['coord'])

        natoms = len(raw_symbols)
        mapping = _validate_atomorder(atomorder, natoms, stru_path)
        coordinates = np.asarray(raw_coords, dtype=float)
        if coordinates.shape != (natoms, 3):
            raise ValueError(
                f"STRU positions shape {coordinates.shape}, expected ({natoms}, 3)"
            )
        if not np.isfinite(coordinates).all():
            raise ValueError("non-finite STRU positions")

        lattice_vectors = np.asarray(lat['vec'], dtype=float)
        if lattice_vectors.shape != (3, 3):
            raise ValueError(
                f"STRU cell shape {lattice_vectors.shape}, expected (3, 3)"
            )
        lattice_constant = float(lat['const'])
        cell = lattice_vectors * lattice_constant * Bohr
        if not np.isfinite(cell).all():
            raise ValueError("non-finite STRU cell")
        cell_inverse = _invert_cell(cell, f"STRU {stru_path}")

        if coord_type.startswith('d'):
            positions_species = coordinates @ cell
        elif coord_type.startswith('c'):
            positions_species = coordinates * lattice_constant * Bohr
        else:
            raise ValueError(f"unsupported STRU coordinate type {stru['coord_type']!r}")
        if not np.isfinite(positions_species).all():
            raise ValueError("non-finite normalized STRU positions")
    except RuntimeError:
        raise
    except (
        AssertionError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        IndexError,
        np.linalg.LinAlgError,
    ) as exc:
        suffix = f"；log: {log_path}" if log_path is not None else ""
        raise RuntimeError(
            f"scf STRU 身份信息无效（STRU: {stru_path}{suffix}；{exc}；fail-closed）"
        ) from exc

    return {
        'path': stru_path,
        'positions': np.asarray(positions_species, dtype=float)[mapping].copy(),
        'cell': np.asarray(cell, dtype=float).copy(),
        'cell_inverse': np.asarray(cell_inverse, dtype=float).copy(),
        'symbols': [raw_symbols[index] for index in mapping],
        'atomorder': mapping,
    }


def _stru_positions_in_ase_order(directory, stru_file, atomorder):
    """Return normalized STRU positions for compatibility with existing callers."""
    return _read_stru_reference(directory, stru_file, atomorder)['positions']


def _frame_coordinate_is_direct(log_path):
    """从 running log 的实际坐标头推导帧侧坐标系，不依赖 STRU 的 coord_type。

    read_abacus_out 对 DIRECT 日志返回分数坐标、对 CARTESIAN 日志返回 Cartesian（原样），
    因此帧侧换算必须以日志实际坐标系为准（spec P3 ③）。STRU 的 coord_type 可能与日志不一致
    （如 write_stru 默认写 Cartesian STRU 而 ABACUS 打印坐标可仍为 DIRECT），不能作为
    帧侧坐标系依据（fix round 1 F1）。坐标头格式两后端一致，取 backend 的
    read_traj_from_running_log 的 `coordinate` 字段（与 read_abacus_out 同解析器，单一事实源）。
    """
    global __LEGACYIO__
    if __LEGACYIO__:
        from .io.legacyio import read_traj_from_running_log
    else:
        from .io.latestio import read_traj_from_running_log
    traj = read_traj_from_running_log(log_path)
    return str(traj[0]['coordinate']).lower().startswith('d')


def _validate_raw_scf_trajectory(log_path, expected):
    """Check raw trajectory cardinality before parser atom reordering."""
    global __LEGACYIO__
    if __LEGACYIO__:
        from .io.legacyio import read_traj_from_running_log
    else:
        from .io.latestio import read_traj_from_running_log

    try:
        trajectory = read_traj_from_running_log(log_path)
        if not trajectory:
            raise ValueError("no raw trajectory frames")
        expected_shape = expected['positions'].shape
        expected_natoms = len(expected['symbols'])
        for frame_index, frame in enumerate(trajectory):
            coords = np.asarray(frame['coords'], dtype=float)
            if coords.shape != expected_shape:
                mismatch = (
                    f"atom count {coords.shape[0]}, expected {expected_shape[0]}; "
                    if coords.ndim >= 1 and coords.shape[0] != expected_shape[0]
                    else ""
                )
                raise ValueError(
                    f"frame {frame_index} {mismatch}positions shape {coords.shape}, "
                    f"expected {expected_shape}"
                )
            if not np.isfinite(coords).all():
                raise ValueError(f"frame {frame_index} positions are non-finite")
            elements = np.asarray(frame['elem'])
            if elements.ndim != 1 or len(elements) != expected_natoms:
                raise ValueError(
                    f"frame {frame_index} atom count {len(elements)}, "
                    f"expected {expected_natoms}"
                )
            cell = np.asarray(frame['cell'], dtype=float)
            if cell.shape != (3, 3):
                raise ValueError(
                    f"frame {frame_index} cell shape {cell.shape}, expected (3, 3)"
                )
            if not np.isfinite(cell).all():
                raise ValueError(f"frame {frame_index} cell is non-finite")
            _invert_cell(cell, f"frame {frame_index}")
    except RuntimeError:
        raise
    except (AssertionError, KeyError, OSError, TypeError, ValueError, IndexError) as exc:
        raise RuntimeError(
            f"scf running log 原始帧校验失败：{log_path}（{exc}；fail-closed）"
        ) from exc
    return trajectory


def _normalize_scf_frame(frame, frame_index, expected, frame_is_direct, atol):
    """Normalize one parser frame and return match diagnostics.

    A finite, well-shaped frame with a different position or cell is a valid
    candidate mismatch. Malformed data is represented as ``ValueError`` so the
    caller can validate every frame before selecting any one of them.
    """
    context = f"frame {frame_index}"
    try:
        symbols = list(frame.get_chemical_symbols())
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{context} symbols are unavailable") from exc
    if len(symbols) != len(expected['symbols']):
        raise ValueError(
            f"{context} atom count {len(symbols)}, expected {len(expected['symbols'])}"
        )
    if symbols != expected['symbols']:
        raise ValueError(
            f"{context} symbols {symbols!r} do not match STRU symbols "
            f"{expected['symbols']!r}"
        )

    try:
        positions = np.asarray(frame.positions, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} positions cannot be converted to float") from exc
    if positions.shape != expected['positions'].shape:
        raise ValueError(
            f"{context} positions shape {positions.shape}, expected "
            f"{expected['positions'].shape}"
        )
    if not np.isfinite(positions).all():
        raise ValueError(f"{context} positions are non-finite")

    try:
        cell = np.asarray(frame.cell, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} cell cannot be converted to float") from exc
    if cell.shape != (3, 3):
        raise ValueError(f"{context} cell shape {cell.shape}, expected (3, 3)")
    if not np.isfinite(cell).all():
        raise ValueError(f"{context} cell is non-finite")
    cell_inverse = _invert_cell(cell, context)

    frame_cart = positions @ cell if frame_is_direct else positions.copy()
    if not np.isfinite(frame_cart).all():
        raise ValueError(f"{context} normalized Cartesian positions are non-finite")
    cell_delta = cell - expected['cell']
    cell_diff = float(np.max(np.abs(cell_delta)))
    same_cell = bool(np.allclose(cell, expected['cell'], atol=atol, rtol=0.0))
    if not same_cell:
        return {
            'frame': frame,
            'frame_index': frame_index,
            'frame_cart': frame_cart,
            'cell_diff': cell_diff,
            'periodic_residual': None,
            'matches': False,
        }

    delta_frac = (frame_cart - expected['positions']) @ cell_inverse
    periodic_cart = (delta_frac - np.rint(delta_frac)) @ cell
    if not np.isfinite(periodic_cart).all():
        raise ValueError(f"{context} periodic residual is non-finite")
    periodic_residual = float(np.max(np.abs(periodic_cart)))
    return {
        'frame': frame,
        'frame_index': frame_index,
        'frame_cart': frame_cart,
        'cell_diff': cell_diff,
        'periodic_residual': periodic_residual,
        'matches': periodic_residual <= atol,
    }


def _select_scf_frame_for_structure(
    frames, log_path, directory, atomorder, atol=1e-4, stru_file='STRU', _reference=None
):
    """Return the latest periodic-equivalent frame; malformed SCF data fails closed.

    Parameters
    ----------
    frames : list of Atoms
        按 atomorder 重排后的 running log 帧（read_abacus_out 返回）。
    log_path : Path
        running log 路径，用于 fail-closed 异常诊断。
    directory : Path
        工作目录（含本次 write_input 落盘的 STRU）。
    atomorder : list of int
        species 序位置 -> ASE 序原子的 revmap（spec P3 ①）。
    stru_file : str or Path
        The STRU filename recorded by ``write_input``; defaults to ``STRU``.
    atol : float
        绝对 Å 容差（spec P3 ③，按坐标打印精度取 ~1e-4 Å 量级）。

    Raises
    ------
    RuntimeError
        无与当前 STRU 坐标匹配的帧（异常含 log 路径、帧数与坐标差异摘要）。
    """
    try:
        nframes = len(frames)
    except TypeError as exc:
        raise RuntimeError(
            f"scf running log 帧集合无效：{log_path}（无法读取帧数；fail-closed）"
        ) from exc
    if nframes == 0:
        raise RuntimeError(
            f"scf running log 无帧：{log_path}（共 0 帧；atol={atol}；fail-closed）"
        )
    if not np.isfinite(atol) or atol < 0:
        raise RuntimeError(f"scf 帧匹配 atol 无效：{atol!r}（fail-closed）")

    expected = _reference or _read_stru_reference(
        directory, stru_file, atomorder, log_path=log_path
    )
    try:
        frame_is_direct = _frame_coordinate_is_direct(log_path)
    except Exception as exc:
        raise RuntimeError(
            f"scf running log 坐标头无法解析：{log_path}（{exc}；fail-closed）"
        ) from exc

    normalized = []
    invalid = []
    for frame_index, frame in enumerate(frames):
        try:
            normalized.append(
                _normalize_scf_frame(
                    frame, frame_index, expected, frame_is_direct, atol
                )
            )
        except (AttributeError, TypeError, ValueError, IndexError) as exc:
            invalid.append(f"frame {frame_index}: {exc}")

    if invalid:
        details = "; ".join(invalid)
        raise RuntimeError(
            f"scf running log 含损坏帧：{log_path}（共 {nframes} 帧；{details}；"
            f"atol={atol}；fail-closed）"
        )

    for info in reversed(normalized):
        if info['matches']:
            return info['frame']

    last = normalized[-1]
    raw_diff = float(
        np.max(np.abs(last['frame_cart'] - expected['positions']))
    )
    periodic = (
        f"{last['periodic_residual']:.6g} Å"
        if last['periodic_residual'] is not None
        else "n/a (cell mismatch)"
    )
    raise RuntimeError(
        f"scf running log 无与当前结构匹配的帧：{log_path}（共 {nframes} 帧；"
        f"末帧 raw Cartesian Å 最大差异 {raw_diff:.6g}；"
        f"periodic residual={periodic}；cell 最大差异={last['cell_diff']:.6g} Å；"
        f"atol={atol}；fail-closed）"
    )


class AbacusTemplate(CalculatorTemplate):
    
    implemented_properties = [
        'energy', 'forces', 'stress', 'free_energy', 'magmom'
    ]
    _label = 'abacus'

    def __init__(self):
        super().__init__(
            'abacus',
            self.implemented_properties
        )
        self.non_convergence_ok = False
        # the redirect stdout and stderr
        self.inputname  = 'INPUT' # hard-coded
        self.outputname = f'{self._label}.out'
        self.errorname  = f'{self._label}.err'

        # fix: inconsistent atoms order may induce bugs, here a list
        # is kept to swap the order of atoms
        self.atomorder  = None
        # Keep the STRU filename used by write_input for the matching pass in
        # read_results.  A template used without write_input retains STRU.
        self.stru_file = 'STRU'

    '''because it may be not one-to-one mapping between the property
    desired to calculate and the keywords used in the calculation,
    in the following a series of functions for mapping the property
    calculation to the keywords settings are implemented'''
    @staticmethod
    def get_energy_keywords(self) -> Dict[str, str]:
        return {}

    @staticmethod
    def get_forces_keywords(self) -> Dict[str, str]:
        return {'cal_force': '1'}
    
    @staticmethod
    def get_stress_keywords(self) -> Dict[str, str]:
        return {'cal_stress': '1'}

    @staticmethod
    def get_free_energy_keywords(self) -> Dict[str, str]:
        return {}

    @staticmethod
    def get_magmom_keywords(self) -> Dict[str, str]:
        return {'nspin': '2'}

    def get_property_keywords(self,
                              parameters: Dict[str, str],
                              properties: List[str]) -> Dict[str, str]:
        '''Connect the relationship between the properties calculation and
        the ABACUS keywords. May be more complicated in the future, therefore
        it is better to have a separate mapping function instead of
        implementing in some other functions.
        
        Parameters
        ----------
        parameters : dict
            The parameters used to perform the calculation.
        properties : list of str
            The list of properties to calculate
        '''
        def keyword_compare_value(value):
            if isinstance(value, bool):
                return '1' if value else '0'
            if isinstance(value, (list, tuple, set)):
                return ' '.join(str(i) for i in value)
            return str(value)

        param_cache_ = {
            key: keyword_compare_value(value)
            for key, value in parameters.items()
            if value is not None
        }

        def counter(param_new: Dict[str, str]) -> Dict[str, str]:
            info = 'desired properties or explicit parameters required contradictory keywords'
            staged = {}
            for k, v in param_new.items():
                if v is None:
                    continue
                normalized_value = keyword_compare_value(v)
                if k in param_cache_ and param_cache_[k] != normalized_value:
                    raise ValueError(f'{info}: {k}={v} (now), {param_cache_[k]} (before)')
                staged[k] = normalized_value
            param_cache_.update(staged)
            return param_new

        for p in properties:
            assert p in self.implemented_properties
            parameters.update(counter(getattr(self, f'get_{p}_keywords')(parameters)))

        self.suffix = parameters.get('suffix', 'ABACUS')
        self.calculation = parameters.get('calculation', 'scf')
        return parameters

    def write_input(self, 
                    profile: AbacusProfile, 
                    directory: Path | str,
                    atoms: Atoms, 
                    parameters: Dict[str, str],
                    properties: List[str]) -> None:
        '''Write the input files for the calculation. This function connects
        the calculation in ASE language (atoms, properties, assisted by the
        parameters) to the input files of ABACUS.

        Parameters
        ----------
        profile : AbacusProfile
            The profile used to perform the calculation.
        directory : Path
            The working directory to store the input files.
        atoms : Atoms
            The atoms object to perform the calculation on. Because 
        parameters: dict
            The parameters used to perform the calculation.
        properties: list of str
            The list of properties to calculate
        '''
        # directory
        directory = Path(directory)
        directory.mkdir(exist_ok=True, parents=True)

        # copy the `parameters` because later we will modify it
        parameters = parameters.copy()
        self.stru_file = parameters.get('stru_file', 'STRU') or 'STRU'

        # STRU
        _ = file_safe_backup(directory / self.stru_file)
        # group atoms by first-occurrence species order. Keep the reverse map so
        # that we will recover the order in function read_results()
        ind = species_group_indices(atoms.get_chemical_symbols())
        self.atomorder = sorted(range(len(atoms)), key=lambda i: ind[i]) # revmap
        # then we write
        _ = write_stru(atoms[ind], 
                       outdir=directory,
                       pp_file=parameters.get('pseudopotentials'),
                       orb_file=parameters.get('basissets'),
                       fname=self.stru_file)

        # KPT, if needed
        if 'kpts' in parameters:
            _ = file_safe_backup(directory / parameters.get('kpoint_file', 'KPT'))
            _ = write_kpt(parameters['kpts'], 
                          directory / parameters.get('kpoint_file', 'KPT'))
        # should this function be responsible for checking the integrity
        # of information provided by the user? There may be the case that
        # user provides incomplete information, such that the ABACUS cannot
        # run with parameters.

        # INPUT
        # after writing the KPT and STRU, delete them from the parameters
        _ = parameters.pop('kpts', None)

        _ = parameters.pop('pseudopotentials', None)
        parameters.update({'pseudo_dir': profile.pseudo_dir})

        _ = parameters.pop('basissets', None)
        parameters.update({'orbital_dir': profile.orbital_dir})
        # update the parameters respect to the properties desired
        parameters = self.get_property_keywords(parameters, properties)
        # postprocess on the parameters: convert the key and values
        # from any to string. For the case where the value is a 
        # array, convert to the string spaced by whitespace
        for k, v in parameters.items():
            # if the v is iterable, convert to the string spaced by whitespace
            if isinstance(v, (list, tuple, set)):
                parameters[k] = ' '.join(str(i) for i in v)
        dst = directory / self.inputname
        _ = file_safe_backup(dst)
        # remove possible key-value pairs whose value is None
        parameters = {k: v for k, v in parameters.items() if v is not None}

        # FIXME: only support the ksdft esolver_type presently
        if parameters.get('esolver_type', 'ksdft') != 'ksdft':
            raise NotImplementedError(
                'ABACUS Lite only supports the ksdft esolver_type presently, '
                'which means the ABACUS should always be used as a DFT '
                'calculator. For other forcefields that ABACUS supports '
                'such as the LJ, DP, etc., please either use the ABACUS '
                'directly, or the implementation of interfaces to ASE '
                'directly.'
            )

        # write the INPUT file to the target directory
        _ = write_input(parameters, dst)

    def execute(self, 
                directory: Path | str, 
                profile: AbacusProfile):
        '''Execute the ABACUS Lite calculation.

        Parameters
        ----------
        directory : Path or str
            The working directory to store the input files.
        profile : AbacusProfile
            The profile used to perform the calculation.

        Raises
        ------
        SubprocessError
            If the ABACUS Lite calculation fails.
        '''
        from subprocess import SubprocessError
        try:
            profile.run(directory=directory, 
                        inputfile=None, 
                        outputfile=self.outputname, 
                        errorfile=self.errorname)
        except SubprocessError:
            message = ['ABACUS Lite calculation failed']
            with open(directory / self.outputname, 'r') as f:
                message.append(f.read())
            with open(directory / self.errorname, 'r') as f:
                message.append(f.read())
            raise SubprocessError('\n'.join(message))

    def read_results(self, directory) -> Dict:
        '''the function that returns the desired properties in dict'''
        global __LEGACYIO__
        if __LEGACYIO__:
            from .io.legacyio import read_abacus_out
        else:
            from .io.latestio import read_abacus_out

        directory = Path(directory)
        outdir = directory / f'OUT.{self.suffix}'
        log = outdir / f'running_{self.calculation}.log'
        stru_file = getattr(self, 'stru_file', 'STRU') or 'STRU'
        reference = None
        parser_atomorder = self.atomorder
        if self.calculation == 'scf':
            # Read and validate STRU/mapping before passing sort_atoms_with to
            # the parser; otherwise a malformed mapping leaks a bare IndexError.
            reference = _read_stru_reference(
                directory, stru_file, self.atomorder, log_path=log
            )
            # Validate raw parser cardinality before sort_atoms_with can slice
            # away an extra/missing atom and make a corrupt frame look valid.
            _validate_raw_scf_trajectory(log, reference)
            parser_atomorder = None if self.atomorder is None else reference['atomorder']

        # 读取全部帧；scf 下按坐标选择当前结构帧，非 scf（relax/md）保持末帧语义（spec R1/R2）
        try:
            frames = read_abacus_out(log, sort_atoms_with=parser_atomorder)
        except (IndexError, AssertionError, KeyError, TypeError, ValueError) as exc:
            if self.calculation != 'scf':
                raise
            raise RuntimeError(
                f"scf running log parser failed：{log}（atomorder/帧结构解析错误："
                f"{exc}；fail-closed）"
            ) from exc
        if not frames:
            raise RuntimeError(f"no ABACUS running-log frames in {log}")
        if self.calculation != 'scf':
            atoms: Optional[Atoms] = frames[-1]  # 原生 relax/md：既有末帧语义（spec R2/P2）
        else:
            atoms = _select_scf_frame_for_structure(
                frames,
                log,
                directory,
                reference['atomorder'],
                stru_file=stru_file,
                _reference=reference,
            )
        assert atoms is not None

        # ``SinglePointDFTCalculator.properties()`` exposes the Fermi level
        # under ASE's ``fermi_level`` property, while the CP adapter consumes
        # the backend-neutral ``efermi`` fact.  Keep both names in the result
        # mapping so file-backed ABACUS evaluations do not lose this value at
        # the GenericFileIOCalculator boundary.  Older ASE snapshots store it
        # on ``eFermi``; tolerate that spelling as well.
        results = dict(atoms.calc.properties())
        efermi = results.get("efermi", results.get("fermi_level"))
        if efermi is None:
            for attribute in ("efermi", "eFermi", "fermi_level"):
                candidate = getattr(atoms.calc, attribute, None)
                if candidate is not None:
                    efermi = candidate
                    break
        if efermi is not None:
            results["efermi"] = efermi
            results.setdefault("fermi_level", efermi)
        return results

    def load_profile(self, cfg, **kwargs):
        return AbacusProfile.from_config(cfg, self.name, **kwargs)

class Abacus(GenericFileIOCalculator):
    def __init__(self, 
                 profile=None, 
                 directory='.', 
                 **kwargs):
        '''Construct the ABACUS calculator.

        The keyword arguments (kwargs) can be one of the ASE standard
        keywords: 'xc', 'kpts' or any of ABACUS'
        native keywords.

        Parameters
        ----------
        profile: AbacusProfile
            the interface that interacts with the ABACUS executable.
        directory: str or Path
            the working directory to store the input files.
        pseudopotentials: dict
            A mapping from the element to the pseudopotential file name,
            e.g. ``{'O': 'O_ONCV_PBE-1.0.upf', 'H': 'H.upf'}``.
        baisssets: dict, optional
            A mapping from the element to the ABACUS numerical atomic 
            orbital file name. This is necessary only when it is an
            ABACUS-LCAO (Linear-Combination-of-Atomic-Orbitals) calculation
            e.g. ``{'O': 'O_gga_10au_100Ry_2s2p1d.orb', 
            'H': 'H_gga_10au_100Ry_2s1p.orb'}``.
        kpts: dict
            The k-points sampling should be given as a dict. For there
            are many modes of k-sampling supported, the content may differ
            in cases. A `mode` key should be used to specify the ksampling,
            allowed modes are: `mp-sampling`, `line` and `point`. For 
            `mp-sampling` mode, `gamma-centered`, `nk` and `kshift` should
            present. `gamma-centered` is a boolean, `nk` and `kshift` should
            be lists of three integers. ... TBD
        inp: dict
            parameters setting in INPUT of ABACUS. NOTE: if there are settings
            on the `pseudo_dir` and `orbital_dir`, these will overwrite the
            value in the profile. If you do not expect this, please only use
            the profile, because the profile stands for interfacing with the
            ASE calculator instance with the computational environment.

        **kwargs:
            Other parameters to be passed to the ABACUS calculator.
        '''
        # not recommended :(
        profile = AbacusProfile('abacus') if profile is None else profile

        # to be compatible with both the legacy and latest format of i/o, the
        # switch is needed. 
        _ = switch_io_backend_version(profile.version())

        # because ABACUS run job in folders, based on the assumption that
        # there is only one job in the folder. Therefore once there are already
        # files in the folder, will try to create a new one...(seriously?)
        inp = kwargs.pop('inp', {})

        super().__init__(
            template=AbacusTemplate(),
            profile=profile,
            parameters=kwargs | inp,
            directory=directory,
        )

    @classmethod
    def restart(cls, profile=None, directory='.', **kwargs):
        '''instantiate one ABACUS calculator from an existing job directory,
        optionally overwrite some keywords'''
        directory = Path(directory)
        inp_read = read_input(directory / 'INPUT')

        pporb_read = read_stru(directory / 'STRU')['species']
        pseudopotentials = kwargs.get(
            'pseudopotentials',
            {pporb['symbol']: pporb['pp_file'] for pporb in pporb_read}
        )
        if 'pseudopotentials' in kwargs:
            del kwargs['pseudopotentials']
        
        basissets = kwargs.get(
            'basissets',
            {pporb['symbol']: pporb.get('orb_file') for pporb in pporb_read}
        )
        if 'basissets' in kwargs:
            del kwargs['basissets']
        if all([forb is None for forb in basissets.values()]):
            basissets = {}
        assert all([forb is not None for forb in basissets.values()])

        kpts = kwargs.get('kpts', read_kpt(directory / inp_read.get('kpoint_file', 'KPT')))
        if 'kpts' in kwargs:
            del kwargs['kpts']

        inp = inp_read | kwargs.get('inp', {})
        if 'inp' in kwargs:
            del kwargs['inp']

        return cls(profile=profile, 
                   directory=directory,
                   pseudopotentials=pseudopotentials,
                   basissets=basissets,
                   kpts=kpts,
                   inp=inp,
                   **kwargs)

    def fixed_density(self,
                      kpts: BandPath | Dict[str, str | int | List[float]],
                      symmetry: str = 'off', 
                      profile=None, 
                      **kwargs) -> 'Abacus':
        '''spawn a new ABACUS calculator with fixed density, based on the present
        instance. This funcionality is mostly only useful when perform the 
        non-self-consistent calculations like band structure.
        This interface is referred from the ASE document at:
        https://ase-lib.org/gettingstarted/tut04_bulk/bulk.html#band-structure
        , however, we also note that it is from the implementation of the 
        GPAW python, not the ASE official.
        To make less development burden as possible, we use the same interface
        as the GPAW python.

        Parameters
        ----------
        kpts : BandPath | Dict[str, str | int | List[float]]
            The k-point path to be calculated. Can be either a BandPath object
            or a dictionary that contains the k-point information. For the latter
            case, see tbgen/calculators/abacus/generalio.py::write_kpt for more
            details.
        symmetry : str, optional
            The symmetry mode to be used. Default is 'off'. Now only the `off`
            mode is supported.
        profile : AbacusProfile, optional
            The profile to be used. Default is None. If None, the profile of
            the present instance will be used.
        **kwargs : dict
            Other parameters to be passed to the ABACUS calculator.
        
        Returns
        -------
        Abacus
            The new ABACUS calculator instance that can perform the nscf calculation
            tasks
        '''
        # we should overwrite the 'calculation' to 'nscf', and 'init_chg' to 'file'
        assert symmetry == 'off'
        
        kwargs.setdefault('inp', {}).update({'calculation': 'nscf',
                                             'init_chg': 'file',
                                             'symmetry': 0,
                                             'out_band': 1,
                                             'kspacing': 0.0,       # overwrite
                                             'gamma_only': False,
                                             'read_file_dir': 'OUT.ABACUS'})  # overwrite

        profile = self.profile if profile is None else profile

        # get the kpoint coordinates
        if isinstance(kpts, BandPath):
            kwargs['kpts'] = {
                'mode': 'point',
                'nk': len(kpts.kpts),
                'nkinterpl': np.ones(len(kpts.kpts), dtype=int).tolist(),
                'coordinate': 'direct',
                'kpoints': kpts.kpts.tolist(),
            }
        else:
            assert isinstance(kpts, dict)
            kwargs['kpts'] = kpts
        
        # return
        return Abacus.restart(profile=profile, 
                              directory=self.directory,
                              **kwargs)

    def band_structure(self, efermi=None):
        '''get the band structure from ABACUS. 
        (now not only GPAW can calculate the band structure ;) )'''
        from ase.spectrum.band_structure import get_band_structure
        return get_band_structure(calc=self, reference=efermi)

class TestAbacusCalculator(unittest.TestCase):

    here = Path(__file__).parent
    pporb = here.parent.parent.parent / 'tests' / 'PP_ORB'

    def test_calculator_results(self):
        from ase.build.bulk import bulk
        silicon = bulk('Si', crystalstructure='diamond', a=5.43)
        aprof = AbacusProfile(
            command='mpirun -np 2 abacus',
            pseudo_dir=self.pporb,
            orbital_dir=self.pporb,
            omp_num_threads=1
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            calculator = Abacus(aprof,
                                directory=tmpdir,
                                pseudopotentials={'Si': 'Si_ONCV_PBE-1.0.upf'},
                                basissets={'Si': 'Si_gga_6au_100Ry_2s2p1d.orb'},
                                inp={'calculation': 'scf',
                                    'basis_type': 'lcao',
                                    'ks_solver': 'genelpa',
                                    'ecutwfc': 40,
                                    'symmetry': 1,
                                    'nspin': 1,
                                    'gamma_only': True,
                                    'cal_force': 1,
                                    'cal_stress': 1})
            silicon.calc = calculator
            e = silicon.get_potential_energy()
        
        # check!
        self.assertAlmostEqual(e, -194.953053309)
        self.assertIsNotNone(calculator.results)
        self.assertIsInstance(calculator.results, dict)
        for k in ['nspins', 'nkpts', 'nbands', 'eigenvalues', 'occupations',
                  'fermi_level', 'kpoint_weights', 'ibz_kpoints', 'energy', 
                  'free_energy', 'natoms', 'forces', 'stress', 'magmoms']:
            self.assertIn(k, calculator.results)
        self.assertEqual(calculator.results['nspins'], 1)
        self.assertEqual(calculator.results['nkpts'], 1)
        self.assertEqual(calculator.results['nbands'], 14)
        self.assertEqual(calculator.results['energy'], e)
        self.assertEqual(calculator.results['free_energy'], e)
        self.assertEqual(calculator.results['natoms'], 2)
        
        for k in ['eigenvalues', 'occupations', 'ibz_kpoints', 'forces', 'stress', 'magmoms']:
            self.assertIsInstance(calculator.results[k], np.ndarray)

        self.assertEqual(calculator.results['eigenvalues'].shape, (1, 1, 14))
        ekb = [-4.82194,  7.62727,  7.62727,  7.62737, 10.2436 , 10.2436 ,
                10.2436 , 10.9884 , 16.057  , 16.057  , 23.8353 , 25.421  ,
                25.421  , 25.4212 ]
        self.assertTrue(np.allclose(calculator.results['eigenvalues'][0, 0, :], np.array(ekb)))

        self.assertEqual(calculator.results['occupations'].shape, (1, 1, 14))
        occ = [2., 2., 2., 2., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.]
        self.assertTrue(np.allclose(calculator.results['occupations'][0, 0, :], np.array(occ)))
        
        self.assertEqual(calculator.results['ibz_kpoints'].shape, (1, 3))
        self.assertTrue(np.allclose(calculator.results['ibz_kpoints'][0, :], np.array([0,0,0])))

        self.assertEqual(calculator.results['forces'].shape, (2, 3))
        self.assertTrue(np.allclose(calculator.results['forces'], np.zeros((2, 3))))

        self.assertEqual(calculator.results['stress'].shape, (6,))
        stress = [-0.19327923, -0.19327923, -0.19327923, -0.        ,  0.        ,   0.        ]
        self.assertTrue(np.allclose(calculator.results['stress'], np.array(stress)))
        
        self.assertEqual(calculator.results['magmoms'].shape, (2,))
        self.assertTrue(np.allclose(calculator.results['magmoms'], np.zeros(2)))

    def test_restart(self):
        from ase.build.bulk import bulk
        silicon = bulk('Si', crystalstructure='diamond', a=5.43)
        aprof = AbacusProfile(
            command='mpirun -np 2 abacus',
            pseudo_dir=self.pporb,
            orbital_dir=self.pporb,
            omp_num_threads=1
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            calculator = Abacus(aprof,
                                directory=tmpdir,
                                pseudopotentials={'Si': 'Si_ONCV_PBE-1.0.upf'},
                                basissets={'Si': 'Si_gga_6au_100Ry_2s2p1d.orb'},
                                inp={'calculation': 'scf',
                                    'basis_type': 'lcao',
                                    'ks_solver': 'genelpa',
                                    'ecutwfc': 40,
                                    'symmetry': 1,
                                    'nspin': 1,
                                    'gamma_only': True,
                                    'cal_force': 1,
                                    'cal_stress': 1})
            silicon.calc = calculator
            e = silicon.get_potential_energy()
        
            # restart
            silicon.calc = Abacus.restart(aprof, directory=tmpdir)
            e2 = silicon.get_potential_energy()
            self.assertAlmostEqual(e2, e)

if __name__ == '__main__':
    unittest.main()
