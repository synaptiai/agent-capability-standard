"""The strict sandbox: the pre-tool-use hook relaxes a Bash call that its
classifier reads as other than a mutate (a read-only command, a checkpoint
taken or restored) only when the settings files it can read configure
Claude Code's strict sandbox, and gives every other Bash call the worst case,
a gated mutate (STANDARD 1.2.0 §5.18.3, RFC-0011; hooks/README.md, The
strict sandbox)."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from grounded_agency.layer_records import deny_settings

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "pretooluse_require_checkpoint.sh"
LAYER_RECORDS = ROOT / "grounded_agency" / "layer_records.py"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("jq") is None,
    reason="needs git and jq",
)

ON_A_SANDBOX_SYSTEM = platform.system() in ("Darwin", "Linux")
needs_sandbox_system = pytest.mark.skipif(
    not ON_A_SANDBOX_SYSTEM, reason="Claude Code has a sandbox on macOS and Linux only"
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **_GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "app.txt").write_text("app\n")
    _git(path, "add", "app.txt")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _forms(path: Path | str) -> list[str]:
    """A path as written (absolute) and as resolved, once each."""
    out = [os.path.abspath(path)]
    if os.path.realpath(path) not in out:
        out.append(os.path.realpath(path))
    return out


def _toplevel(project: Path) -> str | None:
    """The top level of the repository that holds ``project``, as git
    gives it, or None outside one."""
    if not project.is_dir():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=project,
        env={**os.environ, **_GIT_ENV},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def required_rules(
    project: Path,
    config: Path,
    hooks_dir: Path = HOOK.parent,
    local_files: tuple[Path, ...] = (),
    home: Path | None = None,
) -> list[str]:
    """Every deny rule the hook requires for ``project``: the records' rules
    as grounded_agency/layer_records.py gives them, then Edit rules for the
    settings files (project, local, and the local files given), the
    project's .claude/hooks, the user configuration directory (and
    ~/.claude.json when ``home`` is given: no CLAUDE_CONFIG_DIR) and the
    hooks' directory, an Edit rule for the .mcp.json of the project and of its
    repository's top level, Read and
    Edit rules for the audit key file, and Read
    rules for the user's credentials."""
    deny = list(deny_settings(project)["permissions"]["deny"])
    for base in _forms(project):
        deny += [
            f"Edit(/{base}/.claude/settings.json)",
            f"Edit(/{base}/.claude/settings.local.json)",
            f"Edit(/{base}/.claude/hooks/**)",
            f"Edit(/{base}/.mcp.json)",
        ]
    top = _toplevel(project)
    if top is not None and top != os.path.realpath(project):
        deny.append(f"Edit(/{top}/.mcp.json)")
    for local in local_files:
        deny += [f"Edit(/{form})" for form in _forms(local)]
    deny += [f"Edit(/{form}/**)" for form in _forms(config)]
    if home is not None:
        deny += [f"Edit(/{form}/.claude.json)" for form in _forms(home)]
    deny.append(f"Edit(/{os.path.realpath(hooks_dir)}/**)")
    for form in _forms(home or os.path.expanduser("~")):
        key = f"{form}/.config/acs/audit.key"
        deny += [f"Edit(/{key})", f"Read(/{key})"]
        deny += [f"Read(/{form}/.ssh/**)"]
        deny += [
            f"Read(/{form}/.config/gh/hosts.yml)",
            f"Read(/{form}/.git-credentials)",
        ]
        if platform.system() == "Darwin":
            deny.append(f"Read(/{form}/Library/Keychains/**)")
    if platform.system() == "Darwin":
        deny.append("Read(//Library/Keychains/**)")
    return list(dict.fromkeys(deny))


STRICT_SANDBOX: dict[str, Any] = {
    "enabled": True,
    "failIfUnavailable": True,
    "allowUnsandboxedCommands": False,
    "autoAllowBashIfSandboxed": True,
    "network": {"allowedDomains": ["example.com"], "strictAllowlist": True},
    "credentials": {
        "envVars": [
            {"name": "GH_TOKEN", "mode": "deny"},
            {"name": "GITHUB_TOKEN", "mode": "deny"},
        ]
    },
}


def strict(project: Path, config: Path, **kw: Any) -> dict[str, Any]:
    return {
        "sandbox": json.loads(json.dumps(STRICT_SANDBOX)),
        "permissions": {"deny": required_rules(project, config, **kw)},
    }


def _write(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def run_hook(
    project: Path,
    config: Path,
    command: str = "ls",
    *,
    tool_input: dict[str, Any] | None = None,
    hook: Path = HOOK,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": "Bash",
        "tool_input": tool_input if tool_input is not None else {"command": command},
        "permission_mode": "default",
        "tool_use_id": "toolu_strict",
    }
    full_env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(project),
        "CLAUDE_CONFIG_DIR": str(config),
    }
    full_env.pop("AUDIT_HMAC_KEY", None)
    full_env.pop("ACS_HOOK_APPROVAL", None)
    full_env.update(env or {})
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def assert_relaxed(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout == "", result.stdout


def assert_gated(result: subprocess.CompletedProcess[str], reason: str = "") -> None:
    """The call got the worst case: with no checkpoint marker, F501, saying
    that the sandbox is not verified (and why) and how to turn it on."""
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED"), result.stderr
    assert "strict sandbox is not verified" in result.stderr, result.stderr
    assert "hooks/README.md (The strict sandbox)" in result.stderr
    assert "Take a checkpoint first (git stash create)" not in result.stderr
    assert reason in result.stderr, result.stderr


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, Path]:
    """A project repository, and a user config directory whose settings hold
    the strict sandbox for it."""
    project = _repo(tmp_path / "project")
    config = tmp_path / "config"
    _write(config / "settings.json", strict(project, config))
    return project, config


