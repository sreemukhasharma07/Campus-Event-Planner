"""Configuration: relative paths, defaults, and validation (synthetic values only)."""
from pathlib import Path

from backend.config import ConfigError, load_settings


def test_defaults_are_relative_to_project_root(tmp_path):
    s = load_settings(env={}, project_root=tmp_path)
    assert s.documents_dir == tmp_path / "documents"
    assert s.sample_dir == tmp_path / "documents" / "sample_policies"
    assert s.official_dir == tmp_path / "documents" / "official"
    assert s.chunk_max_chars == 900


def test_relative_env_path_is_resolved_against_project_root(tmp_path):
    s = load_settings(env={"DOCUMENTS_DIR": "my_docs"}, project_root=tmp_path)
    assert s.documents_dir == (tmp_path / "my_docs").resolve()
    assert s.sample_dir == s.documents_dir / "sample_policies"


def test_invalid_values_raise_clear_errors(tmp_path):
    for env in ({"CHUNK_MAX_CHARS": "abc"}, {"CHUNK_MAX_CHARS": "50"},
                {"CHUNK_MAX_CHARS": "400", "CHUNK_OVERLAP_CHARS": "300"}):
        try:
            load_settings(env=env, project_root=tmp_path)
        except ConfigError as exc:
            assert "CHUNK" in str(exc)
        else:
            raise AssertionError(f"expected ConfigError for {env}")
