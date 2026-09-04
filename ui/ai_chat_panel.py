from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QComboBox, QDialog, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtCore import Signal, Qt
import json
from ui.theme_manager import ThemeManager
from ui.asset_loader import get_assets_base_url

class ChatWebPage(QWebEnginePage):
    double_clicked_idx = Signal(int)
    append_pdf_idx = Signal(int)
    edit_msg_idx = Signal(int)
    open_settings_requested = Signal()
    retry_requested = Signal()
    
    def acceptNavigationRequest(self, url, _type, isMainFrame):
        if url.scheme() == "action":
            if url.host() == "open_ai_settings":
                self.open_settings_requested.emit()
                return False
            elif url.host() in ("retry_last_query", "retry"):
                self.retry_requested.emit()
                return False
        return super().acceptNavigationRequest(url, _type, isMainFrame)
        
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        if message.startswith("DOUBLE_CLICK_IDX:"):
            try:
                idx = int(message.split(":")[1])
                self.double_clicked_idx.emit(idx)
            except:
                pass
            return
        if message.startswith("APPEND_PDF_IDX:"):
            try:
                idx = int(message.split(":")[1])
                self.append_pdf_idx.emit(idx)
            except:
                pass
            return
        if message.startswith("EDIT_MSG_IDX:"):
            try:
                idx = int(message.split(":")[1])
                self.edit_msg_idx.emit(idx)
            except:
                pass
            return
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceId)

