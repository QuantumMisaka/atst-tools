
import os
import json
import numpy as np
from ase.io import read
from ase.vibrations import Vibrations
from atst_tools.calculators.factory import CalculatorFactory

class VibrationWorkflow:
    def __init__(self, config, calc_name, calc_config):
        self.config = config
        self.calc_name = calc_name
        self.calc_config = calc_config
        self.delta = calc_config.get('delta', 0.01)
        self.nfree = calc_config.get('nfree', 2)
        self.indices = calc_config.get('indices', None) # If None, all atoms
        self.name = calc_config.get('name', 'vib')
        self.init_structure = calc_config.get('init_structure', 'vib_init.stru')

    def run(self):
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
        
        # 6. Write Modes
        vib.write_mode() # Writes traj files for modes
        
        # 7. Get Frequencies and ZPE
        energies = vib.get_energies()
        frequencies = vib.get_frequencies()
        zpe = vib.get_zero_point_energy()
        
        print(f"Zero Point Energy: {zpe:.4f} eV")
        
        # Save results to JSON for easy parsing
        results = {
            'frequencies': frequencies.real.tolist(),
            'imaginary_frequencies': frequencies.imag.tolist(),
            'zpe': zpe
        }
        with open('vibration_results.json', 'w') as f:
            json.dump(results, f, indent=4)
