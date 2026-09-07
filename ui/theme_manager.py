"""
Theme and visual style manager for AI PDF Viewer.
Supports Native, Adobe Acrobat, and Minimalist styles in Light and Dark modes.
"""
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

THEMES = {
    ("Native", "Light"): {
        "bg_window": "#ececec",
        "bg_card": "#ffffff",
        "bg_panel": "#f6f6f8",
        "bg_button": "#e5e5ea",
        "bg_button_hover": "#dcdce0",
        "bg_input": "#ffffff",
        "accent": "#007aff",
        "accent_hover": "#0062cc",
        "accent_text": "#ffffff",
        "text_primary": "#1d1d1f",
        "text_secondary": "#6e6e73",
        "border": "#d2d2d7",
        "border_subtle": "#e5e5ea",
        "radius": "6px",
        "pdf_bg": "#505054",
        "log_bg": "#f5f5f7",
        "chat_ai_bg": "#f1f1f3",
        "chat_user_bg": "#007aff",
        "chat_user_text": "#ffffff",
        "chat_ai_text": "#1d1d1f",
        "chat_code_bg": "#2b2b2b",
        "chat_code_text": "#f8f8f2",
    },
    ("Native", "Dark"): {
        "bg_window": "#1e1e1e",
        "bg_card": "#242426",
        "bg_panel": "#28282b",
        "bg_button": "#333336",
        "bg_button_hover": "#424246",
        "bg_input": "#18181a",
        "accent": "#0a84ff",
        "accent_hover": "#006ee6",
        "accent_text": "#ffffff",
        "text_primary": "#f5f5f7",
        "text_secondary": "#8e8e93",
        "border": "#3a3a3e",
        "border_subtle": "#2c2c30",
        "radius": "6px",
        "pdf_bg": "#121214",
        "log_bg": "#1e1e20",
        "chat_ai_bg": "#2d2d30",
        "chat_user_bg": "#0a84ff",
        "chat_user_text": "#ffffff",
        "chat_ai_text": "#f5f5f7",
        "chat_code_bg": "#19191b",
        "chat_code_text": "#f8f8f2",
    },
    ("Adobe Acrobat", "Light"): {
        "bg_window": "#f4f4f5",
        "bg_card": "#ffffff",
        "bg_panel": "#fafafa",
        "bg_button": "#e4e4e7",
        "bg_button_hover": "#d4d4d8",
        "bg_input": "#ffffff",
        "accent": "#eb1000",
        "accent_hover": "#c40d00",
        "accent_text": "#ffffff",
        "text_primary": "#18181b",
        "text_secondary": "#71717a",
        "border": "#d4d4d8",
        "border_subtle": "#e4e4e7",
        "radius": "3px",
        "pdf_bg": "#4a4a4f",
        "log_bg": "#f4f4f5",
        "chat_ai_bg": "#f4f4f5",
        "chat_user_bg": "#eb1000",
        "chat_user_text": "#ffffff",
        "chat_ai_text": "#18181b",
        "chat_code_bg": "#27272a",
        "chat_code_text": "#fafafa",
    },
    ("Adobe Acrobat", "Dark"): {
        "bg_window": "#18181b",
        "bg_card": "#222225",
        "bg_panel": "#27272a",
        "bg_button": "#323236",
        "bg_button_hover": "#3f3f46",
        "bg_input": "#141416",
        "accent": "#e2231a",
        "accent_hover": "#c40d00",
        "accent_text": "#ffffff",
        "text_primary": "#f4f4f5",
        "text_secondary": "#a1a1aa",
        "border": "#3f3f46",
        "border_subtle": "#27272a",
        "radius": "3px",
        "pdf_bg": "#0f0f11",
        "log_bg": "#1b1b1e",
        "chat_ai_bg": "#2b2b2f",
        "chat_user_bg": "#e2231a",
        "chat_user_text": "#ffffff",
        "chat_ai_text": "#f4f4f5",
        "chat_code_bg": "#141416",
        "chat_code_text": "#f4f4f5",
    },
    ("Minimalist", "Light"): {
        "bg_window": "#fafafa",
        "bg_card": "#ffffff",
        "bg_panel": "#ffffff",
        "bg_button": "#f4f4f5",
        "bg_button_hover": "#e4e4e7",
        "bg_input": "#ffffff",
        "accent": "#09090b",
        "accent_hover": "#27272a",
        "accent_text": "#ffffff",
        "text_primary": "#09090b",
        "text_secondary": "#71717a",
        "border": "#e4e4e7",
        "border_subtle": "#f4f4f5",
        "radius": "2px",
        "pdf_bg": "#5a5a60",
        "log_bg": "#fafafa",
        "chat_ai_bg": "#f4f4f5",
        "chat_user_bg": "#09090b",
        "chat_user_text": "#ffffff",
        "chat_ai_text": "#09090b",
        "chat_code_bg": "#18181b",
        "chat_code_text": "#fafafa",
    },
    ("Minimalist", "Dark"): {
        "bg_window": "#09090b",
        "bg_card": "#121215",
        "bg_panel": "#141417",
        "bg_button": "#18181b",
        "bg_button_hover": "#27272a",
        "bg_input": "#0f0f12",
        "accent": "#f4f4f5",
        "accent_hover": "#e4e4e7",
        "accent_text": "#09090b",
        "text_primary": "#f4f4f5",
        "text_secondary": "#a1a1aa",
        "border": "#27272a",
        "border_subtle": "#1c1c20",
        "radius": "2px",
        "pdf_bg": "#000000",
        "log_bg": "#0e0e11",
        "chat_ai_bg": "#1c1c20",
        "chat_user_bg": "#f4f4f5",
        "chat_user_text": "#09090b",
        "chat_ai_text": "#f4f4f5",
        "chat_code_bg": "#09090b",
        "chat_code_text": "#f4f4f5",
    },
}


