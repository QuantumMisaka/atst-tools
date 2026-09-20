"""Error types for the runtime device and process layer."""

from __future__ import annotations

from atst_tools.api.models import ATSTAPIError, ConfigValidationError


class RuntimeConfigError(ConfigValidationError):
    """Raised when a runtime request is syntactically invalid."""


class RuntimeBindingError(ATSTAPIError):
    """Raised when a runtime request cannot be honoured in this process."""
