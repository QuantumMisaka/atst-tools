"""Git-style command line interface for ATST-Tools.

This module is the import-light console entry point (``atst``).  It decides
between the isolated, device-bound worker launch and the legacy in-process
implementation, then delegates to :mod:`atst_tools.scripts.cli_impl`.

The legacy surface (parsers, helpers and heavy imports) lives in the
implementation module and is reached through :func:`__getattr__` so existing
callers and tests keep working without paying the import cost here.
"""

from __future__ import annotations

import importlib
from typing import Any

_IMPLEMENTATION = "atst_tools.scripts.cli_impl"


def main(argv=None):
    """Run the ``atst`` CLI, using the isolated runtime path when requested."""
    import sys

    from atst_tools.runtime.cli_dispatch import plan_runtime_launch
    from atst_tools.runtime.errors import RuntimeBindingError, RuntimeConfigError

    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        plan = plan_runtime_launch(arguments)
    except RuntimeConfigError as exc:
        raise ValueError(str(exc)) from None
    except RuntimeBindingError as exc:
        raise SystemExit(str(exc)) from None
    if plan is not None:  # pragma: no cover - replaces the process image
        plan.execute()
        return 0
    return importlib.import_module(_IMPLEMENTATION).main(arguments)


def __getattr__(name: str) -> Any:
    """Forward legacy attribute access to the implementation module."""
    value = getattr(importlib.import_module(_IMPLEMENTATION), name)
    globals()[name] = value
    return value


if __name__ == "__main__":  # pragma: no cover - module execution entry
    raise SystemExit(main())
