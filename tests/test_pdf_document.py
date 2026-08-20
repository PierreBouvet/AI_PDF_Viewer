import pytest
import os
import pymupdf as fitz
from backend.pdf_document import PDFDocument

@pytest.fixture
def dummy_pdf(tmp_path):
    pdf_path = tmp_path / "dummy.pdf"
    doc = fitz.open()
    page = doc.new_page(width=500, height=500)
    page.insert_text((50, 50), "Hello World", fontsize=11)
    
    # Add a page that looks like an AI generated one
    page2 = doc.new_page(width=500, height=500)
    page2.insert_text((50, 50), "[[AI_GENERATED_PAGE]] Generated content", fontsize=11)
    
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_load_pdf(dummy_pdf):
    doc = PDFDocument(dummy_pdf)
    assert doc.doc is not None
    assert doc.page_count == 2
    assert doc.file_path == dummy_pdf

def test_get_page_size(dummy_pdf):
    doc = PDFDocument(dummy_pdf)
    width, height = doc.get_page_size(0)
    assert width == 500.0
    assert height == 500.0

def test_get_page_text(dummy_pdf):
    doc = PDFDocument(dummy_pdf)
    text = doc.get_page_text(0)
    assert "Hello World" in text

def test_is_ai_generated(dummy_pdf):
    doc = PDFDocument(dummy_pdf)
    assert doc.is_ai_generated(0) == False
    assert doc.is_ai_generated(1) == True

def test_append_pdf_file(dummy_pdf, tmp_path):
    # Create a small temp pdf to append
    temp_pdf_path = tmp_path / "temp.pdf"
    temp_doc = fitz.open()
    temp_page = temp_doc.new_page()
    temp_page.insert_text((10, 10), "Appended Content")
    temp_doc.save(str(temp_pdf_path))
    temp_doc.close()
    
    output_path = str(tmp_path / "merged.pdf")
    
    doc = PDFDocument(dummy_pdf)
    success, err = doc.append_pdf_file(str(temp_pdf_path), output_path)
    
    assert success is True
    assert doc.page_count == 3
    assert "Appended Content" in doc.get_page_text(2)
