import numpy as np
from ase.calculators.mixing import SumCalculator
from .dmf import DirectMaxFlux
from .fbenm import FB_ENM_Bonds, CFB_ENM


def interpolate_fbenm(
        ref_images,nmove=10,
        output_file='fbenm_ipopt.out',
        correlated=True,
        sequential=True,
        fbenm_only_endpoints=True,
        copy_calc0=True,
        fbenm_options={},
        cfbenm_options={},
        dmf_options={},
        ipopt_options={},
        ):
    """
    Generate a plausible initial reaction path using FB-ENM or
    FB-ENM + CFB-ENM in combination with the direct MaxFlux method.

    This routine constructs a DirectMaxFlux object from the given
    reference images (typically reactant and product) and assigns an
    FB-ENM_Bonds calculator, optionally combined with CFB-ENM,
    to each intermediate image. The DMF solver is then executed with
    a β-update scheme (see FB-ENM's paper) to obtain a plausible path.

    Parameters
    ----------
    ref_images : list of ase.Atoms
        Reference structures defining the initial piecewise linear path
        for the (C)FB-ENM optimization.
    nmove : int, optional
        Number of movable images. Default: 10.
    output_file : str, optional
        File name for IPOPT output. Default: 'fbenm_ipopt.out'.
    correlated : bool, optional
        If True, use FB-ENM + CFB-ENM (correlated ENM).
        If False, use FB-ENM only. Default: True.
    sequential : bool, optional
        Whether to apply a sequential MaxFlux optimization scheme
        that gradually activates interior points. Default: True.
    fbenm_only_endpoints : bool, optional
        If True, construct FB-ENM from only the first and last image.
        If False, use all ref_images for FB-ENM construction.
        Default: True.
    copy_calc0 : bool, optional
        If True, the calculator of images[0] is copied to the other images.
        If False, independently initialize each calculator.
        Default: True.
    fbenm_options : dict, optional
        Keyword arguments forwarded to `FB_ENM_Bonds`.
    cfbenm_options : dict, optional
        Keyword arguments forwarded to `CFB_ENM`.
    dmf_options : dict, optional
        Keyword arguments forwarded to `DirectMaxFlux`.
    ipopt_options : dict, optional
        Keyword arguments forwarded to `DirectMaxFlux.add_ipopt_options()`.

    Returns
    -------
    mxflx : DirectMaxFlux
        The DirectMaxFlux object after the (C)FB-ENM optimization.

    Notes
    -----
    - The returned DirectMaxFlux instance retains all images with their
      assigned ENM calculators, and can be used directly for subsequent
      accurate (first-principles) MaxFlux optimization.
    - For details of FB-ENM and CFB-ENM, see the corresponding papers.
    """

    if fbenm_only_endpoints:
        fbenm_images = [ref_images[0].copy(),ref_images[-1].copy()]
    else:
        fbenm_images = [image.copy() for image in ref_images]

    if copy_calc0:
        calc_f = FB_ENM_Bonds(fbenm_images, **fbenm_options)
        if correlated:
            calc_c = CFB_ENM(fbenm_images,**cfbenm_options)
            def make_calc(i):
                return SumCalculator([calc_f.copy(),
                                      calc_c.copy(fbenm_images)])
        else:
            def make_calc(i):
                return calc_f.copy()
    else:
        if correlated:
            def make_calc(i):
                return SumCalculator([
                    FB_ENM_Bonds(fbenm_images, **fbenm_options),
                    CFB_ENM(fbenm_images,**cfbenm_options)])
        else:
            def make_calc(i):
                return FB_ENM_Bonds(fbenm_images, **fbenm_options)


    mxflx = DirectMaxFlux(ref_images,
                          nmove=nmove,
                          update_teval=False,
                          calc_factory=make_calc,
                          **dmf_options)

    options ={
        'tol': 0.1,
        'dual_inf_tol': 0.01,
        'constr_viol_tol': 0.01,
        'compl_inf_tol': 0.01,
        'nlp_scaling_method':'user-scaling',
        'obj_scaling_factor':0.1,
        'limited_memory_initialization':'constant',
        'limited_memory_init_val':2.5,
        'accept_every_trial_step':'yes',
        'output_file':output_file,
        'max_iter':200,
        }
    mxflx.add_ipopt_options(options)

    if ipopt_options:
        mxflx.add_ipopt_options(ipopt_options)

    if sequential:
        b_scale = 3.0
        w_eval0 = mxflx.w_eval.copy()
        for i in range((nmove+1)//2):
            mxflx.get_forces()
            ens = mxflx.energies.copy()
            w_eval = w_eval0.copy()
            ens[i+2:nmove-i]=0.0
            w_eval[i+2:nmove-i]=0.0
            if np.amax(ens)>0.0:
                mxflx.beta=b_scale/np.amax(ens)
            else:
                mxflx.beta=1.0
            mxflx.set_w_eval(w_eval)

            mxflx.solve(tol=0.1)

    b_scale = 5.0
    for _ in range(5):
        mxflx.get_forces()
        ens = mxflx.energies.copy()
        if np.amax(ens)>0.0:
            mxflx.beta = b_scale/np.amax(ens)
        else:
            mxflx.beta = 1.0

        mxflx.solve(tol=0.1)

    return mxflx
