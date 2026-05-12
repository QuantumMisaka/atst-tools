"""DeepMD-kit ASE calculator adapter."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Hashable

from ase.calculators.calculator import Calculator


def is_dp_calculator(name: str) -> bool:
    """Return whether a calculator name refers to the DeepMD-kit adapter."""
    return name.lower() in {"dp", "deepmd"}


def dp_section(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return DeepMD-kit settings from supported config layouts."""
    calculator = config.get("calculator", {})
    if isinstance(calculator, dict):
        if "dp" in calculator:
            return dict(calculator.get("dp") or {})
        if calculator.get("name") == "deepmd":
            return dict(calculator.get("deepmd") or {})
    if "parameters" in config:
        return dict(config["parameters"])
    return {}


def dp_share_calculator(config: Dict[str, Any], default: bool = True) -> bool:
    """Return the configured DP calculator sharing policy."""
    return bool(dp_section(config).get("share_calculator", default))


def should_share_calculator(name: str, config: Dict[str, Any], parallel: bool = False) -> bool:
    """Return whether workflow images should share a single calculator instance."""
    return is_dp_calculator(name) and not parallel and dp_share_calculator(config)


def _normalize_type_dict(dp_params: Dict[str, Any]) -> dict[str, int] | None:
    type_map = dp_params.pop("type_map", None)
    type_dict = dp_params.pop("type_dict", None)
    if type_map is not None and type_dict is not None:
        raise ValueError("calculator.dp.type_map and calculator.dp.type_dict are mutually exclusive")
    if type_dict is not None:
        return {str(symbol): int(index) for symbol, index in dict(type_dict).items()}
    if type_map is None:
        return None
    return {str(symbol): index for index, symbol in enumerate(type_map)}


def _cache_key(model: str, params: Dict[str, Any]) -> tuple[Hashable, ...]:
    serializable = json.dumps(params, sort_keys=True, default=str)
    return (os.path.abspath(os.path.expanduser(model)), serializable)


class DeepPotentialFactory:
    """Factory for creating DeepMD-kit ASE calculators with optional sharing."""

    _instances: Dict[tuple[Hashable, ...], Calculator] = {}

    @staticmethod
    def get_calculator(
        config: Dict[str, Any],
        shared: bool | None = None,
        **kwargs: Any,
    ) -> Calculator:
        """Create a DeepMD-kit ASE calculator.

        Args:
            config: ATST-Tools configuration dictionary.
            shared: Override the configured calculator sharing policy.
            **kwargs: Workflow-local calculator construction hints.

        Returns:
            Configured ``deepmd.calculator.DP`` instance.
        """
        try:
            from deepmd.calculator import DP
        except ImportError as exc:
            raise ImportError(
                "deepmd-kit is not installed. Install it to use the DP calculator."
            ) from exc

        dp_params = dp_section(config)
        dp_params.update(kwargs)

        model_file = dp_params.pop("model", None)
        if not model_file:
            raise ValueError("Missing required field calculator.dp.model")

        omp = dp_params.pop("omp", None)
        if omp is not None:
            os.environ["OMP_NUM_THREADS"] = str(int(omp))

        share = dp_share_calculator(config) if shared is None else bool(shared)
        dp_params.pop("share_calculator", None)
        dp_params.pop("directory", None)

        type_dict = _normalize_type_dict(dp_params)
        constructor_params: Dict[str, Any] = dict(dp_params)
        if type_dict is not None:
            constructor_params["type_dict"] = type_dict

        key = _cache_key(model_file, constructor_params)
        if share and key in DeepPotentialFactory._instances:
            return DeepPotentialFactory._instances[key]

        calc = DP(model=model_file, **constructor_params)
        if share:
            DeepPotentialFactory._instances[key] = calc
        return calc
