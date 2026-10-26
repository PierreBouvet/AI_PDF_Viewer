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

    from PySide6.QtWidgets import QSizePolicy
    assert dialog.input_title.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert dialog.input_authors.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert dialog.input_publication.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert dialog.input_type.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding

    dialog.close()


def test_zotero_dialog_scientific_db_search(qapp, isolated_test_settings, tmp_path):
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.get_collections_hierarchy.return_value = []
    mock_mgr.config = isolated_test_settings

    dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=None,
        zotero_manager=mock_mgr,
        first_page_text="Sample text",
    )

    assert hasattr(dialog, "btn_db_search")
    assert hasattr(dialog, "btn_doi_search")

    mock_found = {
        "itemType": "journalArticle",
        "title": "Mastering the game of Go",
        "publicationTitle": "Nature",
        "date": "2016",
        "DOI": "10.1038/nature16961",
        "abstractNote": "The game of Go is challenging.",
        "creators": [{"creatorType": "author", "firstName": "David", "lastName": "Silver"}],
        "source": "Crossref"
    }

    # Simulate worker completion
    dialog._on_scientific_database_found(True, "", mock_found)

    assert dialog.input_title.text() == "Mastering the game of Go"
    assert dialog.input_publication.text() == "Nature"
    assert dialog.input_date.text() == "2016"
    assert dialog.input_doi.text() == "10.1038/nature16961"
    assert "Silver, David" in dialog.input_authors.text()
    assert "The game of Go" in dialog.input_abstract.toPlainText()
    assert "Found via Crossref" in dialog.status_feedback.text()

    dialog.close()


def test_zotero_dialog_indexing_state_and_synchronization(qapp, isolated_test_settings, tmp_path):
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.get_collections_hierarchy.return_value = []
    mock_mgr.get_all_library_tags.return_value = ["Genetics", "Robotics", "Transformers"]
    mock_mgr.config = isolated_test_settings

    mock_ai = MagicMock()
    mock_ai.is_indexed = False

    mock_main_window = MagicMock()

    # Case 1: Document NOT indexed -> Offer frame is visible, status badge hidden
    dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=None,
        zotero_manager=mock_mgr,
        ai_assistant=mock_ai,
        main_window=mock_main_window,
    )

    assert not dialog.indexing_offer_frame.isHidden()
    assert dialog.indexing_status_frame.isHidden()
    assert "Index" in dialog.ai_keywords_btn.text()

    # Simulate indexing finished inside dialog
    mock_ai.is_indexed = True
    dialog._on_indexing_for_keywords_finished(True, "", auto_generate_after=False)

    # General window (main_window) is notified
    mock_main_window.on_indexing_finished.assert_called_once()
    # Offer frame is now hidden, status frame is visible
    assert dialog.indexing_offer_frame.isHidden()
    assert not dialog.indexing_status_frame.isHidden()
    assert "Generate AI Keywords" in dialog.ai_keywords_btn.text()

    dialog.close()


def test_zotero_dialog_already_indexed_no_offer(qapp, isolated_test_settings, tmp_path):
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.get_collections_hierarchy.return_value = []
    mock_mgr.get_all_library_tags.return_value = ["Genetics"]
    mock_mgr.config = isolated_test_settings

    mock_ai = MagicMock()
    mock_ai.is_indexed = True  # Already indexed in MainWindow!

    dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=None,
        zotero_manager=mock_mgr,
        ai_assistant=mock_ai,
    )

    # When already indexed in general window, do NOT offer to index again
    assert dialog.indexing_offer_frame.isHidden()
    assert not dialog.indexing_status_frame.isHidden()
    assert "Generate AI Keywords" in dialog.ai_keywords_btn.text()

    dialog.close()