def _user(config: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((config / "settings.json").read_text())
    return data


CONDITIONS: list[tuple[tuple[str, ...], Any, str]] = [
    (("enabled",), None, "sandbox.enabled is not true"),
    (("enabled",), False, "sandbox.enabled is not true"),
    (("enabled",), "true", "sandbox.enabled is not true"),
    (("failIfUnavailable",), None, "sandbox.failIfUnavailable is not true"),
    (("failIfUnavailable",), False, "sandbox.failIfUnavailable is not true"),
    (
        ("allowUnsandboxedCommands",),
        None,
        "allowUnsandboxedCommands is not false",
    ),
    (
        ("allowUnsandboxedCommands",),
        True,
        "allowUnsandboxedCommands is not false",
    ),
    (("network",), None, "strictAllowlist is not true"),
    (("network", "strictAllowlist"), None, "strictAllowlist is not true"),
    (("network", "strictAllowlist"), False, "strictAllowlist is not true"),
    (("excludedCommands",), ["touch *"], "excludedCommands is set"),
    (("filesystem",), {"disabled": True}, "filesystem.disabled is set"),
    (("filesystem",), {"allowRead": ["/"]}, "filesystem.allowRead is set"),
    (
        ("filesystem",),
        {"allowRead": [os.path.expanduser("~/.config/acs")]},
        "filesystem.allowRead is set",
    ),
    (("credentials",), None, "denies GH_TOKEN"),
    (("network", "allowAllUnixSockets"), True, "allowAllUnixSockets is set"),
    (
        ("network", "allowUnixSockets"),
        ["/var/run/docker.sock"],
        "allowUnixSockets is set",
    ),
    (("network", "allowLocalBinding"), True, "allowLocalBinding is set"),
    (("network", "allowMachLookup"), ["com.apple.x"], "allowMachLookup is set"),
    (("network", "httpProxyPort"), 8080, "httpProxyPort is set"),
    (("network", "socksProxyPort"), 1080, "socksProxyPort is set"),
    (("allowAppleEvents",), True, "allowAppleEvents is set"),
    (("allowNestedUserNamespaces",), True, "allowNestedUserNamespaces is set"),
    (("enableWeakerNestedSandbox",), True, "enableWeakerNestedSandbox is set"),
    (
        ("enableWeakerNetworkIsolation",),
        True,
        "enableWeakerNetworkIsolation is set",
    ),
]
"""Each condition of the strict sandbox, as a key path under sandbox, the
value that breaks it (None: removed), and the reason the hook gives."""


# ─── The strict sandbox relaxes; its absence gates ───


@needs_sandbox_system
class TestStrictUserSandbox:
    def test_read_only_command_is_relaxed(self, setup: tuple[Path, Path]) -> None:
        assert_relaxed(run_hook(*setup))

    def test_no_user_settings_gates_every_bash_call(
        self, setup: tuple[Path, Path]
    ) -> None:
        project, config = setup
        (config / "settings.json").unlink()
        assert_gated(run_hook(project, config), "sandbox.enabled is not true")

    def test_the_classification_still_applies(self, setup: tuple[Path, Path]) -> None:
        project, config = setup
        # A command the classifier reads as a mutate stays one, and its
        # refusal names the checkpoint to take.
        for command in ("ls;", "rm app.txt", "ls > out"):
            result = run_hook(project, config, command)
            assert result.returncode == 2
            assert "Take a checkpoint first (git stash create)" in result.stderr
            assert "not verified" not in result.stderr
        # A checkpoint is allowed, and a git read is an observe.
        assert_relaxed(run_hook(project, config, "git stash create"))
        assert_relaxed(run_hook(project, config, "git status"))

    def test_a_checkpoint_without_the_sandbox_is_a_gated_mutate(
        self, setup: tuple[Path, Path]
    ) -> None:
        project, config = setup
        (config / "settings.json").unlink()
        for command in ("git stash create", "git stash list", "git status"):
            assert_gated(run_hook(project, config, command))

    @pytest.mark.parametrize("path,value,reason", CONDITIONS)
    def test_each_condition_in_user_settings(
        self, setup: tuple[Path, Path], path: tuple[str, ...], value: Any, reason: str
    ) -> None:
        project, config = setup
        settings = _user(config)
        where = settings["sandbox"]
        for key in path[:-1]:
            where = where[key]
        if value is None:
            where.pop(path[-1], None)
        else:
            where[path[-1]] = value
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), reason)

    def test_the_sandbox_must_be_an_object(self, setup: tuple[Path, Path]) -> None:
        project, config = setup
        settings = _user(config)
        settings["sandbox"] = True
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), "sandbox is not an object")

    def test_empty_lists_and_false_flags_keep_it_strict(
        self, setup: tuple[Path, Path]
    ) -> None:
        project, config = setup
        settings = _user(config)
        settings["sandbox"].update(
            {
                "excludedCommands": [],
                "enableWeakerNestedSandbox": False,
                "filesystem": {"disabled": False, "allowWrite": ["/tmp/build"]},
            }
        )
        settings["sandbox"]["network"].update(
            {"allowUnixSockets": [], "allowLocalBinding": False}
        )
        _write(config / "settings.json", settings)
        assert_relaxed(run_hook(project, config))

    def test_home_directory_settings_without_claude_config_dir(
        self, tmp_path: Path
    ) -> None:
        project = _repo(tmp_path / "project")
        home = tmp_path / "home"
        user = home / ".claude"
        _write(user / "settings.json", strict(project, user, home=home))
        env = {**os.environ, "HOME": str(home), "CLAUDE_PROJECT_DIR": str(project)}
        env.pop("CLAUDE_CONFIG_DIR", None)
        env.pop("AUDIT_HMAC_KEY", None)

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["bash", str(HOOK)],
                input=json.dumps(
                    {"tool_name": "Bash", "tool_input": {"command": "ls"}}
                ),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

        assert_relaxed(run())
        # ~/.claude.json, the user's tool servers, needs its rule.
        settings = _user(user)
        settings["permissions"]["deny"] = [
            r
            for r in settings["permissions"]["deny"]
            if not r.endswith("/.claude.json)")
        ]
        _write(user / "settings.json", settings)
        assert_gated(run(), ".claude.json")

    def test_user_settings_inside_the_project(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "project")
        config = project / "cfg"
        _write(config / "settings.json", strict(project, config))
        assert_gated(run_hook(project, config), "inside the project directory")

    def test_a_relative_claude_config_dir(self, setup: tuple[Path, Path]) -> None:
        project, _ = setup
        assert_gated(
            run_hook(project, Path("config")),
            "CLAUDE_CONFIG_DIR is not an absolute path",
        )

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS")
    def test_ostype_that_names_another_system(self, setup: tuple[Path, Path]) -> None:
        """bash takes OSTYPE from the environment: the system is decided from
        files only the system installs, and OSTYPE has to agree."""
        project, config = setup
        assert_gated(
            run_hook(project, config, env={"OSTYPE": "linux-gnu"}),
            "does not name this system",
        )

    @pytest.mark.parametrize(
        "key,value",
        [
            (("permissions", "ask"), "Bash"),
            (("env",), {"A": 1}),
            (("hooks",), []),
            (("sandbox", "network", "httpProxyPort"), "8080"),
            (("sandbox", "filesystem"), {"denyRead": "/x"}),
            (("sandbox", "credentials"), {"envVars": ["GH_TOKEN"]}),
        ],
    )
    def test_a_value_of_the_wrong_type(
        self, setup: tuple[Path, Path], key: tuple[str, ...], value: Any
    ) -> None:
        """Claude Code ignores a file with a value of the wrong type."""
        project, config = setup
        settings = _user(config)
        where = settings
        for k in key[:-1]:
            where = where.setdefault(k, {})
        where[key[-1]] = value
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), "of a type Claude Code does not accept")

    @pytest.mark.parametrize(
        "domain",
        [
            "*",
            "localhost",
            "api.localhost",
            "127.0.0.1",
            "169.254.169.254",
            "[::1]",
            "::1",
            "*.com",
            "metadata.google.internal",
            "0x7f000001",
            "Example.com",
            1,
        ],
    )
    def test_an_allowed_domain_outside_the_boundary(
        self, setup: tuple[Path, Path], domain: Any
    ) -> None:
        project, config = setup
        settings = _user(config)
        settings["sandbox"]["network"]["allowedDomains"].append(domain)
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), "allowedDomains")

    def test_allowed_domains_the_setup_command_writes(
        self, setup: tuple[Path, Path]
    ) -> None:
        project, config = setup
        settings = _user(config)
        settings["sandbox"]["network"]["allowedDomains"] = [
            "example.com",
            "*.example.com",
            "registry.npmjs.org:443",
            "pypi.org.",
            "xn--bcher-kva.example",
        ]
        _write(config / "settings.json", settings)
        assert_relaxed(run_hook(project, config))

    def test_cached_server_managed_settings(self, setup: tuple[Path, Path]) -> None:
        project, config = setup
        _write(config / "remote-settings.json", {})
        assert_gated(run_hook(project, config), "remote-settings.json")


