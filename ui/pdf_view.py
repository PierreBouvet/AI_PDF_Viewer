from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
    QGraphicsPathItem, QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QMenu
)
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QPainterPath
from PySide6.QtCore import Qt, Signal, QRectF, QObject, QRunnable, QThreadPool, QTimer
from backend.pdf_document import PDFDocument
from backend.logger import logger
from ui.annotation_toolbar import AnnotationTool, FloatingAnnotationBar


class NoteDialog(QDialog):
    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Note")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(240, 200)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        header = QHBoxLayout()
        title = QLabel("<b>Sticky Note</b>")
        title.setStyleSheet("color: #785a00; font-size: 10pt;")
        header.addWidget(title)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #785a00;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #000000;
            }
        """)
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        layout.addLayout(header)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Type your note...")
        self.text_edit.setText(initial_text)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #fffde7;
                color: #2c2c2e;
                border: 1px solid #ffe082;
                border-radius: 4px;
                font-size: 10pt;
                padding: 4px;
            }
        """)
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        done_btn = QPushButton("Done")
        done_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffd54f;
                color: #3e2723;
                border: 1px solid #ffca28;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #ffca28;
            }
        """)
        done_btn.clicked.connect(self.accept)
        btn_layout.addWidget(done_btn)
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("""
            NoteDialog {
                background-color: #fff9c4;
                border: 1px solid #ffd54f;
                border-radius: 8px;
            }
        """)
        
    def get_text(self) -> str:
        return self.text_edit.toPlainText().strip()


class TextBoxDialog(QDialog):
    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Text")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(280, 130)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        
        header = QLabel("<b>Writing on the PDF</b>")
        header.setStyleSheet("color: #1c1c1e; font-size: 10pt;")
        layout.addWidget(header)
        
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("Type text here...")
        self.line_edit.setText(initial_text)
        self.line_edit.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #007aff;
                border-radius: 4px;
                padding: 6px;
                font-size: 11pt;
            }
        """)
        self.line_edit.returnPressed.connect(self.accept)
        layout.addWidget(self.line_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5e5ea;
                color: #1c1c1e;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        done_btn = QPushButton("Done")
        done_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: white;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
        """)
        done_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(done_btn)
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("""
            TextBoxDialog {
                background-color: #f2f2f7;
                border: 1px solid #c7c7cc;
                border-radius: 8px;
            }
        """)
        
    def get_text(self) -> str:
        return self.line_edit.text().strip()


class PageLoaderSignals(QObject):
    finished = Signal(int, object, float, object)  # page_number, QImage, zoom, page_item


class PageLoaderRunnable(QRunnable):
    def __init__(self, document, page_number, zoom, dpi_scale, page_item):
        super().__init__()
        self.document = document
        self.page_number = page_number
        self.zoom = zoom
        self.dpi_scale = dpi_scale
        self.page_item = page_item
        self.signals = PageLoaderSignals()
        
    def run(self):
        if not self.document:
            return
        image = self.document.get_page_image(self.page_number, self.zoom, self.dpi_scale)
        self.signals.finished.emit(self.page_number, image, self.zoom, self.page_item)


class TileLoaderSignals(QObject):
    finished = Signal(int, object, float, object, object)  # page_number, QImage, zoom, clip_rect, page_item


class TileLoaderRunnable(QRunnable):
    def __init__(self, document, page_number, zoom, dpi_scale, clip_rect, page_item):
        super().__init__()
        self.document = document
        self.page_number = page_number
        self.zoom = zoom
        self.dpi_scale = dpi_scale
        self.clip_rect = clip_rect  # (x0, y0, x1, y1) in page points
        self.page_item = page_item
        self.signals = TileLoaderSignals()
        
    def run(self):
        if not self.document:
            return
        image = self.document.get_page_image(
            self.page_number, 
            zoom_factor=self.zoom, 
            dpi_scale=self.dpi_scale, 
            clip_rect=self.clip_rect
        )
        self.signals.finished.emit(self.page_number, image, self.zoom, self.clip_rect, self.page_item)


class PageItem(QGraphicsRectItem):
    def __init__(self, page_number: int, view: 'PDFView', parent=None):
        super().__init__(parent)
        self.page_number = page_number
        self.view = view
        self.is_loaded = False
        self.pixmap_item = None        # Base full-page overview layer (Z=0.0)
        self.tile_item = None          # High-res viewport tile layer (Z=0.5)
        self.is_tile_loading = False
        self.current_tile_rect = None  # (x0, y0, x1, y1)
        self.current_tile_zoom = 0.0
        self.pending_tile_req = None
        
        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setBrush(QColor(255, 255, 255))
        
    def load(self):
        if self.is_loaded or getattr(self, "is_loading", False):
            return
            
        self.is_loading = True
        dpi_scale = self.view.devicePixelRatioF()
        # Keep base overview fast and lightweight (~8 MB per page)
        base_zoom = min(self.view.transform().m11(), 1.5)
        
        runnable = PageLoaderRunnable(self.view.document, self.page_number, base_zoom, dpi_scale, self)
        runnable.signals.finished.connect(self.view.on_page_image_loaded, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(runnable)
        
    def on_image_loaded(self, page_number, image, zoom):
        if page_number == self.page_number and getattr(self, "is_loading", False):
            if image:
                pixmap = QPixmap.fromImage(image)
                if not getattr(self, "is_loading", False):
                    return
                if self.pixmap_item and self.pixmap_item.scene():
                    self.scene().removeItem(self.pixmap_item)
                self.pixmap_item = QGraphicsPixmapItem(pixmap, self)
                self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                self.pixmap_item.setZValue(0.0)
                item_w = self.pixmap_item.boundingRect().width()
                if self.rect().width() > 0 and item_w > 0:
                    self.pixmap_item.setScale(self.rect().width() / item_w)
                else:
                    self.pixmap_item.setScale(1.0 / zoom)
                self.is_loaded = True
        self.is_loading = False
            
    def reload(self):
        if getattr(self, "is_loading", False):
            return
            
        self.is_loading = True
        dpi_scale = self.view.devicePixelRatioF()
        base_zoom = min(self.view.transform().m11(), 1.5)
        
        runnable = PageLoaderRunnable(self.view.document, self.page_number, base_zoom, dpi_scale, self)
        runnable.signals.finished.connect(self.view.on_page_image_loaded, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(runnable)

    def update_tile(self, clip_rect: tuple, zoom: float, dpi_scale: float):
        if not self.view.document:
            return
            
        x0, y0, x1, y1 = clip_rect
        if x1 <= x0 or y1 <= y0:
            self.clear_tile()
            return
            
        # If current tile already covers clip_rect at the same zoom level (within tolerance), keep it
        if self.tile_item is not None and abs(self.current_tile_zoom - zoom) < 0.05:
            if self.current_tile_rect is not None:
                tx0, ty0, tx1, ty1 = self.current_tile_rect
                if tx0 <= x0 + 2 and ty0 <= y0 + 2 and tx1 >= x1 - 2 and ty1 >= y1 - 2:
                    return
                    
        if self.is_tile_loading:
            self.pending_tile_req = (clip_rect, zoom, dpi_scale)
            return
            
        self.is_tile_loading = True
        runnable = TileLoaderRunnable(self.view.document, self.page_number, zoom, dpi_scale, clip_rect, self)
        runnable.signals.finished.connect(self.view.on_page_tile_loaded, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(runnable)

    def on_tile_loaded(self, page_number, image, zoom, clip_rect):
        self.is_tile_loading = False
        if page_number != self.page_number:
            return
            
        current_zoom = self.view.transform().m11()
        if abs(current_zoom - zoom) > 0.1:
            # Stale zoom; dispatch pending tile request if present
            if self.pending_tile_req:
                req = self.pending_tile_req
                self.pending_tile_req = None
                self.update_tile(*req)
            return
            
        if image:
            pixmap = QPixmap.fromImage(image)
            new_tile = QGraphicsPixmapItem(pixmap, self)
            new_tile.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            new_tile.setZValue(0.5)  # Above base layer (0.0), below annotations
            
            clip_w = clip_rect[2] - clip_rect[0]
            item_w = new_tile.boundingRect().width()
            if clip_w > 0 and item_w > 0:
                new_tile.setScale(clip_w / item_w)
            new_tile.setPos(clip_rect[0], clip_rect[1])
            
            if self.tile_item and self.tile_item.scene():
                self.scene().removeItem(self.tile_item)
            self.tile_item = new_tile
            self.current_tile_rect = clip_rect
            self.current_tile_zoom = zoom
            
        if self.pending_tile_req:
            req = self.pending_tile_req
            self.pending_tile_req = None
            self.update_tile(*req)

    def clear_tile(self):
        self.is_tile_loading = False
        self.pending_tile_req = None
        if self.tile_item:
            if self.scene():
                self.scene().removeItem(self.tile_item)
            self.tile_item = None
        self.current_tile_rect = None
        self.current_tile_zoom = 0.0
            
    def unload(self):
        self.is_loading = False
        self.clear_tile()
        if not self.is_loaded:
            return
            
        if self.pixmap_item:
            if self.scene():
                self.scene().removeItem(self.pixmap_item)
            self.pixmap_item = None
            
        self.is_loaded = False


class PDFView(QGraphicsView):
    page_changed = Signal(int)
    text_action_requested = Signal(str, str) # action_type, text
    annotation_completed = Signal()
    annotation_changed = Signal(int) # page_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        from ui.theme_manager import ThemeManager
        self.setBackgroundBrush(ThemeManager.get_pdf_bg_color())
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        
        self.document = None
        self.current_page = 0
        self.page_items = []
        self._is_jumping = False
        self.selection_items = []
        self.current_selected_text = ""
        
        # Tool state
        self.tool_mode = AnnotationTool.NONE
        self._freehand_item = None
        self._freehand_stroke = []
        self._freehand_path_item = None
        self._textbox_start = None
        self._textbox_item = None
        self._moving_annot = None
        self._moving_annot_page = None
        self._moving_start_scene = None
        self._moving_has_dragged = False
        self._moving_rect_preview = None
        self._moving_global_pos = None
        self._hl_start_scene = None
        self._hl_item = None
        self._hl_preview_items = []
        
        # Floating Annotation Toolbar
        self.annotation_bar = FloatingAnnotationBar(self)
        self.annotation_bar.tool_changed.connect(self.set_annotation_tool)
        self.annotation_completed.connect(self.annotation_bar.clear_selection)
        self.annotation_bar.hide()
        
        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.timeout.connect(self._reload_visible)
        
        self.tile_timer = QTimer(self)
        self.tile_timer.setSingleShot(True)
        self.tile_timer.timeout.connect(self.update_viewport_tiles)

    def update_annotation_bar_pos(self):
        if hasattr(self, "annotation_bar") and self.annotation_bar:
            w = self.width()
            bw = self.annotation_bar.width()
            if bw < 50:
                bw = 140
            x = (w - bw) // 2
            y = 12
            self.annotation_bar.move(x, y)
            self.annotation_bar.raise_()

    def set_annotation_tool(self, tool: AnnotationTool):
        self.tool_mode = tool
        
        # Clear previous visual selections
        for item in self.selection_items:
            if item.scene():
                self.scene.removeItem(item)
        self.selection_items.clear()
        self.current_selected_text = ""
        
        if tool == AnnotationTool.NONE:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif tool == AnnotationTool.HIGHLIGHT_TEXT:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif tool == AnnotationTool.HIGHLIGHT_FREEHAND:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == AnnotationTool.TEXT_BOX:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == AnnotationTool.NOTE:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_theme(self, app_style: str = "Native", color_mode: str = "Light"):
        from ui.theme_manager import ThemeManager
        self.setBackgroundBrush(ThemeManager.get_pdf_bg_color(app_style, color_mode))
        if hasattr(self, "annotation_bar") and self.annotation_bar:
            self.annotation_bar.update_theme(app_style, color_mode)
        
    def dragEnterEvent(self, event):
        event.ignore()
        
    def dropEvent(self, event):
        event.ignore()

    def on_page_image_loaded(self, page_number, image, zoom, page_item):
        import shiboken6
        if shiboken6.isValid(page_item):
            page_item.on_image_loaded(page_number, image, zoom)

    def on_page_tile_loaded(self, page_number, image, zoom, clip_rect, page_item):
        import shiboken6
        if shiboken6.isValid(page_item):
            page_item.on_tile_loaded(page_number, image, zoom, clip_rect)

    def update_viewport_tiles(self):
        if not self.document or not self.page_items:
            return
            
        zoom = self.transform().m11()
        dpi_scale = self.devicePixelRatioF()
        
        if zoom <= 1.2:
            for item in self.page_items:
                item.clear_tile()
            return
            
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        for item in self.page_items:
            item_scene_rect = item.sceneBoundingRect()
            if viewport_rect.intersects(item_scene_rect):
                inter_scene = viewport_rect.intersected(item_scene_rect)
                inter_item = item.mapFromScene(inter_scene).boundingRect()
                
                w = item.rect().width()
                h = item.rect().height()
                margin = 60.0
                x0 = max(0.0, inter_item.left() - margin)
                y0 = max(0.0, inter_item.top() - margin)
                x1 = min(w, inter_item.right() + margin)
                y1 = min(h, inter_item.bottom() + margin)
                
                item.update_tile((x0, y0, x1, y1), zoom, dpi_scale)
            else:
                item.clear_tile()
        
    def set_document(self, doc: PDFDocument):
        self.document = doc
        self.current_page = 0
        self.resetTransform()
        self.render_document()
        
    def render_document(self):
        if hasattr(self, "tile_timer"):
            self.tile_timer.stop()
        self.scene.clear()
        self.selection_items.clear()
        self.page_items.clear()
        self.current_selected_text = ""
        
        if not self.document or self.document.page_count == 0:
            if hasattr(self, "annotation_bar"):
                self.annotation_bar.hide()
            return
            
        if hasattr(self, "annotation_bar"):
            self.annotation_bar.show()
            self.update_annotation_bar_pos()
            
        y_offset = 0.0
        gap = 20.0
        
        for i in range(self.document.page_count):
            width, height = self.document.get_page_size(i)
            
            item = PageItem(i, self)
            item.setRect(0, 0, width, height)
            item.setPos(0, y_offset)
            
            self.scene.addItem(item)
            self.page_items.append(item)
            
            y_offset += height + gap
            
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.check_visibility()
        
    def check_visibility(self):
        if not self.document:
            return
            
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        max_visible_area = 0
        most_visible_page = self.current_page
        
        for item in self.page_items:
            item_rect = item.sceneBoundingRect()
            if viewport_rect.intersects(item_rect):
                item.load()
                
                intersect_rect = viewport_rect.intersected(item_rect)
                visible_area = intersect_rect.width() * intersect_rect.height()
                if visible_area > max_visible_area:
                    max_visible_area = visible_area
                    most_visible_page = item.page_number
            else:
                distance = min(abs(viewport_rect.bottom() - item_rect.top()), 
                               abs(item_rect.bottom() - viewport_rect.top()))
                if distance > 2000:
                    item.unload()
                    
        if not self._is_jumping and most_visible_page != self.current_page:
            self.current_page = most_visible_page
            self.page_changed.emit(self.current_page)
            
    def set_current_page(self, page_num: int):
        if self.document and 0 <= page_num < len(self.page_items):
            self._is_jumping = True
            self.current_page = page_num
            target_item = self.page_items[page_num]
            target_rect = target_item.sceneBoundingRect()
            
            view_rect = self.viewport().rect()
            scene_top_left = self.mapToScene(view_rect.topLeft())
            scene_bottom_right = self.mapToScene(view_rect.bottomRight())
            view_height_in_scene = scene_bottom_right.y() - scene_top_left.y()
            
            center_x = target_rect.center().x()
            center_y = target_rect.top() + (view_height_in_scene / 2)
            
            self.centerOn(center_x, center_y)
            self.check_visibility()
            self.page_changed.emit(self.current_page)
            self._is_jumping = False
            
    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.check_visibility()
        if self.transform().m11() > 1.2:
            self.tile_timer.start(100)
        
    def resizeEvent(self, event):
        old_size = event.oldSize()
        new_size = event.size()
        if self.document and old_size.isValid() and old_size.width() > 0 and new_size.width() > 0 and old_size.width() != new_size.width():
            scale_factor = new_size.width() / old_size.width()
            self.scale(scale_factor, scale_factor)
            self._debounce_reload()
        super().resizeEvent(event)
        self.check_visibility()
        self.update_annotation_bar_pos()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_annotation_bar_pos()
        
    def next_page(self):
        if self.document and self.current_page < self.document.page_count - 1:
            self.set_current_page(self.current_page + 1)
            
    def prev_page(self):
        if self.document and self.current_page > 0:
            self.set_current_page(self.current_page - 1)
            
    def _debounce_reload(self):
        self.reload_timer.start(150)
        if self.transform().m11() > 1.2:
            self.tile_timer.start(150)

    def _reload_visible(self):
        if not self.document:
            return
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        for item in self.page_items:
            item_rect = item.sceneBoundingRect()
            if viewport_rect.intersects(item_rect):
                if item.is_loaded:
                    item.reload()
                else:
                    item.load()
            else:
                distance = min(abs(viewport_rect.bottom() - item_rect.top()), 
                               abs(item_rect.bottom() - viewport_rect.top()))
                if distance > 2000:
                    item.unload()
        if self.transform().m11() > 1.2:
            self.update_viewport_tiles()

    def zoom_in(self):
        self.scale(1.2, 1.2)
        self._reload_visible()
        if self.transform().m11() > 1.2:
            self.tile_timer.start(100)
        
    def zoom_out(self):
        self.scale(1 / 1.2, 1 / 1.2)
        self._reload_visible()
        if self.transform().m11() > 1.2:
            self.tile_timer.start(100)
        else:
            for item in self.page_items:
                item.clear_tile()
        
    def viewportEvent(self, event):
        if event.type() == event.Type.NativeGesture:
            if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                zoom_multiplier = 1.0 + event.value()
                self.scale(zoom_multiplier, zoom_multiplier)
                self._debounce_reload()
                return True
        return super().viewportEvent(event)
        
    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            zoom_multiplier = 1.0 + (event.angleDelta().y() / 1200.0)
            if zoom_multiplier > 0:
                self.scale(zoom_multiplier, zoom_multiplier)
                self._debounce_reload()
            event.accept()
        else:
            super().wheelEvent(event)

    def _find_page_item_at_scene_pos(self, scene_pos):
        for item in self.page_items:
            if item.sceneBoundingRect().contains(scene_pos):
                return item
        return None

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        # 1. Note Tool
        if self.tool_mode == AnnotationTool.NOTE:
            item = self._find_page_item_at_scene_pos(scene_pos)
            if item and self.document:
                local_x = scene_pos.x() - item.sceneBoundingRect().x()
                local_y = scene_pos.y() - item.sceneBoundingRect().y()
                
                dlg = NoteDialog(parent=self)
                dlg.move(event.globalPos())
                if dlg.exec() and dlg.get_text():
                    self.document.add_text_annotation(item.page_number, (local_x, local_y), dlg.get_text())
                    item.unload()
                    item.load()
                    self.annotation_changed.emit(item.page_number)
                    self.annotation_completed.emit()
            return

        # 2. Freehand Highlight Tool
        if self.tool_mode == AnnotationTool.HIGHLIGHT_FREEHAND:
            item = self._find_page_item_at_scene_pos(scene_pos)
            if item:
                self._freehand_item = item
                local_x = scene_pos.x() - item.sceneBoundingRect().x()
                local_y = scene_pos.y() - item.sceneBoundingRect().y()
                self._freehand_stroke = [(local_x, local_y)]
                
                path = QPainterPath()
                path.moveTo(scene_pos)
                self._freehand_path_item = QGraphicsPathItem(path)
                self._freehand_path_item.setPen(QPen(QColor(255, 214, 10, 160), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                self.scene.addItem(self._freehand_path_item)
            return

        # 3. Highlight Text Tool
        if self.tool_mode == AnnotationTool.HIGHLIGHT_TEXT:
            item = self._find_page_item_at_scene_pos(scene_pos)
            if item and self.document:
                self._hl_start_scene = scene_pos
                self._hl_item = item
                self._hl_preview_items = []
                self._hl_cached_words = self.document.get_page_words(item.page_number)
            return

        # 4. Text Box Tool
        if self.tool_mode == AnnotationTool.TEXT_BOX:
            item = self._find_page_item_at_scene_pos(scene_pos)
            if item:
                self._textbox_start = scene_pos
                self._textbox_item = item
            super().mousePressEvent(event)
            return

        # 5. Existing Annotation Click / Drag Check (when no active tool is selected)
        if self.tool_mode == AnnotationTool.NONE and self.document:
            item = self._find_page_item_at_scene_pos(scene_pos)
            if item:
                local_x = scene_pos.x() - item.sceneBoundingRect().x()
                local_y = scene_pos.y() - item.sceneBoundingRect().y()
                annot = self.document.get_annotation_at_point(item.page_number, local_x, local_y)
                if annot:
                    self._moving_annot = annot
                    self._moving_annot_page = item
                    self._moving_start_scene = scene_pos
                    self._moving_has_dragged = False
                    self._moving_global_pos = event.globalPos()
                    return

        # 6. Standard Text Selection Clear
        modifiers = QApplication.keyboardModifiers()
        shift_held = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        
        if not shift_held:
            for item in self.selection_items:
                if item.scene():
                    self.scene.removeItem(item)
            self.selection_items.clear()
            self.current_selected_text = ""
        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        # 1. Moving an existing annotation
        if self._moving_annot and self._moving_annot_page:
            dx = scene_pos.x() - self._moving_start_scene.x()
            dy = scene_pos.y() - self._moving_start_scene.y()
            if abs(dx) > 4 or abs(dy) > 4 or self._moving_has_dragged:
                self._moving_has_dragged = True
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                r = self._moving_annot.rect
                page_top_left = self._moving_annot_page.sceneBoundingRect().topLeft()
                
                if not self._moving_rect_preview:
                    init_rect = QRectF(page_top_left.x() + r.x0, page_top_left.y() + r.y0, r.width, r.height)
                    self._moving_rect_preview = QGraphicsRectItem(init_rect)
                    self._moving_rect_preview.setPen(QPen(QColor(0, 122, 255), 1.5, Qt.PenStyle.DashLine))
                    self._moving_rect_preview.setBrush(QColor(0, 122, 255, 40))
                    self.scene.addItem(self._moving_rect_preview)
                
                self._moving_rect_preview.setRect(QRectF(page_top_left.x() + r.x0 + dx, page_top_left.y() + r.y0 + dy, r.width, r.height))
                return
        
        # 2. Freehand Highlight Drag
        if self.tool_mode == AnnotationTool.HIGHLIGHT_FREEHAND and self._freehand_item and self._freehand_path_item:
            item = self._freehand_item
            local_x = scene_pos.x() - item.sceneBoundingRect().x()
            local_y = scene_pos.y() - item.sceneBoundingRect().y()
            self._freehand_stroke.append((local_x, local_y))
            
            path = QPainterPath()
            start_scene = item.sceneBoundingRect().topLeft()
            path.moveTo(start_scene.x() + self._freehand_stroke[0][0], start_scene.y() + self._freehand_stroke[0][1])
            for pt in self._freehand_stroke[1:]:
                path.lineTo(start_scene.x() + pt[0], start_scene.y() + pt[1])
            self._freehand_path_item.setPath(path)
            return
            
        # 3. Highlight Text Recognition Live Preview
        if self.tool_mode == AnnotationTool.HIGHLIGHT_TEXT and getattr(self, "_hl_item", None) and self.document:
            item = self._hl_item
            p0 = (self._hl_start_scene.x() - item.sceneBoundingRect().x(), self._hl_start_scene.y() - item.sceneBoundingRect().y())
            p1 = (scene_pos.x() - item.sceneBoundingRect().x(), scene_pos.y() - item.sceneBoundingRect().y())
            cached_words = getattr(self, "_hl_cached_words", None)
            _, line_rects = self.document.get_text_range_rects(item.page_number, p0, p1, words=cached_words)
            
            for it in getattr(self, "_hl_preview_items", []):
                if it.scene():
                    self.scene.removeItem(it)
            self._hl_preview_items = []
            
            page_top_left = item.sceneBoundingRect().topLeft()
            for rx0, ry0, rx1, ry1 in line_rects:
                rect_scene = QRectF(page_top_left.x() + rx0, page_top_left.y() + ry0, rx1 - rx0, ry1 - ry0)
                preview = QGraphicsRectItem(rect_scene)
                preview.setBrush(QColor(255, 235, 59, 140))
                preview.setPen(QPen(Qt.GlobalColor.transparent))
                self.scene.addItem(preview)
                self._hl_preview_items.append(preview)
            return
            
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        # 0. Existing Annotation Click / Drag Release
        if self._moving_annot and self._moving_annot_page:
            annot = self._moving_annot
            item = self._moving_annot_page
            has_dragged = getattr(self, "_moving_has_dragged", False)
            global_click_pos = self._moving_global_pos or event.globalPos()
            
            if self._moving_rect_preview and self._moving_rect_preview.scene():
                self.scene.removeItem(self._moving_rect_preview)
            self._moving_rect_preview = None
            self._moving_annot = None
            self._moving_annot_page = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
            if has_dragged:
                dx = scene_pos.x() - self._moving_start_scene.x()
                dy = scene_pos.y() - self._moving_start_scene.y()
                self.document.move_annotation(item.page_number, annot, dx, dy)
                item.unload()
                item.load()
                self.annotation_changed.emit(item.page_number)
                return
            else:
                annot_type = annot.type[1]
                menu = QMenu(self)
                
                if annot_type in ("Text", "FreeText"):
                    edit_action = menu.addAction("Edit")
                    delete_action = menu.addAction("Delete")
                    
                    selected_act = menu.exec_(global_click_pos)
                    if selected_act == edit_action:
                        current_content = annot.info.get("content", "") or annot.get_text()
                        if annot_type == "Text":
                            dlg = NoteDialog(initial_text=current_content, parent=self)
                            dlg.move(global_click_pos)
                            if dlg.exec():
                                self.document.update_annotation_text(item.page_number, annot, dlg.get_text())
                                item.unload()
                                item.load()
                                self.annotation_changed.emit(item.page_number)
                        else:
                            dlg = TextBoxDialog(initial_text=current_content, parent=self)
                            dlg.move(global_click_pos)
                            if dlg.exec():
                                self.document.update_annotation_text(item.page_number, annot, dlg.get_text())
                                item.unload()
                                item.load()
                                self.annotation_changed.emit(item.page_number)
                    elif selected_act == delete_action:
                        self.document.delete_annotation(item.page_number, annot)
                        item.unload()
                        item.load()
                        self.annotation_changed.emit(item.page_number)
                    return
                elif annot_type in ("Highlight", "Ink"):
                    annot_text = self.document.get_annotation_text(item.page_number, annot)
                    explain_act = None
                    discuss_act = None
                    summary_act = None
                    
                    if annot_text:
                        explain_act = menu.addAction("Explain")
                        discuss_act = menu.addAction("Discuss")
                        summary_act = menu.addAction("Bullet summary")
                        menu.addSeparator()
                        
                    delete_action = menu.addAction("Delete")
                    selected_act = menu.exec_(global_click_pos)
                    
                    if selected_act == delete_action:
                        self.document.delete_annotation(item.page_number, annot)
                        item.unload()
                        item.load()
                        self.annotation_changed.emit(item.page_number)
                    elif selected_act == explain_act:
                        self.text_action_requested.emit("explain", annot_text)
                    elif selected_act == discuss_act:
                        self.text_action_requested.emit("discuss", annot_text)
                    elif selected_act == summary_act:
                        self.text_action_requested.emit("summary", annot_text)
                    return
        
        # 1. Freehand Highlight Release
        if self.tool_mode == AnnotationTool.HIGHLIGHT_FREEHAND and self._freehand_item:
            if self._freehand_path_item and self._freehand_path_item.scene():
                self.scene.removeItem(self._freehand_path_item)
            self._freehand_path_item = None
            
            if len(self._freehand_stroke) > 1 and self.document:
                item = self._freehand_item
                self.document.add_ink_annotation(item.page_number, [self._freehand_stroke], color=(1.0, 0.9, 0.0), width=10, opacity=0.5)
                item.unload()
                item.load()
                self.annotation_changed.emit(item.page_number)
                self.annotation_completed.emit()
                
            self._freehand_item = None
            self._freehand_stroke = []
            return

        # 2. Text Box Release
        if self.tool_mode == AnnotationTool.TEXT_BOX and getattr(self, "_textbox_item", None):
            item = self._textbox_item
            scene_start = getattr(self, "_textbox_start", scene_pos)
            
            x0 = min(scene_start.x(), scene_pos.x()) - item.sceneBoundingRect().x()
            y0 = min(scene_start.y(), scene_pos.y()) - item.sceneBoundingRect().y()
            w = max(140, abs(scene_pos.x() - scene_start.x()))
            h = max(36, abs(scene_pos.y() - scene_start.y()))
            
            super().mouseReleaseEvent(event)
            
            dlg = TextBoxDialog(parent=self)
            dlg.move(event.globalPos())
            if dlg.exec() and dlg.get_text() and self.document:
                self.document.add_freetext_annotation(item.page_number, (x0, y0, x0 + w, y0 + h), dlg.get_text(), font_size=12)
                item.unload()
                item.load()
                self.annotation_changed.emit(item.page_number)
                self.annotation_completed.emit()
                
            self._textbox_item = None
            self._textbox_start = None
            return

        # 3. Highlight Text Recognition Release
        if self.tool_mode == AnnotationTool.HIGHLIGHT_TEXT and getattr(self, "_hl_item", None):
            item = self._hl_item
            p0 = (self._hl_start_scene.x() - item.sceneBoundingRect().x(), self._hl_start_scene.y() - item.sceneBoundingRect().y())
            p1 = (scene_pos.x() - item.sceneBoundingRect().x(), scene_pos.y() - item.sceneBoundingRect().y())
            
            for it in getattr(self, "_hl_preview_items", []):
                if it.scene():
                    self.scene.removeItem(it)
            self._hl_preview_items = []
            
            if (abs(p1[0] - p0[0]) > 3 or abs(p1[1] - p0[1]) > 3) and self.document:
                cached_words = getattr(self, "_hl_cached_words", None)
                _, line_rects = self.document.get_text_range_rects(item.page_number, p0, p1, words=cached_words)
                if line_rects:
                    self.document.add_highlight_annotation(item.page_number, line_rects)
                    item.unload()
                    item.load()
                    self.annotation_changed.emit(item.page_number)
                    self.annotation_completed.emit()
                    
            self._hl_item = None
            self._hl_start_scene = None
            self._hl_cached_words = None
            return

        # 4. Standard Rubber Band Selection
        rubber_rect = self.rubberBandRect()
        is_rubber_band = self.dragMode() == QGraphicsView.DragMode.RubberBandDrag
        
        modifiers = QApplication.keyboardModifiers()
        shift_held = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        
        super().mouseReleaseEvent(event)
        
        if is_rubber_band and rubber_rect.isValid() and rubber_rect.width() > 5 and rubber_rect.height() > 5:
            scene_rect = self.mapToScene(rubber_rect).boundingRect()
            self._extract_text_from_scene_rect(scene_rect, append=shift_held)

    def mouseDoubleClickEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        modifiers = QApplication.keyboardModifiers()
        shift_held = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        
        if not shift_held:
            for item in self.selection_items:
                if item.scene():
                    self.scene.removeItem(item)
            self.selection_items.clear()
        
        for item in self.page_items:
            if item.sceneBoundingRect().contains(scene_pos) and self.document:
                local_x = scene_pos.x() - item.sceneBoundingRect().x()
                local_y = scene_pos.y() - item.sceneBoundingRect().y()
                
                word_info = self.document.get_word_at_point(item.page_number, local_x, local_y)
                if word_info:
                    word, rect_coords = word_info
                    
                    x0, y0, x1, y1 = rect_coords
                    unscaled_rect = QRectF(x0, y0, x1 - x0, y1 - y0)
                    unscaled_rect.translate(item.sceneBoundingRect().topLeft())
                    
                    highlight = QGraphicsRectItem(unscaled_rect)
                    highlight.setBrush(QColor(0, 120, 215, 80))
                    highlight.setPen(QPen(Qt.GlobalColor.transparent))
                    self.scene.addItem(highlight)
                    self.selection_items.append(highlight)
                    
                    if shift_held and self.current_selected_text:
                        self.current_selected_text += " " + word
                    else:
                        self.current_selected_text = word
                        
                    QApplication.clipboard().setText(self.current_selected_text)
                    logger.debug(f"Copied word to clipboard: {self.current_selected_text}")
                break
                
        super().mouseDoubleClickEvent(event)

    def _extract_text_from_scene_rect(self, scene_rect: QRectF, append=False):
        extracted_text = ""
        if not self.document:
            return
            
        for item in self.page_items:
            item_rect = item.sceneBoundingRect()
            if item_rect.intersects(scene_rect):
                intersect = item_rect.intersected(scene_rect)
                
                local_x = intersect.x() - item_rect.x()
                local_y = intersect.y() - item_rect.y()
                
                unscaled_rect = (
                    local_x,
                    local_y,
                    local_x + intersect.width(),
                    local_y + intersect.height()
                )
                
                text, word_rects = self.document.get_text_and_rects(item.page_number, unscaled_rect)
                if text.strip():
                    extracted_text += text + "\n"
                    
                    for rx0, ry0, rx1, ry1 in word_rects:
                        word_scene_rect = QRectF(rx0, ry0, rx1 - rx0, ry1 - ry0)
                        word_scene_rect.translate(item.sceneBoundingRect().topLeft())
                        
                        highlight = QGraphicsRectItem(word_scene_rect)
                        highlight.setBrush(QColor(0, 120, 215, 80))
                        highlight.setPen(QPen(Qt.GlobalColor.transparent))
                        self.scene.addItem(highlight)
                        self.selection_items.append(highlight)
                    
        if extracted_text.strip():
            if append and self.current_selected_text:
                final_text = self.current_selected_text + "\n" + extracted_text.strip()
            else:
                final_text = extracted_text.strip()
                
            self.current_selected_text = final_text
            QApplication.clipboard().setText(final_text)
            logger.debug(f"Copied text to clipboard: {final_text[:50]}...")
