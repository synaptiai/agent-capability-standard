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


def assert_blocked(result: subprocess.CompletedProcess[str], reason: str) -> None:
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith("BLOCK: ")
    assert reason in result.stderr
    assert result.stdout == "", "the reason belongs on stderr"


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

    def test_security_md_says_what_enforces_each_check(self) -> None:
        """SECURITY.md §5.4 has one row for each hook that can refuse a call.

        The row says whether code or a model decides: a command hook is code,
        a prompt hook is a model's judgement.
        """
        text = SECURITY_MD.read_text(encoding="utf-8")
        start = text.index("### 5.4 ")
        section = text[start : text.index("\n## 6. ", start)]
        rows = [line for line in section.splitlines() if line.startswith("| ")]
        kinds = {
            "command": ("command hook", "Code: blocks the call"),
            "prompt": ("prompt hook", "A model judges"),
        }

        for skill in SKILLS_WITH_HOOKS:
            for group in frontmatter(skill)["hooks"].get("PreToolUse", []):
                for hook in group["hooks"]:
                    kind, enforced_by = kinds[hook["type"]]
                    where = f"`skills/{skill}/SKILL.md`, {kind} on `{group['matcher']}`"
                    matching = [row for row in rows if where in row]
                    assert len(matching) == 1, f"SECURITY.md §5.4: no row for {where}"
                    assert matching[0].rstrip(" |").endswith(enforced_by), where

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

    def test_pretooluse_command_hooks_are_the_three(self) -> None:
        declared = [
            skill
            for skill in SKILLS_WITH_HOOKS
            if hooks_of(skill, "PreToolUse", "command")
        ]
        assert declared == ["persist", "rollback", "send"]

    @pytest.mark.parametrize("shell", SHELLS)
    @pytest.mark.parametrize(
        ("skill", "matcher"),
        [("persist", "Edit"), ("rollback", "Bash"), ("send", "Bash")],
    )
    def test_unreadable_tool_call_is_blocked(
        self, tmp_path: Path, shell: str, skill: str, matcher: str
    ) -> None:
        """A check that cannot read the call does not let it through."""
        command = command_hook(skill, "PreToolUse", matcher)
        result = run_command(command, "not json", tmp_path, shell)
        assert_blocked(result, "cannot read the tool call")

    @pytest.mark.parametrize("shell", SHELLS)
    @pytest.mark.parametrize(
        ("skill", "matcher", "tool_call"),
        [
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
        assert_blocked(result, "jq is required")


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
        assert_blocked(result, "Internal network access requires explicit approval")

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
        assert_blocked(result, "Cannot persist to system or credential directories")

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
        assert_blocked(result, "Cannot persist to a path with")

    @pytest.mark.parametrize(
        "file_path",
        ["/work/app/.env", "/work/app/config/SECRETS", "/work/app/server.pem"],
    )
    def test_blocks_credential_files(
        self, tmp_path: Path, shell: str, file_path: str
    ) -> None:
        hook = command_hook("persist", "PreToolUse", "Edit")
        result = run_command(hook, edit_call(file_path), tmp_path, shell)
        assert_blocked(result, "Cannot persist to credential files")

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


# ---------------------------------------------------------------------------
# rollback: restoring a git stash when there is none
# ---------------------------------------------------------------------------

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        timeout=30,
    )


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


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
@pytest.mark.parametrize("shell", SHELLS)
class TestRollbackCommandHook:
    @pytest.mark.parametrize("command", ["git stash pop", "git stash apply stash@{0}"])
    def test_blocks_restore_without_a_stash(
        self, repo: Path, shell: str, command: str
    ) -> None:
        hook = command_hook("rollback", "PreToolUse", "Bash")
        result = run_command(hook, bash_call(command), repo, shell, GIT_ENV)
        assert_blocked(result, "No git stash found to restore")

    def test_allows_restore_with_a_stash(self, repo: Path, shell: str) -> None:
        (repo / "a.txt").write_text("two\n")
        git(repo, "stash", "push", "-q", "-m", "checkpoint:chk_1:test")

        hook = command_hook("rollback", "PreToolUse", "Bash")
        result = run_command(hook, bash_call("git stash pop"), repo, shell, GIT_ENV)
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        "command",
        [
            # taking a checkpoint and listing stashes restore nothing
            "git stash push -m 'checkpoint:chk_2:before edit'",
            "git stash list",
            "git status",
        ],
    )
    def test_allows_commands_that_restore_nothing(
        self, repo: Path, shell: str, command: str
    ) -> None:
        hook = command_hook("rollback", "PreToolUse", "Bash")
        result = run_command(hook, bash_call(command), repo, shell, GIT_ENV)
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

    assert entry["input_sha256"] == input_digest(TOOL_INPUTS["Bash"])
    assert f"input_sha256: {entry['input_sha256']}" in skill_line
