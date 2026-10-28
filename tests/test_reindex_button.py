import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from ui.ai_chat_panel import AIChatPanel
from ui.main_window import MainWindow


def test_reindex_button_presence_and_initial_state(qapp):
    panel = AIChatPanel()
    
    assert hasattr(panel, "reindex_btn")
    assert panel.reindex_btn is not None
    assert "Re-index" in panel.reindex_btn.text()
    assert panel.reindex_btn.isEnabled() is True
    assert "Re-index" in panel.reindex_btn.toolTip()
    
    panel.close()


def test_reindex_button_status_transitions(qapp):
    panel = AIChatPanel()

    # 1. Processing state: button is disabled and shows indexing in progress
    panel.set_index_status("processing")
    assert panel.reindex_btn.isEnabled() is False
    assert "Indexing" in panel.reindex_btn.text()

    # 2. Indexed state: button is re-enabled and shows Re-index
    panel.set_index_status("indexed", "gemini-2.5-flash")
    assert panel.reindex_btn.isEnabled() is True
    assert panel.reindex_btn.text() == "🔄 Re-index"
    assert "gemini-2.5-flash" in panel.status_bar.text()

    # 3. Unloaded state: button remains available to trigger indexing
    panel.set_index_status("unloaded")
    assert panel.reindex_btn.isEnabled() is True
    assert panel.reindex_btn.text() == "🔄 Re-index"

    panel.close()


def test_reindex_button_click_emits_index_requested(qapp, qtbot):
    panel = AIChatPanel()
    qtbot.addWidget(panel)

    emitted = []
    panel.index_requested.connect(lambda: emitted.append(True))

    # Clicking should emit index_requested
    panel.reindex_btn.click()
    assert len(emitted) == 1

    # While generating, click should be ignored
    panel.is_generating = True
    panel.reindex_btn.click()
    assert len(emitted) == 1

    panel.is_generating = False
    panel.reindex_btn.click()
    assert len(emitted) == 2

    panel.close()


def test_reindex_button_theme_updates(qapp):
    panel = AIChatPanel()

    # Update to Dark theme
    panel.update_theme(app_style="Native", color_mode="Dark")
    style_dark = panel.reindex_btn.styleSheet()
    assert "#333336" in style_dark or "QPushButton" in style_dark

    # Update to Light theme
    panel.update_theme(app_style="Native", color_mode="Light")
    style_light = panel.reindex_btn.styleSheet()
    assert "#e5e5ea" in style_light or "QPushButton" in style_light

    panel.close()


def test_main_window_reindex_button_triggers_indexing(qapp, isolated_test_settings, tmp_path, qtbot):
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    with patch("keyring.get_password", return_value="fake_api_key"):
        window = MainWindow()
        qtbot.addWidget(window)

        # Mock index_current_document
        window.index_current_document = MagicMock()

        # Click re-index button on chat panel
        window.chat_panel.reindex_btn.click()

        # MainWindow's indexing was triggered via index_requested signal
        window.index_current_document.assert_called_once()

        window.close()
