"""Git-style command line interface for ATST-Tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import dedent

from atst_tools.utils.mpi import bootstrap_mpi_for_ase

bootstrap_mpi_for_ase()

import numpy as np
from ase.io import read, write
from ase.vibrations import Vibrations

from atst_tools.scripts import main as run_cli
from atst_tools.utils.analysis import get_displacement_analysis
from atst_tools.utils.abacus_io import collect_abacus_output, prepare_abacus_input
from atst_tools.utils.config import ConfigLoader, VALID_CALCULATION_TYPES
from atst_tools.utils.idpp import generate
from atst_tools.utils.io import read_structure
from atst_tools.utils.post import NEBPost
from atst_tools.utils.restart_helpers import (
    check_cache_files,
    read_autoneb_final_chain,
    select_last_neb_chain,
    select_post_neb_chain,
)
from atst_tools.utils.thermochemistry import compute_vibration_thermochemistry


def _add_run_parser(subparsers):
    parser = subparsers.add_parser(
        "run",
        help="Run a YAML-driven workflow",
        description="Run an ATST-Tools workflow from a YAML configuration.",
        epilog=dedent(
            """\
            Examples:
              atst run config.yaml
              atst run --dry-run config.yaml
              atst run --show-template neb --calculator abacus
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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


def _write_yaml(data, output=None):
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    if output:
        with Path(output).open("w", encoding="utf-8") as handle:
            yaml.dump(data, handle)
    else:
        import sys

        yaml.dump(data, sys.stdout)


