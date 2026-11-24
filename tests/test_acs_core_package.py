"""The TypeScript package (packages/acs-core/) is in step with the repository.

The package's own tests run with `npm test` there. What is checked here is
what belongs to the repository: the files it copies, and that the Standard
Agents binding uses the package rather than copies of its modules.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "acs-core"
BINDING = ROOT / "examples" / "standard_agents"


def test_license_and_notice_are_the_repositorys() -> None:
    for name in ("LICENSE", "NOTICE"):
        assert (PACKAGE / name).read_bytes() == (ROOT / name).read_bytes(), name


def test_node_version_is_the_sites() -> None:
    assert (PACKAGE / ".nvmrc").read_text() == (ROOT / "site" / ".nvmrc").read_text()


def test_the_package_has_no_runtime_dependency() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text("utf-8"))
    assert manifest["name"] == "@synaptiai/acs-core"
    assert manifest["license"] == "Apache-2.0"
    assert "dependencies" not in manifest
    assert set(manifest["files"]) == {"dist", "README.md", "LICENSE", "NOTICE"}


def test_the_binding_uses_the_package() -> None:
    manifest = json.loads((BINDING / "package.json").read_text("utf-8"))
    assert (
        manifest["dependencies"]["@synaptiai/acs-core"]
        == "file:../../packages/acs-core"
    )
    # The modules the package holds are not kept in the binding as well.
    for moved in ("ontology.gen.ts", "canonical.ts", "flags.ts", "redact.ts"):
        assert not (BINDING / "src" / "acs" / moved).exists(), moved
