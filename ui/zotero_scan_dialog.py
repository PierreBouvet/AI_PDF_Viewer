"""
zotero_scan_dialog.py
---------------------
Dialog to scan the user's Sources directory, match PDFs against local Zotero SQLite,
present the confirmation table, allow manual re-linking via 'Choose other',
and optionally relocate unlinked PDFs to a 'Non-linked' sub-directory.
"""

import os
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QMessageBox, QProgressBar,
    QLineEdit, QDialogButtonBox, QWidget
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from backend.local_library_manager import (
    scan_sources_directory_against_zotero,
    search_zotero_local,
    move_unmatched_files_to_non_linked,
    LocalLibraryManager
)


class ZoteroScanWorker(QThread):
    finished_signal = Signal(bool, str, list)  # success, error, results

    def __init__(self, sources_dir: str, zotero_db_path: Optional[str] = None):
        super().__init__()
        self.sources_dir = sources_dir
        self.zotero_db_path = zotero_db_path

    def run(self):
        try:
            results = scan_sources_directory_against_zotero(
                sources_dir=self.sources_dir,
                zotero_db_path=self.zotero_db_path
            )
            self.finished_signal.emit(True, "", results)
        except Exception as e:
            self.finished_signal.emit(False, str(e), [])


class ZoteroSearchDialog(QDialog):
    """Search dialog to manually find and reassign a Zotero entry to a paper."""

    def __init__(self, query: str = "", zotero_db_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.zotero_db_path = zotero_db_path
        self.selected_item = None
        self.marked_unlinked = False

        self.setWindowTitle("Search Zotero Library")
        self.resize(650, 420)
        self._init_ui(query)
        self._do_search(query)

    def _init_ui(self, initial_query: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Search bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Search Zotero:")
        search_label.setStyleSheet("font-weight: 600;")
        self.search_input = QLineEdit()
        self.search_input.setText(initial_query)
        self.search_input.setPlaceholderText("Search by title, author, year, or DOI...")
        self.search_input.textChanged.connect(self._do_search)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input, 1)
        layout.addLayout(search_layout)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Author", "Year", "Title", "DOI"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(self._on_select)
        layout.addWidget(self.table, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_unlink = QPushButton("Mark as Unlinked")
        self.btn_unlink.setStyleSheet("color: #d32f2f;")
        self.btn_unlink.clicked.connect(self._on_mark_unlinked)
        btn_layout.addWidget(self.btn_unlink)

        btn_layout.addStretch()

        self.btn_select = QPushButton("Select Entry")
        self.btn_select.setStyleSheet("background-color: #2196f3; color: white; font-weight: 600; padding: 6px 14px;")
        self.btn_select.clicked.connect(self._on_select)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_select)
        layout.addLayout(btn_layout)

    def _do_search(self, text: str):
        items = search_zotero_local(text, zotero_db_path=self.zotero_db_path, limit=35)
        self.table.setRowCount(len(items))
        for r, itm in enumerate(items):
            item_author = QTableWidgetItem(itm.get("authors") or itm.get("first_author", ""))
            item_year = QTableWidgetItem(itm.get("year", ""))
            item_title = QTableWidgetItem(itm.get("title", ""))
            item_doi = QTableWidgetItem(itm.get("doi", ""))

            item_author.setData(Qt.ItemDataRole.UserRole, itm)

            self.table.setItem(r, 0, item_author)
            self.table.setItem(r, 1, item_year)
            self.table.setItem(r, 2, item_title)
            self.table.setItem(r, 3, item_doi)

    def _on_select(self):
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            item_widget = self.table.item(curr_row, 0)
            if item_widget:
                self.selected_item = item_widget.data(Qt.ItemDataRole.UserRole)
                self.accept()

    def _on_mark_unlinked(self):
        self.marked_unlinked = True
        self.selected_item = None
        self.accept()


class ZoteroScanDialog(QDialog):
    """
    Scans the Sources directory and presents the 5-column confirmation table.
    """

    def __init__(self, sources_dir: str, zotero_db_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.sources_dir = os.path.abspath(os.path.expanduser(sources_dir))
        self.zotero_db_path = zotero_db_path
        self.results: List[Dict[str, Any]] = []
        self._worker = None

        self.setWindowTitle("Scan Sources Directory & Link to Zotero")
        self.resize(880, 560)
        self.setMinimumSize(750, 450)

        self._init_ui()
        self._start_scan()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header summary
        self.header_label = QLabel("Scanning Sources directory for PDFs...")
        self.header_label.setStyleSheet("font-size: 11pt; font-weight: 600;")
        layout.addWidget(self.header_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate while scanning
        layout.addWidget(self.progress_bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "PDF File",
            "Zotero Authors",
            "Year",
            "Title on Zotero",
            "Action"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 140)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # Bottom options
        bottom_options = QHBoxLayout()
        self.cb_move_unmatched = QCheckBox("Move unmatched papers to 'Non-linked' sub-directory")
        self.cb_move_unmatched.setChecked(True)
        self.cb_move_unmatched.setStyleSheet("font-weight: 500;")
        bottom_options.addWidget(self.cb_move_unmatched)
        bottom_options.addStretch()
        layout.addLayout(bottom_options)

        # Dialog buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply = QPushButton("Confirm & Apply Links")
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: white;
                font-weight: 600;
                padding: 6px 18px;
                border-radius: 4px;
            }
            QPushButton:disabled {
                background-color: #a5d6a7;
            }
        """)
        self.btn_apply.clicked.connect(self._on_apply)

        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_apply)
        layout.addLayout(btn_box)

    def _start_scan(self):
        self.progress_bar.setVisible(True)
        self.btn_apply.setEnabled(False)
        self._worker = ZoteroScanWorker(self.sources_dir, self.zotero_db_path)
        self._worker.finished_signal.connect(self._on_scan_finished)
        self._worker.start()

    def _on_scan_finished(self, success: bool, err_msg: str, results: List[Dict[str, Any]]):
        self.progress_bar.setVisible(False)
        if not success:
            QMessageBox.critical(self, "Scan Error", f"Failed to scan directory:\n{err_msg}")
            self.header_label.setText(f"Scan failed: {err_msg}")
            return

        self.results = results
        matched_count = sum(1 for r in results if r["matched"])
        unmatched_count = len(results) - matched_count

        self.header_label.setText(
            f"Found {len(results)} PDFs in Sources: {matched_count} matched with Zotero, {unmatched_count} unmatched."
        )
        self._render_table()
        self.btn_apply.setEnabled(len(results) > 0)

    def _render_table(self):
        self.table.setRowCount(len(self.results))
        for row_idx, r in enumerate(self.results):
            # Col 0: PDF File
            item_fn = QTableWidgetItem(r["pdf_filename"])
            item_fn.setToolTip(r["pdf_path"])

            # Col 1: Authors
            item_author = QTableWidgetItem(r["zotero_authors"])
            # Col 2: Year
            item_year = QTableWidgetItem(r["zotero_year"])
            # Col 3: Title
            item_title = QTableWidgetItem(r["zotero_title"])

            # Styling for matched vs unmatched
            if r["matched"]:
                bg = QColor("#f1f8e9")
                fg = QColor("#1b5e20")
            else:
                bg = QColor("#fff3e0")
                fg = QColor("#b71c1c")
                item_title.setText("(Unmatched - will be moved to Non-linked/)" if self.cb_move_unmatched.isChecked() else "(Unmatched)")

            for itm in (item_fn, item_author, item_year, item_title):
                itm.setBackground(bg)
                if not r["matched"] and itm != item_fn:
                    itm.setForeground(fg)

            self.table.setItem(row_idx, 0, item_fn)
            self.table.setItem(row_idx, 1, item_author)
            self.table.setItem(row_idx, 2, item_year)
            self.table.setItem(row_idx, 3, item_title)

            # Col 4: Action button
            btn_action = QPushButton("Choose other" if r["matched"] else "Find in Zotero")
            btn_action.setStyleSheet("padding: 4px 8px; font-size: 8.5pt;")
            btn_action.clicked.connect(lambda _, row=row_idx: self._open_choose_other(row))
            self.table.setCellWidget(row_idx, 4, btn_action)

    def _open_choose_other(self, row_idx: int):
        rec = self.results[row_idx]
        cand_query = rec["zotero_title"] or rec["pdf_filename"].replace(".pdf", "")

        dialog = ZoteroSearchDialog(query=cand_query, zotero_db_path=self.zotero_db_path, parent=self)
        if dialog.exec():
            if dialog.marked_unlinked:
                rec["matched"] = False
                rec["zotero_key"] = ""
                rec["zotero_authors"] = ""
                rec["zotero_year"] = ""
                rec["zotero_title"] = ""
            elif dialog.selected_item:
                sel = dialog.selected_item
                rec["matched"] = True
                rec["zotero_key"] = sel.get("key", "")
                rec["zotero_authors"] = sel.get("authors", "")
                rec["zotero_year"] = sel.get("year", "")
                rec["zotero_title"] = sel.get("title", "")

            # Re-render table row
            matched_count = sum(1 for r in self.results if r["matched"])
            unmatched_count = len(self.results) - matched_count
            self.header_label.setText(
                f"Found {len(self.results)} PDFs in Sources: {matched_count} matched with Zotero, {unmatched_count} unmatched."
            )
            self._render_table()

    def _on_apply(self):
        mgr = LocalLibraryManager(self.sources_dir)
        matched_records = [r for r in self.results if r["matched"]]
        unmatched_records = [r for r in self.results if not r["matched"]]

        # 1. Save matched records into .library.sqlite
        for r in matched_records:
            mgr.save_or_update_article(
                local_path=r["pdf_path"],
                title=r["zotero_title"],
                authors_formatted=r["zotero_authors"],
                year=r["zotero_year"],
                zotero_key=r["zotero_key"]
            )

        # 2. Optionally move unmatched files to Non-linked/
        moved_count = 0
        if self.cb_move_unmatched.isChecked() and unmatched_records:
            unmatched_paths = [r["pdf_path"] for r in unmatched_records]
            moved = move_unmatched_files_to_non_linked(unmatched_paths, self.sources_dir)
            moved_count = len(moved)

        QMessageBox.information(
            self,
            "Success",
            f"Successfully cataloged {len(matched_records)} papers in local library database."
            + (f"\nMoved {moved_count} unmatched papers to 'Sources/Non-linked/'." if moved_count > 0 else "")
        )
        self.accept()
