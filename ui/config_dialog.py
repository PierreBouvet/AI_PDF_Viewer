import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox,
    QFontComboBox, QSpinBox, QWidget, QFrame, QStackedWidget,
    QToolButton, QButtonGroup, QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, QSize, QByteArray, Signal, QThread
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from backend.config_manager import ConfigManager
from backend.logger import logger


def get_tab_icon(icon_name: str, fallback_glyph: str, size: int = 24) -> QIcon:
    """
    Looks for a custom icon in icons/ (supports .svg, .png, etc.).
    For SVGs, renders dual-state pixmaps (unselected in #555555, selected in #007aff).
    If no file is found, renders a high-DPI vector glyph fallback.
    """
    candidates = []
    # Possible base names
    name_variants = [
        icon_name.lower(),
        icon_name.capitalize(),
        icon_name.upper(),
        f"settings_{icon_name.lower()}",
        f"icon_{icon_name.lower()}",
    ]
    if icon_name.lower() == "general":
        name_variants.extend(["settings", "Settings", "SETTINGS", "gear", "Gear"])
    elif icon_name.lower() == "ai":
        name_variants.extend(["sparkles", "Sparkles", "brain", "Brain"])
    elif icon_name.lower() == "chatbox":
        name_variants.extend(["chat", "Chat", "message", "Message"])

    for ext in [".svg", ".png", ".jpg", ".jpeg", ".ico"]:
        for variant in name_variants:
            candidates.append(os.path.join("icons", f"{variant}{ext}"))

    found_path = None
    for path in candidates:
        if os.path.exists(path):
            found_path = path
            break

    if found_path:
        if found_path.lower().endswith(".svg"):
            try:
                with open(found_path, "r", encoding="utf-8") as f:
                    svg_content = f.read()

                icon = QIcon()
                for state, color_hex in [(QIcon.State.Off, "#555555"), (QIcon.State.On, "#007aff")]:
                    # Replace currentColor with theme color
                    content = svg_content.replace("currentColor", color_hex)
                    renderer = QSvgRenderer(QByteArray(content.encode("utf-8")))

                    pix = QPixmap(size * 2, size * 2)
                    pix.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pix)
                    renderer.render(painter)
                    painter.end()

                    pix.setDevicePixelRatio(2.0)
                    icon.addPixmap(pix, QIcon.Mode.Normal, state)

                return icon
            except Exception as e:
                logger.error(f"Error loading SVG {found_path}: {e}")
                return QIcon(found_path)
        else:
            return QIcon(found_path)

    # Render fallback glyph as high-DPI pixmap
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    
    font = QFont("Apple Color Emoji" if "darwin" in os.sys.platform else "Segoe UI Emoji")
    font.setPointSize(int(size * 0.85))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, fallback_glyph)
    painter.end()
    
    return QIcon(pixmap)