# ─── dangerouslyDisableSandbox ───


@needs_sandbox_system
@pytest.mark.parametrize("value", [True, "true", 1, {}])
def test_a_call_that_asks_to_leave_the_sandbox(
    setup: tuple[Path, Path], value: Any
) -> None:
    """A gated mutate under the strict sandbox too; its refusal says to run
    the call without the parameter or to take a checkpoint, not to set the
    sandbox up."""
    project, config = setup
    for command in ("ls", "git stash create"):
        result = run_hook(
            project,
            config,
            tool_input={"command": command, "dangerouslyDisableSandbox": value},
        )
        assert result.returncode == 2, result.stderr
        assert result.stderr.startswith("F501 CHECKPOINT_REQUIRED"), result.stderr
        assert "sets dangerouslyDisableSandbox" in result.stderr
        assert "git stash create" in result.stderr
        assert "not verified" not in result.stderr
        assert "README.md" not in result.stderr
    # The same call without the parameter is relaxed: no state is kept.
    assert_relaxed(run_hook(project, config))


@needs_sandbox_system
def test_a_call_that_asks_to_leave_an_unverified_sandbox(
    setup: tuple[Path, Path],
) -> None:
    project, config = setup
    (config / "settings.json").unlink()
    result = run_hook(
        project, config, tool_input={"command": "ls", "dangerouslyDisableSandbox": True}
    )
    assert_gated(result, "sandbox.enabled is not true")


@needs_sandbox_system
def test_a_call_that_asks_to_leave_the_sandbox_with_a_checkpoint(
    setup: tuple[Path, Path],
) -> None:
    """With a checkpoint marker, the approval request names the parameter."""
    project, config = setup
    now = int(time.time())
    _write(
        project / ".claude" / "checkpoint.ok",
        {"checkpoint_id": "chk_1", "created_at": now, "expires_at": now + 1800},
    )
    result = run_hook(
        project, config, tool_input={"command": "ls", "dangerouslyDisableSandbox": True}
    )
    assert result.returncode == 0, result.stderr
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "ask"
    assert "sets dangerouslyDisableSandbox" in decision["permissionDecisionReason"]


@needs_sandbox_system
def test_a_call_that_does_not_ask_to_leave_it(setup: tuple[Path, Path]) -> None:
    project, config = setup
    for value in (False, None):
        assert_relaxed(
            run_hook(
                project,
                config,
                tool_input={"command": "ls", "dangerouslyDisableSandbox": value},
            )
        )


# ─── The deny rules ───


