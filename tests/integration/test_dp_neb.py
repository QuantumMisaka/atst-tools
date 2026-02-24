
import pytest
from ase import Atoms
from ase.build import bulk
from atst_tools.calculators.factory import CalculatorFactory
try:
    from deepmd.calculator import DP
    HAS_DP = True
except ImportError:
    HAS_DP = False

@pytest.mark.skipif(not HAS_DP, reason="DeepMD-kit not installed")
def test_dp_factory_shared_instance():
    """Test that DeepPotentialFactory correctly shares instances."""
    
    config = {
        'calculator': {
            'dp': {
                'model': 'frozen_model.pb'
            }
        }
    }
    
    # Mock DP to avoid actual model loading (which requires a file)
    # Since we can't easily mock imports inside the factory without patching,
    # we will rely on the fact that the factory imports DP inside the method.
    # However, for this integration test, we might want to actually load a dummy model if possible.
    # Or we can just check if the logic works by patching DP.
    
    # For now, let's create a dummy file to bypass file existence check if any
    with open('frozen_model.pb', 'w') as f:
        f.write('dummy')
        
    try:
        # We need to mock deepmd.calculator.DP because loading a dummy file will fail
        import sys
        from unittest.mock import MagicMock
        
        # Mocking the DP class
        mock_dp = MagicMock()
        sys.modules['deepmd.calculator'] = MagicMock()
        sys.modules['deepmd.calculator'].DP = mock_dp
        
        # 1. Test Shared (Default)
        calc1 = CalculatorFactory.get_calculator('dp', config, shared=True)
        calc2 = CalculatorFactory.get_calculator('dp', config, shared=True)
        
        assert calc1 is calc2, "Calculator instances should be shared when shared=True"
        
        # 2. Test Not Shared
        calc3 = CalculatorFactory.get_calculator('dp', config, shared=False)
        assert calc1 is not calc3, "Calculator instances should NOT be shared when shared=False"
        
    finally:
        import os
        if os.path.exists('frozen_model.pb'):
            os.remove('frozen_model.pb')

if __name__ == "__main__":
    pytest.main([__file__])
