"""atst prepare acceptance over repository example input directories."""

from __future__ import annotations

from pathlib import Path

import pytest

from atst_tools.api import validate_config
from atst_tools.utils.reverse_config import (
    build_config_from_abacus_dir,
    endpoint_has_energy_forces,
)


def test_examples_generate_valid_configs():
    """P0: a real repository ABACUS run dir reverse-generates a valid config.

    Workflow dirs like ``examples/01_neb_Li-Si`` hold ``config.yaml`` rather than
    ABACUS INPUT/STRU/KPT. The only complete ABACUS run dirs in ``examples/``
    live under ``examples/18_dmf_production_validation/runs/*/initial``. If the
    checkout has none, the real-dir acceptance is covered by SAI E2E (SPEC R1/R2).
    """
    examples = Path("examples")
    if not examples.is_dir():
        pytest.skip("examples/ not available in this checkout")

    candidates = sorted(examples.glob("18_dmf_production_validation/runs/*/initial"))
    run_dir = next(
        (
            d
            for d in candidates
            if (d / "INPUT").is_file()
            and (d / "STRU").is_file()
            and (d / "KPT").is_file()
            # The output directory is OUT.ABACUS; keep the same glob the gate
            # uses so a case difference here cannot silently skip the fixture.
            and bool(list(d.glob("OUT*/running*.log")))
        ),
        None,
    )
    if run_dir is None:
        pytest.skip(
            "no complete ABACUS run dir in examples/; real-dir acceptance is "
            "covered by SAI E2E (SPEC R1/R2)"
        )

    # The real run dir must satisfy the endpoint energy+forces gate (legacyio,
    # SPEC R-8/R2) and reverse-generate a schema-valid config.
    assert endpoint_has_energy_forces(run_dir) is True
    config = build_config_from_abacus_dir(run_dir, gate_dirs=[run_dir])
    validate_config(config)
    abacus = config["calculator"]["abacus"]
    assert abacus["parameters"]["calculation"] == "scf"  # floor
    assert abacus["parameters"]["cal_force"] == 1  # floor
    assert "pseudo_dir" not in abacus["parameters"]  # promoted to top level
    assert "orbital_dir" not in abacus["parameters"]
    # kpts shape mirrors the toolbox _runtime_kpts: list grid for INPUT
    # selectors (gamma_only/kspacing) or an mp-sampling dict for KPT files.
    assert isinstance(abacus["kpts"], (list, dict))
    assert abacus["pseudopotentials"]
    assert abacus["basissets"]
