#!/usr/bin/env python3
"""Documentation link validator: every relative link must resolve to a real file.

Markdown cross-references are the one kind of reference in this repository that
nothing checked. `validate_skill_refs.py` covers file paths inside SKILL.md
dependency sections and `validate_transform_refs.py` covers `mapping_ref`
paths, but an ordinary `[text](../path/to.md)` in any document could point at
nothing and CI stayed green -- which is how
`docs/integrations/claude_agent_sdk.md` came to cite a `comparisons/` directory
that has never existed.

The failure mode this prevents is deletion drift: a document with inbound
references is removed, the references are not updated, and the break is
invisible until a reader follows one.

Checked:

* inline links -- ``[text](path)``
* reference definitions -- ``[label]: path``
* backtick code spans that name a repository file -- ``` `docs/thing.md` ```

The third case matters more than it looks. Of the nine documents citing
``docs/proposals/OASF_SAFETY_EXTENSIONS.md``, only two do so as Markdown links;
the rest name it in a code span. A link-only check would call a deletion clean
while seven references dangled.

Code spans are checked **only in the index documents** listed in ``INDEX_DOCS``,
and that restriction is load-bearing rather than timid. Measured across the
repository, code-span checking finds 104 "broken" paths, and essentially none
are defects: prose cites paths relative to a package (``capabilities/registry.py``
under ``grounded_agency/``) or a skill directory (``schemas/output_schema.yaml``,
already covered by ``validate_skill_refs.py``); tutorials name files the reader
is about to create; and the NIST profile's roadmap names deliverables that do
not exist *yet*, which is the point of a roadmap. In the index documents the
count is 22 with zero false positives, because those tables exist to point at
real files. A validator that cries wolf trains people to ignore it.

Not checked (deliberately):

* absolute URLs (``http://``, ``https://``, ``mailto:``) -- reaching the
  network would make CI depend on third-party uptime
* anchors within a file (``#section``) -- the fragment is stripped and only the
  file part is resolved; validating heading anchors is a different check
* paths inside fenced code blocks -- those are illustrative, not references

Exit status is 0 when every link resolves, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories that are not part of the documentation set.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "_archive",
    ".entire",
    ".trail",
    ".claude",
    "build",
    "dist",
}

# ``[text](target)`` -- target ends at whitespace, ')' or '#'.
INLINE_LINK = re.compile(r"\[[^\]]*\]\(\s*(?P<target>[^)\s#]+)(?:#[^)]*)?\s*\)")
# ``[label]: target`` at the start of a line.
REFERENCE_LINK = re.compile(
    r"^\s{0,3}\[[^\]]+\]:\s*<?(?P<target>[^>\s#]+)(?:#\S*)?>?\s*$", re.MULTILINE
)
# Fenced code blocks, so illustrative paths inside them are not treated as
# references. Matches the closing fence of the same length, like the RFC
# validator does.
FENCE = re.compile(r"^(?P<fence>```+|~~~+).*?^(?P=fence)\s*$", re.M | re.S)
# A single-backtick code span, e.g. `docs/guides/THING.md`.
CODE_SPAN = re.compile(r"(?<!`)`(?P<target>[^`\n]+)`(?!`)")

EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")

# Documents whose code-span paths are navigational: they exist to point at real
# files, so a path in one that does not resolve is a defect rather than an
# illustration. See the module docstring for why this is not applied repo-wide.
INDEX_DOCS = {"CLAUDE.md", "README.md"}

# Extensions a code span must end in to be treated as a file reference.
CHECKED_SUFFIXES = (".md", ".yaml", ".yml", ".py", ".json", ".toml", ".txt")
# Characters marking a path as illustrative rather than literal --
# `skills/<name>/SKILL.md`, `schemas/profiles/*.yaml`, `{path}/file.md`.
PLACEHOLDER_CHARS = set("<>{}*?|$ ")


def is_file_reference(text: str) -> bool:
    """Whether a code span names a concrete repository file.

    Conservative by construction: a false positive here turns CI red on a
    document that was never wrong, which would train people to ignore the
    check. Anything ambiguous is skipped.
    """
    if "/" not in text or not text.endswith(CHECKED_SUFFIXES):
        return False
    if PLACEHOLDER_CHARS & set(text):
        return False
    if text.startswith(EXTERNAL_PREFIXES) or text.startswith(("~", "/")):
        return False
    # Command fragments such as `python tools/x.py` are not bare paths.
    return len(text.split()) == 1


def strip_fenced_blocks(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbering."""

    def blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return FENCE.sub(blank, text)


