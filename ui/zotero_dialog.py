import os
import re
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox,
    QWidget, QFrame, QStackedWidget, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
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


class ZoteroIndexingWorker(QThread):
    """Background worker for indexing document so AI can analyze the full text."""
    finished_signal = Signal(bool, str)

    def __init__(self, assistant: AIAssistant, pdf_path: str):
        super().__init__()
        self.assistant = assistant
        self.pdf_path = pdf_path

    def run(self):
        try:
            self.assistant.index_pdf(self.pdf_path)
            self.finished_signal.emit(True, "")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class TwoStageKeywordsWorker(QThread):
    """Background worker for fetching library tags and generating AI keywords in two stages."""
    finished_signal = Signal(bool, str, object)

    def __init__(self, assistant: AIAssistant, zotero_manager: ZoteroManager, fallback_text: str = ""):
        super().__init__()
        self.assistant = assistant
        self.zotero_manager = zotero_manager
        self.fallback_text = fallback_text

    def run(self):
        try:
            library_tags = self.zotero_manager.get_all_library_tags()
            result = self.assistant.generate_keywords_two_stage(
                existing_tags=library_tags,
                max_keywords=8,
                fallback_text=self.fallback_text
            )
            self.finished_signal.emit(True, "", {"result": result, "library_tags": library_tags})
        except Exception as e:
            self.finished_signal.emit(False, str(e), None)


class LibraryTagsLoadWorker(QThread):
    """Background worker to fetch library tags without blocking dialog startup."""
    finished_signal = Signal(list)

    def __init__(self, zotero_manager: ZoteroManager):
        super().__init__()
        self.zotero_manager = zotero_manager

    def run(self):
        try:
            tags = self.zotero_manager.get_all_library_tags()
            self.finished_signal.emit(tags)
        except Exception as e:
            logger.warning(f"Failed to fetch library tags in worker: {e}")
            self.finished_signal.emit([])


