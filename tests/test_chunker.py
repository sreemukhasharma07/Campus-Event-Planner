"""Chunking: boundaries, metadata, overlap, tables, stable IDs (synthetic data)."""
import re

from backend.ingestion.chunker import chunk_document
from backend.ingestion.document_loader import load_document
from backend.ingestion.records import DocStatus, LoadedDocument, PageText, SourceClass
from tests.conftest import make_docx

LONG_SENTENCES = " ".join(f"Sentence number {i} describes one planning detail." for i in range(1, 41))


def _loaded(text, file_type="docx", name="t.docx"):
    return LoadedDocument(filename=name, file_type=file_type, file_hash="f" * 64,
                          pages=[PageText(None if file_type == "docx" else 1, text)],
                          document_id="TEST-1", version="SAMPLE 0.1", is_synthetic=True)


def test_sections_are_split_at_headings_and_never_mixed():
    doc = _loaded("# 1. Purpose\nWhy this exists.\n# 2. Steps\n- Step A: Do one thing.\n- Step B: Do another.")
    chunks = chunk_document(doc)
    assert [c.section_heading for c in chunks] == ["Purpose", "Steps"]
    assert "Why this exists." in chunks[0].text and "Step A" not in chunks[0].text
    assert "Step A" in chunks[1].text and "Step B" in chunks[1].text   # procedure stays together


def test_metadata_is_preserved_on_every_chunk():
    chunks = chunk_document(_loaded("# 1. A\nText one.\n# 2. B\nText two."))
    assert chunks
    for c in chunks:
        assert c.source == "t.docx" and c.document_id == "TEST-1" and c.version == "SAMPLE 0.1"
        assert c.file_hash == "f" * 64 and c.is_synthetic and c.source_class == SourceClass.SYNTHETIC
        assert c.chunk_id and c.section_heading and c.text
        assert c.to_dict()["citation"] == c.citation


def test_chunk_ids_are_unique_and_stable_across_runs():
    doc = _loaded(f"# 1. Long\n{LONG_SENTENCES}\n# 2. Short\nOne line.")
    first = [c.chunk_id for c in chunk_document(doc, max_chars=300, overlap_chars=50)]
    second = [c.chunk_id for c in chunk_document(doc, max_chars=300, overlap_chars=50)]
    assert first == second and len(first) == len(set(first)) and len(first) > 2


def test_long_section_respects_max_size_and_does_not_cut_sentences():
    chunks = chunk_document(_loaded(f"# 1. Long\n{LONG_SENTENCES}"), max_chars=300, overlap_chars=0)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 300
        assert c.text.endswith("."), c.text            # every chunk ends on a sentence boundary
        assert c.parts_in_section == len(chunks)
    rebuilt = " ".join(c.text for c in chunks)
    assert rebuilt == LONG_SENTENCES                   # nothing lost, nothing duplicated


def test_overlap_repeats_the_end_of_the_previous_chunk():
    chunks = chunk_document(_loaded(f"# 1. Long\n{LONG_SENTENCES}"), max_chars=300, overlap_chars=100)
    assert len(chunks) > 1
    for before, after in zip(chunks, chunks[1:]):
        first_sentence = re.split(r"(?<=\.)\s", after.text)[0]
        start = before.text.rfind(first_sentence)
        assert start >= 0                                   # next chunk begins with text from the previous one
        repeated = before.text[start:]                      # ... a whole-sentence tail of it
        assert after.text.startswith(repeated) and len(repeated) <= 100
        assert len(after.text) <= 300


def test_word_split_is_the_last_resort_for_one_giant_sentence():
    giant = "word " * 400                                # no sentence punctuation at all
    chunks = chunk_document(_loaded(f"# 1. Big\n{giant}"), max_chars=200, overlap_chars=0)
    assert all(len(c.text) <= 200 for c in chunks)
    assert all(not c.text.startswith("ord") and c.text.split()[0] == "word" for c in chunks)


def test_a_giant_unbroken_token_cannot_loop_forever():
    chunks = chunk_document(_loaded("# 1. Url\n" + "x" * 1000), max_chars=200, overlap_chars=0)
    assert [len(c.text) for c in chunks] == [200] * 5


