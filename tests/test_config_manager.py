import pytest
from PySide6.QtCore import QSettings
from backend.config_manager import ConfigManager

@pytest.fixture(autouse=True)
def clean_settings():
    # Setup: Use a test organization/application to avoid messing with real settings
    settings = QSettings("AIPDFViewer_Test", "Settings_Test")
    settings.clear()
    
    # Temporarily override the QSettings object in the singleton
    # Note: Because it's a singleton, we have to force re-init or patch its settings
    ConfigManager._instance = None
    config = ConfigManager()
    config.settings = settings
    
    yield config
    
    settings.clear()

def test_singleton_instance(clean_settings):
    config1 = ConfigManager()
    config2 = ConfigManager()
    assert config1 is config2

def test_model_name_default(clean_settings):
    assert clean_settings.model_name == "gemini-3.5-flash"

def test_model_name_setter(clean_settings):
    clean_settings.model_name = "gemini-2.5-pro"
    assert clean_settings.model_name == "gemini-2.5-pro"

def test_ai_font_family_default(clean_settings):
    assert clean_settings.ai_font_family == "Optima"

def test_ai_font_family_setter(clean_settings):
    clean_settings.ai_font_family = "Arial"
    assert clean_settings.ai_font_family == "Arial"

def test_ai_font_size_default(clean_settings):
    assert clean_settings.ai_font_size == 11

def test_ai_font_size_setter(clean_settings):
    clean_settings.ai_font_size = 14
    assert clean_settings.ai_font_size == 14