class ThemeManager:
    @staticmethod
    def resolve_color_mode(color_mode: str = "System (Auto)") -> str:
        """
        Resolves 'System (Auto)' to the actual OS theme ('Light' or 'Dark').
        If explicit 'Light' or 'Dark' is chosen, returns that value.
        """
        mode_str = str(color_mode).strip().lower()
        if mode_str.startswith("system") or mode_str == "auto":
            app = QApplication.instance()
            if app:
                try:
                    from PySide6.QtCore import Qt
                    if hasattr(app, "styleHints") and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
                        return "Dark"
                    return "Light"
                except Exception:
                    pass
            # macOS fallback check if app instance not yet initialized
            try:
                import subprocess
                res = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True)
                if "dark" in res.stdout.lower():
                    return "Dark"
            except Exception:
                pass
            return "Light"
        return "Dark" if mode_str == "dark" else "Light"

    @staticmethod
    def get_palette(app_style: str = "Native", color_mode: str = "Light") -> dict:
        resolved_mode = ThemeManager.resolve_color_mode(color_mode)
        key = (app_style, resolved_mode)
        if key in THEMES:
            return THEMES[key]
        # Fallback
        return THEMES.get(("Native", resolved_mode), THEMES[("Native", "Light")])

    @staticmethod
    def get_pdf_bg_color(app_style: str = "Native", color_mode: str = "Light") -> QColor:
        palette = ThemeManager.get_palette(app_style, color_mode)
        return QColor(palette["pdf_bg"])

    @staticmethod
    def get_stylesheet(app_style: str = "Native", color_mode: str = "Light") -> str:
        resolved_mode = ThemeManager.resolve_color_mode(color_mode)
        p = ThemeManager.get_palette(app_style, resolved_mode)
        
        is_dark = (resolved_mode.lower() == "dark")
        font_family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
        
        arrow_icon_name = "chevron-down-dark.svg" if is_dark else "chevron-down-light.svg"
        from ui.asset_loader import get_icon_path
        arrow_icon_path = get_icon_path(arrow_icon_name).replace("\\", "/")
        
        return f"""
        QMainWindow, QDialog, QWidget#centralWidget {{
            background-color: {p['bg_window']};
            color: {p['text_primary']};
            font-family: {font_family};
        }}
        
        QToolBar {{
            background-color: {p['bg_panel']};
            border: none;
            border-bottom: 1px solid {p['border']};
            padding: 4px;
            spacing: 6px;
        }}
        
        QPushButton {{
            background-color: {p['bg_button']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: {p['radius']};
            padding: 5px 12px;
            font-weight: 500;
            font-size: 10pt;
        }}
        QPushButton:hover {{
            background-color: {p['bg_button_hover']};
            border-color: {p['border']};
        }}
        QPushButton:checked {{
            background-color: {p['accent']};
            color: {p['accent_text']};
            border-color: {p['accent_hover']};
        }}
        QPushButton:disabled {{
            opacity: 0.5;
            color: {p['text_secondary']};
        }}
        
        QLineEdit, QSpinBox {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: {p['radius']};
            padding: 4px 8px;
            min-height: 20px;
            selection-background-color: {p['accent']};
            selection-color: {p['accent_text']};
        }}
        QLineEdit:focus, QSpinBox:focus {{
            border: 1px solid {p['accent']};
        }}
        
        QComboBox, QFontComboBox {{
            background-color: {p['bg_input']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: {p['radius']};
            padding: 4px 24px 4px 8px;
            min-height: 20px;
            selection-background-color: {p['accent']};
            selection-color: {p['accent_text']};
        }}
        QComboBox:focus, QFontComboBox:focus {{
            border: 1px solid {p['accent']};
        }}
        
        QComboBox::drop-down, QFontComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border: none;
            background: transparent;
        }}
        QComboBox::down-arrow, QFontComboBox::down-arrow {{
            image: url("{arrow_icon_path}");
            width: 10px;
            height: 10px;
        }}
        QComboBox::down-arrow:disabled, QFontComboBox::down-arrow:disabled {{
            opacity: 0.4;
        }}
        
        QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
            background-color: {p['bg_card']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: {p['radius']};
            selection-background-color: {p['accent']};
            selection-color: {p['accent_text']};
            padding: 4px;
        }}
        QComboBox QAbstractItemView::item, QFontComboBox QAbstractItemView::item {{
            min-height: 18px;
            padding: 2px 6px;
        }}
        
        QListWidget {{
            background-color: {p['bg_panel']};
            color: {p['text_primary']};
            border: none;
            border-right: 1px solid {p['border']};
        }}
        QListWidget::item {{
            border-radius: {p['radius']};
            padding: 4px;
        }}
        QListWidget::item:selected {{
            background-color: {p['accent']};
            color: {p['accent_text']};
        }}
        QListWidget::item:hover:!selected {{
            background-color: {p['bg_button_hover']};
        }}
        
        QSplitter::handle {{
            background-color: {p['border_subtle']};
        }}
        QSplitter::handle:hover {{
            background-color: {p['accent']};
        }}
        
        QScrollBar:vertical {{
            background: {p['bg_panel']};
            width: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {p['border']};
            min-height: 20px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p['text_secondary']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        QScrollBar:horizontal {{
            background: {p['bg_panel']};
            height: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p['border']};
            min-width: 20px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {p['text_secondary']};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        
        QLabel {{
            color: {p['text_primary']};
        }}
        
        QStatusBar {{
            background-color: {p['bg_panel']};
            color: {p['text_secondary']};
            border-top: 1px solid {p['border']};
        }}
        """

    @staticmethod
    def get_chat_css(app_style: str, color_mode: str, font_family: str, font_size: int) -> str:
        p = ThemeManager.get_palette(app_style, color_mode)
        
        return f"""
        body {{
            font-family: '{font_family}', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: {font_size}pt;
            color: {p['chat_ai_text']};
            background-color: {p['bg_card']};
            padding: 10px;
            margin: 0;
            line-height: 1.5;
        }}
        .message {{
            margin-bottom: 14px;
            padding: 10px 14px;
            border-radius: {p['radius']};
            max-width: 90%;
            word-wrap: break-word;
        }}
        .user-message {{
            background-color: {p['chat_user_bg']};
            color: {p['chat_user_text']};
            align-self: flex-end;
            margin-left: auto;
        }}
        .ai-message {{
            background-color: {p['chat_ai_bg']};
            color: {p['chat_ai_text']};
            border: 1px solid {p['border_subtle']};
        }}
        .system-message {{
            color: {p['text_secondary']};
            font-style: italic;
            text-align: center;
            font-size: {max(8, font_size - 2)}pt;
            margin-bottom: 10px;
        }}
        
        .ai-message code {{
            background-color: {p['border_subtle']};
            color: {p['chat_ai_text']};
            padding: 2px 5px;
            border-radius: 4px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.9em;
        }}
        .ai-message pre {{
            background-color: {p['chat_code_bg']};
            color: {p['chat_code_text']};
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
        }}
        .ai-message pre code {{
            background-color: transparent;
            color: inherit;
            padding: 0;
        }}
        .ai-message p {{
            margin-top: 0;
            margin-bottom: 0.6em;
        }}
        .ai-message p:last-child {{
            margin-bottom: 0;
        }}
        #chat-container {{
            display: flex;
            flex-direction: column;
        }}
        
        .explain-section {{
            border: 1px solid {p['border']};
            padding: 10px;
            margin-top: 5px;
            background-color: {p['chat_ai_bg']};
            border-radius: 5px;
        }}
        .discuss-section {{
            border: 1px solid {p['accent']};
            padding: 10px;
            margin-top: 5px;
            background-color: {p['bg_panel']};
            border-radius: 5px;
        }}
        .summary-section {{
            border: 1px solid {p['border']};
            padding: 10px;
            margin-top: 5px;
            background-color: {p['chat_ai_bg']};
            border-radius: 5px;
        }}
        .quote-header {{
            font-size: 9pt;
            font-weight: bold;
            color: {p['text_secondary']};
            margin-bottom: 5px;
        }}
        .quoted-text {{
            font-style: italic;
            margin-bottom: 10px;
            color: {p['text_primary']};
        }}
        .save-btn, .append-btn, .edit-btn {{
            cursor: pointer;
            border: none;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 8.5pt;
            font-weight: bold;
            margin-right: 5px;
        }}
        .save-btn {{
            background-color: {p['accent']};
            color: {p['accent_text']};
        }}
        .append-btn {{
            background-color: {p['bg_button']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
        }}
        .edit-btn {{
            background-color: {p['bg_button']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
        }}
        """

    @staticmethod
    def apply_theme(app, app_style: str = "Native", color_mode: str = "Light"):
        """Applies stylesheet globally to the Qt application."""
        if app is None:
            app = QApplication.instance()
        if app:
            stylesheet = ThemeManager.get_stylesheet(app_style, color_mode)
            app.setStyleSheet(stylesheet)
