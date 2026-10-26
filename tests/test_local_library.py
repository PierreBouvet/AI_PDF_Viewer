import os
import sqlite3
import pytest
from backend.local_library_manager import (
    compute_file_sha256,
    extract_first_author_surname,
    sanitize_title_for_filename,
    format_paper_nomenclature,
    is_in_sources_dir,
    LocalLibraryManager,
    move_unmatched_files_to_non_linked,
    _find_best_zotero_match,
)


def test_extract_first_author_surname():
    # List of dicts
    creators_list = [
        {"lastName": "Vaswani", "firstName": "Ashish"},
        {"lastName": "Shazeer", "firstName": "Noam"},
    ]
    author, multiple = extract_first_author_surname(creators_list)
    assert author == "Vaswani"
    assert multiple is True

    # Single author dict
    author_single, mult_single = extract_first_author_surname([{"lastName": "Wilson", "firstName": "Tony"}])
    assert author_single == "Wilson"
    assert mult_single is False

    # String format
    author_str, mult_str = extract_first_author_surname("Silver, David; Huang, Aja; Hassabis, Demis")
    assert author_str == "Silver"
    assert mult_str is True

    # Compound name
    author_comp, _ = extract_first_author_surname("van de Weijer, J.")
    assert "Weijer" in author_comp or "van de Weijer" in author_comp


def test_sanitize_title_for_filename():
    title = "Attention Is All You Need: A Deep Learning Study / Review?"
    clean = sanitize_title_for_filename(title)
    assert ":" not in clean
    assert "/" not in clean
    assert "?" not in clean
    assert "Attention Is All You Need - A Deep Learning Study Review" in clean

    # Super long title
    long_title = "A " * 150
    clean_long = sanitize_title_for_filename(long_title, max_words_or_chars=50)
    assert len(clean_long) <= 50


def test_format_paper_nomenclature():
    # 1 author + year + title
    name1 = format_paper_nomenclature("Optical sectioning in microscopes", [{"lastName": "Wilson"}], "1989")
    assert name1 == "Wilson - 1989 - Optical sectioning in microscopes.pdf"

    # Multiple authors + year + title
    creators = [{"lastName": "Yu"}, {"lastName": "Smith"}]
    name2 = format_paper_nomenclature("GraphRAG with Process Constraints", creators, "2026")
    assert name2 == "Yu et al. - 2026 - GraphRAG with Process Constraints.pdf"

    # Missing year fallback
    name3 = format_paper_nomenclature("Advances in Microscopy", [{"lastName": "Wilson"}], "")
    assert name3 == "Wilson - Advances in Microscopy.pdf"

    # Missing author fallback
    name4 = format_paper_nomenclature("Whitepaper on AI", [], "2024")
    assert name4 == "2024 - Whitepaper on AI.pdf"

    # Colons and special chars
    name5 = format_paper_nomenclature("Title: Subtitle / Part 1?", [{"lastName": "Doe"}], "2021")
    assert name5 == "Doe - 2021 - Title - Subtitle Part 1.pdf"


def test_is_in_sources_dir(tmp_path):
    sources = tmp_path / "Sources"
    sources.mkdir()
    file_inside = sources / "test.pdf"
    file_inside.write_text("dummy")

    other_dir = tmp_path / "Downloads"
    other_dir.mkdir()
    file_outside = other_dir / "test.pdf"
    file_outside.write_text("dummy")

    assert is_in_sources_dir(str(file_inside), str(sources)) is True
    assert is_in_sources_dir(str(file_outside), str(sources)) is False


