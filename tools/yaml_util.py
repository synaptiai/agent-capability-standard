"""Size-limited YAML loading for tools/ scripts (SEC-003).

Standalone mirror of ``grounded_agency/utils/safe_yaml.py`` that avoids
import dependencies on the ``grounded_agency`` package so ``tools/``
scripts work without installing the package.

IMPORTANT: The canonical source is ``grounded_agency/utils/safe_yaml.py``.
Both files MUST expose the same public API (``safe_yaml_load``,
``YAMLSizeExceededError``, ``DEFAULT_MAX_BYTES``, ``ONTOLOGY_MAX_BYTES``)
with identical behaviour.  When editing either file, update the other
to match.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Default limits
DEFAULT_MAX_BYTES: int = 1 * 1024 * 1024  # 1 MB
ONTOLOGY_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB


class YAMLSizeExceededError(Exception):
    """Raised when a YAML file exceeds the allowed size limit."""

    def __init__(self, path: Path, size: int, max_size: int) -> None:
        self.path = path
        self.size = size
        self.max_size = max_size
        super().__init__(
            f"YAML file exceeds size limit: {path} is {size:,} bytes "
            f"(limit: {max_size:,} bytes)"
        )


def safe_yaml_load(
    path: str | Path,
    max_size: int = DEFAULT_MAX_BYTES,
) -> Any:
    """Load a YAML file with a file-size check.

    Args:
        path: Path to the YAML file.
        max_size: Maximum allowed file size in bytes.

    Returns:
        Parsed YAML content.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the path is a symlink (SEC-006).
        YAMLSizeExceededError: If the file exceeds *max_size*.
        yaml.YAMLError: If the file is not valid YAML.
    """
    path = Path(path)

    if path.is_symlink():
        raise ValueError(f"Refusing to follow symlink: {path}")

    # Open first, then fstat() on the fd to avoid TOCTOU between stat() and open().
    # If the file does not exist, open() raises FileNotFoundError directly.
    with open(path, encoding="utf-8") as f:
        file_size = os.fstat(f.fileno()).st_size
        if file_size > max_size:
            raise YAMLSizeExceededError(path, file_size, max_size)
        return yaml.safe_load(f)
