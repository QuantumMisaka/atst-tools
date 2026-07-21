"""Run an ATST-specific H2/Au CCQN automatic-reactive-mode calculation.

This Python API companion to ``config_auto_modes.yaml`` starts from the supplied
H2/Au transition-state guess and lets CCQN enumerate and select reactive modes.
Install it with ``pip install atst-tools``; add ``[parallel]`` only when an MPI
workflow is launched externally. Project, installation, and API computation
details live at https://github.com/QuantumMisaka/atst-tools ; use the repository
``README.md`` and ``docs/user/CLI_REFERENCE.md`` for CLI/YAML operation.

The example deliberately uses ASE EMT as a lightweight calculator fixture. It
demonstrates the stable ``atst_tools.api`` boundary and does not require a
production backend to run the example contract test.

For production ABACUS CCQN injection, provide a caller-created, correctly configured
``abacuslite`` ASE calculator. The caller must complete the normal
ABACUS pseudopotential, orbital, executable/runtime, and site setup; ATST does not configure
it. ATST-Tools does not install or require ABACUS as a package
dependency for this API.
"""

from ase.calculators.emt import EMT
from ase.io import read

from atst_tools.api import CCQNOptions, run_ccqn


atoms = read("inputs/ccqn_init.stru")
result = run_ccqn(
    atoms,
    EMT(),
    CCQNOptions(
        trajectory="outputs/ccqn_api_auto_modes.traj",
        logfile="outputs/ccqn_api_auto_modes.log",
        final_structure="outputs/ccqn_api_auto_modes_final.extxyz",
        mode_manifest="outputs/ccqn_api_auto_modes_manifest.json",
        diagnostics_file="outputs/ccqn_api_auto_modes_diagnostics.json",
        artifact_manifest="outputs/atst_artifacts_api_auto_modes.json",
        auto_reactive_bonds={
            "enabled": True,
            "molecule_indices": "1-2",
            "active_catalyst_indices": "3-66",
            "cutoff_A": 3.5,
            "max_modes": 8,
            "max_bonds_per_mode": 1,
        },
    ),
)
print(result.status, result.metadata["backend_source"])
