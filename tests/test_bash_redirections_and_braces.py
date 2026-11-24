"""The SDK Bash classifier reads redirections and braces as bash does
(STANDARD 1.2.0 sections 5.18.3, 5.18.8, 4.4.2).

Security round 4, batch 2:

1. bash's `{varname}>file` (also `<`, `>>`, `>&N`) opens a descriptor of 10
   or more and assigns its number to the variable. On a builtin (`echo`,
   `printf`, `pwd`) bash does it in the shell itself, so `echo hi
   {PATH}>/dev/null; ls` runs `./10/ls`, a program the repository ships,
   and `{HOME}` makes git read `./10/.gitconfig`. The classifier kept
   `{PATH}` as an argument and called the line `observe`. A `{...}` word
   right before a redirection now takes the worst case.
2. `>&WORD` duplicates a descriptor only when WORD is ASCII digits; any
   other WORD is `&>WORD`, a file. `str.isdigit` takes any Unicode digit,
   so `cat /etc/hostname >&١` (U+0661) wrote a file classified `observe`.
3. In a double-byte locale bash can read the last byte of a UTF-8
   character and the next ASCII byte as one character. The round 3 fix
   refused the backslash only; a `|` taken joins two commands into one
   (`find t1 -name ぁ|ls -o -delete` deletes there), and a `{` or `}` taken
   makes a brace group. Any character outside ASCII right before a
   character bash treats specially that can be a second byte now takes
   the worst case. The verifier found that bash closes a brace group only
   at a `}` after its first comma (`sort {a},-o}x` is `sort a}x -ox`, in
   every locale), which the brace pattern missed, as it missed a group
   holding a space Unicode has but bash does not split at.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from grounded_agency.capabilities.registry import CapabilityRegistry
from tests.test_bash_program_words import (
    POLICY,
    _adapter,
    _bash,
    _decision,
    _hook,
    _locale,
    _pre,
    _worst,
    needs_hook,
)

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

# Each sets a shell variable through a builtin's `{varname}` redirection,
# then runs an allow-listed command (the reported lines and the verifier's).
VARIABLE_LINES = [
    "echo hi {PATH}>/dev/null; ls",
    "echo x {HOME}>/dev/null; git status --short",
    "pwd {PATH}</dev/null && git status",
    "printf x {PATH}>&2; cat f",
    "echo {IFS}>/dev/null; ls",
    "echo {PATH}>>/dev/null; ls",
    "echo {HOME}>/dev/null && git log -1",
    "pwd {IFS}</dev/null; ls",
    "printf x {HOME}>/dev/null; git status",
    "echo {PATH}>&1 | ls",
    "echo x {PATH} >/dev/null; ls",
    "echo x {a[i=1]}>/dev/null; ls",
]

# `>&WORD` with WORD that Python counts as digits and bash does not.
UNICODE_DIGIT_LINES = [
    "echo payload-arabic >&١",
    "echo payload-sup >&²",
    "cat /etc/hostname >&１",
    "echo payload-circ >&①",
    "echo x >&1٢",
    "echo x >&١٢",
    "echo x 2>&١",
    "cat ~/.ssh/id_rsa >&١",
]

# A character outside ASCII right before one bash treats specially that a
# double-byte encoding can take as a second byte.
DOUBLE_BYTE_LINES = [
    "find t1 -name ぁ|ls -o -delete",
    "git log -1 --grep=ぁ|ls --output=pwned_by_gitlog.txt",
    "sort {ぁ},-o}x",
    "sort {-o,ぁ{x}",
    "ls \\ぁ|ls -o -delete",
    "ls ぁ}x",
    "ls ぁ[x]",
    "ls ぁ~",
    "ls ぁ;ls",
    "ls ぁ>/dev/null",
    "grep 'ぁ|' notes.txt",
]

# Brace groups bash expands and the old pattern did not see.
BRACE_LINES = [
    "sort {a},-o}x",
    "sort {a},--output=}pwn",
    "find . {a},-delete}",
    "sort a{},-o}x",
    "ls {a},b}",
    "find . {a　,-delete}",
    "find . {a ,-delete}",
    "find . x{a}y,-delete}",
    "sort {'a',-o}x",
]

# Lines that read as before: no such form, or a harmless one.
CONTROLS = [
    "git rev-parse @{u}",
    "git stash show stash@{0}",
    "echo x >&2",
    "ls 2>/dev/null",
    "echo {PATH}",
    "ls {}",
    "ls ぁ",
    'grep "ぁ" notes.txt',
    "ls ぁ x | wc -l",
    "ls ぁ-x ぁ_x ぁ1 ぁ:x ぁ=x",
    "echo '{a,b}'",
    "echo {a\\,b}",
    "ls x}{a",
]


@pytest.fixture
def classify(ontology_path: str) -> ToolCapabilityMapper:
    return ToolCapabilityMapper(CapabilityRegistry(ontology_path))


def _run(
    line: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", line],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


class TestVariableRedirections:
    """Defect 1: `{varname}` before a redirection assigns the variable."""

    @needs_bash
    def test_bash_runs_the_repository_program(self, tmp_path: Path) -> None:
        """The premise: after `echo hi {PATH}>/dev/null`, `ls` is the
        repository's `./10/ls` (descriptor 10, or the next free one)."""
        for fd in range(10, 20):
            program = tmp_path / str(fd) / "ls"
            program.parent.mkdir()
            program.write_text(
                f"#!/bin/sh\necho via {fd} > {tmp_path / 'pwned.txt'}\n",
                encoding="utf-8",
            )
            program.chmod(0o755)
        done = _run('echo hi {PATH}>/dev/null; ls; echo "PATH=$PATH"', tmp_path)
        # echo's own output still goes to stdout; descriptor 10 to /dev/null.
        assert done.stdout.splitlines()[-1].startswith("PATH=1"), done.stdout
        assert (tmp_path / "pwned.txt").read_text(encoding="utf-8").startswith("via")

    @needs_bash
    def test_an_external_command_does_not_change_the_shell(
        self, tmp_path: Path
    ) -> None:
        done = _run('env true {HOME}>/dev/null; echo "HOME=$HOME"', tmp_path)
        assert done.stdout.strip() == f"HOME={os.environ['HOME']}"

    @pytest.mark.parametrize("line", VARIABLE_LINES)
    def test_the_line_takes_the_worst_case(
        self, classify: ToolCapabilityMapper, line: str
    ) -> None:
        """They were `observe` (the last two: a blank before the
        redirection, and an array element, which bash takes too in places,
        refused alike)."""
        assert _worst(_bash(classify, line)), line


