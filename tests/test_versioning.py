"""Hashing, metadata parsing, duplicate and version decisions (synthetic data)."""
from backend.ingestion.versioning import (
    KnownDocument, VersionAction, decide_version, extract_document_metadata, parse_version, sha256_file,
)


def _doc(h, name="a.docx", doc_id="DOC-1", version=None, date=None):
    return KnownDocument(h, name, doc_id, version, date)


def test_sha256_is_stable_and_content_based(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_bytes(b"same"); b.write_bytes(b"same"); c.write_bytes(b"different")
    assert sha256_file(a) == sha256_file(b) != sha256_file(c)


def test_parse_version():
    assert parse_version("SAMPLE 0.1") == (0, 1)
    assert parse_version("v2.10") == (2, 10)
    assert parse_version("draft") is None and parse_version(None) is None


def test_effective_date_is_normalised_to_iso():
    meta = extract_document_metadata("Effective date: 5 March 2024\nVersion: 2.0")
    assert meta.effective_date == "2024-03-05" and meta.version == "2.0"


def test_missing_metadata_stays_none():
    meta = extract_document_metadata("Just some text without any header fields.")
    assert meta.document_id is None and meta.version is None
    assert meta.issuing_authority is None and not meta.is_synthetic


def test_duplicate_content_is_detected():
    decision = decide_version(_doc("h1", "copy.docx"), [_doc("h1")])
    assert decision.action == VersionAction.DUPLICATE and not decision.should_ingest


def test_newer_version_is_accepted_and_supersedes_old():
    old = _doc("h1", version="1.0")
    decision = decide_version(_doc("h2", "b.docx", version="2.0"), [old])
    assert decision.action == VersionAction.NEWER_VERSION and decision.supersedes == old


def test_older_version_is_not_ingested_without_explicit_decision():
    known = [_doc("h2", version="2.0")]
    candidate = _doc("h1", "old.docx", version="1.0")
    assert decide_version(candidate, known).action == VersionAction.OLDER_VERSION
    forced = decide_version(candidate, known, allow_replace=True)
    assert forced.action == VersionAction.FORCED and forced.should_ingest


def test_unknown_precedence_needs_review_and_is_not_guessed():
    decision = decide_version(_doc("h2", "b.docx", version="draft"), [_doc("h1", version="final")])
    assert decision.action == VersionAction.NEEDS_REVIEW and not decision.should_ingest


def test_effective_date_beats_version_number():
    known = [_doc("h1", version="9.0", date="2024-01-01")]
    newer = _doc("h2", "b.docx", version="1.0", date="2025-01-01")
    assert decide_version(newer, known).action == VersionAction.NEWER_VERSION


def test_same_filename_without_id_needs_review():
    decision = decide_version(_doc("h2", "policy.docx", doc_id=None), [_doc("h1", "policy.docx", doc_id=None)])
    assert decision.action == VersionAction.NEEDS_REVIEW