def test_zotero_dialog_keywords_table_rendering_and_styling(qapp, isolated_test_settings, tmp_path):
    from PySide6.QtGui import QColor

    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.get_collections_hierarchy.return_value = []
    library_tags = ["Transformers", "Genetics", "Robotics"]
    mock_mgr.get_all_library_tags.return_value = library_tags
    mock_mgr.config = isolated_test_settings

    mock_ai = MagicMock()
    mock_ai.is_indexed = True

    dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=None,
        zotero_manager=mock_mgr,
        ai_assistant=mock_ai,
    )

    # Initially all library tags loaded, 2 columns in table
    assert dialog.table_keywords.columnCount() == 2
    assert dialog.table_keywords.rowCount() == 3

    # Simulate AI two-stage keyword generation result:
    # "Deep Learning" (blind) and "Transformers" (matched from library)
    mock_data = {
        "result": {
            "blind_keywords": ["Deep Learning"],
            "matched_existing_keywords": ["Transformers"],
            "merged_ai_keywords": ["Transformers", "Deep Learning"],
        },
        "library_tags": library_tags
    }
    dialog._on_two_stage_keywords_finished(True, "", mock_data)

    # Table now has 4 rows: Transformers, Deep Learning, Genetics, Robotics
    assert dialog.table_keywords.rowCount() == 4

    # AI keywords are selected as "Add" by default
    assert "Transformers" in dialog.tags
    assert "Deep Learning" in dialog.tags
    assert "Genetics" not in dialog.tags
    assert "Robotics" not in dialog.tags

    # Find row indices
    row_tf = -1
    row_dl = -1
    row_ge = -1
    for r in range(dialog.table_keywords.rowCount()):
        txt = dialog.table_keywords.item(r, 0).text()
        if "Transformers" in txt:
            row_tf = r
        elif "Deep Learning" in txt:
            row_dl = r
        elif "Genetics" in txt:
            row_ge = r

    assert row_tf != -1
    assert row_dl != -1
    assert row_ge != -1

    # Check AI recommended row styling:
    item_tf = dialog.table_keywords.item(row_tf, 0)
    btn_tf = dialog.table_keywords.cellWidget(row_tf, 1)
    # Highlighted in green
    assert item_tf.background().color() == QColor("#e8f5e9")
    assert item_tf.foreground().color() == QColor("#1b5e20")
    # Selected: clearly visible (not slanted/italic)
    assert item_tf.font().italic() is False
    # Action button is "Delete"
    assert btn_tf.text() == "Delete"

    # Check unselected row styling (Genetics):
    item_ge = dialog.table_keywords.item(row_ge, 0)
    btn_ge = dialog.table_keywords.cellWidget(row_ge, 1)
    # Unselected: slanted (italic) and less visible (grey)
    assert item_ge.font().italic() is True
    assert item_ge.foreground().color() == QColor("#8e8e93")
    # Action button is "+ Add"
    assert btn_ge.text() == "+ Add"

    # Now click "+ Add" for Genetics to toggle it
    btn_ge.click()
    assert "Genetics" in dialog.tags

    # Re-inspect Genetics after clicking Add
    for r in range(dialog.table_keywords.rowCount()):
        txt = dialog.table_keywords.item(r, 0).text()
        if "Genetics" in txt:
            item_ge_updated = dialog.table_keywords.item(r, 0)
            btn_ge_updated = dialog.table_keywords.cellWidget(r, 1)
            # Now clearly visible: upright (italic is False)
            assert item_ge_updated.font().italic() is False
            assert btn_ge_updated.text() == "Delete"

    # Now click Delete for Transformers to unselect it
    for r in range(dialog.table_keywords.rowCount()):
        txt = dialog.table_keywords.item(r, 0).text()
        if "Transformers" in txt:
            btn_tf_updated = dialog.table_keywords.cellWidget(r, 1)
            btn_tf_updated.click()
            break

    assert "Transformers" not in dialog.tags

    dialog.close()


def test_ai_assistant_two_stage_prompts_execution(isolated_test_settings):
    from backend.ai_assistant import AIAssistant
    from backend.config_manager import ConfigManager

    isolated_test_settings.ai_provider = "cloud"
    assistant = AIAssistant()
    assistant.uploaded_file = MagicMock()  # Mark as indexed

    # Mock ask_direct to track prompt sequence
    prompts_received = []
    def fake_ask_direct(prompt):
        prompts_received.append(prompt)
        if len(prompts_received) == 1:
            # Blind prompt response
            return "Graph Neural Networks, Molecular Docking, Transformers"
        elif len(prompts_received) == 2:
            # Library selection response
            return "Molecular Docking"
        return "None"

    assistant.ask_direct = fake_ask_direct

    library_tags = ["Molecular Docking", "Bioinformatics", "Genetics"]
    result = assistant.generate_keywords_two_stage(existing_tags=library_tags)

    # 1. Sent 2 prompts one after the other
    assert len(prompts_received) == 2
    # Prompt 1 is blind (indexed document analysis)
    assert "identify up to" in prompts_received[0]
    # Prompt 2 passes the existing library tags
    assert "existing subject keywords/tags already present" in prompts_received[1]
    assert "Molecular Docking" in prompts_received[1]

    # 2. Results merged
    assert "Molecular Docking" in result["matched_existing_keywords"]
    assert "Graph Neural Networks" in result["blind_keywords"]
    assert "Molecular Docking" in result["merged_ai_keywords"]
    assert "Graph Neural Networks" in result["merged_ai_keywords"]


