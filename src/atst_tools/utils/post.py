# Analyze NEB and AutoNEB calculation result 
# part of ATST-Tools

from ase.mep.neb import NEBTools
from ase.io import write
from ase.calculators.singlepoint import SinglePointCalculator
import numpy as np
from typing import List

from atst_tools.utils.restart_helpers import select_post_neb_chain

class NEBPost:
    """Post-Processing of NEB result from Atoms object"""
    def __init__(self, images: List, n_max: int = 0):
        self.all_image = images
        
        # Ensure calculators exist before NEBTools usage
        for atoms in self.all_image:
            # Check if calculator is valid or if energy can be retrieved
            valid_calc = True
            if atoms.calc is not None:
                try:
                    atoms.get_potential_energy()
                except:
                    valid_calc = False
            else:
                valid_calc = False

            if not valid_calc:
                e = atoms.info.get('energy', 0.0)
                f = atoms.arrays.get('forces', None)
                if f is None:
                     f = np.zeros((len(atoms), 3))
                atoms.calc = SinglePointCalculator(atoms, energy=e, forces=f)

        if n_max == 0:
            print("=== n_max set to 0, automatically detect the images of chain by NEBTools ===")
            self.neb_chain = select_post_neb_chain(images, n_max=0)
            self.n_images = len(self.neb_chain)
        elif (n_max > 0) and (isinstance(n_max, int)):
            self.n_images = n_max + 2
            self.neb_chain = select_post_neb_chain(images, n_max=n_max)
        else:
            raise ValueError("n_max must be a non-negative integer")

    def get_barrier(self):
        """Returns energy of all image and the barrier estimate from the NEB, along with the Delta E of the elementary reaction"""
        for i, atoms in enumerate(self.neb_chain):
            try:
                ene = atoms.get_potential_energy()
            except RuntimeError:
                # If calculator is missing, try to get energy from info or stored energy
                if hasattr(atoms, 'get_total_energy'):
                    ene = atoms.get_total_energy()
                elif 'energy' in atoms.info:
                    ene = atoms.info['energy']
                else:
                    print(f"Warning: No energy found for image {i}")
                    ene = 0.0
            print(f"num: {i}; Energy: {ene} (eV)")
        
        # NEBTools might fail if calculators are missing. 
        # We need to ensure atoms have energies attached in a way NEBTools likes.
        for atoms in self.neb_chain:
            if atoms.calc is None:
                # Try to recover energy and forces
                e = atoms.info.get('energy', 0.0)
                f = atoms.arrays.get('forces', None)
                if f is None:
                    # Create dummy forces if missing (not ideal but prevents crash)
                    f = np.zeros((len(atoms), 3))
                atoms.calc = SinglePointCalculator(atoms, energy=e, forces=f)

        barrier = NEBTools(self.neb_chain).get_barrier(fit=True)
        # set fit to True/False is not determined yet
        print(f"Reaction Barrier and Energy Difference: {barrier} (eV)")
        return barrier
    
    def get_TS_stru(self, name="TS_get"):
        """Get TS structure from NEB chain"""
        energies = [atoms.get_potential_energy() for atoms in self.neb_chain]
        atoms = self.neb_chain[int(np.argmax(energies))]
        write(f"{name}.cif", atoms, format="cif")
        try:
            write(f"{name}.stru", atoms, format="stru")
            print(f"TS structure is saved as {name}.cif and {name}.stru")
        except Exception as e:
            print(f"TS structure is saved as {name}.cif")
            print(f"Warning: Failed to save {name}.stru (format 'stru' not supported?): {e}")
        return

    def plot_neb_bands(self, label='nebplots_chain'):
        """makes plots of final neb band in the series in a single PDF"""
        try:
            return NEBTools(self.neb_chain).plot_bands(label=label, nimages=len(self.neb_chain))
        except Exception as e:
            print(f"Warning: Failed to plot NEB bands. {e}")
            return None
    
    def plot_all_bands(self, label='nebplots_all'):
        """Gmakes plots of all band during neb in the series in a single PDF"""
        try:
            return NEBTools(self.all_image).plot_bands(label=label, nimages=self.n_images)
        except Exception as e:
            print(f"Warning: Failed to plot all bands. {e}")
            return None
    
    def write_latest_bands(self, outname="neb_latest"):
        """write latest neb chain to file"""
        write(f"{outname}.traj", self.neb_chain, format="traj")
        extxyz_chain = []
        for atoms in self.neb_chain:
            image = atoms.copy()
            if image.calc is not None:
                for key in ("energy", "free_energy", "stress", "dipole", "magmom"):
                    image.info.pop(key, None)
                for key in ("forces", "stresses", "charges", "magmoms"):
                    if key in image.arrays:
                        del image.arrays[key]
            extxyz_chain.append(image)
        write(f"{outname}.extxyz", extxyz_chain, format="extxyz")
        return
    
    def view_neb_bands(self, traj_file="neb.traj"):
        """view neb chain"""
        import os

        os.system(f'ase gui {traj_file}@-{self.n_images}:')
