# JamesMisaka in 2023-11-06
# Analyze NEB and AutoNEB calculation result 
# part of ATST-Tools scripts

from ase.mep.neb import NEBTools # newest ase
from ase.io import read, write
import sys, os
import numpy as np

# next dev: point-out transition state
class NEBPost():
    """Post-Processing of NEB result from Atoms object"""
    def __init__(self, images, n_max: int = 0):
        self.all_image = images
        
        # Ensure calculators exist before NEBTools usage
        from ase.calculators.singlepoint import SinglePointCalculator
        import numpy as np
        
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
            try:
                self.n_images = NEBTools(self.all_image)._guess_nimages()
            except Exception:
                # Fallback if NEBTools fails to guess (e.g. for simple list of images)
                self.n_images = len(self.all_image)
            self.neb_chain = images[ - self.n_images:]
        elif (n_max > 0) and (type(n_max) == int):
            self.n_images = n_max + 2
            self.neb_chain = images[ - self.n_images:]
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
        # But NEBTools uses .get_potential_energy(). 
        # So we should probably attach a SinglePointCalculator if needed.
        from ase.calculators.singlepoint import SinglePointCalculator
        for atoms in self.neb_chain:
            if atoms.calc is None:
                # Try to recover energy and forces
                e = atoms.info.get('energy', 0.0)
                f = atoms.arrays.get('forces', None)
                if f is None:
                    # Create dummy forces if missing (not ideal but prevents crash)
                    import numpy as np
                    f = np.zeros((len(atoms), 3))
                atoms.calc = SinglePointCalculator(atoms, energy=e, forces=f)

        barrier = NEBTools(self.neb_chain).get_barrier(fit=True)
        # set fit to True/False is not determined yet
        print(f"Reaction Barrier and Energy Difference: {barrier} (eV)")
        return barrier
    
    def get_TS_stru(self, name="TS_get"):
        """Get TS structure from NEB chain"""
        raw_barrier = NEBTools(self.neb_chain).get_barrier(fit=False, raw=True)[0]
        for atoms in self.neb_chain:
            ene = atoms.get_potential_energy()
            if np.isclose(ene, raw_barrier):
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
            return NEBTools(self.neb_chain).plot_bands(label=label)
        except Exception as e:
            print(f"Warning: Failed to plot NEB bands. {e}")
            return None
    
    def plot_all_bands(self, label='nebplots_all'):
        """Gmakes plots of all band during neb in the series in a single PDF"""
        try:
            return NEBTools(self.all_image).plot_bands(label=label)
        except Exception as e:
            print(f"Warning: Failed to plot all bands. {e}")
            return None
    
    def write_latest_bands(self, outname="neb_latest"):
        """write latest neb chain to file"""
        write(f"{outname}.traj", self.neb_chain, format="traj")
        write(f"{outname}.extxyz", self.neb_chain, format="extxyz")
        return
    
    def view_neb_bands(self):
        """view neb chain"""
        os.system(f'ase gui neb.traj@-{self.n_images}:')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Post-Processing of NEB result")
    parser.add_argument("traj", type=str, nargs='+', help="Trajectory files (or single file for traditional NEB)")
    parser.add_argument("-n", "--n_images", type=int, default=0, help="Number of intermediate images (default: 0, auto-detect)")
    parser.add_argument("--autoneb", action="store_true", help="Process AutoNEB results (multiple traj files)")
    
    args = parser.parse_args()

    if args.autoneb:
        print("=== Processing AutoNEB results ===")
        # For AutoNEB, args.traj contains list of trajectory files
        # We assume each file contains ONE image of the chain, so we read the LAST image from each file
        # Wait, the original code logic for autoneb was:
        # result_atoms = [read(traj, format="traj") for traj in traj_files]
        # read(traj) returns the last image by default. So it builds a list of atoms.
        try:
            result_atoms = [read(f, format="traj") for f in args.traj]
            # NEBPost expects a list of Atoms objects
            result = NEBPost(result_atoms, n_max=0)
            result.get_barrier()
            result.plot_neb_bands() # AutoNEB usually produces the final chain directly
            result.write_latest_bands()
            result.get_TS_stru()
        except Exception as e:
            print(f"Error processing AutoNEB files: {e}")
    else:
        # Traditional NEB: usually one trajectory file containing optimization history
        if len(args.traj) > 1:
            print("Warning: Multiple files provided without --autoneb. Using the first one.")
        
        traj_file = args.traj[0]
        print(f"=== Processing NEB trajectory: {traj_file} ===")
        try:
            all_images = read(traj_file, index=":", format="traj")
            result = NEBPost(all_images, n_max=args.n_images)
            result.get_barrier()
            result.plot_all_bands()
            result.plot_neb_bands()
            result.write_latest_bands()
            result.get_TS_stru()
        except Exception as e:
            print(f"Error processing NEB trajectory: {e}")
    