import pytest
import pymupdf as fitz
import tempfile
import os
from backend.pdf_document import PDFDocument
from ui.annotation_toolbar import AnnotationTool, FloatingAnnotationBar


@pytest.fixture
def sample_pdf():
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 100), "This is a test paragraph for annotations.")
    doc.save(path)
    doc.close()
    
    pdf_doc = PDFDocument(path)
    yield pdf_doc
    
    pdf_doc.close()
    if os.path.exists(path):
        os.remove(path)


def test_add_highlight_annotation(sample_pdf):
    # Highlight word
    rects = [(50, 90, 150, 110)]
    assert sample_pdf.add_highlight_annotation(0, rects)
    
    page = sample_pdf.doc[0]
    annots = list(page.annots())
    assert len(annots) >= 1
    assert annots[0].type[0] == fitz.PDF_ANNOT_HIGHLIGHT


def test_multiline_highlight_delete_all_at_once(sample_pdf):
    # Add multi-line highlight across 3 lines
    rects = [
        (50, 90, 150, 110),
        (50, 120, 200, 140),
        (50, 150, 180, 170)
    ]
    assert sample_pdf.add_highlight_annotation(0, rects)
    assert sample_pdf.save_document()[0]
    
    # Verify only 1 unified annotation exists on the page
    page = sample_pdf.doc[0]
    annots = list(page.annots())
    assert len(annots) == 1
    
    # Query on line 2
    annot_on_line2 = sample_pdf.get_annotation_at_point(0, 100, 130)
    assert annot_on_line2 is not None
    assert annot_on_line2.type[1] == "Highlight"
    
    # Delete the highlight from line 2
    assert sample_pdf.delete_annotation(0, annot_on_line2)
    
    # Verify all lines are deleted at once
    assert len(list(sample_pdf.doc[0].annots())) == 0


def test_get_text_range_rects(sample_pdf):
    # Select from "This" to "paragraph"
    text, rects = sample_pdf.get_text_range_rects(0, (50, 95), (160, 95))
    assert "This" in text
    assert "paragraph" in text or "test" in text
    assert len(rects) >= 1


def test_add_text_sticky_note(sample_pdf):
    assert sample_pdf.add_text_annotation(0, (100, 200), "My sticky note")
    
    page = sample_pdf.doc[0]
    annots = list(page.annots())
    assert any(a.type[0] == fitz.PDF_ANNOT_TEXT for a in annots)
    
    note_annot = next(a for a in annots if a.type[0] == fitz.PDF_ANNOT_TEXT)
    assert note_annot.info["content"] == "My sticky note"


def test_add_ink_annotation(sample_pdf):
    strokes = [[(50, 300), (80, 310), (120, 305)]]
    assert sample_pdf.add_ink_annotation(0, strokes)
    
    page = sample_pdf.doc[0]
    annots = list(page.annots())
    assert any(a.type[0] == fitz.PDF_ANNOT_INK for a in annots)


def test_add_freetext_annotation(sample_pdf):
    rect = (50, 400, 250, 450)
    assert sample_pdf.add_freetext_annotation(0, rect, "Writing directly on PDF")
    
    page = sample_pdf.doc[0]
    annots = list(page.annots())
    assert any(a.type[1] == "FreeText" for a in annots)


def test_floating_annotation_bar_cycle(qtbot):
    bar = FloatingAnnotationBar()
    qtbot.addWidget(bar)
    
    assert bar.active_tool == AnnotationTool.NONE
    assert bar.highlight_state == 0
    
    # 1st Click on Highlight: Text recognition
    bar.btn_highlight.click()
    assert bar.active_tool == AnnotationTool.HIGHLIGHT_TEXT
    assert bar.highlight_state == 1
    assert bar.btn_highlight.is_active
    
    # 2nd Click on Highlight: Freehand
    bar.btn_highlight.click()
    assert bar.active_tool == AnnotationTool.HIGHLIGHT_FREEHAND
    assert bar.highlight_state == 2
    assert bar.btn_highlight.is_active
    
    # 3rd Click on Highlight: Inactive
    bar.btn_highlight.click()
    assert bar.active_tool == AnnotationTool.NONE
    assert bar.highlight_state == 0
    assert not bar.btn_highlight.is_active
    
    # Text tool toggle
    bar.btn_text.click()
    assert bar.active_tool == AnnotationTool.TEXT_BOX
    bar.btn_text.click()
    assert bar.active_tool == AnnotationTool.NONE
    
    # Note tool toggle
    bar.btn_note.click()
    assert bar.active_tool == AnnotationTool.NOTE
    bar.btn_note.click()
    assert bar.active_tool == AnnotationTool.NONE


def test_annotation_query_edit_move_delete(sample_pdf):
    # 1. Add a note and text box
    sample_pdf.add_text_annotation(0, (100, 100), "Initial Note")
    sample_pdf.add_freetext_annotation(0, (50, 200, 200, 250), "Initial TextBox")
    
    # 2. Query at point
    note_annot = sample_pdf.get_annotation_at_point(0, 100, 100)
    assert note_annot is not None
    assert note_annot.type[1] == "Text"
    
    # 3. Edit text
    assert sample_pdf.update_annotation_text(0, note_annot, "Updated Note")
    
    textbox_annot = sample_pdf.get_annotation_at_point(0, 80, 220)
    assert textbox_annot is not None
    assert textbox_annot.type[1] == "FreeText"
    assert sample_pdf.update_annotation_text(0, textbox_annot, "Updated TextBox")
    
    # Re-query
    note_annot = sample_pdf.get_annotation_at_point(0, 100, 100)
    assert note_annot.info.get("content") == "Updated Note"
    
    # 4. Move annotation
    r_before = note_annot.rect
    assert sample_pdf.move_annotation(0, note_annot, 30, 40)
    note_annot = sample_pdf.get_annotation_at_point(0, 130, 140)
    assert note_annot is not None
    assert abs(note_annot.rect.x0 - (r_before.x0 + 30)) < 1.0
    
    # 5. Delete annotation
    assert sample_pdf.delete_annotation(0, note_annot)
    assert sample_pdf.get_annotation_at_point(0, 130, 140) is None
