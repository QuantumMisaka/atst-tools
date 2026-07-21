# AbacusAutoNEB implementation
# part of ATST-Tools

from atst_tools.utils.mpi import bootstrap_mpi_for_ase

bootstrap_mpi_for_ase()

import os
import shutil
import types
from functools import partial
from copy import deepcopy
from math import exp, log
from pathlib import Path
import numpy as np
from ase.calculators.singlepoint import SinglePointCalculator
from ase.mep.autoneb import AutoNEB, seriel_writer, store_E_and_F_in_spc
from ase.io import read, write, Trajectory
from ase.parallel import world
from ase.optimize import FIRE, BFGS

from atst_tools.mep.neb import AbacusNEB
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.calculators.dp import is_dp_calculator, should_share_calculator
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.neb_endpoints import endpoint_policy, ensure_neb_endpoint_results
from atst_tools.utils.neb_endpoints import freeze_current_results, freeze_results, get_endpoint_results
from atst_tools.utils.mpi import (
    get_ase_world,
    rank_owns_local_image,
    run_rank_zero_section,
    validate_image_parallel_world,
)


def _store_E_and_F_in_spc_reduced(neb):
    """Freeze parallel NEB image results using reductions instead of broadcasts."""
    neb.get_forces()
    images = neb.images
    if not neb.parallel:
        return store_E_and_F_in_spc(neb)

    energies = np.zeros(neb.nimages)
    forces = np.zeros((neb.nimages, neb.natoms, 3))
    image_index = neb.world.rank * (neb.nimages - 2) // neb.world.size + 1
    forces[image_index] = images[image_index].get_forces()
    energies[image_index] = images[image_index].get_potential_energy()

    neb.world.sum(energies)
    neb.world.sum(forces)

    for i in range(1, neb.nimages - 1):
        images[i].calc = SinglePointCalculator(
            images[i],
            energy=energies[i],
            forces=forces[i],
        )


