# AbacusSella implementation
# part of ATST-Tools
#
# References:
#     Sella transition-state search algorithm:
#     Ásgeirsson, V.; Birgisson, B. O.; Bjornsson, R.; Becker, U.; Neese, F.;
#     Jónsson, H. Sella, an Open-Source Chemical Kinetics Environment.
#     J. Chem. Theory Comput. 18 (8), 4914-4930 (2022).
#     https://doi.org/10.1021/acs.jctc.2c00395

import numpy as np
from ase.io import Trajectory
from sella import Sella

from atst_tools.calculators.factory import CalculatorFactory

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
        """
        Run Sella calculation workflow.

        Args:
            fmax (float, optional): Force convergence criterion.
            
        Returns:
            Atoms: The optimized transition state structure.
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
            dyn.run(fmax=fmax)
        else:
            dyn.run(fmax=fmax, steps=self.max_steps)
        self._warn_if_premature_return(dyn, fmax)
        return ts_atoms

    @staticmethod
    def _warn_if_premature_return(dyn, fmax: float) -> None:
        """Sella 结束但未达到配置收敛阈值时输出中性 advisory warning（不改变返回语义）。

        覆盖优化器提前返回与步数用尽两种客观情形：dyn.converged() 为 False 时只陈述
        客观事实（配置阈值、实际步数），不预判科学原因。是否可接受由前台 AI 与用户
        结合轨迹、原子约束、restart/input 选择与计算成本复核。返回码、workflow 状态
        与 artifact manifest 不受影响。
        """
        try:
            converged = dyn.converged()
        except Exception:
            return
        if not isinstance(converged, (bool, np.bool_)) or bool(converged):
            return
        if not converged:
            nsteps = getattr(dyn, "nsteps", None)
            print(
                "Warning: Sella 结束时未达到配置的收敛阈值"
                f"（workflow=sella, threshold_fmax={fmax}, nsteps={nsteps}）；"
                "最终 fmax 未满足该阈值或鞍点判据未满足。完成只代表计算任务正常结束，"
                "不代表科学收敛；请结合轨迹、原子约束、restart/input 选择与计算成本复核。"
            )
