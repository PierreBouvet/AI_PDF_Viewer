import os
import re
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox,
    QWidget, QFrame, QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QIcon, QFont, QColor

from backend.zotero_manager import ZoteroManager
from backend.ai_assistant import AIAssistant
from backend.logger import logger


class ZoteroOperationWorker(QThread):
    """Background worker for long-running Zotero operations (creating items, uploading files)."""
    finished_signal = Signal(bool, str, object)

    def __init__(self, operation_func, *args, **kwargs):
        super().__init__()
        self.operation_func = operation_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.operation_func(*self.args, **self.kwargs)
            self.finished_signal.emit(True, "", result)
        except Exception as e:
            self.finished_signal.emit(False, str(e), None)


class AIWorker(QThread):
    """Background worker for AI metadata and keyword extraction."""
    finished_signal = Signal(bool, str, object)

    def __init__(self, task_type: str, assistant: AIAssistant, text: str):
        super().__init__()
        self.task_type = task_type
        self.assistant = assistant
        self.text = text

    def run(self):
        try:
            if self.task_type == "keywords":
                keywords = self.assistant.generate_keywords(self.text)
                self.finished_signal.emit(True, "", keywords)
            elif self.task_type == "metadata":
                metadata = self.assistant.extract_bibliographic_metadata(self.text)
                self.finished_signal.emit(True, "", metadata)
        except Exception as e:
            self.finished_signal.emit(False, str(e), None)


