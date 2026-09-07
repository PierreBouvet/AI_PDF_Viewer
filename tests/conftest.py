import pytest
from PySide6.QtCore import QSettings
from backend.config_manager import ConfigManager

@pytest.fixture(autouse=True)
def isolated_test_settings():
    """Ensure every test runs with clean, isolated settings default to cloud provider."""
    test_settings = QSettings("AIPDFViewer_TestEnv", "UnitTestSettings")
    test_settings.clear()
    
    ConfigManager.reset()
    config = ConfigManager()
    config.settings = test_settings
    
    # Defaults
    config.ai_provider = "cloud"
    config.local_endpoint_url = "http://localhost:11434/v1"
    config.local_model_name = "mistral-nemo:latest"
    
    yield config
    
    test_settings.clear()
    ConfigManager.reset()
