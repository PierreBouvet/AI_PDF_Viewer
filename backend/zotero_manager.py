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

    def get_all_library_tags(self, refresh: bool = False) -> List[str]:
        """Fetches all unique tags / keywords used across the user's Zotero library."""
        if hasattr(self, "_cached_library_tags") and self._cached_library_tags is not None and not refresh:
            return self._cached_library_tags

        if not self.is_configured():
            return []

        try:
            client = self.get_client()
            try:
                raw_tags = client.everything(client.tags())
            except Exception:
                raw_tags = client.tags()
            
            tag_names = set()
            if isinstance(raw_tags, list):
                for t in raw_tags:
                    if isinstance(t, str):
                        tag_names.add(t.strip())
                    elif isinstance(t, dict):
                        name = t.get("tag") or t.get("name") or ""
                        if name:
                            tag_names.add(str(name).strip())
            
            # Sort case-insensitively
            sorted_tags = sorted([t for t in tag_names if t], key=lambda s: s.lower())
            self._cached_library_tags = sorted_tags
            return sorted_tags
        except Exception as e:
            logger.error(f"Failed to fetch library tags: {e}")
            return []

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
                results = client.items(q=filename, limit=15)
                for item in results:
                    data = item.get("data", {})
                    if data.get("itemType") == "attachment" and (data.get("filename") == filename or data.get("title") == filename):
                        parent_key = data.get("parentItem")
                        if parent_key:
                            return client.item(parent_key)
                    elif data.get("filename") == filename or data.get("title") == filename:
                        return item
            except Exception as e:
                logger.warning(f"Error querying Zotero by filename '{filename}': {e}")

        # 3. Check by title if provided
        candidate_titles = []
        if title and len(title.strip()) > 3:
            candidate_titles.append(title.strip())
        base_title = filename.replace(".pdf", "").replace(".PDF", "").strip()
        if base_title and base_title not in candidate_titles and len(base_title) > 3:
            candidate_titles.append(base_title)

        for candidate in candidate_titles:
            try:
                clean_title = re.sub(r"[^\w\s]", " ", candidate)
                words = [w for w in clean_title.split() if len(w) > 3][:6]
                if words:
                    query_str = " ".join(words)
                    results = client.items(q=query_str, limit=5)
                    cand_lower = candidate.lower()
                    for item in results:
                        data = item.get("data", {})
                        if data.get("itemType") == "attachment":
                            parent_key = data.get("parentItem")
                            if parent_key:
                                return client.item(parent_key)
                        item_title = str(data.get("title", "")).strip().lower()
                        if item_title and (item_title == cand_lower or cand_lower in item_title or item_title in cand_lower):
                            return item
            except Exception as e:
                logger.warning(f"Error querying Zotero by candidate title '{candidate}': {e}")

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
        if not create_res.get("successful") and not create_res.get("success"):
            failed = create_res.get("failed", {})
            raise RuntimeError(f"Failed to create Zotero item: {failed}")

        parent_dict = create_res.get("successful", {}).get("0") or {}
        parent_key = parent_dict.get("key") or create_res.get("success", {}).get("0")
        if not parent_key:
            raise RuntimeError(f"Failed to obtain created item key from Zotero: {create_res}")

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

        try:
            return client.item(parent_key)
        except Exception:
            return parent_dict or {"key": parent_key, "data": template}

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
            item["data"]["tags"] = [{"tag": t.strip()} for t in tags if t.strip()]

        if metadata:
            for k, v in metadata.items():
                if k in item["data"] and v:
                    item["data"][k] = v

        client.update_item(item)
        try:
            return client.item(item_key)
        except Exception:
            return item


def _clean_abstract(raw: str) -> str:
    """Removes XML/HTML markup from abstracts."""
    if not raw:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(cleaned.split()).strip()


def _parse_crossref_message(msg: Dict[str, Any], fallback_doi: str = "") -> Dict[str, Any]:
    """Parses a Crossref API message dictionary into a standardized metadata format."""
    title_raw = msg.get("title", [""])
    title = title_raw[0] if isinstance(title_raw, list) and title_raw else str(title_raw or "")
    
    container_raw = msg.get("container-title", [""])
    publication = container_raw[0] if isinstance(container_raw, list) and container_raw else str(container_raw or "")
    
    doi = msg.get("DOI", "") or fallback_doi
    
    # Extract year
    date_parts = (
        msg.get("issued", {}).get("date-parts")
        or msg.get("published-print", {}).get("date-parts")
        or msg.get("published-online", {}).get("date-parts")
        or [[None]]
    )
    raw_year = date_parts[0][0] if date_parts and date_parts[0] else None
    year_str = str(raw_year) if raw_year else ""

    creators = []
    for a in msg.get("author", []):
        if not isinstance(a, dict):
            continue
        first_name = a.get("given", "").strip()
        last_name = a.get("family", "").strip()
        single_name = a.get("name", "").strip()
        if last_name or first_name:
            creators.append({
                "creatorType": "author",
                "firstName": first_name,
                "lastName": last_name,
            })
        elif single_name:
            creators.append({
                "creatorType": "author",
                "firstName": "",
                "lastName": single_name,
            })

    type_map = {
        "journal-article": "journalArticle",
        "book": "book",
        "monograph": "book",
        "book-chapter": "bookSection",
        "proceedings-article": "conferencePaper",
        "proceedings": "conferencePaper",
        "posted-content": "preprint",
        "report": "report",
        "dissertation": "thesis",
    }
    raw_type = msg.get("type", "")
    item_type = type_map.get(raw_type, "journalArticle")

    abstract = _clean_abstract(msg.get("abstract", ""))

    return {
        "itemType": item_type,
        "title": title.strip(),
        "creators": creators,
        "publicationTitle": publication.strip(),
        "date": year_str,
        "DOI": doi.strip(),
        "abstractNote": abstract,
        "source": "Crossref",
    }


