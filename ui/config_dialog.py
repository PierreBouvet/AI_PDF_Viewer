import os
import json
import shiboken6
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox,
    QFontComboBox, QSpinBox, QWidget, QFrame, QStackedWidget,
    QToolButton, QButtonGroup, QTextEdit, QCheckBox,
    QRadioButton, QFileDialog
)
from PySide6.QtCore import Qt, QSize, QByteArray, Signal, QThread
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from backend.config_manager import ConfigManager
from backend.logger import logger


from ui.asset_loader import get_icon_path

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
    elif icon_name.lower() == "zotero":
        name_variants.extend(["zotero", "Zotero", "book", "library"])

    for ext in [".svg", ".png", ".jpg", ".jpeg", ".ico"]:
        for variant in name_variants:
            candidates.append(get_icon_path(f"{variant}{ext}"))

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

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
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


class LocalModelFetcherThread(QThread):
    models_fetched = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, endpoint: str, parent=None):
        super().__init__(parent)
        self.endpoint = endpoint

    def run(self):
        try:
            from backend.ai_assistant import ensure_local_ai_server, extract_ollama_base_url
            import urllib.request
            raw_endpoint = (self.endpoint or "").strip()
            base_url = extract_ollama_base_url(raw_endpoint)
            
            # If targeting localhost Ollama, ensure it is running
            if "localhost:11434" in base_url or "127.0.0.1:11434" in base_url:
                ensure_local_ai_server(base_url, timeout_sec=4.0)

            models = []
            
            # 1. Try Ollama native /api/tags
            try:
                req = urllib.request.Request(f"{base_url}/api/tags", headers={"User-Agent": "AI_PDF_Viewer"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            except Exception as e:
                logger.debug(f"Failed to query {base_url}/api/tags: {e}")
                
            # 2. Try OpenAI-compatible /v1/models or /models
            if not models:
                for models_url in [f"{base_url}/v1/models", f"{base_url}/models"]:
                    try:
                        req = urllib.request.Request(models_url, headers={"User-Agent": "AI_PDF_Viewer"})
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
                            if models:
                                break
                    except Exception as e:
                        logger.debug(f"Failed to query {models_url}: {e}")

            if models:
                self.models_fetched.emit(models)
            else:
                self.error_occurred.emit("No models found. Make sure Ollama is running and models are installed.")
        except Exception as e:
            self.error_occurred.emit(str(e))


class AcademicModelFetcherThread(QThread):
    models_fetched = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, base_url: str, client_id: str, client_secret: str, parent=None):
        super().__init__(parent)
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret

    def run(self):
        try:
            from backend.ai_assistant import fetch_academic_models
            models = fetch_academic_models(self.base_url, self.client_id, self.client_secret)
            if models:
                self.models_fetched.emit(models)
            else:
                self.error_occurred.emit("No models returned by academic API.")
        except Exception as e:
            self.error_occurred.emit(str(e))


class ZoteroTestWorker(QThread):
    result_ready = Signal(bool, str)

    def __init__(self, user_id: str, api_key: str, library_type: str = "user", parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.api_key = api_key
        self.library_type = library_type

    def run(self):
        try:
            from pyzotero import zotero
            zot = zotero.Zotero(self.user_id, self.library_type, self.api_key)
            cols = zot.collections(limit=1)
            self.result_ready.emit(True, f"Connected to {self.library_type} library {self.user_id} successfully!")
        except Exception as e:
            err = str(e)
            if "403" in err:
                err = "403 Forbidden: Invalid API key or missing permissions."
            elif "400" in err:
                err = f"400 Bad Request: Check User ID ({self.user_id})."
            self.result_ready.emit(False, f"Connection failed: {err}")


class ConfigDialog(QDialog):
    theme_preview_requested = Signal(str, str)
    
    def __init__(self, parent=None, initial_tab=0, current_api_key=None):
        super().__init__(parent)
        self.fetcher = None
        self.local_fetcher = None
        self.academic_fetcher = None
        self.zotero_test_worker = None
        self.setWindowTitle("Settings")
        self.setFixedSize(540, 520)
        
        self.config = ConfigManager()
        self.key_was_changed = False
        self.academic_keys_were_changed = False
        self.zotero_keys_were_changed = False
        
        # Read initial API key directly from keychain if not explicitly provided
        if current_api_key is not None:
            self._initial_api_key = current_api_key
        else:
            try:
                import keyring
                self._initial_api_key = keyring.get_password("AIPDFViewer", "api_key") or ""
            except Exception:
                self._initial_api_key = ""

        # Read initial academic credentials from keychain (with environment fallback)
        try:
            import keyring
            self._initial_academic_client_id = keyring.get_password("AIPDFViewer", "academic_client_id") or ""
            self._initial_academic_client_secret = keyring.get_password("AIPDFViewer", "academic_client_secret") or ""
        except Exception:
            self._initial_academic_client_id = ""
            self._initial_academic_client_secret = ""

        if not self._initial_academic_client_id:
            self._initial_academic_client_id = os.environ.get("CLIENT_ID", "").strip()
        if not self._initial_academic_client_secret:
            self._initial_academic_client_secret = os.environ.get("CLIENT_SECRET", "").strip()

        # Read initial Zotero credentials from keychain
        try:
            import keyring
            self._initial_zotero_key = keyring.get_password("AIPDFViewer", "zotero_api_key") or ""
        except Exception:
            self._initial_zotero_key = ""
        if not self._initial_zotero_key:
            self._initial_zotero_key = os.environ.get("ZOTERO_API_KEY", "").strip()
        
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
        self.btn_zotero = MacTabButton("Zotero", get_tab_icon("zotero", "📚"))
        
        self.tab_group.addButton(self.btn_general, 0)
        self.tab_group.addButton(self.btn_ai, 1)
        self.tab_group.addButton(self.btn_chatbox, 2)
        self.tab_group.addButton(self.btn_zotero, 3)
        
        tab_bar_layout.addWidget(self.btn_general)
        tab_bar_layout.addWidget(self.btn_ai)
        tab_bar_layout.addWidget(self.btn_chatbox)
        tab_bar_layout.addWidget(self.btn_zotero)
        main_layout.addLayout(tab_bar_layout)
        
        # Separator Line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: #d1d1d6; max-height: 1px; margin-top: 2px; margin-bottom: 6px;")
        main_layout.addWidget(sep)
        
        # 2. Content Pages via QStackedWidget
        self.stack = QStackedWidget()
        self.page_general = self._create_general_page()
        self.page_ai = self._create_ai_page()
        self.page_chatbox = self._create_chatbox_page()
        self.page_zotero = self._create_zotero_page()
        
        self.stack.addWidget(self.page_general)
        self.stack.addWidget(self.page_ai)
        self.stack.addWidget(self.page_chatbox)
        self.stack.addWidget(self.page_zotero)
        
        main_layout.addWidget(self.stack)
        
        # Switch tab signal
        self.tab_group.idClicked.connect(self.stack.setCurrentIndex)
        
        # Initial Tab Selection
        if initial_tab == 1:
            self.btn_ai.setChecked(True)
            self.stack.setCurrentIndex(1)
        elif initial_tab == 2:
            self.btn_chatbox.setChecked(True)
            self.stack.setCurrentIndex(2)
        elif initial_tab == 3:
            self.btn_zotero.setChecked(True)
            self.stack.setCurrentIndex(3)
        else:
            self.btn_general.setChecked(True)
            self.stack.setCurrentIndex(0)
            
        # 3. Bottom Action Buttons (Cancel / Save)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5e5ea;
                color: #1c1c1e;
                font-weight: 500;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #d1d1d6;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setDefault(True)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: #ffffff;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                min-width: 90px;
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
        desc_label = QLabel("Local AI-assisted scientific PDF reader powered by Gemini and Ollama.")
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
        self.style_combo.addItems(["Native", "Adobe Acrobat", "Minimalist"])
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

        # Bibliography & Local Storage Section
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #e5e5ea; margin-top: 6px; margin-bottom: 6px;")
        form.addRow(sep)

        sources_header = QLabel("<b>Bibliography & Local Storage</b>")
        sources_header.setStyleSheet("font-size: 10pt; color: #1c1c1e;")
        sources_desc = QLabel("Centralized folder where scientific papers are renamed and archived.")
        sources_desc.setStyleSheet("color: #636366; font-size: 8.5pt;")
        form.addRow(sources_header)
        form.addRow(sources_desc)

        sources_layout = QHBoxLayout()
        self.sources_dir_input = QLineEdit()
        self.sources_dir_input.setText(self.config.source_directory)
        self.btn_browse_sources = QPushButton("Browse...")
        self.btn_browse_sources.clicked.connect(self._browse_sources_dir)
        sources_layout.addWidget(self.sources_dir_input, 1)
        sources_layout.addWidget(self.btn_browse_sources)
        form.addRow("Sources folder:", sources_layout)

        scan_layout = QHBoxLayout()
        self.btn_scan_sources = QPushButton("Scan Directory for Zotero Links")
        self.btn_scan_sources.setStyleSheet("font-weight: 600; padding: 6px 14px;")
        self.btn_scan_sources.clicked.connect(self._open_scan_sources_dialog)
        scan_layout.addWidget(self.btn_scan_sources)
        scan_layout.addStretch()
        form.addRow("", scan_layout)
        
        layout.addLayout(form)
        layout.addStretch()
        return page

    def _browse_sources_dir(self):
        curr = self.sources_dir_input.text().strip() or os.path.expanduser("~/Documents")
        chosen = QFileDialog.getExistingDirectory(self, "Select Sources Directory", curr)
        if chosen:
            self.sources_dir_input.setText(chosen)

    def _open_scan_sources_dialog(self):
        sources = self.sources_dir_input.text().strip()
        if not sources or not os.path.isdir(sources):
            QMessageBox.warning(self, "Invalid Directory", f"The directory '{sources}' does not exist.")
            return
        from ui.zotero_scan_dialog import ZoteroScanDialog
        dlg = ZoteroScanDialog(sources_dir=sources, parent=self)
        dlg.exec()

    def _on_theme_selection_changed(self):
        style = self.style_combo.currentText()
        mode = self.mode_combo.currentText()
        self.theme_preview_requested.emit(style, mode)

    def _create_ai_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        
        # 1. Top 2-Part Provider Selection Frame
        provider_frame = QFrame()
        provider_frame.setStyleSheet("""
            QFrame {
                background-color: #f2f2f7;
                border: 1px solid #d1d1d6;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        provider_layout = QHBoxLayout(provider_frame)
        provider_layout.setContentsMargins(8, 4, 8, 4)
        provider_layout.setSpacing(20)
        
        self.provider_group = QButtonGroup(self)
        self.radio_cloud = QRadioButton("Cloud (Google Gemini)")
        self.radio_academic = QRadioButton("Academic (ChatGPT)")
        self.radio_local = QRadioButton("Local Model (Ollama / GGUF)")
        
        self.provider_group.addButton(self.radio_cloud)
        self.provider_group.addButton(self.radio_academic)
        self.provider_group.addButton(self.radio_local)
        
        if self.config.ai_provider == "local":
            self.radio_local.setChecked(True)
        elif self.config.ai_provider == "academic":
            self.radio_academic.setChecked(True)
        else:
            self.radio_cloud.setChecked(True)
            
        self.radio_cloud.toggled.connect(self._on_provider_toggled)
        self.radio_academic.toggled.connect(self._on_provider_toggled)
        self.radio_local.toggled.connect(self._on_provider_toggled)
        
        provider_layout.addWidget(self.radio_cloud)
        provider_layout.addWidget(self.radio_academic)
        provider_layout.addWidget(self.radio_local)
        provider_layout.addStretch()
        
        layout.addWidget(provider_frame)
        
        # 2. Container for Cloud (Gemini) Options
        self.cloud_container = QWidget()
        cloud_layout = QVBoxLayout(self.cloud_container)
        cloud_layout.setContentsMargins(0, 0, 0, 0)
        cloud_layout.setSpacing(12)
        
        # API Key Section
        key_group = QVBoxLayout()
        key_header = QLabel("<b>Google Gemini API Key</b>")
        key_header.setStyleSheet("font-size: 10pt; color: #1c1c1e;")
        key_group.addWidget(key_header)
        
        key_input_layout = QHBoxLayout()
        self.key_input = QLineEdit(self._initial_api_key)
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
        cloud_layout.addLayout(key_group)
        
        # Cloud Model Selection Section
        model_group = QVBoxLayout()
        model_header = QLabel("<b>Default Cloud Model</b>")
        model_header.setStyleSheet("font-size: 10pt; color: #1c1c1e;")
        model_group.addWidget(model_header)
        
        self.model_combo = QComboBox()
        current_model = self.config.model_name
        if current_model:
            self.model_combo.addItem(current_model)
        else:
            self.model_combo.addItem("gemini-flash-lite-latest (Default)")
        model_group.addWidget(self.model_combo)
        cloud_layout.addLayout(model_group)
        
        layout.addWidget(self.cloud_container)
        
        # 3. Container for Academic AI Options
        self.academic_container = QWidget()
        academic_layout = QVBoxLayout(self.academic_container)
        academic_layout.setContentsMargins(0, 0, 0, 0)
        academic_layout.setSpacing(10)

        academic_form = QFormLayout()
        academic_form.setSpacing(8)
        academic_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.academic_url_input = QLineEdit(self.config.academic_base_url or "https://meduniwien-api.academic-ai.at")
        self.academic_url_input.setPlaceholderText("https://meduniwien-api.academic-ai.at")
        academic_form.addRow("Base URL:", self.academic_url_input)

        self.academic_id_input = QLineEdit(self._initial_academic_client_id)
        self.academic_id_input.setPlaceholderText("Enter your academic Client ID...")
        academic_form.addRow("Client ID:", self.academic_id_input)

        self.academic_secret_input = QLineEdit(self._initial_academic_client_secret)
        self.academic_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.academic_secret_input.setPlaceholderText("Enter your academic Client Secret...")
        academic_form.addRow("Client Secret:", self.academic_secret_input)

        academic_layout.addLayout(academic_form)

        # Academic Model Selection Section
        academic_model_group = QVBoxLayout()
        academic_model_header = QLabel("<b>Academic Model (ChatGPT)</b>")
        academic_model_header.setStyleSheet("font-size: 10pt; color: #1c1c1e;")
        academic_model_group.addWidget(academic_model_header)

        academic_model_layout = QHBoxLayout()
        self.academic_model_combo = QComboBox()
        current_academic = self.config.academic_model_name or "gpt-4o"
        self.academic_model_combo.addItem(current_academic)

        self.fetch_academic_btn = QPushButton("Fetch Models")
        self.fetch_academic_btn.setStyleSheet("""
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
        self.fetch_academic_btn.clicked.connect(self.fetch_academic_models)

        academic_model_layout.addWidget(self.academic_model_combo)
        academic_model_layout.addWidget(self.fetch_academic_btn)
        academic_model_group.addLayout(academic_model_layout)

        self.academic_status_label = QLabel("")
        self.academic_status_label.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        academic_model_group.addWidget(self.academic_status_label)

        academic_hint = QLabel("Your Client ID and Client Secret are securely saved in your macOS Keychain.")
        academic_hint.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        academic_model_group.addWidget(academic_hint)

        academic_layout.addLayout(academic_model_group)

        layout.addWidget(self.academic_container)
        
        # 3. Container for Local Model Options
        self.local_container = QWidget()
        local_layout = QVBoxLayout(self.local_container)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(10)
        
        # Local Model Dropdown Selection
        local_model_group = QVBoxLayout()
        local_model_header = QLabel("<b>Installed Local Model (Ollama)</b>")
        local_model_header.setStyleSheet("font-size: 10pt; color: #1c1c1e;")
        local_model_group.addWidget(local_model_header)
        
        local_model_layout = QHBoxLayout()
        self.local_model_combo = QComboBox()
        current_local = self.config.local_model_name or "mistral-nemo:latest"
        self.local_model_combo.addItem(current_local)
        
        self.fetch_local_btn = QPushButton("Fetch Local Models")
        self.fetch_local_btn.setStyleSheet("""
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
        self.fetch_local_btn.clicked.connect(self.fetch_local_models)
        
        local_model_layout.addWidget(self.local_model_combo)
        local_model_layout.addWidget(self.fetch_local_btn)
        local_model_group.addLayout(local_model_layout)

        self.local_status_label = QLabel("")
        self.local_status_label.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        local_model_group.addWidget(self.local_status_label)

        local_layout.addLayout(local_model_group)
        
        # Local Endpoint Form
        local_form = QFormLayout()
        local_form.setSpacing(8)
        local_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.endpoint_input = QLineEdit(self.config.local_endpoint_url or "http://localhost:11434/v1")
        self.endpoint_input.setPlaceholderText("http://localhost:11434/v1 (Ollama / Local Server)")
        local_form.addRow("Server URL:", self.endpoint_input)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setSingleStep(1)
        current_sec = int(getattr(self.config, "local_timeout_sec", 300))
        self.timeout_spin.setValue(max(1, min(30, round(current_sec / 60))))
        self.timeout_spin.setSuffix(" min")
        self.timeout_spin.setToolTip("Maximum minutes to wait for local model inference before timing out.")
        local_form.addRow("Timeout:", self.timeout_spin)

        timeout_hint = QLabel("Higher timeout (e.g. 5–10 min) recommended for 12B+ models and long documents.")
        timeout_hint.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        local_form.addRow("", timeout_hint)

        local_layout.addLayout(local_form)
        
        layout.addWidget(self.local_container)
        
        self._on_provider_toggled()
        self._on_key_changed(self._initial_api_key)
        
        # Auto fetch local models if local provider selected
        if self.config.ai_provider == "local":
            self.fetch_local_models()
            
        layout.addStretch()
        return page

    def _on_provider_toggled(self):
        is_cloud = self.radio_cloud.isChecked()
        is_academic = self.radio_academic.isChecked()
        is_local = self.radio_local.isChecked()

        self.cloud_container.setVisible(is_cloud)
        self.academic_container.setVisible(is_academic)
        self.local_container.setVisible(is_local)

        if is_local:
            self.fetch_local_models()
        elif is_academic:
            if self.academic_id_input.text().strip() and self.academic_secret_input.text().strip():
                if self.academic_model_combo.count() <= 1:
                    self.fetch_academic_models()

    def fetch_academic_models(self):
        base_url = self.academic_url_input.text().strip() or "https://meduniwien-api.academic-ai.at"
        client_id = self.academic_id_input.text().strip()
        client_secret = self.academic_secret_input.text().strip()

        if not client_id or not client_secret:
            QMessageBox.warning(self, "Warning", "Please enter both Client ID and Client Secret first.")
            return

        self.fetch_academic_btn.setText("Fetching...")
        self.fetch_academic_btn.setEnabled(False)
        self.academic_status_label.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        self.academic_status_label.setText("Connecting to Academic AI server...")

        try:
            if self.academic_fetcher is not None and shiboken6.isValid(self.academic_fetcher) and self.academic_fetcher.isRunning():
                self.academic_fetcher.wait(300)
        except Exception:
            pass

        self.academic_fetcher = AcademicModelFetcherThread(base_url, client_id, client_secret, parent=self)
        self.academic_fetcher.models_fetched.connect(self._on_academic_models_fetched)
        self.academic_fetcher.error_occurred.connect(self._on_academic_fetch_error)
        self.academic_fetcher.start()

    def _on_academic_models_fetched(self, models: list):
        self.fetch_academic_btn.setText("Fetch Models")
        self.fetch_academic_btn.setEnabled(True)
        if models:
            current = self.config.academic_model_name
            self.academic_model_combo.clear()
            self.academic_model_combo.addItems(models)

            idx = self.academic_model_combo.findText(current)
            if idx >= 0:
                self.academic_model_combo.setCurrentIndex(idx)
            else:
                self.academic_model_combo.setCurrentIndex(0)

            self.academic_status_label.setStyleSheet("color: #34c759; font-size: 8.5pt;")
            self.academic_status_label.setText(f"✓ Found {len(models)} authorized model(s)")
        else:
            self.academic_status_label.setStyleSheet("color: #ff9500; font-size: 8.5pt;")
            self.academic_status_label.setText("No models returned by academic API.")

    def _on_academic_fetch_error(self, err_msg: str):
        self.fetch_academic_btn.setText("Fetch Models")
        self.fetch_academic_btn.setEnabled(True)
        self.academic_status_label.setStyleSheet("color: #ff3b30; font-size: 8.5pt;")
        self.academic_status_label.setText(f"⚠️ {err_msg}")

    def fetch_local_models(self):
        endpoint = self.endpoint_input.text().strip() or "http://localhost:11434/v1"
        self.fetch_local_btn.setText("Fetching...")
        self.fetch_local_btn.setEnabled(False)
        self.local_status_label.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        self.local_status_label.setText("Connecting to local model server...")
        
        try:
            if self.local_fetcher is not None and shiboken6.isValid(self.local_fetcher) and self.local_fetcher.isRunning():
                self.local_fetcher.wait(300)
        except Exception:
            pass

        self.local_fetcher = LocalModelFetcherThread(endpoint, parent=self)
        self.local_fetcher.models_fetched.connect(self._on_local_models_fetched)
        self.local_fetcher.error_occurred.connect(self._on_local_fetch_error)
        self.local_fetcher.start()

    def _on_local_models_fetched(self, models: list):
        self.fetch_local_btn.setText("Fetch Local Models")
        self.fetch_local_btn.setEnabled(True)
        if models:
            current = self.config.local_model_name
            self.local_model_combo.clear()
            self.local_model_combo.addItems(models)
            
            idx = self.local_model_combo.findText(current)
            if idx >= 0:
                self.local_model_combo.setCurrentIndex(idx)
            else:
                self.local_model_combo.setCurrentIndex(0)
            
            self.local_status_label.setStyleSheet("color: #34c759; font-size: 8.5pt;")
            self.local_status_label.setText(f"✓ Found {len(models)} installed model(s)")
        else:
            self.local_status_label.setStyleSheet("color: #ff9500; font-size: 8.5pt;")
            self.local_status_label.setText("No models found. Run 'ollama pull <model>' to install.")

    def _on_local_fetch_error(self, err_msg: str):
        self.fetch_local_btn.setText("Fetch Local Models")
        self.fetch_local_btn.setEnabled(True)
        self.local_status_label.setStyleSheet("color: #ff3b30; font-size: 8.5pt;")
        self.local_status_label.setText(f"⚠️ {err_msg}")

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

    def _create_zotero_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        header = QLabel("<b>Zotero Account Integration</b>")
        header.setStyleSheet("font-size: 11pt; color: #1c1c1e;")
        desc = QLabel("Link your Zotero library to check paper presence, upload PDFs, organize collections, and sync notes.")
        desc.setStyleSheet("color: #636366; font-size: 9.5pt;")
        layout.addWidget(header)
        layout.addWidget(desc)

        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # User ID
        self.zotero_uid_input = QLineEdit(self.config.zotero_user_id)
        self.zotero_uid_input.setPlaceholderText("e.g. 1234567")
        self.zotero_uid_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d1d6;
                border-radius: 5px;
                padding: 5px 8px;
                background-color: #ffffff;
                color: #1c1c1e;
            }
            QLineEdit:focus {
                border: 1px solid #007aff;
            }
        """)
        form.addRow("User ID:", self.zotero_uid_input)

        # API Key
        self.zotero_key_input = QLineEdit(self._initial_zotero_key)
        self.zotero_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.zotero_key_input.setPlaceholderText("Paste your Personal API Key...")
        self.zotero_key_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d1d1d6;
                border-radius: 5px;
                padding: 5px 8px;
                background-color: #ffffff;
                color: #1c1c1e;
            }
            QLineEdit:focus {
                border: 1px solid #007aff;
            }
        """)
        form.addRow("API Key:", self.zotero_key_input)

        # Library Type
        self.zotero_lib_combo = QComboBox()
        self.zotero_lib_combo.addItems(["User Library", "Group Library"])
        if self.config.zotero_library_type == "group":
            self.zotero_lib_combo.setCurrentIndex(1)
        else:
            self.zotero_lib_combo.setCurrentIndex(0)
        self.zotero_lib_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d1d1d6;
                border-radius: 5px;
                padding: 4px 8px;
                background-color: #ffffff;
                color: #1c1c1e;
            }
        """)
        form.addRow("Library Type:", self.zotero_lib_combo)

        # Auto-check checkbox
        self.zotero_auto_check = QCheckBox("Automatically check if opened PDFs are in Zotero")
        self.zotero_auto_check.setChecked(self.config.zotero_auto_check)
        self.zotero_auto_check.setStyleSheet("color: #1c1c1e; font-size: 9.5pt;")
        form.addRow("", self.zotero_auto_check)

        layout.addLayout(form)

        # Helper link
        help_label = QLabel(
            '<a href="https://www.zotero.org/settings/keys" style="color: #007aff; text-decoration: none;">'
            '🔑 Create or view your Zotero API Keys & User ID at zotero.org &rarr;</a>'
        )
        help_label.setOpenExternalLinks(True)
        help_label.setStyleSheet("font-size: 9pt; margin-top: 2px;")
        layout.addWidget(help_label)

        # Test Connection Section
        test_frame = QFrame()
        test_frame.setStyleSheet("background-color: #f2f2f7; border-radius: 6px; padding: 6px;")
        test_layout = QHBoxLayout(test_frame)
        test_layout.setContentsMargins(8, 6, 8, 6)
        test_layout.setSpacing(10)

        self.zotero_test_btn = QPushButton("Test Connection")
        self.zotero_test_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: #ffffff;
                font-weight: 500;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #b0b0b5;
            }
        """)
        self.zotero_test_btn.clicked.connect(self._test_zotero_connection)
        test_layout.addWidget(self.zotero_test_btn)

        self.zotero_test_status = QLabel("Ready to test.")
        self.zotero_test_status.setWordWrap(True)
        self.zotero_test_status.setStyleSheet("font-size: 9.5pt; color: #636366;")
        test_layout.addWidget(self.zotero_test_status, 1)

        layout.addWidget(test_frame)
        layout.addStretch()
        return page

    def _test_zotero_connection(self):
        uid = self.zotero_uid_input.text().strip()
        key = self.zotero_key_input.text().strip()
        lib_type = "group" if self.zotero_lib_combo.currentIndex() == 1 else "user"
        if not uid or not key:
            self.zotero_test_status.setText("<span style='color: #c93b2b;'>Please enter both User ID and API Key.</span>")
            return

        self.zotero_test_btn.setEnabled(False)
        self.zotero_test_btn.setText("Connecting...")
        self.zotero_test_status.setText("Testing connection...")

        self.zotero_test_worker = ZoteroTestWorker(uid, key, lib_type, parent=self)
        self.zotero_test_worker.result_ready.connect(self._on_zotero_test_result)
        self.zotero_test_worker.start()

    def _on_zotero_test_result(self, success: bool, message: str):
        self.zotero_test_btn.setEnabled(True)
        self.zotero_test_btn.setText("Test Connection")
        if success:
            self.zotero_test_status.setText(f"<span style='color: #2e7d32;'>✓ {message}</span>")
        else:
            self.zotero_test_status.setText(f"<span style='color: #c93b2b;'>✗ {message}</span>")

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
        
        try:
            if self.fetcher is not None and shiboken6.isValid(self.fetcher) and self.fetcher.isRunning():
                self.fetcher.wait(300)
        except Exception:
            pass

        self.fetcher = ModelFetcherThread(api_key, parent=self)
        self.fetcher.models_fetched.connect(self._on_models_fetched)
        self.fetcher.error_occurred.connect(self._on_fetch_error)
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

    def done(self, r):
        try:
            if self.fetcher is not None and shiboken6.isValid(self.fetcher) and self.fetcher.isRunning():
                self.fetcher.wait(500)
        except Exception:
            pass
        try:
            if self.local_fetcher is not None and shiboken6.isValid(self.local_fetcher) and self.local_fetcher.isRunning():
                self.local_fetcher.wait(500)
        except Exception:
            pass
        try:
            if self.academic_fetcher is not None and shiboken6.isValid(self.academic_fetcher) and self.academic_fetcher.isRunning():
                self.academic_fetcher.wait(500)
        except Exception:
            pass
        try:
            if self.zotero_test_worker is not None and shiboken6.isValid(self.zotero_test_worker) and self.zotero_test_worker.isRunning():
                self.zotero_test_worker.wait(500)
        except Exception:
            pass
        super().done(r)

    def accept(self):
        new_key = self.key_input.text().strip()
        if new_key != self._initial_api_key:
            self.key_was_changed = True
            try:
                import keyring
                if new_key:
                    keyring.set_password("AIPDFViewer", "api_key", new_key)
                else:
                    try:
                        keyring.delete_password("AIPDFViewer", "api_key")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Failed to save API key to keychain: {e}")

        new_cid = self.academic_id_input.text().strip()
        new_sec = self.academic_secret_input.text().strip()
        if new_cid != self._initial_academic_client_id or new_sec != self._initial_academic_client_secret:
            self.academic_keys_were_changed = True
            try:
                import keyring
                if new_cid:
                    keyring.set_password("AIPDFViewer", "academic_client_id", new_cid)
                else:
                    try:
                        keyring.delete_password("AIPDFViewer", "academic_client_id")
                    except Exception:
                        pass

                if new_sec:
                    keyring.set_password("AIPDFViewer", "academic_client_secret", new_sec)
                else:
                    try:
                        keyring.delete_password("AIPDFViewer", "academic_client_secret")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Failed to save academic credentials to keychain: {e}")

        new_zot_key = self.zotero_key_input.text().strip()
        if new_zot_key != self._initial_zotero_key:
            self.zotero_keys_were_changed = True
            try:
                import keyring
                if new_zot_key:
                    keyring.set_password("AIPDFViewer", "zotero_api_key", new_zot_key)
                else:
                    try:
                        keyring.delete_password("AIPDFViewer", "zotero_api_key")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Failed to save Zotero API key to keychain: {e}")

        self.config.zotero_user_id = self.zotero_uid_input.text().strip()
        self.config.zotero_library_type = "group" if self.zotero_lib_combo.currentIndex() == 1 else "user"
        self.config.zotero_auto_check = self.zotero_auto_check.isChecked()

        self.config.academic_base_url = self.academic_url_input.text().strip() or "https://meduniwien-api.academic-ai.at"
        selected_academic = self.academic_model_combo.currentText().strip()
        if selected_academic and selected_academic != "No models found":
            self.config.academic_model_name = selected_academic
        
        self.config.app_style = self.style_combo.currentText()
        self.config.color_mode = self.mode_combo.currentText()
        if hasattr(self, "sources_dir_input") and self.sources_dir_input is not None:
            self.config.source_directory = self.sources_dir_input.text().strip()
        
        if self.radio_local.isChecked():
            self.config.ai_provider = "local"
            self.config.local_endpoint_url = self.endpoint_input.text().strip()
            self.config.local_model_name = self.local_model_combo.currentText().strip()
            self.config.local_timeout_sec = self.timeout_spin.value() * 60
        elif self.radio_academic.isChecked():
            self.config.ai_provider = "academic"
        else:
            self.config.ai_provider = "cloud"
            selected_model = self.model_combo.currentText().strip()
            if selected_model and selected_model != "No models found":
                self.config.model_name = selected_model
            
        self.config.ai_font_family = self.font_combo.currentFont().family()
        self.config.ai_font_size = self.size_spin.value()
        
        super().accept()

    @property
    def api_key(self) -> str:
        """Returns the current API key entered in the key input field."""
        if hasattr(self, "key_input") and self.key_input is not None:
            return self.key_input.text().strip()
        return getattr(self, "_initial_api_key", "")


SettingsDialog = ConfigDialog

