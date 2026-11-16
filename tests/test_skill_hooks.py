"""Tests for the hooks declared in SKILL.md frontmatter.

Six skills (audit, checkpoint, persist, rollback, send, transform) declare
hooks. The command hooks are run here the way Claude Code runs them: the
command string from the frontmatter is given to a shell, and the tool call
arrives as JSON on stdin. A PreToolUse hook blocks with exit code 2 and the
reason on stderr; any other non-zero exit is a non-blocking error, after which
the tool would still run.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
POSTTOOLUSE_HOOK = ROOT / "hooks" / "posttooluse_log_tool.sh"
SECURITY_MD = ROOT / "spec" / "SECURITY.md"

SKILLS_WITH_HOOKS = ["audit", "checkpoint", "persist", "rollback", "send", "transform"]

# A hook command is run by a shell, so each is tried under sh and under bash
SHELLS = [shell for shell in ("sh", "bash") if shutil.which(shell)]

pytestmark = pytest.mark.skipif(
    not SHELLS or shutil.which("jq") is None,
    reason="the skill hooks need a shell, and jq to read the tool call",
)

SECRET = "sk-live-0123456789abcdef"


def frontmatter(skill: str) -> dict[str, Any]:
    text = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill}: no frontmatter"
    loaded = yaml.safe_load(text.split("---\n", 2)[1])
    assert isinstance(loaded, dict)
    return loaded


def hooks_of(
    skill: str, event: str, hook_type: str, matcher: str | None = None
) -> list[dict[str, Any]]:
    """The hooks of one type a skill declares for an event (and a matcher)."""
    found = []
    for group in frontmatter(skill).get("hooks", {}).get(event, []):
        if matcher is not None and group.get("matcher") != matcher:
            continue
        for hook in group["hooks"]:
            if hook["type"] == hook_type:
                found.append({**hook, "matcher": group.get("matcher")})
    return found


def command_hook(skill: str, event: str, matcher: str) -> str:
    hooks = hooks_of(skill, event, "command", matcher)
    assert len(hooks) == 1, f"{skill}: expected one {event} command hook on {matcher}"
    command = hooks[0]["command"]
    assert isinstance(command, str)
    return command


def run_command(
    command: str,
    tool_call: dict[str, Any] | str,
    cwd: Path,
    shell: str,
    env_override: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    stdin = tool_call if isinstance(tool_call, str) else json.dumps(tool_call)
    return subprocess.run(
        [shell, "-c", command],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=30,
    )


def bash_call(command: str) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def edit_call(file_path: str) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
    }


def input_digest(tool_input: Any) -> str:
    """SHA-256 of the tool input as compact JSON with sorted keys (jq -cS)."""
    canonical = json.dumps(
        tool_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_blocked(
    result: subprocess.CompletedProcess[str], reason: str, opens: str = "BLOCK: "
) -> None:
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith(opens), result.stderr
    assert reason in result.stderr
    assert result.stdout == "", "the reason belongs on stderr"


# A refusal on a text channel opens with the Standard's code and name
# (STANDARD 1.2.0 §5.18.8): a call a command hook cannot read is R407.
OPENS = {
    "audit": "R407 SAFETY_CHECK_FAILED: ",
    "persist": "R407 SAFETY_CHECK_FAILED: ",
    "rollback": "R407 SAFETY_CHECK_FAILED: ",
    "send": "R407 SAFETY_CHECK_FAILED: ",
}
F504 = "F504 CONSTRAINT_VIOLATED: "
SECRET_SCAN = ROOT / "hooks" / "secret_scan.sh"
CREDENTIALS = json.loads(
    (ROOT / "tests" / "conformance" / "secrets" / "credentials.json").read_text(
        encoding="utf-8"
    )
)


# ---------------------------------------------------------------------------
# The frontmatter as a whole
# ---------------------------------------------------------------------------


class TestFrontmatterHooks:
    def test_skills_with_hooks_are_the_six(self) -> None:
        declared = sorted(
            path.parent.name
            for path in SKILLS_DIR.glob("*/SKILL.md")
            if "hooks" in frontmatter(path.parent.name)
        )
        assert declared == SKILLS_WITH_HOOKS

    def test_security_md_maps_every_hook(self) -> None:
        """SECURITY.md §5.4 maps every condition of the skills' hooks to the
        Standard's check it implements, or marks it a model-judged addition
        (STANDARD 1.2.0 §5.18.10).

        Every pre-tool-use hook has at least one row, and each row of a
        command hook says code enforces it; every row cites a section of
        the Standard or says it is a model-judged addition.
        """
        text = SECURITY_MD.read_text(encoding="utf-8")
        start = text.index("### 5.4 ")
        section = text[start : text.index("### 5.5 ", start)]
        rows = [
            [cell.strip() for cell in line.strip("|").split("|")]
            for line in section.splitlines()
            if line.startswith("| `skills/")
        ]
        assert rows
        for hook, condition, standard, enforced_by in rows:
            assert condition and enforced_by, hook
            assert "§5.18" in standard or standard.startswith(
                "Model-judged addition"
            ), (
                hook,
                condition,
            )
        kinds = {"command": "command hook", "prompt": "prompt hook"}
        for skill in SKILLS_WITH_HOOKS:
            for group in frontmatter(skill)["hooks"].get("PreToolUse", []):
                for hook in group["hooks"]:
                    where = (
                        f"`skills/{skill}/SKILL.md`, {kinds[hook['type']]} on "
                        f"`{group['matcher']}`"
                    )
                    matching = [row for row in rows if row[0].startswith(where)]
                    assert matching, f"SECURITY.md §5.4: no row for {where}"
                    if hook["type"] == "command":
                        for row in matching:
                            assert row[3].startswith("Code"), where

    @pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
    @pytest.mark.parametrize(
        ("tool_call", "blocked"),
        [
            ({"tool_name": "Write", "tool_input": {"file_path": "/etc/hosts"}}, True),
            ({"tool_name": "Write", "tool_input": {"file_path": "/work/a.py"}}, False),
            ({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}, False),
            ("not json", True),
        ],
    )
    def test_security_md_example_hook_blocks_with_exit_2(
        self, tmp_path: Path, tool_call: dict[str, Any] | str, blocked: bool
    ) -> None:
        """The example in SECURITY.md §5.3 follows the contract it describes."""
        text = SECURITY_MD.read_text(encoding="utf-8")
        start = text.index("```bash\n", text.index("### 5.3 ")) + len("```bash\n")
        script = text[start : text.index("```", start)]

        result = run_command(script, tool_call, tmp_path, "bash")
        if blocked:
            assert result.returncode == 2, (result.returncode, result.stderr)
            assert result.stderr.startswith("BLOCKED: ")
            assert result.stdout == "", "the reason belongs on stderr"
        else:
            assert result.returncode == 0, result.stderr
            assert result.stderr == ""

    @pytest.mark.parametrize("skill", SKILLS_WITH_HOOKS)
    def test_no_template_placeholders(self, skill: str) -> None:
        """Claude Code substitutes no ``{{tool_input...}}`` text into a hook.

        A command hook reads the tool call from stdin, and a prompt hook gets
        it appended as JSON, so a placeholder would reach the shell or the
        model as literal text.
        """
        for groups in frontmatter(skill)["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    text = hook.get("command") or hook.get("prompt") or ""
                    assert "{{" not in text, f"{skill}: placeholder in {hook['type']}"

    def test_pretooluse_command_hooks_are_the_four(self) -> None:
        declared = [
            skill
            for skill in SKILLS_WITH_HOOKS
            if hooks_of(skill, "PreToolUse", "command")
        ]
        assert declared == ["audit", "persist", "rollback", "send"]

    @pytest.mark.parametrize("skill", ["audit", "persist"])
    def test_secret_scan_copies_are_equal(self, skill: str) -> None:
        """The persist and audit hooks run one scan (STANDARD 1.2.0 §6.7):
        each copies hooks/secret_scan.sh verbatim, from its BEGIN line to
        its END line, as tools/validate_yaml_util_sync.py keeps two copies
        of one utility equal."""
        matcher = "Edit" if skill == "persist" else "Bash"
        command = command_hook(skill, "PreToolUse", matcher)
        source = SECRET_SCAN.read_text(encoding="utf-8").strip()
        start = command.index("# BEGIN secret-scan")
        end = command.index("# END secret-scan") + len("# END secret-scan")
        assert command[start:end] == source

    @pytest.mark.parametrize("shell", SHELLS)
    @pytest.mark.parametrize(
        "vector",
        [
            v
            for v in CREDENTIALS["vectors"]
            if isinstance(v["input"], str) and not v["secret_values"]
        ],
        ids=lambda v: v["name"],
    )
    def test_secret_scan_vectors(self, shell: str, vector: dict[str, Any]) -> None:
        """The scan agrees with the Python and TypeScript refusal rule on
        tests/conformance/secrets/credentials.json (its text vectors)."""
        script = SECRET_SCAN.read_text(encoding="utf-8") + (
            '\nif secret_in "$1"; then echo yes; else echo no; fi\n'
        )
        result = subprocess.run(
            [shell, "-c", script, "scan", vector["input"]],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        expected = "yes" if vector["expect"]["holds"] else "no"
        assert result.stdout.strip() == expected, vector["name"]

    @pytest.mark.parametrize("shell", SHELLS)
    @pytest.mark.parametrize(
        ("skill", "matcher"),
        [
            ("audit", "Bash"),
            ("persist", "Edit"),
            ("rollback", "Bash"),
            ("send", "Bash"),
        ],
    )
    def test_unreadable_tool_call_is_blocked(
        self, tmp_path: Path, shell: str, skill: str, matcher: str
    ) -> None:
        """A check that cannot read the call does not let it through."""
        command = command_hook(skill, "PreToolUse", matcher)
        result = run_command(command, "not json", tmp_path, shell)
        assert_blocked(result, "cannot read the tool call", OPENS.get(skill, "BLOCK: "))

    @pytest.mark.parametrize("shell", SHELLS)
    @pytest.mark.parametrize(
        ("skill", "matcher", "tool_call"),
        [
            ("audit", "Bash", bash_call("wc -l .claude/audit/records.jsonl")),
            ("persist", "Edit", edit_call("/work/app/CLAUDE.md")),
            ("rollback", "Bash", bash_call("git status")),
            ("send", "Bash", bash_call("ls -la")),
        ],
    )
    def test_call_is_blocked_where_jq_is_not_installed(
        self,
        tmp_path: Path,
        shell: str,
        skill: str,
        matcher: str,
        tool_call: dict[str, Any],
    ) -> None:
        """Without jq the hook cannot read the call, so it blocks it."""
        empty_bin = tmp_path / "bin"
        empty_bin.mkdir()
        shell_path = shutil.which(shell)
        assert shell_path is not None

        command = command_hook(skill, "PreToolUse", matcher)
        result = run_command(
            command, tool_call, tmp_path, shell_path, {"PATH": str(empty_bin)}
        )
        assert_blocked(result, "jq is required", OPENS.get(skill, "BLOCK: "))


# ---------------------------------------------------------------------------
# send: a request to localhost or a private IPv4 address
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shell", SHELLS)
class TestSendCommandHook:
    @pytest.mark.parametrize(
        "command",
        [
            "curl http://localhost:8080/health",
            "curl -X POST http://127.0.0.1:3000/hook -d '{}'",
            "wget http://10.0.0.5/payload",
            "curl https://192.168.1.10/api",
            "curl http://172.16.4.2/",
            "curl -s \\\n  http://user@10.1.2.3/x",
            # host names are case-insensitive
            "curl http://LOCALHOST:8080/admin",
            "curl http://Localhost/",
            "curl 10.0.0.1",
            "curl 'http://10.0.0.1?q=1'",
        ],
    )
    def test_blocks_internal_destination(
        self, tmp_path: Path, shell: str, command: str
    ) -> None:
        hook = command_hook("send", "PreToolUse", "Bash")
        result = run_command(hook, bash_call(command), tmp_path, shell)
        assert_blocked(
            result,
            "does not send to localhost or a private IPv4 address",
            "F504 CONSTRAINT_VIOLATED: ",
        )

    @pytest.mark.parametrize(
        "command",
        [
            "curl https://api.example.com/v1/messages",
            # a version number is not an address
            "curl -O https://www.python.org/ftp/python/3.10.2/Python-3.10.2.tgz",
            "curl https://localhost.example.com/",
            # an address-like part of a path or a query is not the host
            "curl -O https://dl.example.com/win/10.0.19041.1/setup.zip",
            "curl https://example.com/?v=10.2.3.4",
            "ls -la",
            "ping 10.0.0.5",
        ],
    )
    def test_allows_other_commands(
        self, tmp_path: Path, shell: str, command: str
    ) -> None:
        hook = command_hook("send", "PreToolUse", "Bash")
        result = run_command(hook, bash_call(command), tmp_path, shell)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# persist: system directories, credential directories and credential files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shell", SHELLS)
class TestPersistCommandHook:
    @pytest.mark.parametrize(
        "file_path",
        [
            "/etc/hosts",
            "/usr/local/bin/tool",
            "{home}/.ssh/config",
            "{home}/.aws/config",
            "~/.config/app/settings.toml",
        ],
    )
    def test_blocks_system_and_credential_directories(
        self, tmp_path: Path, shell: str, file_path: str
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        hook = command_hook("persist", "PreToolUse", "Edit")
        result = run_command(
            hook,
            edit_call(file_path.format(home=home)),
            tmp_path,
            shell,
            {"HOME": str(home)},
        )
        assert_blocked(
            result, "Cannot persist to system or credential directories", F504
        )

    @pytest.mark.parametrize(
        "file_path",
        [
            "//etc/passwd",
            "/tmp/../etc/passwd",
            "{home}/proj/../.ssh/authorized_keys",
            "{home}//.ssh/authorized_keys",
            "{home}/./.ssh/config",
            "../outside/notes.md",
            "/work/app/docs/..",
        ],
    )
    def test_blocks_paths_not_compared_as_written(
        self, tmp_path: Path, shell: str, file_path: str
    ) -> None:
        """'//', '.' and '..' segments would hide a system or credential
        directory from the prefix patterns, so such a path is blocked."""
        home = tmp_path / "home"
        home.mkdir()
        hook = command_hook("persist", "PreToolUse", "Edit")
        result = run_command(
            hook,
            edit_call(file_path.format(home=home)),
            tmp_path,
            shell,
            {"HOME": str(home)},
        )
        assert_blocked(result, "Cannot persist to a path with", F504)

    @pytest.mark.parametrize(
        "file_path",
        ["/work/app/.env", "/work/app/config/SECRETS", "/work/app/server.pem"],
    )
    def test_blocks_credential_files(
        self, tmp_path: Path, shell: str, file_path: str
    ) -> None:
        hook = command_hook("persist", "PreToolUse", "Edit")
        result = run_command(hook, edit_call(file_path), tmp_path, shell)
        assert_blocked(result, "Cannot persist to credential files", F504)

    @pytest.mark.parametrize(
        "file_path",
        [
            "/work/app/CLAUDE.md",
            "/work/app/docs/decisions.md",
            # a directory that only contains .ssh in its name is not ~/.ssh
            "/project/docs/.ssh/notes.md",
            "/work/app/notes..md",
        ],
    )
    def test_allows_project_files(
        self, tmp_path: Path, shell: str, file_path: str
    ) -> None:
        hook = command_hook("persist", "PreToolUse", "Edit")
        result = run_command(hook, edit_call(file_path), tmp_path, shell)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""

    @pytest.mark.parametrize(
        "content",
        [
            "the deploy key is AKIAABCDEFGHIJKLMNOP",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaA==\n",
            'password = "hunter22x"',
            "api_key=abc123def456ghi",
            "use ghp_" + "a" * 36 + " for the bot",
            "DATABASE_URL=postgres://app:s3cretpass@db.internal/app",
            "curl -H 'Authorization: Basic dXNlcjpwYXNzd29yZA==' https://x",
        ],
    )
    def test_blocks_content_that_holds_a_credential(
        self, tmp_path: Path, shell: str, content: str
    ) -> None:
        """Memory is read back as fact, so a credential is refused, not
        redacted (STANDARD 1.2.0 §6.7). The target is an allowed path, so
        only the content scan can block the call: stdin was read once, and
        the content scanned."""
        hook = command_hook("persist", "PreToolUse", "Edit")
        call = edit_call("/work/app/CLAUDE.md")
        call["tool_input"]["new_string"] = content
        result = run_command(hook, call, tmp_path, shell)
        assert_blocked(result, "holds what looks like a credential", F504)

    def test_blocks_a_credential_in_a_whole_files_content(
        self, tmp_path: Path, shell: str
    ) -> None:
        hook = command_hook("persist", "PreToolUse", "Edit")
        call = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/work/app/CLAUDE.md",
                "content": "token: AKIAABCDEFGHIJKLMNOP",
            },
        }
        result = run_command(hook, call, tmp_path, shell)
        assert_blocked(result, "holds what looks like a credential", F504)

    @pytest.mark.parametrize(
        "content",
        [
            "token: rotate monthly",
            "secret: never commit it",
            "Bearer tokens are short-lived",
            "password: see the vault",
            "the tokenizer lives in src/tokens.py",
            "DATABASE_URL=postgres://app:${DB_PASSWORD}@db.internal/app",
            "Authorization: required for the admin API",
        ],
    )
    def test_allows_prose_about_credentials(
        self, tmp_path: Path, shell: str, content: str
    ) -> None:
        hook = command_hook("persist", "PreToolUse", "Edit")
        call = edit_call("/work/app/CLAUDE.md")
        call["tool_input"]["new_string"] = content
        result = run_command(hook, call, tmp_path, shell)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# audit: a record appended to .claude/audit/records.jsonl holds no credential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shell", SHELLS)
class TestAuditCommandHook:
    def test_blocks_a_record_that_holds_a_credential(
        self, tmp_path: Path, shell: str
    ) -> None:
        hook = command_hook("audit", "PreToolUse", "Bash")
        command = (
            'printf \'%s\\n\' \'{"event":"x","token":"ghp_'
            + "b" * 36
            + "\"}' >> .claude/audit/records.jsonl"
        )
        result = run_command(hook, bash_call(command), tmp_path, shell)
        assert_blocked(result, "cite it by reference or digest", F504)

    @pytest.mark.parametrize(
        "secret",
        [
            '"url":"https://deploy:s3cretpass@git.example.com/r.git"',
            '"headers":{"Authorization":"Basic dXNlcjpwYXNzd29yZA=="}',
        ],
    )
    def test_blocks_a_record_with_url_or_header_credentials(
        self, tmp_path: Path, shell: str, secret: str
    ) -> None:
        hook = command_hook("audit", "PreToolUse", "Bash")
        command = (
            'printf \'%s\\n\' \'{"event":"x",' + secret + "}' "
            ">> .claude/audit/records.jsonl"
        )
        result = run_command(hook, bash_call(command), tmp_path, shell)
        assert_blocked(result, "cite it by reference or digest", F504)

    @pytest.mark.parametrize(
        "command",
        [
            'printf \'%s\\n\' \'{"event":"deploy","output_sha256":"ab12"}\' '
            ">> .claude/audit/records.jsonl",
            "wc -l .claude/audit/records.jsonl",
            # A secret in a command that does not touch the records file is
            # other hooks' business.
            "curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz' https://x",
        ],
    )
    def test_allows_other_commands(
        self, tmp_path: Path, shell: str, command: str
    ) -> None:
        hook = command_hook("audit", "PreToolUse", "Bash")
        result = run_command(hook, bash_call(command), tmp_path, shell)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# rollback: a restore must name a checkpoint the project recorded
# ---------------------------------------------------------------------------

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with one commit and no stash."""
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q")
    (path / "a.txt").write_text("one\n")
    git(path, "add", "a.txt")
    git(path, "commit", "-q", "-m", "first")
    return path


