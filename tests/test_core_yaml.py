"""The Rust core's YAML loader against PyYAML (design-114 §2).

The core parses YAML 1.2; the rest of the repository uses PyYAML, which is
YAML 1.1. The two disagree on plain scalars such as ``on``/``yes``/``no``, on
merge keys and on timestamps. Every ACS document in the repository must load
to the same data under both, so that a file means the same thing to the core
and to the Python tools that read it. A divergence is fixed in the file
(usually by quoting), never special-cased in either loader.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from grounded_agency import _core

ROOT = Path(__file__).resolve().parents[1]

# GitHub Actions workflows are not ACS documents: they are read by GitHub's
# own YAML 1.1 loader (where `on:` is the trigger key), so parity with the
# core is neither expected nor wanted there.
NOT_ACS_DOCUMENTS = (".github/",)


def _tracked_yaml_files() -> list[str]:
    """Tracked YAML files, or none outside a git checkout (e.g. an sdist)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "*.yaml", "*.yml"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    files = [f for f in out.split("\0") if f]
    return [f for f in files if not f.startswith(NOT_ACS_DOCUMENTS)]


def _as_json(value: Any) -> Any:
    """PyYAML data as the core would represent it, so equality is meaningful."""
    return json.loads(json.dumps(value))


ACS_FILES = _tracked_yaml_files()


@pytest.mark.skipif(not ACS_FILES, reason="not a git checkout")
def test_repository_has_acs_yaml_files() -> None:
    assert len(ACS_FILES) > 100


@pytest.mark.parametrize("relpath", ACS_FILES)
def test_core_matches_pyyaml(relpath: str) -> None:
    path = ROOT / relpath
    with open(path, encoding="utf-8") as f:
        expected = _as_json(yaml.safe_load(f))
    actual = _core.load_yaml(str(path), _core.ONTOLOGY_MAX_BYTES)
    assert actual == expected


class TestGuards:
    """The core enforces safe_yaml's guards and the ones PyYAML lacks."""

    def test_refuses_symlink(self, tmp_path: Path) -> None:
        real = tmp_path / "real.yaml"
        real.write_text("a: 1\n")
        link = tmp_path / "link.yaml"
        os.symlink(real, link)
        with pytest.raises(ValueError, match="symlink"):
            _core.load_yaml(str(link))

    def test_size_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "big.yaml"
        f.write_text("a: " + "x" * 64 + "\n")
        with pytest.raises(ValueError, match="size limit"):
            _core.load_yaml(str(f), 16)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _core.load_yaml(str(tmp_path / "absent.yaml"))

    def test_directory_is_os_error(self, tmp_path: Path) -> None:
        # Same exception class safe_yaml raises, so OSError handlers still match.
        with pytest.raises(IsADirectoryError):
            _core.load_yaml(str(tmp_path))

    def test_validator_raises_load_errors_like_load_yaml(self, tmp_path: Path) -> None:
        """Validation entry points raise the OSError subclass load_yaml
        raises for a file it cannot read, and ValueError for bad content."""
        ontology = ROOT / "schemas" / "capability_ontology.yaml"
        absent = tmp_path / "absent.yaml"
        bad = tmp_path / "bad.yaml"
        bad.write_text("a: 1\na: 2\n")

        with pytest.raises(FileNotFoundError, match="cannot load ontology"):
            _core.Validator(absent, ROOT)
        with pytest.raises(IsADirectoryError):
            _core.Validator(tmp_path, ROOT)
        with pytest.raises(ValueError, match="duplicate mapping key"):
            _core.Validator(bad, ROOT)

        validator = _core.Validator(ontology, ROOT)
        with pytest.raises(FileNotFoundError, match="cannot load workflow catalog"):
            validator.validate_file(absent)
        with pytest.raises(IsADirectoryError):
            validator.validate_file(tmp_path)
        with pytest.raises(ValueError, match="duplicate mapping key"):
            validator.validate_file(bad)

        with pytest.raises(FileNotFoundError):
            _core.validate_catalog(absent, ontology, ROOT)
        with pytest.raises(FileNotFoundError):
            _core.validate_catalog(bad, absent, ROOT)

    def test_rejects_duplicate_keys(self) -> None:
        # PyYAML silently keeps the last value; YAML 1.2 forbids duplicates.
        with pytest.raises(ValueError, match="duplicate mapping key"):
            _core.load_yaml_str("a: 1\na: 2\n")

    def test_bounds_alias_expansion(self) -> None:
        doc = "a0: &a0 [x, x, x, x, x, x, x, x, x, x]\n"
        for i in range(1, 8):
            refs = ", ".join([f"*a{i - 1}"] * 10)
            doc += f"a{i}: &a{i} [{refs}]\n"
        with pytest.raises(ValueError, match="anchors and aliases copy more than"):
            _core.load_yaml_str(doc)

    def test_yaml_1_2_scalars(self) -> None:
        assert _core.load_yaml_str("on: yes\n") == {"on": "yes"}
