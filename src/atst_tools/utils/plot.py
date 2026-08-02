"""Transition-state trajectory visualization (dual-entry API and CLI).

Public plotting helpers for NEB/AutoNEB energy profiles and Sella/CCQN
convergence curves.  Every helper renders a PNG with the headless matplotlib
Agg backend and returns the written path; the CLI
(``python -m atst_tools.utils.plot``) is a thin adapter over the same
functions, so both entry points share one implementation.

matplotlib is an optional dependency (``pip install "atst-tools[plot]"``).  It
is imported lazily inside ``_pyplot`` so that importing this module or
``atst_tools.api`` never requires it; when it is absent the helpers raise a
clear :class:`ImportError` and the CLI reports the same message and exits 1.

The Sella/CCQN curves consume step energies directly from the trajectory
frames (frame index == step), independent of any progress-event stream.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys
from typing import Any

import ase
import ase.io
import numpy as np

__all__ = ["neb_energy_profile", "sella_energy_curve", "ccqn_energy_curve"]


def _pyplot() -> Any:
    """Return ``matplotlib.pyplot``, importing it lazily with the Agg backend."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "atst_tools.utils.plot requires matplotlib; "
            'install it with `pip install "atst-tools[plot]"`'
        ) from exc
    return plt


def _image_energy(atoms: Any, *, index: int | None = None) -> float:
    """Return a frozen energy for one image without triggering a calculation."""
    calculator = getattr(atoms, "calc", None)
    results = getattr(calculator, "results", None)
    if isinstance(results, dict) and results.get("energy") is not None:
        return float(results["energy"])
    stored = getattr(atoms, "info", {}).get("energy")
    if stored is not None:
        return float(stored)
    where = f"image {index}" if index is not None else "an image"
    raise ValueError(
        f"no stored energy for {where}; attach a calculator with an energy "
        "result or set atoms.info['energy']"
    )


def _neb_energies(chain: Sequence[Any]) -> list[float]:
    """Extract the absolute energies of an NEB chain in band order."""
    if isinstance(chain, (str, bytes, Path)):
        raise TypeError(
            "neb_energy_profile expects a sequence of ASE Atoms, not a path; "
            "use the CLI --chain flag for file input or the sella/ccqn helpers "
            "for trajectory files"
        )
    chain = list(chain)
    if not chain:
        raise ValueError("NEB chain must contain at least one image")
    return [_image_energy(atoms, index=index) for index, atoms in enumerate(chain)]


def _trajectory_frames(traj: Any) -> list[Any]:
    """Resolve a trajectory path, object, or frame sequence to frame list."""
    if isinstance(traj, (str, Path)):
        frames = list(ase.io.Trajectory(traj))
    else:
        frames = list(traj)
    if not frames:
        raise ValueError("trajectory contains no frames")
    return frames


def _trajectory_energies(traj: Any) -> list[float]:
    """Extract per-step energies from a Sella/CCQN trajectory in step order."""
    return [
        _image_energy(atoms, index=index)
        for index, atoms in enumerate(_trajectory_frames(traj))
    ]


def _render(
    x: Sequence[float],
    y: Sequence[float],
    output_png: str | Path,
    *,
    title: str | None,
    xlabel: str,
    ylabel: str,
    dpi: int,
    marker_style: str,
    annotate: Any = None,
) -> Path:
    """Render one energy curve and write it as a PNG, returning the path."""
    output = Path(output_png)
    output.parent.mkdir(parents=True, exist_ok=True)
    plt = _pyplot()
    figure, axes = plt.subplots()
    axes.plot(x, y, marker_style)
    axes.set_xlabel(xlabel)
    axes.set_ylabel(ylabel)
    if title is not None:
        axes.set_title(title)
    if annotate is not None:
        annotate(axes)
    figure.savefig(output, dpi=dpi, bbox_inches="tight")
    plt.close(figure)
    return output


def neb_energy_profile(
    chain: Sequence[Any],
    output_png: str | Path,
    *,
    title: str | None = None,
    barrier: bool = True,
    dpi: int = 300,
) -> Path:
    """Render the NEB/AutoNEB energy profile (E vs image) as a PNG.

    The plotted curve is the image energy relative to the first image; when
    ``barrier`` is true the highest relative-energy image is annotated with an
    arrow and its barrier value.  Energies are read from frozen calculator
    results (or ``atoms.info["energy"]``), never by launching new calculations.

    Args:
        chain: NEB band images as ASE ``Atoms`` in band order.
        output_png: Destination PNG path; parent directories are created.
        title: Optional plot title; defaults to a workflow-appropriate label.
        barrier: Annotate the maximum relative-energy image (default True).
        dpi: Saved PNG resolution in dots per inch.

    Returns:
        The written PNG path.

    Raises:
        TypeError: If ``chain`` is a path rather than an Atoms sequence.
        ValueError: If an image carries no stored energy.
        ImportError: If matplotlib is not installed.
    """
    energies = _neb_energies(chain)
    reference = energies[0]
    relative = [float(energy) - reference for energy in energies]

    def _annotate_barrier(axes: Any) -> None:
        """Mark the maximum relative-energy image when requested."""
        if not barrier or not relative:
            return
        peak = float(np.max(relative))
        peak_index = int(np.argmax(relative))
        span = float(np.max(relative) - np.min(relative))
        offset = 0.1 * (span if span > 0 else abs(peak) if peak else 1.0)
        axes.annotate(
            f"E_barrier = {peak:.3f} eV",
            xy=(peak_index, peak),
            xytext=(peak_index, peak + offset),
            arrowprops=dict(arrowstyle="->"),
        )

    return _render(
        list(range(len(relative))),
        relative,
        output_png,
        title=title if title is not None else "Energy profile along the reaction path",
        xlabel="NEB image index",
        ylabel="Relative energy (eV)",
        dpi=dpi,
        marker_style="o-",
        annotate=_annotate_barrier,
    )