@needs_sandbox_system
class TestDenyRules:
    def test_each_required_rule(self, setup: tuple[Path, Path]) -> None:
        """Every rule layer_records.py gives, and every settings, hooks and
        audit key rule, is required: without any one of them, not strict."""
        project, config = setup
        rules = required_rules(project, config)
        assert any(r.startswith("Read(") and r.endswith("/acs/**)") for r in rules)
        for rule in rules:
            settings = _user(config)
            settings["permissions"]["deny"] = [r for r in rules if r != rule]
            _write(config / "settings.json", settings)
            result = run_hook(project, config)
            assert_gated(result, "permissions.deny in user or managed settings has no")
            assert rule in result.stderr, (rule, result.stderr)

    def test_a_rule_over_a_directory_above_covers(
        self, setup: tuple[Path, Path], tmp_path: Path
    ) -> None:
        project, config = setup
        settings = _user(config)
        home = os.path.expanduser("~")
        deny = [
            f"{t}(/{form}/**)" for form in _forms(tmp_path) for t in ("Edit", "Read")
        ]
        deny.append(f"Edit(/{os.path.realpath(HOOK.parent)}/**)")
        deny += [
            f"{t}(/{form}/.config/acs/**)"
            for form in _forms(home)
            for t in ("Edit", "Read")
        ]
        credentials = ("/.ssh/", "/.git-credentials", "/hosts.yml", "/Keychains/")
        deny += [
            r
            for r in required_rules(project, config)
            if any(c in r for c in credentials)
        ]
        settings["permissions"]["deny"] = deny
        _write(config / "settings.json", settings)
        assert_relaxed(run_hook(project, config))

    def test_bare_tool_rules_do_not_count(self, setup: tuple[Path, Path]) -> None:
        project, config = setup
        settings = _user(config)
        settings["permissions"]["deny"] = ["Edit", "Read"]
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), "permissions.deny")

    def test_a_directory_rule_on_a_file_does_not_count(
        self, setup: tuple[Path, Path]
    ) -> None:
        project, config = setup
        rules = required_rules(project, config)
        marker = f"Edit(/{os.path.abspath(project)}/.claude/checkpoint.ok)"
        settings = _user(config)
        settings["permissions"]["deny"] = [
            r[:-1] + "/**)" if r == marker else r for r in rules
        ]
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), "checkpoint.ok")

    def test_a_linked_user_settings_file(self, setup: tuple[Path, Path]) -> None:
        project, config = setup
        target = config / "real.json"
        (config / "settings.json").rename(target)
        (config / "settings.json").symlink_to(target)
        assert_gated(run_hook(project, config), "is a symbolic link")

    @pytest.mark.parametrize(
        "spell",
        [
            lambda p: f"Edit({p})",  # one slash: relative to the settings file
            lambda p: f"Edit(/{p}*)",  # another glob
            lambda p: f"Edit(/{p}/*)",
            lambda p: f"Write(/{p})",  # another tool
        ],
    )
    def test_other_spellings_do_not_count(
        self, setup: tuple[Path, Path], spell: Any
    ) -> None:
        project, config = setup
        rules = required_rules(project, config)
        marker = f"Edit(/{os.path.abspath(project)}/.claude/checkpoint.ok)"
        assert marker in rules
        settings = _user(config)
        settings["permissions"]["deny"] = [
            spell(r[len("Edit(/") : -1]) if r == marker else r for r in rules
        ]
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), "checkpoint.ok")

    def test_rules_from_the_project_do_not_count(
        self, setup: tuple[Path, Path]
    ) -> None:
        project, config = setup
        rules = required_rules(project, config)
        settings = _user(config)
        settings["permissions"]["deny"] = []
        _write(config / "settings.json", settings)
        _write(project / ".claude" / "settings.json", {"permissions": {"deny": rules}})
        _write(
            project / ".claude" / "settings.local.json",
            {"permissions": {"deny": rules}},
        )
        assert_gated(
            run_hook(project, config),
            "permissions.deny in user or managed settings has no",
        )

    def test_a_linked_worktree(self, tmp_path: Path) -> None:
        main = _repo(tmp_path / "main")
        _git(main, "worktree", "add", "-q", str(tmp_path / "wt"))
        project = tmp_path / "wt"
        config = tmp_path / "config"
        main_local = Path(os.path.realpath(main)) / ".claude" / "settings.local.json"
        _write(
            config / "settings.json", strict(project, config, local_files=(main_local,))
        )
        assert_relaxed(run_hook(project, config))
        # The main checkout's local settings file needs its rule too.
        _write(config / "settings.json", strict(project, config))
        assert_gated(run_hook(project, config), "main/.claude/settings.local.json")
        # And the main checkout's records are its own: the worktree's rules
        # alone do not cover the main checkout as a project.
        _write(
            config / "settings.json", strict(project, config, local_files=(main_local,))
        )
        assert_gated(run_hook(main, config), "permissions.deny")

    def test_a_submodule(self, tmp_path: Path) -> None:
        sub = _repo(tmp_path / "sub")
        project = _repo(tmp_path / "project")
        _git(
            project,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(sub),
            "sub",
        )
        config = tmp_path / "config"
        rules = required_rules(project, config)
        assert any("/modules/sub/acs/**" in r for r in rules)
        _write(config / "settings.json", strict(project, config))
        assert_relaxed(run_hook(project, config))
        settings = _user(config)
        settings["permissions"]["deny"] = [
            r for r in rules if "/modules/sub/acs/" not in r
        ]
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), "/modules/sub/acs/**")

    def test_a_project_reached_through_a_symbolic_link(self, tmp_path: Path) -> None:
        real = _repo(tmp_path / "real")
        project = tmp_path / "link"
        project.symlink_to(real)
        config = tmp_path / "config"
        rules = required_rules(project, config)
        assert f"Edit(/{project}/.claude/checkpoint.ok)" in rules
        assert f"Edit(/{os.path.realpath(real)}/.claude/checkpoint.ok)" in rules
        _write(config / "settings.json", strict(project, config))
        assert_relaxed(run_hook(project, config))
        settings = _user(config)
        settings["permissions"]["deny"] = [
            r for r in rules if not r.startswith(f"Edit(/{project}/")
        ]
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), str(project))

    def test_no_repository(self, tmp_path: Path) -> None:
        project = tmp_path / "plain"
        project.mkdir()
        config = tmp_path / "config"
        _write(config / "settings.json", strict(project, config))
        assert_relaxed(run_hook(project, config))

    def test_the_hook_scripts_directory(
        self, setup: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """The rule names the directory the running hook is in."""
        project, config = setup
        copy = tmp_path / "plugin" / "hooks"
        copy.mkdir(parents=True)
        shutil.copy(HOOK, copy / HOOK.name)
        assert_gated(
            run_hook(project, config, hook=copy / HOOK.name),
            str(os.path.realpath(copy)),
        )
        _write(config / "settings.json", strict(project, config, hooks_dir=copy))
        assert_relaxed(run_hook(project, config, hook=copy / HOOK.name))

    def test_audit_hmac_key_needs_an_environment_deny(
        self, setup: tuple[Path, Path]
    ) -> None:
        project, config = setup
        env = {"AUDIT_HMAC_KEY": "a-key-of-the-person-0123456789"}
        assert_gated(run_hook(project, config, env=env), "denies AUDIT_HMAC_KEY")
        settings = _user(config)
        settings["sandbox"]["credentials"]["envVars"].append(
            {"name": "AUDIT_HMAC_KEY", "mode": "deny"}
        )
        _write(config / "settings.json", settings)
        assert_relaxed(run_hook(project, config, env=env))

    @pytest.mark.parametrize("name", ["GH_TOKEN", "GITHUB_TOKEN"])
    def test_the_token_variables_need_an_environment_deny(
        self, setup: tuple[Path, Path], name: str
    ) -> None:
        project, config = setup
        settings = _user(config)
        envvars = settings["sandbox"]["credentials"]["envVars"]
        settings["sandbox"]["credentials"]["envVars"] = [
            e for e in envvars if e["name"] != name
        ]
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), f"denies {name}")
        envvars = [e for e in envvars if e["name"] != name]
        envvars.append({"name": name, "mode": "allow"})
        settings["sandbox"]["credentials"]["envVars"] = envvars
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), f"denies {name}")

    def test_sandbox_filesystem_lists_count_as_denials(
        self, setup: tuple[Path, Path]
    ) -> None:
        """The setup command's form: a path in sandbox.filesystem.denyWrite
        (for an Edit rule) or denyRead (for a Read rule), as written, at or
        above the path, counts as its rule; in project settings it does not."""
        project, config = setup
        rules = required_rules(project, config)
        settings = _user(config)
        write: list[str] = []
        read: list[str] = []
        for rule in rules:
            tool, path = rule[: rule.index("(")], rule[rule.index("(") + 2 : -1]
            path = path.removesuffix("/**")
            (write if tool == "Edit" else read).append(path)
        settings["permissions"]["deny"] = []
        settings["sandbox"]["filesystem"] = {"denyWrite": write, "denyRead": read}
        _write(config / "settings.json", settings)
        assert_relaxed(run_hook(project, config))
        # A glob, a relative or a // path does not count.
        for spell in ("{}/*", "{}*", ".{}", "/{}"):
            bad = dict(settings["sandbox"]["filesystem"])
            bad["denyRead"] = [spell.format(read[0])] + read[1:]
            settings["sandbox"]["filesystem"] = bad
            _write(config / "settings.json", settings)
            assert_gated(run_hook(project, config), read[0])
        # The same lists in project settings do not count.
        settings["sandbox"].pop("filesystem")
        _write(config / "settings.json", settings)
        _write(
            project / ".claude" / "settings.json",
            {"sandbox": {"filesystem": {"denyWrite": write, "denyRead": read}}},
        )
        assert_gated(run_hook(project, config), "permissions.deny")

    def test_a_tool_server_definition_in_the_project(
        self, setup: tuple[Path, Path]
    ) -> None:
        """A .mcp.json names server code in the repository, which runs outside
        the sandbox: the project directory must be denied to writes."""
        project, config = setup
        _write(project / ".mcp.json", {"mcpServers": {}})
        assert_gated(run_hook(project, config), ".mcp.json names tool servers")
        settings = _user(config)
        settings["sandbox"]["filesystem"] = {
            "denyWrite": _forms(project),
        }
        _write(config / "settings.json", settings)
        assert_relaxed(run_hook(project, config))

    def test_no_tool_server_definition_may_be_written(
        self, setup: tuple[Path, Path]
    ) -> None:
        """Where the project holds no .mcp.json, its path must be denied to
        writes: a sandboxed command could otherwise create one whose tool
        servers the next session starts outside the sandbox."""
        project, config = setup
        settings = _user(config)
        settings["permissions"]["deny"] = [
            rule for rule in settings["permissions"]["deny"] if ".mcp.json" not in rule
        ]
        _write(config / "settings.json", settings)
        assert_gated(run_hook(project, config), ".mcp.json written there")

    @pytest.mark.parametrize(
        "setting",
        [
            {"enableAllProjectMcpServers": True},
            {"enabledMcpjsonServers": ["server"]},
        ],
    )
    def test_user_settings_that_start_project_tool_servers(
        self, setup: tuple[Path, Path], setting: dict[str, Any]
    ) -> None:
        """Tool servers a .mcp.json names start with no prompt under these
        user settings, so they are not strict, with or without a .mcp.json."""
        project, config = setup
        _write(config / "settings.json", {**_user(config), **setting})
        assert not (project / ".mcp.json").exists()
        assert_gated(run_hook(project, config), "enableAllProjectMcpServers")

    def test_allow_managed_permission_rules_only(
        self, setup: tuple[Path, Path], tmp_path: Path
    ) -> None:
        project, config = setup
        hook, managed = _hook_with_managed(tmp_path)
        _write(config / "settings.json", strict(project, config, hooks_dir=hook.parent))
        _write(
            managed / "managed-settings.json", {"allowManagedPermissionRulesOnly": True}
        )
        assert_gated(run_hook(project, config, hook=hook), "permissions.deny")
        _write(
            managed / "managed-settings.json",
            {
                "allowManagedPermissionRulesOnly": True,
                "permissions": {
                    "deny": required_rules(project, config, hooks_dir=hook.parent)
                },
            },
        )
        assert_relaxed(run_hook(project, config, hook=hook))


