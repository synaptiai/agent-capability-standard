"""Tests for safe YAML loading with size limits (SEC-003).

Validates that ``safe_yaml_load`` enforces file-size bounds
to prevent memory exhaustion from oversized YAML payloads.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from grounded_agency.utils.safe_yaml import (
    DEFAULT_MAX_BYTES,
    ONTOLOGY_MAX_BYTES,
    YAMLSizeExceededError,
    safe_yaml_load,
)


@pytest.fixture
def small_yaml(tmp_path: Path) -> Path:
    """Create a small valid YAML file."""
    p = tmp_path / "small.yaml"
    p.write_text("key: value\nlist:\n  - a\n  - b\n", encoding="utf-8")
    return p


@pytest.fixture
def oversized_yaml(tmp_path: Path) -> Path:
    """Create a YAML file that exceeds the default 1 MB limit."""
    p = tmp_path / "oversized.yaml"
    # Single write — clearly exceeds 1 MB
    padding = "x" * DEFAULT_MAX_BYTES
    p.write_text(f"key: {padding}\n", encoding="utf-8")
    return p


class TestSafeYamlLoad:
    """Tests for safe_yaml_load function."""

    def test_loads_small_file(self, small_yaml: Path) -> None:
        result = safe_yaml_load(small_yaml)
        assert result == {"key": "value", "list": ["a", "b"]}

    def test_rejects_oversized_file(self, oversized_yaml: Path) -> None:
        with pytest.raises(YAMLSizeExceededError) as exc_info:
            safe_yaml_load(oversized_yaml)
        assert exc_info.value.path == oversized_yaml
        assert exc_info.value.size > DEFAULT_MAX_BYTES
        assert exc_info.value.max_size == DEFAULT_MAX_BYTES

    def test_custom_max_size_allows_larger_files(self, oversized_yaml: Path) -> None:
        # Allow up to 20 MB — should pass for our ~1 MB file
        result = safe_yaml_load(oversized_yaml, max_size=20 * 1024 * 1024)
        assert isinstance(result, dict)

    def test_custom_max_size_rejects_small_files(self, small_yaml: Path) -> None:
        with pytest.raises(YAMLSizeExceededError):
            safe_yaml_load(small_yaml, max_size=1)  # 1 byte limit

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            safe_yaml_load(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "invalid.yaml"
        p.write_text("{{invalid: yaml: content::", encoding="utf-8")
        with pytest.raises(yaml.YAMLError):
            safe_yaml_load(p)

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        assert safe_yaml_load(p) is None

    def test_accepts_string_path(self, small_yaml: Path) -> None:
        result = safe_yaml_load(str(small_yaml))
        assert result == {"key": "value", "list": ["a", "b"]}

    def test_ontology_max_bytes_is_larger(self) -> None:
        assert ONTOLOGY_MAX_BYTES > DEFAULT_MAX_BYTES
        assert ONTOLOGY_MAX_BYTES == 10 * 1024 * 1024

    def test_error_message_includes_sizes(self, small_yaml: Path) -> None:
        with pytest.raises(YAMLSizeExceededError, match=r"limit.*1 bytes"):
            safe_yaml_load(small_yaml, max_size=1)


class TestSymlinkRejection:
    """Tests for symlink rejection (SEC-006)."""

    def test_rejects_symlink_to_valid_yaml(self, small_yaml: Path, tmp_path: Path) -> None:
        """Symlinks should be rejected even if the target is a valid YAML file."""
        link = tmp_path / "link.yaml"
        link.symlink_to(small_yaml)
        with pytest.raises(ValueError, match="symlink"):
            safe_yaml_load(link)

    def test_rejects_symlink_to_nonexistent(self, tmp_path: Path) -> None:
        """Symlinks to nonexistent targets should be rejected as symlinks, not FileNotFoundError."""
        link = tmp_path / "dangling.yaml"
        link.symlink_to(tmp_path / "does_not_exist.yaml")
        with pytest.raises(ValueError, match="symlink"):
            safe_yaml_load(link)


class TestYAMLSizeExceededError:
    """Tests for the custom exception."""

    def test_attributes(self, tmp_path: Path) -> None:
        p = tmp_path / "test.yaml"
        err = YAMLSizeExceededError(p, 2_000_000, 1_000_000)
        assert err.path == p
        assert err.size == 2_000_000
        assert err.max_size == 1_000_000

    def test_str_representation(self, tmp_path: Path) -> None:
        p = tmp_path / "test.yaml"
        err = YAMLSizeExceededError(p, 2_000_000, 1_000_000)
        msg = str(err)
        assert "2,000,000" in msg
        assert "1,000,000" in msg
