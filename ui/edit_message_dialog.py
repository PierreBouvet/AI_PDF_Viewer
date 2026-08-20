from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QPlainTextEdit, QLabel)
from PySide6.QtGui import QFont

class EditMessageDialog(QDialog):
    def __init__(self, initial_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit AI Response (Markdown)")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel("Edit the raw markdown below. This will update the display and affect what is appended to the PDF.")
        layout.addWidget(info_label)
        
        self.text_edit = QPlainTextEdit()
        font = QFont("Menlo", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_edit.setFont(font)
        self.text_edit.setPlainText(initial_text)
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        
        layout.addLayout(btn_layout)
        
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
    def get_text(self) -> str:
        return self.text_edit.toPlainText()
