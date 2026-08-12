"""AutoNEB stress-freezing tests for the ATST NEB compatibility layer."""

from __future__ import annotations

import numpy as np
from ase import Atoms

from helpers import DummyCalc


class _NoStressCalc(DummyCalc):
    def calculate(self, atoms=None, properties=("energy",), system_changes=None):
        super().calculate(atoms, properties, system_changes)
        self.results.pop("stress", None)


def _image(x: float, with_stress: bool) -> Atoms:
    atoms = Atoms("H", positions=[[x, 0.0, 0.0]])
    calc = DummyCalc() if with_stress else _NoStressCalc()
    atoms.calc = calc
    return atoms


def test_autoneb_store_E_and_F_in_spc_with_stress_serial():
    from atst_tools.mep.autoneb import _store_E_and_F_in_spc_with_stress
    from atst_tools.mep.neb import AbacusNEB

    chain = [_image(0.0, True), _image(1.0, True), _image(2.0, True)]
    neb = AbacusNEB(chain, parallel=False)
    _store_E_and_F_in_spc_with_stress(neb)
    assert "stress" in neb.images[1].calc.results
    assert np.asarray(neb.images[1].calc.results["stress"]).shape == (6,)


def test_autoneb_store_E_and_F_in_spc_with_stress_absent():
    from atst_tools.mep.autoneb import _store_E_and_F_in_spc_with_stress
    from atst_tools.mep.neb import AbacusNEB

    chain = [_image(0.0, False), _image(1.0, False), _image(2.0, False)]
    neb = AbacusNEB(chain, parallel=False)
    _store_E_and_F_in_spc_with_stress(neb)
    assert "stress" not in neb.images[1].calc.results
