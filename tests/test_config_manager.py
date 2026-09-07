import pytest
from PySide6.QtCore import QSettings
from backend.config_manager import ConfigManager

@pytest.fixture(autouse=True)
def clean_settings():
    # Setup: Use a test organization/application to avoid messing with real settings
    settings = QSettings("AIPDFViewer_Test", "Settings_Test")
    settings.clear()
    
    # Reset singleton and temporarily override the QSettings object
    ConfigManager.reset()
    config = ConfigManager()
    config.settings = settings
    
    yield config
    
    settings.clear()
    ConfigManager.reset()

def test_singleton_instance(clean_settings):
    config1 = ConfigManager()
    config2 = ConfigManager()
    assert config1 is config2

def test_singleton_reset():
    config1 = ConfigManager()
    ConfigManager.reset()
    config2 = ConfigManager()
    assert config1 is not config2

def test_model_name_default(clean_settings):
    assert clean_settings.model_name == ""

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

def test_app_style_default_and_setter(clean_settings):
    assert clean_settings.app_style == "Native"
    clean_settings.app_style = "Adobe Acrobat"
    assert clean_settings.app_style == "Adobe Acrobat"

def test_color_mode_default_and_setter(clean_settings):
    assert clean_settings.color_mode == "System (Auto)"
    clean_settings.color_mode = "Dark"
    assert clean_settings.color_mode == "Dark"

def test_theme_manager_resolve_mode():
    from ui.theme_manager import ThemeManager
    assert ThemeManager.resolve_color_mode("Light") == "Light"
    assert ThemeManager.resolve_color_mode("Dark") == "Dark"
    assert ThemeManager.resolve_color_mode("System (Auto)") in ["Light", "Dark"]

def test_theme_manager_palettes():
    from ui.theme_manager import ThemeManager
    for style in ["Native", "Adobe Acrobat", "Minimalist"]:
        for mode in ["System (Auto)", "Light", "Dark"]:
            p = ThemeManager.get_palette(style, mode)
            assert "bg_window" in p
            assert "accent" in p
            assert "pdf_bg" in p
            css = ThemeManager.get_stylesheet(style, mode)
            assert len(css) > 50
            chat_css = ThemeManager.get_chat_css(style, mode, "Optima", 11)
            assert len(chat_css) > 50

def test_local_ai_settings(clean_settings):
    assert clean_settings.ai_provider == "cloud"
    assert clean_settings.local_endpoint_url == "http://localhost:11434/v1"
    assert clean_settings.local_model_name == "mistral-nemo:latest"
    assert clean_settings.local_timeout_sec == 300

    clean_settings.ai_provider = "local"
    clean_settings.local_endpoint_url = "http://localhost:8080/v1"
    clean_settings.local_model_name = "mistral-nemo:12b"
    clean_settings.local_timeout_sec = 600

    assert clean_settings.ai_provider == "local"
    assert clean_settings.local_endpoint_url == "http://localhost:8080/v1"
    assert clean_settings.local_model_name == "mistral-nemo:12b"
    assert clean_settings.local_timeout_sec == 600




