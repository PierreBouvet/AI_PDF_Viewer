import os
import shutil
import tempfile
import keyring
from PySide6.QtWidgets import (QMainWindow, QSplitter, QSplitterHandle, QFileDialog, 
                               QToolBar, QMessageBox, QGraphicsView, QPushButton)
from PySide6.QtGui import QAction, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize

from ui.pdf_view import PDFView
from ui.ai_chat_panel import AIChatPanel
from ui.config_dialog import ConfigDialog
from ui.thumbnail_panel import ThumbnailPanel
from backend.pdf_document import PDFDocument
from backend.ai_assistant import AIAssistant
from backend.prompts_manager import PromptsManager
from ui.prompts_dialog import PromptsDialog
from backend.config_manager import ConfigManager, DEFAULT_FALLBACK_MODEL
from backend.logger import logger

class BackgroundSaveWorker(QThread):
    save_finished = Signal(bool, str, int)  # success, err_msg, version
    
    def __init__(self, file_path: str, doc_bytes: bytes, version: int):
        super().__init__()
        self.file_path = file_path
        self.doc_bytes = doc_bytes
        self.version = version
        
    def run(self):
        if not self.file_path or not self.doc_bytes:
            self.save_finished.emit(False, "Invalid file path or data", self.version)
            return
            
        backup_path = self.file_path + ".backup"
        temp_file = None
        try:
            # 1. Create .backup file
            if os.path.exists(self.file_path):
                shutil.copy2(self.file_path, backup_path)
                
            # 2. Save whole document to temp file
            dir_name = os.path.dirname(self.file_path) or None
            fd, temp_file = tempfile.mkstemp(suffix=".pdf", dir=dir_name)
            with open(temp_file, "wb") as f:
                f.write(self.doc_bytes)
            os.close(fd)
            
            # 3. Move to original location
            shutil.move(temp_file, self.file_path)
            temp_file = None
            
            # 4. Delete backup on success
            if os.path.exists(backup_path):
                os.remove(backup_path)
                
            self.save_finished.emit(True, "", self.version)
        except Exception as e:
            logger.error(f"Background save error: {e}")
            if os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, self.file_path)
                except Exception:
                    pass
            self.save_finished.emit(False, str(e), self.version)
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

class MainSplitterHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.btn = None
        self.handle_type = None
        self.last_width = 200
        
    def setup_collapse_button(self, handle_type: str):
        if self.btn is not None:
            return
        self.handle_type = handle_type
        if handle_type == "thumb":
            init_text = "<"
            init_tip = "Collapse thumbnails"
            self.last_width = 171
        else:
            init_text = ">"
            init_tip = "Collapse AI chat"
            self.last_width = 343
            
        self.btn = QPushButton(init_text, self)
        self.btn.setFixedSize(14, 22)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setToolTip(init_tip)
        self.btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(220, 220, 220, 200);
                border: 1px solid #b0b0b0;
                border-radius: 3px;
                font-weight: bold;
                font-size: 8pt;
                padding: 0px;
                margin: 0px;
                color: #444444;
            }
            QPushButton:hover {
                background-color: #0288d1;
                color: white;
                border-color: #0277bd;
            }
        """)
        self.btn.clicked.connect(self.toggle_collapse)
        self.update_position()
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_position()
        
    def update_position(self):
        if self.btn:
            bx = (self.width() - self.btn.width()) // 2
            by = (self.height() // 2) + 18
            self.btn.move(bx, by)
            
    def update_state(self, collapsed: bool):
        if self.btn and self.handle_type:
            if self.handle_type == "thumb":
                if collapsed:
                    self.btn.setText(">")
                    self.btn.setToolTip("Expand thumbnails")
                else:
                    self.btn.setText("<")
                    self.btn.setToolTip("Collapse thumbnails")
            else:
                if collapsed:
                    self.btn.setText("<")
                    self.btn.setToolTip("Expand AI chat")
                else:
                    self.btn.setText(">")
                    self.btn.setToolTip("Collapse AI chat")
                
    def toggle_collapse(self):
        s = self.splitter()
        sizes = s.sizes()
        if len(sizes) < 3:
            return
        if self.handle_type == "thumb":
            if sizes[0] > 20:
                self.last_width = sizes[0]
                new_sizes = [0, sizes[1] + sizes[0], sizes[2]]
                s.setStretchFactor(0, 0)
                s.setSizes(new_sizes)
                self.update_state(collapsed=True)
            else:
                w = self.last_width if self.last_width > 50 else 171
                new_sizes = [w, max(100, sizes[1] - w), sizes[2]]
                s.setStretchFactor(0, 1)
                s.setSizes(new_sizes)
                self.update_state(collapsed=False)
        else:
            if sizes[2] > 20:
                self.last_width = sizes[2]
                new_sizes = [sizes[0], sizes[1] + sizes[2], 0]
                s.setStretchFactor(2, 0)
                s.setSizes(new_sizes)
                self.update_state(collapsed=True)
            else:
                w = self.last_width if self.last_width > 50 else 340
                new_sizes = [sizes[0], max(100, sizes[1] - w), w]
                s.setStretchFactor(2, 2)
                s.setSizes(new_sizes)
                self.update_state(collapsed=False)
        if hasattr(s, "panel_states_changed"):
            s.panel_states_changed.emit()

class MainSplitter(QSplitter):
    panel_states_changed = Signal()
    
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.splitterMoved.connect(self._on_moved)
        
    def createHandle(self):
        return MainSplitterHandle(self.orientation(), self)
        
    def init_handles(self):
        if self.count() >= 3:
            h1 = self.handle(1)
            if isinstance(h1, MainSplitterHandle):
                h1.setup_collapse_button("thumb")
            h2 = self.handle(2)
            if isinstance(h2, MainSplitterHandle):
                h2.setup_collapse_button("chat")
                
    def _on_moved(self, pos, index):
        sizes = self.sizes()
        if index == 1:
            h = self.handle(1)
            if isinstance(h, MainSplitterHandle):
                if sizes[0] <= 20:
                    self.setStretchFactor(0, 0)
                    h.update_state(collapsed=True)
                else:
                    self.setStretchFactor(0, 1)
                    h.last_width = sizes[0]
                    h.update_state(collapsed=False)
        elif index == 2:
            h = self.handle(2)
            if isinstance(h, MainSplitterHandle):
                if sizes[2] <= 20:
                    self.setStretchFactor(2, 0)
                    h.update_state(collapsed=True)
                else:
                    self.setStretchFactor(2, 2)
                    h.last_width = sizes[2]
                    h.update_state(collapsed=False)
        self.panel_states_changed.emit()

class WorkerThread(QThread):
    result_ready = Signal(str, str, str, str)
    chunk_ready = Signal(str)
    error = Signal(str)
    
    def __init__(self, ai_assistant, question, action_type="chat", use_direct=False, original_prompt="", display_title=""):
        super().__init__()
        self.ai_assistant = ai_assistant
        self.question = question
        self.action_type = action_type
        self.use_direct = use_direct
        self.original_prompt = original_prompt
        self.display_title = display_title
        
    def run(self):
        logger.debug(f"--- SENT TO AI ({self.action_type}) --- (Direct: {self.use_direct})\n{self.question}")
            
        try:
            def callback(chunk):
                self.chunk_ready.emit(chunk)

            if self.use_direct:
                answer = self.ai_assistant.ask_direct(self.question, stream_callback=callback)
            else:
                answer = self.ai_assistant.ask(self.question, stream_callback=callback)
                
            logger.debug(f"--- AI RESPONSE ({self.action_type}) ---\n{answer}")
                
            self.result_ready.emit(answer, self.action_type, self.original_prompt, self.display_title)
        except Exception as e:
            logger.error(f"AI Worker error: {e}")
            self.error.emit(str(e))

from ui.asset_loader import get_assets_base_url

class PDFGenerator(QObject):
    finished = Signal(bool)
    
    def __init__(self, html: str, output_path: str):
        super().__init__()
        self.html = html
        self.output_path = output_path
        
    def start(self):
        try:
            doc = QTextDocument()
            doc.setHtml(self.html)
            
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(self.output_path)
            
            layout = QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter)
            printer.setPageLayout(layout)
            
            doc.print_(printer)
            self.finished.emit(True)
        except Exception as e:
            from backend.logger import logger
            logger.error(f"Failed to generate PDF via QTextDocument: {e}")
            self.finished.emit(False)

class IndexingThread(QThread):
    indexing_finished = Signal()
    error = Signal(str)
    
    def __init__(self, ai_assistant, file_path, excluded_pages=None, included_pages=None):
        super().__init__()
        self.ai_assistant = ai_assistant
        self.file_path = file_path
        self.excluded_pages = excluded_pages
        self.included_pages = included_pages
        
    def run(self):
        try:
            self.ai_assistant.index_pdf(self.file_path, self.excluded_pages, self.included_pages)
            self.indexing_finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class StartupTaskThread(QThread):
    models_ranked = Signal(list)
    error = Signal(str)
    
    def __init__(self, ai_assistant):
        super().__init__()
        self.ai_assistant = ai_assistant
        
    def run(self):
        try:
            ranked = self.ai_assistant.rank_available_models()
            if ranked:
                self.models_ranked.emit(ranked)
        except Exception as e:
            self.error.emit(f"Failed to rank models at startup: {e}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-Enhanced PDF Viewer")
        self.resize(1200, 800)
        self.setAcceptDrops(True)
        
        self.config = ConfigManager()
        saved_model_name = self.config.model_name
        self.ai_font_family = self.config.ai_font_family
        self.ai_font_size = self.config.ai_font_size
        
        # Initialize Backend
        self.pdf_doc = PDFDocument()
        self.ai_assistant = AIAssistant(model_name=saved_model_name or DEFAULT_FALLBACK_MODEL)
        self.prompts_manager = PromptsManager()
        self._save_worker = None
        self._pending_save = None
        
        self.startup_thread = None
        if keyring.get_password("AIPDFViewer", "api_key"):
            self.startup_thread = StartupTaskThread(self.ai_assistant)
            self.startup_thread.models_ranked.connect(self.on_models_ranked)
            self.startup_thread.finished.connect(self.startup_thread.deleteLater)
            self.startup_thread.start()
        
        # Central Splitter
        self.splitter = MainSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(12)
        
        # Log Bar
        from PySide6.QtWidgets import QListWidget, QWidget, QVBoxLayout
        self.log_list = QListWidget()
        self.log_list.setFixedHeight(54) # Roughly 3 lines of 10pt text (3 * 16px + padding)
        self.log_list.setSpacing(0)
        self.log_list.setStyleSheet("""
            QListWidget { background-color: #f5f5f5; color: #555555; font-size: 10pt; border: none; border-top: 1px solid #dcdcdc; }
            QListWidget::item { padding: 0px; margin: 0px; min-height: 16px; }
        """)
        
        # Central Widget
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.splitter)
        central_layout.addWidget(self.log_list)
        
        self.setCentralWidget(central_widget)
        
        # State
        self.excluded_pages = set()
        self.included_pages = set()
        
        # UI Components
        self.thumbnail_panel = ThumbnailPanel()
        self.pdf_view = PDFView()
        self.pdf_view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        from PySide6.QtWidgets import QStackedWidget, QLabel
        from PySide6.QtGui import QPixmap
        
        self.pdf_container = QStackedWidget()
        
        self.placeholder_widget = QWidget()
        ph_layout = QVBoxLayout(self.placeholder_widget)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel()
        from ui.asset_loader import get_icon_path
        icon_pixmap = QPixmap(get_icon_path("full_size.jpg"))
        if not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        text_label = QLabel("Open a PDF article to start investigating")
        text_label.setStyleSheet("font-size: 16pt; color: #555;")
        
        ph_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(text_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.pdf_container.addWidget(self.placeholder_widget)
        self.pdf_container.addWidget(self.pdf_view)
        
        from ui.theme_manager import ThemeManager
        self.chat_panel = AIChatPanel(app_style=self.config.app_style, color_mode=self.config.color_mode)
        self.chat_panel.set_prompts(self.prompts_manager.load_prompts())
        self.chat_panel.update_font(self.ai_font_family, self.ai_font_size)
        
        self.splitter.addWidget(self.thumbnail_panel)
        self.splitter.addWidget(self.pdf_container)
        self.splitter.addWidget(self.chat_panel)
        
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, True)
        
        # Adjust proportions: Thumbnails(1), PDF(4), Chat(2)
        # Chat is 2x thumbnails, PDF is 2x chat
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setStretchFactor(2, 2)
        
        # setSizes actually sets the initial width in pixels (Window width is 1200)
        # 1200 * (1/7) = 171, 1200 * (4/7) = 686, 1200 * (2/7) = 343
        self.splitter.setSizes([171, 686, 343])
        self.splitter.init_handles()
        
        # Toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        
        from PySide6.QtWidgets import QWidget, QSizePolicy, QPushButton
        
        self.open_action = QPushButton("Open PDF")
        self.open_action.clicked.connect(self.open_pdf)
        self.toolbar.addWidget(self.open_action)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setToolTip("Save PDF annotations (Cmd+S / Ctrl+S)")
        self.save_btn.clicked.connect(self.save_current_document)
        self.save_btn.setEnabled(False)
        self.toolbar.addWidget(self.save_btn)
        
        from PySide6.QtGui import QKeySequence, QShortcut
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save_current_document)
        
        self.toolbar.addSeparator()
        
        self.mode_action = QPushButton("Standard")
        self.mode_action.setCheckable(True)
        self.mode_action.clicked.connect(self.toggle_layout_mode)
        self.toolbar.addWidget(self.mode_action)
        
        self.toolbar.addSeparator()
        
        self.pdf_only_action = QPushButton("PDF only")
        self.pdf_only_action.setToolTip("Collapse both thumbnail and AI chat panels")
        self.pdf_only_action.clicked.connect(self.toggle_pdf_only)
        self.toolbar.addWidget(self.pdf_only_action)
        
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        
        config_action = QPushButton("Settings")
        config_action.clicked.connect(self.open_config)
        self.toolbar.addWidget(config_action)
        
        # Connect signals
        self.splitter.panel_states_changed.connect(self.update_pdf_only_button_state)
        self.chat_panel.message_sent.connect(self.handle_chat_message)
        self.chat_panel.open_prompts_dialog.connect(self.open_prompts_dialog)
        self.chat_panel.save_requested.connect(self.save_markdown_response)
        self.chat_panel.append_requested.connect(self.append_response_to_pdf)
        self.chat_panel.index_requested.connect(self.index_current_document)
        self.thumbnail_panel.page_selected.connect(self.go_to_page)
        self.thumbnail_panel.toggle_inclusion_requested.connect(self.toggle_page_inclusion)
        self.thumbnail_panel.delete_page_requested.connect(self.delete_page)
        self.pdf_view.page_changed.connect(self.thumbnail_panel.set_current_page)
        self.pdf_view.text_action_requested.connect(self.handle_text_action)
        self.pdf_view.annotation_changed.connect(self.on_document_modified)
        self.chat_panel.open_settings_requested.connect(self.open_ai_settings)
        self.chat_panel.retry_requested.connect(self.retry_last_action)
        self.chat_panel.stop_requested.connect(self.stop_ai_worker)
        
        self.worker = None
        self.indexer = None
        self.last_ai_action = None
        self.zombie_threads = set()
        self.active_generators = set()
        
        # Initial Theme Apply
        self.update_ui_theme()
        self.update_pdf_only_button_state()
        
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and hasattr(app, "styleHints"):
            try:
                app.styleHints().colorSchemeChanged.connect(self._on_system_theme_changed)
            except Exception:
                pass
        
    def _is_thread_running(self, thread):
        if not thread:
            return False
        try:
            import shiboken6
            if not shiboken6.isValid(thread):
                return False
            return thread.isRunning()
        except Exception:
            return False

    def stop_ai_worker(self):
        """Terminates and cleans up running AI worker on user cancellation."""
        if self._is_thread_running(self.worker):
            thread = self.worker
            try:
                thread.result_ready.disconnect()
            except Exception:
                pass
            try:
                thread.error.disconnect()
            except Exception:
                pass
            self.zombie_threads.add(thread)
            thread.finished.connect(lambda t=thread: self.zombie_threads.discard(t))
            if thread.isRunning():
                thread.terminate()
            self.worker = None
        self.last_ai_action = None
        self.chat_panel.set_generating_state(False)
        self.add_log("AI generation stopped by user")
        self.statusBar().showMessage("AI generation stopped.", 3000)

    def _on_worker_finished(self):
        self.worker = None
        self.chat_panel.set_generating_state(False)

    def showEvent(self, event):
        super().showEvent(event)
        if self._is_thread_running(getattr(self, "startup_thread", None)):
            try:
                self.startup_thread.error.connect(self.on_worker_error)
            except Exception:
                pass

    def _on_system_theme_changed(self):
        if self.config.color_mode.lower().startswith("system") or self.config.color_mode.lower() == "auto":
            self.update_ui_theme()

    def update_ui_theme(self, preview_style: str = None, preview_mode: str = None):
        from ui.theme_manager import ThemeManager
        app_style = preview_style if preview_style is not None else self.config.app_style
        color_mode = preview_mode if preview_mode is not None else self.config.color_mode
        palette = ThemeManager.get_palette(app_style, color_mode)
        
        from PySide6.QtWidgets import QApplication
        ThemeManager.apply_theme(QApplication.instance(), app_style, color_mode)
        
        self.pdf_view.update_theme(app_style, color_mode)
        self.chat_panel.update_theme(app_style, color_mode, self.config.ai_font_family, self.config.ai_font_size)
        
        self.log_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {palette['log_bg']};
                color: {palette['text_secondary']};
                font-size: 10pt;
                border: none;
                border-top: 1px solid {palette['border']};
            }}
            QListWidget::item {{
                padding: 0px;
                margin: 0px;
                min-height: 16px;
            }}
        """)
        
    def toggle_page_inclusion(self, page_index: int):
        is_ai = self.pdf_doc.is_ai_generated(page_index)
        if is_ai:
            if page_index in self.included_pages:
                self.included_pages.remove(page_index)
            else:
                self.included_pages.add(page_index)
        else:
            if page_index in self.excluded_pages:
                self.excluded_pages.remove(page_index)
            else:
                self.excluded_pages.add(page_index)
                
        self.thumbnail_panel.refresh_thumbnail(page_index)
        self.chat_panel.show_index_button()
        self.chat_panel.set_index_status("unloaded")
        
    def open_ai_settings(self):
        self.open_config(initial_tab=1)

    def open_config(self, initial_tab=0):
        old_provider = self.config.ai_provider
        old_model = self.config.model_name
        old_local_endpoint = self.config.local_endpoint_url
        old_local_name = self.config.local_model_name
        old_style = self.config.app_style
        old_mode = self.config.color_mode
        
        dialog = ConfigDialog(self, initial_tab=initial_tab)
        dialog.theme_preview_requested.connect(lambda s, m: self.update_ui_theme(preview_style=s, preview_mode=m))
        
        if dialog.exec():
            new_provider = self.config.ai_provider
            new_model = self.config.model_name
            new_local_endpoint = self.config.local_endpoint_url
            new_local_name = self.config.local_model_name
            
            # Apply appearance options (theme, font)
            self.ai_font_family = self.config.ai_font_family
            self.ai_font_size = self.config.ai_font_size
            self.chat_panel.update_font(self.ai_font_family, self.ai_font_size)
            self.update_ui_theme()
            
            provider_changed = (old_provider != new_provider)
            model_changed = (old_model != new_model and bool(new_model))
            key_changed = getattr(dialog, "key_was_changed", False)
            local_changed = (old_local_endpoint != new_local_endpoint or old_local_name != new_local_name)
            
            if model_changed:
                self.ai_assistant.set_model_name(new_model)

            if provider_changed or model_changed or key_changed or local_changed:
                self.ai_assistant.reset_client()
                self.chat_panel.clear_chat()
                self.chat_panel.set_index_status("unloaded")
                self.ai_assistant.clear_index()
                if self.pdf_doc.doc:
                    self.chat_panel.add_system_message(f"Document: {os.path.basename(self.pdf_doc.file_path)}<br><br><b>Click the 'Index PDF' button below</b> to index with the updated configuration.")
                    self.chat_panel.show_index_button()
                    
                active_model = self.ai_assistant.get_active_model_name()
                if provider_changed:
                    provider_label = "Local Model" if new_provider == "local" else "Cloud (Gemini)"
                    self.add_log(f"AI Provider switched to {provider_label} ({active_model}). Please re-index the document.")
                    QMessageBox.information(self, "AI Provider Changed", f"AI Provider switched to {provider_label} ({active_model}).\nPlease re-index the document to continue.")
                elif model_changed:
                    self.add_log(f"Model changed to {new_model}. Please re-index the document.")
                    QMessageBox.information(self, "Model Changed", f"AI model changed to {new_model}.\nPlease re-index the document to continue.")
                elif local_changed and new_provider == "local":
                    self.add_log(f"Local AI configuration updated ({active_model}). Please re-index the document.")
                    QMessageBox.information(self, "Local AI Configuration Updated", f"Local AI model set to {active_model}.\nPlease re-index the document to continue.")
                else:
                    self.add_log("API Key updated. Please re-index the document.")
                    QMessageBox.information(self, "API Key Updated", "API key updated successfully.\nPlease re-index the document to continue.")
        else:
            # Revert theme preview back to saved configuration
            self.update_ui_theme(preview_style=old_style, preview_mode=old_mode)

    def open_prompts_dialog(self):
        dialog = PromptsDialog(self, self.ai_assistant, self.prompts_manager)
        if dialog.exec():
            # Refresh the combobox
            self.chat_panel.set_prompts(self.prompts_manager.load_prompts())

    def toggle_layout_mode(self, checked):
        if checked:
            self._saved_splitter_sizes = self.splitter.sizes()
            self.mode_action.setText("AI Chat View")
            self.thumbnail_panel.setVisible(False)
            self.pdf_container.setVisible(False)
            self.pdf_only_action.setEnabled(False)
        else:
            self.mode_action.setText("Standard View")
            self.thumbnail_panel.setVisible(True)
            self.pdf_container.setVisible(True)
            self.pdf_only_action.setEnabled(True)
            
            if hasattr(self, "_saved_splitter_sizes") and self._saved_splitter_sizes:
                sizes = self._saved_splitter_sizes
                self.splitter.setStretchFactor(0, 0 if sizes[0] <= 20 else 1)
                self.splitter.setStretchFactor(1, 1 if (sizes[0] <= 20 and sizes[2] <= 20) else 4)
                self.splitter.setStretchFactor(2, 0 if sizes[2] <= 20 else 2)
                self.splitter.setSizes(sizes)
                
                h1 = self.splitter.handle(1)
                if isinstance(h1, MainSplitterHandle):
                    h1.update_state(collapsed=(sizes[0] <= 20))
                h2 = self.splitter.handle(2)
                if isinstance(h2, MainSplitterHandle):
                    h2.update_state(collapsed=(sizes[2] <= 20))
                    
            self.update_pdf_only_button_state()

    def update_pdf_only_button_state(self):
        sizes = self.splitter.sizes()
        if len(sizes) >= 3:
            both_collapsed = (sizes[0] <= 20 and sizes[2] <= 20)
            if both_collapsed:
                self.pdf_only_action.setText("PDF n co")
                self.pdf_only_action.setToolTip("Expand thumbnail and AI chat panels")
            else:
                self.pdf_only_action.setText("PDF only")
                self.pdf_only_action.setToolTip("Collapse both thumbnail and AI chat panels")

    def toggle_pdf_only(self):
        sizes = self.splitter.sizes()
        if len(sizes) < 3:
            return
        
        h1 = self.splitter.handle(1)
        h2 = self.splitter.handle(2)
        
        both_collapsed = (sizes[0] <= 20 and sizes[2] <= 20)
        total_w = sum(sizes)
        
        if both_collapsed:
            # Expand both panels
            w1 = getattr(h1, "last_width", 171)
            if w1 < 50:
                w1 = 171
            w2 = getattr(h2, "last_width", 343)
            if w2 < 50:
                w2 = 343
            w_mid = max(100, total_w - w1 - w2)
            self.splitter.setStretchFactor(0, 1)
            self.splitter.setStretchFactor(1, 4)
            self.splitter.setStretchFactor(2, 2)
            self.splitter.setSizes([w1, w_mid, w2])
            if isinstance(h1, MainSplitterHandle):
                h1.update_state(collapsed=False)
            if isinstance(h2, MainSplitterHandle):
                h2.update_state(collapsed=False)
        else:
            # Collapse both panels
            if sizes[0] > 20 and isinstance(h1, MainSplitterHandle):
                h1.last_width = sizes[0]
            if sizes[2] > 20 and isinstance(h2, MainSplitterHandle):
                h2.last_width = sizes[2]
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 1)
            self.splitter.setStretchFactor(2, 0)
            self.splitter.setSizes([0, total_w, 0])
            if isinstance(h1, MainSplitterHandle):
                h1.update_state(collapsed=True)
            if isinstance(h2, MainSplitterHandle):
                h2.update_state(collapsed=True)
                
        self.update_pdf_only_button_state()

    def open_pdf(self):
        if not self.maybe_save_prompt():
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if file_path:
            self.load_pdf(file_path)

    def on_document_modified(self, page_number: int = -1):
        """Called whenever an annotation is added, changed, or removed."""
        if not self.pdf_doc or not self.pdf_doc.doc:
            return
            
        if page_number >= 0:
            self.thumbnail_panel.refresh_thumbnail(page_number)
            
        # 1. Mark displayed document as unsaved
        self.pdf_doc.is_saved = False
        self.pdf_doc.is_dirty = True
        self.update_save_action_state()
        
        # 2. Extract current document bytes safely under lock
        with self.pdf_doc._lock:
            if not self.pdf_doc.doc or not self.pdf_doc.file_path:
                return
            version = self.pdf_doc._version
            file_path = self.pdf_doc.file_path
            try:
                doc_bytes = self.pdf_doc.doc.tobytes(deflate=True)
            except Exception as e:
                logger.error(f"Error extracting document bytes for auto-save: {e}")
                return
                
        # 3. Launch background process to save document
        if self._save_worker and self._save_worker.isRunning():
            self._pending_save = (file_path, doc_bytes, version)
            return
            
        self._save_worker = BackgroundSaveWorker(file_path, doc_bytes, version)
        self._save_worker.save_finished.connect(self._on_background_save_finished)
        self._save_worker.start()

    def _on_background_save_finished(self, success: bool, err_msg: str, version: int):
        if success:
            if self.pdf_doc and self.pdf_doc._version == version:
                self.pdf_doc.is_saved = True
                self.pdf_doc.is_dirty = False
                self.update_save_action_state()
                self.statusBar().showMessage("Document saved.", 2000)
        else:
            logger.error(f"Auto-save failed: {err_msg}")
            
        if hasattr(self, "_pending_save") and self._pending_save:
            file_path, doc_bytes, ver = self._pending_save
            self._pending_save = None
            self._save_worker = BackgroundSaveWorker(file_path, doc_bytes, ver)
            self._save_worker.save_finished.connect(self._on_background_save_finished)
            self._save_worker.start()
        else:
            self._save_worker = None

    def update_save_action_state(self):
        """Enable Save button only if the displayed document is not saved on disk."""
        if not self.pdf_doc or not self.pdf_doc.doc:
            self.save_btn.setEnabled(False)
        else:
            self.save_btn.setEnabled(not getattr(self.pdf_doc, "is_saved", True))

    def save_current_document(self):
        """Save the currently open document."""
        if not self.pdf_doc or not self.pdf_doc.doc:
            return
        if hasattr(self, "_save_worker") and self._save_worker and self._save_worker.isRunning():
            self._save_worker.wait()
            
        success, err = self.pdf_doc.save_document()
        if success:
            self.pdf_doc.is_saved = True
            self.pdf_doc.is_dirty = False
            self.update_save_action_state()
            self.statusBar().showMessage("Document saved successfully.", 3000)
            self.add_log("Document saved")
        else:
            QMessageBox.critical(self, "Error", f"Failed to save document: {err}")

    def maybe_save_prompt(self) -> bool:
        """Prompts user if document has unsaved changes. Returns True if okay to proceed, False if cancelled."""
        if not self.pdf_doc or not self.pdf_doc.doc or getattr(self.pdf_doc, "is_saved", True):
            return True
            
        filename = os.path.basename(self.pdf_doc.file_path) if self.pdf_doc.file_path else "Document"
        reply = QMessageBox.question(
            self, "Save Document",
            f"Do you want to save the changes made to '{filename}'?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )
        if reply == QMessageBox.StandardButton.Save:
            if hasattr(self, "_save_worker") and self._save_worker and self._save_worker.isRunning():
                self._save_worker.wait()
            success, err = self.pdf_doc.save_document()
            if not success:
                QMessageBox.critical(self, "Error", f"Failed to save document: {err}")
                return False
            self.update_save_action_state()
            return True
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def closeEvent(self, event):
        if not self.maybe_save_prompt():
            event.ignore()
            return
            
        # Collect all active / tracked threads for cleanup
        all_threads = list(self.zombie_threads)
        for attr in ("worker", "indexer", "startup_thread", "_save_worker"):
            t = getattr(self, attr, None)
            if t and self._is_thread_running(t):
                all_threads.append(t)
                
        for thread in all_threads:
            try:
                # Disconnect signals to avoid callbacks during shutdown
                for sig_name in ("result_ready", "error", "finished", "models_ranked", "save_finished"):
                    if hasattr(thread, sig_name):
                        try:
                            getattr(thread, sig_name).disconnect()
                        except Exception:
                            pass
                if thread.isRunning():
                    thread.quit()
                    if not thread.wait(3000):
                        thread.terminate()
                        thread.wait(500)
            except Exception as e:
                logger.error(f"Error during thread shutdown in closeEvent: {e}")
                
        self.zombie_threads.clear()
        self.worker = None
        self.indexer = None
        self.startup_thread = None
        self._save_worker = None

        # Release local AI models from memory (RAM / VRAM) on shutdown
        try:
            from backend.ai_assistant import release_local_ai_models
            from backend.config_manager import ConfigManager
            cfg = ConfigManager()
            release_local_ai_models(cfg.local_endpoint_url, cfg.local_model_name)
        except Exception as e:
            logger.debug(f"Failed to release local AI models on close: {e}")
        
        event.accept()

    def load_pdf(self, file_path):
        # Safely handle any running threads so they don't get destroyed mid-execution
        if self._is_thread_running(self.worker):
            thread = self.worker
            self.zombie_threads.add(thread)
            thread.finished.connect(lambda t=thread: self.zombie_threads.discard(t))
        self.worker = None

        if self._is_thread_running(self.indexer):
            thread = self.indexer
            self.zombie_threads.add(thread)
            thread.finished.connect(lambda t=thread: self.zombie_threads.discard(t))
        self.indexer = None
            
        # Clear previous PDF and UI state
        self.pdf_container.setCurrentIndex(0)
        self.pdf_doc.close()
        self.pdf_view.set_document(None)
        self.thumbnail_panel.set_document(None)
        
        self.chat_panel.setVisible(False)
        self.chat_panel.clear_chat()
        self.chat_panel.set_index_status("unloaded")
        self.ai_assistant.clear_index()
        self.ai_assistant.reset_client()
        self.excluded_pages.clear()
        self.included_pages.clear()
        
        if self.pdf_doc.load(file_path):
            self.pdf_container.setCurrentIndex(1)
            self.pdf_view.set_document(self.pdf_doc)
            self.thumbnail_panel.set_document(self.pdf_doc, self.excluded_pages, self.included_pages)
            self.thumbnail_panel.set_current_page(0)
            
            self.chat_panel.setVisible(True)
            if self.mode_action.isChecked():
                self.mode_action.setChecked(False)
                self.toggle_layout_mode(False)
            
            self.chat_panel.add_system_message(f"Loaded: {os.path.basename(file_path)}<br><br><b>Click the 'Index PDF' button below</b> to enable AI Q&A and text-selection features.")
            self.open_action.setText("Load another PDF")
            self.chat_panel.show_index_button()
            self.add_log(f"PDF loaded: {os.path.basename(file_path)}")
            self.update_save_action_state()
        else:
            self.update_save_action_state()
            QMessageBox.critical(self, "Error", "Failed to load PDF.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith(".pdf"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(".pdf"):
                if not self.maybe_save_prompt():
                    return
                if self.pdf_doc.doc:
                    reply = QMessageBox.question(
                        self, "Confirm Overwrite", 
                        "An article is already open. Do you want to close it and open the new article?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                        QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.load_pdf(file_path)
                else:
                    self.load_pdf(file_path)

    def prev_page(self):
        self.pdf_view.prev_page()
        self.thumbnail_panel.set_current_page(self.pdf_view.current_page)

    def next_page(self):
        self.pdf_view.next_page()
        self.thumbnail_panel.set_current_page(self.pdf_view.current_page)

    def go_to_page(self, page_index: int):
        self.pdf_view.set_current_page(page_index)
        self.thumbnail_panel.set_current_page(page_index)

    def delete_page(self, page_index: int):
        if not self.pdf_doc.doc:
            return
            
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete Page {page_index + 1}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.pdf_doc.delete_page(page_index):
                self.pdf_view.set_document(self.pdf_doc)
                self.thumbnail_panel.set_document(self.pdf_doc, self.excluded_pages, self.included_pages)
                
                new_page = min(page_index, self.pdf_doc.page_count - 1)
                if new_page >= 0:
                    self.pdf_view.set_current_page(new_page)
                    self.thumbnail_panel.set_current_page(new_page)
                    
                self.on_document_modified()
                self.statusBar().showMessage(f"Page {page_index + 1} deleted.", 3000)

    def index_current_document(self):
        if self.ai_assistant.provider == "cloud":
            api_key = keyring.get_password("AIPDFViewer", "api_key")
            if not api_key:
                self.chat_panel.add_system_message("Please configure Google API Key in Settings to enable AI features.")
                return

        # Check document size limits before indexing (CRIT-03)
        from backend.ai_assistant import MAX_PDF_FILE_SIZE_BYTES, MAX_PDF_PAGES, LARGE_DOCUMENT_ERROR_MESSAGE
        if self.pdf_doc and self.pdf_doc.doc:
            file_path = self.pdf_doc.file_path
            file_size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0
            page_count = len(self.pdf_doc.doc)
            if page_count > MAX_PDF_PAGES or file_size > MAX_PDF_FILE_SIZE_BYTES:
                QMessageBox.warning(
                    self,
                    "Document Too Large",
                    LARGE_DOCUMENT_ERROR_MESSAGE
                )
                self.chat_panel.set_index_status("unloaded")
                self.chat_panel.show_index_button()
                return
            
        if self._is_thread_running(self.indexer):
            thread = self.indexer
            self.zombie_threads.add(thread)
            thread.finished.connect(lambda t=thread: self.zombie_threads.discard(t))
        self.indexer = None
            
        self.last_ai_action = ("index", None)
        self.chat_panel.set_index_status("processing")
        file_path = self.pdf_doc.file_path
        
        self.indexer = IndexingThread(self.ai_assistant, file_path, self.excluded_pages, self.included_pages)
        self.indexer.indexing_finished.connect(self.on_indexing_finished)
        self.indexer.error.connect(self.on_indexing_error)
        self.indexer.start()
        
    def on_indexing_finished(self):
        if self.indexer:
            self.indexer.deleteLater()
            self.indexer = None
        if self.ai_assistant.provider == "cloud" and not getattr(self.ai_assistant, "chat_session", None):
            self.on_indexing_error("Indexing session could not be established.")
            return
        elif self.ai_assistant.provider == "local" and not getattr(self.ai_assistant, "local_document_text", None):
            self.on_indexing_error("Document text could not be extracted.")
            return
            
        model = self.ai_assistant.get_active_model_name()
        doc_tokens = 0
        if self.ai_assistant.provider == "local":
            doc_tokens = len(getattr(self.ai_assistant, "local_document_text", "") or "") // 4
        elif self.ai_assistant.provider == "cloud":
            if self.pdf_doc and self.pdf_doc.doc:
                doc_tokens = sum(len(page.get_text()) // 4 for page in self.pdf_doc.doc)
            else:
                doc_tokens = 1000
        self.chat_panel.set_document_tokens(doc_tokens)
        self.chat_panel.set_index_status("indexed", model)
        self.add_log(f"Document indexed successfully by {model}" if model else "Document indexed successfully")
        
    def on_indexing_error(self, error_msg: str):
        if self.indexer:
            self.indexer.deleteLater()
            self.indexer = None
        self.ai_assistant.clear_index()
        self.chat_panel.set_index_status("unloaded")
        self.chat_panel.show_index_button()
        self.chat_panel.add_system_message(f"Indexing failed: {error_msg}")

        # Check if document exceeded size limit (CRIT-03)
        from backend.ai_assistant import LARGE_DOCUMENT_ERROR_MESSAGE
        if "unable to treat these large documents" in error_msg.lower():
            QMessageBox.warning(
                self,
                "Document Too Large",
                LARGE_DOCUMENT_ERROR_MESSAGE
            )
            self.statusBar().showMessage(LARGE_DOCUMENT_ERROR_MESSAGE, 10000)
            return
        
        # Check if it's a quota error
        if "429" in error_msg or "Quota exceeded" in error_msg or "ResourceExhausted" in error_msg:
            import re
            match = re.search(r'retry in (\d+\.?\d*)s', error_msg)
            seconds = int(float(match.group(1))) if match else 60
            
            self.statusBar().showMessage(f"API Quota Exceeded. Please wait {seconds} seconds before trying again.", 10000)
            self.chat_panel.start_countdown(seconds)
        else:
            self.statusBar().showMessage(f"Indexing Error: {error_msg}", 10000)
        
    def on_models_ranked(self, ranked_models: list):
        if ranked_models:
            # If no model has been explicitly chosen by user, pick the top-ranked model
            if not self.config.model_name:
                best_model = ranked_models[0]["name"]
                self.ai_assistant.set_model_name(best_model)
                self.config.model_name = best_model

    def handle_text_action(self, action_type: str, text: str):
        # Ensure AI panel is open
        self.chat_panel.setVisible(True)
        if self.mode_action.isChecked():
            self.mode_action.setChecked(False)
            self.toggle_layout_mode(False)
        
        prompts_dict = self.prompts_manager.load_prompts()
        
        if action_type == "explain":
            display_title = "Explain Passage"
            prompt = f'Explain this passage:\n\n"{text}"\n\nPlease provide exactly 3 sections separated by "|||":\n1. Rephrase the paragraph in the context of the article\n|||\n2. Develop the reasoning in points\n|||\n3. Underline what this paragraph brings to the article\n\nDo not include any other text outside these sections.'
        elif action_type == "summary":
            display_title = "Bullet summary"
            base_prompt = prompts_dict.get("Bullet summary", "Succinctly create a bullet list of ideas summarizing the following paragraph:")
            prompt = f'{base_prompt}\n\n"{text}"'
        else:
            display_title = "Discuss Passage"
            prompt = f'Discuss this passage:\n\n"{text}"\n\nPlease rephrase the selected text in the context of the article and invite me to continue the discussion.'
            
        self.chat_panel.add_user_message(prompt)
        
        has_context = (self.ai_assistant.uploaded_file and getattr(self.ai_assistant, "chat_session", None)) if self.ai_assistant.provider == "cloud" else bool(getattr(self.ai_assistant, "local_document_text", None))
        if not has_context:
            self.chat_panel.add_system_message("Please click 'Index PDF to enable AI Q&A' below before using AI features that require document context.")
            self.chat_panel.show_index_button()
            return
            
        if self._is_thread_running(self.worker):
            thread = self.worker
            self.zombie_threads.add(thread)
            thread.finished.connect(lambda t=thread: self.zombie_threads.discard(t))
            self.worker = None

        self.last_ai_action = ("worker", {
            "question": prompt,
            "action_type": action_type,
            "use_direct": False,
            "original_prompt": prompt,
            "display_title": display_title
        })
        self.chat_panel.set_generating_state(True)
        self.worker = WorkerThread(self.ai_assistant, prompt, action_type, original_prompt=prompt, display_title=display_title)
        self.worker.result_ready.connect(self.on_ai_response)
        self.worker.chunk_ready.connect(self.chat_panel.append_stream_chunk)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        
    def handle_chat_message(self, text: str, is_custom: bool = False, display_title: str = ""):
        self.add_log("Prompt sent to AI model")
        if self._is_thread_running(self.worker):
            thread = self.worker
            self.zombie_threads.add(thread)
            thread.finished.connect(lambda t=thread: self.zombie_threads.discard(t))
            self.worker = None

        self.last_ai_action = ("worker", {
            "question": text,
            "action_type": "chat",
            "use_direct": is_custom,
            "original_prompt": text,
            "display_title": display_title
        })
        self.chat_panel.set_generating_state(True)
        if is_custom:
            self.worker = WorkerThread(self.ai_assistant, text, "chat", use_direct=True, original_prompt=text, display_title=display_title)
        else:
            self.worker = WorkerThread(self.ai_assistant, text, "chat", original_prompt=text, display_title=display_title)
            
        self.worker.result_ready.connect(self.on_ai_response)
        self.worker.chunk_ready.connect(self.chat_panel.append_stream_chunk)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        
    def retry_last_action(self):
        if not hasattr(self, "last_ai_action") or not self.last_ai_action:
            return
            
        action_kind, payload = self.last_ai_action
        if action_kind == "index":
            if self._is_thread_running(self.indexer):
                return
            self.index_current_document()
        elif action_kind == "worker" and payload:
            if self._is_thread_running(self.worker):
                return
            if not payload.get("use_direct"):
                has_context = (self.ai_assistant.uploaded_file and getattr(self.ai_assistant, "chat_session", None)) if self.ai_assistant.provider == "cloud" else bool(getattr(self.ai_assistant, "local_document_text", None))
                if not has_context:
                    self.chat_panel.add_system_message("Please index the document first before retrying.")
                    self.chat_panel.show_index_button()
                    return
                
            self.chat_panel.set_generating_state(True)
            self.add_log("Retrying AI request with the same model...")
            self.worker = WorkerThread(
                self.ai_assistant,
                payload["question"],
                payload["action_type"],
                use_direct=payload["use_direct"],
                original_prompt=payload["original_prompt"],
                display_title=payload["display_title"]
            )
            self.worker.result_ready.connect(self.on_ai_response)
            self.worker.chunk_ready.connect(self.chat_panel.append_stream_chunk)
            self.worker.error.connect(self.on_worker_error)
            self.worker.finished.connect(self._on_worker_finished)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.start()
        
    def on_worker_error(self, error_msg: str):
        self.chat_panel.set_generating_state(False)
        self.chat_panel.add_system_error(error_msg)
        self.statusBar().showMessage("AI Error occurred. See chat panel.", 10000)

    def on_ai_response(self, response: str, action_type: str, original_prompt: str, display_title: str):
        self.add_log("Response received from AI model")
        if action_type == "explain":
            parts = [p.strip() for p in response.split("|||") if p.strip()]
            self.chat_panel.add_explain_message(parts, original_prompt, display_title)
            
        elif action_type == "discuss":
            self.chat_panel.add_discuss_message(response, original_prompt, display_title)
            
        elif action_type == "summary":
            self.chat_panel.add_summary_message(response, original_prompt, display_title)
            
        else:
            self.chat_panel.add_ai_message(response, original_prompt, display_title)

    def save_markdown_response(self, msg_data: dict):
        import datetime
        import subprocess
        import sys
        
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        model = self.ai_assistant.get_active_model_name()
        pdf_name = os.path.splitext(os.path.basename(self.pdf_doc.file_path))[0] if hasattr(self.pdf_doc, 'file_path') and self.pdf_doc.file_path else "Unknown_PDF"
        
        default_name = f"{date_str} - {model} - {pdf_name}.md"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Markdown", default_name, "Markdown Files (*.md)")
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    title = msg_data.get("title", "")
                    prompt = msg_data.get("prompt", "")
                    
                    if title:
                        f.write(f"# {title}\n\n")
                    elif prompt:
                        f.write(f"# Prompt:\n{prompt}\n\n# Response:\n")
                        
                    content = msg_data.get("content", "")
                    
                    if msg_data.get("action") == "explain" and isinstance(content, list):
                        titles = ["Rephrase", "Reasoning", "Contribution"]
                        for i, part in enumerate(content):
                            title = titles[i] if i < len(titles) else f"Section {i+1}"
                            f.write(f"## {title}\n{part}\n\n")
                    else:
                        f.write(f"{content}\n")
                        
                # Open file explorer at location
                if sys.platform == "darwin":
                    subprocess.run(["open", "-R", file_path])
                elif sys.platform == "win32":
                    subprocess.run(["explorer", "/select,", os.path.normpath(file_path)])
                else:
                    subprocess.run(["xdg-open", os.path.dirname(file_path)])
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")

    def append_response_to_pdf(self, msg_data: dict):
        if not self.pdf_doc.doc:
            self.chat_panel.set_all_append_disabled(False)
            QMessageBox.warning(self, "No PDF", "No PDF document is currently open.")
            return
            
        current_file = self.pdf_doc.file_path
        if not current_file:
            self.chat_panel.set_all_append_disabled(False)
            QMessageBox.warning(self, "No PDF", "Cannot append to an unsaved PDF.")
            return
            
        title = msg_data.get("title", "")
        prompt = msg_data.get("prompt", "")
        content = msg_data.get("content", "")
        
        markdown_content = ""
        if title:
            markdown_content += f"# {title}\n\n"
        elif prompt:
            markdown_content += f"# Prompt\n{prompt}\n\n# Response\n"
        
        if msg_data.get("action") == "explain" and isinstance(content, list):
            titles = ["Rephrase", "Reasoning", "Contribution"]
            for i, part in enumerate(content):
                title = titles[i] if i < len(titles) else f"Section {i+1}"
                markdown_content += f"## {title}\n{part}\n\n"
        else:
            markdown_content += f"{content}\n"
            
        import datetime
        model = self.ai_assistant.get_active_model_name()
        date_str = datetime.datetime.now().strftime("%d/%m/%Y")
        footer = f"<p style='text-align: right; font-style: italic; color: grey; font-size: 9pt;'>Generated by {model} on {date_str}</p>"
        
        from backend.markdown_renderer import render_markdown
        parsed_html = render_markdown(markdown_content) + footer
        
        from PySide6.QtGui import QFont, QTextDocument
        doc = QTextDocument()
        doc.setDefaultFont(QFont(self.ai_font_family, int(self.ai_font_size)))
        doc.setHtml(parsed_html)
        
        import tempfile
        import os
        from PySide6.QtPrintSupport import QPrinter
        from PySide6.QtGui import QPageSize
        
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(temp_path)
        printer.setPageSize(QPageSize(QPageSize.A4))
        
        doc.print_(printer)
        
        merged, err_msg = self.pdf_doc.append_pdf_file(temp_path, current_file)
        if merged:
            self.chat_panel.add_system_message(f"Successfully appended response and saved as {os.path.basename(current_file)}")
            self.pdf_view.set_document(self.pdf_doc)
            self.thumbnail_panel.set_document(self.pdf_doc, self.excluded_pages, self.included_pages)
            last_page_idx = self.pdf_doc.page_count - 1
            if last_page_idx >= 0:
                self.pdf_view.set_current_page(last_page_idx)
        else:
            self.statusBar().showMessage(f"Failed to append PDF: {err_msg}", 10000)
            self.chat_panel.add_system_message("Failed to append the generated page to the PDF.")
            
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

    def add_log(self, message: str):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_list.addItem(f"[{timestamp}] {message}")
        self.log_list.scrollToBottom()
