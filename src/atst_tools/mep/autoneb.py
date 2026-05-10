# AbacusAutoNEB implementation
# part of ATST-Tools

import os
import shutil
from pathlib import Path
from ase.mep.autoneb import AutoNEB
from ase.io import read, write, Trajectory
from ase.parallel import world
from ase.optimize import FIRE, BFGS

from atst_tools.mep.neb import AbacusNEB
from atst_tools.calculators.factory import CalculatorFactory

class AbacusAutoNEB(AutoNEB):
    """
    Customized AutoNEB for ABACUS/ATST-Tools.
    
    This class overrides the standard AutoNEB execution to:
    1.  Use `AbacusNEB` instead of standard `NEB` for improved force/stress handling.
    2.  Implement aggressive file cleanup to manage disk usage during long runs.
    3.  Support parallel execution with correct directory management.

    Attributes:
        attach_calculators (callable): Function to attach calculators to images.
        prefix (str): Prefix for trajectory files.
        n_simul (int): Number of simultaneous images to optimize.
        n_max (int): Maximum number of images.
        iter_folder (str): Folder for iteration logs and trajectories.
    """
    
    def __init__(self, attach_calculators, prefix, n_simul, n_max,
                 iter_folder='AutoNEB_iter', **kwargs):
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
        super().__init__(attach_calculators, prefix, n_simul, n_max, 
                         iter_folder=iter_folder, **kwargs)

    def _execute_one_neb(self, exitstack, n_cur, to_run,
                         climb=False, many_steps=False):
        """
        Internal method which executes one NEB optimization.
        
        Overrides ASE AutoNEB._execute_one_neb to use AbacusNEB and handle cleanup.

        Args:
            exitstack: Context manager stack.
            n_cur (int): Current number of images.
            to_run (list): Indices of images to run.
            climb (bool): Whether to use climbing image NEB.
            many_steps (bool): Whether to run many steps (not typically used here).
        """
        closelater = exitstack.enter_context
        self.iteration += 1

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
        self.attach_calculators([self.all_images[i] for i in to_run[1: -1]])

        # 3. Instantiate NEB (Using AbacusNEB instead of standard NEB)
        neb = AbacusNEB([self.all_images[i] for i in to_run],
                        k=[self.k[i] for i in to_run[0:-1]],
                        method=self.method,
                        parallel=self.parallel,
                        remove_rotation_and_translation=self.remove_rotation_and_translation,
                        climb=climb)

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
            
            traj = closelater(Trajectory(
                '%s%03d.traj' % (self.prefix, j + nneb), 'w',
                self.all_images[j + nneb],
                master=(self.world.rank % n == 0),
                properties=["energy", "forces", "stress"] # Added stress
            ))
            filename_ref = self.iter_trajpath(j + nneb, self.iteration)
            trajhist = closelater(Trajectory(
                filename_ref, 'w',
                self.all_images[j + nneb],
                master=(self.world.rank % n == 0),
                properties=["energy", "forces", "stress"] # Added stress
            ))
            qn.attach(traj)
            qn.attach(trajhist)
        else:
            # Serial logic
            for i in to_run[1: -1]:
                traj = closelater(Trajectory(
                    '%s%03d.traj' % (self.prefix, i), 'w',
                    self.all_images[i],
                    properties=["energy", "forces", "stress"]
                ))
                filename_ref = self.iter_trajpath(i, self.iteration)
                trajhist = closelater(Trajectory(
                    filename_ref, 'w',
                    self.all_images[i],
                    properties=["energy", "forces", "stress"]
                ))
                qn.attach(traj)
                qn.attach(trajhist)

        # 6. Run Optimizer
        steps = self.maxsteps
        qn.run(fmax=self.fmax, steps=steps)

        # 7. CLEANUP
        # Remove calculation directories to save space
        for ind in to_run[1: -1]:
            calc = self.all_images[ind].calc
            if calc and hasattr(calc, 'directory'):
                calc_dir = calc.directory
                if os.path.isdir(calc_dir):
                    try:
                        shutil.rmtree(calc_dir)
                    except OSError:
                        pass # Ignore errors

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
        self.calc_config = calc_config
        self.prefix = calc_config.get('prefix', 'run_autoneb')
        self.n_simul = calc_config.get('n_simul', world.size)
        self.n_max = calc_config.get('n_max', 10)
        self.algorism = calc_config.get('algorism', 'improvedtangent')
        requested_parallel = calc_config.get('parallel', True)
        self.parallel = requested_parallel and world.size > 1
        if requested_parallel and not self.parallel:
            print("Notice: image-level AutoNEB parallelism requires MPI-launched atst-run; running images serially.")
        self.fmax = calc_config.get('fmax', 0.05)
        if isinstance(self.fmax, (list, tuple)):
            self.fmax = self.fmax[-1]
        self.maxsteps = calc_config.get('maxsteps', 100)
        self.optimizer_name = calc_config.get('optimizer', 'FIRE')
        self.climb = calc_config.get('climb', True)
        self.iter_folder = calc_config.get('iter_folder', 'AutoNEB_iter')
        self.restart = calc_config.get('restart', False)
        
        # Initial chain
        init_chain_file = calc_config.get('init_chain', 'init_neb_chain.traj')
        self.init_chain = read(init_chain_file, index=':')

    def attach_calculators(self, images):
        """
        Callback to attach calculators to a list of images.

        Args:
            images (list): List of Atoms objects to attach calculators to.
        """
        for i, image in enumerate(images):
             if self.parallel:
                 base_dir = self.calc_config.get('directory', 'autoneb_run')
                 if 'abacus' in self.config:
                      base_dir = self.config['abacus'].get('directory', base_dir)
                      
                 image_dir = f"{base_dir}-rank{world.rank}"
                 
                 image.calc = CalculatorFactory.get_calculator(
                    self.calc_name, 
                    self.config, 
                    directory=image_dir
                 )
             else:
                 base_dir = self.calc_config.get('directory', 'autoneb_run')
                 if 'abacus' in self.config:
                      base_dir = self.config['abacus'].get('directory', base_dir)
                 
                 image.calc = CalculatorFactory.get_calculator(
                    self.calc_name, 
                    self.config, 
                    directory=base_dir
                 )

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
        )
        
        # Write initial files if they don't exist
        for i, atoms in enumerate(self.init_chain):
             filename = f'{self.prefix}{i:03d}.traj'
             write(filename, atoms)
                 
        autoneb.run()
        print("=== AutoNEB Calculation Finished ===")
