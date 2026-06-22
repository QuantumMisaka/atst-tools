# PyDMF: A Python package for double-ended reaction path/transition state optimization

![CI](https://github.com/shin1koda/dmf/actions/workflows/tests.yml/badge.svg)

## Overview

This package provides a Python implementation of the direct MaxFlux (DMF) method and the flat-bottom elastic network model (FB-ENM). These tools offer a variational framework for reaction-path optimization and an efficient approach to generating physically plausible initial paths.

The software is intended for researchers who use ASE-compatible calculators and require either a method for obtaining near–transition-state structures without relying on second or higher energy derivatives, or a method for interpolating between two structures in a chemically plausible manner.

 - Compared with existing double-ended reaction-path optimization methods (e.g., NEB), DMF improves computational efficiency in terms of both the number of energy-evaluation points along the path and the number of optimization iterations.

 - Compared with existing initial-path generation approaches (e.g., IDPP), FB-ENM provides more energetically preferable paths with improved robustness.


## Recent Updates

- v1.2.0: GPU acceleration is now available, thanks to a contribution by @t-0hmura . See [README_TORCH.md](https://github.com/shin1koda/dmf/blob/main/README_TORCH.md) and [PR #3](https://github.com/shin1koda/dmf/pull/3) for details.


## Requirements

- [ASE](https://ase-lib.org/)
- [cyipopt](https://cyipopt.readthedocs.io/en/stable/)


## Installation

We generally recommend installing this package via **conda**, as `cyipopt` is most reliably installed through conda.

```bash
conda create -n pydmf python=3.10
conda activate pydmf
conda install -c conda-forge ase cyipopt
pip install pydmf
```

If you prefer to install `cyipopt` without using conda, please follow its [official installation guide](https://cyipopt.readthedocs.io/en/stable/install.html).
**After installing cyipopt**, you can install PyDMF via pip:

```bash
pip install pydmf
```


## Example usage

### Basic usage

PyDMF is used as part of an ASE script. For the basics of ASE, please refer to its [official documentation](https://ase-lib.org/gettingstarted/gettingstarted.html).
An example script is provided in `sample/sample.py` of [PyDMF GitHub repository](https://github.com/shin1koda/dmf):

```python
import numpy as np
from ase.io import write, read
from ase.calculators.emt import EMT
from dmf import DirectMaxFlux, interpolate_fbenm

# read react.xyz and prod.xyz
ref_images = [read('react.xyz'), read('prod.xyz')]

# generate initial path by FB-ENM
mxflx_fbenm = interpolate_fbenm(ref_images,correlated=True)

# write initial path and its coefficients
write('sample_ini.traj',mxflx_fbenm.images)
coefs = mxflx_fbenm.coefs.copy()
np.save('sample_ini_coefs',coefs)

# set up a variational problem of the direct MaxFlux method
mxflx = DirectMaxFlux(ref_images,coefs=coefs,nmove=3,update_teval=True)

# set up calculators
for image in mxflx.images:
    image.calc = EMT()

# solve the variational problem
mxflx.add_ipopt_options({'output_file':'sample_ipopt.out'})
mxflx.solve(tol='middle')

# write final path and history of x(tmax)
write('sample_fin.traj',mxflx.images)
write('sample_tmax.traj',mxflx.history.images_tmax)
```

You can run it simply by:

```bash
git clone https://github.com/shin1koda/dmf
cd dmf/sample
python sample.py
```

Running the script produces several output files, including:

 - `sample_ini.traj`: FB-ENM–interpolated path written in ASE trajectory format
 - `sample_fin.traj`: Optimized reaction path using the EMT potential
 - `sample_tmax.traj`: History of the estimated highest-energy point during optimization

### Parallel energy/force evaluation

PyDMF supports parallel energy and force evaluations at the energy evaluation points along the path. See [README_PARALLEL.md](https://github.com/shin1koda/dmf/blob/main/README_PARALLEL.md) for details.

## Documentation

For more details, please refer to the [API documentation](https://shin1koda.github.io/dmf/).


## Citation

 1. S.-i. Koda and  S. Saito, Locating Transition States by Variational Reaction Path Optimization with an Energy-Derivative-Free Objective Function, JCTC, 20, 2798–2811 (2024). [doi: 10.1021/acs.jctc.3c01246](https://doi.org/10.1021/acs.jctc.3c01246)
 1. S.-i. Koda and  S. Saito, Flat-bottom Elastic Network Model for Generating Improved Plausible Reaction Paths, JCTC, 20, 7176−7187 (2024). [doi: 10.1021/acs.jctc.4c00792](https://doi.org/10.1021/acs.jctc.4c00792)
 1. S.-i. Koda and  S. Saito, Correlated Flat-bottom Elastic Network Model for Improved Bond Rearrangement in Reaction Paths, JCTC, 21, 3513−3522 (2025). [doi: 10.1021/acs.jctc.4c01549](https://doi.org/10.1021/acs.jctc.4c01549)

Please cite:

 - Ref. 1 when you use the direct MaxFlux method
 - Ref. 2 when you use the flat-bottom elastic network model
 - Ref. 3 when you use the correlated flat-bottom elastic network model


## Related works

PyDMF has been used in the following applications.

 - dmf-g16 (developed by our group): Wrapper software that enables DMF calculations with Gaussian and its native input formats. [Paper](https://doi.org/10.1002/jcc.70378) & [GitHub](https://github.com/shin1koda/dmf-g16).

 - ColabReaction (developed by Karasawa et al.): Web-based application that integrates PyDMF and ML potential UMA. [Application](https://colabreaction.net/), [paper](https://doi.org/10.1021/acs.jcim.5c02398), & [GitHub](https://github.com/BILAB/ColabReaction).


## Community guidelines

### Contributing

Contributions to this project are welcome. If you would like to contribute new features, improvements, or documentation, please open a pull request on GitHub.
Before submitting a PR, we recommend opening a short issue to discuss the proposed change.

### Reporting issues

If you encounter a problem, unexpected behavior, or a potential bug, please report it through the GitHub issue tracker:

https://github.com/shin1koda/dmf/issues

When reporting an issue, please include:
- A clear description of the problem
- Steps to reproduce the issue
- Your environment (Python version, ASE version, cyipopt version, etc.)
- Any relevant error messages or logs

### Seeking support

If you have questions about the usage of the package, or need help integrating it into your workflow, feel free to open an issue labeled “question” on GitHub.
We will do our best to provide guidance based on availability.


## License

This project is distributed under the MIT License.
