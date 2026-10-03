"""Folder ingestion: resilience, duplicates, summaries, synthetic labelling."""
import shutil

import pytest

from backend.ingestion.pipeline import format_summary, ingest_folder
from backend.ingestion.records import DocStatus, SourceClass
from tests.conftest import make_docx, make_pdf


def test_one_bad_file_does_not_stop_the_run(tmp_path, settings):
    make_docx(tmp_path / "good.docx", [("h1", "1. A"), ("p", "Some good text here.")])
    (tmp_path / "broken.docx").write_bytes(b"not a docx")
    (tmp_path / "empty.docx").write_bytes(b"")
    (tmp_path / "data.xlsx").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("ignored")
    result = ingest_folder(tmp_path, SourceClass.SYNTHETIC, settings=settings)
    status = {d.filename: d.status for d in result.documents}
    assert status == {
        "broken.docx": DocStatus.FAILED, "data.xlsx": DocStatus.UNSUPPORTED,
        "empty.docx": DocStatus.EMPTY, "good.docx": DocStatus.OK,
    }
    assert result.ignored_files == ["notes.txt"] and result.chunks


def test_duplicate_files_are_detected_by_hash(tmp_path, settings):
    original = make_docx(tmp_path / "a.docx", [("h1", "1. A"), ("p", "Identical content.")])
    shutil.copy(original, tmp_path / "b_copy.docx")
    result = ingest_folder(tmp_path, SourceClass.SYNTHETIC, settings=settings)
    statuses = sorted(d.status.value for d in result.documents)
    assert statuses == ["duplicate", "ok"]
    assert len({c.source for c in result.chunks}) == 1          # duplicate produced no chunks


def test_older_version_is_skipped_and_reported(tmp_path, settings):
    make_docx(tmp_path / "new.docx", [("p", "Sample document ID: D-1"), ("p", "Version: 2.0"), ("p", "Body text new.")])
    make_docx(tmp_path / "zold.docx", [("p", "Sample document ID: D-1"), ("p", "Version: 1.0"), ("p", "Body text old.")])
    # Files are processed alphabetically: 'new' (v2.0) first, then 'zold' (v1.0).
    result = ingest_folder(tmp_path, SourceClass.SYNTHETIC, settings=settings)
    by_name = {d.filename: d for d in result.documents}
    assert by_name["new.docx"].status == DocStatus.OK
    assert by_name["zold.docx"].status == DocStatus.SKIPPED
    assert "Human decision required" in by_name["zold.docx"].error
    forced = ingest_folder(tmp_path, SourceClass.SYNTHETIC, settings=settings, allow_replace=True)
    assert {d.status for d in forced.documents} == {DocStatus.OK}


def test_nothing_in_sample_folder_is_ever_marked_official(sample_dir, settings, tmp_path):
    docx_only = tmp_path / "docs"
    docx_only.mkdir()
    for path in sample_dir.glob("*.docx"):
        shutil.copy(path, docx_only)
    result = ingest_folder(docx_only, SourceClass.OFFICIAL, settings=settings)    # even if mislabelled official
    assert result.chunks
    assert all(c.source_class == SourceClass.SYNTHETIC and c.is_synthetic for c in result.chunks)
    assert all(d.warnings for d in result.documents)


def test_provided_samples_produce_cited_chunks(sample_dir, settings):
    pytest.importorskip("pymupdf")
    result = ingest_folder(sample_dir, SourceClass.SYNTHETIC, settings=settings)
    assert result.count(DocStatus.OK) == 5 and result.count(DocStatus.FAILED) == 0
    assert {c.document_id for c in result.chunks} == {f"SAMPLE-EVT-00{i}" for i in range(1, 6)}
    assert all(c.citation and c.chunk_id for c in result.chunks)
    assert len({c.chunk_id for c in result.chunks}) == len(result.chunks)
    assert all(c.page == 1 for c in result.chunks if c.source.endswith(".pdf"))


def test_scanned_pdf_is_reported_in_summary(tmp_path, settings):
    make_pdf(tmp_path / "scan.pdf", [""])
    result = ingest_folder(tmp_path, SourceClass.SYNTHETIC, settings=settings)
    text = format_summary(result)
    assert "needs_ocr" in text and "NOT fully processed" in text and not result.chunks


def test_missing_folder_returns_empty_result(tmp_path, settings):
    result = ingest_folder(tmp_path / "nope", SourceClass.SYNTHETIC, settings=settings)
    assert result.documents == [] and result.chunks == []
