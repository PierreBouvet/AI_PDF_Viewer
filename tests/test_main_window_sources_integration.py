import pytest
import os
from unittest.mock import MagicMock, patch
from ui.main_window import MainWindow
from backend.local_library_manager import LocalLibraryManager


def test_main_window_zotero_btn_text_based_on_sources(qapp, isolated_test_settings, tmp_path):
    sources = tmp_path / "Sources"
    sources.mkdir()
    downloads = tmp_path / "Downloads"
    downloads.mkdir()

    isolated_test_settings.source_directory = str(sources)

    win = MagicMock(spec=MainWindow)
    win.config = isolated_test_settings
    win.zotero_btn = MagicMock()
    win.current_zotero_item = None

    # Case 1: Paper outside Sources -> Button is "Add article to Zotero"
    outside_doc = MagicMock()
    outside_doc.file_path = str(downloads / "paper.pdf")
    win.pdf_doc = outside_doc

    MainWindow._update_zotero_btn_text(win)
    win.zotero_btn.setText.assert_called_with("Add article to Zotero")

    # Case 2: Paper inside Sources but not linked -> Button is "+ Zotero"
    inside_doc = MagicMock()
    inside_doc.file_path = str(sources / "paper.pdf")
    win.pdf_doc = inside_doc

    MainWindow._update_zotero_btn_text(win)
    win.zotero_btn.setText.assert_called_with("+ Zotero")

    # Case 3: Paper inside Sources and linked -> Button is "Zotero ✓"
    win.current_zotero_item = {"key": "KEY123", "data": {"title": "Sample Paper"}}
    MainWindow._update_zotero_btn_text(win)
    win.zotero_btn.setText.assert_called_with("Zotero ✓")


def test_main_window_prompt_and_execute_move_to_sources(qapp, isolated_test_settings, tmp_path):
    sources = tmp_path / "Sources"
    sources.mkdir()
    downloads = tmp_path / "Downloads"
    downloads.mkdir()

    isolated_test_settings.source_directory = str(sources)

    raw_pdf = downloads / "raw_paper.pdf"
    raw_pdf.write_text("%PDF-1.4 raw paper content")

    win = MagicMock(spec=MainWindow)
    win.config = isolated_test_settings
    win.zotero_btn = MagicMock()
    win.current_zotero_item = None
    win.add_log = MagicMock()
    win.update_save_action_state = MagicMock()
    win.setWindowTitle = MagicMock()

    mock_doc = MagicMock()
    mock_doc.file_path = str(raw_pdf)
    mock_doc.doc.metadata = {"title": "Scalable Transformers"}
    win.pdf_doc = mock_doc

    zotero_item = {
        "key": "ZOT_KEY_777",
        "data": {
            "key": "ZOT_KEY_777",
            "title": "Scalable Transformers",
            "creators": [{"lastName": "Vaswani"}, {"lastName": "Jones"}],
            "date": "2023",
            "DOI": "10.1234/test"
        }
    }

    # Simulate user clicking "Move to Sources"
    with patch("PySide6.QtWidgets.QMessageBox.exec", return_value=None):
        with patch("PySide6.QtWidgets.QMessageBox.clickedButton") as mock_btn_call:
            # We will test _switch_open_document_to_sources directly
            mgr = LocalLibraryManager(str(sources))
            plan = mgr.prepare_move_plan(
                current_pdf_path=str(raw_pdf),
                title="Scalable Transformers",
                creators=[{"lastName": "Vaswani"}, {"lastName": "Jones"}],
                year="2023",
                doi="10.1234/test",
                zotero_key="ZOT_KEY_777"
            )

            assert plan["candidate_filename"] == "Vaswani et al. - 2023 - Scalable Transformers.pdf"

            final_dest = mgr.execute_move(
                source_path=str(raw_pdf),
                destination_path=plan["target_path"],
                title="Scalable Transformers",
                creators=[{"lastName": "Vaswani"}, {"lastName": "Jones"}],
                year="2023",
                doi="10.1234/test",
                zotero_key="ZOT_KEY_777",
                sha256_hash=plan["sha256"]
            )

            MainWindow._switch_open_document_to_sources(win, final_dest)

            # Verification
            assert os.path.exists(final_dest)
            assert not os.path.exists(str(raw_pdf))
            assert win.pdf_doc.file_path == final_dest
            win.setWindowTitle.assert_called_with("Vaswani et al. - 2023 - Scalable Transformers.pdf")