class AbacusAutoNEB(AutoNEB):
    """
    ASE-native AutoNEB variant that uses ATST's NEB compatibility class.
    
    This class keeps ASE 3.28.0 AutoNEB scheduling and result-freezing
    semantics, while constructing `AbacusNEB` so ATST can carry the local NEB
    real-force backport until it is available in a production ASE release.

    Attributes:
        attach_calculators (callable): Function to attach calculators to images.
        prefix (str): Prefix for trajectory files.
        n_simul (int): Number of simultaneous images to optimize.
        n_max (int): Maximum number of images.
        iter_folder (str): Folder for iteration logs and trajectories.
    """
    
    def __init__(self, attach_calculators, prefix, n_simul, n_max,
                 iter_folder='AutoNEB_iter', allow_shared_calculator=False, **kwargs):
        """
        Initialize AbacusAutoNEB.

        Args:
            attach_calculators (callable): Function that accepts a list of Atoms and attaches calculators.
            prefix (str): File prefix for trajectories.
            n_simul (int): Number of simultaneous images.
            n_max (int): Maximum number of images.
            iter_folder (str): Directory to store iteration history.
            **kwargs: Additional arguments for AutoNEB.
        """
        self.allow_shared_calculator = allow_shared_calculator
        super().__init__(attach_calculators, prefix, n_simul, n_max, 
                         iter_folder=iter_folder, **kwargs)

    def __initialize__(self):
        """Load AutoNEB image files with explicit non-parallel ASE reads."""
        if not os.path.isfile(f"{self.prefix}000.traj"):
            raise OSError(
                f"No file with name {self.prefix}000.traj",
                "was found. Should contain initial image",
            )

        index_exists = [
            i for i in range(self.n_max)
            if os.path.isfile("%s%03d.traj" % (self.prefix, i))
        ]
        n_cur = index_exists[-1] + 1

        if self.world.rank == 0:
            print(
                "The NEB initially has %d images " % len(index_exists),
                "(including the end-points)",
            )
        if len(index_exists) == 1:
            raise Exception("Only a start point exists")

        for i in range(len(index_exists)):
            if i != index_exists[i]:
                raise Exception(
                    "Files must be ordered sequentially",
                    "without gaps.",
                )
        def copy_initial_images():
            for i in index_exists:
                filename_ref = self.iter_trajpath(i, 0)
                if os.path.isfile(filename_ref):
                    try:
                        os.rename(filename_ref, str(filename_ref) + ".bak")
                    except OSError:
                        pass
                filename = "%s%03d.traj" % (self.prefix, i)
                try:
                    shutil.copy2(filename, filename_ref)
                except OSError:
                    pass
        if self.parallel:
            run_rank_zero_section(
                self.world,
                copy_initial_images,
                context="AutoNEB initial image backup",
            )
        elif self.world.rank == 0:
            copy_initial_images()
        self.world.barrier()

        for i in range(n_cur):
            if i in index_exists:
                filename = "%s%03d.traj" % (self.prefix, i)
                newim = read(filename, parallel=False)
                self.all_images.append(newim)
            else:
                self.all_images.append(self.all_images[0].copy())

        self.iteration = 0
        return n_cur

    def _execute_one_neb(self, exitstack, n_cur, to_run,
                         climb=False, many_steps=False):
        """
        Internal method which executes one NEB optimization.

        The control flow mirrors ASE 3.28.0, with `AbacusNEB` substituted for
        ASE `NEB` and image indices annotated before calculators are attached.

        Args:
            exitstack: Context manager stack.
            n_cur (int): Current number of images.
            to_run (list): Indices of images to run.
            climb (bool): Whether to use climbing image NEB.
            many_steps (bool): Whether to run many steps (not typically used here).
        """
        closelater = exitstack.enter_context
        self.iteration += 1
        if self.parallel:
            validate_image_parallel_world(
                self.world,
                len(to_run) - 2,
                "active AutoNEB images",
            )
        def prepare_iteration_files():
            self.iter_folder.mkdir(parents=True, exist_ok=True)
            for i in range(n_cur):
                if i not in to_run[1: -1]:
                    filename = '%s%03d.traj' % (self.prefix, i)
                    with Trajectory(filename, mode='w',
                                    atoms=self.all_images[i]) as traj:
                        traj.write()
                    
                    # ATST-Tools: Backup to iter folder
                    filename_ref = self.iter_trajpath(i, self.iteration)
                    if os.path.isfile(filename):
                        shutil.copy2(filename, filename_ref)

        if self.parallel:
            run_rank_zero_section(
                self.world,
                prepare_iteration_files,
                context="AutoNEB iteration file preparation",
            )
        elif self.world.rank == 0:
            prepare_iteration_files()

        if self.world.rank == 0:
            print('Now starting iteration %d on ' % self.iteration, to_run)

        # 2. Attach Calculators
        for image_index in to_run[1:-1]:
            self.all_images[image_index].info["_atst_autoneb_index"] = image_index
        self.attach_calculators([self.all_images[i] for i in to_run[1: -1]])

        # 3. Instantiate NEB (Using AbacusNEB instead of standard NEB)
        neb = AbacusNEB([self.all_images[i] for i in to_run],
                        k=[self.k[i] for i in to_run[0:-1]],
                        method=self.method,
                        parallel=self.parallel,
                        remove_rotation_and_translation=self.remove_rotation_and_translation,
                        climb=climb,
                        world=self.world,
                        allow_shared_calculator=self.allow_shared_calculator)

        # 4. Run Optimization
        logpath = (self.iter_folder
                   / f'{self.prefix.name}_log_iter{self.iteration:03d}.log')
        qn = closelater(self.optimizer(neb, logfile=logpath))
        
        # 5. Setup Trajectories
        if self.parallel:
            nneb = to_run[0]
            nim = len(to_run) - 2
            n = self.world.size // nim      
            j = 1 + self.world.rank // n    
            assert nim * n == self.world.size
            
            traj = closelater(Trajectory(
                '%s%03d.traj' % (self.prefix, j + nneb), 'w',
                self.all_images[j + nneb],
                master=(self.world.rank % n == 0),
            ))
            filename_ref = self.iter_trajpath(j + nneb, self.iteration)
            trajhist = closelater(Trajectory(
                filename_ref, 'w',
                self.all_images[j + nneb],
                master=(self.world.rank % n == 0),
            ))
            qn.attach(traj)
            qn.attach(trajhist)
        else:
            num = 1
            for i, j in enumerate(to_run[1: -1]):
                filename_ref = self.iter_trajpath(j, self.iteration)
                trajhist = closelater(Trajectory(
                    filename_ref, 'w', self.all_images[j]
                ))
                qn.attach(seriel_writer(trajhist, i, num).write)

                traj = closelater(Trajectory(
                    '%s%03d.traj' % (self.prefix, j), 'w',
                    self.all_images[j]
                ))
                qn.attach(seriel_writer(traj, i, num).write)
                num += 1

        # 6. Run Optimizer
        if isinstance(self.maxsteps, (list, tuple)) and many_steps:
            steps = self.maxsteps[1]
        elif isinstance(self.maxsteps, (list, tuple)) and not many_steps:
            steps = self.maxsteps[0]
        else:
            steps = self.maxsteps

        if isinstance(self.fmax, (list, tuple)) and many_steps:
            fmax = self.fmax[1]
        elif isinstance(self.fmax, (list, tuple)) and not many_steps:
            fmax = self.fmax[0]
        else:
            fmax = self.fmax
        qn.run(fmax=fmax, steps=steps)

        neb.distribute = types.MethodType(_store_E_and_F_in_spc_reduced, neb)
        neb.distribute()

    def run(self):
        """Run AutoNEB with legacy-compatible unconstrained interpolation."""
        n_cur = self.__initialize__()
        while len(self.all_images) < self.n_simul + 2:
            if isinstance(self.k, (float, int)):
                self.k = [self.k] * (len(self.all_images) - 1)
            if self.world.rank == 0:
                print("Now adding images for initial run")

            spring_lengths = []
            for j in range(n_cur - 1):
                spring_vec = self.all_images[j + 1].get_positions() - self.all_images[j].get_positions()
                spring_lengths.append(np.linalg.norm(spring_vec))
            jmax = np.argmax(spring_lengths)

            if self.world.rank == 0:
                print("Max length between images is at ", jmax)

            n_between = self.n_simul if len(self.all_images) == 2 else 1

            to_interpolate = [self.all_images[jmax]]
            for _ in range(n_between):
                to_interpolate += [to_interpolate[0].copy()]
            to_interpolate += [self.all_images[jmax + 1]]

            neb = AbacusNEB(
                to_interpolate,
                world=self.world,
                allow_shared_calculator=self.allow_shared_calculator,
            )
            neb.interpolate(method=self.interpolate_method, apply_constraint=False)

            updated = self.all_images[:jmax + 1]
            updated += to_interpolate[1:-1]
            updated.extend(self.all_images[jmax + 1:])
            self.all_images = updated

            k_tmp = self.k[:jmax]
            k_tmp += [self.k[jmax] * (n_between + 1)] * (n_between + 1)
            k_tmp.extend(self.k[jmax + 1:])
            self.k = k_tmp

            n_cur += n_between

        energies = self.get_energies()
        n_non_valid_energies = len([energy for energy in energies if energy != energy])

        if self.world.rank == 0:
            print("Start of evaluation of the initial images")

        while n_non_valid_energies != 0:
            if isinstance(self.k, (float, int)):
                self.k = [self.k] * (len(self.all_images) - 1)

            to_run, _ = self.which_images_to_run_on()
            self.execute_one_neb(n_cur, to_run, climb=False)

            energies = self.get_energies()
            n_non_valid_energies = len([energy for energy in energies if energy != energy])

        if self.world.rank == 0:
            print("Finished initialisation phase.")

        while n_cur < self.n_max:
            if isinstance(self.k, (float, int)):
                self.k = [self.k] * (len(self.all_images) - 1)
            if self.world.rank == 0:
                print("****Now adding another image until n_max is reached", f"({n_cur}/{self.n_max})****")

            spring_lengths = []
            for j in range(n_cur - 1):
                spring_vec = self.all_images[j + 1].get_positions() - self.all_images[j].get_positions()
                spring_lengths.append(np.linalg.norm(spring_vec))

            total_vec = self.all_images[0].get_positions() - self.all_images[-1].get_positions()
            total_length = np.linalg.norm(total_vec)
            fR = max(spring_lengths) / total_length

            energies = self.get_energies()
            energy_differences = []
            emin = min(energies)
            enorm = max(energies) - emin
            for j in range(n_cur - 1):
                delta_e = (energies[j + 1] - energies[j]) * (energies[j + 1] + energies[j] - 2 * emin) / 2 / enorm
                energy_differences.append(abs(delta_e))

            gR = max(energy_differences) / enorm

            if fR / gR > self.space_energy_ratio:
                jmax = np.argmax(spring_lengths)
                reason = "spring length!"
            else:
                jmax = np.argmax(energy_differences)
                reason = "energy difference between neighbours!"

            if self.world.rank == 0:
                print(f"Adding image between {jmax} and", f"{jmax + 1}. New image point is selected",
                      "on the basis of the biggest " + reason)

            to_interpolate = [self.all_images[jmax]]
            to_interpolate += [to_interpolate[0].copy()]
            to_interpolate += [self.all_images[jmax + 1]]

            neb = AbacusNEB(
                to_interpolate,
                world=self.world,
                allow_shared_calculator=self.allow_shared_calculator,
            )
            neb.interpolate(method=self.interpolate_method, apply_constraint=False)

            updated = self.all_images[:jmax + 1]
            updated += to_interpolate[1:-1]
            updated.extend(self.all_images[jmax + 1:])
            self.all_images = updated

            k_tmp = self.k[:jmax]
            k_tmp += [self.k[jmax] * 2] * 2
            k_tmp.extend(self.k[jmax + 1:])
            self.k = k_tmp

            n_cur += 1
            to_run, _ = self.which_images_to_run_on()

            self.execute_one_neb(n_cur, to_run, climb=False)

        if self.world.rank == 0:
            print("n_max images has been reached")

        if self.climb:
            if isinstance(self.k, (float, int)):
                self.k = [self.k] * (len(self.all_images) - 1)
            if self.world.rank == 0:
                print("****Now doing the CI-NEB calculation****")
            to_run, climb_safe = self.which_images_to_run_on()

            assert climb_safe, "climb_safe should be true at this point!"
            self.execute_one_neb(n_cur, to_run, climb=True, many_steps=True)

        if not self.smooth_curve:
            return self.all_images

        energies = self.get_energies()
        peak = self.get_highest_energy_index()
        k_max = 10

        d1 = np.linalg.norm(self.all_images[peak].get_positions() - self.all_images[0].get_positions())
        d2 = np.linalg.norm(self.all_images[peak].get_positions() - self.all_images[-1].get_positions())
        l1 = -d1**2 / log(0.2)
        l2 = -d2**2 / log(0.2)

        x1 = []
        x2 = []
        for i in range(peak):
            vector = (self.all_images[i].get_positions() + self.all_images[i + 1].get_positions()) / 2
            vector -= self.all_images[0].get_positions()
            x1.append(np.linalg.norm(vector))

        for i in range(peak, len(self.all_images) - 1):
            vector = (self.all_images[i].get_positions() + self.all_images[i + 1].get_positions()) / 2
            vector -= self.all_images[0].get_positions()
            x2.append(np.linalg.norm(vector))
        self.k = [k_max * exp(-((x - d1) ** 2) / l1) for x in x1]
        self.k += [k_max * exp(-((x - d1) ** 2) / l2) for x in x2]

        if self.world.rank == 0:
            print("Now moving from top to start")
        highest_energy_index = self.get_highest_energy_index()
        nneb = highest_energy_index - self.n_simul - 1
        while nneb >= 0:
            self.execute_one_neb(n_cur, range(nneb, nneb + self.n_simul + 2), climb=False)
            nneb -= 1

        nneb = self.get_highest_energy_index()

        if self.world.rank == 0:
            print("Now moving from top to end")
        while nneb <= self.n_max - self.n_simul - 2:
            self.execute_one_neb(n_cur, range(nneb, nneb + self.n_simul + 2), climb=False)
            nneb += 1
        return self.all_images

