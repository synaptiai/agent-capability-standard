#!/usr/bin/env python3
"""Documentation link validator: every relative reference must resolve.

Markdown cross-references are the one kind of reference in this repository that
nothing checked. `validate_skill_refs.py` covers file paths inside SKILL.md
dependency sections and `validate_transform_refs.py` covers `mapping_ref`
paths, but an ordinary `[text](../path/to.md)` in any document could point at
nothing and CI stayed green -- which is how
`docs/integrations/claude_agent_sdk.md` came to cite a `comparisons/` directory
that has never existed.

The failure mode this prevents is deletion drift: a document with inbound
references is removed, the references are not updated, and the break is
invisible until a reader follows one. The corresponding failure mode *of* such
a validator is silence -- under-reporting looks exactly like a clean run -- so
the scanning below is deliberately built to see every link form CommonMark
allows rather than the one form that is most common.

Checked:

* inline links -- ``[text](path)``, including titles ``[t](p "Title")``,
  angle-bracket destinations ``[t](<p>)``, images ``![alt](p)``, and links whose
  text contains nested brackets such as a badge ``[![alt](img)](p)``
* reference definitions -- ``[label]: path``
* reference usages -- ``[text][label]``, checked for a defined label
* backtick code spans naming a repository file -- ``` `docs/thing.md` ``` --
  in the index documents only, see below

Inline links are found by scanning for ``](`` and reading the destination
forward, rather than by anchoring a regex on the opening ``[``. Anchoring on
``[`` cannot see a badge: ``\\[[^\\]]*\\]`` consumes ``[![alt]`` and matches the
*image* destination, leaving the outer link unchecked. In this repository that
would have left the README's links to ``LICENSE``, ``spec/STANDARD-v1.0.0.md``
and ``CHANGELOG.md`` unvalidated.

Code spans are checked **only in the index documents** listed in ``INDEX_DOCS``,
and that restriction is load-bearing rather than timid. Measured across the
repository, code-span checking finds ~109 "broken" paths, and essentially none
are defects: prose cites paths relative to a package (``capabilities/registry.py``
under ``grounded_agency/``) or a skill directory (``schemas/output_schema.yaml``,
already covered by ``validate_skill_refs.py``); tutorials name files the reader
is about to create; and the NIST profile's roadmap names deliverables that do
not exist *yet*, which is the point of a roadmap. In the index documents the
count is 22 with zero false positives, because those tables exist to point at
real files. A validator that cries wolf trains people to ignore it. (All 22 come
from ``CLAUDE.md`` today; ``README.md`` carries no code-span paths and is listed
so its tables are covered if it grows any.)

Files are enumerated with ``git ls-files`` so results depend only on the
committed tree. Walking the filesystem instead makes the numbers depend on
whichever untracked drafts happen to be present, which is how an earlier
revision of this file reported counts that CI could not reproduce.

Not checked (deliberately):

* absolute URLs (``http://``, ``https://``, ``mailto:``) -- reaching the
  network would make CI depend on third-party uptime
* anchors within a file (``#section``) -- the fragment is stripped and only the
  file part is resolved; validating heading anchors is a different check
* paths inside fenced or indented code blocks and HTML comments -- illustrative,
  not references

Exit status is 0 when every reference resolves, 1 otherwise.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

# Directories that are not part of the live documentation set. `_archive/` holds
# frozen v1 material whose internal links intentionally point at files removed in
# the migration; rewriting them would falsify an archive.
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

# ``[label]: target`` at the start of a line, with an optional title.
REFERENCE_DEFINITION = re.compile(
    r"^ {0,3}\[(?P<label>[^\]]+)\]:\s*<?(?P<target>[^>\s#]+)(?:#\S*)?>?"
    r"(?:\s+[\"'(].*)?\s*$",
    re.MULTILINE,
)
# ``[text][label]`` -- a usage. An empty label is the shortcut form ``[label][]``.
REFERENCE_USAGE = re.compile(r"(?<!\!)\[(?P<text>[^\]]+)\]\[(?P<label>[^\]]*)\]")
# A single-backtick code span, e.g. `docs/guides/THING.md`.
CODE_SPAN = re.compile(r"(?<!`)`(?P<target>[^`\n]+)`(?!`)")
# An HTML comment, which may span lines.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# A fence opener/closer: up to three leading spaces, then >=3 backticks or tildes.
FENCE_LINE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")

# Documents whose code-span paths are navigational: they exist to point at real
# files, so a path in one that does not resolve is a defect rather than an
# illustration. See the module docstring for why this is not applied repo-wide.
# Entries MUST be root-level (no path separator) -- code spans resolve from ROOT,
# which only coincides with file-relative resolution at the repository root.
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


def strip_uncheckable(text: str) -> tuple[str, int | None]:
    """Blank out code blocks and HTML comments, preserving line numbering.

    Returns the blanked text and the 1-indexed line of an unclosed fence, if
    any. Fences are matched line by line rather than with a single regex: a
    regex with a lazy body pairs an *unclosed* fence with some later fence line,
    blanking the prose between them and silently suppressing whatever links it
    contained. CommonMark also allows a closing fence longer than its opener and
    forbids an info string on the closer, neither of which a symmetric
    backreference expresses.

    An unclosed fence is reported rather than tolerated. Per CommonMark it runs
    to end of document, so everything after it is correctly treated as code --
    but that means one stray fence silently removes the rest of a file from this
    check. Since an unclosed fence is nearly always a typo, saying so converts
    the silence into a visible error.
    """
    lines = text.split("\n")
    out: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    fence_line: int | None = None

    for lineno, line in enumerate(lines, start=1):
        match = FENCE_LINE.match(line)
        if fence_char is None:
            # Outside a fence: an indented block (4+ spaces) is also code.
            if match:
                fence_char = match.group("fence")[0]
                fence_len = len(match.group("fence"))
                fence_line = lineno
                out.append("")
                continue
            if line.startswith("    ") and line.strip():
                out.append("")
                continue
            out.append(line)
        else:
            # Inside a fence: close only on the same char, at least as long,
            # with nothing after it.
            if (
                match
                and match.group("fence")[0] == fence_char
                and len(match.group("fence")) >= fence_len
                and not match.group("info").strip()
            ):
                fence_char = None
                fence_len = 0
                fence_line = None
            out.append("")

    # An unclosed fence runs to EOF, which the loop above already produces.
    blanked = HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), "\n".join(out))
    return blanked, fence_line


def iter_inline_links(text: str) -> list[tuple[int, str]]:
    """Find ``[text](destination)`` links, returning ``(offset, destination)``.

    Scans for ``](`` and reads the destination forward. Anchoring on the opening
    bracket instead would make nested brackets in the link text -- a badge, an
    image inside a link -- consume the wrong span and check the inner
    destination while ignoring the outer one.
    """
    found: list[tuple[int, str]] = []
    for opener in re.finditer(r"\]\(", text):
        i = opener.end()
        n = len(text)
        while i < n and text[i] in " \t\n":
            i += 1
        if i >= n:
            continue

        if text[i] == "<":
            close = text.find(">", i + 1)
            if close == -1:
                continue
            destination = text[i + 1 : close]
            i = close + 1
        else:
            start = i
            while i < n and text[i] not in " \t\n)":
                i += 1
            destination = text[start:i]

        # Whatever follows must be an optional title then ')'.
        while i < n and text[i] in " \t\n":
            i += 1
        if i < n and text[i] in "\"'(":
            closer = {'"': '"', "'": "'", "(": ")"}[text[i]]
            i = text.find(closer, i + 1)
            if i == -1:
                continue
            i += 1
            while i < n and text[i] in " \t\n":
                i += 1
        if i >= n or text[i] != ")":
            continue

        if destination:
            found.append((opener.start(), destination))
    return found


def iter_markdown_files() -> list[Path]:
    """Markdown files in the committed tree, sorted.

    Uses ``git ls-files`` so a run depends only on what is committed. Untracked
    drafts sitting in the working tree would otherwise change the counts and
    make local results disagree with CI.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "*.md"],
            capture_output=True,
            check=True,
            text=True,
        )
        paths = [ROOT / p for p in result.stdout.split("\0") if p]
        if paths:
            return sorted(
                p
                for p in paths
                if p.is_file()
                and not any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts)
            )
    except (OSError, subprocess.CalledProcessError):
        pass  # Not a git checkout (or git unavailable) -- fall back to a walk.

    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)
    )


