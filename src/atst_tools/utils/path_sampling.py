"""Allocate a fixed image budget according to MIC segment lengths."""

from numbers import Integral
from typing import Sequence

import numpy as np
from ase import Atoms
from ase.geometry import find_mic

from atst_tools.utils.geometry import prepare_fixed_cell_images


def segment_mic_lengths(anchors: Sequence[Atoms]) -> np.ndarray:
    """Measure configuration-space MIC chord lengths between path anchors.

    Each segment length is the Euclidean norm of all per-atom MIC displacement
    components together. It is an endpoint chord estimate, not the arc length
    of a subsequently relaxed path. Atomic indices must already correspond.
    Boundaries follow the same reference-cell preparation as interpolation.

    Args:
        anchors: Ordered endpoint and optional intermediate anchor structures.

    Returns:
        One non-negative length per consecutive anchor pair, in Angstrom.
        Fewer than two anchors give an empty array.

    Raises:
        ValueError: If geometry is invalid or atom identities do not match.
    """
    if len(anchors) < 2:
        return np.empty(0, dtype=float)
    prepared = prepare_fixed_cell_images(anchors, context="Path sampling")
    reference = prepared[0]
    for index, atoms in enumerate(prepared[1:], start=1):
        if not np.array_equal(atoms.numbers, reference.numbers):
            raise ValueError(f"Path sampling anchor {index + 1} has inconsistent atom identities")
    lengths = []
    for start, end in zip(prepared[:-1], prepared[1:]):
        delta = end.positions - start.positions
        if np.any(reference.pbc):
            delta = find_mic(delta, reference.cell, reference.pbc)[0]
        lengths.append(float(np.linalg.norm(delta)))
    return np.asarray(lengths)


def allocate_segment_images(anchors: Sequence[Atoms], n_images: int) -> tuple[int, ...]:
    """Apportion additional interior images by segment MIC chord lengths.

    Spacing depends on interval counts: a segment with ``n`` extra interior
    images has ``n + 1`` intervals. Continuous interval quotas are proportional
    to chord lengths, subject to lower bounds; largest remainders round them
    while conserving the requested image budget. Equal remainders favor later
    segments, preserving the historical right-side remainder for two equal
    segments. When the budget permits, each nonzero segment gets at least one
    interior image. Zero-length segments get none unless every segment has
    zero length, in which case allocation falls back to equal interval quotas.

    Args:
        anchors: Ordered structures including every retained path anchor.
        n_images: Total additional interior images across all segments. The
            supplied internal anchors are retained in addition to this budget.

    Returns:
        One interior-image count per segment, summing exactly to ``n_images``.
        No segments and a zero budget give an empty tuple.

    Raises:
        ValueError: If the budget is invalid, no segment can receive a nonzero
            budget, or anchor geometry/identity is invalid.
    """
    if isinstance(n_images, bool) or not isinstance(n_images, Integral) or n_images < 0:
        raise ValueError("n_images must be a non-negative integer")
    n_images = int(n_images)
    lengths = segment_mic_lengths(anchors)
    count = len(lengths)
    if count == 0:
        if n_images:
            raise ValueError("Path sampling requires at least two anchors for a nonzero image budget")
        return ()
    if n_images == 0:
        return (0,) * count

    # MIC can leave roundoff after translating an identical anchor by a cell.
    active = lengths > 1e-12
    if not np.any(active):
        lengths = np.ones(count)
        active = np.ones(count, dtype=bool)
    lower = np.ones(count, dtype=int)
    if n_images >= int(active.sum()):
        lower[active] = 2
    intervals = lower.astype(float)
    free = active.copy()
    total_intervals = n_images + count
    # Pin short segments at their lower bound, then redistribute the remaining
    # interval quota over unpinned lengths. Zero-length segments stay at one.
    while np.any(free):
        scale = (total_intervals - intervals[~free].sum()) / lengths[free].sum()
        candidates = scale * lengths
        pinned = free & (candidates < lower)
        if not np.any(pinned):
            intervals[free] = candidates[free]
            break
        intervals[pinned] = lower[pinned]
        free[pinned] = False

    rounded = np.floor(intervals).astype(int)
    remainder = total_intervals - int(rounded.sum())
    fractions = intervals - rounded
    # lexsort's final key is primary: largest fractional quota, latest tie.
    order = np.lexsort((-np.arange(count), -fractions))
    rounded[order[:remainder]] += 1
    return tuple(int(value - 1) for value in rounded)