def test_table_header_is_repeated_when_a_table_is_split():
    rows = "\n".join(f"| Item {i} | {i * 10} |" for i in range(1, 41))
    chunks = chunk_document(_loaded("# 1. Costs\n| Item | Cost |\n" + rows), max_chars=250, overlap_chars=0)
    assert len(chunks) > 2
    assert all(c.text.splitlines()[0] == "| Item | Cost |" for c in chunks)
    data_rows = [l for c in chunks for l in c.text.splitlines() if l.startswith("| Item ") and l != "| Item | Cost |"]
    assert len(data_rows) == 40


def test_overlap_never_duplicates_table_header_lines():
    rows = "\n".join(f"| Item {i} | {i} |" for i in range(1, 30))
    chunks = chunk_document(_loaded("# 1. T\n| Item | Cost |\n" + rows), max_chars=200, overlap_chars=60)
    for c in chunks:
        assert c.text.splitlines().count("| Item | Cost |") == 1


def test_front_matter_is_its_own_chunk_with_a_label():
    chunks = chunk_document(_loaded("Title line\nSample document ID: TEST-1\n# 1. Body\nBody text."))
    assert chunks[0].section_type == "front_matter" and chunks[0].section_heading == "Document header"
    assert chunks[1].section_type == "body"


def test_heading_without_body_makes_no_chunk_but_keeps_parent_path():
    doc = _loaded("# 1. Parent\n## 1.1 Child\nChild body text.")
    chunks = chunk_document(doc)
    assert len(chunks) == 1 and chunks[0].section_path == ("Parent", "Child")
    assert chunks[0].section_number == "1.1"


def test_pdf_style_text_numbered_headings_and_wrapped_bullets():
    text = (
        "Title of the sample document\n"
        "1. Details to collect\n"
        "\u2022   First item that is a very long line which wraps onto the next line because the page is narrow\n"
        "    continuation of the first item.\n"
        "\u2022   Second item\n"
        "2. Example checks\n"
        "\u2022   Third item\n"
    )
    chunks = chunk_document(_loaded(text, file_type="pdf", name="t.pdf"))
    headings = [c.section_heading for c in chunks]
    assert headings == ["Document header", "Details to collect", "Example checks"]
    assert "narrow continuation of the first item." in chunks[1].text    # wrapped line rejoined
    assert chunks[1].page == 1 and chunks[1].citation == "t.pdf, p. 1, Section 1: Details to collect"


def test_bullet_glyph_on_its_own_line_is_attached_to_the_next_line():
    chunks = chunk_document(_loaded("1. Items\n\u2022\nFirst thing\n\u2022\nSecond thing", file_type="pdf", name="t.pdf"))
    assert chunks[-1].text == "- First thing\n- Second thing"


def test_numbered_sentence_is_not_mistaken_for_a_heading():
    doc = _loaded("1. Purpose\n3 attendees may register early.\n10 000 seats are not a heading.", file_type="pdf", name="t.pdf")
    chunks = chunk_document(doc)
    body = [c for c in chunks if c.section_heading == "Purpose"][0]
    assert "3 attendees" in body.text and "10 000" in body.text


def test_citation_formats():
    pdf_chunk = chunk_document(_loaded("1. A\nText here.", file_type="pdf", name="x.pdf"))[-1]
    docx_chunk = chunk_document(_loaded("# 2. Budget\nText here."))[-1]
    assert pdf_chunk.citation == "x.pdf, p. 1, Section 1: A"
    assert docx_chunk.citation == "t.docx, Section 2: Budget"             # DOCX: no page, section instead


def test_documents_that_were_not_read_produce_no_chunks():
    for status in (DocStatus.NEEDS_OCR, DocStatus.FAILED, DocStatus.EMPTY):
        doc = LoadedDocument(filename="s.pdf", file_type="pdf", status=status)
        assert chunk_document(doc) == []


def test_bad_parameters_are_rejected():
    for kwargs in ({"max_chars": 50}, {"max_chars": 400, "overlap_chars": 300}):
        try:
            chunk_document(_loaded("# 1. A\nText."), **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kwargs}")


def test_real_docx_round_trip_keeps_table_with_its_section(tmp_path):
    path = make_docx(tmp_path / "r.docx", [
        ("h1", "1. Budget"), ("p", "Costs are listed below."),
        ("table", [["Item", "Cost"], ["Banner", "100"]]),
        ("h1", "2. Notes"), ("p", "Nothing else."),
    ])
    chunks = chunk_document(load_document(path))
    budget = [c for c in chunks if c.section_heading == "Budget"][0]
    assert "| Banner | 100 |" in budget.text and "Costs are listed" in budget.text
