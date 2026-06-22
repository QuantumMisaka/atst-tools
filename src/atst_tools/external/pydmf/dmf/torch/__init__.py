"""
PyTorch-accelerated DMF utilities.

This package mirrors the public API of ``dmf`` but runs internal tensor
operations with PyTorch when available.
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
    "interpolate_fbenm_new",
]
