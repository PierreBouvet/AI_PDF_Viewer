from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QApplication
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PySide6.QtCore import Qt, Signal, QRectF, QObject, QRunnable, QThreadPool
from backend.pdf_document import PDFDocument

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

class PageItem(QGraphicsRectItem):
    def __init__(self, page_number: int, view: 'PDFView', parent=None):
        super().__init__(parent)
        self.page_number = page_number
        self.view = view
        self.is_loaded = False
        self.pixmap_item = None
        
        # Styling the placeholder
        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setBrush(QColor(255, 255, 255))
        
    def load(self):
        if self.is_loaded or getattr(self, "is_loading", False):
            return
            
        self.is_loading = True
        dpi_scale = self.view.devicePixelRatioF()
        zoom = self.view.transform().m11()
        
        runnable = PageLoaderRunnable(self.view.document, self.page_number, zoom, dpi_scale, self)
        runnable.signals.finished.connect(self.view.on_page_image_loaded)
        QThreadPool.globalInstance().start(runnable)
        
    def on_image_loaded(self, page_number, image, zoom):
        # Only process if this is the expected page and we're still supposed to load it
        if page_number == self.page_number and getattr(self, "is_loading", False):
            if image:
                pixmap = QPixmap.fromImage(image)
                # Double check that we didn't get unloaded while waiting
                if not getattr(self, "is_loading", False):
                    return
                self.pixmap_item = QGraphicsPixmapItem(pixmap, self)
                self.pixmap_item.setScale(1.0 / zoom)
                self.is_loaded = True
        self.is_loading = False
            
    def unload(self):
        self.is_loading = False
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Appearance settings
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        self.document = None
        self.current_page = 0
        self.page_items = []
        self._is_jumping = False
        self.selection_items = []
        self.current_selected_text = ""
        
        from PySide6.QtCore import QTimer
        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.timeout.connect(self._reload_visible)
        
    def dragEnterEvent(self, event):
        event.ignore()
        
    def dropEvent(self, event):
        event.ignore()

    def on_page_image_loaded(self, page_number, image, zoom, page_item):
        """Called on the main thread when a page image has finished rendering."""
        page_item.on_image_loaded(page_number, image, zoom)
        
    def set_document(self, doc: PDFDocument):
        self.document = doc
        self.current_page = 0
        self.resetTransform()
        self.render_document()
        
    def render_document(self):
        """Layout all pages vertically in the scene."""
        self.scene.clear()
        self.selection_items.clear()
        self.page_items.clear()
        self.current_selected_text = ""
        
        if not self.document or self.document.page_count == 0:
            return
            
        y_offset = 0.0
        gap = 20.0  # Gap between pages
        
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
        """Load visible pages, unload hidden pages."""
        if not self.document:
            return
            
        viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        
        max_visible_area = 0
        most_visible_page = self.current_page
        
        for item in self.page_items:
            item_rect = item.sceneBoundingRect()
            if viewport_rect.intersects(item_rect):
                item.load()
                
                # Calculate visible area to find the "current" page
                intersect_rect = viewport_rect.intersected(item_rect)
                visible_area = intersect_rect.width() * intersect_rect.height()
                if visible_area > max_visible_area:
                    max_visible_area = visible_area
                    most_visible_page = item.page_number
            else:
                # Add a small buffer: keep 1 page above and below loaded to make scrolling smoother
                distance = min(abs(viewport_rect.bottom() - item_rect.top()), 
                               abs(item_rect.bottom() - viewport_rect.top()))
                if distance > 2000: # Arbitrary unload threshold
                    item.unload()
                    
        if not self._is_jumping and most_visible_page != self.current_page:
            self.current_page = most_visible_page
            self.page_changed.emit(self.current_page)
            
    def set_current_page(self, page_num: int):
        if self.document and 0 <= page_num < len(self.page_items):
            self._is_jumping = True
            self.current_page = page_num
            target_item = self.page_items[page_num]
            
            # Align the top of the page with the top of the view
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
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.check_visibility()
        
    def next_page(self):
        if self.document and self.current_page < self.document.page_count - 1:
            self.set_current_page(self.current_page + 1)
            
    def prev_page(self):
        if self.document and self.current_page > 0:
            self.set_current_page(self.current_page - 1)
            
    def _debounce_reload(self):
        self.reload_timer.start(200)

    def _reload_visible(self):
        for item in self.page_items:
            if item.is_loaded:
                item.unload()
        self.check_visibility()

    def zoom_in(self):
        self.scale(1.2, 1.2)
        self._reload_visible()
        
    def zoom_out(self):
        self.scale(1 / 1.2, 1 / 1.2)
        self._reload_visible()
        
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
            # Handle standard Ctrl+Wheel scrolling for mouse users
            zoom_multiplier = 1.0 + (event.angleDelta().y() / 1200.0)
            if zoom_multiplier > 0:
                self.scale(zoom_multiplier, zoom_multiplier)
                self._debounce_reload()
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        # Check if clicked on an existing selection
        clicked_on_selection = False
        for item in self.selection_items:
            if item.contains(item.mapFromScene(scene_pos)):
                clicked_on_selection = True
                break
                
        if clicked_on_selection and self.current_selected_text:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            explain_action = menu.addAction("Explain")
            discuss_action = menu.addAction("Discuss")
            summary_action = menu.addAction("Bullet summary")
            
            action = menu.exec_(event.globalPos())
            if action == explain_action:
                self.text_action_requested.emit("explain", self.current_selected_text)
            elif action == discuss_action:
                self.text_action_requested.emit("discuss", self.current_selected_text)
            elif action == summary_action:
                self.text_action_requested.emit("summary", self.current_selected_text)
            return # Do not clear selection or start rubber band
            
        modifiers = QApplication.keyboardModifiers()
        shift_held = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        
        if not shift_held:
            # Clear previous visual selections
            for item in self.selection_items:
                self.scene.removeItem(item)
            self.selection_items.clear()
            self.current_selected_text = ""
        
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
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
            # Clear previous selection
            for item in self.selection_items:
                self.scene.removeItem(item)
            self.selection_items.clear()
        
        for item in self.page_items:
            if item.sceneBoundingRect().contains(scene_pos):
                local_x = scene_pos.x() - item.sceneBoundingRect().x()
                local_y = scene_pos.y() - item.sceneBoundingRect().y()
                
                word_info = self.document.get_word_at_point(item.page_number, local_x, local_y)
                if word_info:
                    word, rect_coords = word_info
                    
                    x0, y0, x1, y1 = rect_coords
                    unscaled_rect = QRectF(x0, y0, x1 - x0, y1 - y0)
                    unscaled_rect.translate(item.sceneBoundingRect().topLeft())
                    
                    highlight = QGraphicsRectItem(unscaled_rect)
                    highlight.setBrush(QColor(0, 120, 215, 80)) # Semi-transparent blue
                    highlight.setPen(QPen(Qt.GlobalColor.transparent))
                    self.scene.addItem(highlight)
                    self.selection_items.append(highlight)
                    
                    if shift_held and self.current_selected_text:
                        self.current_selected_text += " " + word
                    else:
                        self.current_selected_text = word
                        
                    QApplication.clipboard().setText(self.current_selected_text)
                    print(f"Copied word to clipboard: {self.current_selected_text}")
                break
                
        super().mouseDoubleClickEvent(event)

    def _extract_text_from_scene_rect(self, scene_rect: QRectF, append=False):
        extracted_text = ""
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
                        highlight.setBrush(QColor(0, 120, 215, 80)) # Semi-transparent blue
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
            print(f"Copied text to clipboard: {final_text[:50]}...")