class ZoteroDialog(QDialog):
    """
    Dialog for inspecting and managing the Zotero status of a PDF:
    - View/Edit bibliographic metadata
    - Select collections / sub-collections (directories)
    - Add custom or AI-generated keywords/tags
    - View and create notes
    - Add the PDF to Zotero with attachment
    """
    item_updated = Signal(dict)

    def __init__(
        self,
        pdf_path: str,
        zotero_item: Optional[Dict[str, Any]] = None,
        zotero_manager: Optional[ZoteroManager] = None,
        ai_assistant: Optional[AIAssistant] = None,
        first_page_text: str = "",
        full_text: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.zotero_item = zotero_item
        self.zotero_manager = zotero_manager or ZoteroManager()
        self.ai_assistant = ai_assistant
        self.first_page_text = first_page_text
        self.full_text = full_text

        self.tags = []
        self._worker = None

        self.setWindowTitle(f"Zotero - {os.path.basename(pdf_path)}")
        self.resize(720, 620)
        self.setMinimumSize(600, 500)

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # 1. Status Banner Header
        self.status_banner = QFrame()
        self.status_banner.setObjectName("statusBanner")
        banner_layout = QHBoxLayout(self.status_banner)
        banner_layout.setContentsMargins(12, 10, 12, 10)
        banner_layout.setSpacing(10)

        self.status_icon = QLabel("📚")
        self.status_icon.setStyleSheet("font-size: 16pt;")
        self.status_label = QLabel("Checking Zotero Library...")
        self.status_label.setStyleSheet("font-size: 11pt; font-weight: 600;")
        banner_layout.addWidget(self.status_icon)
        banner_layout.addWidget(self.status_label, 1)

        self.web_link_btn = QPushButton("View on Zotero Web ↗")
        self.web_link_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #007aff;
                border: 1px solid #007aff;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #e5f1ff;
            }
        """)
        self.web_link_btn.clicked.connect(self._open_zotero_web)
        self.web_link_btn.setVisible(False)
        banner_layout.addWidget(self.web_link_btn)

        main_layout.addWidget(self.status_banner)

        # 2. Main Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d1d1d6;
                border-radius: 8px;
                background-color: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #f2f2f7;
                color: #555555;
                padding: 7px 16px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #d1d1d6;
                border-bottom: none;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #007aff;
                font-weight: 600;
            }
        """)

        self.tab_metadata = self._create_metadata_tab()
        self.tab_collections = self._create_collections_tab()
        self.tab_keywords = self._create_keywords_tab()
        self.tab_notes = self._create_notes_tab()

        self.tabs.addTab(self.tab_metadata, "Metadata")
        self.tabs.addTab(self.tab_collections, "Collections")
        self.tabs.addTab(self.tab_keywords, "Keywords / Tags")
        self.tabs.addTab(self.tab_notes, "Notes")

        main_layout.addWidget(self.tabs, 1)

        # 3. Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)
        bottom_bar.setSpacing(10)

        self.status_feedback = QLabel("")
        self.status_feedback.setStyleSheet("font-size: 9.5pt; color: #555;")
        bottom_bar.addWidget(self.status_feedback, 1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5e5ea;
                color: #1c1c1e;
                border: none;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #d1d1d6;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        bottom_bar.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save to Zotero")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 7px 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #b0b0b5;
            }
        """)
        self.save_btn.clicked.connect(self._save_to_zotero)
        bottom_bar.addWidget(self.save_btn)

        main_layout.addLayout(bottom_bar)

    def _create_metadata_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # AI Extract row
        ai_row = QHBoxLayout()
        ai_row.addWidget(QLabel("Bibliographic Information"))
        ai_row.addStretch()

        self.ai_meta_btn = QPushButton("✨ Extract with AI")
        self.ai_meta_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5f1ff;
                color: #007aff;
                border: 1px solid #007aff;
                border-radius: 5px;
                padding: 4px 10px;
                font-weight: 500;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #cce4ff;
            }
        """)
        self.ai_meta_btn.clicked.connect(self._extract_metadata_ai)
        ai_row.addWidget(self.ai_meta_btn)
        layout.addLayout(ai_row)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.input_type = QComboBox()
        self.input_type.addItems(["journalArticle", "book", "conferencePaper", "report", "preprint", "thesis"])
        form.addRow("Item Type:", self.input_type)

        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Paper or article title")
        form.addRow("Title:", self.input_title)

        self.input_authors = QLineEdit()
        self.input_authors.setPlaceholderText("Authors (e.g. Bouvet, Pierre; Doe, Jane)")
        form.addRow("Authors:", self.input_authors)

        self.input_publication = QLineEdit()
        self.input_publication.setPlaceholderText("Journal, Conference, or Publisher")
        form.addRow("Publication:", self.input_publication)

        self.input_date = QLineEdit()
        self.input_date.setPlaceholderText("Year or Date (e.g. 2026)")
        form.addRow("Date / Year:", self.input_date)

        self.input_doi = QLineEdit()
        self.input_doi.setPlaceholderText("10.xxxx/xxxx")
        form.addRow("DOI:", self.input_doi)

        self.input_abstract = QTextEdit()
        self.input_abstract.setPlaceholderText("Abstract or summary...")
        self.input_abstract.setMaximumHeight(90)
        form.addRow("Abstract:", self.input_abstract)

        layout.addLayout(form)
        layout.addStretch()
        return widget

    def _create_collections_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        desc = QLabel("Select directories / sub-directories where this document should be filed:")
        desc.setStyleSheet("color: #636366; font-size: 9pt;")
        layout.addWidget(desc)

        # Filter / Search
        self.coll_search = QLineEdit()
        self.coll_search.setPlaceholderText("🔍 Filter collections...")
        self.coll_search.textChanged.connect(self._filter_collections)
        layout.addWidget(self.coll_search)

        # Tree Widget
        self.tree_collections = QTreeWidget()
        self.tree_collections.setHeaderHidden(True)
        self.tree_collections.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #d1d1d6;
                border-radius: 6px;
                padding: 4px;
            }
            QTreeWidget::item {
                padding: 4px;
            }
        """)
        layout.addWidget(self.tree_collections, 1)

        # Collection creation actions
        coll_btn_row = QHBoxLayout()
        self.btn_new_coll = QPushButton("+ New Top Collection")
        self.btn_new_coll.setStyleSheet("padding: 4px 10px; font-size: 9pt;")
        self.btn_new_coll.clicked.connect(lambda: self._create_new_collection(parent_key=None))
        coll_btn_row.addWidget(self.btn_new_coll)

        self.btn_new_subcoll = QPushButton("+ New Sub-collection")
        self.btn_new_subcoll.setStyleSheet("padding: 4px 10px; font-size: 9pt;")
        self.btn_new_subcoll.clicked.connect(self._create_subcollection_for_selected)
        coll_btn_row.addWidget(self.btn_new_subcoll)

        coll_btn_row.addStretch()
        layout.addLayout(coll_btn_row)
        return widget

    def _create_keywords_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header + AI generate button
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Document Tags & Keywords"))
        header_row.addStretch()

        self.ai_keywords_btn = QPushButton("✨ Generate AI Keywords")
        self.ai_keywords_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5f1ff;
                color: #007aff;
                border: 1px solid #007aff;
                border-radius: 5px;
                padding: 4px 10px;
                font-weight: 500;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #cce4ff;
            }
        """)
        self.ai_keywords_btn.clicked.connect(self._generate_keywords_ai)
        header_row.addWidget(self.ai_keywords_btn)
        layout.addLayout(header_row)

        # Input to add manual tag
        tag_input_row = QHBoxLayout()
        self.input_new_tag = QLineEdit()
        self.input_new_tag.setPlaceholderText("Enter keyword or tag name...")
        self.input_new_tag.returnPressed.connect(self._add_tag_from_input)
        tag_input_row.addWidget(self.input_new_tag, 1)

        self.btn_add_tag = QPushButton("+ Add")
        self.btn_add_tag.setStyleSheet("padding: 5px 12px;")
        self.btn_add_tag.clicked.connect(self._add_tag_from_input)
        tag_input_row.addWidget(self.btn_add_tag)
        layout.addLayout(tag_input_row)

        # Tags Container Area
        self.tags_scroll = QScrollArea()
        self.tags_scroll.setWidgetResizable(True)
        self.tags_scroll.setStyleSheet("QScrollArea { border: 1px solid #d1d1d6; border-radius: 6px; background-color: #fafafa; }")

        self.tags_container = QWidget()
        self.tags_layout = QVBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(8, 8, 8, 8)
        self.tags_layout.setSpacing(6)
        self.tags_layout.addStretch()

        self.tags_scroll.setWidget(self.tags_container)
        layout.addWidget(self.tags_scroll, 1)

        return widget

    def _create_notes_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        layout.addWidget(QLabel("<b>Existing Notes in Zotero:</b>"))

        self.notes_scroll = QScrollArea()
        self.notes_scroll.setWidgetResizable(True)
        self.notes_scroll.setStyleSheet("QScrollArea { border: 1px solid #d1d1d6; border-radius: 6px; background-color: #fafafa; }")
        self.notes_container = QWidget()
        self.notes_layout = QVBoxLayout(self.notes_container)
        self.notes_layout.setContentsMargins(8, 8, 8, 8)
        self.notes_layout.setSpacing(8)
        self.notes_layout.addStretch()
        self.notes_scroll.setWidget(self.notes_container)
        layout.addWidget(self.notes_scroll, 1)

        layout.addWidget(QLabel("<b>Add New Note:</b>"))
        self.input_new_note = QTextEdit()
        self.input_new_note.setPlaceholderText("Write a note to save to your Zotero library for this paper...")
        self.input_new_note.setMaximumHeight(100)
        layout.addWidget(self.input_new_note)

        return widget

    def _load_data(self):
        """Populates UI with data from matched Zotero item or local PDF metadata."""
        if self.zotero_item:
            self._update_status_banner(
                is_in_library=True,
                title=self.zotero_item.get("data", {}).get("title", "Found in Library"),
                item_key=self.zotero_item.get("data", {}).get("key", "")
            )
            data = self.zotero_item.get("data", {})
            self.input_title.setText(data.get("title", ""))
            self.input_publication.setText(data.get("publicationTitle", ""))
            self.input_date.setText(str(data.get("date", "")))
            self.input_doi.setText(data.get("DOI", ""))
            self.input_abstract.setPlainText(data.get("abstractNote", ""))

            # Creators
            creators = data.get("creators", [])
            creator_strs = []
            for c in creators:
                if c.get("lastName") and c.get("firstName"):
                    creator_strs.append(f"{c['lastName']}, {c['firstName']}")
                elif c.get("name"):
                    creator_strs.append(c["name"])
            self.input_authors.setText("; ".join(creator_strs))

            # Tags
            self.tags = [t["tag"] for t in data.get("tags", []) if "tag" in t]
            self._render_tags()

            # Existing notes
            item_key = data.get("key")
            if item_key:
                self._load_item_notes(item_key)

            self.save_btn.setText("Save Changes to Zotero")
        else:
            self._update_status_banner(is_in_library=False)
            self.input_title.setText(os.path.basename(self.pdf_path).replace(".pdf", ""))
            self.save_btn.setText("Add PDF to Zotero")

        # Load Collections hierarchy
        self._load_collections()

    def _update_status_banner(self, is_in_library: bool, title: str = "", item_key: str = ""):
        if is_in_library:
            self.status_banner.setStyleSheet("""
                #statusBanner {
                    background-color: #e8f5e9;
                    border: 1px solid #81c784;
                    border-radius: 8px;
                }
            """)
            self.status_icon.setText("✅")
            self.status_label.setText(f"In Zotero Library: {title[:40]}..." if len(title) > 40 else f"In Zotero Library: {title}")
            self.status_label.setStyleSheet("font-size: 11pt; font-weight: 600; color: #1b5e20;")
            self.web_link_btn.setVisible(bool(item_key))
            self.web_link_btn.setProperty("item_key", item_key)
        else:
            self.status_banner.setStyleSheet("""
                #statusBanner {
                    background-color: #fff3e0;
                    border: 1px solid #ffb74d;
                    border-radius: 8px;
                }
            """)
            self.status_icon.setText("○")
            self.status_label.setText("Not yet in Zotero Library")
            self.status_label.setStyleSheet("font-size: 11pt; font-weight: 600; color: #e65100;")
            self.web_link_btn.setVisible(False)

    def _load_collections(self):
        """Fetches and renders the collections tree."""
        self.tree_collections.clear()
        try:
            hierarchy = self.zotero_manager.get_collections_hierarchy()
            assigned_keys = set(self.zotero_item.get("data", {}).get("collections", [])) if self.zotero_item else set()

            def add_nodes(parent_item, nodes):
                for node in nodes:
                    item = QTreeWidgetItem()
                    item.setText(0, f"📁 {node['name']}")
                    item.setData(0, Qt.ItemDataRole.UserRole, node["key"])
                    item.setCheckState(0, Qt.CheckState.Checked if node["key"] in assigned_keys else Qt.CheckState.Unchecked)
                    if parent_item is None:
                        self.tree_collections.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    if node["children"]:
                        add_nodes(item, node["children"])

            add_nodes(None, hierarchy)
            self.tree_collections.expandAll()
        except Exception as e:
            logger.error(f"Failed to load Zotero collections tree: {e}")
            item = QTreeWidgetItem()
            item.setText(0, f"(Could not load collections: {e})")
            self.tree_collections.addTopLevelItem(item)

    def _filter_collections(self, text: str):
        query = text.strip().lower()

        def filter_item(item):
            match = query in item.text(0).lower()
            child_matches = False
            for i in range(item.childCount()):
                child = item.child(i)
                if filter_item(child):
                    child_matches = True
            visible = match or child_matches
            item.setHidden(not visible)
            if visible and query:
                item.setExpanded(True)
            return visible

        for i in range(self.tree_collections.topLevelItemCount()):
            filter_item(self.tree_collections.topLevelItem(i))

    def _create_new_collection(self, parent_key: Optional[str] = None):
        from PySide6.QtWidgets import QInputDialog
        title = "New Sub-collection" if parent_key else "New Top Collection"
        prompt = "Enter folder name:"
        name, ok = QInputDialog.getText(self, title, prompt)
        if ok and name.strip():
            try:
                self.zotero_manager.create_collection(name.strip(), parent_key=parent_key)
                self.zotero_manager.get_collections_hierarchy(refresh=True)
                self._load_collections()
                self.status_feedback.setText(f"✓ Created collection '{name.strip()}'")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create collection:\n{e}")

    def _create_subcollection_for_selected(self):
        selected = self.tree_collections.selectedItems()
        parent_key = selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None
        if not parent_key:
            QMessageBox.information(self, "Notice", "Please select a parent folder in the tree first.")
            return
        self._create_new_collection(parent_key=parent_key)

    def _render_tags(self):
        # Clear existing
        while self.tags_layout.count() > 1:
            child = self.tags_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for tag in self.tags:
            chip = QFrame()
            chip.setStyleSheet("""
                QFrame {
                    background-color: #e5f1ff;
                    border: 1px solid #b8daff;
                    border-radius: 12px;
                    padding: 2px 8px;
                }
            """)
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(4, 2, 4, 2)
            chip_layout.setSpacing(6)

            label = QLabel(tag)
            label.setStyleSheet("color: #004085; font-size: 9pt;")
            chip_layout.addWidget(label)

            del_btn = QPushButton("×")
            del_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    color: #721c24;
                    font-weight: bold;
                    font-size: 11pt;
                    padding: 0px 4px;
                }
                QPushButton:hover {
                    color: #f44336;
                }
            """)
            del_btn.clicked.connect(lambda _, t=tag: self._remove_tag(t))
            chip_layout.addWidget(del_btn)

            self.tags_layout.insertWidget(self.tags_layout.count() - 1, chip)

    def _add_tag_from_input(self):
        text = self.input_new_tag.text().strip()
        if text and text not in self.tags:
            self.tags.append(text)
            self._render_tags()
            self.input_new_tag.clear()

    def _remove_tag(self, tag: str):
        if tag in self.tags:
            self.tags.remove(tag)
            self._render_tags()

    def _load_item_notes(self, item_key: str):
        while self.notes_layout.count() > 1:
            child = self.notes_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        try:
            notes = self.zotero_manager.get_item_notes(item_key)
            if not notes:
                empty_lbl = QLabel("<i>No existing notes attached to this item.</i>")
                empty_lbl.setStyleSheet("color: #888; font-size: 9pt;")
                self.notes_layout.insertWidget(0, empty_lbl)
                return

            for n in notes:
                raw_html = n.get("data", {}).get("note", "")
                card = QFrame()
                card.setStyleSheet("""
                    QFrame {
                        background-color: #ffffff;
                        border: 1px solid #e0e0e0;
                        border-radius: 6px;
                        padding: 6px;
                    }
                """)
                c_layout = QVBoxLayout(card)
                c_layout.setContentsMargins(6, 6, 6, 6)
                lbl = QLabel(raw_html)
                lbl.setWordWrap(True)
                c_layout.addWidget(lbl)
                self.notes_layout.insertWidget(self.notes_layout.count() - 1, card)
        except Exception as e:
            logger.error(f"Failed to fetch notes: {e}")

    def _extract_metadata_ai(self):
        if not self.ai_assistant:
            QMessageBox.warning(self, "Warning", "AI Assistant is not configured.")
            return

        text = self.first_page_text or self.full_text[:4000]
        if not text.strip():
            QMessageBox.warning(self, "Warning", "No document text available for AI extraction.")
            return

        self.ai_meta_btn.setEnabled(False)
        self.ai_meta_btn.setText("Extracting...")
        self.status_feedback.setText("Extracting bibliographic metadata with AI...")

        self._ai_worker = AIWorker("metadata", self.ai_assistant, text)
        self._ai_worker.finished_signal.connect(self._on_metadata_extracted)
        self._ai_worker.start()

    def _on_metadata_extracted(self, success: bool, err_msg: str, metadata: Any):
        self.ai_meta_btn.setEnabled(True)
        self.ai_meta_btn.setText("✨ Extract with AI")
        if not success or not isinstance(metadata, dict):
            self.status_feedback.setText(f"AI extraction failed: {err_msg}")
            return

        if metadata.get("title"):
            self.input_title.setText(metadata["title"])
        if metadata.get("publicationTitle"):
            self.input_publication.setText(metadata["publicationTitle"])
        if metadata.get("date"):
            self.input_date.setText(str(metadata["date"]))
        if metadata.get("DOI"):
            self.input_doi.setText(metadata["DOI"])
        if metadata.get("abstractNote"):
            self.input_abstract.setPlainText(metadata["abstractNote"])

        creators = metadata.get("creators", [])
        if creators:
            strs = []
            for c in creators:
                if isinstance(c, dict):
                    if c.get("lastName") and c.get("firstName"):
                        strs.append(f"{c['lastName']}, {c['firstName']}")
                    elif c.get("name"):
                        strs.append(c["name"])
            if strs:
                self.input_authors.setText("; ".join(strs))

        self.status_feedback.setText("✓ Metadata extracted from first page.")

    def _generate_keywords_ai(self):
        if not self.ai_assistant:
            QMessageBox.warning(self, "Warning", "AI Assistant is not configured.")
            return

        text = self.full_text[:6000] if self.full_text else self.first_page_text
        if not text.strip():
            QMessageBox.warning(self, "Warning", "No document text available for keyword generation.")
            return

        self.ai_keywords_btn.setEnabled(False)
        self.ai_keywords_btn.setText("Generating...")
        self.status_feedback.setText("Generating academic keywords with AI...")

        self._ai_worker = AIWorker("keywords", self.ai_assistant, text)
        self._ai_worker.finished_signal.connect(self._on_keywords_generated)
        self._ai_worker.start()

    def _on_keywords_generated(self, success: bool, err_msg: str, keywords: Any):
        self.ai_keywords_btn.setEnabled(True)
        self.ai_keywords_btn.setText("✨ Generate AI Keywords")
        if not success or not isinstance(keywords, list):
            self.status_feedback.setText(f"AI keyword generation failed: {err_msg}")
            return

        added_count = 0
        for kw in keywords:
            if kw and kw not in self.tags:
                self.tags.append(kw)
                added_count += 1

        self._render_tags()
        self.status_feedback.setText(f"✓ Added {added_count} AI keywords.")

    def _get_selected_collection_keys(self) -> List[str]:
        keys = []
        def collect_checked(item):
            if item.checkState(0) == Qt.CheckState.Checked:
                key = item.data(0, Qt.ItemDataRole.UserRole)
                if key:
                    keys.append(key)
            for i in range(item.childCount()):
                collect_checked(item.child(i))

        for i in range(self.tree_collections.topLevelItemCount()):
            collect_checked(self.tree_collections.topLevelItem(i))
        return keys

    def _parse_authors(self, text: str) -> List[Dict[str, str]]:
        creators = []
        raw_list = [a.strip() for a in text.split(";") if a.strip()]
        for item in raw_list:
            if "," in item:
                parts = item.split(",", 1)
                creators.append({"creatorType": "author", "lastName": parts[0].strip(), "firstName": parts[1].strip()})
            else:
                creators.append({"creatorType": "author", "lastName": item, "firstName": ""})
        return creators

    def _save_to_zotero(self):
        title = self.input_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Warning", "Title cannot be empty.")
            return

        metadata = {
            "itemType": self.input_type.currentText(),
            "title": title,
            "publicationTitle": self.input_publication.text().strip(),
            "date": self.input_date.text().strip(),
            "DOI": self.input_doi.text().strip(),
            "abstractNote": self.input_abstract.toPlainText().strip(),
            "creators": self._parse_authors(self.input_authors.text()),
        }

        collection_keys = self._get_selected_collection_keys()
        new_note = self.input_new_note.toPlainText().strip()

        self.save_btn.setEnabled(False)
        self.save_btn.setText("Saving...")
        self.status_feedback.setText("Synchronizing with Zotero...")

        if self.zotero_item:
            # Update existing item
            item_key = self.zotero_item.get("data", {}).get("key")
            def do_update():
                res = self.zotero_manager.update_item(
                    item_key=item_key,
                    collection_keys=collection_keys,
                    tags=self.tags,
                    metadata=metadata
                )
                if new_note:
                    self.zotero_manager.add_note_to_item(item_key, new_note)
                return res

            self._worker = ZoteroOperationWorker(do_update)
            self._worker.finished_signal.connect(self._on_save_finished)
            self._worker.start()
        else:
            # Create new item with attachment
            def do_create():
                return self.zotero_manager.add_pdf_to_zotero(
                    pdf_path=self.pdf_path,
                    metadata=metadata,
                    collection_keys=collection_keys,
                    tags=self.tags,
                    initial_note=new_note if new_note else None
                )

            self._worker = ZoteroOperationWorker(do_create)
            self._worker.finished_signal.connect(self._on_save_finished)
            self._worker.start()

    def _on_save_finished(self, success: bool, err_msg: str, result: Any):
        self.save_btn.setEnabled(True)
        if success:
            self.status_feedback.setText("✓ Saved successfully to Zotero!")
            QMessageBox.information(self, "Success", "Successfully synced document to your Zotero library.")
            self.item_updated.emit(result if isinstance(result, dict) else {})
            self.accept()
        else:
            self.save_btn.setText("Save to Zotero")
            self.status_feedback.setText(f"Error: {err_msg}")
            QMessageBox.critical(self, "Error", f"Failed to save to Zotero:\n{err_msg}")

    def _open_zotero_web(self):
        import webbrowser
        item_key = self.web_link_btn.property("item_key")
        user_id = self.zotero_manager.config.zotero_user_id
        if user_id and item_key:
            url = f"https://www.zotero.org/users/{user_id}/items/{item_key}"
            webbrowser.open(url)
