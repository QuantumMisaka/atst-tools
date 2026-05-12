"""Configuration loading and validation for ATST-Tools."""

from pathlib import Path
from typing import Dict, Any

from atst_tools.utils.config_schema import (
    VALID_CALCULATION_TYPES,
    VALID_CALCULATORS,
    normalize_config,
    parse_config,
)


class ConfigLoader:
    """
    Load and validate configuration from YAML files.
    """
    
    @staticmethod
    def load(config_file: str) -> Dict[str, Any]:
        """
        Load YAML configuration file.

        Args:
            config_file (str): Path to the YAML configuration file.

        Returns:
            dict: Parsed configuration dictionary.

        Raises:
            FileNotFoundError: If the config file does not exist.
        """
        path = Path(config_file)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file {config_file} not found")
            
        with open(config_file, 'r') as f:
            # Use safe_load to avoid arbitrary code execution
            # Prefer ruamel.yaml for better parsing, fallback to PyYAML
            try:
                from ruamel.yaml import YAML
                from ruamel.yaml.error import YAMLError

                yaml_loader = YAML(typ='safe', pure=True)
                try:
                    config = yaml_loader.load(f)
                except YAMLError as exc:
                    raise ValueError(f"Failed to parse YAML configuration {config_file}: {exc}") from exc
            except ImportError:
                import yaml
                try:
                    config = yaml.safe_load(f)
                except yaml.YAMLError as exc:
                    raise ValueError(f"Failed to parse YAML configuration {config_file}: {exc}") from exc
                
        return config

    @staticmethod
    def normalize(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a configuration and populate schema defaults.

        Args:
            config (dict): Raw configuration dictionary.

        Returns:
            dict: Normalized configuration dictionary with default values.

        Raises:
            ValueError: If validation fails.
        """
        return normalize_config(config)

    @staticmethod
    def validate(config: Dict[str, Any]) -> bool:
        """
        Validate configuration structure and values.

        Args:
            config (dict): Configuration dictionary to validate.

        Returns:
            bool: True if validation passes.

        Raises:
            ValueError: If validation fails (missing sections or invalid types).
        """
        parse_config(config)
        return True