# ─── Project and local settings can only weaken ───

WEAKENINGS: list[tuple[dict[str, Any], str]] = [
    ({"sandbox": {"enabled": False}}, "changes the sandbox"),
    ({"sandbox": {"excludedCommands": ["touch *"]}}, "changes the sandbox"),
    ({"sandbox": {"filesystem": {"allowWrite": ["~/"]}}}, "changes the sandbox"),
    ({"sandbox": {"filesystem": {"allowRead": ["~/.ssh"]}}}, "changes the sandbox"),
    ({"sandbox": {"allowUnsandboxedCommands": True}}, "changes the sandbox"),
    ({"sandbox": {"failIfUnavailable": False}}, "changes the sandbox"),
    ({"sandbox": {"network": {"strictAllowlist": False}}}, "changes the sandbox"),
    (
        {"sandbox": {"network": {"allowedDomains": ["www.iana.org"]}}},
        "changes the sandbox",
    ),
    ({"sandbox": {"network": {"allowLocalBinding": True}}}, "changes the sandbox"),
    ({"sandbox": {"enableWeakerNestedSandbox": True}}, "changes the sandbox"),
    ({"sandbox": "off"}, "changes the sandbox"),
    ({"sandbox": {"ignoreViolations": {"*": ["/"]}}}, "changes the sandbox"),
    ({"permissions": {"additionalDirectories": ["~"]}}, "additionalDirectories"),
    ({"permissions": {"allow": ["Edit(~/**)"]}}, "permissions.allow rules for Edit"),
    ({"permissions": {"allow": ["Read(//**)"]}}, "permissions.allow rules for Edit"),
    ({"permissions": {"allow": ["Edit"]}}, "permissions.allow rules for Edit"),
    ({"permissions": {"allow": "Edit(~/**)"}}, "permissions.allow rules for Edit"),
    (
        {
            "sandbox": {
                "credentials": {
                    "envVars": [{"name": "AUDIT_HMAC_KEY", "mode": "allow"}]
                }
            }
        },
        "changes the sandbox",
    ),
    (
        {"sandbox": {"credentials": {"files": [{"path": "~/.ssh", "mode": "allow"}]}}},
        "changes the sandbox",
    ),
    ({"sandbox": {"credentials": {"envVars": [{"name": "X"}]}}}, "changes the sandbox"),
    ({"hooks": {"PreToolUse": []}}, "names commands or tool servers"),
    ({"statusLine": {"type": "command", "command": "x"}}, "names commands"),
    ({"apiKeyHelper": "./key.sh"}, "names commands or tool servers"),
    ({"awsAuthRefresh": "./a.sh"}, "names commands or tool servers"),
    ({"awsCredentialExport": "./a.sh"}, "names commands or tool servers"),
    ({"otelHeadersHelper": "./a.sh"}, "names commands or tool servers"),
    ({"fileSuggestion": {"type": "command", "command": "x"}}, "names commands"),
    ({"enableAllProjectMcpServers": True}, "names commands or tool servers"),
    ({"enabledMcpjsonServers": ["x"]}, "names commands or tool servers"),
]