def sella_energy_curve(
    traj: str | Path | Sequence[Any],
    output_png: str | Path,
    *,
    title: str | None = None,
    dpi: int = 300,
) -> Path:
    """Render a Sella E-vs-step convergence curve from its trajectory as a PNG.

    Each trajectory frame corresponds to one optimizer step; frame energies are
    read from frozen calculator results (or ``atoms.info["energy"]``).

    Args:
        traj: Sella trajectory path, ``Trajectory`` object, or frame sequence.
        output_png: Destination PNG path; parent directories are created.
        title: Optional plot title; defaults to a Sella-specific label.
        dpi: Saved PNG resolution in dots per inch.

    Returns:
        The written PNG path.

    Raises:
        ValueError: If the trajectory is empty or a frame has no stored energy.
        ImportError: If matplotlib is not installed.
    """
    frames = _trajectory_frames(traj)
    energies = [_image_energy(atoms, index=index) for index, atoms in enumerate(frames)]
    return _render(
        list(range(len(frames))),
        energies,
        output_png,
        title=title if title is not None else "Sella convergence (E vs step)",
        xlabel="Step",
        ylabel="Energy (eV)",
        dpi=dpi,
        marker_style="-",
    )


def ccqn_energy_curve(
    traj: str | Path | Sequence[Any],
    output_png: str | Path,
    *,
    title: str | None = None,
    dpi: int = 300,
) -> Path:
    """Render a CCQN E-vs-step convergence curve from its trajectory as a PNG.

    Each trajectory frame corresponds to one optimizer step; frame energies are
    read from frozen calculator results (or ``atoms.info["energy"]``).

    Args:
        traj: CCQN trajectory path, ``Trajectory`` object, or frame sequence.
        output_png: Destination PNG path; parent directories are created.
        title: Optional plot title; defaults to a CCQN-specific label.
        dpi: Saved PNG resolution in dots per inch.

    Returns:
        The written PNG path.

    Raises:
        ValueError: If the trajectory is empty or a frame has no stored energy.
        ImportError: If matplotlib is not installed.
    """
    frames = _trajectory_frames(traj)
    energies = [_image_energy(atoms, index=index) for index, atoms in enumerate(frames)]
    return _render(
        list(range(len(frames))),
        energies,
        output_png,
        title=title if title is not None else "CCQN convergence (E vs step)",
        xlabel="Step",
        ylabel="Energy (eV)",
        dpi=dpi,
        marker_style="-",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for ``python -m atst_tools.utils.plot``.

    The subcommands and flags mirror the Python API parameters one-to-one:
    ``--chain``/``--traj`` select the input, ``--output-png``, ``--title``,
    ``--dpi``, and ``--no-barrier`` map onto the same function arguments.
    """
    parser = argparse.ArgumentParser(
        prog="python -m atst_tools.utils.plot",
        description=(
            "Render transition-state energy plots: NEB/AutoNEB energy profile "
            "(E vs image) and Sella/CCQN convergence curves (E vs step)."
        ),
    )
    subparsers = parser.add_subparsers(
        dest="kind", required=True, metavar="{neb,sella,ccqn}"
    )

    neb = subparsers.add_parser("neb", help="NEB/AutoNEB energy profile (E vs image)")
    neb.add_argument(
        "--chain",
        required=True,
        help="frame file whose frames are the band images in order",
    )
    neb.add_argument(
        "--output-png",
        default="neb_energy_profile.png",
        help="output PNG path (default: %(default)s)",
    )
    neb.add_argument("--title", default=None, help="optional plot title")
    neb.add_argument(
        "--dpi", type=int, default=300, help="PNG resolution (default: %(default)s)"
    )
    neb.add_argument(
        "--no-barrier",
        action="store_false",
        dest="barrier",
        help="omit the barrier annotation",
    )

    for kind, help_text, default_output in (
        ("sella", "Sella convergence curve (E vs step)", "sella_energy_curve.png"),
        ("ccqn", "CCQN convergence curve (E vs step)", "ccqn_energy_curve.png"),
    ):
        subparser = subparsers.add_parser(kind, help=help_text)
        subparser.add_argument(
            "--traj", required=True, help="Sella/CCQN trajectory file"
        )
        subparser.add_argument(
            "--output-png",
            default=default_output,
            help="output PNG path (default: %(default)s)",
        )
        subparser.add_argument("--title", default=None, help="optional plot title")
        subparser.add_argument(
            "--dpi", type=int, default=300, help="PNG resolution (default: %(default)s)"
        )
    return parser


def _run_from_args(args: argparse.Namespace) -> Path:
    """Dispatch parsed CLI arguments to the shared plotting functions."""
    output = Path(args.output_png)
    if args.kind == "neb":
        chain = ase.io.read(args.chain, index=":")
        if isinstance(chain, ase.Atoms):
            chain = [chain]
        return neb_energy_profile(
            chain,
            output,
            title=args.title,
            barrier=getattr(args, "barrier", True),
            dpi=args.dpi,
        )
    if args.kind == "sella":
        return sella_energy_curve(args.traj, output, title=args.title, dpi=args.dpi)
    return ccqn_energy_curve(args.traj, output, title=args.title, dpi=args.dpi)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one plotting command and return a stable process exit code."""
    args = build_parser().parse_args(argv)
    try:
        output = _run_from_args(args)
    except ImportError as exc:
        print(f"plot error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError) as exc:
        print(f"plot error: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through module execution.
    raise SystemExit(main())
