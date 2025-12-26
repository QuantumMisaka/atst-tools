import argparse
from atst_tools.utils.idpp import generate

def main():
    parser = argparse.ArgumentParser(description="Generate Initial NEB Chain (IDPP)")
    parser.add_argument('init_file', help='Initial state file')
    parser.add_argument('final_file', help='Final state file')
    parser.add_argument('n_images', type=int, help='Number of intermediate images')
    parser.add_argument('-o', '--output', default='init_neb_chain.traj', help='Output file')
    parser.add_argument('--method', default='IDPP', choices=['IDPP', 'linear'], help='Interpolation method')
    parser.add_argument('--format', default=None, help='File format (auto-detect if None)')
    parser.add_argument('--no-align', action='store_true', help='Skip atom index alignment')
    
    args = parser.parse_args()
    
    # Calculate n_images for generate function (which expects total images?)
    # The original neb_make.py logic: n_images is intermediate images.
    # generate function expects n_images as intermediate count.
    
    generate(
        method=args.method,
        n_images=args.n_images,
        is_file=args.init_file,
        fs_file=args.final_file,
        output_file=args.output,
        format=args.format,
        no_align=args.no_align
    )

if __name__ == "__main__":
    main()
