"""Git-style command line interface for ATST-Tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from ase.io import read, write
from ase.vibrations import Vibrations

from atst_tools.scripts import main as run_cli
from atst_tools.utils.analysis import get_displacement_analysis
from atst_tools.utils.config import ConfigLoader, VALID_CALCULATION_TYPES
from atst_tools.utils.idpp import generate
from atst_tools.utils.io import read_structure
from atst_tools.utils.post import NEBPost
from atst_tools.utils.restart_helpers import check_cache_files
from atst_tools.utils.thermochemistry import compute_vibration_thermochemistry


def _add_run_parser(subparsers):
    parser = subparsers.add_parser(
        "run",
        help="Run a YAML-driven workflow",
        description="Run an ATST-Tools workflow from a YAML configuration.",
    )
    parser.add_argument("config", nargs="?", help="Path to configuration file (YAML)")
    parser.add_argument("--dry-run", action="store_true", help="Validate YAML and exit")
    parser.add_argument("--restart", action="store_true", help="Resume from checkpoints when supported")
    parser.add_argument("--list-types", action="store_true", help="Print supported calculation types")
    parser.add_argument("--show-template", choices=VALID_CALCULATION_TYPES, help="Print a YAML template")
    parser.add_argument("--calculator", choices=("abacus", "dp"), default="abacus")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    parser.set_defaults(func=_run_command)


def _run_command(args):
    if not args.config and not args.list_types and not args.show_template:
        raise SystemExit("atst run requires CONFIG unless --list-types or --show-template is used")
    return run_cli.run_from_args(args)


def _add_neb_parser(subparsers):
    parser = subparsers.add_parser("neb", help="NEB preparation and analysis tools")
    neb_subparsers = parser.add_subparsers(dest="neb_command", required=True)

    make = neb_subparsers.add_parser("make", help="Generate an initial NEB chain")
    make.add_argument("init_file", help="Initial state file")
    make.add_argument("final_file", help="Final state file")
    make.add_argument("n_images", type=int, help="Number of intermediate images")
    make.add_argument("-o", "--output", default="init_neb_chain.traj", help="Output trajectory")
    make.add_argument("--method", default="IDPP", choices=("IDPP", "linear"), help="Interpolation method")
    make.add_argument("--format", default=None, help="Input file format")
    make.add_argument("--no-align", action="store_true", help="Skip atom index alignment")
    make.set_defaults(func=_neb_make_command)

    post = neb_subparsers.add_parser("post", help="Analyze an NEB trajectory")
    post.add_argument("traj_file", help="NEB trajectory file")
    post.add_argument("--n-max", type=int, default=0, help="Number of intermediate images")
    post.add_argument("--plot", action="store_true", help="Plot NEB bands")
    post.add_argument("--view", action="store_true", help="View NEB bands in ASE GUI")
    post.add_argument("--vib-analysis", action="store_true", help="Suggest vibration atom indices")
    post.add_argument("--vib-thr", type=float, default=0.10, help="Vibration displacement threshold")
    post.set_defaults(func=_neb_post_command)


def _neb_make_command(args):
    return generate(
        method=args.method,
        n_images=args.n_images,
        is_file=args.init_file,
        fs_file=args.final_file,
        output_file=args.output,
        format=args.format,
        no_align=args.no_align,
    )


def _neb_post_command(args):
    images = read(args.traj_file, index=":")
    post = NEBPost(images, n_max=args.n_max)

    print("=== NEB Barrier Analysis ===")
    post.get_barrier()

    print("=== Extracting TS Structure ===")
    post.get_TS_stru()

    if args.vib_analysis:
        print("=== Vibration Displacement Analysis ===")
        ts_idx, indices, norm_vec = get_displacement_analysis(post.neb_chain, thr=args.vib_thr)
        print(f"TS Image Index (in chain): {ts_idx}")
        print(f"Displacement Threshold: {args.vib_thr}")
        print(f"Suggested Vibration Indices (0-based): {indices}")
        print("Normalized Displacement Vector (main components):")
        for idx in indices:
            print(f"  Atom {idx}: {norm_vec[idx]:.4f}")

    if args.plot:
        print("=== Plotting NEB Bands ===")
        post.plot_neb_bands()

    if args.view:
        print("=== Viewing NEB Bands ===")
        post.view_neb_bands()


def _add_dimer_parser(subparsers):
    parser = subparsers.add_parser("dimer", help="Dimer preparation tools")
    dimer_subparsers = parser.add_subparsers(dest="dimer_command", required=True)

    make = dimer_subparsers.add_parser(
        "make-from-neb",
        help="Extract a Dimer initial structure and displacement vector from NEB results",
    )
    make.add_argument("traj_file", help="NEB trajectory file")
    make.add_argument("--n-max", type=int, default=0, help="Number of intermediate images")
    make.add_argument("--output-traj", default="dimer_init.traj", help="Output TS guess trajectory")
    make.add_argument("--output-structure", dest="output_traj", help=argparse.SUPPRESS)
    make.add_argument("--output-vector", default="displacement_vector.npy", help="Output displacement vector")
    make.add_argument("--norm", type=float, default=0.01, help="Displacement vector norm")
    make.set_defaults(func=_dimer_make_from_neb_command)


def _dimer_make_from_neb_command(args):
    images = read(args.traj_file, index=":")
    post = NEBPost(images, n_max=args.n_max)
    chain = post.neb_chain
    energies = [image.get_potential_energy() for image in chain]
    ts_idx = int(np.argmax(energies))
    before = max(0, ts_idx - 1)
    after = min(len(chain) - 1, ts_idx + 1)
    vector = chain[before].positions - chain[after].positions
    vector_norm = np.linalg.norm(vector)
    displacement_vector = vector if vector_norm < 1e-12 else vector / vector_norm * args.norm

    write(args.output_traj, chain[ts_idx])
    np.save(args.output_vector, displacement_vector)
    print(f"TS image index: {ts_idx}")
    print(f"Wrote {args.output_traj}")
    print(f"Wrote {args.output_vector}")


def _add_relax_parser(subparsers):
    parser = subparsers.add_parser("relax", help="Relaxation post-processing tools")
    relax_subparsers = parser.add_subparsers(dest="relax_command", required=True)

    post = relax_subparsers.add_parser(
        "post",
        help="Extract a frame for relax or TS relax restart",
        description=(
            "Extract a structure from a relax trajectory. This is also useful for "
            "TS relax / Single-End Methods restart preparation."
        ),
        epilog="Use this command to prepare restart structures for TS relax / Single-End Methods restart.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    post.add_argument("traj_file", help="Relax, Dimer, or Sella trajectory file")
    post.add_argument("--ind", type=int, default=-1, help="Frame index to extract")
    post.add_argument("--output-format", default="stru", choices=("stru", "cif", "poscar", "traj", "xyz"))
    post.add_argument("--output", help="Output structure path")
    post.set_defaults(func=_relax_post_command)


def _max_force(atoms) -> float:
    try:
        forces = atoms.get_forces()
    except Exception:
        return float("nan")
    if len(forces) == 0:
        return 0.0
    return float(np.linalg.norm(forces, axis=1).max())


def _relax_post_command(args):
    atoms = read(args.traj_file, index=args.ind)
    default_outputs = {"stru": "STRU", "poscar": "POSCAR"}
    output = args.output or default_outputs.get(args.output_format, f"relax_frame_{args.ind}.{args.output_format}")
    write_format = "vasp" if args.output_format == "poscar" else args.output_format
    print(f"Energy: {atoms.get_potential_energy():.10f} eV")
    print(f"Max force: {_max_force(atoms):.10f} eV/Ang")
    try:
        write(output, atoms, format=write_format)
    except Exception as exc:
        if args.output_format != "stru":
            raise
        raise RuntimeError(
            "Failed to write STRU output. Ensure an ASE writer for ABACUS STRU is available, "
            "or use --output-format cif/poscar/traj."
        ) from exc
    print(f"Wrote {output}")


def _add_vibration_parser(subparsers):
    parser = subparsers.add_parser("vibration", help="Vibration post-processing tools")
    vib_subparsers = parser.add_subparsers(dest="vibration_command", required=True)

    post = vib_subparsers.add_parser("post", help="Rebuild vibration summary from existing cache")
    post.add_argument("config", help="Vibration YAML configuration")
    post.add_argument("--write-modes", action="store_true", help="Write ASE vibration mode trajectories")
    post.add_argument("--output", default="vibration_results.json", help="Output JSON file")
    post.set_defaults(func=_vibration_post_command)


def _vibration_post_command(args):
    config = ConfigLoader.load(args.config)
    ConfigLoader.validate(config)
    calc_config = config["calculation"]
    cache_status = check_cache_files(calc_config.get("name", "vib"))
    if cache_status["invalid"]:
        bad_files = ", ".join(str(path) for path in cache_status["invalid"])
        raise RuntimeError(
            "Invalid vibration cache file(s) detected. Remove them or rerun with "
            f"`atst run --restart {args.config}` before post-processing: {bad_files}"
        )
    atoms = read_structure(calc_config.get("init_structure", "vib_init.stru"))
    vib = Vibrations(
        atoms,
        indices=calc_config.get("indices"),
        delta=calc_config.get("delta", 0.01),
        nfree=calc_config.get("nfree", 2),
        name=calc_config.get("name", "vib"),
    )

    vib.summary()
    if args.write_modes:
        vib.write_mode()

    energies = vib.get_energies()
    frequencies = vib.get_frequencies()
    zpe = vib.get_zero_point_energy()
    thermo = compute_vibration_thermochemistry(atoms, energies, calc_config, zpe)

    results = {
        "frequencies": frequencies.real.tolist(),
        "imaginary_frequencies": frequencies.imag.tolist(),
        "zpe": float(zpe),
        "indices": calc_config.get("indices"),
        "thermo": thermo,
    }
    Path(args.output).write_text(json.dumps(results, indent=4), encoding="utf-8")
    print(f"Wrote {args.output}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="atst",
        description="ATST-Tools: ASE workflows and lightweight helpers",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {run_cli._package_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_run_parser(subparsers)
    _add_neb_parser(subparsers)
    _add_dimer_parser(subparsers)
    _add_relax_parser(subparsers)
    _add_vibration_parser(subparsers)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    main()
