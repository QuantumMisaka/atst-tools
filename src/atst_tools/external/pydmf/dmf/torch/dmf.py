import threading
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
from numpy.polynomial import polynomial as P
from scipy.interpolate import BSpline
from scipy.spatial.transform import Rotation
import cyipopt

from functools import cached_property

import torch
from ._torch_config import _resolve_torch_device, _resolve_torch_dtype


@torch.no_grad()
def _interp1d_torch(xq: torch.Tensor, xp: torch.Tensor, fp: torch.Tensor) -> torch.Tensor:
    """
    Linear interpolate fp(xp) at xq using pure PyTorch.

    xp: (M,), fp: (M, *), xq: (K,)
    Returns: (K, *) broadcast along the trailing dims of fp.
    """
    idx = torch.searchsorted(xp,xq,right=False).clamp(1,xp.numel()-1)
    x0, x1 = xp[idx-1], xp[idx]
    lam = (xq-x0)/(x1-x0)
    while lam.dim() < fp.dim():
        lam = lam.unsqueeze(-1)
    f0, f1 = fp[idx-1], fp[idx]
    return f0 + (f1-f0)*lam


def _release_calc_device_cache(calc, *, empty_cache: bool = False):
    if calc is None:
        return

    release = getattr(calc, "release_device_cache", None)
    if callable(release):
        try:
            release(empty_cache=empty_cache)
        except TypeError:
            release()

    mixer = getattr(calc, "mixer", None)
    if mixer is not None:
        sub_calcs = getattr(mixer, "calcs", None)
        if sub_calcs is not None:
            for sub in sub_calcs:
                _release_calc_device_cache(sub, empty_cache=False)


class HistoryBase():
    """
    Container storing the optimization history of the VariationalPathOpt.

    This object collects various physical and numerical quantities evaluated
    along the reaction path during the optimization.  At each IPOPT iteration,
    the ``VariationalPathOpt.intermediate`` method appends the current values
    of these quantities to the corresponding lists below.

    Attributes
    ----------
    forces : list of ndarray
        History of ``VariationalPathOpt.forces``.
    energies : list of ndarray
        History of ``VariationalPathOpt.energies``.
    coefs : list of ndarray
        History of ``VariationalPathOpt.coefs``.
    angs : list of ndarray
        History of ``VariationalPathOpt.angs``.
    tmax : list of float
        History of the location ``t_max`` corresponding to the maximum
        interpolated energy along the path. See Ref. 1 for details.
    images_tmax : list of ase.Atoms
        History of the atomic structure at ``t = t_max``, providing an
        approximate transition-state geometry at each iteration.
    duals : list of float
        History of the scaled dual infeasibility (IPOPT diagnostic).

    """

    def __init__(self):
        self.forces = []
        self.energies = []
        self.coefs = []
        self.angs = []
        self.tmax = []
        self.images_tmax = []
        self.duals = []


