import pytest
from unittest.mock import MagicMock, patch
from backend.config_manager import ConfigManager
from backend.zotero_manager import ZoteroManager
from ui.config_dialog import ZoteroTestWorker


def test_zotero_manager_config(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "1234567"
    config.zotero_library_type = "user"
    config.zotero_auto_check = True

    manager = ZoteroManager(config)
    assert manager.config.zotero_user_id == "1234567"
    assert manager.config.zotero_library_type == "user"
    assert manager.config.zotero_auto_check is True


def test_zotero_keyring_storage(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "99999"
    manager = ZoteroManager(config)

    with patch("keyring.get_password", return_value="my_secret_key"):
        with patch("keyring.set_password") as mock_set:
            assert manager.get_api_key() == "my_secret_key"
            assert manager.is_configured() is True

            manager.set_api_key("new_key")
            mock_set.assert_called_once_with("AIPDFViewer", "zotero_api_key", "new_key")


def test_test_connection_success(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    manager = ZoteroManager(config)

    mock_client = MagicMock()
    mock_client.library_type = "user"
    mock_client.collections.return_value = [{"key": "ABC", "data": {"name": "TestCol"}}]
    mock_client.items.return_value = [{"key": "XYZ"}]

    with patch.object(manager, "get_api_key", return_value="test_key"):
        with patch.object(manager, "get_client", return_value=mock_client):
            success, msg, details = manager.test_connection()
            assert success is True
            assert "Successfully connected" in msg
            assert details["sample_collections_count"] == 1


def test_test_connection_missing_credentials(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = ""
    manager = ZoteroManager(config)

    with patch.object(manager, "get_api_key", return_value=""):
        success, msg, _ = manager.test_connection()
        assert success is False
        assert "User ID" in msg


def test_collections_hierarchy(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    manager = ZoteroManager(config)

    raw_collections = [
        {"key": "ROOT1", "data": {"name": "Root Folder 1", "parentCollection": False}},
        {"key": "CHILD1", "data": {"name": "Child Folder 1", "parentCollection": "ROOT1"}},
        {"key": "ROOT2", "data": {"name": "Root Folder 2", "parentCollection": None}},
    ]

    mock_client = MagicMock()
    mock_client.everything.side_effect = lambda x: x
    mock_client.collections.return_value = raw_collections

    with patch.object(manager, "get_client", return_value=mock_client):
        hierarchy = manager.get_collections_hierarchy(refresh=True)
        assert len(hierarchy) == 2
        root1 = next(c for c in hierarchy if c["key"] == "ROOT1")
        assert len(root1["children"]) == 1
        assert root1["children"][0]["name"] == "Child Folder 1"


def test_create_collection(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    manager = ZoteroManager(config)

    mock_client = MagicMock()
    mock_client.create_collections.return_value = {"successful": {"0": {"key": "NEW123"}}}

    with patch.object(manager, "get_client", return_value=mock_client):
        res = manager.create_collection("Machine Learning", parent_key="ROOT1")
        mock_client.create_collections.assert_called_once_with([{"name": "Machine Learning", "parentCollection": "ROOT1"}])
        assert res == {"successful": {"0": {"key": "NEW123"}}}


def test_find_item_by_doi(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    manager = ZoteroManager(config)

    mock_item = {"key": "PAPER1", "data": {"title": "Attention Is All You Need", "DOI": "10.48550/arXiv.1706.03762"}}
    mock_client = MagicMock()
    mock_client.items.return_value = [mock_item]

    with patch.object(manager, "get_client", return_value=mock_client):
        found = manager.find_item_for_pdf("/fake/path.pdf", doi="10.48550/arXiv.1706.03762")
        assert found is not None
        assert found["key"] == "PAPER1"


def test_add_note_to_item(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    manager = ZoteroManager(config)

    mock_client = MagicMock()
    mock_client.item_template.return_value = {"note": "", "tags": []}
    mock_client.create_items.return_value = {"successful": {"0": {"key": "NOTE1"}}}

    with patch.object(manager, "get_client", return_value=mock_client):
        res = manager.add_note_to_item("PARENT_KEY", "<p>Great paper!</p>", tags=["AI"])
        assert res == {"successful": {"0": {"key": "NOTE1"}}}
        mock_client.create_items.assert_called_once()
        created_note = mock_client.create_items.call_args[0][0][0]
        assert created_note["parentItem"] == "PARENT_KEY"
        assert "<p>Great paper!</p>" in created_note["note"]
        assert created_note["tags"] == [{"tag": "AI"}]


def test_zotero_test_worker_signals(qapp):
    worker = ZoteroTestWorker("user_id_123", "api_key_abc", "user")
    results = []
    worker.result_ready.connect(lambda s, m: results.append((s, m)))

    mock_zotero_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.collections.return_value = [{"key": "COL1"}]
    mock_zotero_cls.return_value = mock_instance

    with patch.dict("sys.modules", {"pyzotero": MagicMock(zotero=mock_zotero_cls)}):
        worker.run()

    assert len(results) == 1
    success, msg = results[0]
    assert success is True
    assert "successfully" in msg.lower()
