"""ASE-native NEB compatibility wrapper used by ATST-Tools."""

from atst_tools.utils.mpi import bootstrap_mpi_for_ase

bootstrap_mpi_for_ase()

import threading

import numpy as np
from ase.build import minimize_rotation_and_translation
from ase.mep.neb import NEB, NEBState
from ase.optimize.precon import Precon, PreconImages


def _world_sum_scalar(world, value):
    """Return a scalar sum using the communicator's modern API when present."""
    if hasattr(world, "sum_scalar"):
        return world.sum_scalar(value)
    return world.sum(value)


class AbacusNEB(NEB):
    """NEB wrapper retaining ATST's public class name.

    The implementation follows ASE 3.28.0 `BaseNEB.get_forces()` with the
    development-branch real-force fix backported from `ase/ase` commits
    `57d55d02d` and `e7d9968ca`. This keeps trajectory images populated with
    unconstrained forces without reintroducing ATST-specific stress handling.
    """

    def __init__(
        self,
        images,
        k=0.1,
        climb=False,
        parallel=False,
        remove_rotation_and_translation=False,
        world=None,
        method="improvedtangent",
        allow_shared_calculator=False,
        precon=None,
        **kwargs,
    ):
        """Initialize an ASE NEB object under the legacy ATST class name."""
        super().__init__(
            images,
            k=k,
            climb=climb,
            parallel=parallel,
            remove_rotation_and_translation=remove_rotation_and_translation,
            world=world,
            method=method,
            allow_shared_calculator=allow_shared_calculator,
            precon=precon,
            **kwargs,
        )

    def get_forces(self):
        """Evaluate NEB forces using ASE 3.28.0 plus real-force backport."""
        images = self.images

        if not self.allow_shared_calculator:
            calculators = [
                image.calc for image in images if image.calc is not None
            ]
            if len(set(calculators)) != len(calculators):
                msg = (
                    "One or more NEB images share the same calculator.  "
                    "Each image must have its own calculator.  "
                    "You may wish to use the ase.mep.SingleCalculatorNEB "
                    "class instead, although using separate calculators "
                    "is recommended."
                )
                raise ValueError(msg)

        forces = np.zeros(((self.nimages - 2), self.natoms, 3))
        energies = np.zeros(self.nimages)
        real_forces = np.zeros((self.nimages, self.natoms, 3))

        if self.remove_rotation_and_translation:
            for i in range(1, self.nimages):
                minimize_rotation_and_translation(images[i - 1], images[i])

        if self.method != "aseneb":
            energies[0] = images[0].get_potential_energy()
            energies[-1] = images[-1].get_potential_energy()

        if not self.parallel:
            for i in range(1, self.nimages - 1):
                forces[i - 1] = images[i].get_forces()
                energies[i] = images[i].get_potential_energy()
                real_forces[i] = images[i].get_forces(apply_constraint=False)

        elif self.world.size == 1:

            def run(image, energies, forces, real_forces):
                forces[:] = image.get_forces()
                energies[:] = image.get_potential_energy()
                real_forces[:] = image.get_forces(apply_constraint=False)

            threads = [
                threading.Thread(
                    target=run,
                    args=(
                        images[i],
                        energies[i : i + 1],
                        forces[i - 1 : i],
                        real_forces[i : i + 1],
                    ),
                )
                for i in range(1, self.nimages - 1)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            i = self.world.rank * (self.nimages - 2) // self.world.size + 1
            local_energies = np.zeros(self.nimages)
            try:
                forces[i - 1] = images[i].get_forces()
                energies[i] = images[i].get_potential_energy()
                local_energies[i] = energies[i]
                real_forces[i] = images[i].get_forces(apply_constraint=False)
            except Exception:
                error = _world_sum_scalar(self.world, 1.0)
                raise
            else:
                error = _world_sum_scalar(self.world, 0.0)
                if error:
                    raise RuntimeError("Parallel NEB failed!")

            self.world.sum(local_energies)
            self.world.sum(forces)
            self.world.sum(real_forces)
            energies[1:-1] = local_energies[1:-1]

        if self.precon is None or isinstance(self.precon, (str, Precon, list)):
            self.precon = PreconImages(self.precon, images)

        precon_forces = self.precon.apply(forces, index=slice(1, -1))

        self.energies = energies
        self.real_forces = real_forces

        state = NEBState(self, images, energies)
        self.imax = state.imax
        self.emax = state.emax

        spring1 = state.spring(0)

        self.residuals = []
        for i in range(1, self.nimages - 1):
            spring2 = state.spring(i)
            tangent = self.neb_method.get_tangent(state, spring1, spring2, i)

            tangential_force = np.vdot(forces[i - 1], tangent)
            imgforce = precon_forces[i - 1]

            if i == self.imax and self.climb:
                if self.method == "aseneb":
                    tangent_mag = np.vdot(tangent, tangent)
                    imgforce -= 2 * tangential_force / tangent_mag * tangent
                else:
                    imgforce -= 2 * tangential_force * tangent
            else:
                self.neb_method.add_image_force(
                    state,
                    tangential_force,
                    tangent,
                    imgforce,
                    spring1,
                    spring2,
                    i,
                )
                residual = self.precon.get_residual(i, imgforce)
                self.residuals.append(residual)

            spring1 = spring2

        return precon_forces.reshape((-1, 3))
