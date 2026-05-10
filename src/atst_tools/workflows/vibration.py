"""Vibration workflow."""

import os
import json
from pathlib import Path
import numpy as np
from ase.vibrations import Vibrations
from atst_tools.calculators.factory import CalculatorFactory
from atst_tools.utils.io import read_structure
from atst_tools.utils.restart_helpers import clean_cache_files
from atst_tools.utils.thermochemistry import compute_vibration_thermochemistry

class VibrationWorkflow:
    """
    Workflow for vibrational analysis and harmonic thermodynamics.

    Attributes:
        config (dict): Global configuration.
        calc_name (str): Calculator name.
        calc_config (dict): Calculation-specific configuration.
        delta (float): Displacement for finite difference method.
        nfree (int): Number of displacements per degree of freedom.
        indices (list): List of indices of atoms to vibrate.
        name (str): Name prefix for vibration files.
        init_structure (str): Path to initial structure.
        temp (float): Temperature for thermodynamic analysis.
    """
    
    def __init__(self, config, calc_name, calc_config):
        """
        Initialize VibrationWorkflow.

        Args:
            config (dict): Global configuration.
            calc_name (str): Calculator name.
            calc_config (dict): Calculation configuration.
        """
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.delta = calc_config.get('delta', 0.01)
        self.nfree = calc_config.get('nfree', 2)
        self.indices = calc_config.get('indices', None) # If None, all atoms
        self.name = calc_config.get('name', 'vib')
        self.init_structure = calc_config.get('init_structure', 'vib_init.stru')
        self.temp = calc_config.get('temperature', 300.0) # Temperature for thermo analysis
        self.restart = calc_config.get('restart', False)

    def _prepare_cache(self):
        vib_path = Path(self.name)
        if not vib_path.exists():
            return
        if self.restart:
            status = clean_cache_files(vib_path, keep_good=True)
            if status["invalid"]:
                print(
                    "Removed invalid vibration cache file(s): "
                    + ", ".join(str(path) for path in status["invalid"])
                )
            return
        clean_cache_files(vib_path, keep_good=False)

    def run(self):
        """
        Execute the vibration analysis workflow.
        """
        print(f"=== Starting Vibrational Analysis with {self.calc_name} ===")
        
        # 1. Read Structure
        if not os.path.exists(self.init_structure):
             if os.path.exists('init.traj'):
                 self.init_structure = 'init.traj'
             else:
                 raise FileNotFoundError(f"Initial structure {self.init_structure} not found")

        try:
            atoms = read_structure(self.init_structure)
        except Exception as e:
            print(f"Error reading structure: {e}")
            raise

        # 2. Setup Calculator
        directory = self.calc_config.get('directory', 'vib_run')
        if 'abacus' in self.config:
             directory = self.config['abacus'].get('directory', directory)
        
        atoms.calc = CalculatorFactory.get_calculator(
            self.calc_name, 
            self.config, 
            directory=directory
        )

        # 3. Setup Vibrations
        # Use ASE Vibrations class
        self._prepare_cache()
        vib = Vibrations(atoms, 
                         indices=self.indices, 
                         delta=self.delta, 
                         nfree=self.nfree, 
                         name=self.name)
        
        # 4. Run Calculation
        vib.run()
        
        # 5. Summary
        print("=== Vibration Calculation Finished ===")
        vib.summary()
        
        # 6. Get Frequencies and ZPE
        energies = vib.get_energies() 
        frequencies = vib.get_frequencies()
        zpe = vib.get_zero_point_energy()
        
        print(f"Zero Point Energy: {zpe:.4f} eV")

        thermo = compute_vibration_thermochemistry(atoms, energies, self.calc_config, zpe)
        model = thermo["model"]
        print(f"=== Starting {model} Thermodynamic Analysis at T={thermo['temperature']} K ===")
        print(f"Entropy (S): {thermo.get('entropy', 0.0):.6e} eV/K")
        if model == "ideal_gas":
            print(f"Gibbs Free Energy (G): {thermo.get('gibbs_free_energy', 0.0):.6f} eV")
        else:
            print(f"Internal Energy (U): {thermo.get('internal_energy', 0.0):.6f} eV")
            print(f"Helmholtz Free Energy (F): {thermo.get('helmholtz_free_energy', 0.0):.6f} eV")

        # Save results to JSON for easy parsing
        results = {
            'frequencies': frequencies.real.tolist(),
            'imaginary_frequencies': frequencies.imag.tolist(),
            'zpe': zpe,
            'indices': self.indices,
            'thermo': thermo,
        }
        with open('vibration_results.json', 'w') as f:
            json.dump(results, f, indent=4)