ROLLBACK_ENV = {**GIT_ENV, "CLAUDE_PROJECT_DIR": ""}


def checkpoint(repo: Path, where: str = "marker") -> str:
    """Take a checkpoint as the plugin does: `git stash create` (which writes
    no refs/stash, so `git stash list` stays empty) and a marker recording
    its commit, live or filed under used/ or ended/."""
    (repo / "a.txt").write_text("two\n")
    sha = git(repo, "stash", "create", "checkpoint:x").strip()
    assert git(repo, "stash", "list") == ""
    record = json.dumps({"checkpoint_id": sha, "commit": sha})
    claude = repo / ".claude"
    if where == "marker":
        claude.mkdir()
        (claude / "checkpoint.ok").write_text(record)
    else:
        (claude / "checkpoints" / where).mkdir(parents=True)
        (claude / "checkpoints" / where / "m.1").write_text(record)
    return sha


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
@pytest.mark.parametrize("shell", SHELLS)
class TestRollbackCommandHook:
    """STANDARD 1.2.0 §5.18.6: a rollback needs a checkpoint taken earlier,
    valid or not. In this skill a `git stash pop|apply` must name the commit
    a checkpoint recorded (F503 otherwise), whatever `git stash list` holds."""

    @pytest.mark.parametrize("where", ["marker", "used", "ended"])
    def test_allows_restoring_a_recorded_checkpoint(
        self, repo: Path, shell: str, where: str
    ) -> None:
        sha = checkpoint(repo, where)
        hook = command_hook("rollback", "PreToolUse", "Bash")
        for command in (f"git stash apply {sha}", f"git stash pop {sha}"):
            result = run_command(hook, bash_call(command), repo, shell, ROLLBACK_ENV)
            assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        "command",
        [
            "git stash pop",
            "git stash apply",
            "git stash apply stash@{0}",
            "git stash apply HEAD",
            "git stash apply 0123456789abcdef0123456789abcdef01234567",
            "git stash apply --index {sha}",
            "git stash apply {short}",
            "git stash apply {sha} && git stash pop",
        ],
    )
    def test_blocks_a_restore_of_no_recorded_checkpoint(
        self, repo: Path, shell: str, command: str
    ) -> None:
        sha = checkpoint(repo)
        hook = command_hook("rollback", "PreToolUse", "Bash")
        text = command.replace("{sha}", sha).replace("{short}", sha[:12])
        result = run_command(hook, bash_call(text), repo, shell, ROLLBACK_ENV)
        assert_blocked(
            result,
            "restores no checkpoint taken in this project",
            "F503 ROLLBACK_FAILED: ",
        )

    def test_an_unrelated_stash_does_not_let_a_bare_pop_through(
        self, repo: Path, shell: str
    ) -> None:
        (repo / "a.txt").write_text("two\n")
        git(repo, "stash", "push", "-q", "-m", "unrelated")
        hook = command_hook("rollback", "PreToolUse", "Bash")
        result = run_command(
            hook, bash_call("git stash pop"), repo, shell, ROLLBACK_ENV
        )
        assert_blocked(result, "restores no checkpoint", "F503 ROLLBACK_FAILED: ")

    def test_reads_the_markers_of_claude_project_dir(
        self, repo: Path, tmp_path: Path, shell: str
    ) -> None:
        sha = checkpoint(repo)
        hook = command_hook("rollback", "PreToolUse", "Bash")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        call = bash_call(f"git stash apply {sha}")
        env = {**GIT_ENV, "CLAUDE_PROJECT_DIR": str(repo)}
        assert run_command(hook, call, elsewhere, shell, env).returncode == 0
        env = {**GIT_ENV, "CLAUDE_PROJECT_DIR": str(elsewhere)}
        assert run_command(hook, call, repo, shell, env).returncode == 2

    @pytest.mark.parametrize(
        "command",
        [
            # taking a checkpoint and listing stashes restore nothing
            "git stash create checkpoint:x",
            "git stash push -m 'checkpoint:chk_2:before edit'",
            "git stash list",
            "git status",
        ],
    )
    def test_allows_commands_that_restore_nothing(
        self, repo: Path, shell: str, command: str
    ) -> None:
        hook = command_hook("rollback", "PreToolUse", "Bash")
        result = run_command(hook, bash_call(command), repo, shell, ROLLBACK_ENV)
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# PostToolUse: the skills' own logs hold a digest, not the input
# ---------------------------------------------------------------------------

