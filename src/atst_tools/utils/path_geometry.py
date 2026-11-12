"""Shared MIC contact facts and conservative geometry checks for paths."""

from typing import Any

import numpy as np
from ase.data import covalent_radii


def path_contact_facts(frames) -> dict[str, Any]:
    """Return the tightest interatomic contact facts of an interpolated path.

    Every atom pair is graded against its own endpoints: the smallest distance
    that pair reaches on any frame is compared with the smaller of the two
    endpoint distances for that same pair.  A pair driven far below both
    endpoints can flag a collapsed interpolation. This ratio is a diagnostic
    rather than a rejection rule: a reaction can also shorten or form a bond.

    The reference is deliberately per pair: a global endpoint minimum would be
    dominated by the tightest bond of the system (for example a 1 Ang X-H bond)
    and could hide a collapsed metal-metal contact.

    Distances use the minimum image convention whenever the frames are periodic.

    Args:
        frames: Path frames, including both endpoints.

    Returns:
        Mapping with ``min_distance_A``, ``min_distance_pair`` (0-based),
        ``min_distance_ratio``, ``ratio_pair`` (0-based) and
        ``ratio_reference_A``, plus the corresponding frame indices and the
        smallest distance divided by the pair's summed ASE covalent radii.
        All frame and pair indices are 0-based. Empty when fewer than two
        frames are provided or there is no atom pair.
    """
    if len(frames) < 2:
        return {}
    return _measure_contact_facts(frames)


def _measure_contact_facts(frames) -> dict[str, Any]:
    """Measure contacts, including a single frame for geometry validation."""
    if not frames or len(frames[0]) < 2:
        return {}
    natoms = len(frames[0])
    use_mic = bool(np.any(frames[0].get_pbc()))
    pair_mask = ~np.eye(natoms, dtype=bool)
    start_distances = frames[0].get_all_distances(mic=use_mic)
    end_distances = frames[-1].get_all_distances(mic=use_mic)
    reference = np.minimum(start_distances, end_distances)
    measured = pair_mask & (reference > 0.0)
    safe_reference = np.where(measured, reference, 1.0)

    min_distance = np.inf
    min_pair = (0, 0)
    worst_ratio = np.inf
    worst_pair = (0, 0)
    worst_reference = np.inf
    min_image = 0
    ratio_image = 0
    min_covalent_ratio = np.inf
    covalent_pair = (0, 0)
    covalent_image = 0
    radii = covalent_radii[frames[0].numbers]
    radii_sum = radii[:, None] + radii[None, :]
    for index, frame in enumerate(frames):
        if index == 0:
            distances = start_distances
        elif index == len(frames) - 1:
            distances = end_distances
        else:
            distances = frame.get_all_distances(mic=use_mic)
        masked = np.where(pair_mask, distances, np.inf)
        row, column = np.unravel_index(int(np.argmin(masked)), masked.shape)
        if masked[row, column] < min_distance:
            min_distance = float(masked[row, column])
            min_pair = (int(row), int(column))
            min_image = index
        ratios = np.where(measured, distances / safe_reference, np.inf)
        row, column = np.unravel_index(int(np.argmin(ratios)), ratios.shape)
        if ratios[row, column] < worst_ratio:
            worst_ratio = float(ratios[row, column])
            worst_pair = (int(row), int(column))
            worst_reference = float(reference[row, column])
            ratio_image = index
        covalent_ratios = np.where(pair_mask, distances / radii_sum, np.inf)
        row, column = np.unravel_index(int(np.argmin(covalent_ratios)), covalent_ratios.shape)
        if covalent_ratios[row, column] < min_covalent_ratio:
            min_covalent_ratio = float(covalent_ratios[row, column])
            covalent_pair = (int(row), int(column))
            covalent_image = index

    return {
        "min_distance_A": min_distance,
        "min_distance_pair": min_pair,
        "min_distance_ratio": worst_ratio,
        "ratio_pair": worst_pair,
        "ratio_reference_A": worst_reference,
        "min_distance_image": min_image,
        "ratio_image": ratio_image,
        "min_covalent_ratio": min_covalent_ratio,
        "covalent_pair": covalent_pair,
        "covalent_image": covalent_image,
    }


def validate_path_geometry(frames, *, context: str = "Generated path") -> dict[str, Any]:
    """Reject non-finite geometry and severe atomic contacts before consumption.

    A contact below half the sum of ASE covalent radii is treated as a severe
    overlap. This conservative, element-dependent heuristic is not a bond
    validity test or proof that a path is physically meaningful. In particular,
    no rejection is based on a universal 1 Ang cutoff or endpoint-distance
    ratio, so ordinary short bonds and bond formation remain permitted.

    Args:
        frames: Path frames, including endpoints.
        context: Operation name included in errors.

    Returns:
        Contact measurements, including a single frame. Unlike the public
        path summary, validation does not skip single-frame contacts.

    Raises:
        ValueError: If a frame is non-finite or contains a severe overlap.
    """
    for index, frame in enumerate(frames):
        if not np.isfinite(frame.positions).all():
            raise ValueError(f"{context}: non-finite positions in image {index + 1}")
        if not np.isfinite(frame.cell.array).all():
            raise ValueError(f"{context}: non-finite cell in image {index + 1}")
    # A lone frame has no path-summary semantics but still requires collision
    # validation; keep that separate from the public summary's empty result.
    facts = _measure_contact_facts(frames)
    if facts and facts["min_covalent_ratio"] < 0.5:
        image = facts["covalent_image"]
        row, column = facts["covalent_pair"]
        frame = frames[image]
        distance = frame.get_distance(row, column, mic=bool(np.any(frame.pbc)))
        symbols = frame.get_chemical_symbols()
        threshold = 0.5 * (covalent_radii[frame.numbers[row]] + covalent_radii[frame.numbers[column]])
        raise ValueError(
            f"{context}: severe atomic overlap in image {image + 1}: "
            f"{symbols[row]}{row + 1}-{symbols[column]}{column + 1}, "
            f"MIC distance {distance:.3f} Ang < {threshold:.3f} Ang "
            "(half the summed covalent radii). Check endpoint atom mapping "
            "and rebuild the interpolation path."
        )
    return facts