class ScientificDBSearchWorker(QThread):
    """Background worker for querying reference scientific databases (Crossref & arXiv)."""
    finished_signal = Signal(bool, str, object)

    def __init__(self, doi: str = "", title: str = "", text_snippet: str = ""):
        super().__init__()
        self.doi = doi
        self.title = title
        self.text_snippet = text_snippet

    def run(self):
        try:
            from backend.zotero_manager import lookup_scientific_article
            result = lookup_scientific_article(doi=self.doi, title=self.title, text_snippet=self.text_snippet)
            if result:
                self.finished_signal.emit(True, "", result)
            else:
                self.finished_signal.emit(False, "No matching record found in Crossref or arXiv.", None)
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
        main_window=None,
    ):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.zotero_item = zotero_item
        self.zotero_manager = zotero_manager or ZoteroManager()
        self.ai_assistant = ai_assistant
        self.first_page_text = first_page_text
        self.full_text = full_text
        self.main_window = main_window or (parent if hasattr(parent, "on_indexing_finished") else None)

        self.tags = []
        self._keyword_data: Dict[str, Dict[str, Any]] = {}
        self._current_sorted_keyword_names: List[str] = []
        self._worker = None
        self._ai_worker = None
        self._db_worker = None
        self._index_worker = None
        self._two_stage_worker = None
        self._tags_worker = None

        self.setWindowTitle(f"Zotero - {os.path.basename(pdf_path)}")
        self.resize(780, 640)
        self.setMinimumSize(650, 520)

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

        self.ai_meta_btn = QPushButton("Extract with AI")
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
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.input_type = QComboBox()
        self.input_type.addItems(["journalArticle", "book", "conferencePaper", "report", "preprint", "thesis"])
        self.input_type.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Item Type:", self.input_type)

        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Paper or article title")
        self.input_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Title:", self.input_title)

        self.input_authors = QLineEdit()
        self.input_authors.setPlaceholderText("Authors (e.g. Bouvet, Pierre; Doe, Jane)")
        self.input_authors.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Authors:", self.input_authors)

        self.input_publication = QLineEdit()
        self.input_publication.setPlaceholderText("Journal, Conference, or Publisher")
        self.input_publication.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Publication:", self.input_publication)

        self.input_date = QLineEdit()
        self.input_date.setPlaceholderText("Year or Date (e.g. 2026)")
        self.input_date.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Date / Year:", self.input_date)

        doi_container = QWidget()
        doi_layout = QHBoxLayout(doi_container)
        doi_layout.setContentsMargins(0, 0, 0, 0)
        doi_layout.setSpacing(6)

        self.input_doi = QLineEdit()
        self.input_doi.setPlaceholderText("10.xxxx/xxxx (e.g. 10.1038/nature14539)")
        self.input_doi.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        doi_layout.addWidget(self.input_doi, 1)

        self.btn_doi_search = QPushButton("🔍")
        self.btn_doi_search.setToolTip("Quick search DOI on Crossref")
        self.btn_doi_search.setFixedWidth(32)
        self.btn_doi_search.setStyleSheet("""
            QPushButton {
                background-color: #f2f7ff;
                color: #007aff;
                border: 1px solid #99c2ff;
                border-radius: 4px;
                padding: 3px 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dceaff;
            }
        """)
        self.btn_doi_search.clicked.connect(self._search_scientific_database)
        doi_layout.addWidget(self.btn_doi_search)
        doi_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("DOI:", doi_container)

        self.input_abstract = QTextEdit()
        self.input_abstract.setPlaceholderText("Abstract or summary...")
        self.input_abstract.setMinimumHeight(85)
        self.input_abstract.setMaximumHeight(120)
        self.input_abstract.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        form.addRow("Abstract:", self.input_abstract)

        layout.addLayout(form)

        # Database search row at bottom of metadata pane
        db_box = QFrame()
        db_box.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
        """)
        db_layout = QHBoxLayout(db_box)
        db_layout.setContentsMargins(10, 8, 10, 8)
        db_layout.setSpacing(10)

        db_icon = QLabel("🌐")
        db_icon.setStyleSheet("font-size: 14pt;")
        db_layout.addWidget(db_icon)

        db_text_layout = QVBoxLayout()
        db_text_layout.setSpacing(2)
        db_title = QLabel("Reference Scientific Database")
        db_title.setStyleSheet("font-weight: 600; font-size: 9.5pt; color: #1c1c1e;")
        db_desc = QLabel("Query Crossref and arXiv by DOI or Title to auto-fill metadata")
        db_desc.setStyleSheet("color: #636366; font-size: 8.5pt;")
        db_text_layout.addWidget(db_title)
        db_text_layout.addWidget(db_desc)
        db_layout.addLayout(db_text_layout, 1)

        self.btn_db_search = QPushButton("🔍 Auto-Lookup Article")
        self.btn_db_search.setToolTip("Search Crossref and arXiv databases to automatically populate bibliographic fields")
        self.btn_db_search.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: 600;
                font-size: 9.5pt;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #b0b0b5;
            }
        """)
        self.btn_db_search.clicked.connect(self._search_scientific_database)
        db_layout.addWidget(self.btn_db_search)

        layout.addWidget(db_box)
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

        # Header Row
        header_row = QHBoxLayout()
        header_title = QLabel("<b>Document Tags & Keywords</b>")
        header_title.setStyleSheet("font-size: 11pt; color: #1c1c1e;")
        header_row.addWidget(header_title)
        header_row.addStretch()

        self.ai_keywords_btn = QPushButton("✨ Generate AI Keywords")
        self.ai_keywords_btn.setToolTip("Prompt AI to extract paper keywords and cross-reference with existing library tags")
        self.ai_keywords_btn.setStyleSheet("""
            QPushButton {
                background-color: #007aff;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #b0b0b5;
            }
        """)
        self.ai_keywords_btn.clicked.connect(self._on_ai_keywords_clicked)
        header_row.addWidget(self.ai_keywords_btn)
        layout.addLayout(header_row)

        # --- Indexing Offer Frame (shown if document is NOT indexed) ---
        self.indexing_offer_frame = QFrame()
        self.indexing_offer_frame.setObjectName("indexingOfferFrame")
        self.indexing_offer_frame.setStyleSheet("""
            #indexingOfferFrame {
                background-color: #fff9e6;
                border: 1px solid #ffe082;
                border-radius: 8px;
            }
        """)
        offer_layout = QHBoxLayout(self.indexing_offer_frame)
        offer_layout.setContentsMargins(12, 8, 12, 8)
        offer_layout.setSpacing(10)

        offer_icon = QLabel("⚡")
        offer_icon.setStyleSheet("font-size: 16pt;")
        offer_layout.addWidget(offer_icon)

        offer_text_layout = QVBoxLayout()
        offer_text_layout.setSpacing(2)
        offer_title = QLabel("Document Not Yet Indexed")
        offer_title.setStyleSheet("font-weight: 600; font-size: 9.5pt; color: #b78103;")
        offer_desc = QLabel("Index this document first to enable the AI to read the full text and recommend coherent keywords.")
        offer_desc.setStyleSheet("color: #6d4c41; font-size: 8.5pt;")
        offer_text_layout.addWidget(offer_title)
        offer_text_layout.addWidget(offer_desc)
        offer_layout.addLayout(offer_text_layout, 1)

        self.btn_index_doc = QPushButton("Index Document")
        self.btn_index_doc.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
            QPushButton:disabled {
                background-color: #ffd54f;
            }
        """)
        self.btn_index_doc.clicked.connect(lambda: self._start_indexing_for_keywords(auto_generate_after=True))
        offer_layout.addWidget(self.btn_index_doc)

        layout.addWidget(self.indexing_offer_frame)

        # --- Indexing Status Frame (shown if document IS indexed) ---
        self.indexing_status_frame = QFrame()
        self.indexing_status_frame.setObjectName("indexingStatusFrame")
        self.indexing_status_frame.setStyleSheet("""
            #indexingStatusFrame {
                background-color: #e8f5e9;
                border: 1px solid #81c784;
                border-radius: 6px;
            }
        """)
        status_layout = QHBoxLayout(self.indexing_status_frame)
        status_layout.setContentsMargins(10, 6, 10, 6)
        status_layout.setSpacing(8)

        status_icon = QLabel("✓")
        status_icon.setStyleSheet("font-weight: bold; color: #2e7d32; font-size: 11pt;")
        status_layout.addWidget(status_icon)

        status_text = QLabel("Document is indexed and ready for AI keyword analysis.")
        status_text.setStyleSheet("color: #1b5e20; font-size: 9pt; font-weight: 500;")
        status_layout.addWidget(status_text, 1)

        layout.addWidget(self.indexing_status_frame)

        # Filter & manual add row
        filter_row = QHBoxLayout()
        self.input_filter_keywords = QLineEdit()
        self.input_filter_keywords.setPlaceholderText("🔍 Filter library keywords...")
        self.input_filter_keywords.textChanged.connect(self._filter_keyword_table)
        filter_row.addWidget(self.input_filter_keywords, 1)

        self.input_new_custom_tag = QLineEdit()
        self.input_new_custom_tag.setPlaceholderText("Add custom keyword...")
        self.input_new_custom_tag.returnPressed.connect(self._add_custom_keyword)
        filter_row.addWidget(self.input_new_custom_tag, 1)

        self.btn_add_custom_tag = QPushButton("+ Add")
        self.btn_add_custom_tag.setStyleSheet("padding: 5px 12px; font-weight: 500;")
        self.btn_add_custom_tag.clicked.connect(self._add_custom_keyword)
        filter_row.addWidget(self.btn_add_custom_tag)
        layout.addLayout(filter_row)

        # Compatibility aliases
        self.input_new_tag = self.input_new_custom_tag
        self.btn_add_tag = self.btn_add_custom_tag

        # Helper & counter row
        info_row = QHBoxLayout()
        self.lbl_keywords_summary = QLabel("All library keywords listed below. Click Add/Delete to select.")
        self.lbl_keywords_summary.setStyleSheet("color: #636366; font-size: 8.5pt;")
        info_row.addWidget(self.lbl_keywords_summary)
        info_row.addStretch()

        self.lbl_selected_counter = QLabel("Selected: 0")
        self.lbl_selected_counter.setStyleSheet("font-weight: 600; font-size: 9pt; color: #007aff;")
        info_row.addWidget(self.lbl_selected_counter)
        layout.addLayout(info_row)

        # 2-Column Scrollable Table
        self.table_keywords = QTableWidget(0, 2)
        self.table_keywords.setHorizontalHeaderLabels(["Keyword / Tag", "Action"])
        self.table_keywords.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_keywords.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_keywords.setColumnWidth(1, 95)
        self.table_keywords.verticalHeader().setVisible(False)
        self.table_keywords.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table_keywords.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table_keywords.cellClicked.connect(self._on_table_cell_clicked)
        self.table_keywords.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #d1d1d6;
                border-radius: 6px;
                gridline-color: #f0f0f2;
            }
            QHeaderView::section {
                background-color: #f7f7f8;
                color: #3a3a3c;
                font-weight: 600;
                font-size: 9pt;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #d1d1d6;
            }
        """)
        layout.addWidget(self.table_keywords, 1)

        self._update_indexing_ui_state()
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
            data = self.zotero_item.get("data", self.zotero_item)
            item_key = self.zotero_item.get("key") or data.get("key", "")
            title = data.get("title") or self.zotero_item.get("title", "Found in Library")
            self._update_status_banner(
                is_in_library=True,
                title=title,
                item_key=item_key
            )
            item_type = data.get("itemType", "")
            if item_type:
                idx = self.input_type.findText(item_type)
                if idx >= 0:
                    self.input_type.setCurrentIndex(idx)

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
            self.tags = [t["tag"] for t in data.get("tags", []) if isinstance(t, dict) and "tag" in t]
            for t in self.tags:
                self._keyword_data[t] = {"selected": True, "is_ai": False}

            # Existing notes
            if item_key:
                self._load_item_notes(item_key)

            self.save_btn.setText("Save Changes to Zotero")
        else:
            self._update_status_banner(is_in_library=False)
            self.input_title.setText(os.path.basename(self.pdf_path).replace(".pdf", ""))
            self.save_btn.setText("Add PDF to Zotero")

        # Load Collections hierarchy
        self._load_collections()

        # Load all library tags from Zotero and render keywords table
        self._load_library_tags()
        self._render_keywords_table()

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

    def _is_document_indexed(self) -> bool:
        """Returns True if the document is already indexed in the AI assistant."""
        if not self.ai_assistant:
            return False
        return bool(getattr(self.ai_assistant, "is_indexed", False))

    def _update_indexing_ui_state(self):
        """Shows/hides indexing offer banner vs status badge depending on assistant index state."""
        is_indexed = self._is_document_indexed()
        if hasattr(self, "indexing_offer_frame"):
            self.indexing_offer_frame.setVisible(not is_indexed)
        if hasattr(self, "indexing_status_frame"):
            self.indexing_status_frame.setVisible(is_indexed)
        if hasattr(self, "ai_keywords_btn"):
            if is_indexed:
                self.ai_keywords_btn.setText("✨ Generate AI Keywords")
                self.ai_keywords_btn.setToolTip("Prompt AI to extract paper keywords and cross-reference with existing library tags")
            else:
                self.ai_keywords_btn.setText("⚡ Index & Generate Keywords")
                self.ai_keywords_btn.setToolTip("Document not indexed. Click to index first, then generate keywords.")

    def _on_ai_keywords_clicked(self):
        """Handler when clicking the primary AI keywords button."""
        if not self.ai_assistant:
            QMessageBox.warning(self, "Warning", "AI Assistant is not configured.")
            return

        if not self._is_document_indexed():
            reply = QMessageBox.question(
                self,
                "Document Not Indexed",
                "The document has not been indexed yet.\n\n"
                "Indexing is required so the AI can analyze the entire paper and recommend coherent keywords.\n\n"
                "Would you like to index the document now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._start_indexing_for_keywords(auto_generate_after=True)
            return

        self._start_two_stage_keywords_generation()

    def _start_indexing_for_keywords(self, auto_generate_after: bool = True):
        """Runs document indexing in background and synchronizes with the main window."""
        if not self.ai_assistant:
            QMessageBox.warning(self, "Warning", "AI Assistant is not configured.")
            return

        if not os.path.exists(self.pdf_path):
            QMessageBox.warning(self, "Warning", f"PDF file not found: {self.pdf_path}")
            return

        self.btn_index_doc.setEnabled(False)
        self.btn_index_doc.setText("Indexing...")
        self.ai_keywords_btn.setEnabled(False)
        self.status_feedback.setText("Indexing document for AI analysis...")

        self._index_worker = ZoteroIndexingWorker(self.ai_assistant, self.pdf_path)
        self._index_worker.finished_signal.connect(
            lambda success, err: self._on_indexing_for_keywords_finished(success, err, auto_generate_after)
        )
        self._index_worker.start()

    def _on_indexing_for_keywords_finished(self, success: bool, err_msg: str, auto_generate_after: bool):
        self.btn_index_doc.setEnabled(True)
        self.btn_index_doc.setText("Index Document")
        self.ai_keywords_btn.setEnabled(True)

        if not success:
            self.status_feedback.setText(f"Indexing failed: {err_msg}")
            QMessageBox.critical(self, "Indexing Failed", f"Could not index document:\n{err_msg}")
            return

        # 1. Update dialog UI state to show indexed
        self._update_indexing_ui_state()

        # 2. Synchronize with the general window (MainWindow)
        if self.main_window and hasattr(self.main_window, "on_indexing_finished"):
            try:
                self.main_window.on_indexing_finished()
            except Exception as e:
                logger.error(f"Failed to synchronize indexing with main window: {e}")

        self.status_feedback.setText("✓ Document indexed successfully.")

        # 3. If auto-generate requested, proceed directly with two-stage keyword generation
        if auto_generate_after:
            self._start_two_stage_keywords_generation()

    def _start_two_stage_keywords_generation(self):
        """Initiates two-stage AI keyword generation: blind prompt -> existing tags prompt -> merge."""
        self.ai_keywords_btn.setEnabled(False)
        self.ai_keywords_btn.setText("Generating...")
        self.status_feedback.setText("Generating AI keywords (Stage 1: blind analysis, Stage 2: library matching)...")

        fallback_text = self.full_text[:3000] if self.full_text else self.first_page_text
        self._two_stage_worker = TwoStageKeywordsWorker(self.ai_assistant, self.zotero_manager, fallback_text=fallback_text)
        self._two_stage_worker.finished_signal.connect(self._on_two_stage_keywords_finished)
        self._two_stage_worker.start()

    def _on_two_stage_keywords_finished(self, success: bool, err_msg: str, data: Any):
        self.ai_keywords_btn.setEnabled(True)
        self.ai_keywords_btn.setText("✨ Generate AI Keywords")

        if not success or not isinstance(data, dict):
            self.status_feedback.setText(f"AI keyword generation failed: {err_msg}")
            QMessageBox.warning(self, "Keyword Generation Failed", f"AI could not generate keywords:\n{err_msg}")
            return

        result = data.get("result", {})
        merged = result.get("merged_ai_keywords", [])
        matched = result.get("matched_existing_keywords", [])
        blind = result.get("blind_keywords", [])
        library_tags = data.get("library_tags", [])

        # Ensure all library tags exist in _keyword_data
        for tag in library_tags:
            tag_clean = str(tag).strip()
            if tag_clean and tag_clean not in self._keyword_data:
                self._keyword_data[tag_clean] = {"selected": False, "is_ai": False}

        # Apply AI recommendations: selected by default and marked as AI
        for tag in merged:
            tag_clean = str(tag).strip()
            if not tag_clean:
                continue
            if tag_clean not in self._keyword_data:
                self._keyword_data[tag_clean] = {"selected": True, "is_ai": True}
            else:
                self._keyword_data[tag_clean]["selected"] = True
                self._keyword_data[tag_clean]["is_ai"] = True

        self._render_keywords_table()
        self.status_feedback.setText(
            f"✓ AI recommended {len(merged)} keywords ({len(matched)} from library, {len(blind)} new) - selected by default."
        )

    def _load_library_tags(self):
        """Loads all existing tags across the user's Zotero library."""
        try:
            tags = self.zotero_manager.get_all_library_tags()
            self._on_library_tags_loaded(tags)
        except Exception as e:
            logger.warning(f"Failed to fetch library tags: {e}")

    def _on_library_tags_loaded(self, tags: List[str]):
        for t in tags:
            tag_clean = str(t).strip()
            if tag_clean and tag_clean not in self._keyword_data:
                self._keyword_data[tag_clean] = {"selected": False, "is_ai": False}
        self._render_keywords_table()

    def _render_keywords_table(self):
        """Renders the 2-column scrollable table of all keywords."""
        self.tags = [name for name, info in self._keyword_data.items() if info.get("selected")]
        if hasattr(self, "lbl_selected_counter"):
            self.lbl_selected_counter.setText(f"Selected: {len(self.tags)}")

        # Sorting: AI recommended & selected first, then other selected, then AI unselected, then rest alphabetically
        def sort_key(name):
            info = self._keyword_data[name]
            sel = info.get("selected", False)
            is_ai = info.get("is_ai", False)
            if is_ai and sel:
                return (0, name.lower())
            elif sel:
                return (1, name.lower())
            elif is_ai:
                return (2, name.lower())
            else:
                return (3, name.lower())

        sorted_names = sorted(self._keyword_data.keys(), key=sort_key)
        self._current_sorted_keyword_names = sorted_names

        self.table_keywords.setRowCount(len(sorted_names))
        for row_idx, name in enumerate(sorted_names):
            info = self._keyword_data[name]
            is_sel = info.get("selected", False)
            is_ai = info.get("is_ai", False)

            # Column 0: Keyword Name
            display_text = f"{name}   ✨ AI" if is_ai else name
            item_name = QTableWidgetItem(display_text)
            item_name.setFlags(Qt.ItemFlag.ItemIsEnabled)

            font = QFont()
            if is_sel:
                font.setItalic(False)
                font.setBold(True if is_ai else False)
                item_name.setFont(font)
                if is_ai:
                    item_name.setForeground(QColor("#1b5e20"))
                    item_name.setBackground(QColor("#e8f5e9"))
                else:
                    item_name.setForeground(QColor("#1c1c1e"))
                    item_name.setBackground(QColor("#f4f9ff"))
            else:
                font.setItalic(True)
                font.setBold(False)
                item_name.setFont(font)
                item_name.setForeground(QColor("#8e8e93"))
                item_name.setBackground(QColor("#ffffff"))

            self.table_keywords.setItem(row_idx, 0, item_name)

            # Column 1: Add / Delete Action Button
            btn = QPushButton()
            if is_sel:
                btn.setText("Delete")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #ffebee;
                        color: #c62828;
                        border: 1px solid #ffcdd2;
                        border-radius: 4px;
                        padding: 3px 6px;
                        font-weight: 600;
                        font-size: 8.5pt;
                    }
                    QPushButton:hover {
                        background-color: #ffcdd2;
                        color: #b71c1c;
                    }
                """)
            else:
                btn.setText("+ Add")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f2f7ff;
                        color: #007aff;
                        border: 1px solid #b8daff;
                        border-radius: 4px;
                        padding: 3px 6px;
                        font-weight: 600;
                        font-size: 8.5pt;
                    }
                    QPushButton:hover {
                        background-color: #dceaff;
                    }
                """)

            btn.clicked.connect(lambda _, n=name: self._toggle_keyword_selection(n))
            self.table_keywords.setCellWidget(row_idx, 1, btn)
            self.table_keywords.setRowHeight(row_idx, 30)

        current_filter = self.input_filter_keywords.text().strip()
        if current_filter:
            self._filter_keyword_table(current_filter)

    def _toggle_keyword_selection(self, name: str):
        """Toggles the selection state of a keyword."""
        if name in self._keyword_data:
            self._keyword_data[name]["selected"] = not self._keyword_data[name]["selected"]
            self._render_keywords_table()

    def _on_table_cell_clicked(self, row: int, col: int):
        if col == 0 and 0 <= row < len(self._current_sorted_keyword_names):
            self._toggle_keyword_selection(self._current_sorted_keyword_names[row])

    def _filter_keyword_table(self, query: str):
        """Filters rows in table based on search query."""
        q = query.strip().lower()
        for row in range(self.table_keywords.rowCount()):
            item = self.table_keywords.item(row, 0)
            if not item:
                continue
            text = item.text().lower()
            self.table_keywords.setRowHidden(row, bool(q and q not in text))

    def _add_custom_keyword(self):
        """Adds a new user-entered keyword to the table as selected."""
        text = self.input_new_custom_tag.text().strip()
        if text:
            if text not in self._keyword_data:
                self._keyword_data[text] = {"selected": True, "is_ai": False}
            else:
                self._keyword_data[text]["selected"] = True
            self.input_new_custom_tag.clear()
            self._render_keywords_table()

    def _render_tags(self):
        """Backwards compatibility alias."""
        self._render_keywords_table()

    def _add_tag_from_input(self):
        """Backwards compatibility alias."""
        self._add_custom_keyword()

    def _remove_tag(self, tag: str):
        """Backwards compatibility alias."""
        if tag in self._keyword_data:
            self._keyword_data[tag]["selected"] = False
            self._render_keywords_table()

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
        self.ai_meta_btn.setText("Extract with AI")
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

    def _search_scientific_database(self):
        """Searches Crossref and arXiv reference databases using DOI or title."""
        doi = self.input_doi.text().strip()
        title = self.input_title.text().strip()
        snippet = self.first_page_text or self.full_text[:3000]

        if not doi and not title and not snippet.strip():
            QMessageBox.information(
                self,
                "Search Information",
                "Please enter a DOI or Title in the fields above, or ensure the opened PDF has readable text."
            )
            return

        self.btn_db_search.setEnabled(False)
        self.btn_db_search.setText("🔍 Searching...")
        if hasattr(self, "btn_doi_search"):
            self.btn_doi_search.setEnabled(False)
        self.status_feedback.setText("Searching reference scientific article databases (Crossref & arXiv)...")

        self._db_worker = ScientificDBSearchWorker(doi=doi, title=title, text_snippet=snippet)
        self._db_worker.finished_signal.connect(self._on_scientific_database_found)
        self._db_worker.start()

    def _on_scientific_database_found(self, success: bool, err_msg: str, metadata: Any):
        self.btn_db_search.setEnabled(True)
        self.btn_db_search.setText("🔍 Auto-Lookup Article")
        if hasattr(self, "btn_doi_search"):
            self.btn_doi_search.setEnabled(True)

        if not success or not isinstance(metadata, dict):
            self.status_feedback.setText(f"Database search: {err_msg}")
            QMessageBox.information(
                self,
                "Article Not Found",
                f"Could not find a canonical record in Crossref or arXiv.\n\n"
                f"Details: {err_msg}\n\n"
                "Tip: You can use the 'Extract with AI' button at the top to extract metadata directly from the document text."
            )
            return

        source = metadata.get("source", "Scientific Database")
        title = metadata.get("title", "")
        if title:
            self.input_title.setText(title)
        if metadata.get("publicationTitle"):
            self.input_publication.setText(metadata["publicationTitle"])
        if metadata.get("date"):
            self.input_date.setText(str(metadata["date"]))
        if metadata.get("DOI"):
            self.input_doi.setText(metadata["DOI"])
        if metadata.get("abstractNote"):
            self.input_abstract.setPlainText(metadata["abstractNote"])
        if metadata.get("itemType"):
            idx = self.input_type.findText(metadata["itemType"])
            if idx >= 0:
                self.input_type.setCurrentIndex(idx)

        creators = metadata.get("creators", [])
        if creators:
            strs = []
            for c in creators:
                if isinstance(c, dict):
                    if c.get("lastName") and c.get("firstName"):
                        strs.append(f"{c['lastName']}, {c['firstName']}")
                    elif c.get("name"):
                        strs.append(c["name"])
                    elif c.get("lastName"):
                        strs.append(c["lastName"])
            if strs:
                self.input_authors.setText("; ".join(strs))

        display_title = f"{title[:40]}..." if len(title) > 40 else title
        self.status_feedback.setText(f"✓ Found via {source}: {display_title}")

    def _generate_keywords_ai(self):
        """Triggers the keyword workflow (indexing check followed by two-stage generation)."""
        self._on_ai_keywords_clicked()

    def _on_keywords_generated(self, success: bool, err_msg: str, keywords: Any):
        """Handler for single-stage keywords worker (if called directly)."""
        self.ai_keywords_btn.setEnabled(True)
        self.ai_keywords_btn.setText("✨ Generate AI Keywords")
        if not success or not isinstance(keywords, list):
            self.status_feedback.setText(f"AI keyword generation failed: {err_msg}")
            return

        added_count = 0
        for kw in keywords:
            cleaned = str(kw).strip()
            if cleaned:
                if cleaned not in self._keyword_data:
                    self._keyword_data[cleaned] = {"selected": True, "is_ai": True}
                    added_count += 1
                else:
                    self._keyword_data[cleaned]["selected"] = True
                    self._keyword_data[cleaned]["is_ai"] = True

        self._render_keywords_table()
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

        # Synchronize selected tags
        self.tags = [name for name, info in self._keyword_data.items() if info.get("selected")]

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
            item_key = self.zotero_item.get("key") or self.zotero_item.get("data", {}).get("key")
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
            item_to_emit = None
            if isinstance(result, dict) and (result.get("key") or result.get("data", {}).get("key")):
                item_to_emit = result
                self.zotero_item = result
            elif self.zotero_item:
                item_to_emit = self.zotero_item

            QMessageBox.information(self, "Success", "Successfully synced document to your Zotero library.")
            if item_to_emit:
                self.item_updated.emit(item_to_emit)
            self.accept()
        else:
            self.save_btn.setText("Save Changes to Zotero" if self.zotero_item else "Add PDF to Zotero")
            self.status_feedback.setText(f"Error: {err_msg}")
            QMessageBox.critical(self, "Error", f"Failed to save to Zotero:\n{err_msg}")

    def _open_zotero_web(self):
        import webbrowser
        item_key = self.web_link_btn.property("item_key")
        user_id = self.zotero_manager.config.zotero_user_id
        if user_id and item_key:
            url = f"https://www.zotero.org/users/{user_id}/items/{item_key}"
            webbrowser.open(url)
