"""Segment sampling respects MIC path lengths and the total image budget."""

import numpy as np
import pytest
from ase import Atoms

from atst_tools.utils.path_sampling import allocate_segment_images, segment_mic_lengths


def _anchors(*x):
    return [Atoms("H", positions=[[value, 0, 0]]) for value in x]


def test_allocation_weights_intervals_rather_than_only_interiors():
    # Nine intervals (seven added images plus two anchor segments), length 1:3.
    assert allocate_segment_images(_anchors(0, 1, 4), 7) == (1, 6)
    assert allocate_segment_images(_anchors(0, 1, 7), 7) == (1, 6)


def test_equal_length_remainder_keeps_legacy_right_segment_tie_order():
    assert allocate_segment_images(_anchors(0, 1, 2), 7) == (3, 4)


@pytest.mark.parametrize("budget", range(10))
def test_budget_conserved_with_minimum_sampling_when_possible(budget):
    anchors = _anchors(0, 0.1, 10, 11)
    allocation = allocate_segment_images(anchors, budget)
    assert sum(allocation) == budget
    assert all(n >= 0 for n in allocation)
    if budget >= 3:
        assert all(n >= 1 for n in allocation)


def test_zero_length_segments_receive_no_images_when_an_edge_moves():
    assert allocate_segment_images(_anchors(0, 0, 2), 7) == (0, 7)
    assert allocate_segment_images(_anchors(0, 2, 2), 7) == (7, 0)
    assert allocate_segment_images(_anchors(0, 0, 0), 7) == (3, 4)
    assert allocate_segment_images(_anchors(0, 0, 0), 0) == (0, 0)


def test_zero_and_one_edge_budgets():
    assert allocate_segment_images(_anchors(0), 0) == ()
    assert allocate_segment_images([], 0) == ()
    assert allocate_segment_images(_anchors(0, 1), 7) == (7,)
    assert allocate_segment_images(_anchors(0, 0), 7) == (7,)
    assert allocate_segment_images(_anchors(0, 1, 10), 0) == (0, 0)
    assert allocate_segment_images(_anchors(0, 1, 10), 1) == (0, 1)
    with pytest.raises(ValueError, match="at least two anchors"):
        allocate_segment_images(_anchors(0), 1)


def test_skew_cell_wrapping_and_partial_pbc_do_not_change_allocation():
    cell = np.array([[8.3575, 0, 0], [4.17875, 7.2378, 0], [0, 0, 20]])
    anchors = [Atoms("H", positions=[[x, 0, 0]], cell=cell, pbc=[1, 1, 0]) for x in (0, 0.25, 1.75)]
    lengths = segment_mic_lengths(anchors)
    np.testing.assert_allclose(lengths, [0.25, 1.5])
    expected = allocate_segment_images(anchors, 7)
    shifted = [a.copy() for a in anchors]
    shifted[1].positions += 3 * cell[0] - 2 * cell[1]
    shifted[2].positions -= cell[0]
    np.testing.assert_allclose(segment_mic_lengths(shifted), lengths)
    assert allocate_segment_images(shifted, 7) == expected
    shifted[2].positions += cell[2]
    assert segment_mic_lengths(shifted)[1] > 20


def test_length_is_configuration_space_norm_over_all_atoms():
    start = Atoms("H2", positions=[[0, 0, 0], [0, 0, 0]])
    end = Atoms("H2", positions=[[3, 0, 0], [0, 4, 0]])
    np.testing.assert_allclose(segment_mic_lengths([start, end]), [5])


@pytest.mark.parametrize("budget", [-1, 1.5, True, "7"])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValueError, match="non-negative integer"):
        allocate_segment_images(_anchors(0, 1), budget)
