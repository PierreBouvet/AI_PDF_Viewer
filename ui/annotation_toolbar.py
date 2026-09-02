"""
Floating animated annotation toolbar for AI PDF Viewer.
Uses local SVGs: icons/text.svg, icons/highlighter.svg, icons/highlighter_A.svg, icons/sticky-note.svg
"""
import os
from enum import Enum
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, Signal, QPropertyAnimation, QEasingCurve, QSize, QByteArray
)
from PySide6.QtGui import (
    QIcon, QPainter, QPixmap, QColor, QPen, QBrush
)
from PySide6.QtSvg import QSvgRenderer


from ui.theme_manager import ThemeManager
from backend.logger import logger

class AnnotationTool(Enum):
    NONE = "none"
    TEXT_BOX = "text_box"
    HIGHLIGHT_TEXT = "highlight_text"
    HIGHLIGHT_FREEHAND = "highlight_freehand"
    NOTE = "note"


def load_svg_icon(svg_filename: str, active: bool = False, is_dark: bool = False, size: int = 24) -> QIcon:
    """Loads and tints local SVGs for high-DPI retina display."""
    svg_path = os.path.join("icons", svg_filename)
    if not os.path.exists(svg_path):
        return QIcon()
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            content = f.read()
        target_color = "#ffffff" if active else ("#e5e5ea" if is_dark else "#333333")
        content = content.replace('stroke="currentColor"', f'stroke="{target_color}"')
        content = content.replace('stroke="#7e7e7e"', f'stroke="{target_color}"')
        content = content.replace('fill="#000000"', f'fill="{target_color}"')
        
        renderer = QSvgRenderer(QByteArray(content.encode("utf-8")))
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        icon = QIcon()
        icon.addPixmap(pixmap)
        return icon
    except Exception as e:
        logger.error(f"Error loading SVG icon {svg_filename}: {e}")
        return QIcon()


class AnnotationButton(QPushButton):
    """Square icon button with hover animations and active states."""
    def __init__(self, tooltip: str, parent=None):
        super().__init__(parent)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.is_hovered = False
        self.is_active = False
        self.is_dark = False
        
        self.base_size = 28
        self.hover_size = 32
        
        self.update_style()

    def set_active(self, active: bool):
        self.is_active = active
        self.update_style()

    def set_dark(self, is_dark: bool):
        self.is_dark = is_dark
        self.update_style()

    def enterEvent(self, event):
        self.is_hovered = True
        self.update_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update_style()
        super().leaveEvent(event)

    def update_style(self):
        current_dim = self.hover_size if (self.is_hovered or self.is_active) else self.base_size
        self.setFixedSize(current_dim, current_dim)
        self.setIconSize(QSize(current_dim - 10, current_dim - 10))

        hover_bg = "rgba(255, 255, 255, 0.12)" if self.is_dark else "rgba(0, 0, 0, 0.08)"
        hover_border = "rgba(255, 255, 255, 0.18)" if self.is_dark else "rgba(0, 0, 0, 0.12)"

        if self.is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: #007aff;
                    border: 1px solid #0062cc;
                    border-radius: {current_dim // 2}px;
                    padding: 0px;
                    margin: 0px;
                }}
            """)
        elif self.is_hovered:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hover_bg};
                    border: 1px solid {hover_border};
                    border-radius: {current_dim // 2}px;
                    padding: 0px;
                    margin: 0px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: {current_dim // 2}px;
                    padding: 0px;
                    margin: 0px;
                }}
            """)