@needs_sandbox_system
class TestProjectAndLocalSettings:
    @pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
    @pytest.mark.parametrize("weakening,reason", WEAKENINGS)
    def test_a_weakening_over_a_strict_user_sandbox(
        self,
        setup: tuple[Path, Path],
        name: str,
        weakening: dict[str, Any],
        reason: str,
    ) -> None:
        project, config = setup
        _write(project / ".claude" / name, weakening)
        result = run_hook(project, config)
        assert_gated(result, reason)
        assert name in result.stderr

    def test_a_weakening_in_the_main_checkouts_local_settings(
        self, tmp_path: Path
    ) -> None:
        main = _repo(tmp_path / "main")
        _git(main, "worktree", "add", "-q", str(tmp_path / "wt"))
        project = tmp_path / "wt"
        config = tmp_path / "config"
        main_local = Path(os.path.realpath(main)) / ".claude" / "settings.local.json"
        _write(
            config / "settings.json", strict(project, config, local_files=(main_local,))
        )
        _write(
            main / ".claude" / "settings.local.json", {"sandbox": {"enabled": False}}
        )
        assert_gated(
            run_hook(project, config),
            "main/.claude/settings.local.json changes the sandbox",
        )

    def test_a_weakening_in_the_repository_roots_local_settings(
        self, tmp_path: Path
    ) -> None:
        top = _repo(tmp_path / "top")
        project = top / "sub"
        project.mkdir()
        config = tmp_path / "config"
        top_local = Path(os.path.realpath(top)) / ".claude" / "settings.local.json"
        _write(
            config / "settings.json", strict(project, config, local_files=(top_local,))
        )
        assert_relaxed(run_hook(project, config))
        _write(
            top / ".claude" / "settings.local.json",
            {"sandbox": {"excludedCommands": ["ls"]}},
        )
        assert_gated(
            run_hook(project, config),
            "top/.claude/settings.local.json changes the sandbox",
        )

    def test_an_edit_allow_rule_in_the_repository_roots_local_settings(
        self, tmp_path: Path
    ) -> None:
        top = _repo(tmp_path / "top")
        project = top / "sub"
        project.mkdir()
        config = tmp_path / "config"
        top_local = Path(os.path.realpath(top)) / ".claude" / "settings.local.json"
        _write(
            config / "settings.json", strict(project, config, local_files=(top_local,))
        )
        _write(top_local, {"permissions": {"allow": ["Edit(~/**)"]}})
        assert_gated(
            run_hook(project, config),
            "top/.claude/settings.local.json sets permissions.allow rules for Edit",
        )

    @pytest.mark.parametrize(
        "variable", ["CLAUDE_CONFIG_DIR", "HOME", "PATH", "OSTYPE", "BASH_ENV"]
    )
    def test_a_local_file_that_moves_the_user_settings(
        self, tmp_path: Path, variable: str
    ) -> None:
        """A local file outside the project directory (the repository root's)
        that sets the variable naming the user settings in env: the hook
        cannot tell that the user settings it reads are the person's."""
        top = _repo(tmp_path / "top")
        project = top / "sub"
        project.mkdir()
        config = tmp_path / "config"
        top_local = Path(os.path.realpath(top)) / ".claude" / "settings.local.json"
        _write(
            config / "settings.json", strict(project, config, local_files=(top_local,))
        )
        _write(top / ".claude" / "settings.local.json", {"env": {variable: "/x"}})
        assert_gated(
            run_hook(project, config),
            "set variables in env that are not Claude Code's own",
        )
        # A variable that is Claude Code's own is let through.
        _write(
            top / ".claude" / "settings.local.json",
            {"env": {"MAX_THINKING_TOKENS": "1"}},
        )
        assert_relaxed(run_hook(project, config))

    @pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
    def test_the_project_naming_the_user_settings(
        self, setup: tuple[Path, Path], name: str
    ) -> None:
        """The project directory's own files: every call is refused (R407),
        before the sandbox is read."""
        project, config = setup
        _write(project / ".claude" / name, {"env": {"CLAUDE_CONFIG_DIR": str(config)}})
        result = run_hook(project, config)
        assert result.returncode == 2, result.stderr
        assert result.stderr.startswith("R407 SAFETY_CHECK_FAILED"), result.stderr
        assert "CLAUDE_CONFIG_DIR" in result.stderr

    def test_narrowing_settings_keep_it_strict(self, setup: tuple[Path, Path]) -> None:
        project, config = setup
        _write(
            project / ".claude" / "settings.json",
            {
                "sandbox": {
                    "enabled": True,
                    "failIfUnavailable": True,
                    "allowUnsandboxedCommands": False,
                    "autoAllowBashIfSandboxed": False,
                    "excludedCommands": [],
                    "filesystem": {"denyWrite": ["/x"], "denyRead": ["/y"]},
                    "network": {
                        "deniedDomains": ["evil.example"],
                        "strictAllowlist": True,
                    },
                    "credentials": {"envVars": [{"name": "X", "mode": "deny"}]},
                },
                "permissions": {"deny": ["Bash(curl *)"], "allow": ["Bash(ls)"]},
                "hooks": {},
            },
        )
        assert_relaxed(run_hook(project, config))

    def test_a_project_cannot_claim_a_sandbox(self, tmp_path: Path) -> None:
        project = _repo(tmp_path / "project")
        config = tmp_path / "config"
        config.mkdir()
        claim = strict(project, config)
        _write(project / ".claude" / "settings.json", claim)
        assert_gated(run_hook(project, config), "sandbox.enabled is not true")
        _write(project / ".claude" / "settings.local.json", claim)
        assert_gated(run_hook(project, config))


