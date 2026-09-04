import sys
import os
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from ui.main_window import MainWindow

DEBUG = False

# Default fallback model when no specific model has been selected or saved.
# Change this model identifier here if a different fallback model is preferred in the future.
DEFAULT_FALLBACK_MODEL = "gemini-flash-lite-latest"

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
    
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        app_dir = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
        os.chdir(app_dir)
        
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
    
    # Handle files passed via command line
    if len(sys.argv) > 1 and sys.argv[1].endswith(".pdf"):
        window.load_pdf(sys.argv[1])
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