def iter_markdown_files() -> list[Path]:
    """Every Markdown file in the documentation set, sorted."""
    files = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return sorted(files)


def is_external(target: str) -> bool:
    """Whether a link target points outside the repository."""
    return target.startswith(EXTERNAL_PREFIXES)


def line_of(text: str, index: int) -> int:
    """1-indexed line number of a character offset."""
    return text.count("\n", 0, index) + 1


def resolve(source: Path, target: str) -> Path:
    """Resolve a link target relative to the file containing it.

    A target beginning with ``/`` is treated as repository-root-relative, which
    is how such links render on GitHub.
    """
    if target.startswith("/"):
        return ROOT / target.lstrip("/")
    return source.parent / target


def iter_references(text: str, *, check_code_spans: bool) -> list[tuple[int, str, str]]:
    """Yield ``(line, target, kind)`` for every checkable reference in *text*.

    ``kind`` is ``"link"`` (resolved relative to the containing file, as
    Markdown renders it) or ``"path"`` (a code span, resolved from the
    repository root, which is how such paths are written here).
    """
    found: list[tuple[int, str, str]] = []
    seen: set[tuple[int, str]] = set()

    for pattern in (INLINE_LINK, REFERENCE_LINK):
        for match in pattern.finditer(text):
            target = match.group("target").strip()
            if not target or is_external(target):
                continue
            # Skip pure anchors and template placeholders such as {path}.
            if target.startswith(("#", "{", "<", "$")):
                continue
            key = (line_of(text, match.start()), target)
            if key not in seen:
                seen.add(key)
                found.append((key[0], target, "link"))

    if not check_code_spans:
        return found

    for match in CODE_SPAN.finditer(text):
        target = match.group("target").strip()
        if not is_file_reference(target):
            continue
        key = (line_of(text, match.start()), target)
        if key not in seen:
            seen.add(key)
            found.append((key[0], target, "path"))

    return found


def check_file(path: Path) -> tuple[list[str], int]:
    """Return ``(error messages, references checked)`` for *path*."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ([f"{path.relative_to(ROOT)}: could not read ({exc})"], 0)

    text = strip_fenced_blocks(raw)
    references = iter_references(
        text, check_code_spans=str(path.relative_to(ROOT)) in INDEX_DOCS
    )
    errors: list[str] = []

    for lineno, target, kind in references:
        resolved = ROOT / target if kind == "path" else resolve(path, target)
        if not resolved.exists():
            label = "broken link" if kind == "link" else "broken file reference"
            errors.append(
                f"{path.relative_to(ROOT)}:{lineno}: {label} "
                f"{target!r} -> {resolved} does not exist"
            )
    return errors, len(references)


def main() -> int:
    files = iter_markdown_files()
    errors: list[str] = []
    reference_count = 0

    for path in files:
        file_errors, count = check_file(path)
        errors.extend(file_errors)
        reference_count += count

    if errors:
        print(f"FAIL: {len(errors)} broken documentation reference(s)\n")
        for error in errors:
            print(f"  - {error}")
        print(
            "\nA reference whose target does not exist is a claim without "
            "evidence.\nUpdate the reference, or restore the file it names."
        )
        return 1

    print(f"OK: {reference_count} reference(s) across {len(files)} file(s) resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
