import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from ui.main_window import MainWindow

DEBUG = False

def main():
    # Set up environment variables if needed
    os.environ["QT_API"] = "pyside6"
    os.environ["DEBUG_AI"] = "1" if DEBUG else "0"
    
    app = QApplication(sys.argv)
    app.setApplicationName("AI PDF Viewer")
    
    # Set default application font size to 11pt
    font = app.font()
    font.setPointSize(11)
    app.setFont(font)
    
    from qt_material import apply_stylesheet
    apply_stylesheet(app, theme='light_blue_500.xml', extra={'density_scale': -2})
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

