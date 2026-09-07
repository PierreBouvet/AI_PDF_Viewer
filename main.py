import sys
import os
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from ui.main_window import MainWindow

DEBUG = False

# icons found at: https://lucide.dev/icons/
# To define the DEFAULT_FALLBACK_MODEL (the model used when no model has been selected), please edit backend/config_manager.py

class PDFViewerApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.main_window = None

    def set_main_window(self, window):
        self.main_window = window

    def event(self, e):
        if e.type() == QEvent.Type.FileOpen:
            if self.main_window:
                self.main_window.load_pdf(e.file())
            return True
        return super().event(e)

def main():
    # Set up environment variables if needed
    os.environ["QT_API"] = "pyside6"
    os.environ["DEBUG_AI"] = "1" if DEBUG else "0"
    
    app = PDFViewerApp(sys.argv)
    app.setApplicationName("AI PDF Viewer")
    
    # Set default application font size to 11pt
    font = app.font()
    font.setPointSize(11)
    app.setFont(font)
    
    from backend.config_manager import ConfigManager
    from ui.theme_manager import ThemeManager
    config = ConfigManager()
    ThemeManager.apply_theme(app, config.app_style, config.color_mode)
    
    window = MainWindow()
    app.set_main_window(window)
    window.show()

    def on_quit():
        try:
            from backend.ai_assistant import release_local_ai_models
            from backend.config_manager import ConfigManager
            cfg = ConfigManager()
            release_local_ai_models(cfg.local_endpoint_url, cfg.local_model_name)
        except Exception:
            pass

    app.aboutToQuit.connect(on_quit)

    # Handle files passed via command line
    if len(sys.argv) > 1 and sys.argv[1].endswith(".pdf"):
        window.load_pdf(sys.argv[1])
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

