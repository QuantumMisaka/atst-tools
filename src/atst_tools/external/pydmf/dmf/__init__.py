"""
This package provides an implementation of the Direct MaxFlux (DMF) method
for variational reaction-path optimization, together with the FB-ENM family
of elastic network model (ENM) calculators and several supporting utility
functions.

The public API of the package is intentionally kept small and consists of:

* **DirectMaxFlux**
    The main optimization class implementing the Direct MaxFlux method.

* **HistoryDMF**
    A container storing the optimization history produced by
    :class:`DirectMaxFlux`.

* **FB_ENM**, **CFB_ENM**, **FB_ENM_Bonds**
    The family of FB-ENM calculators compatible with ASE, used for
    computing energies and forces along structural pathways.

* **interpolate_fbenm**
    A utility function for interpolating given structures from the FB-ENM
    calculators.

Internal implementation classes, including the abstract base class
``VariationalPathOpt`` and various helper routines, are **not** part of the
public API and may change without notice.

All classes and functions listed above can be imported directly from
the top-level package, e.g.,

.. code-block:: python

    from dmf import DirectMaxFlux, FB_ENM, interpolate_fbenm

See each API page for detailed documentation.
"""

try:
    import cyipopt
except ImportError:
    raise ImportError(
        "\n"
        "The PyDMF package requires the 'cyipopt' library.\n"
        "Please install cyipopt from conda-forge BEFORE installing dmf:\n\n"
        "    conda install -c conda-forge cyipopt \n\n"
    )
from .dmf import DirectMaxFlux,HistoryDMF
from .fbenm import FB_ENM, CFB_ENM, FB_ENM_Bonds
from .interpolate import interpolate_fbenm

__all__ = [
    "DirectMaxFlux",
    "HistoryDMF",
    "FB_ENM",
    "CFB_ENM",
    "FB_ENM_Bonds",
    "interpolate_fbenm",
]
