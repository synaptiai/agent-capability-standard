#!/usr/bin/env python3
"""RFC validator: validates spec/RFC-*.md structure and references.

`spec/GOVERNANCE.md` requires community proposals to arrive as RFCs carrying
motivation, alternatives, a backward-compatibility analysis, and conformance
test updates. Nothing enforced that, so an RFC could omit any of it and still
be merged.

Validates:
1) Filename follows RFC-<4 digits>-<kebab-slug>.md and numbers are unique
2) Title line matches the filename's RFC number
3) Status / Target / Date metadata are present and well-formed
4) Every section GOVERNANCE requires is present and non-empty
5) Repository paths referenced by the RFC actually exist
6) An Accepted RFC records its review window, of at least 14 days and ending
   on its Date, and who accepted it: at least one maintainer named in
   .github/CODEOWNERS (spec/GOVERNANCE.md, "Decision-making"). The RFCs
   accepted before that rule (ACCEPTED_BEFORE_REVIEW_RULE) are exempt.

Usage:
- python3 tools/validate_rfcs.py
- python3 tools/validate_rfcs.py --verbose
- python3 tools/validate_rfcs.py --rfc-dir path/to/fixtures

"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RFC_DIR = ROOT / "spec"

FILENAME_PATTERN = re.compile(r"^RFC-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
TITLE_PATTERN = re.compile(r"^# RFC-(\d{4}):\s*\S")
STATUS_PATTERN = re.compile(
    r"^\*\*Status:\*\*\s*(Draft|Accepted|Rejected|Superseded)\s*$"
)
TARGET_PATTERN = re.compile(r"^\*\*Target:\*\*\s*\S")
DATE_PATTERN = re.compile(r"^\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})\s*$")
REVIEW_WINDOW_PATTERN = re.compile(
    r"^\*\*Review window:\*\*\s*(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\s*$"
)
ACCEPTED_BY_PATTERN = re.compile(r"^\*\*Accepted by:\*\*\s*(.*?)\s*$")
HANDLE_PATTERN = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")

# spec/GOVERNANCE.md: an RFC is open for review for at least this many days
# before it is Accepted, and acceptance needs this many maintainers.
MIN_REVIEW_DAYS = 14
MIN_APPROVERS = 1
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"

# Accepted before the review rule existed; they record neither line.
ACCEPTED_BEFORE_REVIEW_RULE = frozenset(
    {"0001", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010"}
)

# spec/GOVERNANCE.md: "Changes require: Motivation, Alternatives, Backward
# compatibility analysis, Conformance test updates."
REQUIRED_SECTIONS = [
    "Summary",
    "Motivation",
    "Goals",
    "Non-goals",
    "Key decisions",
    "Backward compatibility",
    "Conformance test updates",
    "Alternatives considered",
    "Open questions",
]

# Inline code spans that look like repository paths.
PATH_PATTERN = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|yaml|yml|json|md))`")

# Fenced code blocks, so an example inside one is never read as document
# structure: a `## Heading` in a fence would otherwise satisfy the
# required-section check, and a path in a YAML sample would be checked for
# existence.
FENCE_PATTERN = re.compile(r"^(?P<fence>```+|~~~+).*?^(?P=fence)\s*$", re.M | re.S)


def strip_fenced_blocks(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbering."""

    def blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return FENCE_PATTERN.sub(blank, text)


def parse_sections(text: str) -> dict[str, str]:
    """Map each `## Heading` to the body text beneath it."""
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(body).strip()
            current = line[3:].strip()
            body = []
        elif current is not None:
            body.append(line)

    if current is not None:
        sections[current] = "\n".join(body).strip()

    return sections


def header_lines(lines: list[str]) -> list[str]:
    """The lines before the first `## ` section: the title and metadata."""
    header: list[str] = []
    for line in lines:
        if line.startswith("## "):
            break
        header.append(line)
    return header


def maintainers(codeowners: Path = CODEOWNERS) -> set[str]:
    """The handles .github/CODEOWNERS names, lower-cased."""
    try:
        text = codeowners.read_text(encoding="utf-8")
    except OSError:
        return set()
    handles: set[str] = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        for token in line.split()[1:]:
            if HANDLE_PATTERN.fullmatch(token):
                handles.add(token.lower())
    return handles


