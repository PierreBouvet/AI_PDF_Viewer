import pytest
import os
import tempfile
from PySide6.QtGui import QColor
from backend.prompts_manager import PromptsManager
from ui.config_dialog import ConfigDialog
from ui.annotation_toolbar import FloatingAnnotationBar

def test_prompts_manager_custom_path(tmp_path):
    csv_file = str(tmp_path / "custom_prompts.csv")
    pm = PromptsManager(file_path=csv_file)
    
    # Initial load should seed default
    prompts = pm.load_prompts()
    assert "Bullet summary" in prompts
    assert os.path.exists(csv_file)
    
    # Save custom prompt
    prompts["Test Prompt"] = "This is a test prompt content"
    pm.save_prompts(prompts)
    
    pm2 = PromptsManager(file_path=csv_file)
    reloaded = pm2.load_prompts()
    assert "Test Prompt" in reloaded
    assert reloaded["Test Prompt"] == "This is a test prompt content"

def test_config_dialog_accept_without_api_key(qtbot):
    dialog = ConfigDialog(current_api_key="")
    qtbot.addWidget(dialog)
    
    dialog.key_input.setText("")
    dialog.style_combo.setCurrentText("Minimalist")
    dialog.mode_combo.setCurrentText("Dark")
    
    # accept() should complete without throwing a warning popup block
    dialog.accept()
    
    assert dialog.config.app_style == "Minimalist"
    assert dialog.config.color_mode == "Dark"
    assert dialog.api_key == ""

def test_floating_annotation_bar_theme(qtbot):
    bar = FloatingAnnotationBar()
    qtbot.addWidget(bar)
    
    # Light theme
    bar.update_theme("Native macOS", "Light")
    assert not bar.is_dark
    assert bar.bg_color == QColor(255, 255, 255)
    
    # Dark theme
    bar.update_theme("Native macOS", "Dark")
    assert bar.is_dark
    assert bar.bg_color == QColor("#242426")
