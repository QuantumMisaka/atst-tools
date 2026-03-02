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
        
        # NOTE: Abacus() constructor does not accept 'command' directly if it's using the old ASE-Abacus style
        # where command is part of profile.
        # But looking at abacuslite code (core.py), Abacus.__init__ takes (profile, directory, **kwargs).
        # And it creates a default profile if none is provided: profile = AbacusProfile('abacus').
        # However, we want to pass our custom command.
        
        # So we should create the profile explicitly here.
        from atst_tools.external.abacuslite import AbacusProfile
        
        # Extract profile-related args from mapped_params to avoid passing them twice or to wrong place
        profile_kwargs = {}
        if 'pseudo_dir' in mapped_params:
             # AbacusProfile expects pseudo_dir (optional)
             # But Abacus() also can take pseudo_dir (via kwargs -> inp or direct?)
             # Actually AbacusProfile takes pseudo_dir and orbital_dir.
             pass
        
        # Let's check AbacusProfile.__init__: command, pseudo_dir, orbital_dir, omp_num_threads
        pseudo_dir = mapped_params.get('pseudo_dir')
        orbital_dir = mapped_params.get('orbital_dir')
        
        # NOTE: mapped_params is from config['calculator']['abacus']
        # If config['calculator']['abacus'] has pseudo_dir, it should be here.
        
        # Wait, the config file has:
        # parameters:
        #    pseudo_dir: ...
        #    orbital_dir: ...
        
        # The factory logic:
        # calc_params = config.get('calculator', {}).get('abacus', {})
        # mapped_params = calc_params.copy()
        
        # But 'parameters' is INSIDE 'abacus' dict in config?
        # Let's check config.yaml structure again.
        # calculator:
        #   abacus:
        #     parameters:
        #       pseudo_dir: ...
        
        # So pseudo_dir is inside 'parameters' sub-dict, NOT directly under 'abacus'!
        
        # The code above does:
        # calc_params = config.get('calculator', {}).get('abacus', {})
        # mapped_params = calc_params.copy()
        
        # This copies 'command', 'mpi', 'directory', 'kpts', AND 'parameters' (which is a dict).
        # It does NOT flatten 'parameters' into mapped_params!
        
        # So mapped_params['parameters'] is the dict containing pseudo_dir.
        # mapped_params itself does NOT contain pseudo_dir directly!
        
        # We need to extract pseudo_dir/orbital_dir from mapped_params['parameters'] if they exist there!
        
        abacus_params = mapped_params.get('parameters', {})
        pseudo_dir = mapped_params.get('pseudo_dir', abacus_params.get('pseudo_dir'))
        orbital_dir = mapped_params.get('orbital_dir', abacus_params.get('orbital_dir'))
        
        # Create profile
        # NOTE: If the user provides a 'command' (e.g. 'mpirun -np 4 abacus'), we must ensure
        # that it is passed correctly to the AbacusProfile.
        # The AbacusProfile constructor takes 'command' as the first argument.
        # The Abacus calculator constructor takes 'profile' and **kwargs.
        
        # If 'command' is not provided in mapped_params, we might need a default or raise an error.
        # For now, let's assume it's provided or handled by defaults.
        
        # However, there is a catch: if the user specifies 'command' in the config, 
        # it might contain MPI instructions.
        # AbacusProfile expects the full command string.
        
        profile_command = command if command else 'abacus'
        
        profile = AbacusProfile(
            command=profile_command,
            pseudo_dir=pseudo_dir,
            orbital_dir=orbital_dir,
            omp_num_threads=omp
        )
        
        # Remove profile args from mapped_params if they are meant for profile only?
        # Abacus() takes directory, profile, and **kwargs.
        # kwargs can contain pseudopotentials, basissets, kpts, inp.
        # It seems Abacus() constructor does NOT take 'command'.
        
        # Clean mapped_params to avoid passing 'directory', 'command' etc again if they are in there
        if 'directory' in mapped_params:
            del mapped_params['directory']
        if 'command' in mapped_params:
            del mapped_params['command']
        if 'mpi' in mapped_params:
            del mapped_params['mpi']
        if 'omp' in mapped_params:
            del mapped_params['omp']
        if 'parameters' in mapped_params:
            del mapped_params['parameters']
            
        # Prepare kpts if it is a list
        if 'kpts' in mapped_params and isinstance(mapped_params['kpts'], list):
             # assume it is a MP sampling
             kpts_list = mapped_params['kpts']
             if len(kpts_list) == 3:
                 mapped_params['kpts'] = {
                     'mode': 'mp-sampling',
                     'nk': kpts_list,
                     'gamma-centered': True,
                     'kshift': [0, 0, 0]
                 }
                 
        # IMPORTANT: 'parameters' from config should be merged into mapped_params
        # because Abacus() expects them as kwargs.
        # But we already extracted pseudo_dir/orbital_dir from it.
        # Now we need to pass the REST of parameters to Abacus()!
        
        if abacus_params:
             # Merge abacus_params into mapped_params, but do NOT overwrite existing keys
             # (though mapped_params was a copy of config['calculator']['abacus'], which contains 'parameters' as a dict)
             # Wait, mapped_params HAS 'parameters' key which is a dict.
             # And we DELETED it above: if 'parameters' in mapped_params: del ...
             
             # So we lost all parameters like ecutwfc, etc. !!!
             # This is why the INPUT file is empty/missing parameters!
             
             # We must flatten abacus_params into mapped_params BEFORE deleting 'parameters' key!
             # Or just pass them as kwargs.
             
             for k, v in abacus_params.items():
                 if k not in ['pseudo_dir', 'orbital_dir']: # We handled these via profile
                     mapped_params[k] = v
        
        # NOTE: At this point, mapped_params contains flattened parameters from 'parameters' dict.
        # But wait, did we handle top-level keys like 'ecutwfc' if they were outside 'parameters'?
        # In the config structure:
        # calculator:
        #   abacus:
        #     command: ...
        #     mpi: ...
        #     parameters:
        #        ecutwfc: 100
        #        ...
        
        # So 'ecutwfc' is indeed inside 'parameters'.
        # Our loop above correctly extracts them.
        
        # What about keys that are NOT in parameters?
        # mapped_params initially contained everything in config['calculator']['abacus'].
        # We deleted 'directory', 'command', 'mpi', 'omp', 'parameters'.
        # So mapped_params is now empty (or contains other unknown keys).
        # Then we fill it with items from abacus_params.
        # This seems correct!
        
        return Abacus(
            directory=directory,
            profile=profile,
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