def is_external(target: str) -> bool:
    """Whether a reference target points outside the repository."""
    return target.startswith(EXTERNAL_PREFIXES)


def is_checkable(target: str) -> bool:
    """Whether a target names a repository path this tool should resolve."""
    if not target or is_external(target):
        return False
    # Pure anchors and template placeholders such as {path} or $VAR.
    return not target.startswith(("#", "{", "<", "$"))


def line_of(text: str, index: int) -> int:
    """1-indexed line number of a character offset."""
    return text.count("\n", 0, index) + 1


def resolve(source: Path, target: str) -> Path:
    """Resolve a link target relative to the file containing it.

    A target beginning with ``/`` is treated as repository-root-relative, which
    is how such links render on GitHub. Percent-escapes are decoded so a link to
    ``my%20file.md`` resolves against ``my file.md`` on disk.
    """
    decoded = unquote(target)
    if decoded.startswith("/"):
        return ROOT / decoded.lstrip("/")
    return source.parent / decoded


def check_file(path: Path) -> tuple[list[str], int]:
    """Return ``(error messages, references checked)`` for *path*."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ([f"{path.relative_to(ROOT)}: could not read ({exc})"], 0)

    text, unclosed_fence = strip_uncheckable(raw)
    # Inline code spans are captured before being blanked: they are checked as
    # file references in the index documents, but must not be scanned for links
    # or labels. A regex character class such as `[a-zA-Z_][a-zA-Z0-9_]*`
    # contains "][" and would otherwise parse as a reference usage.
    code_spans = list(CODE_SPAN.finditer(text))
    prose = CODE_SPAN.sub(lambda m: " " * len(m.group(0)), text)
    rel = path.relative_to(ROOT)
    errors: list[str] = []
    if unclosed_fence is not None:
        errors.append(
            f"{rel}:{unclosed_fence}: unclosed code fence -- everything after "
            "this line is treated as code and its references go unchecked"
        )
    checked = 0
    seen: set[tuple[int, str, str]] = set()

    def record(offset: int, target: str, kind: str) -> None:
        nonlocal checked
        if not is_checkable(target):
            return
        lineno = line_of(text, offset)
        if (lineno, target, kind) in seen:
            return
        seen.add((lineno, target, kind))
        checked += 1

        resolved = ROOT / unquote(target) if kind == "path" else resolve(path, target)
        if not resolved.exists():
            label = "broken link" if kind == "link" else "broken file reference"
            errors.append(
                f"{rel}:{lineno}: {label} {target!r} -> {resolved} does not exist"
            )

    for offset, destination in iter_inline_links(prose):
        record(offset, destination.split("#", 1)[0], "link")

    labels: set[str] = set()
    for match in REFERENCE_DEFINITION.finditer(prose):
        labels.add(match.group("label").strip().lower())
        record(match.start(), match.group("target"), "link")

    # A usage naming no definition is a broken reference of a different kind:
    # the target file may be fine, but the link renders as literal text.
    for match in REFERENCE_USAGE.finditer(prose):
        label = (match.group("label") or match.group("text")).strip().lower()
        checked += 1
        if label not in labels:
            errors.append(
                f"{rel}:{line_of(text, match.start())}: undefined link label "
                f"[{match.group('label') or match.group('text')}] -- no matching "
                "[label]: definition in this file"
            )

    if str(rel) in INDEX_DOCS:
        for match in code_spans:
            target = match.group("target").strip()
            if is_file_reference(target):
                record(match.start(), target, "path")

    return errors, checked


def main() -> int:
    assert all("/" not in name for name in INDEX_DOCS), (
        "INDEX_DOCS entries must be root-level: code spans resolve from the "
        "repository root, which only coincides with file-relative resolution "
        "for files at the root."
    )

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