def validate_review(
    lines: list[str], errors: list[str], name: str, owners: set[str]
) -> None:
    """An Accepted RFC records its review window and who accepted it."""
    header = header_lines(lines)
    status = next((m for line in header if (m := STATUS_PATTERN.match(line))), None)
    if status is None or status.group(1) != "Accepted":
        return
    number_match = FILENAME_PATTERN.match(name)
    number = number_match.group(1) if number_match else None
    window_line = next(
        (line for line in header if line.startswith("**Review window:**")), None
    )
    accepted_line = next(
        (line for line in header if line.startswith("**Accepted by:**")), None
    )
    if (
        number in ACCEPTED_BEFORE_REVIEW_RULE
        and window_line is None
        and accepted_line is None
    ):
        return

    window = REVIEW_WINDOW_PATTERN.match(window_line) if window_line else None
    if window is None:
        errors.append(
            f"[{name}] An Accepted RFC needs a '**Review window:** YYYY-MM-DD to "
            "YYYY-MM-DD' line in the header"
        )
    else:
        try:
            opened, accepted = (date.fromisoformat(g) for g in window.groups())
        except ValueError:
            errors.append(f"[{name}] Review window has an invalid date")
        else:
            days = (accepted - opened).days
            if days < MIN_REVIEW_DAYS:
                errors.append(
                    f"[{name}] Review window is {days} days; acceptance needs at "
                    f"least {MIN_REVIEW_DAYS}"
                )
            date_value = next(
                (m.group(1) for line in header if (m := DATE_PATTERN.match(line))),
                None,
            )
            if date_value is not None and date_value != window.group(2):
                errors.append(
                    f"[{name}] Review window ends {window.group(2)}, but the "
                    f"RFC's Date (its acceptance date) is {date_value}"
                )

    accepted_by = ACCEPTED_BY_PATTERN.match(accepted_line) if accepted_line else None
    handles = HANDLE_PATTERN.findall(accepted_by.group(1)) if accepted_by else []
    if not handles:
        errors.append(
            f"[{name}] An Accepted RFC needs an '**Accepted by:** @<login>' line "
            "in the header"
        )
        return
    approvers = {handle.lower() for handle in handles}
    unknown = sorted(approvers - owners)
    if unknown:
        errors.append(
            f"[{name}] Accepted by {', '.join(unknown)}, who .github/CODEOWNERS "
            "does not name as a maintainer"
        )
    if len(approvers & owners) < MIN_APPROVERS:
        errors.append(
            f"[{name}] Acceptance needs at least {MIN_APPROVERS} maintainer(s) "
            "named in .github/CODEOWNERS"
        )


def validate_metadata(lines: list[str], errors: list[str], name: str) -> None:
    """Title, Status, Target and Date sit in the header, before the first section."""
    header = header_lines(lines)

    title_match = next(
        (TITLE_PATTERN.match(line) for line in header if TITLE_PATTERN.match(line)),
        None,
    )
    if title_match is None:
        errors.append(f"[{name}] Missing '# RFC-NNNN: <title>' heading")
    else:
        file_number = FILENAME_PATTERN.match(name)
        if file_number and title_match.group(1) != file_number.group(1):
            errors.append(
                f"[{name}] Title says RFC-{title_match.group(1)} but the filename "
                f"says RFC-{file_number.group(1)}"
            )

    for label, pattern in (
        ("Status", STATUS_PATTERN),
        ("Target", TARGET_PATTERN),
        ("Date", DATE_PATTERN),
    ):
        if not any(pattern.match(line) for line in header):
            errors.append(
                f"[{name}] Missing or malformed '**{label}:**' line in the header"
            )


def validate_sections(text: str, errors: list[str], name: str) -> None:
    """Every section GOVERNANCE requires is present and carries content."""
    sections = parse_sections(text)

    for heading in REQUIRED_SECTIONS:
        if heading not in sections:
            errors.append(f"[{name}] Missing required section '## {heading}'")
        elif not sections[heading]:
            errors.append(f"[{name}] Section '## {heading}' is empty")


def validate_referenced_paths(text: str, errors: list[str], name: str) -> None:
    """Repository paths cited by an RFC must exist (no phantom references)."""
    for match in sorted(set(PATH_PATTERN.findall(text))):
        # Only check things that look repo-rooted; bare filenames in prose
        # (e.g. `run.yaml`) are not necessarily paths.
        if "/" not in match:
            continue
        if not (ROOT / match).exists():
            errors.append(f"[{name}] References path that does not exist: {match}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate spec/RFC-*.md structure and references"
    )
    parser.add_argument("--verbose", action="store_true", help="Print each RFC")
    parser.add_argument(
        "--rfc-dir",
        default=None,
        help="Override the directory searched for RFC-*.md files.",
    )
    parser.add_argument(
        "--codeowners",
        default=None,
        help="Override the CODEOWNERS file that names the maintainers.",
    )
    args = parser.parse_args()

    rfc_dir = Path(args.rfc_dir) if args.rfc_dir else DEFAULT_RFC_DIR
    owners = maintainers(Path(args.codeowners) if args.codeowners else CODEOWNERS)

    errors: list[str] = []
    seen_numbers: dict[str, str] = {}
    validated_count = 0

    rfc_files = sorted(rfc_dir.glob("RFC-*.md"))
    if not rfc_files:
        print(f"WARNING: No RFC files found in {rfc_dir}")
        sys.exit(0)

    for path in rfc_files:
        name = path.name

        if args.verbose:
            print(f"Validating: {name}")

        filename_match = FILENAME_PATTERN.match(name)
        if filename_match is None:
            errors.append(
                f"[{name}] Filename must match RFC-<4 digits>-<kebab-slug>.md"
            )
        else:
            number = filename_match.group(1)
            if number in seen_numbers:
                errors.append(
                    f"[{name}] Duplicate RFC number {number}; already used by "
                    f"{seen_numbers[number]}"
                )
            else:
                seen_numbers[number] = name

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"[{name}] Could not read the file: {exc}")
            continue

        prose = strip_fenced_blocks(text)
        validate_metadata(prose.splitlines(), errors, name)
        validate_sections(prose, errors, name)
        validate_referenced_paths(prose, errors, name)
        validate_review(prose.splitlines(), errors, name, owners)
        validated_count += 1

    if errors:
        print("RFC VALIDATION FAIL:")
        for error in errors:
            print(f"  - {error}")
        print(f"\nValidated {validated_count} RFCs with {len(errors)} errors")
        sys.exit(1)

    print(f"RFC VALIDATION PASS: {validated_count} RFCs validated")


if __name__ == "__main__":
    main()
