"""
local_library_manager.py
-------------------------
Manages the user's centralized local bibliography repository (the 'Sources' directory).
Handles:
1. SQLite database management (.library.sqlite) inside the Sources directory.
2. Standardized academic nomenclature: '{First author surname} et al. - {year} - {title}.pdf'.
3. APFS filename sanitization and safe length limiting.
4. Duplicate checking (SHA-256 and name collision with '_i' resolution).
5. Moving files into the Sources directory and recording metadata.
6. Offline high-speed scanning of Sources files matched against Zotero's local SQLite database.
7. Relocating unlinked files to a 'Non-linked' sub-directory.
"""

import os
import re
import shutil
import sqlite3
import hashlib
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional, Tuple
from backend.logger import logger


def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a file for content deduplication."""
    if not os.path.isfile(file_path):
        return ""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def extract_first_author_surname(creators: Any) -> Tuple[str, bool]:
    """
    Extracts the first author's surname and determines if there are multiple authors.
    Returns (first_author_surname, has_multiple_authors).
    """
    if not creators:
        return "", False

    parsed_authors = []

    if isinstance(creators, str):
        # Format: "Smith, John; Doe, Jane" or "John Smith, Jane Doe"
        raw_items = [p.strip() for p in re.split(r"[;\n]", creators) if p.strip()]
        for item in raw_items:
            if "," in item:
                surname = item.split(",")[0].strip()
                if surname:
                    parsed_authors.append(surname)
            else:
                parts = item.split()
                if parts:
                    parsed_authors.append(parts[-1].strip())
    elif isinstance(creators, list):
        for c in creators:
            if isinstance(c, dict):
                last = c.get("lastName", "").strip()
                if not last:
                    # fallback to name
                    full = c.get("name", "").strip()
                    if full:
                        last = full.split()[-1]
                if last:
                    parsed_authors.append(last)
            elif isinstance(c, str):
                item = c.strip()
                if "," in item:
                    parsed_authors.append(item.split(",")[0].strip())
                elif item:
                    parsed_authors.append(item.split()[-1].strip())

    if not parsed_authors:
        return "", False

    first_author = parsed_authors[0]
    # Clean leading/trailing punctuation
    first_author = re.sub(r"^[^\w]+|[^\w]+$", "", first_author)
    has_multiple = len(parsed_authors) > 1

    return first_author, has_multiple


def sanitize_title_for_filename(title: str, max_words_or_chars: int = 100) -> str:
    """
    Cleans an article title for filesystem naming:
    - Replaces colons with ' - '
    - Strips illegal characters: / \\ ? " * | < >
    - Collapses whitespaces
    - Truncates safely at word boundary to avoid exceeding APFS 255-byte limit
    """
    if not title:
        return "Untitled"

    # Remove XML / HTML tags
    clean = re.sub(r"<[^>]+>", " ", title)

    # Replace colons with spaced hyphen
    clean = clean.replace(":", " - ")

    # Strip forbidden filesystem characters
    clean = re.sub(r'[/\\?*"|<>~#%&{}]', '', clean)

    # Collapse multiple spaces and dashes
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = re.sub(r"\s*-\s*-\s*", " - ", clean)

    # Truncate at word boundary if too long
    if len(clean) > max_words_or_chars:
        truncated = clean[:max_words_or_chars]
        last_space = truncated.rfind(" ")
        if last_space > 30:
            clean = truncated[:last_space].rstrip(" .,;-")
        else:
            clean = truncated.rstrip(" .,;-")

    return clean.strip(" .,;-") or "Untitled"


def format_paper_nomenclature(title: str, creators: Any, year: str = "") -> str:
    """
    Generates standardized academic filename:
    '{First author surname} et al. - {year} - {title}.pdf'
    Fallbacks:
    - 1 author: '{First author surname} - {year} - {title}.pdf'
    - No year: '{Author_str} - {title}.pdf'
    - No author: '{year} - {title}.pdf' or '{title}.pdf'
    """
    first_author, has_multiple = extract_first_author_surname(creators)
    clean_title = sanitize_title_for_filename(title, max_words_or_chars=110)

    # Clean year (extract 4 digits)
    clean_year = ""
    if year:
        m = re.search(r"\b(19\d{2}|20\d{2})\b", str(year))
        if m:
            clean_year = m.group(1)

    author_part = ""
    if first_author:
        author_part = f"{first_author} et al." if has_multiple else first_author

    parts = []
    if author_part:
        parts.append(author_part)
    if clean_year:
        parts.append(clean_year)
    if clean_title:
        parts.append(clean_title)

    filename = " - ".join(parts) + ".pdf"

    # Final APFS length guard (max 240 bytes)
    if len(filename.encode("utf-8")) > 240:
        # shorten title part
        overflow = len(filename.encode("utf-8")) - 240
        clean_title = clean_title[:-overflow].rstrip(" .,;-")
        parts[-1] = clean_title
        filename = " - ".join(parts) + ".pdf"

    return filename


def is_in_sources_dir(file_path: str, sources_dir: str) -> bool:
    """Checks whether file_path is located inside sources_dir."""
    if not file_path or not sources_dir:
        return False
    try:
        norm_path = os.path.realpath(os.path.abspath(file_path))
        norm_sources = os.path.realpath(os.path.abspath(sources_dir))
        return os.path.commonpath([norm_path, norm_sources]) == norm_sources
    except Exception:
        return False


class LocalLibraryManager:
    """
    Manages the local SQLite database (.library.sqlite) in the Sources directory
    and handles file movement, collision resolution, and metadata indexing.
    """

    def __init__(self, sources_dir: str):
        self.sources_dir = os.path.abspath(os.path.expanduser(sources_dir))
        self.db_path = os.path.join(self.sources_dir, ".library.sqlite")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not os.path.isdir(self.sources_dir):
            os.makedirs(self.sources_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes database schema."""
        if not os.path.isdir(self.sources_dir):
            try:
                os.makedirs(self.sources_dir, exist_ok=True)
            except Exception as e:
                logger.error(f"Cannot create sources directory {self.sources_dir}: {e}")
                return

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sha256 TEXT UNIQUE,
                doi TEXT,
                zotero_key TEXT,
                title TEXT NOT NULL,
                first_author TEXT,
                authors_formatted TEXT,
                year TEXT,
                local_path TEXT NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_doi ON articles(doi)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_sha ON articles(sha256)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_zotero ON articles(zotero_key)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_path ON articles(local_path)")
        conn.commit()
        conn.close()

    def find_article_by_sha256(self, sha256_hash: str) -> Optional[Dict[str, Any]]:
        if not sha256_hash:
            return None
        conn = self._get_connection()
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM articles WHERE sha256 = ?", (sha256_hash,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def find_article_by_path(self, local_path: str) -> Optional[Dict[str, Any]]:
        if not local_path:
            return None
        conn = self._get_connection()
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM articles WHERE local_path = ?", (local_path,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def find_article_by_zotero_key(self, zotero_key: str) -> Optional[Dict[str, Any]]:
        if not zotero_key:
            return None
        conn = self._get_connection()
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM articles WHERE zotero_key = ?", (zotero_key,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def find_article_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        if not doi:
            return None
        clean_doi = doi.strip().lower()
        conn = self._get_connection()
        cur = conn.cursor()
        row = cur.execute("SELECT * FROM articles WHERE lower(doi) = ?", (clean_doi,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def save_or_update_article(
        self,
        local_path: str,
        title: str,
        first_author: str = "",
        authors_formatted: str = "",
        year: str = "",
        doi: str = "",
        zotero_key: str = "",
        sha256_hash: str = ""
    ) -> int:
        """Inserts or updates an article in the local library database."""
        if not sha256_hash and os.path.isfile(local_path):
            sha256_hash = compute_file_sha256(local_path)

        conn = self._get_connection()
        cur = conn.cursor()

        # Check existing
        existing_id = None
        if sha256_hash:
            r = cur.execute("SELECT id FROM articles WHERE sha256 = ?", (sha256_hash,)).fetchone()
            if r:
                existing_id = r["id"]

        if not existing_id:
            r = cur.execute("SELECT id FROM articles WHERE local_path = ?", (local_path,)).fetchone()
            if r:
                existing_id = r["id"]

        if existing_id:
            cur.execute("""
                UPDATE articles
                SET title = ?, first_author = ?, authors_formatted = ?, year = ?, doi = ?, zotero_key = ?, local_path = ?
                WHERE id = ?
            """, (title, first_author, authors_formatted, year, doi, zotero_key, local_path, existing_id))
            art_id = existing_id
        else:
            cur.execute("""
                INSERT INTO articles (sha256, doi, zotero_key, title, first_author, authors_formatted, year, local_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sha256_hash, doi, zotero_key, title, first_author, authors_formatted, year, local_path))
            art_id = cur.lastrowid

        conn.commit()
        conn.close()
        return art_id

    def prepare_move_plan(
        self,
        current_pdf_path: str,
        title: str,
        creators: Any,
        year: str = "",
        doi: str = "",
        zotero_key: str = "",
    ) -> Dict[str, Any]:
        """
        Determines target filename and checks for collision/duplicates.
        Returns a dictionary describing the planned move:
        {
            "status": "ready" | "already_in_sources" | "identical_file_exists" | "name_collision",
            "candidate_filename": str,
            "target_path": str,
            "existing_file_path": str (if collision),
            "sha256": str,
        }
        """
        if is_in_sources_dir(current_pdf_path, self.sources_dir):
            return {
                "status": "already_in_sources",
                "candidate_filename": os.path.basename(current_pdf_path),
                "target_path": current_pdf_path,
                "existing_file_path": current_pdf_path,
                "sha256": compute_file_sha256(current_pdf_path),
            }

        candidate_name = format_paper_nomenclature(title, creators, year)
        target_path = os.path.join(self.sources_dir, candidate_name)
        file_sha = compute_file_sha256(current_pdf_path)

        if not os.path.exists(target_path):
            return {
                "status": "ready",
                "candidate_filename": candidate_name,
                "target_path": target_path,
                "existing_file_path": None,
                "sha256": file_sha,
            }

        # Target exists on disk! Check if it's the exact same file
        existing_sha = compute_file_sha256(target_path)
        if file_sha and existing_sha and file_sha == existing_sha:
            return {
                "status": "identical_file_exists",
                "candidate_filename": candidate_name,
                "target_path": target_path,
                "existing_file_path": target_path,
                "sha256": file_sha,
            }

        # Different content but same name: resolve numbered candidate name
        base, ext = os.path.splitext(candidate_name)
        i = 1
        alt_path = os.path.join(self.sources_dir, f"{base}_{i}{ext}")
        while os.path.exists(alt_path):
            if compute_file_sha256(alt_path) == file_sha:
                return {
                    "status": "identical_file_exists",
                    "candidate_filename": os.path.basename(alt_path),
                    "target_path": alt_path,
                    "existing_file_path": alt_path,
                    "sha256": file_sha,
                }
            i += 1
            alt_path = os.path.join(self.sources_dir, f"{base}_{i}{ext}")

        return {
            "status": "name_collision",
            "candidate_filename": candidate_name,
            "suggested_numbered_filename": os.path.basename(alt_path),
            "target_path": target_path,
            "numbered_target_path": alt_path,
            "existing_file_path": target_path,
            "sha256": file_sha,
        }

    def execute_move(
        self,
        source_path: str,
        destination_path: str,
        title: str,
        creators: Any,
        year: str = "",
        doi: str = "",
        zotero_key: str = "",
        sha256_hash: str = ""
    ) -> str:
        """
        Moves the file from source_path to destination_path and indexes it in .library.sqlite.
        Returns final destination path.
        """
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.move(source_path, destination_path)

        first_author, has_multiple = extract_first_author_surname(creators)
        author_fmt = f"{first_author} et al." if has_multiple else first_author

        self.save_or_update_article(
            local_path=destination_path,
            title=title,
            first_author=first_author,
            authors_formatted=author_fmt,
            year=year,
            doi=doi,
            zotero_key=zotero_key,
            sha256_hash=sha256_hash or compute_file_sha256(destination_path)
        )
        return destination_path


# -----------------------------------------------------------------------------------------
# Fast Local Zotero SQLite Scanner & Matcher
# -----------------------------------------------------------------------------------------

def scan_sources_directory_against_zotero(
    sources_dir: str,
    zotero_db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Scans the Sources directory and matches every PDF against the local Zotero SQLite database.
    Performs completely offline with zero network calls and high speed.
    """
    sources_dir = os.path.abspath(os.path.expanduser(sources_dir))
    if not zotero_db_path:
        zotero_db_path = os.path.expanduser("~/Zotero/zotero.sqlite")
    else:
        zotero_db_path = os.path.expanduser(zotero_db_path)

    if not os.path.isfile(zotero_db_path):
        logger.warning(f"Zotero local database not found at {zotero_db_path}")
        return []

    # 1. Connect to Zotero database in read-only immutable mode
    zotero_items = _load_zotero_items_in_memory(zotero_db_path)

    # 2. Collect all PDF files in sources_dir (skipping hidden and 'Non-linked' folder)
    results = []
    if not os.path.isdir(sources_dir):
        return results

    non_linked_dir = os.path.join(sources_dir, "Non-linked")

    for entry in os.scandir(sources_dir):
        if entry.is_file() and entry.name.lower().endswith(".pdf") and not entry.name.startswith("."):
            filename = entry.name
            full_path = entry.path

            match_info = _find_best_zotero_match(filename, zotero_items)
            results.append({
                "pdf_filename": filename,
                "pdf_path": full_path,
                "matched": bool(match_info),
                "zotero_key": match_info.get("key", "") if match_info else "",
                "zotero_authors": match_info.get("authors", "") if match_info else "",
                "zotero_year": match_info.get("year", "") if match_info else "",
                "zotero_title": match_info.get("title", "") if match_info else "",
                "confidence": match_info.get("confidence", 0.0) if match_info else 0.0,
            })

    # Sort results: unmatched first, then alphabetical
    results.sort(key=lambda x: (x["matched"], x["pdf_filename"].lower()))
    return results


def _load_zotero_items_in_memory(zotero_db_path: str) -> List[Dict[str, Any]]:
    """Loads indexed bibliographic items and attachment paths from local Zotero SQLite."""
    conn = sqlite3.connect(f"file:{zotero_db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Query items with title, DOI, date, and any attachment filenames
    query = """
    SELECT 
        i.itemID,
        i.key,
        it.typeName,
        (SELECT value FROM itemData id 
         JOIN itemDataValues idv ON id.valueID = idv.valueID 
         JOIN fields f ON id.fieldID = f.fieldID 
         WHERE id.itemID = i.itemID AND f.fieldName = 'title') as title,
        (SELECT value FROM itemData id 
         JOIN itemDataValues idv ON id.valueID = idv.valueID 
         JOIN fields f ON id.fieldID = f.fieldID 
         WHERE id.itemID = i.itemID AND f.fieldName = 'DOI') as doi,
        (SELECT value FROM itemData id 
         JOIN itemDataValues idv ON id.valueID = idv.valueID 
         JOIN fields f ON id.fieldID = f.fieldID 
         WHERE id.itemID = i.itemID AND f.fieldName = 'date') as date_val,
        ia.path as attachment_path
    FROM items i
    JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
    LEFT JOIN itemAttachments ia ON ia.parentItemID = i.itemID AND ia.contentType = 'application/pdf'
    WHERE it.typeName NOT IN ('attachment', 'note')
    """
    rows = cur.execute(query).fetchall()

    # Creators
    creator_query = """
    SELECT ic.itemID, c.firstName, c.lastName
    FROM itemCreators ic
    JOIN creators c ON ic.creatorID = c.creatorID
    ORDER BY ic.orderIndex
    """
    creator_rows = cur.execute(creator_query).fetchall()
    creators_by_item: Dict[int, List[str]] = {}
    for cr in creator_rows:
        item_id = cr["itemID"]
        last = cr["lastName"] or ""
        first = cr["firstName"] or ""
        author_str = f"{last}, {first}".strip(", ")
        creators_by_item.setdefault(item_id, []).append(author_str)

    items = []
    for r in rows:
        item_id = r["itemID"]
        raw_date = str(r["date_val"] or "")
        year_m = re.search(r"\b(19\d{2}|20\d{2})\b", raw_date)
        year = year_m.group(1) if year_m else ""

        authors_list = creators_by_item.get(item_id, [])
        first_author = ""
        authors_fmt = ""
        if authors_list:
            first_surname = authors_list[0].split(",")[0].strip()
            first_author = first_surname
            authors_fmt = f"{first_surname} et al." if len(authors_list) > 1 else first_surname

        att_path = str(r["attachment_path"] or "")
        att_filename = att_path.replace("storage:", "").strip()

        items.append({
            "key": r["key"],
            "title": str(r["title"] or "").strip(),
            "doi": str(r["doi"] or "").strip().lower(),
            "year": year,
            "first_author": first_author,
            "authors": authors_fmt,
            "attachment_filename": att_filename.lower(),
        })

    conn.close()
    return items


def _find_best_zotero_match(filename: str, zotero_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Heuristically matches a PDF filename to an in-memory Zotero item."""
    clean_fn = filename.lower()
    base_name = re.sub(r"\.pdf$", "", clean_fn, flags=re.IGNORECASE)

    # 1. Exact attachment filename match
    for item in zotero_items:
        if item["attachment_filename"] and item["attachment_filename"] == clean_fn:
            return {**item, "confidence": 1.0}

    # 2. Parse filename segments: e.g. "Author et al - Year - Title" or "Author-Year-Title"
    # Match patterns like: "Weisel_Litvinov-2017-Fibrin..." or "Yu et al - 2026 - Title..."
    cand_year = ""
    year_match = re.search(r"[-_\s]((?:19|20)\d{2})[-_\s]", base_name)
    cand_author = ""
    cand_title = ""

    if year_match:
        cand_year = year_match.group(1)
        before_year = base_name[:year_match.start()].strip(" -_")
        after_year = base_name[year_match.end():].strip(" -_")

        # Author is in before_year
        author_tokens = re.split(r"[-_\s]", before_year)
        cand_author = author_tokens[0] if author_tokens else ""
        cand_title = after_year

    best_match = None
    best_score = 0.0

    for item in zotero_items:
        score = 0.0
        item_title = item["title"].lower()
        item_author = item["first_author"].lower()
        item_year = item["year"]

        # Exact title substring in filename or filename in title
        if item_title and len(item_title) > 8:
            clean_item_title = re.sub(r"[^\w\s]", "", item_title)
            clean_base = re.sub(r"[^\w\s]", "", base_name)
            if clean_item_title in clean_base or clean_base in clean_item_title:
                score += 0.7
            else:
                ratio = SequenceMatcher(None, clean_item_title, clean_base).ratio()
                if ratio > 0.6:
                    score += ratio * 0.7

        # Author match
        if cand_author and item_author:
            if cand_author in item_author or item_author in cand_author:
                score += 0.2

        # Year match
        if cand_year and item_year and cand_year == item_year:
            score += 0.1

        if score > best_score:
            best_score = score
            best_match = item

    if best_match and best_score >= 0.55:
        return {**best_match, "confidence": round(best_score, 2)}

    return None


def search_zotero_local(query: str, zotero_db_path: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
    """Searches the local Zotero SQLite database by title, creator, or DOI for interactive linking."""
    if not zotero_db_path:
        zotero_db_path = os.path.expanduser("~/Zotero/zotero.sqlite")
    else:
        zotero_db_path = os.path.expanduser(zotero_db_path)

    if not os.path.isfile(zotero_db_path):
        return []

    items = _load_zotero_items_in_memory(zotero_db_path)
    clean_q = query.strip().lower()
    if not clean_q:
        return items[:limit]

    matches = []
    q_words = [w for w in clean_q.split() if len(w) > 1]

    for item in items:
        searchable_text = f"{item['title']} {item['first_author']} {item['authors']} {item['year']} {item['doi']}".lower()
        if all(w in searchable_text for w in q_words):
            matches.append(item)
            if len(matches) >= limit:
                break

    return matches


def move_unmatched_files_to_non_linked(unmatched_paths: List[str], sources_dir: str) -> List[Tuple[str, str]]:
    """
    Moves unmatched PDF files to a 'Non-linked' directory inside Sources.
    Returns list of (old_path, new_path).
    """
    sources_dir = os.path.abspath(os.path.expanduser(sources_dir))
    non_linked_dir = os.path.join(sources_dir, "Non-linked")
    os.makedirs(non_linked_dir, exist_ok=True)

    moved = []
    for p in unmatched_paths:
        if os.path.isfile(p):
            fname = os.path.basename(p)
            dest = os.path.join(non_linked_dir, fname)
            # Collision guard in Non-linked
            if os.path.exists(dest) and dest != p:
                base, ext = os.path.splitext(fname)
                i = 1
                while os.path.exists(os.path.join(non_linked_dir, f"{base}_{i}{ext}")):
                    i += 1
                dest = os.path.join(non_linked_dir, f"{base}_{i}{ext}")
            shutil.move(p, dest)
            moved.append((p, dest))
    return moved
