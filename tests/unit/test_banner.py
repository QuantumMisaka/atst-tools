"""Tests for the ATST-Tools project banner."""

from atst_tools.utils.banner import ATST_ASCII, BANNER_CREDITS, render_banner


def test_render_banner_contains_ascii_atst_and_contributor_credits():
    """The banner should include the ATST art and governed credit lines."""
    banner = render_banner()

    assert ATST_ASCII in banner
    assert BANNER_CREDITS in banner
    assert "Core developer: @QuantumMisaka" in banner
    assert "Contributors: @Jerry, @MoseyQAQ, and the ATST-Tools contributors" in banner
    assert banner.endswith("\n")