class TestUnicodeDigits:
    """Defect 2: `>&` with digits outside ASCII names a file."""

    @needs_bash
    def test_bash_writes_a_file_of_that_name(self, tmp_path: Path) -> None:
        _run("echo payload-arabic >&١; cat /etc/hostname >&１", tmp_path)
        assert (tmp_path / "١").read_text(encoding="utf-8") == "payload-arabic\n"
        assert (tmp_path / "１").exists()

    @pytest.mark.parametrize("line", UNICODE_DIGIT_LINES)
    def test_the_line_takes_the_worst_case(
        self, classify: ToolCapabilityMapper, line: str
    ) -> None:
        """They were `observe`."""
        assert _worst(_bash(classify, line)), line


class TestDoubleByteSpecials:
    """Defect 3: a `|`, `{` or `}` (and the like) taken as a second byte."""

    def test_bash_runs_one_find_there(self, tmp_path: Path) -> None:
        """The premise: in a GBK locale the `|` is gone and find deletes;
        in the C locale ls refuses `-o -delete` and nothing is deleted."""
        locales = _locale(tmp_path, "zh_CN.GBK", "GBK")
        if locales is None or shutil.which("bash") is None:
            pytest.skip("needs bash and localedef with the GBK charmap")
        line = DOUBLE_BYTE_LINES[0]
        for where, env in (
            ("there", {"LOCPATH": str(locales), "LC_ALL": "zh_CN.GBK"}),
            ("here", {"LC_ALL": "C"}),
        ):
            (tmp_path / where / "t1").mkdir(parents=True)
            (tmp_path / where / "t1" / "f").write_text("x", encoding="utf-8")
            _run(line, tmp_path / where, env)
        assert not (tmp_path / "there" / "t1").exists()
        assert (tmp_path / "here" / "t1" / "f").exists()

    @pytest.mark.parametrize("line", DOUBLE_BYTE_LINES)
    def test_the_line_takes_the_worst_case(
        self, classify: ToolCapabilityMapper, line: str
    ) -> None:
        """They were `observe` (the last a control: a quoted `|` is no
        operator in either reading, but refused alike)."""
        assert _worst(_bash(classify, line)), line


