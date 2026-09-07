from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QComboBox, QDialog, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import Signal, Slot, QObject, Qt
import json
from ui.theme_manager import ThemeManager
from ui.asset_loader import get_assets_base_url

class ChatBridge(QObject):
    double_clicked_idx = Signal(int)
    append_pdf_idx = Signal(int)
    edit_msg_idx = Signal(int)
    open_settings_requested = Signal()
    retry_requested = Signal()

    @Slot(int)
    def on_double_click(self, idx: int):
        self.double_clicked_idx.emit(idx)

    @Slot(int)
    def on_append_pdf(self, idx: int):
        self.append_pdf_idx.emit(idx)

    @Slot(int)
    def on_edit_msg(self, idx: int):
        self.edit_msg_idx.emit(idx)

    @Slot()
    def on_open_settings(self):
        self.open_settings_requested.emit()

    @Slot()
    def on_retry(self):
        self.retry_requested.emit()

class ChatWebPage(QWebEnginePage):
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
        
        # Chat History via WebEngine
        self.web_view = QWebEngineView()
        self.web_page = ChatWebPage(self.web_view)
        self.bridge = ChatBridge(self)
        self.channel = QWebChannel(self.web_page)
        self.channel.registerObject("bridge", self.bridge)
        self.web_page.setWebChannel(self.channel)
        
        self.bridge.double_clicked_idx.connect(self.request_save_message)
        self.bridge.append_pdf_idx.connect(self.request_append_message)
        self.bridge.edit_msg_idx.connect(self.request_edit_message)
        self.bridge.open_settings_requested.connect(self.open_settings_requested)
        self.bridge.retry_requested.connect(self.retry_requested)
        
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
        self.document_tokens = 0
        
        self.prompts_combo.currentIndexChanged.connect(self._on_prompt_combo_changed)
        self.input_field.textChanged.connect(self._update_send_button_estimate)
        
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

    def set_document_tokens(self, tokens: int):
        """Set the estimated token count of the indexed document and update estimates."""
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
        """Refresh estimated response times across prompts dropdown and the Send button."""
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
            self.send_btn.setToolTip(
                f"Estimated response time: NA\n"
                f"• Model: {model_name}\n"
                f"• Calibration: No previous runs recorded for this model yet. Run a prompt to calibrate.\n"
                f"• Document context: ~{self.document_tokens:,} tokens\n"
                f"• Prompt length: ~{prompt_tokens} tokens"
            )
        elif est_str:
            from backend.model_benchmark import ModelBenchmarkManager
            run_count = ModelBenchmarkManager().get_run_count(model_name)
            calib_info = f" (calibrated from last {run_count} runs)" if run_count > 0 else ""
            self.send_btn.setText(f"Send ({est_str})")
            self.send_btn.setToolTip(
                f"Estimated response time: {est_str}\n"
                f"• Model: {model_name}{calib_info}\n"
                f"• Document context: ~{self.document_tokens:,} tokens\n"
                f"• Prompt length: ~{prompt_tokens} tokens"
            )
        else:
            self.send_btn.setText("Send")
            self.send_btn.setToolTip("Send question to AI assistant")
        
    def set_generating_state(self, is_generating: bool):
        """Toggle input controls and switch Send/Stop button during AI generation."""
        self.is_generating = is_generating
        self.prompts_combo.setEnabled(not is_generating)
        self.input_field.setEnabled(not is_generating and self.prompts_combo.currentIndex() <= 0)
        if is_generating:
            self.send_btn.setText("Stop")
            self.send_btn.setStyleSheet("background-color: #e81123; color: #ffffff; font-weight: 500; border: none; border-radius: 4px; padding: 6px 12px;")
            self.show_loading()
        else:
            self.send_btn.setStyleSheet("background-color: #dcdcdc; color: #000000; font-weight: 500; border: none; border-radius: 4px; padding: 6px 12px;")
            self._update_send_button_estimate()
            self.hide_loading()

    def _send_message(self):
        if self.is_generating:
            # Stop button clicked
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
            # If it's a custom predefined prompt, show the expression name instead of huge prompt text
            self.add_user_message(display_text)
            
            if not is_custom:
                self.input_field.clear()
                
            # Automatically switch back to "--- Custom Input ---"
            self.prompts_combo.setCurrentIndex(0)
                
            self.set_generating_state(True)
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
            <script src="qwebchannel.js"></script>
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
                let pyBridge = null;
                function initWebChannel(callback) {{
                    if (window.pyBridge) {{
                        if (callback) callback(window.pyBridge);
                        return;
                    }}
                    if (typeof QWebChannel !== "undefined" && typeof qt !== "undefined" && qt.webChannelTransport) {{
                        new QWebChannel(qt.webChannelTransport, function(channel) {{
                            window.pyBridge = channel.objects.bridge;
                            if (callback) callback(window.pyBridge);
                        }});
                    }}
                }}
                initWebChannel();
                window.addEventListener('load', function() {{ initWebChannel(); }});

                function notifyDoubleClick(idx) {{
                    initWebChannel(function(bridge) {{
                        if (bridge && bridge.on_double_click) {{
                            bridge.on_double_click(parseInt(idx));
                        }}
                    }});
                }}

                function notifyEditMsg(idx) {{
                    initWebChannel(function(bridge) {{
                        if (bridge && bridge.on_edit_msg) {{
                            bridge.on_edit_msg(parseInt(idx));
                        }}
                    }});
                }}

                function notifyAppendPdf(idx) {{
                    initWebChannel(function(bridge) {{
                        if (bridge && bridge.on_append_pdf) {{
                            bridge.on_append_pdf(parseInt(idx));
                        }}
                    }});
                }}

                let isAppending = false;
                const appendedIndices = new Set();

                function setAllAppendDisabled(disabled) {{
                    isAppending = disabled;
                    const buttons = document.querySelectorAll('button[data-action="append"]');
                    buttons.forEach(btn => {{
                        const idx = parseInt(btn.getAttribute('data-idx'));
                        if (isAppending) {{
                            btn.disabled = true;
                            btn.style.opacity = '0.5';
                            btn.style.cursor = 'not-allowed';
                        }} else {{
                            if (appendedIndices.has(idx)) {{
                                btn.disabled = true;
                                btn.style.opacity = '0.5';
                                btn.style.cursor = 'not-allowed';
                            }} else {{
                                btn.disabled = false;
                                btn.style.opacity = '1.0';
                                btn.style.cursor = 'pointer';
                            }}
                        }}
                    }});
                }}

                function getAppendButtonHtml(idx) {{
                    const isAppended = appendedIndices.has(idx);
                    const isDisabled = isAppending || isAppended;
                    const style = isDisabled
                        ? "margin-top:8px; padding:4px 8px; font-size:9pt; cursor:not-allowed; opacity:0.5; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;"
                        : "margin-top:8px; padding:4px 8px; font-size:9pt; cursor:pointer; opacity:1.0; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;";
                    const disabledAttr = isDisabled ? " disabled" : "";
                    return `<button data-action="append" data-idx="${{idx}}" style="${{style}}"${{disabledAttr}}>Append to PDF</button>`;
                }}

                function getEditButtonHtml(idx) {{
                    return `<button data-action="edit" data-idx="${{idx}}" style="margin-top:8px; margin-right:8px; padding:4px 8px; font-size:9pt; cursor:pointer; background-color:#e1e1e1; border:1px solid #ccc; border-radius:4px;">Edit Response</button>`;
                }}

                document.addEventListener('DOMContentLoaded', () => {{
                    initWebChannel();
                    const container = document.getElementById('chat-container');
                    if (container) {{
                        container.addEventListener('click', (e) => {{
                            const target = e.target.closest('button[data-action]');
                            if (!target || target.disabled) return;
                            const action = target.getAttribute('data-action');
                            const idx = target.getAttribute('data-idx');
                            if (action === 'edit') {{
                                notifyEditMsg(idx);
                            }} else if (action === 'append') {{
                                if (isAppending) return;
                                const numIdx = parseInt(idx);
                                appendedIndices.add(numIdx);
                                setAllAppendDisabled(true);
                                notifyAppendPdf(idx);
                            }}
                        }});
                    }}
                }});

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
                            notifyDoubleClick(idx);
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
                            html += '<br>' + getEditButtonHtml(idx) + getAppendButtonHtml(idx);
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
                            notifyDoubleClick(idx);
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
                        html += '<br>' + getAppendButtonHtml(idx);
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
                            notifyDoubleClick(idx);
                        }};
                        msgDiv.style.cursor = "pointer";
                        msgDiv.title = "Double-click to open in new window";
                    }}
                    
                    let parsedText = renderMarkdownSafe(text);
                    let html = `<b>AI Discuss:</b><br><div class='discuss-section'>${{parsedText}}</div>`;
                    if (idx !== undefined && idx !== null) {{
                        html += '<br>' + getEditButtonHtml(idx) + getAppendButtonHtml(idx);
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
                            notifyDoubleClick(idx);
                        }};
                        msgDiv.style.cursor = "pointer";
                        msgDiv.title = "Double-click to open in new window";
                    }}
                    
                    let parsedText = renderMarkdownSafe(text);
                    let html = `<b>AI Summary:</b><br><div class='summary-section'>${{parsedText}}</div>`;
                    if (idx !== undefined && idx !== null) {{
                        html += '<br>' + getEditButtonHtml(idx) + getAppendButtonHtml(idx);
                    }}
                    
                    msgDiv.innerHTML = html;
                    container.appendChild(msgDiv);
                    triggerMathJax();
                }}
                
                function updateMessage(idx, newText, msgType) {{
                    const msgDiv = document.getElementById('msg-' + idx);
                    if (!msgDiv) return;
                    
                    const numIdx = parseInt(idx);
                    appendedIndices.delete(numIdx);
                    
                    let html = '<b>AI' + (msgType === "chat" ? "" : " " + msgType.charAt(0).toUpperCase() + msgType.slice(1)) + ':</b><br>';
                    let parsedText = renderMarkdownSafe(newText);
                    
                    if (msgType === "discuss") {{
                        html += `<div class='discuss-section'>${{parsedText}}</div>`;
                    }} else if (msgType === "summary") {{
                        html += `<div class='summary-section'>${{parsedText}}</div>`;
                    }} else {{
                        html += parsedText;
                    }}
                    
                    html += '<br>' + getEditButtonHtml(idx) + getAppendButtonHtml(idx);
                    
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
        self.set_generating_state(False)
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "chat", "content": message, "prompt": original_prompt, "title": display_title})
        js = f"addMessage('ai', {json.dumps(message)}, true, {idx});"
        self.web_view.page().runJavaScript(js)

    def add_explain_message(self, parts: list, original_prompt: str = "", display_title: str = ""):
        self.set_generating_state(False)
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "explain", "content": parts, "prompt": original_prompt, "title": display_title})
        js = f"addExplainMessage({json.dumps(parts)}, {idx});"
        self.web_view.page().runJavaScript(js)
        
    def add_discuss_message(self, text: str, original_prompt: str = "", display_title: str = ""):
        self.set_generating_state(False)
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "discuss", "content": text, "prompt": original_prompt, "title": display_title})
        js = f"addDiscussMessage({json.dumps(text)}, {idx});"
        self.web_view.page().runJavaScript(js)

    def add_summary_message(self, text: str, original_prompt: str = "", display_title: str = ""):
        self.set_generating_state(False)
        idx = len(self.raw_messages)
        self.raw_messages.append({"action": "summary", "content": text, "prompt": original_prompt, "title": display_title})
        js = f"addSummaryMessage({json.dumps(text)}, {idx});"
        self.web_view.page().runJavaScript(js)

    def add_system_message(self, message: str):
        self.hide_loading()
        js = f"addMessage('system', {json.dumps(message)}, false);"
        self.web_view.page().runJavaScript(js)

    def add_system_error(self, error_msg: str, allow_retry: bool = True):
        self.set_generating_state(False)
        js = f"addSystemError({json.dumps(error_msg)}, {json.dumps(allow_retry)});"
        self.web_view.page().runJavaScript(js)

    def start_countdown(self, seconds: int):
        self.set_generating_state(False)
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
            
    def set_all_append_disabled(self, disabled: bool):
        import json
        js = f"setAllAppendDisabled({json.dumps(disabled)});"
        self.web_view.page().runJavaScript(js)

    def clear_chat(self):
        self.raw_messages = []
        self.web_view.setHtml(self._get_html_template(), get_assets_base_url())
        self.index_btn.setVisible(False)
