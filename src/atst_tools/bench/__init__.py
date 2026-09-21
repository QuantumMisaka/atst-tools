"""Benchmark toolchain for bounded independent-case runs (GPU tuning P3).

This package is a validation and benchmarking orchestration layer: it consumes
a finite case manifest inside one existing allocation, runs each case as an
isolated worker in its own directory, and keeps every attempt's evidence:
``batch_runner`` (the case-list executor), ``sweep`` (variant matrix) and
``record`` (self-describing measurement record).  It
is not a production queue and adds no ``atst batch`` public interface.
"""

from __future__ import annotations

__all__ = ["batch_runner"]
