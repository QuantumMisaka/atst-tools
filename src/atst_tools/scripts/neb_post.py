import argparse
from ase.io import read
from atst_tools.utils.post import NEBPost
from atst_tools.utils.analysis import get_displacement_analysis

def main():
    parser = argparse.ArgumentParser(description="Analyze NEB Calculation Results")
    parser.add_argument('traj_file', help='NEB trajectory file (e.g., neb.traj)')
    parser.add_argument('--n-max', type=int, default=0, help='Number of intermediate images (0 for auto-detect)')
    parser.add_argument('--plot', action='store_true', help='Plot NEB bands')
    parser.add_argument('--view', action='store_true', help='View NEB bands in ASE GUI')
    parser.add_argument('--vib-analysis', action='store_true', help='Analyze displacement for vibration indices')
    parser.add_argument('--vib-thr', type=float, default=0.10, help='Threshold for vibration displacement analysis (default: 0.10)')
    
    args = parser.parse_args()
    
    images = read(args.traj_file, index=':')
    post = NEBPost(images, n_max=args.n_max)
    
    print("=== NEB Barrier Analysis ===")
    post.get_barrier()
    
    print("=== Extracting TS Structure ===")
    post.get_TS_stru()
    
    if args.vib_analysis:
        print("=== Vibration Displacement Analysis ===")
        # NEBPost prepares neb_chain, pass it to analysis
        ts_idx, indices, norm_vec = get_displacement_analysis(post.neb_chain, thr=args.vib_thr)
        print(f"TS Image Index (in chain): {ts_idx}")
        print(f"Displacement Threshold: {args.vib_thr}")
        print(f"Suggested Vibration Indices (0-based): {indices}")
        print(f"Normalized Displacement Vector (main components):")
        for idx in indices:
            print(f"  Atom {idx}: {norm_vec[idx]:.4f}")
    
    if args.plot:
        print("=== Plotting NEB Bands ===")
        post.plot_neb_bands()
        
    if args.view:
        print("=== Viewing NEB Bands ===")
        post.view_neb_bands()

if __name__ == "__main__":
    main()
