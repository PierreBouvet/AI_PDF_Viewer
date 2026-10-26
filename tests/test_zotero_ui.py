import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from ui.config_dialog import ConfigDialog
from ui.zotero_dialog import ZoteroDialog
from backend.config_manager import ConfigManager
from backend.zotero_manager import ZoteroManager


def test_config_dialog_zotero_tab(qapp, isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    config.zotero_library_type = "user"
    config.zotero_auto_check = True

    with patch("keyring.get_password", return_value="test_api_key_123"):
        dialog = ConfigDialog()

        # Switch to Zotero tab
        assert hasattr(dialog, "btn_zotero")
        dialog.btn_zotero.click()
        assert dialog.stack.currentWidget() == dialog.page_zotero

        # Verify fields populated
        assert dialog.zotero_uid_input.text() == "12345"
        assert dialog.zotero_key_input.text() == "test_api_key_123"
        assert dialog.zotero_lib_combo.currentText() == "User Library"
        assert dialog.zotero_auto_check.isChecked() is True

        dialog.close()


def test_zotero_dialog_init_not_in_library(qapp, isolated_test_settings, tmp_path):
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.get_collections_hierarchy.return_value = []
    mock_mgr.config = isolated_test_settings

    dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=None,
        zotero_manager=mock_mgr,
        first_page_text="Sample Article Title\nDOI: 10.1234/sample",
        full_text="Sample text content for keywords",
    )

    assert "Not yet in Zotero Library" in dialog.status_label.text()
    assert dialog.tabs.count() == 4
    assert dialog.save_btn.text() == "Add PDF to Zotero"

    dialog.close()


def test_zotero_dialog_init_in_library(qapp, isolated_test_settings, tmp_path):
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.get_collections_hierarchy.return_value = []
    mock_mgr.get_item_notes.return_value = []
    mock_mgr.config = isolated_test_settings

    existing_item = {
        "key": "ITEMKEY1",
        "data": {
            "key": "ITEMKEY1",
            "title": "Quantum Deep Learning",
            "publicationTitle": "Nature Machine Intelligence",
            "date": "2024",
            "DOI": "10.1038/s42256-024-00123-x",
            "abstractNote": "A comprehensive study on quantum deep learning.",
            "creators": [{"creatorType": "author", "firstName": "Alice", "lastName": "Smith"}],
            "tags": [{"tag": "Quantum"}, {"tag": "AI"}],
            "collections": [],
        }
    }

    dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=existing_item,
        zotero_manager=mock_mgr,
    )

    assert "In Zotero Library" in dialog.status_label.text()
    assert dialog.input_title.text() == "Quantum Deep Learning"
    assert dialog.input_publication.text() == "Nature Machine Intelligence"
    assert dialog.input_doi.text() == "10.1038/s42256-024-00123-x"
    assert "Smith, Alice" in dialog.input_authors.text()
    assert "Quantum" in dialog.tags
    assert "AI" in dialog.tags

    dialog.close()
