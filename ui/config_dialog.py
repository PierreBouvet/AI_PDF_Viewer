from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, 
                               QPushButton, QMessageBox, QFontComboBox, QSpinBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from backend.config_manager import ConfigManager

class ConfigDialog(QDialog):
    def __init__(self, parent=None, current_api_key=""):
        super().__init__(parent)
        self.setWindowTitle("AI Configuration")
        self.resize(400, 250)
        
        self.config = ConfigManager()
        self.api_key = current_api_key
        
        layout = QVBoxLayout(self)
        
        # API Key
        key_layout = QHBoxLayout()
        key_label = QLabel("Google API Key:")
        self.key_input = QLineEdit(self.api_key)
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.textChanged.connect(self._on_key_changed)
        
        self.fetch_btn = QPushButton("Fetch Models")
        self.fetch_btn.clicked.connect(self.fetch_models)
        
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.key_input)
        key_layout.addWidget(self.fetch_btn)
        
        # Model Selection
        model_layout = QHBoxLayout()
        model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        # Set current model if exists
        self.model_combo.addItem(self.config.model_name)
            
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        
        self._on_key_changed(self.api_key)
        
        # Font Configuration
        font_layout = QHBoxLayout()
        font_label = QLabel("AI Font:")
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self.config.ai_font_family))
        
        size_label = QLabel("Size (pt):")
        self.size_spin = QSpinBox()
        self.size_spin.setRange(5, 72)
        self.size_spin.setValue(self.config.ai_font_size)
        
        font_layout.addWidget(font_label)
        font_layout.addWidget(self.font_combo)
        font_layout.addWidget(size_label)
        font_layout.addWidget(self.size_spin)
        
        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(key_layout)
        layout.addLayout(model_layout)
        layout.addLayout(font_layout)
        layout.addLayout(btn_layout)
        
    def _on_key_changed(self, text):
        self.model_combo.setEnabled(bool(text.strip()))
        
    def fetch_models(self):
        api_key = self.key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter an API key first.")
            return
            
        self.fetch_btn.setText("Fetching...")
        self.fetch_btn.setEnabled(False)
        self.model_combo.clear()
        
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            models = client.models.list()
            
            model_names = []
            for m in models:
                if 'embed' in m.name.lower():
                    pass
                    
                name = m.name.replace("models/", "")
                if 'gemini' in name.lower() and 'vision' not in name.lower():
                    model_names.append(name)
            
            if model_names:
                self.model_combo.addItems(model_names)
            else:
                self.model_combo.addItem("No models found")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch models:\n{str(e)}")
            self.model_combo.addItem(self.config.model_name)
            
        finally:
            self.fetch_btn.setText("Fetch Models")
            self.fetch_btn.setEnabled(True)
        
    def accept(self):
        self.api_key = self.key_input.text().strip()
        
        self.config.model_name = self.model_combo.currentText()
        self.config.ai_font_family = self.font_combo.currentFont().family()
        self.config.ai_font_size = self.size_spin.value()
        
        if not self.api_key:
            QMessageBox.warning(self, "Warning", "API Key cannot be empty.")
            return
        super().accept()
