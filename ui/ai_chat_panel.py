from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QComboBox, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtCore import Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices
import json
from ui.theme_manager import ThemeManager
from backend.markdown_renderer import render_markdown, escape_html
import urllib.parse

class ChatWebPage(QWebEnginePage):
    def __init__(self, panel, profile, parent=None):
        super().__init__(profile, parent)
        self.panel = panel

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        scheme = url.scheme()
        if scheme == "action":
            self.panel._handle_link_click(url)
            return False
        elif scheme in ("http", "https"):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, _type, isMainFrame)

class AIChatPanel(QWidget):
    message_sent = Signal(str, bool, str)
    stop_requested = Signal()
    open_prompts_dialog = Signal()
    save_requested = Signal(dict)
    index_requested = Signal()
    append_requested = Signal(dict)
    open_settings_requested = Signal()
    retry_requested = Signal()
    
    def __init__(self, parent=None, app_style="Native", color_mode="Light"):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.is_generating = False
        
        self.app_style = app_style
        self.color_mode = color_mode
        self.font_family = "Optima"
        self.font_size = 11
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 5, 0)
        
        # Status Bar
        self.status_bar = QLabel()
        self.status_bar.setAlignment(Qt.AlignmentFlag.AlignCenter if hasattr(Qt, 'AlignmentFlag') else Qt.AlignCenter)
        self.status_bar.setFixedHeight(20)
        layout.addWidget(self.status_bar)
        
        # Chat History via QWebEngineView
        self.web_view = QWebEngineView()
        self.web_page = ChatWebPage(self, QWebEngineProfile.defaultProfile(), self.web_view)
        self.web_view.setPage(self.web_page)
        layout.addWidget(self.web_view)
        
        self.raw_messages = []
        self.appended_indices = set()
        
        # Prompts Area (Above input)
        prompts_layout = QHBoxLayout()
        self.prompts_combo = QComboBox()
        
        from PySide6.QtWidgets import QStyledItemDelegate
        delegate = QStyledItemDelegate()
        self.prompts_combo.setItemDelegate(delegate)
        self.prompts_combo.setStyleSheet("""
            QComboBox QAbstractItemView::item {
                min-height: 14px;
                padding: 2px 4px;
                margin: 0px;
            }
        """)
        self.prompts_combo.addItem("--- Custom Input ---")
        
        self.manage_prompts_btn = QPushButton("🔧")
        self.manage_prompts_btn.setFixedWidth(40)
        self.manage_prompts_btn.setStyleSheet("background-color: #dcdcdc; color: #000000; border: none; border-radius: 4px; padding: 4px;")
        self.manage_prompts_btn.clicked.connect(self.open_prompts_dialog.emit)
        
        prompts_layout.addWidget(self.prompts_combo)
        prompts_layout.addWidget(self.manage_prompts_btn)
        
        # Input Area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask a question about the PDF...")
        self.input_field.returnPressed.connect(self._send_message)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet("background-color: #dcdcdc; color: #000000; font-weight: 500; border: none; border-radius: 4px; padding: 6px 12px;")
        self.send_btn.clicked.connect(self._send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(prompts_layout)
        
        self.index_btn = QPushButton("Index PDF to enable AI Q&A")
        self.index_btn.setStyleSheet("padding: 8px; background-color: #0078D7; color: white; font-weight: bold; border-radius: 4px; margin-bottom: 5px;")
        self.index_btn.clicked.connect(self._on_index_clicked)
        self.index_btn.setVisible(False)
        layout.addWidget(self.index_btn)
        
        layout.addLayout(input_layout)
        
        self.prompts_dict = {}
        self.document_tokens = 0
        
        self.prompts_combo.currentIndexChanged.connect(self._on_prompt_combo_changed)
        self.input_field.textChanged.connect(self._update_send_button_estimate)
        
        self.set_index_status("unloaded")
        self._refresh_chat_display()
        
    def _handle_link_click(self, url: QUrl):
        scheme = url.scheme()
        host = url.host()
        path = url.path().lstrip('/')
        
        if scheme == "action":
            if host == "open_ai_settings":
                self.open_settings_requested.emit()
            elif host in ("retry_last_query", "retry"):
                self.retry_requested.emit()
            elif host == "append":
                try:
                    idx = int(path)
                    if idx not in self.appended_indices:
                        self.appended_indices.add(idx)
                        self._request_append_message(idx)
                        self._refresh_chat_display()
                except ValueError:
                    pass
            elif host == "edit":
                try:
                    idx = int(path)
                    self._request_edit_message(idx)
                except ValueError:
                    pass
        else:
            QDesktopServices.openUrl(url)

    def _request_append_message(self, idx: int):
        if 0 <= idx < len(self.raw_messages):
            msg_data = self.raw_messages[idx]
            self.append_requested.emit(msg_data)
            
    def _request_edit_message(self, idx: int):
        if 0 <= idx < len(self.raw_messages):
            msg_data = self.raw_messages[idx]
            action = msg_data.get("action", "")
            if action in ["chat", "discuss", "summary"]:
                current_text = msg_data.get("content", "")
                
                from ui.edit_message_dialog import EditMessageDialog
                dialog = EditMessageDialog(current_text, self)
                if dialog.exec():
                    new_text = dialog.get_text()
                    if new_text != current_text:
                        msg_data["content"] = new_text
                        self._refresh_chat_display()
                        
    def update_font(self, font_family: str, font_size: int):
        self.update_theme(font_family=font_family, font_size=font_size)

    def update_theme(self, app_style: str = None, color_mode: str = None, font_family: str = None, font_size: int = None):
        if app_style is not None:
            self.app_style = app_style
        if color_mode is not None:
            self.color_mode = color_mode
        if font_family is not None:
            self.font_family = font_family
        if font_size is not None:
            self.font_size = font_size
            
        self._refresh_chat_display()

    def _get_button_html(self, idx: int):
        is_appended = idx in self.appended_indices
        
        edit_btn = f'<a href="action://edit/{idx}" style="text-decoration:none; color:#1a73e8; font-size:12px; margin-right:15px; font-weight:bold;">[✎ Edit Response]</a>'
        
        if is_appended:
            append_btn = f'<span style="color:#777; font-size:12px; font-weight:bold;">[✓ Appended]</span>'
        else:
            append_btn = f'<a href="action://append/{idx}" style="text-decoration:none; color:#1a73e8; font-size:12px; font-weight:bold;">[+ Append to PDF]</a>'
            
        return f'<div style="margin-top:10px;">{edit_btn} {append_btn}</div>'

    def _refresh_chat_display(self):
        p = ThemeManager.get_palette(self.app_style, self.color_mode)
        font = f"font-family: '{self.font_family}'; font-size: {self.font_size}pt;"
        
        # Build HTML content
        html_parts = []
        katex_head = """
        <head>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
            <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
        </head>
        """
        html_parts.append(f"<!DOCTYPE html>\n<html>{katex_head}<body style=\"{font} background-color: {p['bg_card']}; margin: 5px; word-wrap: break-word;\">")
        
        for idx, msg in enumerate(self.raw_messages):
            sender = msg.get("sender", "ai")
            action = msg.get("action", "chat")
            
            if sender == "user":
                html_parts.append(f'''
                <div style="display: flex; justify-content: flex-end; margin-bottom: 15px;">
                    <div style="background-color: {p["chat_user_bg"]}; color: {p["chat_user_text"]}; padding: 10px; border-radius: 12px 12px 0 12px; max-width: 80%; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        <b>You:</b><br>{escape_html(msg.get("content", ""))}
                    </div>
                </div>
                ''')
            elif sender == "system":
                html_parts.append(f'''
                <div style="text-align: center; margin-bottom: 15px;">
                    <span style="color: {p["text_secondary"]}; font-style: italic; font-size: 9pt;">
                        {msg.get("content", "")}
                    </span>
                </div>
                ''')
            else:
                content = msg.get("content", "")
                bubble_content = ""
                
                if action == "chat":
                    bubble_content = f"<b>AI:</b><br>{render_markdown(content)}<br>{self._get_button_html(idx)}"
                    
                elif action == "discuss":
                    bubble_content = f"<b>AI Discuss:</b><br>"
                    bubble_content += f'<div style="background-color: {p["bg_panel"]}; border: 1px solid {p["accent"]}; border-radius: 8px; margin-top: 5px; padding: 10px;">'
                    bubble_content += render_markdown(content)
                    bubble_content += f'</div><br>{self._get_button_html(idx)}'
                    
                elif action == "summary":
                    bubble_content = f"<b>AI Summary:</b><br>"
                    bubble_content += f'<div style="background-color: {p["chat_ai_bg"]}; border: 1px solid {p["border"]}; border-radius: 8px; margin-top: 5px; padding: 10px;">'
                    bubble_content += render_markdown(content)
                    bubble_content += f'</div><br>{self._get_button_html(idx)}'
                    
                elif action == "explain":
                    bubble_content = f"<b>AI Explain:</b><br>"
                    parts = content if isinstance(content, list) else [content]
                    titles = ["Rephrase", "Reasoning", "Contribution"]
                    for i, part in enumerate(parts):
                        title = titles[i] if i < len(titles) else f"Section {i+1}"
                        bubble_content += f'<div style="background-color: {p["chat_ai_bg"]}; border: 1px solid {p["border"]}; border-radius: 8px; margin-top: 5px; padding: 10px;">'
                        bubble_content += f'<b>{title}</b><br>{render_markdown(part)}'
                        bubble_content += f'</div>'
                    
                    bubble_content += f'<br><a href="action://append/{idx}" style="text-decoration:none; color:#1a73e8; font-size:12px; font-weight:bold;">[+ Append to PDF]</a>'
                
                html_parts.append(f'''
                <div style="display: flex; justify-content: flex-start; margin-bottom: 15px;">
                    <div style="background-color: {p["chat_ai_bg"]}; color: {p["chat_ai_text"]}; border: 1px solid {p["border_subtle"]}; padding: 10px; border-radius: 12px 12px 12px 0; max-width: 90%; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        {bubble_content}
                    </div>
                </div>
                ''')
                
        if self.is_generating:
            html_parts.append(f'''
            <div style="display: flex; justify-content: flex-start; margin-bottom: 15px;">
                <div style="background-color: {p["chat_ai_bg"]}; color: {p["chat_ai_text"]}; border: 1px solid {p["border_subtle"]}; padding: 10px; border-radius: 12px 12px 12px 0; max-width: 90%; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div id="streaming-bubble"><i>AI is generating...</i></div>
                </div>
            </div>
            ''')
            
        html_parts.append("""
        <script>
            function tryRenderMath() {
                if (window.renderMathInElement) {
                    renderMathInElement(document.body, {
                        delimiters: [
                            {left: '$$', right: '$$', display: true},
                            {left: '$', right: '$', display: false}
                        ],
                        throwOnError: false
                    });
                } else {
                    setTimeout(tryRenderMath, 50);
                }
            }
            tryRenderMath();
        </script>
        </body></html>
        """)
        
        self.web_view.setHtml("".join(html_parts))
        
        # Scroll to bottom using Javascript
        self.web_view.page().runJavaScript("window.scrollTo(0, document.body.scrollHeight);")

    def _on_index_clicked(self):
        self.index_btn.setVisible(False)
        self.index_requested.emit()

    def show_index_button(self):
        self.index_btn.setVisible(True)

    def set_document_tokens(self, tokens: int):
        self.document_tokens = max(0, tokens)
        self.update_estimated_times()
        
    def set_index_status(self, status: str, model_name: str = ""):
        is_indexed = (status == "indexed")
        self.prompts_combo.setVisible(is_indexed)
        self.manage_prompts_btn.setVisible(is_indexed)
        self.input_field.setVisible(is_indexed)
        self.send_btn.setVisible(is_indexed)
        
        if status == "unloaded":
            self.document_tokens = 0
            self.status_bar.setText("Status: Not Indexed")
            self.status_bar.setStyleSheet("background-color: #E81123; color: white; padding: 2px; font-size: 9pt; font-weight: bold;")
        elif status == "processing":
            self.status_bar.setText("Status: Indexing in progress...")
            self.status_bar.setStyleSheet("background-color: #F2A900; color: white; padding: 2px; font-size: 9pt; font-weight: bold;")
        elif status == "indexed":
            text = f"Indexed by {model_name}" if model_name else "Indexed"
            self.status_bar.setText(text)
            self.status_bar.setStyleSheet("background-color: #107C10; color: white; padding: 2px; font-size: 9pt; font-weight: bold;")
        
        self.update_estimated_times()
        
    def set_prompts(self, prompts: dict):
        self.prompts_dict = prompts
        self.update_estimated_times()

    def update_estimated_times(self):
        from backend.config_manager import ConfigManager
        from backend.ai_assistant import estimate_response_time_seconds, format_estimated_duration
        
        cfg = ConfigManager()
        provider = cfg.ai_provider
        model_name = cfg.local_model_name if provider == "local" else (cfg.model_name or "gemini-flash-lite-latest")

        current_key = self.prompts_combo.currentData()
        self.prompts_combo.blockSignals(True)
        self.prompts_combo.clear()
        self.prompts_combo.addItem("--- Custom Input ---", "")
        
        for k, v in self.prompts_dict.items():
            if self.document_tokens > 0:
                prompt_tokens = len(v) // 4
                est_sec = estimate_response_time_seconds(provider, model_name, self.document_tokens, prompt_tokens, prompt_text=v)
                est_str = format_estimated_duration(est_sec)
                display_label = f"{k} ({est_str})" if est_str else k
            else:
                display_label = k
            self.prompts_combo.addItem(display_label, k)
            
        if current_key:
            idx = self.prompts_combo.findData(current_key)
            if idx >= 0:
                self.prompts_combo.setCurrentIndex(idx)
        self.prompts_combo.blockSignals(False)

        self._update_send_button_estimate()

    def _on_prompt_combo_changed(self, index: int):
        is_custom = (index <= 0)
        self.input_field.setEnabled(is_custom)
        if not is_custom:
            self.input_field.setPlaceholderText("Predefined prompt selected above...")
        else:
            self.input_field.setPlaceholderText("Ask a question about the PDF...")
        self._update_send_button_estimate()

    def _update_send_button_estimate(self):
        if getattr(self, 'is_generating', False):
            self.send_btn.setText("Stop")
            self.send_btn.setToolTip("")
            return

        from backend.config_manager import ConfigManager
        from backend.ai_assistant import estimate_response_time_seconds, format_estimated_duration
        
        cfg = ConfigManager()
        provider = cfg.ai_provider
        model_name = cfg.local_model_name if provider == "local" else (cfg.model_name or "gemini-flash-lite-latest")

        if self.document_tokens <= 0:
            self.send_btn.setText("Send")
            self.send_btn.setToolTip("Send question to AI assistant")
            return

        if self.prompts_combo.currentIndex() > 0:
            key = self.prompts_combo.currentData()
            prompt_text = self.prompts_dict.get(key, "")
        else:
            prompt_text = self.input_field.text().strip()

        prompt_tokens = len(prompt_text) // 4
        est_sec = estimate_response_time_seconds(provider, model_name, self.document_tokens, prompt_tokens, prompt_text=prompt_text)
        est_str = format_estimated_duration(est_sec)

        if est_str == "NA":
            self.send_btn.setText("Send (NA)")
            self.send_btn.setToolTip("Estimated response time: NA")
        elif est_str:
            self.send_btn.setText(f"Send ({est_str})")
            self.send_btn.setToolTip(f"Estimated response time: {est_str}")
        else:
            self.send_btn.setText("Send")
            self.send_btn.setToolTip("Send question to AI assistant")
        
    def set_generating_state(self, is_generating: bool):
        self.is_generating = is_generating
        self.prompts_combo.setEnabled(not is_generating)
        self.input_field.setEnabled(not is_generating and self.prompts_combo.currentIndex() <= 0)
        
        if is_generating:
            self._stream_buffer = ""
            self.send_btn.setText("Stop")
            self.send_btn.setStyleSheet("background-color: #e81123; color: #ffffff; font-weight: 500; border: none; border-radius: 4px; padding: 6px 12px;")
            self._refresh_chat_display()
        else:
            self._stream_buffer = ""
            self.send_btn.setStyleSheet("background-color: #dcdcdc; color: #000000; font-weight: 500; border: none; border-radius: 4px; padding: 6px 12px;")
            self._update_send_button_estimate()
            self._refresh_chat_display()

    def append_stream_chunk(self, chunk: str):
        if not hasattr(self, "_stream_buffer"):
            self._stream_buffer = ""
        self._stream_buffer += chunk
        
        from backend.markdown_renderer import render_markdown
        html_chunk = render_markdown(self._stream_buffer)
        
        escaped_html = json.dumps(html_chunk)
        js = f"""
        var bubble = document.getElementById('streaming-bubble');
        if (bubble) {{
            bubble.innerHTML = {escaped_html};
            if (window.renderMathInElement) {{
                renderMathInElement(bubble, {{
                    delimiters: [
                        {{left: '$$', right: '$$', display: true}},
                        {{left: '$', right: '$', display: false}}
                    ],
                    throwOnError: false
                }});
            }}
            window.scrollTo(0, document.body.scrollHeight);
        }}
        """
        self.web_view.page().runJavaScript(js)

    def _send_message(self):
        if self.is_generating:
            self.stop_requested.emit()
            self.add_system_message("Stopped by the user")
            self.set_generating_state(False)
            return

        text = ""
        is_custom = False
        display_text = ""
        
        if self.prompts_combo.currentIndex() > 0:
            key = self.prompts_combo.currentData()
            text = self.prompts_dict.get(key, "")
            is_custom = True
            display_text = key
        else:
            text = self.input_field.text().strip()
            display_text = text
            
        if text:
            self.add_user_message(display_text)
            
            if not is_custom:
                self.input_field.clear()
                
            self.prompts_combo.setCurrentIndex(0)
            self.set_generating_state(True)
            self.message_sent.emit(text, is_custom, display_text if is_custom else "")
            
    def add_user_message(self, message: str):
        self.raw_messages.append({"sender": "user", "content": message})
        self._refresh_chat_display()
        
    def add_ai_message(self, message: str, original_prompt: str = "", display_title: str = ""):
        self.raw_messages.append({"sender": "ai", "action": "chat", "content": message, "prompt": original_prompt, "title": display_title})
        self.set_generating_state(False)

    def add_explain_message(self, parts: list, original_prompt: str = "", display_title: str = ""):
        self.raw_messages.append({"sender": "ai", "action": "explain", "content": parts, "prompt": original_prompt, "title": display_title})
        self.set_generating_state(False)
        
    def add_discuss_message(self, text: str, original_prompt: str = "", display_title: str = ""):
        self.raw_messages.append({"sender": "ai", "action": "discuss", "content": text, "prompt": original_prompt, "title": display_title})
        self.set_generating_state(False)

    def add_summary_message(self, text: str, original_prompt: str = "", display_title: str = ""):
        self.raw_messages.append({"sender": "ai", "action": "summary", "content": text, "prompt": original_prompt, "title": display_title})
        self.set_generating_state(False)

    def add_system_message(self, message: str):
        self.raw_messages.append({"sender": "system", "content": message})
        self._refresh_chat_display()

    def clear_chat(self):
        self.raw_messages = []
        self.appended_indices.clear()
        self.index_btn.setVisible(False)
        self._refresh_chat_display()

    def set_all_append_disabled(self, disabled: bool):
        # We handle disables per item now, this could be a no-op 
        # or we could clear all if needed. For now, leave it no-op.
        pass
