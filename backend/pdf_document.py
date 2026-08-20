import pymupdf as fitz
from PySide6.QtGui import QImage
from typing import List, Tuple, Optional

class PDFDocument:
    def __init__(self, file_path: str = ""):
        self.file_path = file_path
        self.doc: Optional[fitz.Document] = None
        if file_path:
            self.load(file_path)
            
    def load(self, file_path: str) -> bool:
        """Load a PDF document."""
        try:
            self.doc = fitz.open(file_path)
            self.file_path = file_path
            return True
        except Exception as e:
            print(f"Error loading PDF: {e}")
            self.doc = None
            return False
            
    def close(self):
        """Close the document."""
        if self.doc:
            self.doc.close()
            self.doc = None
            
    @property
    def page_count(self) -> int:
        if self.doc:
            return len(self.doc)
        return 0
        
    def get_page_size(self, page_number: int) -> Tuple[float, float]:
        """Return (width, height) of the page."""
        if not self.doc or page_number < 0 or page_number >= len(self.doc):
            return (0.0, 0.0)
        rect = self.doc[page_number].rect
        return (rect.width, rect.height)
        
    def get_page_image(self, page_number: int, zoom_factor: float = 1.0, dpi_scale: float = 2.0) -> Optional[QImage]:
        """Render a page to a QImage, supporting high DPI scaling."""
        if not self.doc or page_number < 0 or page_number >= len(self.doc):
            return None
            
        page = self.doc[page_number]
        # Multiply zoom factor by the DPI scale to render at a higher resolution
        actual_zoom = zoom_factor * dpi_scale
        matrix = fitz.Matrix(actual_zoom, actual_zoom)
        pix = page.get_pixmap(matrix=matrix)
        
        # Convert PyMuPDF pixmap to QImage
        fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        # We tell the QImage about its logical DPI relation
        image.setDevicePixelRatio(dpi_scale)
        return image.copy()

    def get_page_thumbnail(self, page_number: int, max_size: int = 150) -> Optional[QImage]:
        """Extract a low-resolution thumbnail image."""
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
        if not self.doc or page_number < 0 or page_number >= len(self.doc):
            return ""
        page = self.doc[page_number]
        return page.get_text("text")

    def get_text_in_rect(self, page_number: int, rect_coords: Tuple[float, float, float, float]) -> str:
        """Extract text from a specific rectangular area on a page."""
        if not self.doc or page_number < 0 or page_number >= len(self.doc):
            return ""
        page = self.doc[page_number]
        rect = fitz.Rect(*rect_coords)
        return page.get_text("text", clip=rect)

    def get_text_and_rects(self, page_number: int, rect_coords: Tuple[float, float, float, float]) -> Tuple[str, list]:
        """Extract text and the bounding boxes of individual words in a rectangular area."""
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
        if not self.doc:
            return ""
        text = ""
        for i in range(len(self.doc)):
            text += self.get_page_text(i) + "\n"
        return text

    def is_ai_generated(self, page_index: int) -> bool:
        """Check if a specific page is AI generated."""
        if not self.doc or page_index < 0 or page_index >= self.doc.page_count:
            return False
        text = self.doc[page_index].get_text()
        return "[[AI_GENERATED_PAGE]]" in text or "Generated by " in text

    def append_pdf_file(self, temp_pdf_path: str, output_path: str) -> Tuple[bool, str]:
        """Merge a temporary PDF into the current document. Supports in-place update with backup."""
        if not self.doc:
            return False, "No document is open."
            
        import os
        import shutil
        import tempfile
        
        backup_path = None
        is_inplace = (os.path.abspath(output_path) == os.path.abspath(self.file_path))
        
        try:
            temp_doc = fitz.open(temp_pdf_path)
            self.doc.insert_pdf(temp_doc)
            temp_doc.close()
            
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
            print(f"Failed to append pages: {e}")
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
