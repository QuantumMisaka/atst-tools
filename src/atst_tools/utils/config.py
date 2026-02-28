# ATST-Tools configuration loader
# part of ATST-Tools

import yaml
from pathlib import Path
from typing import Dict, Any

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
        # 1. Check for required calculation section
        if 'calculation' not in config:
            raise ValueError("Missing required section 'calculation' in configuration")
            
        # 2. Check for calculator configuration (either 'abacus' or 'calculator' section)
        if 'abacus' not in config and 'calculator' not in config:
            # Check if calculation type is 'd2s' which might have its own params handling?
            # But generally we need a calculator definition.
            raise ValueError("Missing calculator configuration (either 'abacus' or 'calculator' section)")
                
        # 3. Validate calculation type
        calc_type = config['calculation'].get('type')
        valid_types = ['neb', 'autoneb', 'dimer', 'sella', 'd2s', 'relax', 'vibration']
        
        if calc_type not in valid_types:
            raise ValueError(f"Unsupported calculation type: {calc_type}. Supported: {valid_types}")

        return True