def _parse_arxiv_entry(entry, ns: Dict[str, str], fallback_id: str = "") -> Dict[str, Any]:
    """Parses an arXiv Atom XML entry into a standardized metadata format."""
    title_node = entry.find("atom:title", ns)
    title = title_node.text.strip().replace("\n", " ") if title_node is not None and title_node.text else ""
    title = " ".join(title.split())

    summary_node = entry.find("atom:summary", ns)
    abstract = summary_node.text.strip().replace("\n", " ") if summary_node is not None and summary_node.text else ""
    abstract = " ".join(abstract.split())

    published_node = entry.find("atom:published", ns)
    date_str = published_node.text[:4] if published_node is not None and published_node.text else ""

    creators = []
    for a in entry.findall("atom:author", ns):
        name_node = a.find("atom:name", ns)
        if name_node is not None and name_node.text:
            parts = name_node.text.strip().split()
            if len(parts) > 1:
                creators.append({
                    "creatorType": "author",
                    "firstName": " ".join(parts[:-1]),
                    "lastName": parts[-1],
                })
            elif len(parts) == 1:
                creators.append({
                    "creatorType": "author",
                    "firstName": "",
                    "lastName": parts[0],
                })

    id_node = entry.find("atom:id", ns)
    doi = ""
    if id_node is not None and id_node.text and "arxiv.org/abs/" in id_node.text:
        arx_id = id_node.text.split("arxiv.org/abs/")[-1].strip()
        doi = f"10.48550/arXiv.{arx_id}"
    elif fallback_id:
        doi = f"10.48550/arXiv.{fallback_id}"

    return {
        "itemType": "preprint",
        "title": title,
        "creators": creators,
        "publicationTitle": "arXiv",
        "date": date_str,
        "DOI": doi,
        "abstractNote": abstract,
        "source": "arXiv",
    }


def lookup_scientific_article(
    doi: str = "",
    title: str = "",
    text_snippet: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Queries canonical scientific databases (Crossref, with arXiv fallback)
    to find bibliographic records for an article and returns normalized metadata.
    """
    import urllib.request
    import urllib.parse
    import json
    from difflib import SequenceMatcher

    clean_doi = ""
    if doi:
        m = re.search(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', doi)
        if m:
            clean_doi = m.group(0).rstrip('.;,)')
    if not clean_doi and text_snippet:
        m = re.search(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', text_snippet[:3000])
        if m:
            clean_doi = m.group(0).rstrip('.;,)')

    headers = {
        "User-Agent": "AI-Enhanced-PDF-Viewer/1.1 (https://github.com/pierrebouvet/AI_PDF_Viewer; mailto:support@aipdfviewer.local)"
    }

    # 1. Try direct DOI query on Crossref
    if clean_doi:
        try:
            quoted_doi = urllib.parse.quote(clean_doi, safe="/")
            url = f"https://api.crossref.org/works/{quoted_doi}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg = data.get("message", {})
                if msg:
                    return _parse_crossref_message(msg, fallback_doi=clean_doi)
        except Exception as e:
            logger.info(f"Crossref direct DOI query failed for '{clean_doi}': {e}")

    # 2. Try title query on Crossref
    candidate_title = title.strip()
    if not candidate_title and text_snippet:
        lines = [line.strip() for line in text_snippet.split("\n") if line.strip()]
        for line in lines[:5]:
            if len(line) > 12 and not any(kw in line.lower() for kw in ["issn", "isbn", "doi", "volume", "issue", "http", "published"]):
                candidate_title = line
                break

    if candidate_title:
        try:
            query_url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(candidate_title)}&rows=3"
            req = urllib.request.Request(query_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("message", {}).get("items", [])
                for item in items:
                    raw_title_list = item.get("title", [""])
                    raw_title = raw_title_list[0] if raw_title_list else ""
                    ratio = SequenceMatcher(None, candidate_title.lower(), raw_title.lower()).ratio()
                    if ratio >= 0.5 or candidate_title.lower() in raw_title.lower() or raw_title.lower() in candidate_title.lower():
                        return _parse_crossref_message(item)
        except Exception as e:
            logger.info(f"Crossref title query failed for '{candidate_title}': {e}")

    # 3. Try arXiv lookup
    arxiv_id = ""
    if clean_doi and "arxiv." in clean_doi.lower():
        arxiv_match = re.search(r'arXiv\.([0-9]+\.[0-9]+)', clean_doi, re.IGNORECASE)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)
    if not arxiv_id and text_snippet:
        arxiv_match = re.search(r'arXiv:([0-9]+\.[0-9]+)', text_snippet[:3000], re.IGNORECASE)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)

    try:
        import xml.etree.ElementTree as ET
        if arxiv_id:
            arxiv_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        elif candidate_title:
            arxiv_url = f"https://export.arxiv.org/api/query?search_query=ti:{urllib.parse.quote(candidate_title)}&max_results=1"
        else:
            arxiv_url = None

        if arxiv_url:
            req = urllib.request.Request(arxiv_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read().decode("utf-8"))
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entry = root.find("atom:entry", ns)
                if entry is not None:
                    return _parse_arxiv_entry(entry, ns, fallback_id=arxiv_id)
    except Exception as e:
        logger.info(f"arXiv query failed: {e}")

    return None
