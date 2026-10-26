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


def test_lookup_scientific_article_crossref_doi():
    import json
    import io
    from backend.zotero_manager import lookup_scientific_article

    mock_crossref_resp = {
        "status": "ok",
        "message": {
            "title": ["Mastering the game of Go with deep neural networks and tree search"],
            "container-title": ["Nature"],
            "DOI": "10.1038/nature16961",
            "type": "journal-article",
            "issued": {"date-parts": [[2016, 1, 28]]},
            "author": [
                {"given": "David", "family": "Silver"},
                {"given": "Aja", "family": "Huang"},
                {"given": "Demis", "family": "Hassabis"}
            ],
            "abstract": "<jats:p>The game of Go has long been viewed as the most challenging of classic games.</jats:p>"
        }
    }

    mock_resp = io.BytesIO(json.dumps(mock_crossref_resp).encode("utf-8"))

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = lookup_scientific_article(doi="10.1038/nature16961")
        assert res is not None
        assert res["title"] == "Mastering the game of Go with deep neural networks and tree search"
        assert res["publicationTitle"] == "Nature"
        assert res["date"] == "2016"
        assert res["DOI"] == "10.1038/nature16961"
        assert res["itemType"] == "journalArticle"
        assert len(res["creators"]) == 3
        assert res["creators"][0]["lastName"] == "Silver"
        assert "The game of Go" in res["abstractNote"]
        assert "<jats:p>" not in res["abstractNote"]


def test_lookup_scientific_article_arxiv_fallback():
    import io
    from backend.zotero_manager import lookup_scientific_article

    arxiv_xml = """<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/1706.03762v1</id>
        <published>2017-06-12T17:57:34Z</published>
        <title>Attention Is All You Need</title>
        <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
        <author><name>Ashish Vaswani</name></author>
        <author><name>Noam Shazeer</name></author>
      </entry>
    </feed>"""

    mock_resp = io.BytesIO(arxiv_xml.encode("utf-8"))

    # Fail crossref, succeed arxiv
    def mock_urlopen(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "crossref.org" in url:
            raise Exception("Crossref 404")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = lookup_scientific_article(title="Attention Is All You Need", text_snippet="arXiv:1706.03762")
        assert res is not None
        assert res["title"] == "Attention Is All You Need"
        assert res["publicationTitle"] == "arXiv"
        assert res["date"] == "2017"
        assert "1706.03762" in res["DOI"]
        assert res["itemType"] == "preprint"
        assert len(res["creators"]) == 2
        assert res["creators"][0]["lastName"] == "Vaswani"


def test_scientific_db_search_worker_signals(qapp):
    from ui.zotero_dialog import ScientificDBSearchWorker
    worker = ScientificDBSearchWorker(doi="10.1234/test")
    results = []
    worker.finished_signal.connect(lambda s, e, r: results.append((s, e, r)))

    mock_result = {
        "title": "Quantum Computation",
        "publicationTitle": "Science",
        "date": "2024",
        "DOI": "10.1234/test",
        "creators": [],
        "abstractNote": "Test abstract"
    }

    with patch("backend.zotero_manager.lookup_scientific_article", return_value=mock_result):
        worker.run()

    assert len(results) == 1
    success, err, data = results[0]
    assert success is True
    assert data["title"] == "Quantum Computation"


def test_update_item_handles_raw_response_and_fetches_canonical_item(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    manager = ZoteroManager(config)

    initial_item = {
        "key": "ITEM_KEY_123",
        "data": {
            "key": "ITEM_KEY_123",
            "title": "Original Title",
            "tags": [{"tag": "OldTag"}],
            "collections": []
        }
    }
    updated_remote_item = {
        "key": "ITEM_KEY_123",
        "data": {
            "key": "ITEM_KEY_123",
            "title": "Original Title",
            "tags": [{"tag": "NewTag1"}, {"tag": "NewTag2"}],
            "collections": ["COL_A"]
        }
    }

    mock_client = MagicMock()
    mock_client.item.side_effect = [initial_item, updated_remote_item]
    # In real pyzotero, update_item returns an httpx2.Response object (not a dict)
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_client.update_item.return_value = mock_response

    with patch.object(manager, "get_client", return_value=mock_client):
        res = manager.update_item(
            item_key="ITEM_KEY_123",
            collection_keys=["COL_A"],
            tags=["NewTag1", "NewTag2"]
        )

        assert isinstance(res, dict)
        assert res["key"] == "ITEM_KEY_123"
        assert len(res["data"]["tags"]) == 2
        assert res["data"]["tags"][0]["tag"] == "NewTag1"
        assert res["data"]["tags"][1]["tag"] == "NewTag2"
        assert res["data"]["collections"] == ["COL_A"]


def test_find_item_by_title_resolves_attachment_parent(isolated_test_settings):
    config = isolated_test_settings
    config.zotero_user_id = "12345"
    manager = ZoteroManager(config)

    attachment_item = {
        "key": "ATT_999",
        "data": {
            "itemType": "attachment",
            "parentItem": "PARENT_888",
            "title": "nature_paper.pdf",
            "filename": "nature_paper.pdf"
        }
    }
    parent_item = {
        "key": "PARENT_888",
        "data": {
            "key": "PARENT_888",
            "itemType": "journalArticle",
            "title": "Mastering the game of Go"
        }
    }

    mock_client = MagicMock()
    # 1. DOI fails or empty
    # 2. Filename query returns empty
    # 3. Candidate title query returns the attachment
    mock_client.items.return_value = [attachment_item]
    mock_client.item.return_value = parent_item

    with patch.object(manager, "get_client", return_value=mock_client):
        found = manager.find_item_for_pdf("/path/nature_paper.pdf", title="Mastering the game of Go")
        assert found is not None
        assert found["key"] == "PARENT_888"
        mock_client.item.assert_called_with("PARENT_888")