# Bash and Read get two keys out of sorted order, so that a log hook that
# stops sorting keys (jq -c in place of jq -cS) gives a different digest.
TOOL_INPUTS: dict[str, dict[str, Any]] = {
    "Bash": {
        "description": "Fetch the example page",
        "command": f"curl -H 'Authorization: Bearer {SECRET}' https://example.com",
    },
    "Edit": {
        "file_path": "/work/app/notes.md",
        "old_string": "token: none",
        "new_string": f"token: {SECRET}",
    },
    "Read": {"limit": 2000, "file_path": f"/work/app/{SECRET}.txt"},
    "Grep": {"pattern": SECRET, "path": "/work/app"},
}

LOG_HOOKS = [
    (skill, hook["matcher"])
    for skill in SKILLS_WITH_HOOKS
    for hook in hooks_of(skill, "PostToolUse", "command")
]


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(("skill", "matcher"), LOG_HOOKS)
class TestSkillLogHooks:
    def test_logs_a_digest_and_not_the_input(
        self, tmp_path: Path, shell: str, skill: str, matcher: str
    ) -> None:
        tool_input = TOOL_INPUTS[matcher]
        tool_call = {
            "hook_event_name": "PostToolUse",
            "tool_name": matcher,
            "tool_input": tool_input,
            "tool_response": {"stdout": SECRET},
        }
        command = command_hook(skill, "PostToolUse", matcher)
        result = run_command(command, tool_call, tmp_path, shell)
        assert result.returncode == 0, result.stderr

        logs = list((tmp_path / ".audit").glob("*.log"))
        assert len(logs) == 1, "one log file under .audit/"
        lines = logs[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, "one line per call"

        line = lines[0]
        assert f"| {matcher} | input_sha256: {input_digest(tool_input)}" in line
        assert SECRET not in line
        for value in tool_input.values():
            if isinstance(value, str):
                assert value not in line, "the tool input is not written"

    def test_unreadable_call_is_logged_without_a_digest(
        self, tmp_path: Path, shell: str, skill: str, matcher: str
    ) -> None:
        command = command_hook(skill, "PostToolUse", matcher)
        # a DIGEST in the environment is not taken for the call's digest
        result = run_command(
            command, f"not json {SECRET}", tmp_path, shell, {"DIGEST": "f" * 64}
        )
        assert result.returncode == 0

        (log,) = (tmp_path / ".audit").glob("*.log")
        line = log.read_text(encoding="utf-8")
        assert "input_sha256: unavailable" in line
        assert SECRET not in line


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_skill_log_digest_matches_the_plugin_audit_log(tmp_path: Path) -> None:
    """The same call has the same digest in a skill's log and in audit.log."""
    tool_call = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": TOOL_INPUTS["Bash"],
    }
    command = command_hook("send", "PostToolUse", "Bash")
    assert run_command(command, tool_call, tmp_path, SHELLS[0]).returncode == 0
    skill_line = (tmp_path / ".audit" / "send-operations.log").read_text()

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    subprocess.run(
        ["bash", str(POSTTOOLUSE_HOOK)],
        input=json.dumps(tool_call),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=True,
    )
    entry = json.loads((tmp_path / ".claude" / "audit.log").read_text())

    assert entry["details"]["input_sha256"] == input_digest(TOOL_INPUTS["Bash"])
    assert f"input_sha256: {entry['details']['input_sha256']}" in skill_line


