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
    QIcon, QPainter, QPixmap
)
from PySide6.QtSvg import QSvgRenderer


class AnnotationTool(Enum):
    NONE = "none"
    TEXT_BOX = "text_box"
    HIGHLIGHT_TEXT = "highlight_text"
    HIGHLIGHT_FREEHAND = "highlight_freehand"
    NOTE = "note"


def load_svg_icon(svg_filename: str, active: bool = False, size: int = 24) -> QIcon:
    """Loads and tints local SVGs for high-DPI retina display."""
    svg_path = os.path.join("icons", svg_filename)
    if not os.path.exists(svg_path):
        return QIcon()
    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            content = f.read()
        target_color = "#ffffff" if active else "#333333"
        content = content.replace('stroke="currentColor"', f'stroke="{target_color}"')
        content = content.replace('stroke="#7e7e7e"', f'stroke="{target_color}"')
        content = content.replace('fill="#000000"', f'fill="{target_color}"')
        
        renderer = QSvgRenderer(QByteArray(content.encode("utf-8")))
        pix = QPixmap(size * 2, size * 2)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        renderer.render(p)
        p.end()
        pix.setDevicePixelRatio(2.0)
        return QIcon(pix)
    except Exception as e:
        print(f"Failed to load SVG {svg_filename}: {e}")
        return QIcon()


class AnnotationButton(QPushButton):
    def __init__(self, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.is_active = False
        self.is_hovered = False
        self.base_size = 28
        self.hover_size = 32
        self.setFixedSize(self.base_size, self.base_size)
        self.update_style()

    def set_active(self, active: bool):
        self.is_active = active
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
                    background-color: rgba(255, 255, 255, 0.45);
                    border: 1px solid rgba(0, 0, 0, 0.15);
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
        self.btn_text.setIcon(load_svg_icon("text.svg", active=False))
        self.btn_text.clicked.connect(self._on_text_clicked)
        self.layout.addWidget(self.btn_text)
        
        # 2. Highlight Button (3-state cycle) -> highlighter.svg / highlighter_A.svg
        self.btn_highlight = AnnotationButton("Highlight (Click to cycle: Text recognition -> Freehand -> Off)", self)
        self.highlight_state = 0 # 0: none, 1: text, 2: freehand
        self.btn_highlight.setIcon(load_svg_icon("highlighter.svg", active=False))
        self.btn_highlight.clicked.connect(self._on_highlight_clicked)
        self.layout.addWidget(self.btn_highlight)
        
        # 3. Note Button -> sticky-note.svg
        self.btn_note = AnnotationButton("Add Sticky Note", self)
        self.btn_note.setIcon(load_svg_icon("sticky-note.svg", active=False))
        self.btn_note.clicked.connect(self._on_note_clicked)
        self.layout.addWidget(self.btn_note)
        
        self.setFixedHeight(34)
        self.update_bar_style()

    def enterEvent(self, event):
        self.is_hovered = True
        self._animate_opacity(0.80)
        self.setFixedHeight(40)
        self.update_bar_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        if self.active_tool == AnnotationTool.NONE:
            self._animate_opacity(0.20)
            self.setFixedHeight(34)
        else:
            self._animate_opacity(0.80)
        self.update_bar_style()
        super().leaveEvent(event)

    def _animate_opacity(self, target: float):
        self.opacity_anim.stop()
        self.opacity_anim.setStartValue(self.opacity_effect.opacity())
        self.opacity_anim.setEndValue(target)
        self.opacity_anim.start()

    def update_bar_style(self):
        h = self.height()
        radius = h // 2
        bg = "rgba(240, 240, 245, 0.92)" if self.is_hovered else "rgba(220, 220, 228, 0.85)"
        border = "rgba(0, 0, 0, 0.18)" if self.is_hovered else "rgba(0, 0, 0, 0.10)"
        self.setStyleSheet(f"""
            FloatingAnnotationBar {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {radius}px;
            }}
        """)

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
            self._animate_opacity(0.85)
        elif not self.is_hovered:
            self._animate_opacity(0.20)
            self.setFixedHeight(34)
            
        self.tool_changed.emit(self.active_tool)

    def clear_selection(self):
        self.set_tool(AnnotationTool.NONE)