def test_local_library_manager_db_and_move(tmp_path):
    sources = tmp_path / "Sources"
    mgr = LocalLibraryManager(str(sources))

    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    pdf_source = downloads / "raw_download.pdf"
    pdf_source.write_text("%PDF-1.4 sample content for hash")

    # 1. Prepare move plan
    plan = mgr.prepare_move_plan(
        current_pdf_path=str(pdf_source),
        title="Attention Is All You Need",
        creators=[{"lastName": "Vaswani"}, {"lastName": "Shazeer"}],
        year="2017",
        doi="10.48550/arXiv.1706.03762",
        zotero_key="ZOTERO123"
    )

    assert plan["status"] == "ready"
    assert plan["candidate_filename"] == "Vaswani et al. - 2017 - Attention Is All You Need.pdf"
    target_path = plan["target_path"]

    # 2. Execute move
    dest = mgr.execute_move(
        source_path=str(pdf_source),
        destination_path=target_path,
        title="Attention Is All You Need",
        creators=[{"lastName": "Vaswani"}, {"lastName": "Shazeer"}],
        year="2017",
        doi="10.48550/arXiv.1706.03762",
        zotero_key="ZOTERO123"
    )

    assert os.path.exists(dest)
    assert not os.path.exists(str(pdf_source))

    # 3. Verify database record
    art = mgr.find_article_by_doi("10.48550/arXiv.1706.03762")
    assert art is not None
    assert art["title"] == "Attention Is All You Need"
    assert art["zotero_key"] == "ZOTERO123"
    assert art["first_author"] == "Vaswani"
    assert art["authors_formatted"] == "Vaswani et al."
    assert art["local_path"] == dest

    # 4. Check duplicate detection with identical content
    new_download = downloads / "another_copy.pdf"
    new_download.write_text("%PDF-1.4 sample content for hash")  # exact same content
    plan_dup = mgr.prepare_move_plan(
        current_pdf_path=str(new_download),
        title="Attention Is All You Need",
        creators=[{"lastName": "Vaswani"}, {"lastName": "Shazeer"}],
        year="2017"
    )
    assert plan_dup["status"] == "identical_file_exists"

    # 5. Check name collision with different content
    different_file = downloads / "different_paper.pdf"
    different_file.write_text("%PDF-1.4 completely different paper text")
    plan_collision = mgr.prepare_move_plan(
        current_pdf_path=str(different_file),
        title="Attention Is All You Need",
        creators=[{"lastName": "Vaswani"}, {"lastName": "Shazeer"}],
        year="2017"
    )
    assert plan_collision["status"] == "name_collision"
    assert "_1.pdf" in plan_collision["suggested_numbered_filename"]


def test_move_unmatched_files_to_non_linked(tmp_path):
    sources = tmp_path / "Sources"
    sources.mkdir()

    file1 = sources / "unmatched1.pdf"
    file1.write_text("%PDF-1.4 test 1")
    file2 = sources / "unmatched2.pdf"
    file2.write_text("%PDF-1.4 test 2")

    moved = move_unmatched_files_to_non_linked([str(file1), str(file2)], str(sources))
    assert len(moved) == 2

    non_linked = sources / "Non-linked"
    assert non_linked.exists()
    assert (non_linked / "unmatched1.pdf").exists()
    assert (non_linked / "unmatched2.pdf").exists()
    assert not file1.exists()
    assert not file2.exists()


def test_heuristic_zotero_matcher():
    items = [
        {
            "key": "KEY1",
            "title": "Optical Sectioning in Confocal Fluorescent Microscopes",
            "first_author": "Wilson",
            "authors": "Wilson",
            "year": "1989",
            "attachment_filename": "wilson-1989-optical sectioning in confocal fluorescent microscopes.pdf",
        },
        {
            "key": "KEY2",
            "title": "GraphRAG-R1 Graph Retrieval-Augmented Generation",
            "first_author": "Yu",
            "authors": "Yu et al.",
            "year": "2026",
            "attachment_filename": "",
        }
    ]

    # Exact filename match
    m1 = _find_best_zotero_match("Wilson-1989-Optical sectioning in confocal fluorescent microscopes.pdf", items)
    assert m1 is not None
    assert m1["key"] == "KEY1"

    # Title + Author match
    m2 = _find_best_zotero_match("Yu et al - 2026 - GraphRAG-R1 Graph Retrieval-Augmented Generation.pdf", items)
    assert m2 is not None
    assert m2["key"] == "KEY2"