class AIChatPanel(QWidget):
    message_sent = Signal(str, bool, str)
    open_prompts_dialog = Signal()
    save_requested = Signal(dict)
    index_requested = Signal()
    append_requested = Signal(dict)
    open_settings_requested = Signal()
    retry_requested = Signal()
    
    def __init__(self, parent=None, app_style="Native macOS", color_mode="Light"):
        super().__init__(parent)
        self.setMinimumWidth(0)
        
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
        
        # Chat History via WebEngine
        self.web_view = QWebEngineView()
        self.web_page = ChatWebPage(self.web_view)
        self.web_page.double_clicked_idx.connect(self.request_save_message)
        self.web_page.append_pdf_idx.connect(self.request_append_message)
        self.web_page.edit_msg_idx.connect(self.request_edit_message)
        self.web_page.open_settings_requested.connect(self.open_settings_requested)
        self.web_page.retry_requested.connect(self.retry_requested)
        self.web_view.setPage(self.web_page)
        self.web_view.setHtml(self._get_html_template(), get_assets_base_url())
        layout.addWidget(self.web_view)
        
        self.raw_messages = []
        
        # Prompts Area (Above input)
        prompts_layout = QHBoxLayout()
        self.prompts_combo = QComboBox()
        
        # Override qt-material's custom delegate to restore compact native spacing
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
        
        self.set_index_status("unloaded")
        
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
            
        css = ThemeManager.get_chat_css(self.app_style, self.color_mode, self.font_family, self.font_size)
        css_escaped = css.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        js = f"""
        (function() {{
            let styleTag = document.getElementById('custom-theme-style');
            if (!styleTag) {{
                styleTag = document.createElement('style');
                styleTag.id = 'custom-theme-style';
                document.head.appendChild(styleTag);
            }}
            styleTag.textContent = `{css_escaped}`;
        }})();
        """
        self.web_view.page().runJavaScript(js)
        
    def _on_index_clicked(self):
        self.index_btn.setVisible(False)
        self.index_requested.emit()

    def show_index_button(self):
        self.index_btn.setVisible(True)
        
    def set_index_status(self, status: str, model_name: str = ""):
        is_indexed = (status == "indexed")
        self.prompts_combo.setVisible(is_indexed)
        self.manage_prompts_btn.setVisible(is_indexed)
        self.input_field.setVisible(is_indexed)
        self.send_btn.setVisible(is_indexed)
        
        if status == "unloaded":
            self.status_bar.setText("Status: Not Indexed")
            self.status_bar.setStyleSheet("background-color: #E81123; color: white; padding: 2px; font-size: 9pt; font-weight: bold;")
        elif status == "processing":
            self.status_bar.setText("Status: Indexing in progress...")
            self.status_bar.setStyleSheet("background-color: #F2A900; color: white; padding: 2px; font-size: 9pt; font-weight: bold;")
        elif status == "indexed":
            text = f"Indexed by {model_name}" if model_name else "Indexed"
            self.status_bar.setText(text)
            self.status_bar.setStyleSheet("background-color: #107C10; color: white; padding: 2px; font-size: 9pt; font-weight: bold;")
        
    def set_prompts(self, prompts: dict):
        self.prompts_dict = prompts
        self.prompts_combo.clear()
        self.prompts_combo.addItem("--- Custom Input ---")
        self.prompts_combo.addItems(list(prompts.keys()))
        
    def _send_message(self):
        text = ""
        is_custom = False
        
        if self.prompts_combo.currentIndex() > 0:
            expr = self.prompts_combo.currentText()
            text = self.prompts_dict.get(expr, "")
            is_custom = True
        else:
            text = self.input_field.text().strip()
            
        if text:
            # If it's a custom predefined prompt, show the expression instead of the huge prompt text
            display_text = self.prompts_combo.currentText() if is_custom else text
            self.add_user_message(display_text)
            
            if not is_custom:
                self.input_field.clear()
                
            # Automatically switch back to "--- Custom Input ---"
            self.prompts_combo.setCurrentIndex(0)
                
            self.show_loading()
            self.message_sent.emit(text, is_custom, display_text if is_custom else "")
            
    def show_loading(self):
        self.web_view.page().runJavaScript("showLoading();")
        
    def hide_loading(self):
        self.web_view.page().runJavaScript("hideLoading();")
            
    def _get_html_template(self):
        import secrets
        self.csp_nonce = secrets.token_hex(16)
        chat_css = ThemeManager.get_chat_css(self.app_style, self.color_mode, self.font_family, self.font_size)
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-eval' 'nonce-{self.csp_nonce}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:;">
            <script src="marked.min.js"></script>
            <script src="purify.min.js"></script>
            <script nonce="{self.csp_nonce}">
            window.MathJax = {{
                tex: {{
                    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                    processEscapes: true
                }},
                options: {{
                    ignoreHtmlClass: 'tex2jax_ignore',
                    processHtmlClass: 'tex2jax_process'
                }}
            }};
            </script>
            <script src="tex-mml-chtml.js" integrity="sha384-Wuix6BuhrWbjDBs24bXrjf4ZQ5aFeFWBuKkFekO2t8xFU0iNaLQfp2K6/1Nxveei" crossorigin="anonymous"></script>
            <style id="custom-theme-style">
                __CHAT_CSS__
                .loading-indicator {{
                    font-style: italic;
                    color: #888;
                }}
                .dots::after {{
                    content: '';
                    animation: dots 1.5s steps(4, end) infinite;
                }}
                @keyframes dots {{
                    0%, 20% {{ content: ''; }}
                    40% {{ content: '.'; }}
                    60% {{ content: '..'; }}
                    80%, 100% {{ content: '...'; }}
                }}
            </style>
            <script nonce="{self.csp_nonce}">
                document.addEventListener('DOMContentLoaded', () => {{
                    const container = document.getElementById('chat-container');
                    if (container) {{
                        container.addEventListener('click', (e) => {{
                            const target = e.target.closest('button[data-action]');
                            if (!target || target.disabled) return;
                            const action = target.getAttribute('data-action');
                            const idx = target.getAttribute('data-idx');
                            if (action === 'edit') {{
                                console.log('EDIT_MSG_IDX:' + idx);
                            }} else if (action === 'append') {{
                                target.disabled = true;
                                target.style.opacity = '0.5';
                                target.style.cursor = 'not-allowed';
                                console.log('APPEND_PDF_IDX:' + idx);
                            }}
                        }});
                    }}
                }});

                function setAppendDisabled(idx, disabled) {{
                    const btn = document.querySelector(`button[data-action="append"][data-idx="${{idx}}"]`);
                    if (btn) {{
                        btn.disabled = disabled;
                        btn.style.opacity = disabled ? '0.5' : '1.0';
                        btn.style.cursor = disabled ? 'not-allowed' : 'pointer';
                    }}
                }}

                function renderMarkdownSafe(text) {{
                    if (!window.DOMPurify) {{
                        console.error("Security Error: DOMPurify is not available. Markdown rendering aborted.");
                        return escapeHtml(text);
                    }}
                    if (window.marked) {{
                        return DOMPurify.sanitize(marked.parse(text));
                    }}
                    return DOMPurify.sanitize(text);
                }}

                function sanitizeText(text) {{
                    if (!window.DOMPurify) {{
                        console.error("Security Error: DOMPurify is not available. Raw text sanitization aborted.");
                        return escapeHtml(text);
                    }}
                    return DOMPurify.sanitize(text);
                }}

                function escapeHtml(str) {{
                    if (typeof str !== 'string') return '';
                    return str.replace(/[&<>"']/g, function(m) {{
                        return {{
                            '&': '&amp;',
                            '<': '&lt;',
                            '>': '&gt;',
                            '"': '&quot;',
                            "'": '&#39;'
                        }}[m];
                    }});
                }}

                function showLoading() {{
                    hideLoading();
                    const container = document.getElementById('chat-container');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message ai-message loading-indicator';
                    msgDiv.id = 'loading-indicator';
                    msgDiv.innerHTML = '<b>AI is generating</b><span class="dots"></span>';
                    container.appendChild(msgDiv);
                    window.scrollTo(0, document.body.scrollHeight);
                }}
                function hideLoading() {{
                    const el = document.getElementById('loading-indicator');
                    if (el) el.remove();
                }}

                function startCountdown(seconds) {{
                    hideLoading();
                    const container = document.getElementById('chat-container');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message system-message';
                    msgDiv.id = 'countdown-' + Date.now();
                    
                    let timeLeft = seconds;
                    let displayTime = timeLeft > 60 ? Math.ceil(timeLeft/60) + ' minutes' : timeLeft + ' seconds';
                    msgDiv.innerHTML = `<b>API Quota Exceeded!</b><br>Please wait <span class='countdown-timer'>${{displayTime}}</span> before trying again.<br><i>Tip: You can switch to another model.</i>`;
                    container.appendChild(msgDiv);
                    window.scrollTo(0, document.body.scrollHeight);
                    
                    const timerSpan = msgDiv.querySelector('.countdown-timer');
                    const interval = setInterval(() => {{
                        timeLeft--;
                        if (timeLeft <= 0) {{
                            clearInterval(interval);
                            msgDiv.innerHTML = `<b>Ready!</b><br>You can try asking your question again, or switch models if the daily limit was reached.`;
                        }} else {{
                            if (timerSpan) {{
                                timerSpan.innerText = timeLeft > 60 ? Math.ceil(timeLeft/60) + ' minutes' : timeLeft + ' seconds';
                            }}
                        }}
                    }}, 1000);
                }}
                
                function addSystemError(errorMsg, allowRetry) {{
                    hideLoading();
                    const container = document.getElementById('chat-container');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message system-message';
                    const safeError = window.DOMPurify ? DOMPurify.sanitize(errorMsg, {{ALLOWED_TAGS: [], ALLOWED_ATTR: []}}) : escapeHtml(errorMsg);
                    let retryHtml = '';
                    if (allowRetry !== false && errorMsg && errorMsg.indexOf('503') !== -1) {{
                        retryHtml = ' or <a href="action://retry_last_query" style="color:#1a73e8; text-decoration:underline;">retry with the same model</a>';
                    }}
                    msgDiv.innerHTML = `<div style="color:#d93025; margin-bottom: 10px;"><b>Error:</b> ${{safeError}}<br><br>You can change the model <a href="action://open_ai_settings" style="color:#1a73e8; text-decoration:underline;">here</a>${{retryHtml}}.</div>`;
                    container.appendChild(msgDiv);
                    window.scrollTo(0, document.body.scrollHeight);
                }}

                function addMessage(sender, text, isMarkdown, idx) {{
                    const container = document.getElementById('chat-container');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message ' + sender + '-message';
                    
                    if (idx !== undefined && idx !== null) {{
                        msgDiv.id = 'msg-' + idx;
                        msgDiv.ondblclick = function() {{
                            console.log("DOUBLE_CLICK_IDX:" + idx);
                        }};
                        msgDiv.style.cursor = "pointer";
                        msgDiv.title = "Double-click to open in new window";
                    }}
                    
                    if (sender === 'user') {{
                        msgDiv.innerHTML = '<b>You:</b> ' + sanitizeText(text);
                    }} else if (sender === 'system') {{
                        msgDiv.innerHTML = sanitizeText(text);
                    }} else {{
                        // AI Message
                        let html = '<b>AI:</b><br>';
                        if (isMarkdown) {{
                            html += renderMarkdownSafe(text);
                        }} else {{
                            html += sanitizeText(text);
                        }}
                        if (idx !== undefined && idx !== null) {{
                            html += `<br><button data-action="edit" data-idx="${{idx}}" style="margin-top:8px; margin-right:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Edit Response</button>`;
                            html += `<button data-action="append" data-idx="${{idx}}" style="margin-top:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Append to PDF</button>`;
                        }}
                        msgDiv.innerHTML = html;
                    }}
                    
                    container.appendChild(msgDiv);
                    triggerMathJax();
                }}
                
                function addExplainMessage(parts, idx) {{
                    const container = document.getElementById('chat-container');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message ai-message';
                    
                    if (idx !== undefined && idx !== null) {{
                        msgDiv.ondblclick = function() {{
                            console.log("DOUBLE_CLICK_IDX:" + idx);
                        }};
                        msgDiv.style.cursor = "pointer";
                        msgDiv.title = "Double-click to open in new window";
                    }}
                    
                    let html = '<b>AI Explain:</b><br>';
                    const titles = ["Rephrase", "Reasoning", "Contribution"];
                    
                    for (let i = 0; i < parts.length; i++) {{
                        let title = i < titles.length ? titles[i] : 'Section ' + (i+1);
                        let parsedPart = renderMarkdownSafe(parts[i]);
                        html += `<div class='explain-section'><b>${{title}}</b><br>${{parsedPart}}</div>`;
                    }}
                    if (idx !== undefined && idx !== null) {{
                        html += `<br><button data-action="append" data-idx="${{idx}}" style="margin-top:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Append to PDF</button>`;
                    }}
                    
                    msgDiv.innerHTML = html;
                    container.appendChild(msgDiv);
                    triggerMathJax();
                }}
                
                function addDiscussMessage(text, idx) {{
                    const container = document.getElementById('chat-container');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message ai-message';
                    
                    if (idx !== undefined && idx !== null) {{
                        msgDiv.id = 'msg-' + idx;
                        msgDiv.ondblclick = function() {{
                            console.log("DOUBLE_CLICK_IDX:" + idx);
                        }};
                        msgDiv.style.cursor = "pointer";
                        msgDiv.title = "Double-click to open in new window";
                    }}
                    
                    let parsedText = renderMarkdownSafe(text);
                    let html = `<b>AI Discuss:</b><br><div class='discuss-section'>${{parsedText}}</div>`;
                    if (idx !== undefined && idx !== null) {{
                        html += `<br><button data-action="edit" data-idx="${{idx}}" style="margin-top:8px; margin-right:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Edit Response</button>`;
                        html += `<button data-action="append" data-idx="${{idx}}" style="margin-top:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Append to PDF</button>`;
                    }}
                    
                    msgDiv.innerHTML = html;
                    container.appendChild(msgDiv);
                    triggerMathJax();
                }}
                
                function addSummaryMessage(text, idx) {{
                    const container = document.getElementById('chat-container');
                    const msgDiv = document.createElement('div');
                    msgDiv.className = 'message ai-message';
                    
                    if (idx !== undefined && idx !== null) {{
                        msgDiv.id = 'msg-' + idx;
                        msgDiv.ondblclick = function() {{
                            console.log("DOUBLE_CLICK_IDX:" + idx);
                        }};
                        msgDiv.style.cursor = "pointer";
                        msgDiv.title = "Double-click to open in new window";
                    }}
                    
                    let parsedText = renderMarkdownSafe(text);
                    let html = `<b>AI Summary:</b><br><div class='summary-section'>${{parsedText}}</div>`;
                    if (idx !== undefined && idx !== null) {{
                        html += `<br><button data-action="edit" data-idx="${{idx}}" style="margin-top:8px; margin-right:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Edit Response</button>`;
                        html += `<button data-action="append" data-idx="${{idx}}" style="margin-top:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Append to PDF</button>`;
                    }}
                    
                    msgDiv.innerHTML = html;
                    container.appendChild(msgDiv);
                    triggerMathJax();
                }}
                
                function updateMessage(idx, newText, msgType) {{
                    const msgDiv = document.getElementById('msg-' + idx);
                    if (!msgDiv) return;
                    
                    let html = '<b>AI' + (msgType === "chat" ? "" : " " + msgType.charAt(0).toUpperCase() + msgType.slice(1)) + ':</b><br>';
                    let parsedText = renderMarkdownSafe(newText);
                    
                    if (msgType === "discuss") {{
                        html += `<div class='discuss-section'>${{parsedText}}</div>`;
                    }} else if (msgType === "summary") {{
                        html += `<div class='summary-section'>${{parsedText}}</div>`;
                    }} else {{
                        html += parsedText;
                    }}
                    
                    html += `<br><button data-action="edit" data-idx="${{idx}}" style="margin-top:8px; margin-right:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Edit Response</button>`;
                    html += `<button data-action="append" data-idx="${{idx}}" style="margin-top:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Append to PDF</button>`;
                    
                    msgDiv.innerHTML = html;
                    triggerMathJax();
                }}

                function triggerMathJax() {{
                    if (window.MathJax) {{
                        MathJax.typesetPromise().then(() => {{
                            window.scrollTo(0, document.body.scrollHeight);
                        }}).catch((err) => console.log(err.message));
                    }}
                    window.scrollTo(0, document.body.scrollHeight);
                }}
            </script>
        </head>
        <body>
            <div id="chat-container"></div>
        </body>
        </html>
        """
        return html.replace("__CHAT_CSS__", chat_css)

    def add_user_message(self, message: str):
        js = f"addMessage('user', {json.dumps(message)}, false);"
        self.web_view.page().runJavaScript(js)
        
    def add_ai_message(self, message: str, original_prompt: str = "", display_title: str = ""):
        self.hide_loading()
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "chat", "content": message, "prompt": original_prompt, "title": display_title})
        js = f"addMessage('ai', {json.dumps(message)}, true, {idx});"
        self.web_view.page().runJavaScript(js)

    def add_explain_message(self, parts: list, original_prompt: str = "", display_title: str = ""):
        self.hide_loading()
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "explain", "content": parts, "prompt": original_prompt, "title": display_title})
        js = f"addExplainMessage({json.dumps(parts)}, {idx});"
        self.web_view.page().runJavaScript(js)
        
    def add_discuss_message(self, text: str, original_prompt: str = "", display_title: str = ""):
        self.hide_loading()
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "discuss", "content": text, "prompt": original_prompt, "title": display_title})
        js = f"addDiscussMessage({json.dumps(text)}, {idx});"
        self.web_view.page().runJavaScript(js)

    def add_summary_message(self, text: str, original_prompt: str = "", display_title: str = ""):
        self.hide_loading()
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "summary", "content": text, "prompt": original_prompt, "title": display_title})
        js = f"addSummaryMessage({json.dumps(text)}, {idx});"
        self.web_view.page().runJavaScript(js)

    def add_system_message(self, message: str):
        self.hide_loading()
        js = f"addMessage('system', {json.dumps(message)}, false);"
        self.web_view.page().runJavaScript(js)

    def add_system_error(self, error_msg: str, allow_retry: bool = True):
        self.hide_loading()
        js = f"addSystemError({json.dumps(error_msg)}, {json.dumps(allow_retry)});"
        self.web_view.page().runJavaScript(js)

    def start_countdown(self, seconds: int):
        self.hide_loading()
        js = f"startCountdown({seconds});"
        self.web_view.page().runJavaScript(js)

    def request_save_message(self, idx: int):
        if 0 <= idx < len(self.raw_messages):
            msg_data = self.raw_messages[idx]
            self.save_requested.emit(msg_data)
            
    def request_edit_message(self, idx: int):
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
                        import json
                        js = f"updateMessage({idx}, {json.dumps(new_text)}, '{action}');"
                        self.web_view.page().runJavaScript(js)

    def request_append_message(self, idx: int):
        if 0 <= idx < len(self.raw_messages):
            msg_data = self.raw_messages[idx]
            self.append_requested.emit(msg_data)
            
    def clear_chat(self):
        self.raw_messages = []
        self.web_view.setHtml(self._get_html_template(), get_assets_base_url())
        self.index_btn.setVisible(False)
