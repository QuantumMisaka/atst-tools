from typing import Dict, Any
import os
from ase.calculators.calculator import Calculator
from atst_tools.external.abacuslite.core import Abacus

class AbacusFactory:
    """Factory for creating ABACUS calculators using abacuslite."""
    
    @staticmethod
    def get_calculator(config: Dict[str, Any], 
                      directory: str = '.', 
                      mpi: int = 1, 
                      omp: int = 1,
                      **kwargs) -> Calculator:
        """
        Create an ABACUS calculator instance.
        
        Args:
            config (dict): Configuration dictionary containing calculator settings.
            directory (str): Working directory for calculation.
            mpi (int): Number of MPI processes.
            omp (int): Number of OpenMP threads.
            **kwargs: Additional arguments passed to Abacus calculator.
            
        Returns:
            Calculator: Configured ASE Calculator.
        """
        # Extract ABACUS specific parameters
        calc_params = config.get('calculator', {}).get('abacus', {})
        if not calc_params and 'parameters' in config:
            # Fallback for old config structure
            calc_params = config['parameters']
            
        # Set environment variables
        os.environ['OMP_NUM_THREADS'] = str(omp)
        
        # Prepare command
        abacus_cmd = config.get('command', 'abacus')
        if "{mpi}" in abacus_cmd:
            command = abacus_cmd.format(mpi=mpi)
        elif mpi > 1:
            command = f"mpirun -np {mpi} {abacus_cmd}"
        else:
            command = abacus_cmd
            
        # Map parameters from old ASE-Abacus style to AbacusLite style if needed
        # AbacusLite uses: pseudopotentials, basissets, orbital_dir
        # Old config might use: pp, basis, basis_dir
        mapped_params = calc_params.copy()
        
        if 'pp' in mapped_params:
            mapped_params['pseudopotentials'] = mapped_params.pop('pp')
        if 'basis' in mapped_params:
            mapped_params['basissets'] = mapped_params.pop('basis')
        if 'basis_dir' in mapped_params:
            mapped_params['orbital_dir'] = mapped_params.pop('basis_dir')
            
        # Create calculator
        # Note: abacuslite uses 'profile' dict or command string
        # Here we pass command directly if supported, or via profile
        return Abacus(
            directory=directory,
            command=command,
            **mapped_params
        )

class DeepPotentialFactory:
    """Factory for creating DeepMD calculators with instance sharing."""
    
    _instances: Dict[str, Calculator] = {}
    
    @staticmethod
    def get_calculator(config: Dict[str, Any], 
                      shared: bool = True,
                      **kwargs) -> Calculator:
        """
        Create a DeepMD calculator instance.
        
        Args:
            config (dict): Configuration dictionary.
            shared (bool): Whether to share calculator instance (for serial execution).
            **kwargs: Additional arguments.
            
        Returns:
            Calculator: Configured ASE Calculator.
            
        Raises:
            ImportError: If deepmd-kit is not installed.
        """
        try:
            from deepmd.calculator import DP
        except ImportError:
            raise ImportError("deepmd-kit is not installed. Please install it to use DP calculator.")
            
        dp_params = config.get('calculator', {}).get('dp', {})
        if not dp_params and 'parameters' in config:
             dp_params = config['parameters']
             
        model_file = dp_params.get('model', 'frozen_model.pb')
        type_map = dp_params.get('type_map', None) # Optional, DP can infer
        
        # Unique key for caching based on model path
        model_key = os.path.abspath(model_file)
        
        if shared and model_key in DeepPotentialFactory._instances:
            return DeepPotentialFactory._instances[model_key]
            
        calc = DP(model=model_file, type_map=type_map)
        
        if shared:
            DeepPotentialFactory._instances[model_key] = calc
        
        return calc

class CalculatorFactory:
    """Unified factory for creating calculators."""
    
    @staticmethod
    def get_calculator(name: str, config: Dict[str, Any], **kwargs) -> Calculator:
        """
        Get a calculator instance by name.
        
        Args:
            name (str): Calculator name ('abacus' or 'dp').
            config (dict): Full configuration dictionary.
            **kwargs: Additional arguments passed to specific factory.
            
        Returns:
            Calculator: Configured ASE Calculator instance.
            
        Raises:
            ValueError: If calculator name is not supported.
        """
        name = name.lower()
        
        if name == 'abacus':
            return AbacusFactory.get_calculator(config, **kwargs)
        elif name == 'dp' or name == 'deepmd':
            return DeepPotentialFactory.get_calculator(config, **kwargs)
        else:
            raise ValueError(f"Unsupported calculator: {name}. Supported: 'abacus', 'dp'")