# ─── Files that cannot be read ───


def assert_refused(result: subprocess.CompletedProcess[str], reason: str = "") -> None:
    """Gated (assert_gated), or blocked outright: a project or local settings
    file that jq cannot read blocks every call before any classification
    (R407, the hook's check of the project's env)."""
    if result.stderr.startswith(
        "R407 SAFETY_CHECK_FAILED: the project's settings files"
    ):
        assert result.returncode == 2
        return
    assert_gated(result, reason)


def _settings_path(which: str, project: Path, config: Path) -> Path:
    return {
        "user": config / "settings.json",
        "project": project / ".claude" / "settings.json",
        "local": project / ".claude" / "settings.local.json",
    }[which]


@needs_sandbox_system
class TestUnreadableSettings:
    @pytest.mark.parametrize("which", ["user", "project", "local"])
    @pytest.mark.parametrize(
        "text", ["{", "", "[]", '"sandbox"', "null", "{} {}", '{"a": 1,}']
    )
    def test_a_file_that_is_not_a_json_object(
        self, setup: tuple[Path, Path], which: str, text: str
    ) -> None:
        project, config = setup
        _write(_settings_path(which, project, config), text)
        assert_refused(run_hook(project, config), "is not a JSON object")

    @pytest.mark.parametrize("which", ["user", "project", "local"])
    @pytest.mark.parametrize("kind", ["directory", "fifo", "dangling link"])
    def test_not_a_regular_file(
        self, setup: tuple[Path, Path], which: str, kind: str
    ) -> None:
        project, config = setup
        path = _settings_path(which, project, config)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        if kind == "directory":
            path.mkdir()
        elif kind == "fifo":
            os.mkfifo(path)
        else:
            path.symlink_to(project / "nowhere")
        reason = "is not a regular file"
        if which == "user" and kind == "dangling link":
            reason = "is a symbolic link"
        assert_refused(run_hook(project, config), reason)

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any file"
    )
    @pytest.mark.parametrize("which", ["user", "project", "local"])
    def test_a_file_the_hook_cannot_read(
        self, setup: tuple[Path, Path], which: str
    ) -> None:
        project, config = setup
        path = _settings_path(which, project, config)
        if not path.exists():
            _write(path, {})
        path.chmod(0)
        try:
            assert_refused(
                run_hook(project, config), "is not a regular file this hook can read"
            )
        finally:
            path.chmod(0o600)


# ─── Managed settings ───