class TestPromptHooksAreModelJudgedAdditions:
    """STANDARD 1.2.0 §5.18.10: a check the Standard requires is decided by
    code; a prompt hook keeps only model-judged additions."""

    OPENING = "Model-judged additions (STANDARD 1.2.0 §5.18.10)"

    @pytest.mark.parametrize("skill", SKILLS_WITH_HOOKS)
    def test_every_prompt_hook_opens_with_the_model_judged_line(
        self, skill: str
    ) -> None:
        for event in ("PreToolUse", "PostToolUse"):
            for hook in hooks_of(skill, event, "prompt"):
                assert hook["prompt"].startswith(self.OPENING), skill

    @pytest.mark.parametrize(
        ("skill", "removed"),
        [
            ("send", ["explicitly approved", "Checkpoint exists", "Rate limits"]),
            ("rollback", ["has not expired", "exists and is valid"]),
        ],
    )
    def test_code_decided_conditions_are_gone(
        self, skill: str, removed: list[str]
    ) -> None:
        (hook,) = hooks_of(skill, "PreToolUse", "prompt")
        conditions = hook["prompt"].split("\n\n", 1)[1]
        for phrase in removed:
            assert phrase.lower() not in conditions.lower(), (skill, phrase)

    def test_no_skill_writes_the_checkpoint_marker(self) -> None:
        """The marker is the safety layer's own record: a skill takes a
        checkpoint with a state-saving command (§5.18.6) instead."""
        for path in SKILLS_DIR.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            assert "Create `.claude/checkpoint.ok`" not in text, path
            assert "Create checkpoint marker" not in text, path