def test_zotero_dialog_save_keywords_preserves_item_and_reopening(qapp, isolated_test_settings, tmp_path):
    """
    Reproduces and verifies the user flow:
    1. Document is in Zotero library.
    2. User opens Zotero dialog, adds/updates keywords, and saves.
    3. Dialog emits valid canonical item dict (never empty).
    4. MainWindow maintains the valid item (current_zotero_item).
    5. Re-opening the Zotero dialog recognizes the article immediately as 'In Zotero Library' with updated keywords.
    """
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    initial_item = {
        "key": "ZOTERO_KEY_999",
        "data": {
            "key": "ZOTERO_KEY_999",
            "title": "Scalable Deep Learning",
            "publicationTitle": "IEEE TPAMI",
            "date": "2023",
            "DOI": "10.1109/TPAMI.2023.12345",
            "abstractNote": "Deep learning at scale.",
            "creators": [{"creatorType": "author", "firstName": "Alice", "lastName": "Smith"}],
            "tags": [{"tag": "Deep Learning"}],
            "collections": [],
        }
    }

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.get_collections_hierarchy.return_value = []
    mock_mgr.get_all_library_tags.return_value = ["Deep Learning", "Transformers", "Computer Vision"]
    mock_mgr.get_item_notes.return_value = []
    mock_mgr.config = isolated_test_settings

    # Mock MainWindow
    mock_main_window = MagicMock()
    mock_main_window.current_zotero_item = initial_item

    # Step 1: Open dialog with existing item
    dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=mock_main_window.current_zotero_item,
        zotero_manager=mock_mgr,
        main_window=mock_main_window,
    )

    assert "In Zotero Library" in dialog.status_label.text()
    assert "Deep Learning" in dialog.tags

    # Step 2: User adds a new keyword
    dialog.tags.append("Transformers")
    dialog._keyword_data["Transformers"] = {"selected": True, "is_ai": False}

    # Simulate update returning the updated item dictionary
    updated_item = {
        "key": "ZOTERO_KEY_999",
        "data": {
            "key": "ZOTERO_KEY_999",
            "title": "Scalable Deep Learning",
            "tags": [{"tag": "Deep Learning"}, {"tag": "Transformers"}],
        }
    }

    emitted_items = []
    dialog.item_updated.connect(lambda item: emitted_items.append(item))

    # Simulate save worker finished
    dialog._on_save_finished(True, "", updated_item)

    # Step 3: Verify emitted item is valid and NOT empty
    assert len(emitted_items) == 1
    emitted = emitted_items[0]
    assert isinstance(emitted, dict)
    assert emitted.get("key") == "ZOTERO_KEY_999"
    assert len(emitted.get("data", {}).get("tags", [])) == 2

    # Step 4: Simulate MainWindow receiving the updated item
    from ui.main_window import MainWindow
    MainWindow._on_zotero_item_updated(mock_main_window, emitted)
    assert mock_main_window.current_zotero_item == emitted
    assert mock_main_window.current_zotero_item.get("key") == "ZOTERO_KEY_999"

    dialog.close()

    # Step 5: User clicks "Zotero" again in MainWindow -> opens new dialog
    reopened_dialog = ZoteroDialog(
        pdf_path=str(pdf_file),
        zotero_item=mock_main_window.current_zotero_item,
        zotero_manager=mock_mgr,
        main_window=mock_main_window,
    )

    assert "In Zotero Library" in reopened_dialog.status_label.text()
    assert reopened_dialog.save_btn.text() == "Save Changes to Zotero"
    assert "Deep Learning" in reopened_dialog.tags
    assert "Transformers" in reopened_dialog.tags

    reopened_dialog.close()


def test_main_window_open_zotero_dialog_when_already_linked(qapp, isolated_test_settings, tmp_path):
    from ui.main_window import MainWindow

    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_text("%PDF-1.4 sample")

    mock_mgr = MagicMock(spec=ZoteroManager)
    mock_mgr.is_configured.return_value = True

    mock_doc = MagicMock()
    mock_doc.file_path = str(pdf_file)
    mock_doc.page_count = 3
    mock_doc.get_page_text.return_value = "Sample text from page"
    mock_doc.doc.metadata = {"title": "Sample Paper"}

    main_win = MagicMock(spec=MainWindow)
    main_win.pdf_doc = mock_doc
    main_win.zotero_manager = mock_mgr
    main_win.ai_assistant = MagicMock()
    main_win.current_zotero_item = {"key": "KEY123", "data": {"key": "KEY123", "title": "Sample Paper"}}
    main_win.zotero_btn = MagicMock()

    with patch("ui.main_window.ZoteroDialog") as mock_dialog_cls:
        mock_dialog_inst = MagicMock()
        mock_dialog_cls.return_value = mock_dialog_inst
        MainWindow.open_zotero_dialog(main_win)

        mock_dialog_cls.assert_called_once()
        call_kwargs = mock_dialog_cls.call_args[1]
        assert call_kwargs["zotero_item"] == main_win.current_zotero_item
        assert call_kwargs["first_page_text"] == "Sample text from page"


