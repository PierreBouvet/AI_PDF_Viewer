import threading
import os
import shutil
import tempfile
from collections import OrderedDict
import pymupdf as fitz
from PySide6.QtGui import QImage
from typing import List, Tuple, Optional
from backend.logger import logger

class PDFDocument:
    MAX_WORDS_CACHE_SIZE = 50

    def __init__(self, file_path: str = ""):
        self.file_path = file_path
        self.doc: Optional[fitz.Document] = None
        self.is_dirty = False
        self.is_saved = True
        self._version = 0
        self._lock = threading.RLock()
        self._words_cache = OrderedDict()
        if file_path:
            self.load(file_path)
            
    def load(self, file_path: str) -> bool:
        """Load a PDF document."""
        with self._lock:
            try:
                self.doc = fitz.open(file_path)
                self.file_path = file_path
                self.is_dirty = False
                self.is_saved = True
                self._version = 0
                self._words_cache.clear()
                return True
            except Exception as e:
                logger.error(f"Error loading PDF: {e}")
                self.doc = None
                self._words_cache.clear()
                return False
            
    def close(self):
        """Close the document."""
        with self._lock:
            self._words_cache.clear()
            if self.doc:
                try:
                    self.doc.close()
                except Exception:
                    pass
                self.doc = None
            
    @property
    def page_count(self) -> int:
        with self._lock:
            if self.doc:
                return len(self.doc)
            return 0
            
    def delete_page(self, page_number: int) -> bool:
        """Delete a page from the document."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return False
            try:
                self.doc.delete_page(page_number)
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                self.invalidate_cache()
                return True
            except Exception as e:
                logger.error(f"Error deleting page: {e}")
                return False
        
    def get_page_size(self, page_number: int) -> Tuple[float, float]:
        """Return (width, height) of the page."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return (0.0, 0.0)
            rect = self.doc[page_number].rect
            return (rect.width, rect.height)
        
    def get_page_image(self, page_number: int, zoom_factor: float = 1.0, dpi_scale: float = 2.0, max_zoom: float = 2.0, clip_rect: Optional[Tuple[float, float, float, float]] = None) -> Optional[QImage]:
        """Render a page or a clipped sub-region of a page to a QImage, supporting high DPI scaling."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return None
                
            page = self.doc[page_number]
            
            fitz_clip = None
            if clip_rect is not None:
                # clip_rect is (x0, y0, x1, y1) in page points.
                # When rendering a small clipped viewport tile, we don't cap zoom because the tile area is bounded.
                fitz_clip = fitz.Rect(*clip_rect).intersect(page.rect)
                if fitz_clip.is_empty or fitz_clip.width <= 0 or fitz_clip.height <= 0:
                    return None
                actual_zoom = zoom_factor * dpi_scale
            else:
                # Full-page overview: cap zoom factor to keep base overview memory lightweight (~8 MB)
                effective_zoom = min(zoom_factor, max_zoom) if max_zoom > 0 else zoom_factor
                actual_zoom = effective_zoom * dpi_scale
                
            matrix = fitz.Matrix(actual_zoom, actual_zoom)
            pix = page.get_pixmap(matrix=matrix, clip=fitz_clip)
            
            # Convert PyMuPDF pixmap to QImage
            fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            # We tell the QImage about its logical DPI relation
            image.setDevicePixelRatio(dpi_scale)
            return image.copy() # MUST copy: pix.samples buffer is freed when pix goes out of scope

    def get_page_thumbnail(self, page_number: int, max_size: int = 150) -> Optional[QImage]:
        """Extract a low-resolution thumbnail image."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return None
                
            page = self.doc[page_number]
            # Calculate matrix to fit max_size
            rect = page.rect
            scale = max_size / max(rect.width, rect.height)
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix)
            
            fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            return image.copy()
        
    def get_page_text(self, page_number: int) -> str:
        """Extract text from a specific page."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return ""
            page = self.doc[page_number]
            return page.get_text("text")

    def get_text_in_rect(self, page_number: int, rect_coords: Tuple[float, float, float, float]) -> str:
        """Extract text from a specific rectangular area on a page."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return ""
            page = self.doc[page_number]
            rect = fitz.Rect(*rect_coords)
            return page.get_text("text", clip=rect)

    def get_text_and_rects(self, page_number: int, rect_coords: Tuple[float, float, float, float]) -> Tuple[str, list]:
        """Extract text and the bounding boxes of individual words in a rectangular area."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return ("", [])
            page = self.doc[page_number]
            rect = fitz.Rect(*rect_coords)
            
            text = page.get_text("text", clip=rect)
            words = page.get_text("words", clip=rect)
            rects = [(w[0], w[1], w[2], w[3]) for w in words]
            
            return (text, rects)

    def get_word_at_point(self, page_number: int, x: float, y: float) -> Optional[Tuple[str, Tuple[float, float, float, float]]]:
        """Find and return the word and its bounding box at a specific coordinate."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return None
            page = self.doc[page_number]
            words = page.get_text("words")
            point = fitz.Point(x, y)
            for w in words:
                rect = fitz.Rect(w[:4])
                if rect.contains(point):
                    return (w[4], (w[0], w[1], w[2], w[3]))
            return None

    def get_all_text(self) -> str:
        """Extract all text from the document."""
        with self._lock:
            if not self.doc:
                return ""
            parts = [page.get_text("text") for page in self.doc]
            return "\n".join(parts)

    def is_ai_generated(self, page_index: int) -> bool:
        """Check if a specific page is AI generated using PDF metadata (with legacy fallback)."""
        with self._lock:
            if not self.doc or page_index < 0 or page_index >= self.doc.page_count:
                return False
            page = self.doc[page_index]
            try:
                val = self.doc.xref_get_key(page.xref, "AI_Generated")
                if val == ("bool", "true") or val == ("name", "/true") or val == ("string", "true"):
                    return True
            except Exception:
                pass
            text = page.get_text()
            return "[[AI_GENERATED_PAGE]]" in text

    def append_pdf_file(self, temp_pdf_path: str, output_path: str) -> Tuple[bool, str]:
        """Merge a temporary PDF into the current document. Supports in-place update with backup."""
        with self._lock:
            if not self.doc:
                return False, "No document is open."
                
            backup_path = None
            is_inplace = (os.path.abspath(output_path) == os.path.abspath(self.file_path))
            
            try:
                old_count = self.doc.page_count
                temp_doc = fitz.open(temp_pdf_path)
                self.doc.insert_pdf(temp_doc)
                temp_doc.close()
                new_count = self.doc.page_count
                
                # Tag all newly appended pages with metadata
                for idx in range(old_count, new_count):
                    try:
                        self.doc.xref_set_key(self.doc[idx].xref, "AI_Generated", "true")
                    except Exception as tag_err:
                        logger.warning(f"Could not set AI_Generated metadata on page {idx}: {tag_err}")
                
                if is_inplace:
                    # 1. Create a backup of the original document
                    backup_path = output_path + ".backup"
                    shutil.copy2(self.file_path, backup_path)
                    
                    # 2. Save to a temporary file since PyMuPDF can't overwrite an open file directly
                    fd, save_temp = tempfile.mkstemp(suffix=".pdf")
                    os.close(fd)
                    self.doc.save(save_temp)
                    
                    # 3. Close the PyMuPDF document to release the file lock
                    self.close()
                    
                    # 4. Replace the original file with the new generated PDF
                    shutil.move(save_temp, output_path)
                    
                    # 5. Delete the backup since it was successful
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    
                    # 6. Re-open the document
                    self.load(output_path)
                    return True, ""
                else:
                    self.doc.save(output_path)
                    self.load(output_path)
                    return True, ""
                    
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Failed to append pages: {e}")
                # If we failed and have a backup, try to restore it
                if is_inplace and backup_path and os.path.exists(backup_path):
                    try:
                        self.close()
                        shutil.move(backup_path, output_path)
                        self.load(output_path)
                    except Exception as restore_err:
                        err_msg += f"\nFailed to restore backup: {restore_err}"
                return False, err_msg
                
            finally:
                if os.path.exists(temp_pdf_path):
                    try:
                        os.remove(temp_pdf_path)
                    except Exception:
                        pass

    def add_highlight_annotation(self, page_number: int, rects: List[Tuple[float, float, float, float]]) -> bool:
        """Add standard PDF highlight annotation over rectangles (single unified multi-line annotation)."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc) or not rects:
                return False
            try:
                page = self.doc[page_number]
                quads = [fitz.Rect(*r).quad for r in rects]
                annot = page.add_highlight_annot(quads=quads)
                annot.set_colors(stroke=(1.0, 0.9, 0.0))
                annot.update()
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                return True
            except Exception as e:
                logger.error(f"Error adding highlight annot: {e}")
                return False

    def add_text_annotation(self, page_number: int, point: Tuple[float, float], text: str) -> bool:
        """Add standard PDF sticky Note annotation (Preview & Acrobat compatible)."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return False
            try:
                page = self.doc[page_number]
                p = fitz.Point(point[0], point[1])
                annot = page.add_text_annot(p, text, icon="Comment")
                annot.set_colors(stroke=(1.0, 0.85, 0.0))
                annot.update()
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                return True
            except Exception as e:
                logger.error(f"Error adding text annot: {e}")
                return False

    def add_ink_annotation(self, page_number: int, strokes: List[List[Tuple[float, float]]], color=(1.0, 0.9, 0.0), width=8, opacity=0.5) -> bool:
        """Add freehand marker stroke ink annotation."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc) or not strokes:
                return False
            try:
                page = self.doc[page_number]
                annot = page.add_ink_annot(strokes)
                annot.set_colors(stroke=color)
                annot.set_border(width=width)
                annot.set_opacity(opacity)
                annot.update()
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                return True
            except Exception as e:
                logger.error(f"Error adding ink annot: {e}")
                return False

    def add_freetext_annotation(self, page_number: int, rect: Tuple[float, float, float, float], text: str, font_size=12, text_color=(0, 0, 0), fill_color=None) -> bool:
        """Add standard PDF FreeText annotation (Text box on the PDF)."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return False
            try:
                page = self.doc[page_number]
                r = fitz.Rect(*rect)
                annot = page.add_freetext_annot(r, text, fontsize=font_size, text_color=text_color, fill_color=fill_color)
                annot.update()
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                return True
            except Exception as e:
                logger.error(f"Error adding freetext annot: {e}")
                return False

    def invalidate_cache(self, page_number: Optional[int] = None):
        """Invalidate words and rendering cache."""
        with self._lock:
            if page_number is not None:
                self._words_cache.pop(page_number, None)
            else:
                self._words_cache.clear()

    def get_page_words(self, page_number: int) -> list:
        """Extract and cache the word list for a page with LRU eviction."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return []
            if page_number in self._words_cache:
                self._words_cache.move_to_end(page_number)
                return self._words_cache[page_number]
            try:
                words = self.doc[page_number].get_text("words")
                self._words_cache[page_number] = words
                self._words_cache.move_to_end(page_number)
                if len(self._words_cache) > self.MAX_WORDS_CACHE_SIZE:
                    self._words_cache.popitem(last=False)
                return words
            except Exception as e:
                logger.error(f"Error getting page words: {e}")
                return []

    def get_text_range_rects(self, page_number: int, p0: Tuple[float, float], p1: Tuple[float, float], words: Optional[List] = None) -> Tuple[str, List[Tuple[float, float, float, float]]]:
        """Get text and merged line bounding boxes between two arbitrary points in reading order."""
        if words is None:
            words = self.get_page_words(page_number)
        if not words:
            return "", []
        try:
            def find_closest_word_index(words_list, pt):
                x, y = pt
                for idx, w in enumerate(words_list):
                    if w[0] <= x <= w[2] and w[1] <= y <= w[3]:
                        return idx
                best_idx = 0
                best_dist = float("inf")
                for idx, w in enumerate(words_list):
                    cx, cy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
                    dist = (cx - x)**2 + 4.0 * (cy - y)**2
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = idx
                return best_idx
                
            idx0 = find_closest_word_index(words, p0)
            idx1 = find_closest_word_index(words, p1)
            i_min, i_max = min(idx0, idx1), max(idx0, idx1)
            selected_words = words[i_min:i_max + 1]
            
            lines = {}
            for w in selected_words:
                key = (w[5], w[6])
                if key not in lines:
                    lines[key] = [w[0], w[1], w[2], w[3]]
                else:
                    lines[key][0] = min(lines[key][0], w[0])
                    lines[key][1] = min(lines[key][1], w[1])
                    lines[key][2] = max(lines[key][2], w[2])
                    lines[key][3] = max(lines[key][3], w[3])
            return " ".join(w[4] for w in selected_words), [tuple(r) for r in lines.values()]
        except Exception as e:
            logger.error(f"Error extracting text range: {e}")
            return "", []

    def get_annotation_at_point(self, page_number: int, x: float, y: float, tolerance: float = 6.0):
        """Find topmost annotation on page_number containing point (x, y)."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc):
                return None
            try:
                page = self.doc[page_number]
                point = fitz.Point(x, y)
                annots = list(page.annots())
                for annot in reversed(annots):
                    # Check for highlight quad vertices first if available
                    if annot.type[1] == "Highlight" and getattr(annot, "vertices", None):
                        verts = annot.vertices
                        matched = False
                        for i in range(0, len(verts), 4):
                            chunk = verts[i:i+4]
                            if len(chunk) == 4:
                                min_x = min(p[0] for p in chunk) - tolerance
                                max_x = max(p[0] for p in chunk) + tolerance
                                min_y = min(p[1] for p in chunk) - tolerance
                                max_y = max(p[1] for p in chunk) + tolerance
                                if min_x <= x <= max_x and min_y <= y <= max_y:
                                    matched = True
                                    break
                        if matched:
                            annot.parent_page = page
                            return annot
                    
                    # Default / fallback bounding rect check
                    r = fitz.Rect(annot.rect)
                    r_expanded = fitz.Rect(r.x0 - tolerance, r.y0 - tolerance, r.x1 + tolerance, r.y1 + tolerance)
                    if r_expanded.contains(point):
                        annot.parent_page = page
                        return annot
                return None
            except Exception as e:
                logger.error(f"Error finding annot at point: {e}")
                return None

    def delete_annotation(self, page_number: int, annot) -> bool:
        """Delete an annotation from page."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc) or not annot:
                return False
            try:
                page = getattr(annot, "parent_page", None) or self.doc[page_number]
                page.delete_annot(annot)
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                return True
            except Exception as e:
                logger.error(f"Error deleting annot: {e}")
                return False

    def update_annotation_text(self, page_number: int, annot, new_text: str) -> bool:
        """Update annotation text content (for notes and text boxes)."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc) or not annot:
                return False
            try:
                page = getattr(annot, "parent_page", None) or self.doc[page_number]
                annot_type = annot.type[1]
                if annot_type == "FreeText":
                    r = annot.rect
                    page.delete_annot(annot)
                    self.add_freetext_annotation(page_number, (r.x0, r.y0, r.x1, r.y1), new_text)
                else:
                    annot.set_info(content=new_text)
                    annot.update()
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                return True
            except Exception as e:
                logger.error(f"Error updating annot text: {e}")
                return False

    def move_annotation(self, page_number: int, annot, dx: float, dy: float) -> bool:
        """Move annotation by offset (dx, dy)."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc) or not annot:
                return False
            try:
                page = getattr(annot, "parent_page", None) or self.doc[page_number]
                annot_type = annot.type[1]
                r = annot.rect
                new_r = fitz.Rect(r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy)
                if annot_type == "FreeText":
                    content = annot.info.get("content", "") or annot.get_text()
                    page.delete_annot(annot)
                    self.add_freetext_annotation(page_number, (new_r.x0, new_r.y0, new_r.x1, new_r.y1), content)
                else:
                    annot.set_rect(new_r)
                    annot.update()
                self.is_dirty = True
                self.is_saved = False
                self._version += 1
                return True
            except Exception as e:
                logger.error(f"Error moving annot: {e}")
                return False

    def get_annotation_text(self, page_number: int, annot) -> str:
        """Extract text covered by an annotation (e.g. highlight or ink) or stored in it."""
        with self._lock:
            if not self.doc or page_number < 0 or page_number >= len(self.doc) or not annot:
                return ""
            try:
                page = getattr(annot, "parent_page", None) or self.doc[page_number]
                annot_type = annot.type[1]
                
                # If it's a note or text box, it may have content in info
                stored = annot.info.get("content", "") or annot.get_text()
                if stored and stored.strip():
                    return stored.strip()
                    
                # For Highlight annotations, check quad vertices or rect clip
                if annot_type == "Highlight" and getattr(annot, "vertices", None):
                    verts = annot.vertices
                    chunks = []
                    for i in range(0, len(verts), 4):
                        chunk = verts[i:i+4]
                        if len(chunk) == 4:
                            min_x = min(p[0] for p in chunk)
                            max_x = max(p[0] for p in chunk)
                            min_y = min(p[1] for p in chunk)
                            max_y = max(p[1] for p in chunk)
                            clip_rect = fitz.Rect(min_x, min_y, max_x, max_y)
                            txt = page.get_text("text", clip=clip_rect).strip()
                            if txt:
                                chunks.append(txt)
                    if chunks:
                        return " ".join(chunks)

                # Fallback to rect clip on page
                rect = fitz.Rect(annot.rect)
                text = page.get_text("text", clip=rect).strip()
                return text
            except Exception as e:
                logger.error(f"Error getting text from annot: {e}")
                return ""

    def save_document(self, output_path: str = "") -> Tuple[bool, str]:
        """Persist document and all annotations to PDF file with safe backup."""
        with self._lock:
            if not self.doc:
                return False, "No document loaded"
            save_path = output_path or self.file_path
            if not save_path:
                return False, "No output path specified"
            
            backup_path = None
            temp_file = None
            is_inplace = (os.path.abspath(save_path) == os.path.abspath(self.file_path)) if self.file_path else False
            try:
                if is_inplace:
                    # 1. Create backup of original before touching it
                    backup_path = save_path + ".backup"
                    if os.path.exists(save_path):
                        shutil.copy2(save_path, backup_path)
                    
                    # 2. Save to temporary file
                    dir_name = os.path.dirname(save_path) or None
                    fd, temp_file = tempfile.mkstemp(suffix=".pdf", dir=dir_name)
                    os.close(fd)
                    self.doc.save(temp_file, incremental=False, deflate=True)
                    
                    # 3. Atomic move
                    shutil.move(temp_file, save_path)
                    temp_file = None
                    
                    # 4. Remove backup on success
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                else:
                    self.doc.save(save_path, incremental=False, deflate=True)
                    self.file_path = save_path
                self.is_dirty = False
                self.is_saved = True
                return True, ""
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Failed to save document: {e}")
                # Restore backup on failure
                if is_inplace and backup_path and os.path.exists(backup_path):
                    try:
                        shutil.move(backup_path, save_path)
                    except Exception as restore_err:
                        err_msg += f"\nFailed to restore backup: {restore_err}"
                return False, err_msg
            finally:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass

