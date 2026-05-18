# AbacusAutoNEB implementation
# part of ATST-Tools

import os
import shutil
import types
from pathlib import Path
from ase.mep.autoneb import AutoNEB, seriel_writer, store_E_and_F_in_spc
from ase.io import read, write, Trajectory
from ase.parallel import world
from ase.optimize import FIRE, BFGS

from atst_tools.mep.neb import AbacusNEB
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.calculators.dp import is_dp_calculator, should_share_calculator
from atst_tools.utils.config_schema import apply_calculation_defaults
from atst_tools.utils.neb_endpoints import endpoint_policy, ensure_neb_endpoint_results

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
        if self.world.rank == 0:
            self.iter_folder.mkdir(parents=True, exist_ok=True)

        # 1. Backup unused images
        if self.world.rank == 0:
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

        neb.distribute = types.MethodType(store_E_and_F_in_spc, neb)
        neb.distribute()

class AutoNEBRunner:
    """
    Helper class to configure and run AutoNEB workflows from a dictionary configuration.
    
    Attributes:
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
    """
    def __init__(self, config, calc_name, calc_config):
        """
        Initialize AutoNEBRunner.

        Args:
            config (dict): Global configuration.
            calc_name (str): Calculator name.
            calc_config (dict): Calculation config section.
        """
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config if "config_version" in config else apply_calculation_defaults(calc_config)
        calc_config = self.calc_config
        self.prefix = calc_config['prefix']
        self.n_simul = calc_config.get('n_simul') or world.size
        self.n_max = calc_config['n_max']
        self.algorism = calc_config['algorism']
        requested_parallel = calc_config['parallel']
        self.parallel = requested_parallel and world.size > 1
        if requested_parallel and not self.parallel:
            print("Notice: image-level AutoNEB parallelism requires MPI-launched atst run; running images serially.")
        self.fmax = calc_config['fmax']
        self.maxsteps = calc_config['maxsteps']
        self.optimizer_name = calc_config['optimizer']
        self.climb = calc_config['climb']
        self.iter_folder = calc_config['iter_folder']
        self.restart = calc_config['restart']
        self.allow_shared_calculator = should_share_calculator(
            self.calc_name,
            self.config,
            parallel=self.parallel,
        )
        self._shared_calc = None
        
        # Initial chain
        init_chain_file = calc_config['init_chain']
        self.init_chain = read(init_chain_file, index=':')

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
             if self.parallel:
                 base_dir = self._base_directory()
                 image_dir = f"{base_dir}-rank{world.rank}"
                 
                 image.calc = self._get_calculator(image_dir, shared=False)
             else:
                 base_dir = self._base_directory()
                 image_index = image.info.get("_atst_autoneb_index", i)
                 image_dir = f"{base_dir}/image_{int(image_index):03d}"
                 image.calc = self._get_calculator(image_dir, shared=False)

    def _get_optimizer(self):
        """
        Get the optimizer class based on configuration.

        Returns:
            class: ASE optimizer class.
        """
        if self.optimizer_name.upper() == 'FIRE':
            return FIRE
        elif self.optimizer_name.upper() == 'BFGS':
            return BFGS
        else:
            return FIRE

    def run(self):
        """
        Run the AutoNEB workflow.
        """
        print("=== Starting AutoNEB Calculation ===")

        if not self.restart:
            for path in Path(".").glob(f"{self.prefix}[0-9][0-9][0-9].traj"):
                path.unlink()
            iter_path = Path(self.iter_folder)
            if iter_path.exists():
                shutil.rmtree(iter_path)

        base_dir = self._base_directory()
        ensure_neb_endpoint_results(
            self.init_chain,
            lambda directory: self._get_calculator(f"{base_dir}/{directory}"),
            policy=endpoint_policy(self.calc_config, default="auto"),
            directories=("endpoint_initial", "endpoint_final"),
            context="AutoNEB",
        )
        
        autoneb = AbacusAutoNEB(
            attach_calculators=self.attach_calculators,
            prefix=self.prefix,
            n_simul=self.n_simul,
            n_max=self.n_max,
            iter_folder=self.iter_folder,
            world=world,
            method=self.algorism,
            parallel=self.parallel,
            optimizer=self._get_optimizer(),
            fmax=self.fmax,
            maxsteps=self.maxsteps,
            climb=self.climb,
            allow_shared_calculator=self.allow_shared_calculator,
        )
        
        # Write initial files if they don't exist
        for i, atoms in enumerate(self.init_chain):
             filename = f'{self.prefix}{i:03d}.traj'
             write(filename, atoms)
                 
        autoneb.run()
        print("=== AutoNEB Calculation Finished ===")
