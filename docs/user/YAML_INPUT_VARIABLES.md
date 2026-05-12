# YAML Input Variables

This file is generated from `src/atst_tools/utils/config_schema.py`.
It lists governed non-calculator YAML variables for `atst run`.
Calculator backend variables are documented separately in `CONFIG_REFERENCE.md`.

| YAML path | Level | Type | Default | Meaning |
| --- | --- | --- | --- | --- |
| config_version | top-level | `str` | `'2.0.0'` | Configuration schema version. |
| calculation.neb.type | calculation.type=neb | `'neb'` | `required` | Select the ordinary NEB or DyNEB workflow. |
| calculation.neb.init_chain | calculation.type=neb | `str \| NoneType` | `null` | Initial NEB chain trajectory. |
| calculation.neb.make | calculation.type=neb | `dict` | `null` | Nested chain generation configuration. |
| calculation.neb.make.init_structure | calculation.neb.make | `str` | `required` | Initial-state structure file. |
| calculation.neb.make.final_structure | calculation.neb.make | `str` | `required` | Final-state structure file. |
| calculation.neb.make.n_images | calculation.neb.make | `int` | `required` | Number of intermediate NEB images, excluding endpoints. |
| calculation.neb.make.method | calculation.neb.make | `'IDPP' \| 'linear'` | `'IDPP'` | Interpolation method. |
| calculation.neb.make.output | calculation.neb.make | `str` | `'init_neb_chain.traj'` | Generated chain trajectory path. |
| calculation.neb.make.ts_guess | calculation.neb.make | `str \| NoneType` | `null` | Optional transition-state guess for segmented interpolation. |
| calculation.neb.make.fix | calculation.neb.make | `str \| dict[str, Any] \| NoneType` | `null` | Optional fixed-atom rule, e.g. HEIGHT:DIR. |
| calculation.neb.make.magmom | calculation.neb.make | `str \| dict[str, float] \| NoneType` | `null` | Optional magnetic moments by element. |
| calculation.neb.make.no_align | calculation.neb.make | `bool` | `False` | Disable atom-index alignment before interpolation. |
| calculation.neb.make.format | calculation.neb.make | `str \| NoneType` | `null` | Optional ASE input format override. |
| calculation.neb.trajectory | calculation.type=neb | `str` | `'neb.traj'` | NEB trajectory output. |
| calculation.neb.restart | calculation.type=neb | `bool` | `False` | Restart from the latest complete trajectory band. |
| calculation.neb.climb | calculation.type=neb | `bool` | `True` | Enable climbing-image NEB. |
| calculation.neb.fmax | calculation.type=neb | `float` | `0.05` | Force convergence threshold in eV/Ang. |
| calculation.neb.k | calculation.type=neb | `float \| list[float]` | `0.1` | NEB spring constant(s) in eV/Ang^2. |
| calculation.neb.algorism | calculation.type=neb | `str` | `'improvedtangent'` | ASE NEB tangent method. |
| calculation.neb.parallel | calculation.type=neb | `bool` | `True` | Enable image-level parallelism when MPI is available. |
| calculation.neb.max_steps | calculation.type=neb | `int` | `100` | Maximum optimizer steps. |
| calculation.neb.optimizer | calculation.type=neb | `str` | `'FIRE'` | ASE optimizer name. |
| calculation.neb.endpoint_singlepoint | calculation.type=neb | `'auto' \| 'always' \| 'never'` | `'auto'` | Endpoint result policy before NEB starts. |
| calculation.autoneb.type | calculation.type=autoneb | `'autoneb'` | `required` | Select the AutoNEB workflow. |
| calculation.autoneb.init_chain | calculation.type=autoneb | `str` | `required` | Initial NEB chain trajectory. |
| calculation.autoneb.prefix | calculation.type=autoneb | `str` | `'run_autoneb'` | AutoNEB per-image output prefix. |
| calculation.autoneb.n_simul | calculation.type=autoneb | `int \| NoneType` | `null` | Number of images optimized simultaneously. |
| calculation.autoneb.n_max | calculation.type=autoneb | `int` | `10` | Maximum number of AutoNEB images. |
| calculation.autoneb.algorism | calculation.type=autoneb | `str` | `'improvedtangent'` | ASE NEB tangent method. |
| calculation.autoneb.parallel | calculation.type=autoneb | `bool` | `True` | Enable image-level parallelism when MPI is available. |
| calculation.autoneb.optimizer | calculation.type=autoneb | `'FIRE' \| 'BFGS'` | `'FIRE'` | Optimizer used for AutoNEB iterations. |
| calculation.autoneb.fmax | calculation.type=autoneb | `float \| list[float]` | `0.05` | Force threshold or AutoNEB threshold schedule. |
| calculation.autoneb.maxsteps | calculation.type=autoneb | `int` | `100` | Maximum optimizer steps per AutoNEB iteration. |
| calculation.autoneb.climb | calculation.type=autoneb | `bool` | `True` | Enable climbing image in AutoNEB refinement. |
| calculation.autoneb.iter_folder | calculation.type=autoneb | `str` | `'AutoNEB_iter'` | Directory for AutoNEB iteration history. |
| calculation.autoneb.restart | calculation.type=autoneb | `bool` | `False` | Reuse existing AutoNEB image files. |
| calculation.autoneb.directory | calculation.type=autoneb | `str` | `'autoneb_run'` | Base calculator directory. |
| calculation.autoneb.endpoint_singlepoint | calculation.type=autoneb | `'auto' \| 'always' \| 'never'` | `'auto'` | Endpoint result policy. |
| calculation.dimer.type | calculation.type=dimer | `'dimer'` | `required` | Select the standalone ASE Dimer workflow. |
| calculation.dimer.init_structure | calculation.type=dimer | `str` | `required` | Initial transition-state guess. |
| calculation.dimer.trajectory | calculation.type=dimer | `str` | `'dimer.traj'` | Dimer trajectory output. |
| calculation.dimer.restart | calculation.type=dimer | `bool` | `False` | Restart from the last trajectory frame. |
| calculation.dimer.fmax | calculation.type=dimer | `float` | `0.05` | Force convergence threshold in eV/Ang. |
| calculation.dimer.max_steps | calculation.type=dimer | `int \| NoneType` | `null` | Maximum optimizer steps. |
| calculation.dimer.init_eigenmode_method | calculation.type=dimer | `'displacement' \| 'gauss'` | `'displacement'` | Initial eigenmode strategy. |
| calculation.dimer.displacement_vector | calculation.type=dimer | `str \| NoneType` | `null` | Path to a NumPy displacement vector. |
| calculation.dimer.dimer_separation | calculation.type=dimer | `float` | `0.01` | Finite-difference dimer separation. |
| calculation.dimer.max_num_rot | calculation.type=dimer | `int` | `3` | Maximum dimer rotations per step. |
| calculation.dimer.directory | calculation.type=dimer | `str` | `'dimer_run'` | Calculator working directory. |
| calculation.sella.type | calculation.type=sella | `'sella'` | `required` | Select the standalone Sella saddle-point workflow. |
| calculation.sella.init_structure | calculation.type=sella | `str` | `required` | Initial transition-state guess. |
| calculation.sella.trajectory | calculation.type=sella | `str` | `'sella.traj'` | Sella trajectory output. |
| calculation.sella.restart | calculation.type=sella | `bool` | `False` | Restart from the last trajectory frame. |
| calculation.sella.fmax | calculation.type=sella | `float` | `0.05` | Force convergence threshold in eV/Ang. |
| calculation.sella.max_steps | calculation.type=sella | `int \| NoneType` | `null` | Maximum optimizer steps. |
| calculation.sella.eta | calculation.type=sella | `float` | `0.005` | Sella eta parameter. |
| calculation.sella.order | calculation.type=sella | `int` | `1` | Saddle-point order. |
| calculation.sella.directory | calculation.type=sella | `str` | `'sella_run'` | Calculator working directory. |
| calculation.d2s.type | calculation.type=d2s | `'d2s'` | `required` | Select the double-ended to single-ended transition-state workflow. |
| calculation.d2s.method | calculation.type=d2s | `'dimer' \| 'sella'` | `'dimer'` | Single-ended refinement method. |
| calculation.d2s.init_file | calculation.type=d2s | `str` | `required` | Initial-state structure file. |
| calculation.d2s.final_file | calculation.type=d2s | `str` | `required` | Final-state structure file. |
| calculation.d2s.directory | calculation.type=d2s | `str` | `'run_d2s'` | Base workflow directory. |
| calculation.d2s.restart | calculation.type=d2s | `bool` | `False` | Reuse rough NEB and single-ended checkpoints. |
| calculation.d2s.endpoint_singlepoint | calculation.type=d2s | `'auto' \| 'always' \| 'never'` | `'auto'` | Endpoint result policy. |
| calculation.d2s.endpoint_optimization | calculation.type=d2s | `dict` | `schema defaults` | Endpoint optimization policy. |
| calculation.d2s.endpoint_optimization.enabled | calculation.d2s.endpoint_optimization | `bool` | `True` | Optimize endpoints before rough DyNEB. |
| calculation.d2s.endpoint_optimization.skip_if_has_results | calculation.d2s.endpoint_optimization | `bool` | `True` | Skip endpoints that already have energy and forces. |
| calculation.d2s.endpoint_optimization.fmax | calculation.d2s.endpoint_optimization | `float` | `0.05` | Endpoint optimization force threshold. |
| calculation.d2s.endpoint_optimization.max_steps | calculation.d2s.endpoint_optimization | `int` | `200` | Endpoint optimization step limit. |
| calculation.d2s.neb | calculation.type=d2s | `dict` | `schema defaults` | Rough DyNEB configuration. |
| calculation.d2s.neb.n_images | calculation.d2s.neb | `int` | `8` | Number of intermediate rough DyNEB images. |
| calculation.d2s.neb.fmax | calculation.d2s.neb | `float` | `0.8` | Rough DyNEB force threshold. |
| calculation.d2s.neb.algorism | calculation.d2s.neb | `str` | `'improvedtangent'` | DyNEB tangent method. |
| calculation.d2s.neb.climb | calculation.d2s.neb | `bool` | `True` | Enable climbing image in rough DyNEB. |
| calculation.d2s.neb.max_steps | calculation.d2s.neb | `int` | `200` | Rough DyNEB maximum steps. |
| calculation.d2s.dimer | calculation.type=d2s | `dict` | `schema defaults` | Dimer refinement configuration. |
| calculation.d2s.dimer.fmax | calculation.d2s.dimer | `float` | `0.05` | Dimer force threshold. |
| calculation.d2s.dimer.max_steps | calculation.d2s.dimer | `int \| NoneType` | `null` | Dimer maximum steps. |
| calculation.d2s.dimer.trajectory | calculation.d2s.dimer | `str` | `'dimer.traj'` | Dimer trajectory output. |
| calculation.d2s.dimer.directory | calculation.d2s.dimer | `str \| NoneType` | `null` | Dimer calculator directory. |
| calculation.d2s.dimer.init_eigenmode_method | calculation.d2s.dimer | `'displacement' \| 'gauss'` | `'displacement'` | Dimer eigenmode method. |
| calculation.d2s.dimer.dimer_separation | calculation.d2s.dimer | `float` | `0.01` | Dimer separation. |
| calculation.d2s.dimer.max_num_rot | calculation.d2s.dimer | `int` | `3` | Maximum dimer rotations per step. |
| calculation.d2s.sella | calculation.type=d2s | `dict` | `schema defaults` | Sella refinement configuration. |
| calculation.d2s.sella.fmax | calculation.d2s.sella | `float` | `0.05` | Sella force threshold. |
| calculation.d2s.sella.max_steps | calculation.d2s.sella | `int \| NoneType` | `null` | Sella maximum steps. |
| calculation.d2s.sella.trajectory | calculation.d2s.sella | `str` | `'sella.traj'` | Sella trajectory output. |
| calculation.d2s.sella.directory | calculation.d2s.sella | `str \| NoneType` | `null` | Sella calculator directory. |
| calculation.d2s.sella.eta | calculation.d2s.sella | `float` | `0.005` | Sella eta parameter. |
| calculation.d2s.sella.order | calculation.d2s.sella | `int` | `1` | Saddle-point order. |
| calculation.d2s.vibration | calculation.type=d2s | `dict` | `schema defaults` | Optional vibration configuration. |
| calculation.d2s.vibration.enabled | calculation.d2s.vibration | `bool` | `False` | Run vibration after single-ended refinement. |
| calculation.d2s.vibration.indices | calculation.d2s.vibration | `'auto' \| 'all' \| list[int]` | `'auto'` | Atom index selection. |
| calculation.d2s.vibration.threshold | calculation.d2s.vibration | `float` | `0.1` | Displacement threshold for auto indices. |
| calculation.d2s.vibration.delta | calculation.d2s.vibration | `float` | `0.01` | Finite-difference displacement in Ang. |
| calculation.d2s.vibration.nfree | calculation.d2s.vibration | `2 \| 4` | `2` | Number of displacements per degree of freedom. |
| calculation.d2s.vibration.name | calculation.d2s.vibration | `str` | `'d2s_vib'` | ASE vibration cache prefix. |
| calculation.d2s.vibration.results_file | calculation.d2s.vibration | `str` | `'d2s_vibration_results.json'` | Vibration JSON output. |
| calculation.d2s.vibration.directory | calculation.d2s.vibration | `str` | `'VIBRATION'` | Vibration calculator directory. |
| calculation.d2s.vibration.thermochemistry | calculation.d2s.vibration | `dict` | `schema defaults` | Thermochemistry settings. |
| calculation.d2s.vibration.thermochemistry.model | calculation.d2s.vibration.thermochemistry | `'harmonic' \| 'ideal_gas'` | `'harmonic'` | Thermochemistry model. |
| calculation.d2s.vibration.thermochemistry.temperature | calculation.d2s.vibration.thermochemistry | `float` | `300.0` | Temperature in Kelvin. |
| calculation.d2s.vibration.thermochemistry.ignore_imag_modes | calculation.d2s.vibration.thermochemistry | `bool` | `True` | Ignore imaginary modes in thermochemistry. |
| calculation.d2s.vibration.thermochemistry.pressure | calculation.d2s.vibration.thermochemistry | `float` | `101325.0` | Pressure in Pa for ideal-gas thermo. |
| calculation.d2s.vibration.thermochemistry.geometry | calculation.d2s.vibration.thermochemistry | `'monatomic' \| 'linear' \| 'nonlinear'` | `'nonlinear'` | Molecular geometry for ideal-gas thermo. |
| calculation.d2s.vibration.thermochemistry.symmetrynumber | calculation.d2s.vibration.thermochemistry | `int` | `1` | Rotational symmetry number. |
| calculation.d2s.vibration.thermochemistry.spin | calculation.d2s.vibration.thermochemistry | `float` | `0.0` | Spin for ideal-gas thermo. |
| calculation.d2s.vibration.thermochemistry.potentialenergy | calculation.d2s.vibration.thermochemistry | `float` | `0.0` | Potential energy override for ideal-gas thermo. |
| calculation.relax.type | calculation.type=relax | `'relax'` | `required` | Select the structure relaxation workflow. |
| calculation.relax.init_structure | calculation.type=relax | `str` | `required` | Initial structure file. |
| calculation.relax.fmax | calculation.type=relax | `float` | `0.05` | Force convergence threshold in eV/Ang. |
| calculation.relax.max_steps | calculation.type=relax | `int` | `200` | Maximum optimizer steps. |
| calculation.relax.optimizer | calculation.type=relax | `str` | `'FIRE'` | ASE optimizer name. |
| calculation.relax.trajectory | calculation.type=relax | `str` | `'relax.traj'` | Relaxation trajectory output. |
| calculation.relax.logfile | calculation.type=relax | `str` | `'relax.log'` | Optimizer log file. |
| calculation.relax.restart | calculation.type=relax | `bool` | `False` | Restart from the last trajectory frame. |
| calculation.relax.directory | calculation.type=relax | `str` | `'relax_run'` | Calculator working directory. |
| calculation.vibration.type | calculation.type=vibration | `'vibration'` | `required` | Select the finite-difference vibration workflow. |
| calculation.vibration.init_structure | calculation.type=vibration | `str` | `required` | Optimized structure for finite-difference vibrations. |
| calculation.vibration.delta | calculation.type=vibration | `float` | `0.01` | Finite-difference displacement in Ang. |
| calculation.vibration.nfree | calculation.type=vibration | `2 \| 4` | `2` | Number of displacements per degree of freedom. |
| calculation.vibration.indices | calculation.type=vibration | `list[int] \| NoneType` | `null` | Atom indices to vibrate; None means all atoms. |
| calculation.vibration.name | calculation.type=vibration | `str` | `'vib'` | ASE vibration cache prefix. |
| calculation.vibration.restart | calculation.type=vibration | `bool` | `False` | Reuse existing vibration cache files. |
| calculation.vibration.directory | calculation.type=vibration | `str` | `'vib_run'` | Calculator working directory. |
| calculation.vibration.thermochemistry | calculation.type=vibration | `dict` | `schema defaults` | Thermochemistry settings. |
| calculation.vibration.thermochemistry.model | calculation.vibration.thermochemistry | `'harmonic' \| 'ideal_gas'` | `'harmonic'` | Thermochemistry model. |
| calculation.vibration.thermochemistry.temperature | calculation.vibration.thermochemistry | `float` | `300.0` | Temperature in Kelvin. |
| calculation.vibration.thermochemistry.ignore_imag_modes | calculation.vibration.thermochemistry | `bool` | `True` | Ignore imaginary modes in thermochemistry. |
| calculation.vibration.thermochemistry.pressure | calculation.vibration.thermochemistry | `float` | `101325.0` | Pressure in Pa for ideal-gas thermo. |
| calculation.vibration.thermochemistry.geometry | calculation.vibration.thermochemistry | `'monatomic' \| 'linear' \| 'nonlinear'` | `'nonlinear'` | Molecular geometry for ideal-gas thermo. |
| calculation.vibration.thermochemistry.symmetrynumber | calculation.vibration.thermochemistry | `int` | `1` | Rotational symmetry number. |
| calculation.vibration.thermochemistry.spin | calculation.vibration.thermochemistry | `float` | `0.0` | Spin for ideal-gas thermo. |
| calculation.vibration.thermochemistry.potentialenergy | calculation.vibration.thermochemistry | `float` | `0.0` | Potential energy override for ideal-gas thermo. |
| calculation.irc.type | calculation.type=irc | `'irc'` | `required` | Select the Sella intrinsic reaction coordinate workflow. |
| calculation.irc.init_structure | calculation.type=irc | `str` | `required` | Transition-state structure file. |
| calculation.irc.trajectory | calculation.type=irc | `str` | `'irc_log.traj'` | IRC trajectory output. |
| calculation.irc.normalized_trajectory | calculation.type=irc | `str \| NoneType` | `null` | Normalized trajectory for direction=both. |
| calculation.irc.direction | calculation.type=irc | `'both' \| 'forward' \| 'reverse'` | `'both'` | IRC direction. |
| calculation.irc.restart | calculation.type=irc | `bool` | `False` | Append from the last trajectory frame. |
| calculation.irc.directory | calculation.type=irc | `str` | `'irc_run'` | Calculator working directory. |
| calculation.irc.fmax | calculation.type=irc | `float` | `0.05` | IRC force threshold. |
| calculation.irc.max_steps | calculation.type=irc | `int` | `1000` | Maximum steps per IRC direction. |
| calculation.irc.dx | calculation.type=irc | `float` | `0.1` | IRC step size. |
| calculation.irc.eta | calculation.type=irc | `float` | `0.0001` | Sella IRC eta parameter. |
| calculation.irc.gamma | calculation.type=irc | `float` | `0.1` | Sella IRC gamma parameter. |
| calculation.irc.irctol | calculation.type=irc | `float` | `0.01` | IRC tolerance. |
| calculation.irc.keep_going | calculation.type=irc | `bool` | `False` | Forwarded to sella.IRC. |
