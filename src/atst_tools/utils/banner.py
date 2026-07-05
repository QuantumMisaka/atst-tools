"""Project banner rendering for ATST-Tools."""

from __future__ import annotations

ATST_ASCII = r"""
    _  _____ ____ _____
   / \|_   _/ ___|_   _|
  / _ \ | | \___ \ | |
 / ___ \| |  ___) || |
/_/   \_\_| |____/ |_|
""".strip("\n")

BANNER_CREDITS = (
    "Core developer: @QuantumMisaka\n"
    "Contributors: @Jerry, @MoseyQAQ, and the ATST-Tools contributors"
)


def render_banner() -> str:
    """Return the ATST project banner.

    Returns:
        ASCII banner text with contributor credits and a trailing newline.
    """
    return f"{ATST_ASCII}\n{BANNER_CREDITS}\n"
