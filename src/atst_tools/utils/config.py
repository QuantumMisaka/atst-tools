"""Configuration loading and validation for ATST-Tools."""

from pathlib import Path
from typing import Dict, Any


VALID_CALCULATION_TYPES = ("neb", "autoneb", "dimer", "sella", "d2s", "relax", "vibration", "irc")
VALID_CALCULATORS = ("abacus", "dp", "deepmd")

_REQUIRED_CALCULATION_FIELDS = {
    "neb": (),
    "autoneb": ("init_chain",),
    "dimer": ("init_structure",),
    "sella": ("init_structure",),
    "d2s": ("init_file", "final_file"),
    "relax": ("init_structure",),
    "vibration": ("init_structure",),
    "irc": ("init_structure",),
}


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
                yaml_loader = YAML(typ='safe', pure=True)
                config = yaml_loader.load(f)
            except ImportError:
                import yaml
                config = yaml.safe_load(f)
                
        return config

    @staticmethod
    def validate(config: Dict[str, Any]) -> bool:
        """
        Validate configuration structure (Basic check).

        Args:
            config (dict): Configuration dictionary to validate.

        Returns:
            bool: True if validation passes.

        Raises:
            ValueError: If validation fails (missing sections or invalid types).
        """
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a YAML mapping")

        # 1. Check for required calculation section
        if 'calculation' not in config:
            raise ValueError("Missing required section 'calculation' in configuration")

        calculation = config['calculation']
        if not isinstance(calculation, dict):
            raise ValueError("'calculation' must be a mapping")

        # 2. Validate calculation type and required workflow inputs.
        calc_type = calculation.get('type')
        if calc_type not in VALID_CALCULATION_TYPES:
            raise ValueError(
                f"Unsupported calculation type: {calc_type}. "
                f"Supported: {list(VALID_CALCULATION_TYPES)}"
            )

        missing_fields = [
            field for field in _REQUIRED_CALCULATION_FIELDS[calc_type]
            if field not in calculation
        ]
        if missing_fields:
            raise ValueError(
                f"Missing required field(s) for calculation.type={calc_type}: "
                f"{', '.join(missing_fields)}"
            )

        if calc_type == "neb":
            has_init_chain = "init_chain" in calculation
            has_make = "make" in calculation
            if has_init_chain == has_make:
                raise ValueError("calculation.type=neb requires exactly one of 'init_chain' or 'make'")
            if has_make and not isinstance(calculation["make"], dict):
                raise ValueError("'calculation.make' must be a mapping")
            if has_make:
                missing_make = [
                    field for field in ("init_structure", "final_structure", "n_images")
                    if field not in calculation["make"]
                ]
                if missing_make:
                    raise ValueError(
                        "Missing required field(s) for calculation.make: "
                        + ", ".join(missing_make)
                    )

        if calc_type == "irc" and calculation.get("direction", "both") not in {"both", "forward", "reverse"}:
            raise ValueError("calculation.direction for irc must be 'both', 'forward', or 'reverse'")

        if calc_type == "vibration" and "thermochemistry" in calculation:
            thermochemistry = calculation["thermochemistry"]
            if not isinstance(thermochemistry, dict):
                raise ValueError("'calculation.thermochemistry' must be a mapping")
            model = thermochemistry.get("model", "harmonic")
            if model not in {"harmonic", "ideal_gas"}:
                raise ValueError("vibration thermochemistry.model must be 'harmonic' or 'ideal_gas'")

        # 3. Validate calculator configuration. The root-level 'abacus' layout is
        # retained only as a migration path; new YAML should use calculator.name.
        if 'calculator' in config:
            calculator = config['calculator']
            if not isinstance(calculator, dict):
                raise ValueError("'calculator' must be a mapping")
            calc_name = calculator.get('name')
            if calc_name not in VALID_CALCULATORS:
                raise ValueError(
                    f"Unsupported calculator name: {calc_name}. "
                    f"Supported: {list(VALID_CALCULATORS)}"
                )
            section = 'dp' if calc_name == 'deepmd' else calc_name
            if section not in calculator:
                raise ValueError(
                    f"Missing calculator.{section} section for calculator.name={calc_name}"
                )
            if not isinstance(calculator[section], dict):
                raise ValueError(f"'calculator.{section}' must be a mapping")
            if section == "dp" and not calculator[section].get("model"):
                raise ValueError("Missing required field calculator.dp.model")
        elif 'abacus' in config:
            if not isinstance(config['abacus'], dict):
                raise ValueError("'abacus' must be a mapping")
        else:
            raise ValueError("Missing calculator configuration. Use 'calculator.name' and a matching section.")

        return True