class VariationalPathOpt(ABC, cyipopt.Problem):
    r"""
    Abstract base class for variational reaction–path optimization.

    This class formulates a general functional

    .. math::

        \tilde{I}[x(t)] = K(I[x(t)]),

    where

    .. math::

        I[x(t)] = \int_0^1 dt\, \vert \dot{x}(t) \vert \, F(x(t)).

    The functions \(K(I)\), \(F(x)\), and their derivatives are supplied
    by concrete subclasses. Subclasses (e.g., ``DirectMaxFlux``) must
    implement

    - ``_get_objective``          — returns \( K(I) \)
    - ``_get_grad_objective``     — returns the gradient of the objective
      with respect to the internal optimization variables
    - ``_get_func_en``            — returns \(F(E)\) and \(dF/dE\)

    See their docstrings for details.

    Additional features include:
    - construction of initial B-spline coefficients from ``ref_images``
    - optional removal of translational and rotational redundancy
    - parallel energy/force evaluation using Python threads


    Parameters
    ----------

    ref_images : list of ase.Atoms
        List of atomic structures representing an initial guess for the path.
        If ``coefs`` is **not** provided, a piecewise linear interpolation
        through ``ref_images`` is constructed, and B-spline coefficients are
        obtained by fitting this interpolated path.
        If ``coefs`` **is** provided, no interpolation is performed:
        ``ref_images[0]`` is used only to extract atomic numbers, masses,
        cell, and PBC settings.

    coefs : ndarray of shape ``(nbasis, natoms, 3)``, optional
        Initial B-spline coefficients. If provided, interpolation from
        ``ref_images`` is skipped and these coefficients define the initial
        path. Default: None.

    nsegs : int, optional
        Number of B-spline segments. The number of basis functions per
        Cartesian degree of freedom is ``nbasis = nsegs + dspl``.
        See Ref. 1 for details. Default: 4.

    dspl : int, optional
        Polynomial degree of the B-spline basis. Default: 3.

    remove_rotation_and_translation : bool, optional
        If True, remove global translational and rotational motion using
        nonlinear constraints. Default: True.

    mass_weighted : bool, optional
        If True, the velocity norm \( \vert \dot{x}(t) \vert \) uses mass-weighted
        coordinates. Default: False.

    calc_factory : callable, optional
        Factory function returning a calculator for image index ``i``.
        If provided, ``calc_factory(i)`` is assigned to ``images[i].calc``.
        Default: None.

    parallel : bool, optional
        Evaluate energies and forces in parallel using Python threads.
        Default: False.

    world : MPI communicator, optional
        Communicator used when ``parallel=True``. Default: None.

    t_eval : ndarray, optional
        Energy evaluation points in \( t \in [0,1] \).
        If omitted, an even distribution
        np.linspace(0.0,1.0,2*nsegs+1) is generated.

    w_eval : ndarray of shape ``(len(t_eval),)``, optional
        Quadrature weights for evaluating the integral

        .. math::

            I[x] \approx \sum_i w_i\, \vert \dot{x}(t) \vert \, e^{\beta E(x(t_i))}.

        If omitted, trapezoidal weights are used.

    n_vel : int, optional
        Number of discretized velocity constraints.
        Default: ``4 * nsegs``.

    n_trans : int, optional
        Number of translational constraints.
        Default: ``2 * nsegs``.

    n_rot : int, optional
        Number of rotational constraints.
        Default: ``2 * nsegs``.

    eps_vel : float, optional
        Tolerance for velocity constraints. Default: 0.01.

    eps_rot : float, optional
        Tolerance for rotational constraints. Default: 0.01.

    device : str or torch.device, optional
        Torch device for internal tensors. If None, auto-select.
    dtype : str or torch.dtype, optional
        Torch floating-point dtype for internal calculations
        (``float32`` or ``float64``). Default: ``float64``.


    Attributes
    ----------

    # ---- Path representation ----

    images : list of ase.Atoms
        Atomic structures at ``t_eval``.
        The length of this list is ``len(t_eval)`` (including both endpoints).

    coefs : ndarray of shape ``(nbasis, natoms, 3)``
        Current B-spline coefficients defining the variational path.

    angs : ndarray of shape ``(3,)``
        Euler angles used when removing rotational redundancy.

    # ---- Energies and forces ----

    energies : ndarray of shape ``(len(t_eval),)``
        Energies evaluated at ``t_eval``.

    forces : ndarray of shape ``(len(t_eval), natoms, 3)``
        Forces evaluated at ``t_eval``.

    e0 : float
        Minimum endpoint energy.

    # ---- Evaluation grid ----

    t_eval : ndarray
        Energy evaluation points along the path.

    w_eval : ndarray of shape ``(len(t_eval),)``
        Quadrature weights associated with ``t_eval``.

    # ---- Constraint configuration ----

    n_vel : int
        Number of velocity constraints.

    n_trans : int
        Number of translational constraints.

    n_rot : int
        Number of rotational constraints.

    eps_vel : float
        Tolerance for velocity constraints.

    eps_rot : float
        Tolerance for rotational constraints.

    remove_rotation_and_translation : bool
        Whether translational/rotational redundancy is removed.

    # ---- B-spline representation ----

    nsegs : int
        Number of B-spline segments.

    dspl : int
        Degree of the B-spline basis.

    nbasis : int
        Number of B-spline basis functions per Cartesian degree of freedom.
        ``nbasis = nsegs + dspl``.

    # ---- Optimization ----

    ipopt_options : dict
        IPOPT options used for the optimization.

    history : HistoryBase
        Container storing iteration-by-iteration quantities.

    """

    def __init__(self,
        ref_images,
        coefs=None, nsegs=4,dspl=3,
        remove_rotation_and_translation=True,
        mass_weighted=False,
        calc_factory=None,
        parallel=False,
        t_eval=None,w_eval=None,
        n_vel=None,n_trans=None,n_rot=None,
        eps_vel=0.01,eps_rot=0.01,
        device=None,
        dtype=None,
        ):
        self.device = _resolve_torch_device(device)
        self.torch_dtype = _resolve_torch_dtype(dtype)

        # Parallel calculation
        self.parallel = parallel

        #Initialize images
        if t_eval is None:
            self._nimages = 2*nsegs+1
        else:
            self._nimages = len(t_eval)

        self.images=[]
        for _ in range(self._nimages):
            self.images.append(ref_images[0].copy())

        #calc_factory
        self.calc_factory = calc_factory

        if self.calc_factory is not None:
            for i, image in enumerate(self.images):
                image.calc = self.calc_factory(i)

        #Atoms
        self.natoms = len(ref_images[0])
        if mass_weighted:
            self._masses = ref_images[0].get_masses().astype(np.float64)
        else:
            self._masses = np.ones(self.natoms)
        self._mass_fracs = self._masses/np.sum(self._masses)

        #Constraints
        self.remove_rotation_and_translation = remove_rotation_and_translation
        self.eps_vel = float(eps_vel)
        self.eps_rot = float(eps_rot)

        #B-spline basis functions
        self.nsegs = int(nsegs)
        self.dspl = int(dspl)
        self.nbasis = self.nsegs + self.dspl
        _t_knot = np.concatenate([
            np.zeros(self.dspl),
            np.linspace(0.0,1.0,self.nsegs+1),
            np.ones(self.dspl)])
        self._t_knot = _t_knot
        basis = [
            BSpline(_t_knot, np.identity(self.nbasis)[i], self.dspl)
            for i in range(self.nbasis)]
        d1basis = [b.derivative(nu=1) for b in basis]
        d2basis = [b.derivative(nu=2) for b in basis]
        self._basis = [basis,d1basis,d2basis]

        # Callback/evaluation caches
        self._cached_callback_x = None
        self._positions_ready = False
        self._state_eval_ready = False

        #t-sequences
        if t_eval is None:
            self.set_t_eval(np.linspace(0.0,1.0,2*self.nsegs+1))
        else:
            self.set_t_eval(np.asarray(t_eval))

        self.set_w_eval(w_eval)

        if n_vel is None:
            self.n_vel = 4*self.nsegs
        else:
            self.n_vel = int(n_vel)
        self.t_vel = np.linspace(0.0,1.0,self.n_vel+1)

        if n_trans is None:
            self.n_trans = 2*self.nsegs
        else:
            self.n_trans = int(n_trans)
        self.t_trans = np.linspace(0.0,1.0,self.n_trans+1)[1:-1]

        if n_rot is None:
            self.n_rot = 2*self.nsegs
        else:
            self.n_rot = int(n_rot)
        self.t_rot = np.linspace(0.0,1.0,self.n_rot+1)
        self._dt_vel_t = torch.as_tensor(
            self.t_vel[1:] - self.t_vel[:-1], dtype=self.torch_dtype, device=self.device
        )
        self._t_fd_vel_t = torch.zeros(
            self.t_vel.size + 1, dtype=self.torch_dtype, device=self.device
        )
        self._t_fd_vel_t[1:-1] = 0.5 * (
            torch.as_tensor(self.t_vel[1:], dtype=self.torch_dtype, device=self.device)
            + torch.as_tensor(self.t_vel[:-1], dtype=self.torch_dtype, device=self.device)
        )
        self._t_fd_vel_t[-1] = torch.tensor(
            1.0, dtype=self.torch_dtype, device=self.device
        )

        #Basis values: [derivative order, basis, t]
        self._P_eval = self._get_basis_values(self.t_eval)
        self._P_vel = self._get_basis_values(self.t_vel)
        self._P_trans = self._get_basis_values(self.t_trans)
        self._P_rot = self._get_basis_values(self.t_rot)

        #Coefficients: [basis, atoms, xyz]
        self.coefs = np.empty([self.nbasis, self.natoms, 3])
        self.angs = np.zeros(3)
        if coefs is not None:
            self.coefs[...] = coefs
        else:
            self.coefs[...] = self._get_coefs_from_ref_images(ref_images)
        self._coefs0 = self.coefs.copy()

        # torch mirrors
        self._masses_t = torch.as_tensor(self._masses, dtype=self.torch_dtype, device=self.device)
        self._mass_fracs_t = torch.as_tensor(self._mass_fracs, dtype=self.torch_dtype, device=self.device)
        self._P_eval_t = torch.as_tensor(self._P_eval, dtype=self.torch_dtype, device=self.device)
        self._P_vel_t = torch.as_tensor(self._P_vel, dtype=self.torch_dtype, device=self.device)
        self._P_trans_t = torch.as_tensor(self._P_trans, dtype=self.torch_dtype, device=self.device)
        self._P_rot_t = torch.as_tensor(self._P_rot, dtype=self.torch_dtype, device=self.device)
        self.coefs_t = torch.as_tensor(self.coefs, dtype=self.torch_dtype, device=self.device)

        #Initialize images
        self.set_positions()

        #Jacobian of the translation constraints
        self._jac_trans = np.einsum(
            'a,bi,st->isbat',self._mass_fracs,
            self._P_trans[0],np.identity(3))

        self.forces = None
        self.energies = None

        self.history = HistoryBase()

        #initialize cyipopt.Problem
        nvar = (self.nbasis-2)*3*self.natoms
        if self.remove_rotation_and_translation:
            nvar += 3

        self.var_scales = 1.0

        m_vel = self.t_vel.size-1
        cl = np.full(m_vel,1.0-self.eps_vel)
        cu = np.full(m_vel,1.0+self.eps_vel)

        if self.remove_rotation_and_translation:
            cl_trans=np.zeros(3*self.t_trans.size)
            cu_trans=np.zeros(3*self.t_trans.size)
            m_rot = 3*(self.t_rot.size-1)
            cl_rot=np.full(m_rot,-self.eps_rot)
            cu_rot=np.full(m_rot, self.eps_rot)

            cl = np.hstack([cl,cl_trans,cl_rot])
            cu = np.hstack([cu,cu_trans,cu_rot])

        lb = np.full(nvar,-2.0e19)
        ub = np.full(nvar, 2.0e19)

        cyipopt.Problem.__init__(self,
            n=nvar, m=len(cl),
            lb=lb, ub=ub,
            cl=cl, cu=cu,)

        #set ipopt options
        defaults ={
            'tol': 1.0,
            'dual_inf_tol': 0.04,
            'constr_viol_tol': 0.01,
            'compl_inf_tol': 0.01,
            'nlp_scaling_method':'user-scaling',
            'obj_scaling_factor':0.1,
            'limited_memory_initialization':'constant',
            'limited_memory_init_val':2.5,
            'accept_every_trial_step':'yes',
            'output_file':'pathopt.out',

            "mumps_mem_percent": 2,
            "hessian_approximation": "limited-memory",
            "limited_memory_max_history": 5,
            }

        self.ipopt_options = dict()
        self.add_ipopt_options(defaults)


    def _get_basis_values(self, t_seq: np.ndarray) -> np.ndarray:
        return np.array([[[
            b(t) for t in t_seq]
            for b in self._basis[nu]]
            for nu in range(3)])

    def _invalidate_eval_cache(self):
        self._state_eval_ready = False

    def _invalidate_callback_x_cache(self):
        self._cached_callback_x = None

    def _ensure_current_state(self):
        if not self._positions_ready:
            self.set_positions()
        if not self._state_eval_ready:
            self.get_forces()
            self._state_eval_ready = True

    def _set_x_if_changed(self, x: np.ndarray):
        x_arr = np.asarray(x)
        if (
            self._cached_callback_x is not None
            and self._cached_callback_x.shape == x_arr.shape
            and np.array_equal(self._cached_callback_x, x_arr)
        ):
            return

        self.set_x(x_arr)
        if (
            self._cached_callback_x is None
            or self._cached_callback_x.shape != x_arr.shape
        ):
            self._cached_callback_x = x_arr.copy()
        else:
            self._cached_callback_x[...] = x_arr

    def set_t_eval(self,t_eval):
        """
        Set the energy evaluation points ``t_eval``.

        This also updates the cached B-spline basis values used for evaluating
        positions and derivatives.

        Parameters
        ----------
        t_eval : ndarray
            1D array of parameter values in the interval ``[0, 1]``.
            Its length must match the length of the initial ``t_eval`` used
            at initialization, because the number of images is fixed.

        """
        self.t_eval = np.asarray(t_eval)
        self._P_eval = self._get_basis_values(self.t_eval)
        self._P_eval_t = torch.as_tensor(self._P_eval, dtype=self.torch_dtype, device=self.device)
        self._t_eval_t = torch.as_tensor(
            self.t_eval, dtype=self.torch_dtype, device=self.device
        )
        self._positions_ready = False
        self._invalidate_eval_cache()
        self._invalidate_callback_x_cache()

    def set_w_eval(self, w_eval: Optional[np.ndarray] = None):
        """
        Set the quadrature weights ``w_eval`` used in the action integral.

        If ``w_eval`` is not provided, trapezoidal weights are generated from
        the current values of ``t_eval``.  The number of weights must
        match the number of energy evaluation points, which is fixed after
        initialization.

        Parameters
        ----------
        w_eval : ndarray, optional
            1D array of quadrature weights corresponding to ``t_eval``.
            Its length must match that of ``t_eval``.  If omitted,
            trapezoidal-rule weights are constructed automatically.

        """
        if w_eval is not None:
            self.w_eval = w_eval
        else:
            w = np.zeros_like(self.t_eval)
            w[0] = 0.5*(self.t_eval[1]-self.t_eval[0])
            w[-1] = 0.5*(self.t_eval[-1]-self.t_eval[-2])
            w[1:-1] = 0.5*(self.t_eval[2:]-self.t_eval[:-2])
            self.w_eval = w
        self._invalidate_callback_x_cache()

    def _get_coefs_from_ref_images(self, ref_images) -> np.ndarray:
        ref_images_copy = [image.copy() for image in ref_images]
        #Translate and rotate ref_images
        if self.remove_rotation_and_translation:
            prev_image = None
            for image in ref_images_copy:
                pos = image.get_positions()
                image.translate(-self._mass_fracs@pos)
                if prev_image is not None:
                    pos = image.get_positions()
                    prev_pos = prev_image.get_positions()
                    r = Rotation.align_vectors(
                        prev_pos,pos,weights=self._masses)[0]
                    image.set_positions(r.apply(pos))
                prev_image = image

        nimages = len(ref_images_copy)
        pos_ref = np.empty([nimages, self.natoms, 3])
        t_ref = np.zeros(nimages)
        for i,image in enumerate(ref_images_copy):
            pos_ref[i] = image.get_positions().astype(np.float64)
        diff = pos_ref[1:] - pos_ref[:-1]
        l = np.sqrt(
            (self._masses[None,:,None]*diff**2).sum(axis=(1,2)))
        t_ref[1:] = np.cumsum(l)/np.sum(l)

        t_ref_interp = np.linspace(0.0,1.0,4*self.nsegs+1)[1:-1]
        pos_ref_interp = _interp1d_torch(
            torch.as_tensor(t_ref_interp, dtype=self.torch_dtype, device=self.device),
            torch.as_tensor(t_ref, dtype=self.torch_dtype, device=self.device),
            torch.as_tensor(pos_ref, dtype=self.torch_dtype, device=self.device)
            ).cpu().numpy()
        P_ref_interp0 = self._get_basis_values(t_ref_interp)[0]

        #Solving least-square equations
        A = np.matmul(P_ref_interp0[1:-1],P_ref_interp0[1:-1].T)
        x = pos_ref_interp\
            - np.tensordot(P_ref_interp0[0],pos_ref[0],axes=0)\
            - np.tensordot(P_ref_interp0[-1],pos_ref[-1],axes=0)
        y = np.tensordot(P_ref_interp0[1:-1],x,axes=1).reshape(-1,3*self.natoms)

        coefs = np.empty([self.nbasis, self.natoms, 3])
        coefs[0] = pos_ref[0]
        coefs[-1] = pos_ref[-1]
        coefs[1:-1] = np.linalg.solve(A,y).reshape(-1,self.natoms,3)

        return coefs

    def get_positions(self, t=None, P=None, nu=0) -> np.ndarray:
        """
        Evaluate the positions (or their derivatives) along the path.

        Normally, users provide only ``t``; however, advanced users may supply
        precomputed basis values ``P`` (from ``_get_basis_values()``) to avoid
        repeated evaluations.

        If both ``t`` and ``P`` are provided, ``P`` takes priority.

        Parameters
        ----------
        t : ndarray, optional
            1D array of parameter values in ``[0, 1]`` at which positions (or
            derivatives) are evaluated.  If omitted, ``t_eval`` is used.

        P : ndarray, optional
            Precomputed B-spline basis values from ``_get_basis_values()``.
            Default: None.

        nu : int, optional
            Derivative order with respect to ``t`` (0, 1, or 2). Default: 0.

        Returns
        -------
        ndarray
            Array of shape ``(len(t), natoms, 3)`` containing the positions
            (``nu = 0``) or the ``nu``-th derivatives of the path.

        """
        if t is None:
            t_temp = self.t_eval
        else:
            t_temp = t
        if P is None:
            P_temp = self._get_basis_values(t_temp)
        else:
            P_temp = P
        return np.tensordot(P_temp[nu].T,self.coefs,1)

    def set_coefs_angs(self,coefs=None,angs=None):
        """
        Update the B-spline coefficients and/or rotation angles.

        This method updates ``coefs`` and ``angs`` if the
        corresponding arguments are provided.  After updating the angles,
        the final B-spline control point (``coefs[-1]``) is recomputed as

        .. math::

            \mathrm{coefs}[-1] = \mathrm{coefs}_0[-1] \, R_x R_y R_z,

        where ``R_x, R_y, R_z`` are the rotation matrices generated from
        ``self.angs``.  This ensures that the endpoint geometry is kept
        consistent under rotational constraints.

        Parameters
        ----------
        coefs : ndarray of shape (nbasis, natoms, 3), optional
            New B-spline coefficients.
            If omitted, the current coefficients are preserved.

        angs : ndarray of shape (3,), optional
            Rotation angles used to the final endpoint alignment.
            If omitted, the current angles are preserved.

        """
        if coefs is not None:
            self.coefs = coefs
            coefs_t = torch.as_tensor(self.coefs, dtype=self.torch_dtype, device=self.device)
            if (
                hasattr(self, "coefs_t")
                and self.coefs_t.shape == coefs_t.shape
                and self.coefs_t.device == coefs_t.device
                and self.coefs_t.dtype == coefs_t.dtype
            ):
                self.coefs_t.copy_(coefs_t)
            else:
                self.coefs_t = coefs_t
        if angs is not None:
            self.angs = angs
        R=self._get_rot_mats()
        self.coefs[-1]=self._coefs0[-1]@R[0]@R[1]@R[2]
        self.coefs_t[-1].copy_(torch.as_tensor(self.coefs[-1], dtype=self.torch_dtype, device=self.device))
        self._positions_ready = False
        self._invalidate_eval_cache()
        self._invalidate_callback_x_cache()

    def _get_positions_torch(self, P_t: torch.Tensor, nu=0) -> torch.Tensor:
        return torch.tensordot(P_t[nu].T.contiguous(),self.coefs_t,1)

    def _get_rot_mats(self) -> np.ndarray:
        # Explicit vectorized construction of Rx, Ry, Rz from Euler angles.
        s = np.sin(self.angs)
        c = np.cos(self.angs)
        R = np.array(
            [
                [[1.0, 0.0, 0.0], [0.0, c[0], -s[0]], [0.0, s[0], c[0]]],
                [[c[1], 0.0, s[1]], [0.0, 1.0, 0.0], [-s[1], 0.0, c[1]]],
                [[c[2], -s[2], 0.0], [s[2], c[2], 0.0], [0.0, 0.0, 1.0]],
            ],
            dtype=np.float64,
        )
        return R

    def set_positions(self, coefs=None, angs=None):
        """
        Update the positions of all images along the path.

        This method first updates the B-spline coefficients and/or rotation
        angles by calling :meth:`set_coefs_angs`.  It then recomputes the
        atomic positions along the path using :meth:`get_positions`, and
        writes these positions into the existing ``self.images`` objects.

        Note that this method does **not** change the number of images;
        it only updates their positions according to the current path
        parameters.

        Parameters
        ----------
        coefs : ndarray of shape (nbasis, natoms, 3), optional
            New B-spline coefficients.  If omitted, the existing coefficients
            are preserved.

        angs : ndarray of shape (3,), optional
            Rotation angles used for endpoint alignment.  If omitted,
            the existing angles are preserved.

        """
        self.set_coefs_angs(coefs, angs)
        pos = self.get_positions()
        for i in range(self.t_eval.size):
            self.images[i].set_positions(pos[i])
        self._positions_ready = True
        self._invalidate_eval_cache()

    def _get_consts_trans(self) -> np.ndarray:
        pos = self.get_positions(P=self._P_trans)
        return self._mass_fracs@pos

    def _get_jac_trans(self) -> np.ndarray:
        return self._jac_trans

    def _get_consts_rot(self) -> np.ndarray:
        pos = self.get_positions(P=self._P_rot)
        return self._mass_fracs@np.cross(pos[:-1],pos[1:])

    def _get_jac_rot(self) -> np.ndarray:
        pos = self.get_positions(P=self._P_rot)
        y = np.cross(np.identity(3),pos[...,None,:])
        jac_rot = \
            np.einsum(
                'a,bi,iats->isbat',
                self._mass_fracs,
                self._P_rot[0,:,:-1],
                y[1:]) \
            - np.einsum(
                'a,bi,iats->isbat',
                self._mass_fracs,
                self._P_rot[0,:,1:],
                y[:-1])
        return jac_rot
    def _get_consts_vel(self) -> np.ndarray:
        pos_t = self._get_positions_torch(self._P_vel_t)
        diffs = pos_t[1:] - pos_t[:-1]
        d2s = torch.sum(self._masses_t[None, :, None] * diffs**2, dim=(1, 2))
        ave = torch.mean(d2s)
        # Guard against division-by-zero in pathological trial steps
        ave = torch.clamp(ave, min=1.0e-300)
        return (d2s / ave).cpu().numpy()

    def _get_jac_vel(self) -> np.ndarray:
        pos_t = self._get_positions_torch(self._P_vel_t)
        diffs = pos_t[1:] - pos_t[:-1]
        d2s = torch.sum(self._masses_t[None, :, None] * diffs**2, dim=(1, 2))
        diff_P = self._P_vel_t[0, :, 1:] - self._P_vel_t[0, :, :-1]
        jac_d2s = 2.0 * torch.einsum(
            'a,bi,ias->ibas',
            self._masses_t, diff_P, diffs
        )
        ave_d2s = torch.mean(d2s)
        # Guard against division-by-zero in pathological trial steps
        ave_d2s = torch.clamp(ave_d2s, min=1.0e-300)
        return (
            jac_d2s / ave_d2s
            - torch.tensordot(d2s, torch.mean(jac_d2s, dim=0), 0) / (ave_d2s**2)
        ).cpu().numpy()

    def _get_jac_fin_rot(self) -> np.ndarray:
        R = self._get_rot_mats()
        s = np.sin(self.angs)
        c = np.cos(self.angs)

        dR0 = np.array(
            [[0.0, 0.0, 0.0], [0.0, -s[0], -c[0]], [0.0, c[0], -s[0]]],
            dtype=np.float64,
        )
        dR1 = np.array(
            [[-s[1], 0.0, c[1]], [0.0, 0.0, 0.0], [-c[1], 0.0, -s[1]]],
            dtype=np.float64,
        )
        dR2 = np.array(
            [[-s[2], -c[2], 0.0], [c[2], -s[2], 0.0], [0.0, 0.0, 0.0]],
            dtype=np.float64,
        )

        jac_rot = np.empty([self.natoms, 3, 3], dtype=np.float64)
        jac_rot[..., 0] = self._coefs0[-1] @ dR0 @ R[1] @ R[2]
        jac_rot[..., 1] = self._coefs0[-1] @ R[0] @ dR1 @ R[2]
        jac_rot[..., 2] = self._coefs0[-1] @ R[0] @ R[1] @ dR2

        return jac_rot

    def _reshape_jacs(self,jacs):

        def remove_axis(jac):
            if len(jac)==1:
                return jac[0]
            else:
                return jac

        #All constraints are aligned in the 0th axis
        aligned_jac = np.vstack([
            jac.reshape([-1,self.nbasis,self.natoms,3])
            for jac in jacs])
        nc = len(aligned_jac)

        jac_coefs = aligned_jac[:,1:-1,:,:].reshape([nc,-1])

        if self.remove_rotation_and_translation:
            jac_fin_rot = self._get_jac_fin_rot()
            jac_rot = np.tensordot(aligned_jac[:,-1,:,:],jac_fin_rot)
            return remove_axis(np.hstack([jac_coefs,jac_rot]))
        else:
            return remove_axis(jac_coefs)

    def _reshape_consts(self,consts):
        return np.hstack([np.ravel(c) for c in consts]).astype(np.float64)

    @cached_property
    def _e_f_ends(self):
        forces = np.empty([self._nimages, self.natoms, 3])
        energies = np.empty(self._nimages)

        idxs = [0,self._nimages-1]

        self._get_forces_by_img_idxs(idxs,energies,forces)

        return energies[idxs], forces[idxs]


    @cached_property
    def _f_ends(self):
        e, f = self._e_f_ends
        return f


    @cached_property
    def _e_ends(self):
        e, f = self._e_f_ends
        return e


    @cached_property
    def e0(self) -> float:
        """
        float:
            Minimum endpoint energy used to shift the energy scale.
        """
        return float(np.amin(self._e_ends))

    def get_forces(self) -> np.ndarray:
        eps_t=0.01

        forces = np.empty([self._nimages, self.natoms, 3])
        energies = np.empty(self._nimages)

        t = self.t_eval
        mask_head = t < eps_t
        mask_tail = t > 1.0 - eps_t
        mask_mid = ~(mask_head | mask_tail)

        if np.any(mask_head):
            forces[mask_head] = self._f_ends[0]
            energies[mask_head] = self._e_ends[0]

        if np.any(mask_tail):
            R = self._get_rot_mats()
            f_end_rot = self._f_ends[1] @ R[0] @ R[1] @ R[2]
            forces[mask_tail] = f_end_rot
            energies[mask_tail] = self._e_ends[1]

        idxs = np.flatnonzero(mask_mid).tolist()
        if idxs:
            self._get_forces_by_img_idxs(idxs,energies,forces)


        self.energies = energies
        self.forces = forces
        self._state_eval_ready = True

        return forces


    def _get_forces_by_img_idxs(self,idxs,energies,forces):
        if self.parallel:

            def run(image, energies, forces):
                forces[:] = image.get_forces()
                energies[:] = image.get_potential_energy()

            threads = [threading.Thread(target=run,
                                        args=(self.images[i],
                                              energies[i:i+1],
                                              forces[i:i+1]))
                       for i in idxs]

            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            for i in idxs:
                _release_calc_device_cache(self.images[i].calc, empty_cache=False)

        else:

            for i in idxs:
                image = self.images[i]
                forces[i] = image.get_forces()
                energies[i] = image.get_potential_energy()
                _release_calc_device_cache(image.calc, empty_cache=False)

            # Give allocator a chance to defragment between large-image evaluations.
            if self.device.type == "cuda" and self.natoms >= 2000 and torch.cuda.is_available():
                torch.cuda.empty_cache()


    @abstractmethod
    def _get_objective(self) -> float:
        """
        Compute the objective value K(I).

        This method returns the scalar objective value used by IPOPT.
        Subclasses must implement a mapping

            I  →  K(I),

        where ``I`` is the action computed internally from the path
        (via ``_get_action``).

        Returns
        -------
        float
            The value of the objective K(I).

        Examples
        --------
        In ``DirectMaxFlux``, the objective is

            K(I) = log(I) / beta

        implemented as:

        .. code-block:: python

            def _get_objective(self):
                return np.log(self._get_action()) / self.beta

        """
        pass

    @abstractmethod
    def _get_grad_objective(self) -> np.ndarray:
        """
        Compute the derivative of K(I) with respect to ``coefs``.

        Returns
        -------
        ndarray
            The derivative of the objective with respect to the B-spline
            coefficients (and rotation angles, if applicable).  The shape
            matches that of the flattened optimization variable vector.

        Examples
        --------
        In ``DirectMaxFlux``, where

            K(I) = log(I) / beta,

        the derivative is implemented as:

        .. code-block:: python

            def _get_grad_objective(self):
                return self._get_grad_action() / self._get_action() / self.beta

        """
        pass

    @abstractmethod
    def _get_func_en(self, en: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Evaluate the energy-dependent function F(E) and its derivative dF/dE.

        This function defines the integrand weights used in the action

            I = ∫ |ẋ(t)| F(E(t)) dt.

        Parameters
        ----------
        en : ndarray
            Array of energy values E(t_i) at the quadrature points.

        Returns
        -------
        F_en : ndarray
            The array F(E(t_i)).

        dF_en : ndarray
            The array dF/dE evaluated at the same points.

        Examples
        --------
        In ``DirectMaxFlux``, the choice is

            F(E) = exp(beta * E),    dF/dE = beta * exp(beta * E)

        implemented as:

        .. code-block:: python

            def _get_func_en(self, en):
                return np.exp(self.beta * en), self.beta * np.exp(self.beta * en)

        """
        pass


    @torch.no_grad()
    def _get_norm_vels(self,nu=0):
        pos_t = self._get_positions_torch(self._P_vel_t)
        diffs = pos_t[1:]-pos_t[:-1]

        norm_dx = torch.sqrt(
            torch.sum(self._masses_t[None,:,None]*diffs**2,dim=(1,2)))
        # Avoid division-by-zero in pathological trial steps (e.g., collapsed segments)
        norm_dx = torch.clamp(norm_dx, min=1.0e-12)
        dt = self._dt_vel_t
        t_fd_vel = self._t_fd_vel_t

        if nu==0:
            fd_vels = torch.zeros(self.t_vel.size + 1, dtype=self.torch_dtype, device=self.device)
            fd_vels[1:-1] = norm_dx/dt
            fd_vels[0] = fd_vels[1]
            fd_vels[-1] = fd_vels[-2]

            return _interp1d_torch(
                self._t_eval_t,
                t_fd_vel,fd_vels).cpu().numpy()
        else:
            diff_P_vel0 = self._P_vel_t[0,:,1:]-self._P_vel_t[0,:,:-1]
            grad_norm_vel = torch.einsum(
                'i,bi,a,ias->ibas',
                1.0/(dt*norm_dx),
                diff_P_vel0,
                self._masses_t,
                diffs)
            grad_fd_vels = torch.zeros(
                [self.t_vel.size+1,self.nbasis,self.natoms,3],
                dtype=self.torch_dtype, device=self.device)
            grad_fd_vels[1:-1] = grad_norm_vel
            grad_fd_vels[0] = grad_norm_vel[0]
            grad_fd_vels[-1] = grad_norm_vel[-1]

            return _interp1d_torch(
                self._t_eval_t,
                t_fd_vel,grad_fd_vels).cpu().numpy()

    @torch.no_grad()
    def _get_action(self) -> float:

        self._ensure_current_state()

        norm_vels = self._get_norm_vels()
        fe,dfe = self._get_func_en(self.energies)
        action = np.sum(self.w_eval*norm_vels*fe)

        return action

    @torch.no_grad()
    def _get_grad_action(self) -> np.ndarray:

        self._ensure_current_state()

        fe,dfe = self._get_func_en(self.energies)
        norm_vels = self._get_norm_vels()
        grad_norm_vels = self._get_norm_vels(nu=1)

        grad_action = np.tensordot(self.w_eval*fe,grad_norm_vels,1) \
            - np.tensordot(
                self._P_eval[0]*self.w_eval*norm_vels*dfe,
                self.forces,1)

        return grad_action


    def interpolate_energies(
        self, t_eval=None, energies=None, forces=None, coefs=None,
        delta_e=None):
        r"""
        Construct a piecewise-cubic interpolation of the energy along the path.

        This method reconstructs a smooth interpolation
        :math:`\tilde{E}(t)` of the discrete energy values evaluated at
        ``t_eval``.  The interpolation is ``C^1``-continuous and uses both
        energies and their first derivatives.

        Optionally, the method can also locate the values of ``t`` satisfying

        .. math::

            \tilde{E}(t) = E_{\max} - \Delta E,

        for user-specified ``delta_e``.

        See Ref. 1 for details.

        Parameters
        ----------
        t_eval : ndarray, optional
            1D array of parameter values at which energies/forces were evaluated.
            If omitted, ``self.t_eval`` is used.  Only the region
            ``t_eval <= 1`` is used internally.

        energies : ndarray, optional
            Energy values at ``t_eval``.  If omitted, ``self.energies`` is used.

        forces : ndarray, optional
            Forces at ``t_eval`` with shape ``(len(t_eval), natoms, 3)``.
            If omitted, ``self.forces`` is used.

        coefs : ndarray of shape ``(nbasis, natoms, 3)``, optional
            B-spline control-point coefficients.
            If omitted, ``self.coefs`` is used.

        delta_e : list of float, optional
            Energy offsets :math:`\Delta E`.  If provided,
            this method also returns the corresponding parameter values ``t``
            satisfying

            .. math::

                \tilde{E}(t) = E_{\max} - \Delta E.

        Returns
        -------
        polys : ndarray of shape ``(len(t_eval) - 1, 4)``
            Polynomial coefficients defining the piecewise cubic interpolation.
            Each segment corresponds to:

            .. math::

                \tilde{E}(t)
                = c_0 + c_1 t + c_2 t^2 + c_3 t^3.

        t_max : float
            The parameter value ``t`` at which the interpolated energy
            :math:`\tilde{E}(t)` attains its maximum.

        e_max : float
            The maximum interpolated energy :math:`\tilde{E}(t_{\max})`.

        t_de : list of ndarray, optional
            Returned only when ``delta_e`` is provided.
            ``t_de[j]`` contains all roots satisfying
            :math:`\tilde{E}(t) = E_{\max} - \Delta E_j`.

        """

        if t_eval is None:
            t_eval = self.t_eval
        i_fin = np.where(t_eval>0.99)[0][0]
        t_eval = t_eval[:i_fin+1]

        if energies is None:
            energies = self.energies
        energies = energies[:i_fin+1]

        if forces is None:
            forces = self.forces
        forces = forces[:i_fin+1]

        if coefs is None:
            coefs = self.coefs

        P_eval1 = self._get_basis_values(t_eval)[1]
        d_energies = -np.einsum(
            'bi,bas,ias->i',
            P_eval1, coefs, forces)

        # Vectorized assembly of cubic Hermite systems for each interval.
        t0 = t_eval
        t2 = t0 * t0
        t3 = t2 * t0
        rows_val = np.stack([np.ones_like(t0), t0, t2, t3], axis=1)
        rows_der = np.stack([np.zeros_like(t0), np.ones_like(t0), 2.0 * t0, 3.0 * t2], axis=1)

        # For each segment i:
        # A_i = [val(t_i), der(t_i), val(t_{i+1}), der(t_{i+1})], b_i = [E_i, dE_i, E_{i+1}, dE_{i+1}]
        A = np.stack([rows_val[:-1], rows_der[:-1], rows_val[1:], rows_der[1:]], axis=1)
        b = np.stack([energies[:-1], d_energies[:-1], energies[1:], d_energies[1:]], axis=1)
        polys = np.linalg.solve(A, b[..., None])[..., 0]

        if d_energies[np.argmax(energies)]>0.0:
            imax = np.argmax(energies)
        else:
            imax = np.argmax(energies)-1

        if imax == -1:
            t_max = 0.0
            e_max = energies[0]
        elif imax == i_fin:
            t_max = 1.0
            e_max = energies[-1]
        else:
            t_max = -( polys[imax,2] + np.sqrt(polys[imax,2]**2 \
                -3.0*polys[imax,1]*polys[imax,3])) \
                /(3.0*polys[imax,3])

            t_max_pow = np.array([t_max**i for i in range(4)])
            e_max=np.sum(t_max_pow*polys[imax])

        if delta_e is not None:
            t_de = []
            for de in delta_e:
                tlist = np.array([])
                for i in range(len(t_eval)-1):
                    p = P.Polynomial(polys[i])
                    p -= e_max-de
                    roots = p.roots()
                    roots = roots.real[abs(roots.imag)<1e-5]
                    roots = roots[(roots>=t_eval[i])&(roots<t_eval[i+1])]
                    tlist = np.append(tlist,roots)
                t_de.append(tlist)
            return polys,t_max,e_max,t_de

        return polys,t_max,e_max

    def solve(self, tol='tight'):
        """
        Solve the variational optimization problem using IPOPT.

        The current path parameters are flattened into a 1D variable vector
        ``x`` and passed to IPOPT.  After optimization, the updated vector is
        written back via ``set_x``.  The return values are those provided by
        ``cyipopt.Problem.solve``.

        The argument ``tol`` provides a convenient shortcut for adjusting the
        IPOPT option ``dual_inf_tol`` using the presets from Ref. 1:

        - ``'tight'``  →  ``dual_inf_tol = 0.04``
        - ``'middle'`` →  ``dual_inf_tol = 0.10``
        - ``'loose'``  →  ``dual_inf_tol = 0.20``
        - a float value directly sets ``dual_inf_tol`` to that number.

        Parameters
        ----------
        tol : {'tight', 'middle', 'loose'} or float, optional
            Desired dual infeasibility tolerance.  Default is ``'tight'``.

        Returns
        -------
        x_opt : ndarray
            Optimized 1D variable array.

        info : dict
            IPOPT information dictionary.

        """

        if tol:
            if isinstance(tol,float):
                self.add_ipopt_options({'dual_inf_tol':tol})
            elif isinstance(tol,str):
                if tol.strip().upper()=='TIGHT':
                    self.add_ipopt_options({'dual_inf_tol':0.04})
                elif tol.strip().upper()=='MIDDLE':
                    self.add_ipopt_options({'dual_inf_tol':0.1})
                elif tol.strip().upper()=='LOOSE':
                    self.add_ipopt_options({'dual_inf_tol':0.2})

        x0 = self.get_x()
        x,info = super().solve(x0)
        self.set_x(x)
        return x,info


    def add_ipopt_options(self, dict_options):
        """
        Add or update IPOPT options.

        This method updates ``self.ipopt_options`` with the key–value pairs
        given in ``dict_options`` and forwards them to IPOPT via
        ``self.add_option``.

        Parameters
        ----------
        dict_options : dict
            Dictionary of IPOPT options (e.g., ``{"tol": 1e-3}``).

        """
        self.ipopt_options.update(dict_options)
        for item in self.ipopt_options.items():
            self.add_option(*item)


    def get_x(self) -> np.ndarray:
        """
        Return the flattened optimization variable vector used by IPOPT.

        Although mainly intended for internal use, this method is exposed
        because :meth:`solve` returns the optimized variable vector ``x``.
        The returned array contains all internal degrees of freedom:

        - the flattened interior B-spline coefficients ``coefs[1:-1]``
          (endpoint coefficients are fixed), and
        - the rotation angles ``angs`` if
          ``remove_rotation_and_translation=True``.

        Returns
        -------
        x : ndarray of shape (nvar,)
            Flattened optimization variable vector.

        """
        x = self.coefs[1:-1].flatten()
        if self.remove_rotation_and_translation:
            x = np.hstack([x, self.angs])
        return x


    def set_x(self, x):
        """
        Update ``coefs`` and ``angs`` from the flattened optimization vector.

        This method is normally not called directly by end-users; it is invoked
        internally during IPOPT callbacks such as :meth:`objective`,
        :meth:`gradient`, :meth:`constraints`, and :meth:`jacobian`.

        The input vector ``x`` must be exactly the one produced by
        :meth:`get_x`.  The method reconstructs:

        - ``coefs[1:-1]`` (interior B-spline control points), and
        - ``angs`` (rotation angles, if enabled),

        and then updates all image positions via :meth:`set_positions`.

        Parameters
        ----------
        x : ndarray of shape (nvar,)
            Flattened optimization variable vector.

        """
        nc = (self.nbasis - 2) * 3 * self.natoms
        self.coefs[1:-1] = x[:nc].reshape((-1, self.natoms, 3))
        self.coefs_t[1:-1].copy_(
            torch.as_tensor(
                self.coefs[1:-1], dtype=self.torch_dtype, device=self.device
            )
        )
        if self.remove_rotation_and_translation:
            self.set_positions(angs=x[-3:])
        else:
            self.set_positions()


    def objective(self, x: np.ndarray) -> float:
        """
        IPOPT callback: objective function.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the scalar objective evaluated at that state.
        """
        self._set_x_if_changed(x)
        return self._get_objective()

    def gradient(self, x: np.ndarray) -> np.ndarray:
        """
        IPOPT callback: gradient of the objective.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the gradient of the objective with respect to ``x``.
        """
        self._set_x_if_changed(x)
        grad = self._reshape_jacs(
            [self._get_grad_objective()])
        return grad*self.var_scales

    def constraints(self, x: np.ndarray) -> np.ndarray:
        """
        IPOPT callback: nonlinear constraint values.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the array of constraint values at that state.
        """
        self._set_x_if_changed(x)
        c_list = [self._get_consts_vel()]
        if self.remove_rotation_and_translation:
            c_list.append(self._get_consts_trans())
            c_list.append(self._get_consts_rot())
        return self._reshape_consts(c_list)

    def jacobian(self, x: np.ndarray) -> np.ndarray:
        """
        IPOPT callback: Jacobian of the constraints.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the Jacobian matrix of the constraint functions.
        """
        self._set_x_if_changed(x)
        j_list = [self._get_jac_vel()]
        if self.remove_rotation_and_translation:
            j_list.append(self._get_jac_trans())
            j_list.append(self._get_jac_rot())
        return self._reshape_jacs(j_list)*self.var_scales

    def intermediate(self, alg_mod, iter_count, obj_value,
                    inf_pr, inf_du, mu, d_norm, regularization_size,
                    alpha_du, alpha_pr, ls_trials):
        """
        IPOPT callback: per-iteration monitor.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT at the end of each iteration.
        The arguments are provided by IPOPT and follow its callback
        interface specification.

        In addition to the default IPOPT behavior, this method records
        iteration-by-iteration quantities into ``self.history``.
        See :class:`HistoryBase` for details.

        Parameters
        ----------
        alg_mod, iter_count, obj_value, inf_pr, inf_du, mu, d_norm, regularization_size, alpha_du, alpha_pr, ls_trials :
            Values supplied directly by IPOPT at each iteration.
            These are passed through unchanged and are not meant
            to be modified by the user.

        """

        self.history.forces.append(self.forces)
        self.history.energies.append(self.energies)
        self.history.coefs.append(self.coefs)
        self.history.angs.append(self.angs)
        self.history.duals.append(inf_du)

        polys,tmax,emax_interp = self.interpolate_energies()

        P_tmax = np.array(
            [b(tmax) for b in self._basis[0]])
        image_tmax = self.images[0].copy()
        image_tmax.set_positions(
            np.tensordot(P_tmax,self.coefs,1))
        self.history.tmax.append(tmax)
        self.history.images_tmax.append(image_tmax)


class HistoryDMF():
    """
    Container storing the optimization history of the ``DirectMaxFlux`` method.

    This object collects various physical and numerical quantities evaluated
    along the reaction path during the optimization.  At each IPOPT iteration,
    the ``DirectMaxFlux.intermediate`` method appends the current values of
    these quantities to the corresponding lists below.

    Attributes
    ----------
    forces : list of ndarray
        History of ``DirectMaxFlux.forces``.
    energies : list of ndarray
        History of ``DirectMaxFlux.energies``.
    coefs : list of ndarray
        History of ``DirectMaxFlux.coefs``.
    angs : list of ndarray
        History of ``DirectMaxFlux.angs``.
    t_eval : list of ndarray
        History of ``DirectMaxFlux.t_eval``.
    tmax : list of float
        History of the location ``t_max`` corresponding to the maximum
        interpolated energy along the path. See Ref. 1 for details.
    images_tmax : list of ase.Atoms
        History of the atomic structure at ``t = t_max``, providing an
        approximate transition-state geometry at each iteration.
    duals : list of float
        History of the scaled dual infeasibility (IPOPT diagnostic).

    """

    def __init__(self):
        self.forces = []
        self.energies = []
        self.coefs = []
        self.angs = []
        self.t_eval = []
        self.tmax = []
        self.images_tmax = []
        self.duals = []


class DirectMaxFlux(VariationalPathOpt):
    r"""
    Variational reaction path/transition states optimization based on
    the **direct MaxFlux method**.

    Ref. 1.
       S.-i. Koda and S. Saito,
       *Locating Transition States by Variational Reaction Path Optimization
       with an Energy-Derivative-Free Objective Function*
       J. Chem. Theory Comput. **20**, 2798–2811 (2024).

    This class implements the MaxFlux variational principle in the large-β
    (low-temperature) regime for locating transition states (TSs) and
    approximating minimum-energy paths (MEPs), following the formulation of
    Ref. 1.

    The reaction path \( x(t) \) is represented by a B-spline expansion, and
    the following functional is minimized:

    .. math::

        \tilde{I}[x] = \beta^{-1} \log I[x],

    where

    .. math::

        I[x] = \int_0^1 dt\, \vert \dot{x}(t) \vert \, e^{\beta E(x(t))}.

    With large \( \beta \), the highest-energy point along the optimized
    path approximates the TS geometry.

    The method requires only first-order atomic forces, because the objective
    contains no derivatives of the potential energy.

    Additional features include:
    - construction of initial B-spline coefficients from ``ref_images``
    - optional removal of translational and rotational redundancy
    - parallel energy/force evaluation Python threads
    - optional adaptive refinement of ``t_eval`` near the high-energy region


    Parameters
    ----------

    ref_images : list of ase.Atoms
        List of atomic structures representing an initial guess for the path.
        If ``coefs`` is **not** provided, a piecewise linear interpolation
        through ``ref_images`` is constructed, and B-spline coefficients are
        obtained by fitting this interpolated path.
        If ``coefs`` **is** provided, no interpolation is performed:
        ``ref_images[0]`` is used only to extract atomic numbers, masses,
        cell, and PBC settings.

    coefs : ndarray of shape ``(nbasis, natoms, 3)``, optional
        Initial B-spline coefficients. If provided, interpolation from
        ``ref_images`` is skipped and these coefficients define the initial
        path. Default: None.

    nsegs : int, optional
        Number of B-spline segments. The number of basis functions per
        Cartesian degree of freedom is ``nbasis = nsegs + dspl``.
        See Ref. 1 for details. Default: 4.

    dspl : int, optional
        Polynomial degree of the B-spline basis. Default: 3.

    remove_rotation_and_translation : bool, optional
        If True, remove global translational and rotational motion using
        nonlinear constraints. Default: True.

    mass_weighted : bool, optional
        If True, the velocity norm \( \vert \dot{x}(t) \vert \) uses mass-weighted
        coordinates. Default: False.

    calc_factory : callable, optional
        Factory function returning a calculator for image index ``i``.
        If provided, ``calc_factory(i)`` is assigned to ``images[i].calc``.
        Default: None.

    parallel : bool, optional
        Evaluate energies and forces in parallel using Python threads.
        Default: False.

    world : MPI communicator, optional
        Communicator used when ``parallel=True``. Default: None.

    t_eval : ndarray of shape ``(nmove+2,)``, optional
        **Initial** evaluation points in \( t \in [0,1] \).
        If omitted or ``update_teval`` is True, an even distribution
        np.linspace(0.0,1.0,nmove+2) is generated.

    w_eval : ndarray of shape ``(nmove+2,)``, optional
        **Initial** quadrature weights for evaluating the integral

        .. math::

            I[x] \approx \sum_i w_i\, \vert \dot{x}(t) \vert \, e^{\beta E(x(t_i))}.

        If omitted, trapezoidal weights are used.

    n_vel : int, optional
        Number of discretized velocity constraints.
        Default: ``4 * nsegs``.

    n_trans : int, optional
        Number of translational constraints.
        Default: ``2 * nsegs``.

    n_rot : int, optional
        Number of rotational constraints.
        Default: ``2 * nsegs``.

    eps_vel : float, optional
        Tolerance for velocity constraints. Default: 0.01.

    eps_rot : float, optional
        Tolerance for rotational constraints. Default: 0.01.

    beta : float, optional
        Reciprocal temperature \( \beta \) (in 1/eV) used in the MaxFlux
        functional. Default: 10.0.

    nmove : int, optional
        Number of **movable** interior evaluation points.
        Total number of images = ``nmove + 2`` (including both endpoints).
        Default: 5.

    update_teval : bool, optional
        If True, ``t_eval`` is adaptively updated toward the high-energy region
        during optimization. Default: False.

    params_t_update : dict, optional
        Parameters controlling the update of ``t_eval``.
        Includes keys such as ``max_alpha0``, ``de``, ``dia``, ``mua``,
        ``dib``, ``mub``, ``epsb`` (Defaults are the same as in Ref. 1).

    device : str or torch.device, optional
        Torch device for internal tensors. If None, auto-select.
    dtype : str or torch.dtype, optional
        Torch floating-point dtype for internal calculations
        (``float32`` or ``float64``). Default: ``float64``.


    Attributes
    ----------

    # ---- Path representation ----

    images : list of ase.Atoms
        Atomic structures at the **current** ``t_eval``.
        The length of this list is ``nmove + 2`` (including both endpoints).

    coefs : ndarray of shape ``(nbasis, natoms, 3)``
        Current B-spline coefficients defining the variational path.

    angs : ndarray of shape ``(3,)``
        Euler angles used when removing rotational redundancy.

    # ---- Energies and forces ----

    energies : ndarray of shape ``(nmove+2,)``
        Energies evaluated at the **current** ``t_eval`` (shifted by ``e0``).

    forces : ndarray of shape ``(nmove+2, natoms, 3)``
        Forces evaluated at the **current** ``t_eval``.

    # ---- Evaluation grid ----

    t_eval : ndarray of shape ``(nmove+2,)``
        **Current** energy evaluation points along the path.
        If ``update_teval=True``, these differ from the initial values.

    w_eval : ndarray of shape ``(nmove+2,)``
        **Current** quadrature weights associated with ``t_eval``.

    # ---- Constraint configuration ----

    n_vel : int
        Number of velocity constraints.

    n_trans : int
        Number of translational constraints.

    n_rot : int
        Number of rotational constraints.

    eps_vel : float
        Tolerance for velocity constraints.

    eps_rot : float
        Tolerance for rotational constraints.

    remove_rotation_and_translation : bool
        Whether translational/rotational redundancy is removed.

    # ---- B-spline representation ----

    nsegs : int
        Number of B-spline segments.

    dspl : int
        Degree of the B-spline basis.

    nbasis : int
        Number of B-spline basis functions per Cartesian degree of freedom.
        ``nbasis = nsegs + dspl``.

    # ---- MaxFlux functional parameters ----

    beta : float
        Reciprocal temperature \( \beta \).

    nmove : int
        Number of movable interior evaluation points.

    update_teval : bool
        Whether ``t_eval`` is adaptively updated.

    params_t_update : dict
        Parameters controlling the update of ``t_eval``.

    # ---- Optimization ----

    ipopt_options : dict
        IPOPT options used for the optimization.

    history : HistoryDMF
        Container storing iteration-by-iteration quantities.

    """

    def __init__(
        self,
        ref_images,
        coefs=None, nsegs: int = 4, dspl: int = 3,
        remove_rotation_and_translation: bool = True,
        mass_weighted: bool = False,
        calc_factory=None,
        parallel: bool = False,
        t_eval: Optional[np.ndarray] = None,
        w_eval: Optional[np.ndarray] = None,
        n_vel: Optional[int] = None,
        n_trans: Optional[int] = None,
        n_rot: Optional[int] = None,
        eps_vel: float = 0.01,
        eps_rot: float = 0.01,
        beta: float = 10.0,
        nmove: int = 5,
        update_teval: bool = False,
        params_t_update: Optional[dict] = None,
        device=None,
        dtype=None,
        ):

        args = locals()
        base_params = [
            'ref_images','coefs','nsegs','dspl',
            'remove_rotation_and_translation','mass_weighted',
            'calc_factory','parallel','t_eval','w_eval','n_vel',
            'n_trans','n_rot','eps_vel','eps_rot','device','dtype']
        base_args = {k:args[k] for k in base_params}

        if params_t_update is None:
            params_t_update = {}
        params_defaults = {
            'max_alpha0': 0.1,
            'de': 0.15,
            'dia': 1.0,
            'mua': 5.0,
            'dib': 0.2,
            'mub': 5.0,
            'epsb': 0.02,
        }
        for key, value in params_defaults.items():
            params_t_update.setdefault(key, value)

        self.beta: float = float(beta)
        self.params_t_update: dict = params_t_update
        self._max_alpha: float = params_t_update['max_alpha0']

        self.update_teval: bool = bool(update_teval)

        self.nmove: int = int(nmove)

        if t_eval is None or self.update_teval:
            t_eval_init = np.linspace(0.0, 1.0, nmove + 2)
        else:
            t_eval_init = np.asarray(t_eval, dtype=np.float64)
            if t_eval_init.ndim != 1:
                raise ValueError("t_eval must be a 1D array.")
            if t_eval_init.size != (nmove + 2):
                raise ValueError(
                    "len(t_eval) must be nmove + 2 "
                    f"(got len(t_eval)={t_eval_init.size}, nmove={nmove})."
                )
            if not np.all(np.diff(t_eval_init) > 0.0):
                raise ValueError("t_eval must be strictly increasing.")
            if (t_eval_init[0] < 0.0) or (t_eval_init[-1] > 1.0):
                raise ValueError(
                    "t_eval must satisfy 0.0 <= t_eval[0] and t_eval[-1] <= 1.0."
                )
            if (not np.isclose(t_eval_init[0], 0.0)) or (not np.isclose(t_eval_init[-1], 1.0)):
                raise ValueError("t_eval endpoints must be 0.0 and 1.0.")

        base_args.update(t_eval=t_eval_init)

        super().__init__(**base_args)

        self.history = HistoryDMF()


    def get_forces(self):
        super().get_forces()
        self.energies -= self.e0
        return self.forces


    def _log_action_and_probs(self, energies: np.ndarray, norm_vels: np.ndarray):
        """Numerically stable evaluation of log(action) and normalized weights.

        The MaxFlux action is::

            action = Σ_i w_i * |ẋ(t_i)| * exp(beta * E_i)

        This returns:
            log_action = log(action)
            p          = (w_i * |ẋ| * exp(beta E_i)) / action   (Σ p = 1)

        Notes
        -----
        - Uses a log-sum-exp formulation to avoid overflow/underflow in exp.
        - Entries with zero (or non-finite) weights are ignored (p_i = 0).
        """
        w = np.asarray(self.w_eval, dtype=np.float64)
        v = np.asarray(norm_vels, dtype=np.float64)
        e = np.asarray(energies, dtype=np.float64)

        # Replace non-finite energies with a large penalty so the line search backs off.
        if not np.isfinite(e).all():
            e = np.nan_to_num(e, nan=1.0e6, posinf=1.0e6, neginf=1.0e6)

        a = w * v  # quadrature weight × speed
        mask = (a > 0.0) & np.isfinite(a)

        log_terms = np.full_like(e, -np.inf, dtype=np.float64)
        log_terms[mask] = np.log(a[mask]) + self.beta * e[mask]

        m = np.max(log_terms)
        if not np.isfinite(m):
            return -np.inf, np.zeros_like(e, dtype=np.float64)

        exp_terms = np.exp(log_terms - m)
        denom = float(np.sum(exp_terms))
        if (not np.isfinite(denom)) or (denom <= 0.0):
            return -np.inf, np.zeros_like(e, dtype=np.float64)

        p = exp_terms / denom
        log_action = float(m + np.log(denom))
        return log_action, p


    def _get_objective(self):
        """Stable objective: log(action)/beta."""
        self._ensure_current_state()

        norm_vels = self._get_norm_vels()
        log_action, _ = self._log_action_and_probs(self.energies, norm_vels)

        if not np.isfinite(log_action):
            # Force IPOPT to backtrack (avoids "Invalid number" termination).
            return 1.0e20

        return log_action / self.beta


    def _get_grad_objective(self):
        """Stable gradient of log(action)/beta (no exp overflow)."""
        self._ensure_current_state()

        norm_vels = self._get_norm_vels()
        grad_norm_vels = self._get_norm_vels(nu=1)

        log_action, p = self._log_action_and_probs(self.energies, norm_vels)

        # Safety: if anything went wrong, return zeros instead of NaNs/Infs
        if (not np.isfinite(log_action)) or (not np.isfinite(p).all()):
            return np.zeros((self.nbasis, self.natoms, 3), dtype=np.float64)

        # First term: (1/beta) * Σ (p_i/|ẋ_i|) * ∂|ẋ_i|/∂c
        v_safe = np.maximum(norm_vels, 1.0e-300)
        w1 = (p / v_safe) / self.beta
        term1 = np.tensordot(w1, grad_norm_vels, axes=([0], [0]))

        # Second term: Σ p_i * ∂E_i/∂c, assembled from forces and basis values
        forces = np.asarray(self.forces, dtype=np.float64)
        if not np.isfinite(forces).all():
            forces = np.nan_to_num(forces, nan=0.0, posinf=0.0, neginf=0.0)

        term2 = np.tensordot(self._P_eval[0] * p, forces, axes=([1], [0]))

        grad = term1 - term2
        if not np.isfinite(grad).all():
            grad = np.nan_to_num(grad, nan=0.0, posinf=0.0, neginf=0.0)
        return grad


    def _get_func_en(self,en):
        """Legacy exp(beta*E) helper (kept for compatibility).

        DirectMaxFlux overrides objective/gradient with a log-sum-exp formulation,
        but the base-class helpers still call this. We clip the exponent to avoid
        overflow if users call `_get_action()` directly.
        """
        x = self.beta * np.asarray(en, dtype=np.float64)
        x = np.clip(x, -700.0, 700.0)
        ex = np.exp(x)
        return ex, self.beta * ex

    def intermediate(self, alg_mod, iter_count, obj_value,
                     inf_pr, inf_du, mu, d_norm, regularization_size,
                     alpha_du, alpha_pr, ls_trials):
        """
        IPOPT callback: per-iteration monitor.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT at the end of each iteration.
        The arguments are provided by IPOPT and follow its callback
        interface specification.

        In addition to the default IPOPT behavior, this method records
        iteration-by-iteration quantities into ``self.history``.
        See :class:`HistoryDMF` for details.

        If ``update_teval=True``, this method also adaptively updates
        the energy evaluation points ``t_eval`` based on the current
        energy profile and dual infeasibility.  See Ref. 1 for details.

        Parameters
        ----------
        alg_mod, iter_count, obj_value, inf_pr, inf_du, mu, d_norm, regularization_size, alpha_du, alpha_pr, ls_trials :
            Values supplied directly by IPOPT at each iteration.
            These are passed through unchanged and are not meant
            to be modified by the user.

        """

        super().intermediate(alg_mod, iter_count, obj_value,
                     inf_pr, inf_du, mu, d_norm, regularization_size,
                     alpha_du, alpha_pr, ls_trials)

        if self.update_teval:
            self.history.t_eval.append(self.t_eval.copy())

            polys,tmax,emax_interp = self.interpolate_energies()

            un_di = inf_du \
                /self.ipopt_options['obj_scaling_factor'] \
                /np.amax(self.var_scales)

            de   = self.params_t_update['de']
            dia  = self.params_t_update['dia']
            mua  = self.params_t_update['mua']
            dib  = self.params_t_update['dib']
            mub  = self.params_t_update['mub']
            epsb = self.params_t_update['epsb']

            ca = 0.5*(1.0+np.tanh(-2.0*mua*(un_di-dia)))
            cb = 1.0-0.5*epsb*(1.0+np.tanh(-2.0*mub*(un_di-dib)))

            nmove = self.nmove
            barrier = emax_interp - np.amax(self._e_ends)+self.e0
            de = min(2.0/float(nmove+1)*barrier,de)
            delta_e = de*np.arange(0.5*(nmove%2+1.0),0.5*(nmove+1.0),1.0)
            t_de = self.interpolate_energies(delta_e=delta_e)[3]
            t_cand_m = np.hstack([tl[tl<tmax] for tl in t_de])
            t_cand_p = np.hstack([tl[tl>tmax] for tl in t_de])
            temp_t_eval_m = t_cand_m[
                np.argsort(np.abs(t_cand_m-tmax))[:nmove//2]]
            temp_t_eval_p = t_cand_p[
                np.argsort(np.abs(t_cand_p-tmax))[:nmove//2]]
            if nmove%2==1:
                temp_t_eval_p = np.append(temp_t_eval_p,tmax)
            temp_t_eval = np.sort(np.append(temp_t_eval_m,temp_t_eval_p))

            alpha = ca*self._max_alpha
            t_eval = self.t_eval.copy()
            if temp_t_eval.size == t_eval[1:-1].size:
                t_eval[1:-1] = (1.0-alpha)*t_eval[1:-1] + alpha*temp_t_eval

            self.set_t_eval(t_eval)
            self.set_w_eval()

            self._max_alpha *= cb