class AutoNEBRunner:
    """
    Helper class to configure and run AutoNEB workflows from a dictionary configuration.
    
    Attributes:
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
    """
    def __init__(self, config, calc_name, calc_config, *, world=None):
        """
        Initialize AutoNEBRunner.

        Args:
            config (dict): Global configuration.
            calc_name (str): Calculator name.
            calc_config (dict): Calculation config section.
        """
        self.config = config
        self.calc_name = calc_name
        self.calc_config = apply_calculation_defaults(calc_config)
        calc_config = self.calc_config
        self.prefix = calc_config['prefix']
        self.world = world if world is not None else get_ase_world()
        self.n_simul = calc_config.get('n_simul') or self.world.size
        self.n_max = calc_config['n_max']
        self.algorism = calc_config['algorism']
        requested_parallel = calc_config['parallel']
        self.parallel = requested_parallel and self.world.size > 1
        if requested_parallel and not self.parallel:
            print("Notice: image-level AutoNEB parallelism requires MPI-launched atst run; running images serially.")
        if self.parallel:
            validate_image_parallel_world(self.world, self.n_simul, "AutoNEB n_simul")
        self.fmax = calc_config['fmax']
        self.maxsteps = calc_config['maxsteps']
        self.neb_backend = calc_config.get("neb_backend", "atst")
        self.optimizer_name = calc_config['optimizer']
        self.optimizer_kwargs = dict(calc_config.get('optimizer_kwargs', {}))
        self.climb = calc_config['climb']
        self.iter_folder = calc_config['iter_folder']
        self.restart = calc_config['restart']
        self.allow_shared_calculator = (
            self.neb_backend != "ase"
            and should_share_calculator(
                self.calc_name,
                self.config,
                parallel=self.parallel,
            )
        )
        self._shared_calc = None
        
        # Initial chain
        init_chain_file = calc_config['init_chain']
        self.init_chain = read(init_chain_file, index=':')
        self._image_index_by_id = {id(image): index for index, image in enumerate(self.init_chain)}
        self._active_autoneb = None
        self._apply_legacy_endpoint_conditions()

    def _apply_legacy_endpoint_conditions(self):
        """Copy middle-image constraints and magmoms to endpoints as main did."""
        if len(self.init_chain) < 3:
            return
        endpoint_results = {}
        for index in (0, -1):
            results = get_endpoint_results(self.init_chain[index])
            if results is not None:
                endpoint_results[index] = (
                    results[0],
                    results[1],
                    self.init_chain[index].info.get("atst_endpoint_result", "provided"),
                )
        reference = self.init_chain[len(self.init_chain) // 2]
        magmoms = reference.get_initial_magnetic_moments()
        constraints = reference.constraints
        for endpoint in (self.init_chain[0], self.init_chain[-1]):
            endpoint.set_initial_magnetic_moments(magmoms)
            if constraints:
                endpoint.set_constraint(deepcopy(constraints))
        for index, (energy, forces, status) in endpoint_results.items():
            freeze_results(self.init_chain[index], energy, forces, status=status)

    def _base_directory(self):
        base_dir = self.calc_config['directory']
        if 'calculator' in self.config:
            base_dir = self.config.get('calculator', {}).get(self.calc_name, {}).get('directory', base_dir)
        if 'abacus' in self.config:
            base_dir = self.config['abacus'].get('directory', base_dir)
        return base_dir

    def _get_calculator(self, directory, shared=None):
        kwargs = {"directory": directory}
        if is_dp_calculator(self.calc_name) and shared is not None:
            kwargs["shared"] = shared
        return CalculatorFactory.get_calculator(self.calc_name, self.config, **kwargs)

    def _image_index(self, image, fallback: int) -> int:
        if "_atst_autoneb_index" in image.info:
            return int(image.info["_atst_autoneb_index"])
        if id(image) in self._image_index_by_id:
            return self._image_index_by_id[id(image)]
        active_images = getattr(self._active_autoneb, "all_images", None)
        if active_images is not None:
            for index, candidate in enumerate(active_images):
                if candidate is image:
                    self._image_index_by_id[id(image)] = index
                    return index
        return fallback

    def attach_calculators(self, images):
        """
        Callback to attach calculators to a list of images.

        Args:
            images (list): List of Atoms objects to attach calculators to.
        """
        if self.allow_shared_calculator:
            if self._shared_calc is None:
                self._shared_calc = self._get_calculator(
                    f"{self._base_directory()}/shared",
                    shared=True,
                )
            for image in images:
                image.calc = self._shared_calc
            return

        for i, image in enumerate(images):
            if self.parallel and not rank_owns_local_image(self.world, i):
                continue
            if self.parallel:
                base_dir = self._base_directory()
                image_index = self._image_index(image, i)
                image_dir = f"{base_dir}/image_{int(image_index):03d}"
                image.calc = self._get_calculator(image_dir, shared=False)
            else:
                base_dir = self._base_directory()
                image_index = self._image_index(image, i)
                image_dir = f"{base_dir}/image_{int(image_index):03d}"
                image.calc = self._get_calculator(image_dir, shared=False)

    def _prepare_endpoint_results(self):
        """Prepare endpoint single-point results once and synchronize images."""
        base_dir = self._base_directory()
        policy = endpoint_policy(self.calc_config, default="auto")

        def prepare():
            ensure_neb_endpoint_results(
                self.init_chain,
                lambda directory: self._get_calculator(f"{base_dir}/{directory}"),
                policy=policy,
                directories=("endpoint_initial", "endpoint_final"),
                context="AutoNEB",
            )

        if not self.parallel:
            prepare()
            return

        sync_file = Path(".atst_autoneb_endpoint_synced.traj")
        def prepare_and_write():
            prepare()
            write(sync_file, self.init_chain)
        run_rank_zero_section(
            self.world,
            prepare_and_write,
            context="AutoNEB endpoint preparation",
        )
        self.world.barrier()
        self.init_chain = read(sync_file, index=":", parallel=False)
        self.world.barrier()
        def remove_sync_file():
            sync_file.unlink(missing_ok=True)
        run_rank_zero_section(
            self.world,
            remove_sync_file,
            context="AutoNEB endpoint synchronization cleanup",
        )
        self.world.barrier()

    def _get_optimizer(self):
        """
        Get the optimizer class based on configuration.

        Returns:
            class: ASE optimizer class.
        """
        if self.optimizer_name.upper() == 'FIRE':
            optimizer = FIRE
        elif self.optimizer_name.upper() == 'BFGS':
            optimizer = BFGS
        else:
            optimizer = FIRE
        if self.optimizer_kwargs:
            return partial(optimizer, **self.optimizer_kwargs)
        return optimizer

    def _freeze_final_image_results(self, images):
        """Ensure final AutoNEB image files can be summarized without calculators."""
        base_dir = self._base_directory()
        shared_calc = None
        for index, image in enumerate(images):
            try:
                image.get_potential_energy()
                image.get_forces()
            except Exception:
                if is_dp_calculator(self.calc_name):
                    if shared_calc is None:
                        shared_calc = self._get_calculator(f"{base_dir}/final_shared", shared=True)
                    image.calc = shared_calc
                else:
                    image.calc = self._get_calculator(f"{base_dir}/final_image_{index:03d}")
            freeze_current_results(image)

    def run(self):
        """
        Run the AutoNEB workflow.
        """
        print("=== Starting AutoNEB Calculation ===")
        if self.parallel and self.world.rank == 0:
            print(
                "Image-level AutoNEB parallelism active: "
                f"world.size={self.world.size}, n_simul={self.n_simul}"
            )

        def cleanup_previous_run():
            for path in Path(".").glob(f"{self.prefix}[0-9][0-9][0-9].traj"):
                path.unlink()
            iter_path = Path(self.iter_folder)
            if iter_path.exists():
                shutil.rmtree(iter_path)

        if not self.restart:
            if self.parallel:
                run_rank_zero_section(
                    self.world,
                    cleanup_previous_run,
                    context="AutoNEB previous-output cleanup",
                )
            elif self.world.rank == 0:
                cleanup_previous_run()
        if self.parallel:
            self.world.barrier()

        self._prepare_endpoint_results()
        
        autoneb_kwargs = {
            "attach_calculators": self.attach_calculators,
            "prefix": self.prefix,
            "n_simul": self.n_simul,
            "n_max": self.n_max,
            "iter_folder": self.iter_folder,
            "world": self.world,
            "method": self.algorism,
            "parallel": self.parallel,
            "optimizer": self._get_optimizer(),
            "fmax": self.fmax,
            "maxsteps": self.maxsteps,
            "climb": self.climb,
        }
        if self.neb_backend == "ase":
            autoneb = AutoNEB(**autoneb_kwargs)
        else:
            autoneb = AbacusAutoNEB(
                **autoneb_kwargs,
                allow_shared_calculator=self.allow_shared_calculator,
            )
        
        # Write initial files if they don't exist
        def write_initial_files():
            for i, atoms in enumerate(self.init_chain):
                filename = f'{self.prefix}{i:03d}.traj'
                write(filename, atoms)
        if self.parallel:
            run_rank_zero_section(
                self.world,
                write_initial_files,
                context="AutoNEB initial image writing",
            )
        elif self.world.rank == 0:
            write_initial_files()
        if self.parallel:
            self.world.barrier()
                 
        self._active_autoneb = autoneb
        try:
            autoneb.run()
        finally:
            self._active_autoneb = None
        final_images = getattr(autoneb, "all_images", None)
        def freeze_and_write_final_images():
            if final_images is None:
                return
            self._freeze_final_image_results(final_images)
            for i, atoms in enumerate(final_images):
                filename = f'{self.prefix}{i:03d}.traj'
                write(filename, atoms)
        if self.parallel:
            run_rank_zero_section(
                self.world,
                freeze_and_write_final_images,
                context="AutoNEB final image writing",
            )
        elif self.world.rank == 0:
            freeze_and_write_final_images()
        print("=== AutoNEB Calculation Finished ===")
        return final_images if self.world.rank == 0 else None