class TestBraceGroups:
    """Defect 3, the verifier's finding: braces bash closes late."""

    @needs_bash
    def test_bash_expands_them(self, tmp_path: Path) -> None:
        """The premise, in the C locale and in UTF-8."""
        for env in ({"LC_ALL": "C"}, {"LC_ALL": "C.UTF-8"}):
            done = _run("printf '<%s>\\n' {a},-o}x x{a}y,z}", tmp_path, env)
            assert done.stdout.split() == ["<a}x>", "<-ox>", "<xa}y>", "<xz>"]
        done = _run("printf '<%s>\\n' {a　,-o}", tmp_path, {"LC_ALL": "C.UTF-8"})
        assert done.stdout.split("\n")[1] == "<-o>"

    @needs_bash
    def test_find_deletes_through_one(self, tmp_path: Path) -> None:
        (tmp_path / "t2").mkdir()
        _run("find t2 {a},-delete}", tmp_path, {"LC_ALL": "C"})
        assert not (tmp_path / "t2").exists()

    @pytest.mark.parametrize("line", BRACE_LINES)
    def test_the_line_takes_the_worst_case(
        self, classify: ToolCapabilityMapper, line: str
    ) -> None:
        """They were `observe` but the last, a quoted alternative."""
        assert _worst(_bash(classify, line)), line

    def test_the_reading_stays_linear(self, classify: ToolCapabilityMapper) -> None:
        """A 4096-byte line of opening braces and commas, then one of
        commas and dots, classify in bounded time."""
        for line in ("ls " + "{," * 2046, "ls {" + ",.." * 1364):
            assert len(line.encode()) <= 4096
            start = time.monotonic()
            _bash(classify, line)
            assert time.monotonic() - start < 2.0


@pytest.mark.parametrize("line", CONTROLS)
def test_other_lines_still_read(classify: ToolCapabilityMapper, line: str) -> None:
    assert _bash(classify, line).capabilities == ("observe",), line


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "line", [VARIABLE_LINES[0], UNICODE_DIGIT_LINES[2], DOUBLE_BYTE_LINES[0]]
)
async def test_the_adapter_gates_it(
    ontology_path: str, tmp_path: Path, line: str
) -> None:
    """The adapter allowed each with no decision, with and without a
    destination policy."""
    adapter = _adapter(ontology_path, tmp_path, approval="ask")
    decision, why = _decision(await _pre(adapter, line))
    assert decision == "deny" and why.startswith("F501 CHECKPOINT_REQUIRED:"), why
    guarded = _adapter(
        ontology_path, tmp_path, approval="ask", allowed_destinations=POLICY
    )
    guarded.create_checkpoint(["*"], "t")
    decision, why = _decision(await _pre(guarded, line))
    assert decision == "deny" and why.startswith("F504 CONSTRAINT_VIOLATED:"), why


@needs_hook
@pytest.mark.parametrize(
    "line",
    [
        VARIABLE_LINES[0],
        VARIABLE_LINES[1],
        UNICODE_DIGIT_LINES[0],
        DOUBLE_BYTE_LINES[1],
        DOUBLE_BYTE_LINES[2],
        BRACE_LINES[2],
    ],
)
def test_the_plugin_hook_gated_it_already(tmp_path: Path, line: str) -> None:
    """The hook refuses `{`, `}`, `>`, `&`, `;` and `|` anywhere."""
    result = _hook(tmp_path, line)
    assert result.returncode == 2, line
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED: "), line
