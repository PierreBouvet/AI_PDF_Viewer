import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from ui.zotero_scan_dialog import ZoteroScanDialog, ZoteroSearchDialog
from backend.local_library_manager import LocalLibraryManager


def test_zotero_search_dialog(qapp):
    mock_items = [
        {
            "key": "KEY1",
            "title": "Attention Is All You Need",
            "first_author": "Vaswani",
            "authors": "Vaswani et al.",
            "year": "2017",
            "doi": "10.48550/arXiv.1706.03762"
        },
        {
            "key": "KEY2",
            "title": "Mastering the game of Go",
            "first_author": "Silver",
            "authors": "Silver et al.",
            "year": "2016",
            "doi": "10.1038/nature16961"
        }
    ]

    with patch("ui.zotero_scan_dialog.search_zotero_local", return_value=mock_items):
        dialog = ZoteroSearchDialog(query="Attention")
        assert dialog.table.rowCount() == 2

        # Select row 0
        dialog.table.selectRow(0)
        dialog._on_select()
        assert dialog.selected_item is not None
        assert dialog.selected_item["key"] == "KEY1"

        dialog.close()


def test_zotero_scan_dialog_rendering_and_apply(qapp, tmp_path):
    sources = tmp_path / "Sources"
    sources.mkdir()

    pdf1 = sources / "Vaswani et al. - 2017 - Attention Is All You Need.pdf"
    pdf1.write_text("%PDF-1.4 paper 1")

    pdf2 = sources / "unmatched_paper.pdf"
    pdf2.write_text("%PDF-1.4 paper 2")

    mock_scan_results = [
        {
            "pdf_filename": pdf1.name,
            "pdf_path": str(pdf1),
            "matched": True,
            "zotero_key": "KEY123",
            "zotero_authors": "Vaswani et al.",
            "zotero_year": "2017",
            "zotero_title": "Attention Is All You Need",
            "confidence": 0.95
        },
        {
            "pdf_filename": pdf2.name,
            "pdf_path": str(pdf2),
            "matched": False,
            "zotero_key": "",
            "zotero_authors": "",
            "zotero_year": "",
            "zotero_title": "",
            "confidence": 0.0
        }
    ]

    with patch("ui.zotero_scan_dialog.scan_sources_directory_against_zotero", return_value=mock_scan_results):
        dialog = ZoteroScanDialog(sources_dir=str(sources))
        # Wait for worker finish simulation
        dialog._on_scan_finished(True, "", mock_scan_results)

        assert dialog.table.rowCount() == 2
        assert "2 PDFs in Sources: 1 matched with Zotero, 1 unmatched" in dialog.header_label.text()

        # Row 0 is matched
        assert dialog.table.item(0, 0).text() == pdf1.name
        assert dialog.table.item(0, 1).text() == "Vaswani et al."
        assert dialog.table.item(0, 2).text() == "2017"

        # Row 1 is unmatched
        assert dialog.table.item(1, 0).text() == pdf2.name

        # Ensure apply catalogs matched file in .library.sqlite and moves unmatched file
        dialog.cb_move_unmatched.setChecked(True)
        with patch("PySide6.QtWidgets.QMessageBox.information") as mock_info:
            dialog._on_apply()
            mock_info.assert_called_once()

        # Check database
        mgr = LocalLibraryManager(str(sources))
        art = mgr.find_article_by_zotero_key("KEY123")
        assert art is not None
        assert art["title"] == "Attention Is All You Need"

        # Check Non-linked folder
        non_linked = sources / "Non-linked"
        assert non_linked.exists()
        assert (non_linked / pdf2.name).exists()
        assert not pdf2.exists()

        dialog.close()
