# ATST-Tools configuration loader
# part of ATST-Tools

import yaml
from pathlib import Path
from typing import Dict, Any

class ConfigLoader:
    """Load configuration from YAML file"""
    
    @staticmethod
    def load(config_file: str) -> Dict[str, Any]:
        """Load YAML configuration file"""
        if not Path(config_file).exists():
            raise FileNotFoundError(f"Configuration file {config_file} not found")
            
        with open(config_file, 'r') as f:
            # Use safe_load to avoid arbitrary code execution
            # but we need to ensure we can parse scientific notation if any
            # ruamel.yaml is recommended but standard PyYAML is also fine for basic types
            try:
                from ruamel.yaml import YAML
                yaml = YAML(typ='safe', pure=True)
                config = yaml.load(f)
            except ImportError:
                import yaml
                config = yaml.safe_load(f)
                
        return config

    @staticmethod
    def validate(config: Dict[str, Any]):
        """Validate configuration structure (Basic check)"""
        required_sections = ['calculation', 'abacus']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required section '{section}' in configuration")
                
        # Validate calculation type
        calc_type = config['calculation'].get('type')
        if calc_type not in ['neb', 'autoneb', 'dimer', 'sella', 'd2s']:
            raise ValueError(f"Unsupported calculation type: {calc_type}")

        return True
