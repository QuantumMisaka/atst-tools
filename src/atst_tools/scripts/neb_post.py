import argparse
from ase.io import read
from atst_tools.utils.post import NEBPost

def main():
    parser = argparse.ArgumentParser(description="Analyze NEB Calculation Results")
    parser.add_argument('traj_file', help='NEB trajectory file (e.g., neb.traj)')
    parser.add_argument('--n-max', type=int, default=0, help='Number of intermediate images (0 for auto-detect)')
    parser.add_argument('--plot', action='store_true', help='Plot NEB bands')
    parser.add_argument('--view', action='store_true', help='View NEB bands in ASE GUI')
    
    args = parser.parse_args()
    
    images = read(args.traj_file, index=':')
    post = NEBPost(images, n_max=args.n_max)
    
    print("=== NEB Barrier Analysis ===")
    post.get_barrier()
    
    print("=== Extracting TS Structure ===")
    post.get_TS_stru()
    
    if args.plot:
        print("=== Plotting NEB Bands ===")
        post.plot_neb_bands()
        
    if args.view:
        print("=== Viewing NEB Bands ===")
        post.view_neb_bands()

if __name__ == "__main__":
    main()