def _add_config_parser(subparsers):
    parser = subparsers.add_parser("config", help="Configuration validation and inspection tools")
    config_subparsers = parser.add_subparsers(dest="config_command", required=True)

    validate = config_subparsers.add_parser(
        "validate",
        help="Validate an ATST YAML configuration",
        description="Validate an ATST YAML file and optionally print the schema-normalized configuration.",
        epilog=dedent(
            """\
            Examples:
              atst config validate config.yaml
              atst config validate config.yaml --print-normalized
              atst config validate config.yaml --output used_config.yaml
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    validate.add_argument("config", help="Path to configuration file (YAML)")
    validate.add_argument("--print-normalized", action="store_true", help="Print normalized YAML to stdout")
    validate.add_argument("--output", help="Write normalized YAML to this path")
    validate.set_defaults(func=_config_validate_command)


def _config_validate_command(args):
    config = ConfigLoader.normalize(ConfigLoader.load(args.config))
    if args.output:
        _write_yaml(config, args.output)
        print(f"Wrote normalized config to {args.output}")
    if args.print_normalized:
        _write_yaml(config)
    if not args.output and not args.print_normalized:
        print("Configuration is valid")


def _add_abacus_parser(subparsers):
    parser = subparsers.add_parser(
        "abacus",
        help="ABACUS input preparation and output collection helpers",
        description=(
            "Prepare ABACUS input files and collect conservative output summaries. "
            "These helpers do not run ABACUS or submit jobs."
        ),
    )
    abacus_subparsers = parser.add_subparsers(dest="abacus_command", required=True)

    prepare = abacus_subparsers.add_parser(
        "prepare",
        help="Write INPUT, KPT, and STRU from an ATST config",
        epilog=dedent(
            """\
            Example:
              atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    prepare.add_argument("config", help="ATST YAML configuration using calculator.name: abacus")
    prepare.add_argument("--structure", required=True, help="Structure file to write into STRU")
    prepare.add_argument("--output-dir", required=True, help="Directory for INPUT, KPT, and STRU")
    prepare.add_argument("--force", action="store_true", help="Overwrite existing INPUT/KPT/STRU files")
    prepare.set_defaults(func=_abacus_prepare_command)

    collect = abacus_subparsers.add_parser(
        "collect",
        help="Collect a JSON summary from an ABACUS run directory",
        epilog=dedent(
            """\
            Examples:
              atst abacus collect run_neb --output abacus_results.json
              atst abacus collect run_neb --output abacus_results.json --structure final.extxyz
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    collect.add_argument("run_dir", help="ABACUS run directory")
    collect.add_argument("--output", default="abacus_results.json", help="Output JSON summary")
    collect.add_argument("--structure", help="Optional output structure for a parsed final frame")
    collect.set_defaults(func=_abacus_collect_command)


def _abacus_prepare_command(args):
    paths = prepare_abacus_input(
        args.config,
        args.structure,
        args.output_dir,
        force=args.force,
    )
    print("Wrote ABACUS input files:")
    for name in ("INPUT", "KPT", "STRU"):
        print(f"  {name}: {paths[name]}")


def _abacus_collect_command(args):
    summary = collect_abacus_output(args.run_dir, args.output, structure=args.structure)
    print(f"Wrote {args.output}")
    if summary["parsed"]:
        print("Parsed final ABACUS frame")
    elif summary["parse_error"]:
        print(f"Collected file summary; parser skipped with: {summary['parse_error']}")
    else:
        print("Collected file summary; no parseable eig_occ.txt was found")


def _add_neb_parser(subparsers):
    parser = subparsers.add_parser("neb", help="NEB preparation and analysis tools")
    neb_subparsers = parser.add_subparsers(dest="neb_command", required=True)

    make = neb_subparsers.add_parser("make", help="Generate an initial NEB chain")
    make.add_argument("init_file", help="Initial state file")
    make.add_argument("final_file", help="Final state file")
    make.add_argument("n_images", type=int, help="Number of intermediate images")
    make.add_argument("-o", "--output", default="init_neb_chain.traj", help="Output trajectory")
    make.add_argument(
        "--method",
        default="IDPP",
        choices=("IDPP", "linear"),
        help="Interpolation method (default: IDPP)",
    )
    make.add_argument("--format", default=None, help="Input file format")
    make.add_argument("--no-align", action="store_true", help="Skip atom index alignment")
    make.add_argument("--fix", help="Fix atoms below HEIGHT along DIR, e.g. 0.25:2")
    make.add_argument("--mag", help="Set magnetic moments, e.g. Fe:2.5,O:1.0")
    make.add_argument("--from-chain", help="Reuse the last N_IMAGES+2 frames from an existing chain")
    make.add_argument("--ts", help="Transition-state guess for segmented interpolation")
    make.set_defaults(func=_neb_make_command)

    post = neb_subparsers.add_parser("post", help="Analyze an NEB trajectory")
    post.add_argument("traj_file", nargs="?", help="NEB trajectory file")
    post.add_argument("--n-max", type=int, default=0, help="Number of intermediate images")
    post.add_argument("--plot", action="store_true", help="Plot NEB bands")
    post.add_argument("--plot-all", action="store_true", help="Plot all bands in the input trajectory")
    post.add_argument("--view", action="store_true", help="View NEB bands in ASE GUI")
    post.add_argument("--vib-analysis", action="store_true", help="Suggest vibration atom indices")
    post.add_argument("--vib-thr", type=float, default=0.10, help="Vibration displacement threshold")
    post.add_argument("--autoneb-prefix", help="Read AutoNEB per-image files matching PREFIX*.traj/extxyz")
    post.add_argument("--autoneb-files", nargs="+", help="Read explicit AutoNEB per-image files")
    post.add_argument("--output-prefix", default="TS_get", help="Prefix for extracted TS structure")
    post.add_argument("--write-latest", help="Write selected latest band to PREFIX.traj and PREFIX.extxyz")
    post.add_argument("--write-neb-init-chain", help="Write selected final chain for ordinary NEB refinement")
    post.add_argument("--strict-band", action="store_true", help="Require trajectory length to be whole NEB bands")
    post.set_defaults(func=_neb_post_command)


def _parse_fix(value):
    if value is None:
        return None, None
    try:
        height, direction = value.split(":", 1)
        return float(height), int(direction)
    except ValueError as exc:
        raise SystemExit("--fix must use HEIGHT:DIR, e.g. 0.25:2") from exc


def _parse_mag(value):
    if value is None:
        return None, None
    elements = []
    moments = []
    for item in value.split(","):
        try:
            element, moment = item.split(":", 1)
            elements.append(element)
            moments.append(float(moment))
        except ValueError as exc:
            raise SystemExit("--mag must use ELEMENT:MOMENT[,ELEMENT:MOMENT...]") from exc
    return elements, moments


def _neb_make_command(args):
    if args.from_chain:
        images = read(args.from_chain, index=":")
        write(args.output, select_last_neb_chain(images, args.n_images + 2, strict=False))
        print(f"Wrote {args.output}")
        return

    fix_height, fix_dir = _parse_fix(args.fix)
    mag_ele, mag_num = _parse_mag(args.mag)
    return generate(
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


def _neb_post_command(args):
    if args.autoneb_prefix and args.autoneb_files:
        raise SystemExit("Use only one of --autoneb-prefix or --autoneb-files")
    if args.autoneb_prefix:
        images = read_autoneb_final_chain(args.autoneb_prefix)
    elif args.autoneb_files:
        images = read_autoneb_final_chain(args.autoneb_files)
    else:
        if not args.traj_file:
            raise SystemExit("atst neb post requires TRAJ unless AutoNEB input is provided")
        images = read(args.traj_file, index=":")

    strict = args.strict_band or bool(args.write_neb_init_chain)
    selected = select_post_neb_chain(images, n_max=args.n_max, strict=strict)
    post = NEBPost(selected, n_max=0)

    print("=== NEB Barrier Analysis ===")
    post.get_barrier()

    print("=== Extracting TS Structure ===")
    post.get_TS_stru(name=args.output_prefix)

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

    if args.plot_all:
        print("=== Plotting All NEB Bands ===")
        NEBPost(images, n_max=0).plot_all_bands()

    if args.write_latest:
        post.write_latest_bands(args.write_latest)
        print(f"Wrote {args.write_latest}.traj and {args.write_latest}.extxyz")

    if args.write_neb_init_chain:
        write(args.write_neb_init_chain, post.neb_chain)
        print(f"Wrote {args.write_neb_init_chain}")

    if args.view:
        print("=== Viewing NEB Bands ===")
        post.view_neb_bands(args.traj_file or args.write_neb_init_chain or "neb.traj")


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
    config = ConfigLoader.normalize(config)
    calc_config = config["calculation"]
    cache_status = check_cache_files(calc_config["name"])
    if cache_status["invalid"]:
        bad_files = ", ".join(str(path) for path in cache_status["invalid"])
        raise RuntimeError(
            "Invalid vibration cache file(s) detected. Remove them or rerun with "
            f"`atst run --restart {args.config}` before post-processing: {bad_files}"
        )
    atoms = read_structure(calc_config["init_structure"])
    vib = Vibrations(
        atoms,
        indices=calc_config.get("indices"),
        delta=calc_config["delta"],
        nfree=calc_config["nfree"],
        name=calc_config["name"],
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


def _add_traj_parser(subparsers):
    parser = subparsers.add_parser("traj", help="Trajectory collection and conversion tools")
    traj_subparsers = parser.add_subparsers(dest="traj_command", required=True)

    collect = traj_subparsers.add_parser("collect", help="Collect structures into a multi-frame trajectory")
    collect.add_argument("structures", nargs="+", help="Input structure files")
    collect.add_argument("-o", "--output", default="collection.traj", help="Output trajectory")
    collect.add_argument("--no-calc", action="store_true", help="Drop attached calculators before writing")
    collect.set_defaults(func=_traj_collect_command)

    transform = traj_subparsers.add_parser("transform", help="Transform trajectory frames to another format")
    transform.add_argument("traj_file", help="Input trajectory")
    transform.add_argument("--format", choices=("traj", "extxyz", "stru", "cif"), default="extxyz")
    transform.add_argument("--neb", action="store_true", help="Select the latest NEB band before writing")
    transform.add_argument("--n-max", type=int, default=0, help="Number of intermediate NEB images")
    transform.add_argument("--output-prefix", default="frame", help="Output prefix or directory")
    transform.set_defaults(func=_traj_transform_command)


def _traj_collect_command(args):
    frames = []
    for structure in sorted(args.structures):
        atoms = read(structure)
        if args.no_calc:
            atoms.calc = None
        frames.append(atoms)
    write(args.output, frames)
    print(f"Wrote {args.output} ({len(frames)} frame(s))")


def _traj_transform_command(args):
    frames = read(args.traj_file, index=":")
    if args.neb:
        frames = select_post_neb_chain(frames, n_max=args.n_max, strict=args.n_max > 0)

    if args.format in {"traj", "extxyz"}:
        output = f"{args.output_prefix}.{args.format}"
        write(output, frames, format=args.format)
        print(f"Wrote {output}")
        return

    output_dir = Path(args.output_prefix)
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, atoms in enumerate(frames):
        output = output_dir / f"{index:04d}.{args.format}"
        write(str(output), atoms, format=args.format)
    print(f"Wrote {len(frames)} file(s) under {output_dir}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="atst",
        description="ATST-Tools: ASE workflows and lightweight helpers",
        epilog=dedent(
            """\
            Examples:
              atst run config.yaml
              atst config validate config.yaml --print-normalized
              atst abacus prepare config.yaml --structure inputs/init.stru --output-dir abacus_input
              atst neb post neb.traj --n-max 5 --vib-analysis
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {run_cli._package_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_run_parser(subparsers)
    _add_config_parser(subparsers)
    _add_abacus_parser(subparsers)
    _add_neb_parser(subparsers)
    _add_dimer_parser(subparsers)
    _add_relax_parser(subparsers)
    _add_vibration_parser(subparsers)
    _add_traj_parser(subparsers)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    main()
