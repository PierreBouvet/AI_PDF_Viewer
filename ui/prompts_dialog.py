from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QComboBox, QTextEdit,
                               QPushButton, QMessageBox, QListWidget, QSplitter)
from PySide6.QtCore import Qt, QThread, Signal
from backend.prompts_manager import PromptsManager

class ImproveWorker(QThread):
    result_ready = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, ai_assistant, prompt_text, model_name):
        super().__init__()
        self.ai_assistant = ai_assistant
        self.prompt_text = prompt_text
        self.model_name = model_name
        
    def run(self):
        try:
            prompt_query = f"You are going to improve the following prompt: {self.prompt_text}"
            answer = self.ai_assistant.ask_direct(prompt_query, model_override=self.model_name)
            self.result_ready.emit(answer)
        except Exception as e:
            self.error_occurred.emit(str(e))

class PromptsDialog(QDialog):
    def __init__(self, parent=None, ai_assistant=None, prompts_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Custom Prompts")
        self.resize(800, 500)
        
        self.ai_assistant = ai_assistant
        self.prompts_manager = prompts_manager
        self.prompts = self.prompts_manager.load_prompts()
        
        layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Panel (List)
        left_widget = QDialog()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.list_widget = QListWidget()
        for expr in self.prompts.keys():
            self.list_widget.addItem(expr)
        self.list_widget.currentItemChanged.connect(self.on_item_selected)
            
        list_btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        delete_btn = QPushButton("Delete")
        add_btn.clicked.connect(self.add_prompt)
        delete_btn.clicked.connect(self.delete_prompt)
        list_btn_layout.addWidget(add_btn)
        list_btn_layout.addWidget(delete_btn)
        
        left_layout.addWidget(QLabel("Saved Prompts:"))
        left_layout.addWidget(self.list_widget)
        left_layout.addLayout(list_btn_layout)
        
        # Right Panel (Edit)
        right_widget = QDialog()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.expr_input = QLineEdit()
        self.expr_input.setPlaceholderText("Expression (e.g. Bullet summary)")
        self.expr_input.textChanged.connect(self.on_expr_changed)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Prompt content...")
        self.prompt_input.textChanged.connect(self.on_prompt_changed)
        
        ai_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.populate_models()
        
        self.improve_btn = QPushButton("✨ AI Improve")
        self.improve_btn.clicked.connect(self.improve_prompt)
        
        ai_layout.addWidget(QLabel("Model:"))
        ai_layout.addWidget(self.model_combo)
        ai_layout.addWidget(self.improve_btn)
        ai_layout.addStretch()
        
        right_layout.addWidget(QLabel("Expression / Name:"))
        right_layout.addWidget(self.expr_input)
        right_layout.addWidget(QLabel("Prompt:"))
        right_layout.addWidget(self.prompt_input)
        right_layout.addLayout(ai_layout)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
        
        # Bottom Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save && Close")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        self._current_item = None
        self._updating = False
        self.worker = None
        
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def populate_models(self):
        # We can try to use the client.models.list() if API key exists
        import keyring
        api_key = keyring.get_password("AIPDFViewer", "api_key")
        if self.ai_assistant and api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                models = client.models.list()
                for m in models:
                    name = m.name.replace("models/", "")
                    if 'gemini' in name.lower() and 'vision' not in name.lower() and 'embed' not in name.lower():
                        self.model_combo.addItem(name)
                        
                # Set current model
                index = self.model_combo.findText(self.ai_assistant.model_name)
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
                    
            except Exception:
                self.model_combo.addItem(self.ai_assistant.model_name)
        else:
            self.model_combo.addItem(self.ai_assistant.model_name if self.ai_assistant else "gemini-3.6-flash")

    def on_item_selected(self, current, previous):
        self._updating = True
        self._current_item = current
        if current:
            expr = current.text()
            self.expr_input.setText(expr)
            self.prompt_input.setPlainText(self.prompts.get(expr, ""))
        else:
            self.expr_input.clear()
            self.prompt_input.clear()
        self._updating = False

    def on_expr_changed(self, text):
        if self._updating or not self._current_item:
            return
        
        old_expr = self._current_item.text()
        new_expr = text.strip()
        
        if new_expr and new_expr != old_expr:
            # Update dict key
            val = self.prompts.pop(old_expr, "")
            self.prompts[new_expr] = val
            
            # Update list item text silently
            self._updating = True
            self._current_item.setText(new_expr)
            self._updating = False

    def on_prompt_changed(self):
        if self._updating or not self._current_item:
            return
        
        expr = self._current_item.text()
        self.prompts[expr] = self.prompt_input.toPlainText()

    def add_prompt(self):
        new_expr = f"New Prompt {self.list_widget.count() + 1}"
        self.prompts[new_expr] = ""
        self.list_widget.addItem(new_expr)
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)
        self.expr_input.setFocus()

    def delete_prompt(self):
        current = self.list_widget.currentItem()
        if current:
            expr = current.text()
            if expr in self.prompts:
                del self.prompts[expr]
            self.list_widget.takeItem(self.list_widget.row(current))

    def improve_prompt(self):
        import keyring
        api_key = keyring.get_password("AIPDFViewer", "api_key")
        if not self.ai_assistant or not api_key:
            QMessageBox.warning(self, "API Key Missing", "Please configure the Google API key first.")
            return
            
        current_text = self.prompt_input.toPlainText().strip()
        if not current_text:
            QMessageBox.warning(self, "Empty Prompt", "Please enter a prompt to improve.")
            return
            
        self.improve_btn.setText("Improving...")
        self.improve_btn.setEnabled(False)
        self.prompt_input.setEnabled(False)
        
        selected_model = self.model_combo.currentText()
        
        self.worker = ImproveWorker(self.ai_assistant, current_text, selected_model)
        self.worker.result_ready.connect(self.on_improve_finished)
        self.worker.error_occurred.connect(self.on_improve_error)
        self.worker.start()

    def on_improve_finished(self, improved_text):
        self.improve_btn.setText("✨ AI Improve")
        self.improve_btn.setEnabled(True)
        self.prompt_input.setEnabled(True)
        
        # As per user request, notify them to trim filler text
        QMessageBox.information(self, "Prompt Improved", 
            "The AI has improved your prompt.\n\nPlease review it and trim any conversational filler (e.g. 'Here is your improved prompt:') before saving.")
            
        self._updating = True
        self.prompt_input.setPlainText(improved_text)
        self._updating = False
        
        # Trigger the manual save to dict
        self.on_prompt_changed()

    def on_improve_error(self, err_msg):
        self.improve_btn.setText("✨ AI Improve")
        self.improve_btn.setEnabled(True)
        self.prompt_input.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Failed to improve prompt:\n{err_msg}")

    def accept(self):
        self.prompts_manager.save_prompts(self.prompts)
        super().accept()
