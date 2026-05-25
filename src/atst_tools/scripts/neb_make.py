import argparse
from ase.io import read, write
from atst_tools.utils.idpp import generate
from atst_tools.utils.restart_helpers import select_last_neb_chain


def _parse_fix(value):
    if value is None:
        return None, None
    height, direction = value.split(":", 1)
    return float(height), int(direction)


def _parse_mag(value):
    if value is None:
        return None, None
    elements = []
    moments = []
    for item in value.split(","):
        element, moment = item.split(":", 1)
        elements.append(element)
        moments.append(float(moment))
    return elements, moments

def main():
    parser = argparse.ArgumentParser(description="Generate Initial NEB Chain (IDPP or linear)")
    parser.add_argument('init_file', help='Initial state file')
    parser.add_argument('final_file', help='Final state file')
    parser.add_argument('n_images', type=int, help='Number of intermediate images')
    parser.add_argument('-o', '--output', default='init_neb_chain.traj', help='Output file')
    parser.add_argument('--method', default='IDPP', choices=['IDPP', 'linear'], help='Interpolation method (default: IDPP)')
    parser.add_argument('--format', default=None, help='File format (auto-detect if None)')
    parser.add_argument('--no-align', action='store_true', help='Skip atom index alignment')
    parser.add_argument('--fix', help='Fix atoms below HEIGHT along DIR, e.g. 0.25:2')
    parser.add_argument('--mag', help='Set magnetic moments, e.g. Fe:2.5,O:1.0')
    parser.add_argument('--from-chain', help='Reuse last N_IMAGES+2 frames from a trajectory')
    parser.add_argument('--ts', help='Transition-state guess for segmented interpolation')
    
    args = parser.parse_args()
    
    if args.from_chain:
        images = read(args.from_chain, index=":")
        write(args.output, select_last_neb_chain(images, args.n_images + 2, strict=False))
        return

    fix_height, fix_dir = _parse_fix(args.fix)
    mag_ele, mag_num = _parse_mag(args.mag)
    
    generate(
        method=args.method,
        n_images=args.n_images,
        is_file=args.init_file,
        fs_file=args.final_file,
        output_file=args.output,
        format=args.format,
        fix_height=fix_height,
        fix_dir=fix_dir,
        mag_ele=mag_ele,
        mag_num=mag_num,
        no_align=args.no_align,
        ts_file=args.ts,
    )

if __name__ == "__main__":
    main()
