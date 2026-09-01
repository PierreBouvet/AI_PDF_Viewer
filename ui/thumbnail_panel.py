from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QListView, QMenu
from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor
from backend.pdf_document import PDFDocument

class ThumbnailPanel(QWidget):
    page_selected = Signal(int)
    toggle_inclusion_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        
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
        self.document = None
        self.excluded_pages = set()
        self.included_pages = set()
        
    def set_document(self, doc: PDFDocument, excluded_pages: set = None, included_pages: set = None):
        self.document = doc
        self.excluded_pages = excluded_pages if excluded_pages is not None else set()
        self.included_pages = included_pages if included_pages is not None else set()
        self.list_widget.clear()
        
        if not self.document:
            return
            
        # Extract thumbnails for all pages
        for i in range(self.document.page_count):
            self._add_thumbnail_item(i)
            
    def refresh_thumbnail(self, page_index: int):
        if not self.document or page_index < 0 or page_index >= self.list_widget.count():
            return
            
        item = self.list_widget.item(page_index)
        if not item:
            return
            
        image = self.document.get_page_thumbnail(page_index, max_size=300)
        if image:
            image.setDevicePixelRatio(self.devicePixelRatioF())
            pixmap = QPixmap.fromImage(image)
            
            painter = QPainter(pixmap)
            is_ai = self.document.is_ai_generated(page_index)
            
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

    def _add_thumbnail_item(self, page_index: int):
        image = self.document.get_page_thumbnail(page_index, max_size=300)
        if image:
            image.setDevicePixelRatio(self.devicePixelRatioF())
            pixmap = QPixmap.fromImage(image)
            
            painter = QPainter(pixmap)
            is_ai = self.document.is_ai_generated(page_index)
            
            font = QFont("Arial", 5, QFont.Weight.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            
            logical_width = pixmap.width() / image.devicePixelRatio()
            
            if is_ai:
                painter.setPen(Qt.GlobalColor.red)
                painter.drawText(2, 8, "AI")
                
            if is_ai and page_index in self.included_pages:
                painter.setPen(Qt.GlobalColor.green)
                text = "Added"
                painter.drawText(logical_width - fm.horizontalAdvance(text) - 2, 8, text)
            elif not is_ai and page_index in self.excluded_pages:
                painter.setPen(Qt.GlobalColor.red)
                text = "Removed"
                painter.drawText(logical_width - fm.horizontalAdvance(text) - 2, 8, text)
                
            painter.end()
            
            icon = QIcon(pixmap)
            item = QListWidgetItem(icon, f"Page {page_index + 1}")
            item.setData(Qt.ItemDataRole.UserRole, page_index) # Store the page index
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)
                
    def set_current_page(self, page_num: int):
        """Highlight the current page in the thumbnail list."""
        if 0 <= page_num < self.list_widget.count():
            self.list_widget.setCurrentRow(page_num)

    def _on_item_clicked(self, item: QListWidgetItem):
        page_index = item.data(Qt.ItemDataRole.UserRole)
        self.page_selected.emit(page_index)

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
            
        page_index = item.data(Qt.ItemDataRole.UserRole)
        is_ai = self.document.is_ai_generated(page_index)
        
        menu = QMenu(self)
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
        if selected_action == action:
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
