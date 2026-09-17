# AbacusSella implementation
# part of ATST-Tools
#
# References:
#     Sella transition-state search algorithm:
#     Ásgeirsson, V.; Birgisson, B. O.; Bjornsson, R.; Becker, U.; Neese, F.;
#     Jónsson, H. Sella, an Open-Source Chemical Kinetics Environment.
#     J. Chem. Theory Comput. 18 (8), 4914-4930 (2022).
#     https://doi.org/10.1021/acs.jctc.2c00395

from ase.io import Trajectory
from sella import Sella

from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.convergence import (
    StageRecord,
    as_finite_float,
    as_step_count,
    emit_unconverged_advisory,
)

class AbacusSella:
    """
    Customize Sella calculation workflow by using ABACUS.

    This class manages the setup and execution of the Sella method for finding
    saddle points (Transition States) using ABACUS as the force calculator.

    Attributes:
        init_Atoms (Atoms): Initial structure (guess for TS).
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
        traj_file (str): Output trajectory file.
        sella_eta (float): Sella eta parameter.
        fmax (float): Force convergence criterion.

    References:
        Ásgeirsson, V.; Birgisson, B. O.; Bjornsson, R.; Becker, U.; Neese, F.;
        Jónsson, H. Sella, an Open-Source Chemical Kinetics Environment.
        J. Chem. Theory Comput. 18 (8), 4914-4930 (2022).
        https://doi.org/10.1021/acs.jctc.2c00395
    """
    
    def __init__(self, init_Atoms, config, calc_name, calc_config,
                 traj_file='run_sella.traj',
                 sella_eta=0.005,
                 fmax=0.05,
                 order=1):
        """
        Initialize Sella method by using ASE-ABACUS.

        Args:
            init_Atoms (Atoms): Initial Atoms object.
            config (dict): Global configuration dictionary.
            calc_name (str): Name of the calculator.
            calc_config (dict): Calculation configuration dictionary.
            traj_file (str): Path to output trajectory file.
            sella_eta (float): Sella eta parameter.
            fmax (float): Force convergence criterion.
            order (int): Saddle-point order.
        """
        self.init_Atoms = init_Atoms
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.traj_file = traj_file
        self.sella_eta = sella_eta
        self.fmax = fmax
        self.order = order
        self.max_steps = calc_config.get('max_steps')
        
    def set_calculator(self):
        """
        Set calculators using Factory.

        Returns:
            Calculator: Configured calculator instance.
        """
        directory = self.calc_config.get('directory', 'sella_run')
        if 'abacus' in self.config:
             directory = self.config['abacus'].get('directory', directory)
        
        return CalculatorFactory.get_calculator(
            self.calc_name, 
            self.config, 
            directory=directory
        )
    
    def run(self, fmax=None):
        """Run Sella and persist its durable convergence record.

        Args:
            fmax (float, optional): Force convergence criterion.

        Returns:
            Atoms: The optimized transition state structure.  The optimizer's
            ``run()`` return value is the authoritative convergence signal: a
            known ``False`` prints one shared English advisory and is recorded
            in the manifest without changing the returned structure.  The
            record is also exposed as ``last_stage_record`` for nesting
            workflows, and an explicit ``artifact_manifest: None`` disables the
            manifest write so only the owning workflow (D2S) writes one.
        """
        if fmax is None:
            fmax = self.fmax

        ts_atoms = self.init_Atoms
        ts_atoms.calc = self.set_calculator()
        
        # Setup Sella constraints if any
        # Sella handles constraints internally but we can also use ase constraints
        # cons = Constraints(ts_atoms) 
        # For now, we rely on Sella's default handling of ASE constraints
        
        traj = Trajectory(self.traj_file, 'w', ts_atoms)
        
        dyn = Sella(
            ts_atoms,
            trajectory=traj,
            eta = self.sella_eta,
            order=self.order,
        )
        
        if self.max_steps is None:
            converged_signal = dyn.run(fmax=fmax)
        else:
            converged_signal = dyn.run(fmax=fmax, steps=self.max_steps)
        record = StageRecord(
            name="sella",
            role="final",
            criterion="sella_projected_force+constraint",
            converged=converged_signal,
            fmax=as_finite_float(fmax),
            steps=as_step_count(self.max_steps),
            actual_steps=as_step_count(getattr(dyn, "nsteps", None)),
        )
        emit_unconverged_advisory(record, workflow="sella")
        # Expose the same record to callers (e.g. nested D2S refinement) so the
        # owning workflow can persist the facts without re-deriving them.
        self.last_stage_record = record
        # An explicit ``None`` disables the manifest, which lets a nesting
        # workflow (D2S) stay the only writer of the top-level manifest.
        manifest_path = self.calc_config.get("artifact_manifest", "atst_artifacts.json")
        if manifest_path is not None:
            write_artifact_manifest(
                manifest_path,
                workflow="sella",
                artifacts=[{"role": "trajectory", "path": self.traj_file}],
                stages=[record.to_manifest()],
            )
        return ts_atoms
