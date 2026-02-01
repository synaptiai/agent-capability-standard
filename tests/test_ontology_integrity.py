"""Tests for ontology integrity verification (SEC-012).

Validates SHA-256 checksum verification, symlink rejection,
and absolute path resolution for the ontology file.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from grounded_agency.adapter import (
    _find_ontology_path,
    verify_ontology_integrity,
)
from grounded_agency.capabilities.registry import CapabilityRegistry


@pytest.fixture
def ontology_path() -> str:
    """Find the real ontology path."""
    return _find_ontology_path()


@pytest.fixture
def ontology_hash(ontology_path: str) -> str:
    """Compute SHA-256 of the real ontology file."""
    sha = hashlib.sha256()
    with open(ontology_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


class TestVerifyOntologyIntegrity:
    """Tests for verify_ontology_integrity function."""

    def test_passes_with_correct_hash(
        self, ontology_path: str, ontology_hash: str
    ) -> None:
        assert verify_ontology_integrity(ontology_path, ontology_hash) is True

    def test_fails_with_wrong_hash(self, ontology_path: str) -> None:
        assert verify_ontology_integrity(ontology_path, "bad_hash") is False

    def test_passes_with_no_hash(self, ontology_path: str) -> None:
        # Should pass when no expected hash and no sidecar file
        assert verify_ontology_integrity(ontology_path, None) is True

    def test_fails_for_nonexistent_file(self) -> None:
        assert verify_ontology_integrity("/nonexistent/file.yaml", None) is False

    def test_passes_with_sidecar_file(
        self, ontology_path: str, ontology_hash: str, tmp_path: Path
    ) -> None:
        """Test sidecar .sha256 file mechanism."""
        # Copy ontology to temp dir
        src = Path(ontology_path)
        dest = tmp_path / "capability_ontology.yaml"
        dest.write_bytes(src.read_bytes())

        # Create sidecar
        sidecar = tmp_path / "capability_ontology.yaml.sha256"
        sidecar.write_text(f"{ontology_hash}  capability_ontology.yaml\n")

        assert verify_ontology_integrity(str(dest), None) is True

    def test_fails_with_wrong_sidecar(self, ontology_path: str, tmp_path: Path) -> None:
        """Test sidecar with wrong hash."""
        src = Path(ontology_path)
        dest = tmp_path / "capability_ontology.yaml"
        dest.write_bytes(src.read_bytes())

        sidecar = tmp_path / "capability_ontology.yaml.sha256"
        sidecar.write_text(
            "0000000000000000000000000000000000000000000000000000000000000000\n"
        )

        assert verify_ontology_integrity(str(dest), None) is False


class TestFindOntologyPath:
    """Tests for _find_ontology_path function."""

    def test_returns_absolute_path(self) -> None:
        path = _find_ontology_path()
        assert os.path.isabs(path)

    def test_path_exists(self) -> None:
        path = _find_ontology_path()
        assert Path(path).exists()

    def test_path_is_not_symlink(self) -> None:
        path = _find_ontology_path()
        assert not Path(path).is_symlink()


class TestRegistrySymlinkRejection:
    """Tests for SEC-012 symlink rejection in registry."""

    def test_rejects_symlinked_ontology(
        self, ontology_path: str, tmp_path: Path
    ) -> None:
        """Registry should reject symlinked ontology files."""
        link_path = tmp_path / "symlinked_ontology.yaml"
        link_path.symlink_to(ontology_path)

        with pytest.raises(ValueError, match="SEC-012"):
            CapabilityRegistry(str(link_path))
            # Force loading
            _ = CapabilityRegistry(str(link_path)).ontology
