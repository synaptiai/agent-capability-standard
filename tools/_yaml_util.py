"""Size-limited YAML loading for tools/ scripts (SEC-003).

Standalone version that avoids import dependencies on the
``grounded_agency`` package.  Mirrors the API of
``grounded_agency.utils.safe_yaml`` so call-sites look identical.
"""

from __future__ import annotations

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
        YAMLSizeExceededError: If the file exceeds *max_size*.
        yaml.YAMLError: If the file is not valid YAML.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    file_size = path.stat().st_size
    if file_size > max_size:
        raise YAMLSizeExceededError(path, file_size, max_size)

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
