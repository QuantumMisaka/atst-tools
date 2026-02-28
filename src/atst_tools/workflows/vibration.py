# Vibration Workflow
# part of ATST-Tools

import os
import json
import numpy as np
from ase.io import read
from ase.vibrations import Vibrations
from ase.thermochemistry import HarmonicThermo
from atst_tools.calculators.factory import CalculatorFactory

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
            atoms = read(self.init_structure)
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

        # 8. Harmonic Thermodynamic Analysis
        print(f"=== Starting Harmonic Thermodynamic Analysis at T={self.temp} K ===")
        # Filter real, positive energies for thermo analysis
        # energies are in eV. 
        real_vib_energies = np.array([energy for energy in energies if energy.imag == 0 and energy.real > 0], dtype=float)
        
        if len(real_vib_energies) == 0:
             print("Warning: No valid real vibrational modes found for thermodynamic analysis.")
             entropy = 0.0
             free_energy = 0.0
             internal_energy = 0.0
        else:
             thermo = HarmonicThermo(real_vib_energies)
             entropy = thermo.get_entropy(self.temp)
             internal_energy = thermo.get_internal_energy(self.temp)
             free_energy = thermo.get_helmholtz_energy(self.temp)
             
             print(f"Entropy (S): {entropy:.6e} eV/K")
             print(f"Internal Energy (U): {internal_energy:.6f} eV")
             print(f"Helmholtz Free Energy (F): {free_energy:.6f} eV")

        # Save results to JSON for easy parsing
        results = {
            'frequencies': frequencies.real.tolist(),
            'imaginary_frequencies': frequencies.imag.tolist(),
            'zpe': zpe,
            'thermo': {
                'temperature': self.temp,
                'entropy': entropy,
                'internal_energy': internal_energy,
                'free_energy': free_energy
            }
        }
        with open('vibration_results.json', 'w') as f:
            json.dump(results, f, indent=4)
