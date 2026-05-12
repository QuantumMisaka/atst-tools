# AbacusNEB implementation
# part of ATST-Tools

import threading
import numpy as np
from ase.mep.neb import NEB, NEBState as _NEBState
from ase.parallel import world
from ase.io import Trajectory
from ase.optimize import FIRE

class AbacusNEB(NEB):
    """
    Customized NEB class for ABACUS that handles stress tensor retrieval and broadcasting.
    
    This class extends ASE's NEB to support:
    1.  Collection and broadcasting of stress tensors (for future variable-cell NEB support).
    2.  Improved parallel execution handling for ATST-Tools environment.
    3.  Retrieval of "real" forces (without constraints) for analysis.

    Attributes:
        stresses (np.ndarray): Array storing stress tensors for images.
        real_forces (np.ndarray): Array storing unconstrained forces.
        energies (np.ndarray): Array storing potential energies.
    """
    def __init__(self, images, k=0.1, climb=False, parallel=False,
                 remove_rotation_and_translation=False, world=None,
                 method='aseneb', allow_shared_calculator=False,
                 precon=None, **kwargs):
        """
        Initialize AbacusNEB.

        Args:
            images (list): List of Atoms objects (images).
            k (float or list): Spring constant(s) in eV/Angstrom.
            climb (bool): Whether to use climbing image NEB.
            parallel (bool): Whether to parallelize force calculations over MPI.
            remove_rotation_and_translation (bool): Whether to minimize rotation/translation.
            world: MPI communicator.
            method (str): Tangent method ('aseneb', 'improvedtangent', etc.).
            allow_shared_calculator (bool): Allow shared calculator instance.
            precon: Preconditioner object or configuration.
            **kwargs: Additional arguments passed to ASE NEB.
        """
        super().__init__(images, k=k, climb=climb, parallel=parallel,
                         remove_rotation_and_translation=remove_rotation_and_translation,
                         world=world, method=method,
                         allow_shared_calculator=allow_shared_calculator,
                         precon=precon, **kwargs)
        # Extra storage for stress
        self.stresses = None 

    def get_forces(self):
        """
        Evaluate and return the NEB forces.

        This method overrides ASE's get_forces to inject stress collection and
        broadcast additional data (real_forces, stress) across MPI ranks.

        Returns:
            np.ndarray: The projected NEB forces (flattened).
        """
        images = self.images
        
        # ... (Standard ASE checks for shared calculators) ...

        forces = np.empty(((self.nimages - 2), self.natoms, 3))
        energies = np.empty(self.nimages)
        
        # ATST-Tools Extension: Storage for real forces (without constraints) and stresses
        real_forces = np.empty(((self.nimages - 2), self.natoms, 3))
        stresses = np.empty(((self.nimages - 2), 6))

        if self.remove_rotation_and_translation:
            for i in range(1, self.nimages):
                from ase.build import minimize_rotation_and_translation
                minimize_rotation_and_translation(images[i - 1], images[i])

        if self.method != 'aseneb':
            energies[0] = images[0].get_potential_energy()
            energies[-1] = images[-1].get_potential_energy()

        if not self.parallel:
            # Serial execution
            for i in range(1, self.nimages - 1):
                forces[i - 1] = images[i].get_forces()
                energies[i] = images[i].get_potential_energy()
                # ATST-Tools: Try getting stress if available
                try:
                    stresses[i-1] = images[i].get_stress()
                except:
                    stresses[i-1] = np.zeros(6)

        elif self.world.size == 1:
            # Threaded execution (rarely used with MPI)
            def run(image, energies, forces):
                forces[:] = image.get_forces()
                energies[:] = image.get_potential_energy()

            threads = [threading.Thread(target=run,
                                        args=(images[i],
                                              energies[i:i + 1],
                                              forces[i - 1:i]))
                       for i in range(1, self.nimages - 1)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        else:
            # Parallelize over images (MPI)
            i = self.world.rank * (self.nimages - 2) // self.world.size + 1
            try:
                forces[i - 1] = images[i].get_forces()
                # ATST-Tools: Store real forces and stresses
                real_forces[i - 1] = images[i].get_forces(apply_constraint=False)
                energies[i] = images[i].get_potential_energy()
                try:
                    stresses[i - 1] = images[i].get_stress()
                except:
                    stresses[i - 1] = np.zeros(6)
            except Exception:
                # Make sure other images also fail:
                error = self.world.sum(1.0)
                raise
            else:
                error = self.world.sum(0.0)
                if error:
                    raise RuntimeError('Parallel NEB failed!')

            # Broadcast results
            for i in range(1, self.nimages - 1):
                root = (i - 1) * self.world.size // (self.nimages - 2)
                self.world.broadcast(energies[i:i + 1], root)
                self.world.broadcast(forces[i - 1], root)
                # ATST-Tools: Broadcast extended data
                self.world.broadcast(real_forces[i - 1], root)
                self.world.broadcast(stresses[i - 1:i], root)

        # Preconditioner logic (standard ASE)
        if (self.precon is None or isinstance(self.precon, str) or
                isinstance(self.precon, list)): # simplified check
            from ase.optimize.precon import PreconImages
            self.precon = PreconImages(self.precon, images)

        precon_forces = self.precon.apply(forces, index=slice(1, -1))

        # Save for later use in iterimages:
        self.energies = energies
        self.real_forces = real_forces
        self.stresses = stresses 

        # RE-IMPLEMENTATION of NEB Force Projection
        state = _NEBState(self, images, energies)
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
                if self.method == 'aseneb':
                    tangent_mag = np.vdot(tangent, tangent)
                    imgforce -= 2 * tangential_force / tangent_mag * tangent
                else:
                    imgforce -= 2 * tangential_force * tangent
            else:
                self.neb_method.add_image_force(state, tangential_force,
                                                tangent, imgforce, spring1,
                                                spring2, i)
                residual = self.precon.get_residual(i, imgforce)
                self.residuals.append(residual)
            spring1 = spring2

        return precon_forces.reshape((-1, 3))

    def iterimages(self):
        """
        Yield images with calculated properties frozen attached.

        Allows Trajectory to write images with the correct energy, forces, and stress
        that were calculated during the last get_forces() call.

        Yields:
            Atoms: Image with attached SinglePointCalculator.
        """
        for i, atoms in enumerate(self.images):
            if i == 0 or i == self.nimages - 1:
                yield atoms
            else:
                atoms = atoms.copy()
                # Inject stress info into the single point calculator
                self.freeze_results_on_image(
                    atoms, energy=self.energies[i],
                    forces=self.real_forces[i-1] if self.real_forces is not None else None,
                    stress=self.stresses[i-1] if self.stresses is not None else None
                )
                yield atoms