def _hook_with_managed(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of the hook whose managed settings directory, and macOS
    managed preferences directory, are under ``tmp_path``."""
    managed = tmp_path / "managed"
    mdm = tmp_path / "mdm"
    text = HOOK.read_text()
    for name, value in (
        ("SANDBOX_MANAGED_DARWIN", managed),
        ("SANDBOX_MANAGED_LINUX", managed),
        ("SANDBOX_MDM_DIR", mdm),
    ):
        text, n = re.subn(rf"^{name}='[^']*'$", f"{name}='{value}'", text, flags=re.M)
        assert n == 1, name
    copy = tmp_path / "plugin" / "hooks" / HOOK.name
    copy.parent.mkdir(parents=True)
    copy.write_text(text)
    return copy, managed


@needs_sandbox_system
class TestManagedSettings:
    @pytest.fixture
    def env(self, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
        project = _repo(tmp_path / "project")
        config = tmp_path / "config"
        hook, managed = _hook_with_managed(tmp_path)
        _write(config / "settings.json", strict(project, config, hooks_dir=hook.parent))
        return project, config, hook, managed

    def test_no_managed_settings(self, env: tuple[Path, Path, Path, Path]) -> None:
        project, config, hook, _ = env
        assert_relaxed(run_hook(project, config, hook=hook))

    def test_managed_settings_alone(self, env: tuple[Path, Path, Path, Path]) -> None:
        project, config, hook, managed = env
        _write(managed / "managed-settings.json", _user(config))
        (config / "settings.json").unlink()
        assert_relaxed(run_hook(project, config, hook=hook))

    @pytest.mark.parametrize("path,value,reason", CONDITIONS)
    def test_each_condition_in_managed_settings_alone(
        self,
        env: tuple[Path, Path, Path, Path],
        path: tuple[str, ...],
        value: Any,
        reason: str,
    ) -> None:
        project, config, hook, managed = env
        settings = _user(config)
        (config / "settings.json").unlink()
        where = settings["sandbox"]
        for key in path[:-1]:
            where = where[key]
        if value is None:
            where.pop(path[-1], None)
        else:
            where[path[-1]] = value
        _write(managed / "managed-settings.json", settings)
        assert_gated(run_hook(project, config, hook=hook), reason)

    def test_managed_settings_override_the_user(
        self, env: tuple[Path, Path, Path, Path]
    ) -> None:
        project, config, hook, managed = env
        _write(managed / "managed-settings.json", {"sandbox": {"enabled": False}})
        assert_gated(
            run_hook(project, config, hook=hook), "sandbox.enabled is not true"
        )

    def test_a_drop_in_file(self, env: tuple[Path, Path, Path, Path]) -> None:
        project, config, hook, managed = env
        _write(managed / "managed-settings.json", {"sandbox": {"enabled": True}})
        _write(
            managed / "managed-settings.d" / "20-x.json",
            {"sandbox": {"excludedCommands": ["git *"]}},
        )
        assert_gated(run_hook(project, config, hook=hook), "excludedCommands is set")
        # A later drop-in replaces an earlier one's value; a hidden one or one
        # not ending in .json is not read.
        (managed / "managed-settings.d" / "20-x.json").unlink()
        _write(
            managed / "managed-settings.d" / "10-a.json",
            {"sandbox": {"enabled": False}},
        )
        _write(
            managed / "managed-settings.d" / "20-b.json", {"sandbox": {"enabled": True}}
        )
        _write(
            managed / "managed-settings.d" / ".hidden.json",
            {"sandbox": {"enabled": False}},
        )
        _write(managed / "managed-settings.d" / "30-c.txt", "{")
        assert_relaxed(run_hook(project, config, hook=hook))

    def test_a_malformed_managed_file(self, env: tuple[Path, Path, Path, Path]) -> None:
        project, config, hook, managed = env
        _write(managed / "managed-settings.d" / "10-a.json", "{")
        assert_gated(run_hook(project, config, hook=hook), "is not a JSON object")

    @pytest.mark.skipif(
        platform.system() != "Darwin", reason="macOS managed preferences"
    )
    def test_a_managed_preferences_profile(
        self, env: tuple[Path, Path, Path, Path], tmp_path: Path
    ) -> None:
        project, config, hook, _ = env
        _write(tmp_path / "mdm" / "com.anthropic.claudecode.plist", "<plist/>")
        assert_gated(
            run_hook(project, config, hook=hook), "managed preferences profile"
        )


# ─── The user-scope spike's settings ───


@needs_sandbox_system
def test_the_user_scope_spikes_settings(tmp_path: Path) -> None:
    """The settings of the user-scope spike (#141): a strict sandbox with a
    relative records rule, and no rules for the settings files or hooks.
    Not strict: the rules the hook needs are absent."""
    project = _repo(tmp_path / "project")
    config = tmp_path / "config"
    _write(
        config / "settings.json",
        {
            "sandbox": {
                "enabled": True,
                "failIfUnavailable": True,
                "allowUnsandboxedCommands": False,
                "autoAllowBashIfSandboxed": True,
                "network": {"allowedDomains": ["example.com"], "strictAllowlist": True},
            },
            "permissions": {"deny": ["Edit(.claude/audit.log)"]},
        },
    )
    assert_gated(
        run_hook(project, config), "permissions.deny in user or managed settings has no"
    )


# ─── The setup command ───


def test_the_refusal_names_no_command_that_does_not_exist() -> None:
    """The refusal and the documents may send the person to the setup
    command only once the plugin ships it."""
    shipped = (ROOT / "commands" / "grounded-setup.md").exists() or (
        ROOT / "skills" / "grounded-setup" / "SKILL.md"
    ).exists()
    for path in (
        HOOK,
        ROOT / "hooks" / "README.md",
        ROOT / "spec" / "SECURITY.md",
        ROOT / "CHANGELOG.md",
        ROOT / "CLAUDE.md",
    ):
        if "/grounded-setup" in path.read_text(encoding="utf-8"):
            assert shipped, f"{path.name} names /grounded-setup, which is not shipped"


@needs_sandbox_system
@pytest.mark.parametrize("layout", ["top", "below-top", "worktree"])
@pytest.mark.parametrize("config_dir", [False, True], ids=["home", "config-dir"])
def test_the_setup_commands_settings_verify(
    tmp_path: Path, layout: str, config_dir: bool
) -> None:
    """The settings the setup command computes for a project make the hook
    relax a read-only command there (runs once that command is in the
    package): for a project at its repository's top level, below it, and in
    a linked worktree, with and without CLAUDE_CONFIG_DIR."""
    setup_settings = pytest.importorskip("grounded_agency.sandbox_settings")
    project = _repo(tmp_path / "project")
    if layout == "below-top":
        project = project / "pkg"
        project.mkdir()
    elif layout == "worktree":
        _git(project, "worktree", "add", "-q", str(tmp_path / "wt"))
        project = tmp_path / "wt"
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    environ = {"HOME": str(home)}
    settings_dir = home / ".claude"
    if config_dir:
        settings_dir = tmp_path / "config"
        settings_dir.mkdir()
        environ["CLAUDE_CONFIG_DIR"] = str(settings_dir)
    computed = setup_settings.compute_settings(
        str(project),
        str(home),
        sys.platform,
        str(ROOT),
        extra_domains=("example.com",),
        environ=environ,
    )
    _write(settings_dir / "settings.json", computed.settings)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.pop("AUDIT_HMAC_KEY", None)
    env.update(environ)
    done = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert_relaxed(done)
