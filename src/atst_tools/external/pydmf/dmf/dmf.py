import threading
from abc import ABC, abstractmethod

import numpy as np
from numpy.polynomial import polynomial as P
from scipy.interpolate import BSpline,interp1d
from scipy.spatial.transform import Rotation
import cyipopt

from functools import cached_property

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
        ):

        #Prallel calculation
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
            self._masses = ref_images[0].get_masses()
        else:
            self._masses = np.ones(self.natoms)
        self._mass_fracs = self._masses/np.sum(self._masses)

        #Constraints
        self.remove_rotation_and_translation \
            = remove_rotation_and_translation
        self.eps_vel = eps_vel
        self.eps_rot = eps_rot

        #B-spline basis functions
        self.nsegs = nsegs
        self.dspl = dspl
        self.nbasis = nsegs + dspl
        _t_knot = np.concatenate([
            np.zeros(dspl),
            np.linspace(0.0,1.0,nsegs+1),
            np.ones(dspl)])
        self._t_knot = _t_knot
        basis = [
            BSpline(_t_knot, np.identity(self.nbasis)[i], dspl)
            for i in range(self.nbasis)]
        d1basis = [b.derivative(nu=1) for b in basis]
        d2basis = [b.derivative(nu=2) for b in basis]
        self._basis = [basis,d1basis,d2basis]


        #t-sequences
        if t_eval is None:
            self.set_t_eval(np.linspace(0.0,1.0,2*nsegs+1))
        else:
            self.set_t_eval(t_eval)

        self.set_w_eval(w_eval)

        if n_vel is None:
            self.n_vel = 4*nsegs
        else:
            self.n_vel = n_vel
        self.t_vel = np.linspace(0.0,1.0,self.n_vel+1)

        if n_trans is None:
            self.n_trans = 2*nsegs
        else:
            self.n_trans = n_trans
        self.t_trans = np.linspace(0.0,1.0,self.n_trans+1)[1:-1]

        if n_rot is None:
            self.n_rot = 2*nsegs
        else:
            self.n_rot = n_rot
        self.t_rot = np.linspace(0.0,1.0,self.n_rot+1)

        #Basis values: [derivative order, basis, t]
        self._P_eval = self._get_basis_values(self.t_eval)
        self._P_vel = self._get_basis_values(self.t_vel)
        self._P_trans = self._get_basis_values(self.t_trans)
        self._P_rot = self._get_basis_values(self.t_rot)

        #Coefficients: [basis, atoms, xyz]
        self.coefs = np.empty([self.nbasis, self.natoms, 3])
        self.angs = np.zeros(3)
        if coefs is not None:
            self.coefs = coefs
        else:
            self.coefs = self._get_coefs_from_ref_images(ref_images)
        self._coefs0 = self.coefs.copy()

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
            }

        self.ipopt_options = dict()
        self.add_ipopt_options(defaults)


    def _get_basis_values(self,t_seq):
        return np.array([[[
            b(t) for t in t_seq]
            for b in self._basis[nu]]
            for nu in range(3)])

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
        self.t_eval = t_eval
        self._P_eval = self._get_basis_values(self.t_eval)

    def set_w_eval(self, w_eval=None):
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

    def _get_coefs_from_ref_images(self,ref_images):
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
            pos_ref[i] = image.get_positions()
        diff = pos_ref[1:] - pos_ref[:-1]
        l = np.sqrt(
            (self._masses[None,:,None]*diff**2).sum(axis=(1,2)))
        t_ref[1:] = np.cumsum(l)/np.sum(l)

        f = interp1d(t_ref,pos_ref,axis=0)
        t_ref_interp = np.linspace(0.0,1.0,4*self.nsegs+1)[1:-1]
        pos_ref_interp = f(t_ref_interp)
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

    def get_positions(self,t=None,P=None,nu=0):
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
            self.coefs=coefs
        if angs is not None:
            self.angs = angs
        R=self._get_rot_mats()
        self.coefs[-1]=self._coefs0[-1]@R[0]@R[1]@R[2]

    def _get_rot_mats(self):
        R=np.zeros([3,3,3])
        for i in range(3):
            j=(i+1)%3
            k=(i+2)%3
            R[i,i,i]= 1.0
            R[i,j,j]= np.cos(self.angs[i])
            R[i,j,k]=-np.sin(self.angs[i])
            R[i,k,j]= np.sin(self.angs[i])
            R[i,k,k]= np.cos(self.angs[i])
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

    def _get_consts_trans(self):
        pos = self.get_positions(P=self._P_trans)
        return self._mass_fracs@pos

    def _get_jac_trans(self):
        return self._jac_trans

    def _get_consts_rot(self):
        pos = self.get_positions(P=self._P_rot)
        return self._mass_fracs@np.cross(pos[:-1],pos[1:])

    def _get_jac_rot(self):
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

    def _get_consts_vel(self):
        pos = self.get_positions(P=self._P_vel)
        diffs = pos[1:]-pos[:-1]
        d2s = (self._masses[None,:,None]*diffs**2).sum(axis=(1,2))
        return d2s/np.average(d2s)

    def _get_jac_vel(self):
        pos = self.get_positions(P=self._P_vel)
        diffs = pos[1:]-pos[:-1]
        d2s = (self._masses[None,:,None]*diffs**2).sum(axis=(1,2))
        diff_P = self._P_vel[0,:,1:]-self._P_vel[0,:,:-1]
        jac_d2s = 2.0*np.einsum(
            'a,bi,ias->ibas',
            self._masses,diff_P,diffs)
        ave_d2s = np.average(d2s)
        return jac_d2s/ave_d2s \
            - np.tensordot(d2s,np.average(jac_d2s,axis=0),0)/(ave_d2s)**2

    def _get_jac_fin_rot(self):
        R=self._get_rot_mats()

        dR=np.zeros([3,3,3])
        for i in range(3):
            j=(i+1)%3
            k=(i+2)%3
            dR[i,j,j]=-np.sin(self.angs[i])
            dR[i,j,k]=-np.cos(self.angs[i])
            dR[i,k,j]= np.cos(self.angs[i])
            dR[i,k,k]=-np.sin(self.angs[i])

        jac_rot = np.empty([self.natoms,3,3])
        jac_rot[...,0] = self._coefs0[-1]@dR[0]@R[1]@R[2]
        jac_rot[...,1] = self._coefs0[-1]@R[0]@dR[1]@R[2]
        jac_rot[...,2] = self._coefs0[-1]@R[0]@R[1]@dR[2]

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
        return np.hstack([np.ravel(c) for c in consts])


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
    def e0(self):
        """
        float:
            Minimum endpoint energy used to shift the energy scale.
        """
        return np.amin(self._e_ends)


    def get_forces(self):
        eps_t=0.01
        eps_w=0.001

        forces = np.empty([self._nimages, self.natoms, 3])
        energies = np.empty(self._nimages)
        e0 = self.e0

        idxs=[]
        for i in range(self._nimages):
            if self.t_eval[i]<eps_t:
                forces[i] = self._f_ends[0]
                energies[i] = self._e_ends[0]
            elif self.t_eval[i]>1.0-eps_t:
                R=self._get_rot_mats()
                f = self._f_ends[1]
                forces[i] = f@R[0]@R[1]@R[2]
                energies[i] = self._e_ends[1]
            else:
                idxs.append(i)

        self._get_forces_by_img_idxs(idxs,energies,forces)

        self.energies = energies
        self.forces = forces

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

        else:

            for i in idxs:
                forces[i] = self.images[i].get_forces()
                energies[i] = self.images[i].get_potential_energy()


    @abstractmethod
    def _get_objective(self):
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
    def _get_grad_objective(self):
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
    def _get_func_en(self, en):
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


    def _get_norm_vels(self,nu=0):
        pos = self.get_positions(P=self._P_vel)
        diffs = pos[1:]-pos[:-1]

        norm_dx = np.sqrt(
            np.sum(self._masses[None,:,None]*diffs**2,axis=(1,2)))
        dt = self.t_vel[1:]-self.t_vel[:-1]

        t_fd_vel = np.zeros(self.t_vel.size+1)
        t_fd_vel[1:-1] = 0.5*(self.t_vel[1:]+self.t_vel[:-1])
        t_fd_vel[-1] = 1.0

        if nu==0:
            fd_vels = np.zeros(self.t_vel.size + 1)
            fd_vels[1:-1] = norm_dx/dt
            fd_vels[0] = fd_vels[1]
            fd_vels[-1] = fd_vels[-2]

            f = interp1d(t_fd_vel,fd_vels)
            return f(self.t_eval)
        else:
            diff_P_vel0 = self._P_vel[0,:,1:]-self._P_vel[0,:,:-1]
            grad_norm_vel = np.einsum(
                'i,bi,a,ias->ibas',
                1.0/(dt*norm_dx),
                diff_P_vel0,
                self._masses,
                diffs)
            grad_fd_vels = np.zeros(
                [self.t_vel.size+1,self.nbasis,self.natoms,3])
            grad_fd_vels[1:-1] = grad_norm_vel
            grad_fd_vels[0] = grad_norm_vel[0]
            grad_fd_vels[-1] = grad_norm_vel[-1]

            f = interp1d(t_fd_vel,grad_fd_vels,axis=0)
            return f(self.t_eval)

    def _get_action(self):

        self.set_positions()
        self.get_forces()

        norm_vels = self._get_norm_vels()
        fe,dfe = self._get_func_en(self.energies)
        action = np.sum(self.w_eval*norm_vels*fe)

        return action

    def _get_grad_action(self):

        self.set_positions()
        self.get_forces()

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

        t_pows = np.zeros([2*len(t_eval),4])
        for i in range(4):
            t_pows[::2,i] = t_eval**i
            if i<3:
                t_pows[1::2,i+1] = (i+1)*t_eval**i

        ens_dens = np.zeros(2*len(t_eval))
        ens_dens[::2] = energies
        ens_dens[1::2] = d_energies

        polys = np.zeros([len(t_eval)-1,4])
        for i in range(len(t_eval)-1):
            polys[i] = np.linalg.solve(
                t_pows[2*i:2*i+4],ens_dens[2*i:2*i+4])

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


    def get_x(self):
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
        coefs = self._coefs0.copy()

        coefs[1:-1] = x[:nc].reshape((-1, self.natoms, 3))

        angs = np.zeros(3)
        if self.remove_rotation_and_translation:
            angs = x[-3:]

        self.set_positions(coefs, angs)


    def objective(self, x):
        """
        IPOPT callback: objective function.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the scalar objective evaluated at that state.
        """
        self.set_x(x)
        return self._get_objective()

    def gradient(self, x):
        """
        IPOPT callback: gradient of the objective.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the gradient of the objective with respect to ``x``.
        """
        self.set_x(x)
        grad = self._reshape_jacs(
            [self._get_grad_objective()])
        return grad*self.var_scales

    def constraints(self, x):
        """
        IPOPT callback: nonlinear constraint values.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the array of constraint values at that state.
        """
        self.set_x(x)
        c_list = [self._get_consts_vel()]
        if self.remove_rotation_and_translation:
            c_list.append(self._get_consts_trans())
            c_list.append(self._get_consts_rot())
        return self._reshape_consts(c_list)

    def jacobian(self, x):
        """
        IPOPT callback: Jacobian of the constraints.

        This method is not intended to be called directly by users.
        It is invoked internally by IPOPT during the optimization process.
        The argument ``x`` is the flattened optimization variable vector,
        and the return value is the Jacobian matrix of the constraint functions.
        """
        self.set_x(x)
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
    - parallel energy/force evaluation using Python threads
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
        coefs=None, nsegs=4,dspl=3,
        remove_rotation_and_translation=True,
        mass_weighted=False,
        calc_factory=None,
        parallel=False,
        t_eval=None,w_eval=None,
        n_vel=None,n_trans=None,n_rot=None,
        eps_vel=0.01,eps_rot=0.01,
        beta = 10.0,
        nmove = 5,
        update_teval = False,
        params_t_update = {
            'max_alpha0':0.1,'de':0.15,
            'dia':1.0,'mua':5.0,
            'dib':0.2,'mub':5.0,'epsb':0.02,},
        ):

        args = locals()
        base_params = [
            'ref_images','coefs','nsegs','dspl',
            'remove_rotation_and_translation','mass_weighted',
            'calc_factory',
            'parallel','t_eval','w_eval','n_vel',
            'n_trans','n_rot','eps_vel','eps_rot']
        base_args = {k:args[k] for k in base_params}

        self.beta = beta
        self.params_t_update = params_t_update
        self._max_alpha = params_t_update['max_alpha0']

        self.update_teval = update_teval

        self.nmove = nmove

        base_args.update(t_eval=np.linspace(0.0,1.0,nmove+2))

        super().__init__(**base_args)

        self.history = HistoryDMF()


    def get_forces(self):
        super().get_forces()
        self.energies -= self.e0
        return self.forces

    def _get_objective(self):
        return np.log(self._get_action())/self.beta

    def _get_grad_objective(self):
        return self._get_grad_action()/self._get_action()/self.beta

    def _get_func_en(self,en):
        return np.exp(self.beta*en),self.beta*np.exp(self.beta*en)

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
            self.history.t_eval.append(self.t_eval)

            polys,tmax,emax_interp = self.interpolate_energies()

            un_di = inf_du \
                /self.ipopt_options['obj_scaling_factor'] \
                /np.amax(self.var_scales)
            tol_di = self.ipopt_options['dual_inf_tol'] \
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
            t_eval[1:-1] = (1.0-alpha)*t_eval[1:-1] + alpha*temp_t_eval

            self.set_t_eval(t_eval)
            self.set_w_eval()

            self._max_alpha *= cb
