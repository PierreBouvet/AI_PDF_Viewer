from typing import Optional, Set
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QListView, QMenu
from PySide6.QtCore import Signal, QSize, Qt, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen, QShortcut, QKeySequence, QImage
from backend.pdf_document import PDFDocument
from backend.logger import logger


class ThumbnailLoaderSignals(QObject):
    finished = Signal(int, object, bool, int)  # page_index, QImage or None, is_ai, gen_id


class ThumbnailLoaderRunnable(QRunnable):
    def __init__(self, document: PDFDocument, page_index: int, gen_id: int):
        super().__init__()
        self.document = document
        self.page_index = page_index
        self.gen_id = gen_id
        self.signals = ThumbnailLoaderSignals()

    def run(self):
        if not self.document:
            return
        try:
            image = self.document.get_page_thumbnail(self.page_index, max_size=300)
            is_ai = self.document.is_ai_generated(self.page_index)
            self.signals.finished.emit(self.page_index, image, is_ai, self.gen_id)
        except Exception as e:
            logger.debug(f"Failed to render thumbnail for page {self.page_index}: {e}")


class ThumbnailPanel(QWidget):
    page_selected = Signal(int)
    toggle_inclusion_requested = Signal(int)
    delete_page_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self._generation_id = 0
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 0, 0, 0)
        
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListView.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(120, 160))
        self.list_widget.setResizeMode(QListView.ResizeMode.Fixed)
        self.list_widget.setSpacing(10)
        
        # Context menu
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        
        # When an item is clicked, emit the page number
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        
        layout.addWidget(self.list_widget)
        self.document: Optional[PDFDocument] = None
        self.excluded_pages: Set[int] = set()
        self.included_pages: Set[int] = set()
        
        # Shortcuts for deletion
        self.del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.list_widget)
        self.del_shortcut.activated.connect(self._on_delete_shortcut)
        self.back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.list_widget)
        self.back_shortcut.activated.connect(self._on_delete_shortcut)

    def _on_delete_shortcut(self):
        current = self.list_widget.currentItem()
        if current:
            page_index = current.data(Qt.ItemDataRole.UserRole)
            self.delete_page_requested.emit(page_index)

    def _create_placeholder_pixmap(self) -> QPixmap:
        size = self.list_widget.iconSize()
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(int(size.width() * dpr), int(size.height() * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(QColor(245, 245, 247))
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor(220, 220, 225), 1))
        painter.drawRect(0, 0, size.width() - 1, size.height() - 1)
        painter.end()
        return pixmap

    def set_document(self, doc: PDFDocument, excluded_pages: set = None, included_pages: set = None):
        self._generation_id += 1
        gen_id = self._generation_id
        
        self.document = doc
        self.excluded_pages = excluded_pages if excluded_pages is not None else set()
        self.included_pages = included_pages if included_pages is not None else set()
        self.list_widget.clear()
        
        if not self.document or self.document.page_count <= 0:
            return
            
        placeholder_pixmap = self._create_placeholder_pixmap()
        placeholder_icon = QIcon(placeholder_pixmap)
        
        # Populate all placeholder items immediately (non-blocking)
        for i in range(self.document.page_count):
            item = QListWidgetItem(placeholder_icon, f"Page {i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)
            
            # Dispatch background worker to render thumbnail asynchronously
            runnable = ThumbnailLoaderRunnable(self.document, i, gen_id)
            runnable.signals.finished.connect(self._on_thumbnail_loaded, Qt.ConnectionType.QueuedConnection)
            QThreadPool.globalInstance().start(runnable)

    def refresh_thumbnail(self, page_index: int):
        if not self.document or page_index < 0 or page_index >= self.list_widget.count():
            return
        runnable = ThumbnailLoaderRunnable(self.document, page_index, self._generation_id)
        runnable.signals.finished.connect(self._on_thumbnail_loaded, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(runnable)

    def _on_thumbnail_loaded(self, page_index: int, image: Optional[QImage], is_ai: bool, gen_id: int):
        if gen_id != self._generation_id or not self.document:
            return
        if page_index < 0 or page_index >= self.list_widget.count():
            return
        item = self.list_widget.item(page_index)
        if not item or item.data(Qt.ItemDataRole.UserRole) != page_index:
            return
        if not image:
            return
            
        image.setDevicePixelRatio(self.devicePixelRatioF())
        pixmap = QPixmap.fromImage(image)
        
        painter = QPainter(pixmap)
        font = QFont("Arial", 5, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        
        logical_width = pixmap.width() / image.devicePixelRatio()
        
        # Draw AI tag top-left
        if is_ai:
            painter.setPen(Qt.GlobalColor.red)
            painter.drawText(2, 8, "AI")
            
        # Draw Status tags top-right
        if is_ai and page_index in self.included_pages:
            painter.setPen(Qt.GlobalColor.green)
            text = "Added"
            painter.drawText(logical_width - fm.horizontalAdvance(text) - 2, 8, text)
        elif not is_ai and page_index in self.excluded_pages:
            painter.setPen(Qt.GlobalColor.red)
            text = "Removed"
            painter.drawText(logical_width - fm.horizontalAdvance(text) - 2, 8, text)
            
        painter.end()
        item.setIcon(QIcon(pixmap))

    def set_current_page(self, page_num: int):
        """Highlight the current page in the thumbnail list."""
        if 0 <= page_num < self.list_widget.count():
            self.list_widget.setCurrentRow(page_num)

    def _on_item_clicked(self, item: QListWidgetItem):
        page_index = item.data(Qt.ItemDataRole.UserRole)
        self.page_selected.emit(page_index)

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item or not self.document:
            return
            
        page_index = item.data(Qt.ItemDataRole.UserRole)
        is_ai = self.document.is_ai_generated(page_index)
        
        menu = QMenu(self)
        delete_action = menu.addAction("Delete Page")
        menu.addSeparator()
        
        if is_ai:
            if page_index in self.included_pages:
                action = menu.addAction("Remove from AI Context")
            else:
                action = menu.addAction("Add to AI Context")
        else:
            if page_index in self.excluded_pages:
                action = menu.addAction("Add to AI Context")
            else:
                action = menu.addAction("Remove from AI Context")
                
        selected_action = menu.exec(self.list_widget.mapToGlobal(pos))
        if selected_action == delete_action:
            self.delete_page_requested.emit(page_index)
        elif selected_action == action:
            self.toggle_inclusion_requested.emit(page_index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Calculate new icon size based on panel width
        # Subtracting margins and scrollbar width approx
        w = self.width() - 35
        if w < 50:
            w = 50
        h = int(w * 1.414) # Standard A4 aspect ratio approx
        self.list_widget.setIconSize(QSize(w, h))
