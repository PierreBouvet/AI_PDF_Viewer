import os
import re
import keyring
from typing import Optional, List, Dict, Tuple, Any
from backend.config_manager import ConfigManager
from backend.logger import logger

try:
    from pyzotero import zotero
    PYZOTERO_AVAILABLE = True
except ImportError:
    zotero = None
    PYZOTERO_AVAILABLE = False


class ZoteroManager:
    """
    Manages communication with the Zotero Web API v3 using pyzotero.
    Supports library search, attachment upload, collection hierarchy organization,
    notes creation, and tag management.
    """

    SERVICE_NAME = "AIPDFViewer"
    KEY_ACCOUNT = "zotero_api_key"

    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or ConfigManager()
        self._client = None
        self._cached_collections = None

    def get_api_key(self) -> str:
        """Retrieve Zotero API key from system keyring with environment fallback."""
        try:
            key = keyring.get_password(self.SERVICE_NAME, self.KEY_ACCOUNT)
            if key:
                return key.strip()
        except Exception as e:
            logger.warning(f"Failed to access keyring for Zotero API key: {e}")

        return os.environ.get("ZOTERO_API_KEY", "").strip()

    def set_api_key(self, api_key: str):
        """Save Zotero API key securely in system keyring."""
        self._client = None
        try:
            if api_key.strip():
                keyring.set_password(self.SERVICE_NAME, self.KEY_ACCOUNT, api_key.strip())
            else:
                try:
                    keyring.delete_password(self.SERVICE_NAME, self.KEY_ACCOUNT)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to write Zotero API key to keyring: {e}")

    def is_configured(self) -> bool:
        """Returns True if User ID and API Key are both present."""
        return bool(self.config.zotero_user_id and self.get_api_key())

    def get_client(self):
        """Initializes or returns cached pyzotero client."""
        if not PYZOTERO_AVAILABLE:
            raise RuntimeError("pyzotero package is not installed. Please install it via 'pip install pyzotero'.")

        user_id = self.config.zotero_user_id
        api_key = self.get_api_key()
        library_type = self.config.zotero_library_type or "user"

        if not user_id or not api_key:
            raise ValueError("Zotero User ID or API Key is missing. Please configure them in Settings > Zotero.")

        if self._client is None:
            self._client = zotero.Zotero(user_id, library_type, api_key)

        return self._client

    def test_connection(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Tests the connection to Zotero API and fetches basic library information.
        Returns: (success: bool, message: str, details: dict)
        """
        if not PYZOTERO_AVAILABLE:
            return False, "pyzotero library is not installed", {}

        user_id = self.config.zotero_user_id
        api_key = self.get_api_key()
        if not user_id:
            return False, "Zotero User ID is required", {}
        if not api_key:
            return False, "Zotero API Key is required", {}

        try:
            client = self.get_client()
            # Test read permissions with collections query
            collections = client.collections(limit=5)
            details = {
                "user_id": user_id,
                "library_type": client.library_type,
                "sample_collections_count": len(collections),
            }
            return True, f"Successfully connected to Zotero ({client.library_type} library {user_id})", details
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Zotero connection test failed: {err_msg}")
            if "403" in err_msg:
                return False, "Access forbidden (403): Please ensure your API key has read/write permissions for library access.", {}
            elif "400" in err_msg:
                return False, f"Invalid request (400): Please check your User ID ({user_id}).", {}
            return False, f"Connection failed: {err_msg}", {}

    def get_collections_hierarchy(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches all collections from Zotero and organizes them into a nested tree structure.
        Returns list of root collection dicts with 'children' lists.
        """
        if self._cached_collections and not refresh:
            return self._cached_collections

        client = self.get_client()
        try:
            raw_collections = client.everything(client.collections())
        except Exception:
            raw_collections = client.collections()

        collections_map = {}
        for col in raw_collections:
            data = col.get("data", {}) if isinstance(col, dict) else {}
            key = data.get("key") or col.get("key", "")
            name = data.get("name") or col.get("name", "Untitled")
            parent_val = data.get("parentCollection", None)
            parent_key = parent_val if (parent_val and isinstance(parent_val, str)) else None
            collections_map[key] = {
                "key": key,
                "name": name,
                "parent_key": parent_key,
                "children": [],
                "raw": col,
            }

        root_collections = []
        for key, node in collections_map.items():
            parent_key = node["parent_key"]
            if parent_key and parent_key in collections_map:
                collections_map[parent_key]["children"].append(node)
            else:
                root_collections.append(node)

        # Sort alphabetically
        def sort_nodes(nodes):
            nodes.sort(key=lambda n: n["name"].lower())
            for n in nodes:
                sort_nodes(n["children"])

        sort_nodes(root_collections)
        self._cached_collections = root_collections
        return root_collections

    def create_collection(self, name: str, parent_key: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new collection or subcollection."""
        client = self.get_client()
        payload = {"name": name.strip()}
        if parent_key:
            payload["parentCollection"] = parent_key

        res = client.create_collections([payload])
        self._cached_collections = None  # invalidate cache
        return res

    def find_item_for_pdf(self, pdf_path: str, title: str = "", doi: str = "") -> Optional[Dict[str, Any]]:
        """
        Searches the Zotero library to determine if the PDF is already present.
        Order of matching:
        1. Exact DOI match in item metadata
        2. Exact filename match among attachments
        3. Title keyword search
        """
        if not self.is_configured():
            return None

        client = self.get_client()
        filename = os.path.basename(pdf_path)

        # 1. Check by DOI if provided
        if doi:
            clean_doi = doi.strip().lower()
            try:
                results = client.items(q=doi, limit=10)
                for item in results:
                    item_doi = str(item.get("data", {}).get("DOI", "")).strip().lower()
                    if item_doi == clean_doi or clean_doi in item_doi:
                        return item
            except Exception as e:
                logger.warning(f"Error querying Zotero by DOI '{doi}': {e}")

        # 2. Check by filename in attachments
        if filename:
            try:
                results = client.items(q=filename, limit=10)
                for item in results:
                    data = item.get("data", {})
                    if data.get("itemType") == "attachment" and data.get("filename") == filename:
                        parent_key = data.get("parentItem")
                        if parent_key:
                            parent = client.item(parent_key)
                            return parent
                    elif data.get("filename") == filename:
                        return item
            except Exception as e:
                logger.warning(f"Error querying Zotero by filename '{filename}': {e}")

        # 3. Check by title if provided
        if title and len(title.strip()) > 5:
            try:
                clean_title = re.sub(r"[^\w\s]", " ", title)
                words = [w for w in clean_title.split() if len(w) > 3][:6]
                if words:
                    query_str = " ".join(words)
                    results = client.items(q=query_str, limit=5)
                    title_lower = title.strip().lower()
                    for item in results:
                        item_title = str(item.get("data", {}).get("title", "")).strip().lower()
                        if item_title and (item_title == title_lower or title_lower in item_title or item_title in title_lower):
                            return item
            except Exception as e:
                logger.warning(f"Error querying Zotero by title: {e}")

        return None

    def get_item_notes(self, item_key: str) -> List[Dict[str, Any]]:
        """Retrieves all child notes associated with an item."""
        client = self.get_client()
        try:
            children = client.children(item_key)
            notes = [c for c in children if c.get("data", {}).get("itemType") == "note"]
            return notes
        except Exception as e:
            logger.error(f"Failed to fetch notes for item {item_key}: {e}")
            return []

    def add_note_to_item(self, item_key: str, note_html: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Creates a child note on a parent Zotero item."""
        client = self.get_client()
        note_template = {
            "itemType": "note",
            "parentItem": item_key,
            "note": note_html,
        }
        if tags:
            note_template["tags"] = [{"tag": t} for t in tags]
        res = client.create_items([note_template])
        return res

    def add_pdf_to_zotero(
        self,
        pdf_path: str,
        metadata: Dict[str, Any],
        collection_keys: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        initial_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new parent bibliographic item in Zotero, uploads the PDF as an attachment,
        assigns it to collection(s), adds tags, and optionally attaches a child note.
        """
        client = self.get_client()
        item_type = metadata.get("itemType", "journalArticle")

        try:
            template = client.item_template(item_type)
        except Exception:
            template = client.item_template("journalArticle")

        # Fill bibliographic metadata
        if "title" in metadata and metadata["title"]:
            template["title"] = metadata["title"]
        else:
            template["title"] = os.path.basename(pdf_path)

        if "abstractNote" in metadata:
            template["abstractNote"] = metadata["abstractNote"]
        if "publicationTitle" in metadata:
            template["publicationTitle"] = metadata["publicationTitle"]
        if "date" in metadata:
            template["date"] = metadata["date"]
        if "DOI" in metadata:
            template["DOI"] = metadata["DOI"]
        if "url" in metadata:
            template["url"] = metadata["url"]

        # Creators (authors)
        if "creators" in metadata and isinstance(metadata["creators"], list):
            valid_creators = []
            for c in metadata["creators"]:
                if isinstance(c, dict) and (c.get("lastName") or c.get("name")):
                    valid_creators.append({
                        "creatorType": c.get("creatorType", "author"),
                        "firstName": c.get("firstName", ""),
                        "lastName": c.get("lastName", c.get("name", "")),
                    })
            if valid_creators:
                template["creators"] = valid_creators

        # Collections
        if collection_keys:
            template["collections"] = collection_keys

        # Tags
        if tags:
            template["tags"] = [{"tag": t.strip()} for t in tags if t.strip()]

        # 1. Create parent bibliographic item
        create_res = client.create_items([template])
        if not create_res.get("successful"):
            failed = create_res.get("failed", {})
            raise RuntimeError(f"Failed to create Zotero item: {failed}")

        parent_item = create_res["successful"]["0"]
        parent_key = parent_item["key"]

        # 2. Upload PDF attachment if file exists
        if os.path.isfile(pdf_path):
            attachment = {
                "itemType": "attachment",
                "linkMode": "imported_file",
                "title": os.path.basename(pdf_path),
                "filename": os.path.basename(pdf_path),
                "contentType": "application/pdf",
            }
            try:
                client.upload_attachments([attachment], parent_key, basedir=os.path.dirname(pdf_path))
            except Exception as e:
                logger.error(f"Error uploading PDF attachment to Zotero: {e}")

        # 3. Add initial note if provided
        if initial_note:
            try:
                self.add_note_to_item(parent_key, initial_note)
            except Exception as e:
                logger.error(f"Error adding initial note to Zotero item {parent_key}: {e}")

        return parent_item

    def update_item(
        self,
        item_key: str,
        collection_keys: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Updates collections, tags, or metadata for an existing Zotero item."""
        client = self.get_client()
        item = client.item(item_key)

        if collection_keys is not None:
            item["data"]["collections"] = collection_keys

        if tags is not None:
            existing_tags = {t["tag"] for t in item["data"].get("tags", [])}
            for t in tags:
                if t.strip():
                    existing_tags.add(t.strip())
            item["data"]["tags"] = [{"tag": t} for t in sorted(existing_tags)]

        if metadata:
            for k, v in metadata.items():
                if k in item["data"] and v:
                    item["data"][k] = v

        return client.update_item(item)
