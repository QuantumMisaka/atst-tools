from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseCalculator(ABC):
    """Abstract base class for ATST calculators."""

    @abstractmethod
    def get_calculator(self, **kwargs) -> Any:
        """Return a configured ASE calculator instance."""
        pass
