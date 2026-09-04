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

def test_chat_web_page_retry_requested(qtbot):
    from ui.ai_chat_panel import ChatWebPage
    from PySide6.QtCore import QUrl
    
    page = ChatWebPage()
    with qtbot.waitSignal(page.retry_requested, timeout=1000) as blocker:
        result = page.acceptNavigationRequest(QUrl("action://retry_last_query"), None, True)
        assert result is False
    assert blocker.signal_triggered

def test_ai_chat_panel_html_template_503_retry():
    from ui.ai_chat_panel import AIChatPanel
    
    # Check that template includes 503 retry option
    panel = AIChatPanel()
    template = panel._get_html_template()
    assert "503" in template
    assert "action://retry_last_query" in template
    assert "retry with the same model" in template

def test_main_window_indexing_error_and_retry(qtbot, monkeypatch):
    import keyring
    from unittest.mock import MagicMock
    monkeypatch.setattr(keyring, "get_password", lambda *args, **kwargs: None)
    from ui.main_window import MainWindow
    
    window = MainWindow()
    qtbot.addWidget(window)
    
    # Simulate index button being hidden during indexing
    window.chat_panel.index_btn.setVisible(False)
    window.chat_panel.set_index_status("processing")
    
    window.chat_panel.add_system_error = MagicMock()
    window.on_indexing_error("503 Service Unavailable")
    window.chat_panel.add_system_error.assert_called_once_with("Indexing failed: 503 Service Unavailable", allow_retry=False)
    
    # Check that status is unloaded and index button is set to visible (not hidden)
    assert window.chat_panel.status_bar.text() == "Status: Not Indexed"
    assert not window.chat_panel.index_btn.isHidden()
    # Check that input fields are hidden (chat does not open)
    assert window.chat_panel.input_field.isHidden()
    
    # Test retry indexing
    window.last_ai_action = ("index", None)
    window.index_current_document = MagicMock()
    window.retry_last_action()
    window.index_current_document.assert_called_once()
    
    # Test retry worker query (mocking WorkerThread to avoid running real network thread)
    mock_worker = MagicMock()
    monkeypatch.setattr("ui.main_window.WorkerThread", lambda *args, **kwargs: mock_worker)
    window.last_ai_action = ("worker", {
        "question": "test question",
        "action_type": "chat",
        "use_direct": True,
        "original_prompt": "test question",
        "display_title": ""
    })
    window.retry_last_action()
    assert window.worker == mock_worker
    mock_worker.start.assert_called_once()
    
    # Test deleted worker thread scenario (simulating libshiboken RuntimeError on deleted C++ object)
    class DeletedThread:
        def isRunning(self):
            raise RuntimeError("libshiboken: Internal C++ object (WorkerThread) already deleted.")
            
    assert window._is_thread_running(DeletedThread()) is False
    window.worker = DeletedThread()
    mock_worker2 = MagicMock()
    monkeypatch.setattr("ui.main_window.WorkerThread", lambda *args, **kwargs: mock_worker2)
    window.retry_last_action()
    assert window.worker == mock_worker2
    mock_worker2.start.assert_called_once()

def test_page_item_load_queued_connection(monkeypatch):
    from unittest.mock import MagicMock
    from PySide6.QtCore import Qt
    from ui.pdf_view import PageItem
    
    mock_view = MagicMock()
    mock_view.devicePixelRatioF.return_value = 1.0
    mock_view.transform.return_value.m11.return_value = 1.0
    mock_view.document = MagicMock()
    
    page_item = PageItem(0, mock_view)
    
    # Mock QThreadPool.globalInstance().start
    monkeypatch.setattr("PySide6.QtCore.QThreadPool.start", lambda self, r: None)
    
    mock_finished = MagicMock()
    class MockSignals:
        def __init__(self):
            self.finished = mock_finished
    monkeypatch.setattr("ui.pdf_view.PageLoaderSignals", MockSignals)
    
    page_item.load()
    mock_finished.connect.assert_called_once_with(mock_view.on_page_image_loaded, Qt.ConnectionType.QueuedConnection)

def test_page_item_image_loaded_scaling(qtbot):
    from unittest.mock import MagicMock
    from ui.pdf_view import PageItem
    from PySide6.QtWidgets import QGraphicsScene
    from PySide6.QtGui import QImage

    scene = QGraphicsScene()
    mock_view = MagicMock()
    page_item = PageItem(0, mock_view)
    page_item.setRect(0, 0, 500, 700)
    scene.addItem(page_item)
    page_item.is_loading = True

    # High-DPI image rendered at 2.0x DPI and 1.0x zoom (1000x1400 physical pixels)
    img = QImage(1000, 1400, QImage.Format_RGB888)
    img.setDevicePixelRatio(2.0)

    page_item.on_image_loaded(0, img, zoom=1.0)

    assert page_item.is_loaded is True
    assert page_item.pixmap_item is not None
    # Scene bounding rect must match page rect (500x700), not miniature 250x350
    assert page_item.pixmap_item.sceneBoundingRect().width() == 500.0
    assert page_item.pixmap_item.sceneBoundingRect().height() == 700.0

def test_page_item_tile_loaded_positioning_and_scale(qtbot):
    from unittest.mock import MagicMock
    from ui.pdf_view import PageItem
    from PySide6.QtWidgets import QGraphicsScene
    from PySide6.QtGui import QImage

    scene = QGraphicsScene()
    mock_view = MagicMock()
    mock_view.transform().m11.return_value = 4.0
    page_item = PageItem(0, mock_view)
    page_item.setRect(0, 0, 500, 700)
    page_item.setPos(0, 100)
    scene.addItem(page_item)

    # Tile clip in page coords: (50, 60, 250, 360) -> width 200, height 300
    clip = (50.0, 60.0, 250.0, 360.0)
    # At zoom 4.0, dpi_scale 2.0 -> actual_zoom = 8.0 -> 200*8 = 1600 px, 300*8 = 2400 px
    tile_img = QImage(1600, 2400, QImage.Format_RGB888)
    tile_img.setDevicePixelRatio(2.0)

    page_item.on_tile_loaded(0, tile_img, zoom=4.0, clip_rect=clip)

    assert page_item.tile_item is not None
    tile_scene_rect = page_item.tile_item.sceneBoundingRect()
    # In scene coordinates, page top-left is (0, 100).
    # Tile top-left must be (50, 100 + 60) = (50, 160)
    assert tile_scene_rect.x() == 50.0
    assert tile_scene_rect.y() == 160.0
    assert tile_scene_rect.width() == 200.0
    assert tile_scene_rect.height() == 300.0
    assert page_item.tile_item.zValue() == 0.5

    # Test clear_tile
    page_item.clear_tile()
    assert page_item.tile_item is None