class MacTabButton(QToolButton):
    """A macOS Settings style toolbar tab button with icon above text and pill selection."""
    def __init__(self, text: str, icon: QIcon, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setIcon(icon)
        self.setIconSize(QSize(26, 26))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(78, 58)
        self.setStyleSheet("""
            QToolButton {
                border: none;
                border-radius: 8px;
                background-color: transparent;
                color: #555555;
                font-size: 9.5pt;
                font-weight: 500;
                padding: 4px;
                margin: 0px 4px;
            }
            QToolButton:hover {
                background-color: rgba(0, 0, 0, 0.05);
                color: #111111;
            }
            QToolButton:checked {
                background-color: rgba(0, 122, 255, 0.14);
                color: #007aff;
                font-weight: 600;
            }
        """)


class ModelFetcherThread(QThread):
    models_fetched = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            models = client.models.list()
            
            model_names = []
            for m in models:
                if 'embed' in m.name.lower():
                    continue
                name = m.name.replace("models/", "")
                if 'gemini' in name.lower() and 'vision' not in name.lower():
                    model_names.append(name)
            self.models_fetched.emit(model_names)
        except Exception as e:
            self.error_occurred.emit(str(e))


class ConfigDialog(QDialog):
    theme_preview_requested = Signal(str, str)
    
    def __init__(self, parent=None, current_api_key="", initial_tab=0):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(500, 420)
        
        self.config = ConfigManager()
        self.api_key = current_api_key
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 16)
        main_layout.setSpacing(10)
        
        # 1. Top macOS-style Tab Bar
        tab_bar_layout = QHBoxLayout()
        tab_bar_layout.setContentsMargins(0, 0, 0, 0)
        tab_bar_layout.setSpacing(12)
        tab_bar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        
        self.btn_general = MacTabButton("General", get_tab_icon("general", "⚙️"))
        self.btn_ai = MacTabButton("AI", get_tab_icon("ai", "✨"))
        self.btn_chatbox = MacTabButton("Chatbox", get_tab_icon("chatbox", "💬"))
        
        self.tab_group.addButton(self.btn_general, 0)
        self.tab_group.addButton(self.btn_ai, 1)
        self.tab_group.addButton(self.btn_chatbox, 2)
        
        tab_bar_layout.addWidget(self.btn_general)
        tab_bar_layout.addWidget(self.btn_ai)
        tab_bar_layout.addWidget(self.btn_chatbox)
        
        main_layout.addLayout(tab_bar_layout)
        
        # 2. Subtle Divider Line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet("border: none; border-top: 1px solid #d5d5da; margin-top: 2px; margin-bottom: 6px;")
        main_layout.addWidget(sep)
        
        # 3. Stacked Pages
        self.pages_stack = QStackedWidget()
        
        self.page_general = self._create_general_page()
        self.page_ai = self._create_ai_page()
        self.page_chatbox = self._create_chatbox_page()
        
        self.pages_stack.addWidget(self.page_general)
        self.pages_stack.addWidget(self.page_ai)
        self.pages_stack.addWidget(self.page_chatbox)
        
        self.tab_group.idClicked.connect(self.pages_stack.setCurrentIndex)
        
        if initial_tab == 1:
            self.btn_ai.setChecked(True)
            self.pages_stack.setCurrentIndex(1)
        elif initial_tab == 2:
            self.btn_chatbox.setChecked(True)
            self.pages_stack.setCurrentIndex(2)
        else:
            self.btn_general.setChecked(True)
            self.pages_stack.setCurrentIndex(0)
        
        main_layout.addWidget(self.pages_stack, stretch=1)
        
        # 4. Bottom Action Buttons (Cancel / Save)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(10)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5e5ea;
                color: #000000;
                font-weight: 500;
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #d1d1d6;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: #ffffff;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
        """)
        self.save_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(btn_layout)

    def _create_general_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)
        
        # App Info Section
        info_label = QLabel("<b>AI PDF Viewer</b>")
        info_label.setStyleSheet("font-size: 11pt; color: #1c1c1e;")
        desc_label = QLabel("Local AI-assisted scientific PDF reader powered by Google Gemini.")
        desc_label.setStyleSheet("color: #636366; font-size: 9.5pt;")
        
        layout.addWidget(info_label)
        layout.addWidget(desc_label)
        
        # Form items
        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # Style Selector
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Native macOS", "Adobe Acrobat", "Minimalist"])
        idx = self.style_combo.findText(self.config.app_style)
        if idx >= 0:
            self.style_combo.setCurrentIndex(idx)
        self.style_combo.currentTextChanged.connect(self._on_theme_selection_changed)
        form.addRow("Application style:", self.style_combo)
        
        # Appearance Mode Selector
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["System (Auto)", "Light", "Dark"])
        idx = self.mode_combo.findText(self.config.color_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.currentTextChanged.connect(self._on_theme_selection_changed)
        form.addRow("Appearance:", self.mode_combo)
        
        self.auto_zoom_check = QCheckBox("Keep PDF page ratio constant on resize")
        self.auto_zoom_check.setChecked(True)
        self.auto_zoom_check.setEnabled(False) # Fixed native feature
        form.addRow("View behavior:", self.auto_zoom_check)
        
        layout.addLayout(form)
        layout.addStretch()
        return page

    def _on_theme_selection_changed(self):
        style = self.style_combo.currentText()
        mode = self.mode_combo.currentText()
        self.theme_preview_requested.emit(style, mode)

    def _create_ai_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)
        
        # API Key Section
        key_group = QVBoxLayout()
        key_header = QLabel("<b>Google Gemini API Key</b>")
        key_header.setStyleSheet("font-size: 10.5pt; color: #1c1c1e;")
        key_group.addWidget(key_header)
        
        key_input_layout = QHBoxLayout()
        self.key_input = QLineEdit(self.api_key)
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Enter your Gemini API key...")
        self.key_input.textChanged.connect(self._on_key_changed)
        
        self.fetch_btn = QPushButton("Fetch Models")
        self.fetch_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: #ffffff;
                font-weight: 500;
                border: none;
                border-radius: 5px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #b0bec5;
            }
        """)
        self.fetch_btn.clicked.connect(self.fetch_models)
        
        key_input_layout.addWidget(self.key_input)
        key_input_layout.addWidget(self.fetch_btn)
        key_group.addLayout(key_input_layout)
        
        key_hint = QLabel("Your API key is securely saved in your macOS Keychain.")
        key_hint.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        key_group.addWidget(key_hint)
        
        layout.addLayout(key_group)
        
        # Model Selection Section
        model_group = QVBoxLayout()
        model_header = QLabel("<b>Default AI Model</b>")
        model_header.setStyleSheet("font-size: 10.5pt; color: #1c1c1e;")
        model_group.addWidget(model_header)
        
        self.model_combo = QComboBox()
        self.model_combo.addItem(self.config.model_name)
        model_group.addWidget(self.model_combo)
        
        layout.addLayout(model_group)
        
        self._on_key_changed(self.api_key)
        layout.addStretch()
        return page

    def _create_chatbox_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        
        header = QLabel("<b>Chatbox Typography</b>")
        header.setStyleSheet("font-size: 10.5pt; color: #1c1c1e;")
        layout.addWidget(header)
        
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # Font Family
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self.config.ai_font_family))
        self.font_combo.currentFontChanged.connect(self._update_preview)
        form.addRow("Font Family:", self.font_combo)
        
        # Font Size
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 36)
        self.size_spin.setValue(self.config.ai_font_size)
        self.size_spin.setSuffix(" pt")
        self.size_spin.valueChanged.connect(self._update_preview)
        form.addRow("Font Size:", self.size_spin)
        
        layout.addLayout(form)
        
        # Live Preview Box
        preview_label = QLabel("<b>Preview:</b>")
        preview_label.setStyleSheet("font-size: 9.5pt; color: #636366; margin-top: 4px;")
        layout.addWidget(preview_label)
        
        self.preview_box = QLabel("This is a live preview of the AI response text formatting and typography.")
        self.preview_box.setWordWrap(True)
        self.preview_box.setStyleSheet("""
            QLabel {
                background-color: #f2f2f7;
                border: 1px solid #d1d1d6;
                border-radius: 8px;
                padding: 10px;
                color: #1c1c1e;
            }
        """)
        self._update_preview()
        layout.addWidget(self.preview_box)
        
        layout.addStretch()
        return page

    def _update_preview(self):
        font_family = self.font_combo.currentFont().family()
        font_size = self.size_spin.value()
        preview_font = QFont(font_family, font_size)
        self.preview_box.setFont(preview_font)

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
        
        self.fetcher = ModelFetcherThread(api_key)
        self.fetcher.models_fetched.connect(self._on_models_fetched)
        self.fetcher.error_occurred.connect(self._on_fetch_error)
        self.fetcher.finished.connect(self.fetcher.deleteLater)
        self.fetcher.start()

    def _on_models_fetched(self, model_names: list):
        self.fetch_btn.setText("Fetch Models")
        self.fetch_btn.setEnabled(True)
        if model_names:
            self.model_combo.addItems(model_names)
            # Try to select currently configured model if present
            idx = self.model_combo.findText(self.config.model_name)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.addItem("No models found")

    def _on_fetch_error(self, err_msg: str):
        self.fetch_btn.setText("Fetch Models")
        self.fetch_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Failed to fetch models:\n{err_msg}")
        self.model_combo.addItem(self.config.model_name)

    def accept(self):
        self.api_key = self.key_input.text().strip()
        
        self.config.app_style = self.style_combo.currentText()
        self.config.color_mode = self.mode_combo.currentText()
        
        selected_model = self.model_combo.currentText().strip()
        if selected_model and selected_model != "No models found":
            self.config.model_name = selected_model
            
        self.config.ai_font_family = self.font_combo.currentFont().family()
        self.config.ai_font_size = self.size_spin.value()
        
        super().accept()


SettingsDialog = ConfigDialog