class FloatingAnnotationBar(QWidget):
    tool_changed = Signal(object)  # AnnotationTool

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_tool = AnnotationTool.NONE
        self.is_hovered = False
        self.is_dark = False
        self.bg_color = QColor(255, 255, 255)
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.20)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_anim.setDuration(220)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 4, 8, 4)
        self.layout.setSpacing(8)
        
        # 1. Text Box Button ("Writing on the PDF") -> text.svg
        self.btn_text = AnnotationButton("Writing on the PDF (Text box)", self)
        self.btn_text.setIcon(load_svg_icon("text.svg", active=False, is_dark=self.is_dark))
        self.btn_text.clicked.connect(self._on_text_clicked)
        self.layout.addWidget(self.btn_text)
        
        # 2. Highlight Button (3-state cycle) -> highlighter.svg / highlighter_A.svg
        self.btn_highlight = AnnotationButton("Highlight (Click to cycle: Text recognition -> Freehand -> Off)", self)
        self.highlight_state = 0 # 0: none, 1: text, 2: freehand
        self.btn_highlight.setIcon(load_svg_icon("highlighter.svg", active=False, is_dark=self.is_dark))
        self.btn_highlight.clicked.connect(self._on_highlight_clicked)
        self.layout.addWidget(self.btn_highlight)
        
        # 3. Note Button -> sticky-note.svg
        self.btn_note = AnnotationButton("Add Sticky Note", self)
        self.btn_note.setIcon(load_svg_icon("sticky-note.svg", active=False, is_dark=self.is_dark))
        self.btn_note.clicked.connect(self._on_note_clicked)
        self.layout.addWidget(self.btn_note)
        
        self.setFixedHeight(34)

    def update_theme(self, app_style: str = "Native macOS", color_mode: str = "Light"):
        mode = ThemeManager.resolve_color_mode(color_mode)
        self.is_dark = (mode.lower() == "dark")
        self.bg_color = QColor("#242426") if self.is_dark else QColor(255, 255, 255)
        
        self.btn_text.set_dark(self.is_dark)
        self.btn_highlight.set_dark(self.is_dark)
        self.btn_note.set_dark(self.is_dark)
        
        self._refresh_icons()
        self.update()

    def _refresh_icons(self):
        is_text = (self.active_tool == AnnotationTool.TEXT_BOX)
        self.btn_text.setIcon(load_svg_icon("text.svg", active=is_text, is_dark=self.is_dark))
        
        is_hl_text = (self.active_tool == AnnotationTool.HIGHLIGHT_TEXT)
        is_hl_free = (self.active_tool == AnnotationTool.HIGHLIGHT_FREEHAND)
        
        if is_hl_text:
            icon_file = "highlighter_A.svg" if os.path.exists(os.path.join("icons", "highlighter_A.svg")) else "highlighter.svg"
            self.btn_highlight.setIcon(load_svg_icon(icon_file, active=True, is_dark=self.is_dark))
        elif is_hl_free:
            self.btn_highlight.setIcon(load_svg_icon("highlighter.svg", active=True, is_dark=self.is_dark))
        else:
            self.btn_highlight.setIcon(load_svg_icon("highlighter.svg", active=False, is_dark=self.is_dark))
            
        is_note = (self.active_tool == AnnotationTool.NOTE)
        self.btn_note.setIcon(load_svg_icon("sticky-note.svg", active=is_note, is_dark=self.is_dark))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = rect.height() / 2.0
        
        painter.setBrush(QBrush(self.bg_color))
        
        if self.is_dark:
            border_alpha = 70 if self.is_hovered else 40
            painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1.0))
        else:
            border_alpha = 55 if self.is_hovered else 30
            painter.setPen(QPen(QColor(0, 0, 0, border_alpha), 1.0))
        
        painter.drawRoundedRect(rect, radius, radius)

    def enterEvent(self, event):
        self.is_hovered = True
        self._animate_opacity(1.00)
        self.setFixedHeight(40)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        if self.active_tool == AnnotationTool.NONE:
            self._animate_opacity(0.20)
            self.setFixedHeight(34)
        else:
            self._animate_opacity(1.00)
        self.update()
        super().leaveEvent(event)

    def _animate_opacity(self, target: float):
        self.opacity_anim.stop()
        self.opacity_anim.setStartValue(self.opacity_effect.opacity())
        self.opacity_anim.setEndValue(target)
        self.opacity_anim.start()

    def update_bar_style(self):
        self.update()

    def _on_text_clicked(self):
        if self.active_tool == AnnotationTool.TEXT_BOX:
            self.set_tool(AnnotationTool.NONE)
        else:
            self.set_tool(AnnotationTool.TEXT_BOX)

    def _on_highlight_clicked(self):
        if self.highlight_state == 0:
            self.highlight_state = 1
            self.set_tool(AnnotationTool.HIGHLIGHT_TEXT)
        elif self.highlight_state == 1:
            self.highlight_state = 2
            self.set_tool(AnnotationTool.HIGHLIGHT_FREEHAND)
        else:
            self.highlight_state = 0
            self.set_tool(AnnotationTool.NONE)

    def _on_note_clicked(self):
        if self.active_tool == AnnotationTool.NOTE:
            self.set_tool(AnnotationTool.NONE)
        else:
            self.set_tool(AnnotationTool.NOTE)

    def set_tool(self, tool: AnnotationTool):
        self.active_tool = tool
        
        is_text = (tool == AnnotationTool.TEXT_BOX)
        self.btn_text.set_active(is_text)
        self.btn_text.setIcon(load_svg_icon("text.svg", active=is_text))
        
        is_hl_text = (tool == AnnotationTool.HIGHLIGHT_TEXT)
        is_hl_free = (tool == AnnotationTool.HIGHLIGHT_FREEHAND)
        
        if is_hl_text:
            self.highlight_state = 1
            self.btn_highlight.set_active(True)
            # Use highlighter_A.svg for text recognition highlighter
            icon_file = "highlighter_A.svg" if os.path.exists(os.path.join("icons", "highlighter_A.svg")) else "highlighter.svg"
            self.btn_highlight.setIcon(load_svg_icon(icon_file, active=True))
            self.btn_highlight.setToolTip("Highlight: Active text recognition (Click for free-hand)")
        elif is_hl_free:
            self.highlight_state = 2
            self.btn_highlight.set_active(True)
            self.btn_highlight.setIcon(load_svg_icon("highlighter.svg", active=True))
            self.btn_highlight.setToolTip("Highlight: Free-hand marker (Click to turn off)")
        else:
            self.highlight_state = 0
            self.btn_highlight.set_active(False)
            self.btn_highlight.setIcon(load_svg_icon("highlighter.svg", active=False))
            self.btn_highlight.setToolTip("Highlight (Click to cycle: Text recognition -> Freehand -> Off)")
            
        is_note = (tool == AnnotationTool.NOTE)
        self.btn_note.set_active(is_note)
        self.btn_note.setIcon(load_svg_icon("sticky-note.svg", active=is_note))
        
        if tool != AnnotationTool.NONE:
            self._animate_opacity(1.00)
        elif not self.is_hovered:
            self._animate_opacity(0.20)
            self.setFixedHeight(34)
            
        self.tool_changed.emit(self.active_tool)

    def clear_selection(self):
        self.set_tool(AnnotationTool.NONE)
