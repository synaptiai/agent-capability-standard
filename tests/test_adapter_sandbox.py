"""The operating-system boundary of Bash in the Python adapter (STANDARD
1.2.0 section 5.18.3, RFC-0011).

``wrap_options()`` turns on a strict sandbox where the options carry none
of their own and adds deny rules for the layer's records; the Bash
classifier relaxes a call only while the options the adapter built, and the
settings files the CLI loads beside them, hold every property of the
boundary. Otherwise every Bash call is its worst case.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._internal.transport.subprocess_cli import (
    SubprocessCLITransport,
)

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig, layer_records
from grounded_agency.capabilities.mapper import ToolCapabilityMapper
from grounded_agency.utils import sandbox as sandbox_module
from grounded_agency.utils.sandbox import (
    CHECKED_PERMISSION_MODES,
    CREDENTIAL_ENV_VARS,
    boundary_faults,
    flag_settings,
)

_UNREAD_POLICY_SOURCES = sandbox_module.unread_policy_sources


@pytest.fixture(autouse=True)
def _own_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home directory of the test's own, no Claude Code configuration
    directory or credential locations from the environment, no
    ``CLAUDE_CODE_SANDBOX`` variable, and no managed settings or policy
    source of the machine's: what the boundary protects and reads is the
    test's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for name in ("CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "GH_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    for name in [n for n in os.environ if n.startswith("CLAUDE_CODE_SANDBOX")]:
        monkeypatch.delenv(name)
    monkeypatch.setattr(sandbox_module, "managed_settings_files", lambda: [])
    monkeypatch.setattr(sandbox_module, "unread_policy_sources", lambda env=None: [])
    return home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    where = tmp_path / "project"
    where.mkdir()
    return where


def _adapter(tmp_path: Path, **config: Any) -> GroundedAgentAdapter:
    return GroundedAgentAdapter(
        GroundedAgentConfig(
            checkpoint_dir=str(tmp_path / "records" / "checkpoints"),
            audit_log_path=str(tmp_path / "records" / "audit.log"),
            **config,
        )
    )


def _options(project: Path, **kwargs: Any) -> ClaudeAgentOptions:
    kwargs.setdefault("setting_sources", [])
    return ClaudeAgentOptions(cwd=str(project), **kwargs)


def _bash(adapter: GroundedAgentAdapter, command: str, **extra: Any) -> Any:
    return adapter.mapper.map_tool("Bash", {"command": command, **extra})


def _relaxed(adapter: GroundedAgentAdapter) -> bool:
    """Whether `ls` is an observation and `git stash create` a checkpoint
    (the classifier relaxes), rather than both Bash's worst case."""
    ls = _bash(adapter, "ls")
    stash = _bash(adapter, "git stash create")
    if ls.capability_id == "observe":
        assert stash.capability_id == "checkpoint"
        return True
    for mapping in (ls, stash):
        assert {"mutate", "send"} <= set(mapping.capabilities)
        assert mapping.requires_checkpoint and mapping.requires_approval
    return False


def _deny(options: Any) -> list[str]:
    return list(json.loads(options.settings)["permissions"]["deny"])


# --- the default -----------------------------------------------------------


def test_default_options_get_the_strict_sandbox(tmp_path: Path, project: Path) -> None:
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project))
    sandbox = wrapped.sandbox
    assert sandbox["enabled"] is True
    assert sandbox["failIfUnavailable"] is True
    assert sandbox["allowUnsandboxedCommands"] is False
    assert sandbox["autoAllowBashIfSandboxed"] is False
    assert sandbox["filesystem"].get("allowWrite") is None
    assert sandbox["excludedCommands"] == []
    assert sandbox["network"]["strictAllowlist"] is True
    assert sandbox["network"]["allowedDomains"] == []
    home = os.path.realpath(os.environ["HOME"])
    files = {e["path"] for e in sandbox["credentials"]["files"]}
    for path in (
        f"{home}/Library/Keychains",
        "/Library/Keychains",
        f"{home}/.ssh",
        f"{home}/.config/gh",
        f"{home}/.git-credentials",
        f"{home}/.config/git/credentials",
        f"{home}/.config/acs/audit.key",
    ):
        assert path in files
        assert path in sandbox["filesystem"]["denyRead"]
    unset = {e["name"] for e in sandbox["credentials"]["envVars"]}
    assert set(CREDENTIAL_ENV_VARS) <= unset
    assert {"GH_TOKEN", "GITHUB_TOKEN", "AUDIT_HMAC_KEY"} <= set(CREDENTIAL_ENV_VARS)
    # Every variable of the environment named like a credential, and no
    # other.
    for name in unset - set(CREDENTIAL_ENV_VARS):
        assert sandbox_module.CREDENTIAL_NAME.search(name)
    for name in os.environ:
        if sandbox_module.CREDENTIAL_NAME.search(name):
            assert name in unset
    # Deny rules for the records: literal absolute paths, Edit and Read.
    deny = _deny(wrapped)
    records = os.path.realpath(tmp_path / "records")
    for name in ("checkpoints", "audit.log"):
        assert f"Edit(/{records}/{name})" in deny
        assert f"Read(/{records}/{name})" in deny
    assert f"Edit(/{os.path.realpath(project)}/.claude)" in deny
    assert f"Read(/{home}/.ssh)" in deny
    # The plugin hooks' records: the rules and denyWrite paths
    # layer_records gives, as it gives them. Their directory rules are the
    # only ones with a glob.
    fragment = layer_records.deny_settings(str(project))
    hooks_rules = fragment["permissions"]["deny"]
    assert f"Edit(/{os.path.realpath(project)}/.claude/checkpoints/**)" in hooks_rules
    assert all(rule in deny for rule in hooks_rules)
    assert [r for r in deny if "*" in r] == [r for r in hooks_rules if "*" in r]
    assert all(r.endswith("/**)") for r in deny if "*" in r)
    assert (
        sandbox["filesystem"]["denyWrite"]
        == fragment["sandbox"]["filesystem"]["denyWrite"]
    )
    assert (
        boundary_faults(flag_settings(wrapped), adapter._wrapped_boundaries[0].paths)
        == []
    )
    assert _relaxed(adapter)


def test_the_cli_is_started_with_the_sandbox_and_the_deny_rules(
    tmp_path: Path, project: Path
) -> None:
    """The settings reach the command line the Agent SDK builds."""
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, cli_path="/usr/bin/true"))
    command = SubprocessCLITransport(prompt="x", options=wrapped)._build_command()
    settings = json.loads(command[command.index("--settings") + 1])
    assert settings["sandbox"] == wrapped.sandbox
    assert settings["sandbox"]["network"]["strictAllowlist"] is True
    assert settings["sandbox"]["failIfUnavailable"] is True
    assert settings["permissions"]["deny"] == _deny(wrapped)


def test_records_in_a_repository_name_its_real_git_directories(
    tmp_path: Path, project: Path
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(project)], check=True)
    adapter = _adapter(tmp_path)
    deny = _deny(adapter.wrap_options(_options(project)))
    git_dir = os.path.realpath(project / ".git")
    for rule in (
        f"Edit(/{git_dir}/acs/**)",
        f"Read(/{git_dir}/acs/**)",
        f"Edit(/{git_dir}/config)",
        f"Edit(/{git_dir}/hooks)",
    ):
        assert rule in deny


def test_before_any_wrap_every_bash_call_is_the_worst_case(tmp_path: Path) -> None:
    assert not _relaxed(_adapter(tmp_path))
    mapper = ToolCapabilityMapper()
    assert mapper.os_boundary is None
    assert {"mutate", "send"} <= set(
        mapper.map_tool("Bash", {"command": "ls"}).capabilities
    )


def test_a_check_that_fails_is_the_worst_case() -> None:
    mapper = ToolCapabilityMapper()

    def broken() -> bool:
        raise OSError("cannot read")

    mapper.os_boundary = broken
    assert mapper.map_tool("Bash", {"command": "ls"}).capability_id != "observe"
    mapper.os_boundary = lambda: True
    assert mapper.map_tool("Bash", {"command": "ls"}).capability_id == "observe"


# --- dangerouslyDisableSandbox --------------------------------------------


@pytest.mark.parametrize("value", [True, "true", 1, None, "false"])
def test_a_call_asking_to_leave_the_sandbox_is_the_worst_case(
    tmp_path: Path, project: Path, value: Any
) -> None:
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    for command in ("ls", "git stash create"):
        mapping = _bash(adapter, command, dangerouslyDisableSandbox=value)
        assert {"mutate", "send"} <= set(mapping.capabilities)
        assert mapping.requires_checkpoint and mapping.requires_approval
    # false is no request: the call is classified as usual.
    assert _bash(adapter, "ls", dangerouslyDisableSandbox=False).capability_id == (
        "observe"
    )


# --- a caller's own sandbox -----------------------------------------------


def test_a_callers_own_sandbox_is_kept(tmp_path: Path, project: Path) -> None:
    own = {"enabled": True, "autoAllowBashIfSandboxed": True}
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, sandbox=own))
    assert wrapped.sandbox == own
    # The deny rules are added all the same.
    assert _deny(wrapped)
    # It lacks the boundary's properties: the classifier does not relax.
    assert not _relaxed(adapter)


def test_a_callers_sandbox_without_the_records_deny_write_is_not_verified(
    tmp_path: Path, project: Path
) -> None:
    """The adapter adds nothing to a caller's sandbox: it is verified only
    when its denyWrite holds every path layer_records gives."""
    strict = _adapter(tmp_path).wrap_options(_options(project)).sandbox
    deny_write = layer_records.deny_settings(str(project))["sandbox"]["filesystem"][
        "denyWrite"
    ]
    assert strict["filesystem"]["denyWrite"] == deny_write
    own = copy.deepcopy(strict)
    own["filesystem"]["denyWrite"] = deny_write[:-1]
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, sandbox=own))
    assert wrapped.sandbox["filesystem"]["denyWrite"] == deny_write[:-1]
    assert f"the sandbox does not deny writing {deny_write[-1]}" in (
        adapter._wrapped_boundaries[0].faults
    )
    assert not _relaxed(adapter)


def test_a_sandbox_in_the_callers_settings_is_kept(
    tmp_path: Path, project: Path
) -> None:
    own = {"sandbox": {"enabled": False}, "permissions": {"deny": ["Bash(rm:*)"]}}
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, settings=json.dumps(own)))
    # No options.sandbox: the SDK would put it in place of the settings'.
    assert wrapped.sandbox is None
    settings = json.loads(wrapped.settings)
    assert settings["sandbox"] == {"enabled": False}
    assert settings["permissions"]["deny"][0] == "Bash(rm:*)"
    assert len(settings["permissions"]["deny"]) > 1
    assert not _relaxed(adapter)


def test_a_callers_sandbox_with_every_property_is_verified(
    tmp_path: Path, project: Path
) -> None:
    strict = _adapter(tmp_path).wrap_options(_options(project)).sandbox
    own = copy.deepcopy(strict)
    own["network"]["allowedDomains"] = ["pypi.org"]
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, sandbox=own))
    assert wrapped.sandbox is own
    assert _relaxed(adapter)


def test_a_settings_file_is_read_and_passed_inline(
    tmp_path: Path, project: Path
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": "x", "permissions": {"allow": ["Read"]}}))
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, settings=str(path)))
    settings = json.loads(wrapped.settings)
    assert settings["model"] == "x"
    assert settings["permissions"]["allow"] == ["Read"]
    assert settings["permissions"]["deny"]
    assert _relaxed(adapter)


def test_settings_that_cannot_be_read_are_passed_on_and_not_verified(
    tmp_path: Path, project: Path
) -> None:
    missing = str(tmp_path / "missing.json")
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, settings=missing))
    assert wrapped.settings == missing
    assert wrapped.sandbox is None
    assert not _relaxed(adapter)


def test_wrapping_again_adds_no_rule_twice(tmp_path: Path, project: Path) -> None:
    adapter = _adapter(tmp_path)
    once = adapter.wrap_options(_options(project))
    twice = adapter.wrap_options(once)
    assert _deny(twice) == _deny(once)
    assert twice.sandbox == once.sandbox
    assert _relaxed(adapter)


# --- a weak sandbox -------------------------------------------------------


def _set(document: dict[str, Any], path: str, value: Any) -> None:
    *parents, last = path.split(".")
    for key in parents:
        document = document.setdefault(key, {})
    if value is _DELETE:
        document.pop(last, None)
    else:
        document[last] = value


_DELETE = object()

WEAKENINGS: list[tuple[str, Any]] = [
    ("enabled", False),
    ("enabled", _DELETE),
    ("failIfUnavailable", False),
    ("failIfUnavailable", _DELETE),
    ("autoAllowBashIfSandboxed", True),
    ("autoAllowBashIfSandboxed", _DELETE),
    ("allowUnsandboxedCommands", True),
    ("allowUnsandboxedCommands", _DELETE),
    ("excludedCommands", ["ls *"]),
    ("enableWeakerNestedSandbox", True),
    ("enableWeakerNetworkIsolation", True),
    ("allowNestedUserNamespaces", True),
    ("allowAppleEvents", True),
    ("network.strictAllowlist", False),
    ("network.strictAllowlist", _DELETE),
    ("network.allowUnixSockets", ["/var/run/docker.sock"]),
    ("network.allowAllUnixSockets", True),
    ("network.allowLocalBinding", True),
    ("network.allowMachLookup", ["*"]),
    ("network.httpProxyPort", 8080),
    ("network.socksProxyPort", 1080),
    ("network.allowedDomains", ["localhost"]),
    ("network.allowedDomains", ["127.0.0.1"]),
    ("network.allowedDomains", ["169.254.169.254"]),
    ("network.allowedDomains", ["*"]),
    ("network.allowedDomains", ["metadata.google.internal"]),
    ("network.allowedDomains", ["localhost."]),
    ("network.allowedDomains", ["0x7f000001"]),
    ("network.allowedDomains", ["foo.local."]),
    ("network.allowedDomains", ["*.*"]),
    ("network.allowedDomains", ["pypi.org:443"]),
    ("network.allowedDomains", ["metadata.tencentyun.com"]),
    ("network.allowedDomains", [""]),
    ("network.allowedDomains", "pypi.org"),
    ("filesystem.disabled", True),
    ("filesystem.allowRead", ["~/.ssh"]),
    ("filesystem.allowWrite", ["/"]),
    ("credentials.envVars", []),
    ("credentials.files", []),
    ("filesystem.denyRead", []),
    ("filesystem.denyWrite", []),
    ("filesystem.denyWrite", _DELETE),
]


@pytest.mark.parametrize(("path", "value"), WEAKENINGS)
def test_a_sandbox_missing_a_property_is_not_verified(
    tmp_path: Path, project: Path, path: str, value: Any
) -> None:
    strict = _adapter(tmp_path).wrap_options(_options(project)).sandbox
    weak = copy.deepcopy(strict)
    _set(weak, path, value)
    if path == "credentials.files":
        # The denyRead entries alone still keep the files unreadable.
        weak["filesystem"]["denyRead"] = []
    if path == "filesystem.denyRead":
        weak["credentials"]["files"] = weak["credentials"]["files"][1:]
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, sandbox=weak))
    assert boundary_faults(flag_settings(wrapped), adapter._wrapped_boundaries[0].paths)
    assert not _relaxed(adapter)


def test_a_missing_deny_rule_is_not_verified(tmp_path: Path, project: Path) -> None:
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project))
    paths = adapter._wrapped_boundaries[0].paths
    settings = flag_settings(wrapped)
    assert settings is not None
    deny = settings["permissions"]["deny"]
    for rule in list(deny):
        fewer = {**settings, "permissions": {"deny": [r for r in deny if r != rule]}}
        assert boundary_faults(fewer, paths) == [f"permissions.deny has no {rule}"]


def test_a_missing_deny_write_path_is_not_verified(
    tmp_path: Path, project: Path
) -> None:
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project))
    paths = adapter._wrapped_boundaries[0].paths
    settings = flag_settings(wrapped)
    assert settings is not None
    deny_write = settings["sandbox"]["filesystem"]["denyWrite"]
    assert deny_write
    for path in list(deny_write):
        fewer = copy.deepcopy(settings)
        fewer["sandbox"]["filesystem"]["denyWrite"] = [
            p for p in deny_write if p != path
        ]
        assert boundary_faults(fewer, paths) == [
            f"the sandbox does not deny writing {path}"
        ]


@pytest.mark.parametrize(
    "key",
    [
        "settings",
        "setting-sources",
        "allowedTools",
        "allowed-tools",
        "add-dir",
        "plugin-dir",
        "mcp-config",
        "permission-mode",
        "dangerously-skip-permissions",
        "verbose",
    ],
)
def test_extra_args_are_not_verified(tmp_path: Path, project: Path, key: str) -> None:
    """The SDK passes extra_args after its own flags, so any of them can
    override what the options set: only a flag known to change none of it
    passes."""
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, extra_args={key: "user,project,local"}))
    assert not _relaxed(adapter)


def test_a_harmless_extra_arg_is_verified(tmp_path: Path, project: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, extra_args={"debug-to-stderr": None}))
    assert _relaxed(adapter)


def test_added_directories_are_not_verified(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    """The CLI lets a sandboxed command write each directory added to the
    session."""
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, add_dirs=[str(_own_home)]))
    assert not _relaxed(adapter)
    adapter = _adapter(tmp_path)
    own = json.dumps({"permissions": {"additionalDirectories": [str(_own_home)]}})
    adapter.wrap_options(_options(project, settings=own))
    assert not _relaxed(adapter)
    _write(
        project / ".claude" / "settings.json",
        {"permissions": {"additionalDirectories": ["/"]}},
    )
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert not _relaxed(adapter)


def test_every_wrapped_options_must_hold_it(tmp_path: Path, project: Path) -> None:
    """The mapper is the adapter's: one wrap without the boundary stops the
    relaxation for every session it serves."""
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    adapter.wrap_options(_options(project, sandbox={"enabled": True}))
    assert not _relaxed(adapter)


# --- no sandbox -----------------------------------------------------------


def test_with_the_sandbox_off_every_bash_call_is_the_worst_case(
    tmp_path: Path, project: Path
) -> None:
    adapter = _adapter(tmp_path, sandbox=False)
    wrapped = adapter.wrap_options(_options(project))
    assert wrapped.sandbox is None
    assert _deny(wrapped)
    assert not _relaxed(adapter)


# --- the network allowlist and destination policies -----------------------


def test_an_allowlist_is_passed_and_verified(tmp_path: Path, project: Path) -> None:
    adapter = _adapter(tmp_path, sandbox_allowed_domains=["pypi.org", "*.github.com"])
    wrapped = adapter.wrap_options(_options(project))
    assert wrapped.sandbox["network"]["allowedDomains"] == ["pypi.org", "*.github.com"]
    assert _relaxed(adapter)


def test_an_allowlist_under_a_destination_policy_is_not_verified(
    tmp_path: Path, project: Path
) -> None:
    adapter = _adapter(
        tmp_path,
        sandbox_allowed_domains=["pypi.org"],
        allowed_destinations=["https://pypi.org/*"],
    )
    adapter.wrap_options(_options(project))
    assert not _relaxed(adapter)
    # An empty allowlist reaches no host, so the policy changes nothing.
    adapter = _adapter(tmp_path, allowed_destinations=["https://pypi.org/*"])
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)


def test_the_allowlist_must_be_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        GroundedAgentConfig(sandbox_allowed_domains="pypi.org")
    with pytest.raises(ValueError):
        GroundedAgentConfig(sandbox_allowed_domains=[""])


# --- the other settings sources --------------------------------------------


def _write(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document) if not isinstance(document, str) else document)


@pytest.mark.parametrize(
    "weakening",
    [
        {"enabled": False},
        {"allowUnsandboxedCommands": True},
        {"excludedCommands": ["ls *"]},
        {"network": {"allowedDomains": ["example.com"]}},
        {"network": {"strictAllowlist": False}},
        {"filesystem": {"allowRead": ["/"]}},
        {"filesystem": {"allowWrite": ["/"]}},
    ],
)
@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_a_project_settings_file_that_weakens_it(
    tmp_path: Path, project: Path, weakening: dict[str, Any], name: str
) -> None:
    _write(project / ".claude" / name, {"sandbox": weakening})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=None))
    assert not _relaxed(adapter)
    # A host that does not load the project's settings is not affected.
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["user"]))
    assert _relaxed(adapter)


def test_a_settings_file_that_changed_since_the_wrap(
    tmp_path: Path, project: Path
) -> None:
    """The CLI may have loaded a file before it changed, or reload it after:
    a change of any file the options load leaves the boundary unverified,
    whatever the file now says, until it holds what it held at the wrap."""
    settings = project / ".claude" / "settings.json"
    _write(settings, {"model": "x"})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert _relaxed(adapter)
    _write(settings, {"sandbox": {"enabled": True}})
    assert not _relaxed(adapter)
    settings.unlink()
    assert not _relaxed(adapter)
    _write(settings, {"model": "x"})
    assert _relaxed(adapter)
    # A file that appears where there was none counts too.
    _write(project / ".claude" / "settings.local.json", "{}")
    assert _relaxed(adapter)  # not a source these options load
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["local"]))
    (project / ".claude" / "settings.local.json").unlink()
    assert not _relaxed(adapter)


def test_a_settings_file_that_cannot_be_read(tmp_path: Path, project: Path) -> None:
    _write(project / ".claude" / "settings.json", "{ not json")
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert not _relaxed(adapter)


def test_the_users_settings_file(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    config = tmp_path / "config"
    _write(config / "settings.json", {"sandbox": {"excludedCommands": ["git *"]}})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(
        _options(
            project,
            setting_sources=["user"],
            env={"CLAUDE_CONFIG_DIR": str(config)},
        )
    )
    assert not _relaxed(adapter)
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["user"]))
    assert _relaxed(adapter)


def test_managed_settings_that_weaken_it(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed = tmp_path / "managed-settings.json"
    _write(managed, {"sandbox": {"allowUnsandboxedCommands": True}})
    monkeypatch.setattr(
        sandbox_module, "managed_settings_files", lambda: [str(managed)]
    )
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert not _relaxed(adapter)
    _write(managed, {"sandbox": {"enabled": True}, "permissions": {"allow": ["Read"]}})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    # Managed settings that change after the wrap.
    _write(managed, {"sandbox": {"enabled": True}})
    assert not _relaxed(adapter)


@pytest.mark.parametrize(
    "rule",
    ["WebFetch", "WebFetch(domain:example.com)", "Edit(/tmp/x)", "Read(~/.ssh)"],
)
def test_allow_rules_that_widen_the_sandbox(
    tmp_path: Path, project: Path, rule: str
) -> None:
    """The CLI merges WebFetch allow rules into the sandbox's allowlist and
    Edit or Read rules with a path into what it may write or read."""
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, allowed_tools=["Read", rule]))
    assert not _relaxed(adapter)
    adapter = _adapter(tmp_path)
    own = json.dumps({"permissions": {"allow": [rule]}})
    adapter.wrap_options(_options(project, settings=own))
    assert not _relaxed(adapter)
    _write(project / ".claude" / "settings.json", {"permissions": {"allow": [rule]}})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert not _relaxed(adapter)


def test_tool_names_alone_do_not_widen_it(tmp_path: Path, project: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.wrap_options(
        _options(project, allowed_tools=["Read", "Write", "Edit", "Bash"])
    )
    assert _relaxed(adapter)


def test_sandbox_variables_in_the_environment(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)
    adapter.wrap_options(
        _options(project, env={"CLAUDE_CODE_SANDBOX_LEAVE_PARENT_FOLDERS_ALONE": "1"})
    )
    assert not _relaxed(adapter)
    monkeypatch.setenv("CLAUDE_CODE_SANDBOX_LEAVE_DENIES_TO_SRT_WIN", "1")
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert not _relaxed(adapter)


def test_server_managed_settings_are_not_read(
    tmp_path: Path, project: Path, _own_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sandbox_module, "unread_policy_sources", _UNREAD_POLICY_SOURCES)
    _write(_own_home / ".claude" / "remote-settings.json", {})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert not _relaxed(adapter)


def test_options_wrapped_again_alike_are_kept_once(
    tmp_path: Path, project: Path
) -> None:
    adapter = _adapter(tmp_path)
    base = _options(project)
    for _ in range(3):
        adapter.wrap_options(base)
    assert len(adapter._wrapped_boundaries) == 1
    assert _relaxed(adapter)


def test_a_snapshot_store_after_a_checkpoint(tmp_path: Path, project: Path) -> None:
    from grounded_agency.state.snapshots import FileSnapshotStore

    (project / "a.txt").write_text("a")
    store = FileSnapshotStore(project, tmp_path / "records" / "snapshots")
    adapter = _adapter(tmp_path, snapshots=store)
    deny = _deny(adapter.wrap_options(_options(project)))
    assert f"Edit(/{os.path.realpath(tmp_path / 'records' / 'snapshots')})" in deny
    adapter.create_checkpoint(["*"], "before")
    assert _relaxed(adapter)


def test_a_record_with_a_second_hard_link(tmp_path: Path, project: Path) -> None:
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    log = tmp_path / "records" / "audit.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("x")
    assert _relaxed(adapter)
    os.link(log, project / "log-link")
    assert not _relaxed(adapter)


def test_a_credential_file_with_a_second_hard_link(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    key = _own_home / ".ssh" / "id_ed25519"
    key.parent.mkdir()
    key.write_text("k")
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    os.link(key, project / "key")
    assert not _relaxed(adapter)


# --- through the PreToolUse hook ------------------------------------------


async def test_the_hook_asks_for_ls_only_without_the_boundary(
    tmp_path: Path, project: Path
) -> None:
    """Under the sandbox `ls` passes the PreToolUse hook with no checkpoint;
    without it, it is refused for want of one (F501)."""

    async def run(adapter: GroundedAgentAdapter, wrapped: Any) -> dict[str, Any]:
        (hook,) = [
            fn
            for entry in wrapped.hooks["PreToolUse"]
            for fn in entry.hooks
            if getattr(fn, "_grounded_adapter", None) is adapter
        ]
        return await hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "tool_use_id": "t1",
                "permission_mode": "bypassPermissions",
                "cwd": str(project),
            },
            "t1",
            None,
        )

    adapter = _adapter(tmp_path)
    assert await run(adapter, adapter.wrap_options(_options(project))) == {}
    adapter = _adapter(tmp_path, sandbox=False)
    out = await run(adapter, adapter.wrap_options(_options(project)))
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"].startswith("F501")


async def _hook_on(
    adapter: GroundedAgentAdapter, wrapped: Any, project: Path, **extra: Any
) -> dict[str, Any]:
    """The adapter's PreToolUse hook on `git stash create`, with the hook
    input's members ``extra``."""
    (hook,) = [
        fn
        for entry in wrapped.hooks["PreToolUse"]
        for fn in entry.hooks
        if getattr(fn, "_grounded_adapter", None) is adapter
    ]
    return await hook(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git stash create"},
            "tool_use_id": "t1",
            "cwd": str(project),
            **extra,
        },
        "t1",
        None,
    )


@pytest.mark.parametrize(
    "mode", ["default", "acceptEdits", "plan", "auto", "dontAsk", "someFutureMode"]
)
async def test_a_mode_not_checked_is_the_worst_case(
    tmp_path: Path, project: Path, mode: str
) -> None:
    """STANDARD 1.2.0 section 5.18.3: the layer knows which sources the CLI
    reads and which values it honours only for the modes of
    CHECKED_PERMISSION_MODES. In any other mode, named by the hook input,
    `git stash create` is Bash's worst case: it needs a checkpoint (F501),
    and is kept as a call the boundary did not hold for."""
    assert mode not in CHECKED_PERMISSION_MODES
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    out = await _hook_on(adapter, wrapped, project, permission_mode=mode)
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"].startswith("F501")
    assert not adapter._bash_boundary_held("t1")


@pytest.mark.parametrize("mode", sorted(CHECKED_PERMISSION_MODES))
async def test_a_checked_mode_relaxes(tmp_path: Path, project: Path, mode: str) -> None:
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project))
    assert await _hook_on(adapter, wrapped, project, permission_mode=mode) == {}
    assert adapter._bash_boundary_held("t1")


async def test_options_in_a_mode_not_checked_are_not_verified(
    tmp_path: Path, project: Path
) -> None:
    """Options that start the session in a mode outside the set leave the
    boundary unverified, and a hook input that names no mode falls back to
    the options' mode."""
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project, permission_mode="plan"))
    assert not _relaxed(adapter)
    out = await _hook_on(adapter, wrapped, project)
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("F501")


def test_a_default_mode_not_checked_in_a_settings_file_is_not_verified(
    tmp_path: Path, project: Path
) -> None:
    _write(
        project / ".claude" / "settings.json", {"permissions": {"defaultMode": "plan"}}
    )
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert not _relaxed(adapter)
    # A value that is not a mode name at all is not a checked mode.
    _write(project / ".claude" / "settings.json", {"permissions": {"defaultMode": []}})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert not _relaxed(adapter)
    _write(
        project / ".claude" / "settings.json",
        {"permissions": {"defaultMode": "acceptEdits"}},
    )
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert not _relaxed(adapter)
    _write(
        project / ".claude" / "settings.json",
        {"permissions": {"defaultMode": "bypassPermissions"}},
    )
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["project"]))
    assert _relaxed(adapter)


def test_options_with_no_settings_or_sandbox_field(
    tmp_path: Path, project: Path
) -> None:
    """Options of an Agent SDK whose options have neither field are wrapped
    without them, and the boundary is unverified."""
    from dataclasses import dataclass, field

    @dataclass
    class OldOptions:
        cwd: str = ""
        hooks: dict[str, Any] = field(default_factory=dict)
        setting_sources: list[str] = field(default_factory=list)
        enable_file_checkpointing: bool = False
        can_use_tool: Any = None

    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(OldOptions(cwd=str(project)))
    assert not hasattr(wrapped, "sandbox")
    assert not _relaxed(adapter)


# --- code that runs outside the sandbox ------------------------------------


def test_the_code_outside_the_sandbox_is_not_writable(
    tmp_path: Path, project: Path
) -> None:
    """This package, the Agent SDK's, the interpreter and its packages:
    each an Edit deny rule."""
    import sys
    import sysconfig

    import claude_agent_sdk

    import grounded_agency

    deny = _deny(_adapter(tmp_path).wrap_options(_options(project)))
    for path in (
        os.path.dirname(os.path.realpath(grounded_agency.__file__)),
        os.path.dirname(os.path.realpath(claude_agent_sdk.__file__)),
        os.path.realpath(sysconfig.get_paths()["purelib"]),
        os.path.realpath(sys.executable),
    ):
        assert f"Edit(/{path})" in deny


def test_a_local_plugin_and_the_cli_path(tmp_path: Path, project: Path) -> None:
    plugin = project / "plug"
    (plugin / "hooks").mkdir(parents=True)
    (plugin / "hooks" / "h.sh").write_text("true")
    cli = project / "claude"
    cli.write_text("")
    adapter = _adapter(tmp_path)
    deny = _deny(
        adapter.wrap_options(
            _options(
                project,
                plugins=[{"type": "local", "path": str(plugin)}],
                cli_path=str(cli),
            )
        )
    )
    assert f"Edit(/{os.path.realpath(plugin)})" in deny
    assert f"Edit(/{os.path.realpath(cli)})" in deny
    # The CLI cli_path names is of a version this layer does not know.
    assert not _relaxed(adapter)
    adapter = _adapter(tmp_path)
    adapter.wrap_options(
        _options(project, plugins=[{"type": "local", "path": str(plugin)}])
    )
    assert _relaxed(adapter)
    # A plugin hook with a second hard link in the project.
    os.link(plugin / "hooks" / "h.sh", project / "h-link")
    assert not _relaxed(adapter)


# --- the CLI's version -------------------------------------------------------


def test_the_bundled_cli_of_a_checked_version_is_verified(
    tmp_path: Path, project: Path
) -> None:
    from claude_agent_sdk._cli_version import __cli_version__

    assert __cli_version__ in sandbox_module.CHECKED_CLI_VERSIONS
    assert sandbox_module.cli_faults(_options(project)) == []
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)


def test_a_cli_named_by_cli_path_is_not_verified(tmp_path: Path, project: Path) -> None:
    """Section 5.18.3: a layer that does not know, for the host's version,
    which sources it reads and which values it honours has not verified
    the boundary; the version of a CLI cli_path names is not known."""
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, cli_path="/usr/bin/true"))
    assert not _relaxed(adapter)


def test_a_bundled_cli_of_another_version_is_not_verified(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sandbox_module, "CHECKED_CLI_VERSIONS", frozenset({"0.0.0"}))
    faults = sandbox_module.cli_faults(_options(project))
    assert len(faults) == 1 and "checks the settings of Claude Code 0.0.0" in faults[0]
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert not _relaxed(adapter)


def test_no_bundled_cli_is_not_verified(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a bundled CLI the SDK runs the claude on PATH."""
    real_isfile = os.path.isfile
    monkeypatch.setattr(
        sandbox_module.os.path,
        "isfile",
        lambda p: False if "_bundled" in str(p) else real_isfile(p),
    )
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert not _relaxed(adapter)


def test_the_files_a_stdio_server_runs(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = project / "srv.py"
    script.write_text("")
    bin_dir = project / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    adapter = _adapter(tmp_path)
    deny = _deny(
        adapter.wrap_options(
            _options(
                project,
                mcp_servers={
                    "x": {"command": "python3", "args": [str(script)]},
                    "y": {"command": "./srv.py"},
                    "z": {"command": "my-server"},
                    "web": {"type": "http", "url": "https://example.com"},
                },
            )
        )
    )
    real = os.path.realpath(project)
    assert f"Edit(/{real}/srv.py)" in deny
    # A command found through a PATH directory inside the project, whether
    # or not it is there yet.
    assert f"Edit(/{real}/bin/my-server)" in deny
    assert f"Edit(/{real}/bin/python3)" in deny
    assert _relaxed(adapter)


def test_the_servers_of_the_projects_mcp_json(tmp_path: Path, project: Path) -> None:
    (project / "srv.js").write_text("")
    _write(
        project / ".mcp.json",
        {"mcpServers": {"s": {"command": "node", "args": ["srv.js"]}}},
    )
    adapter = _adapter(tmp_path)
    deny = _deny(adapter.wrap_options(_options(project)))
    assert f"Edit(/{os.path.realpath(project)}/srv.js)" in deny
    assert _relaxed(adapter)
    # Unless the options load only their own servers.
    deny = _deny(
        _adapter(tmp_path).wrap_options(_options(project, strict_mcp_config=True))
    )
    assert f"Edit(/{os.path.realpath(project)}/srv.js)" not in deny


@pytest.mark.parametrize("servers", ["/tmp/servers.json", '{"mcpServers": {}}'])
def test_a_server_list_this_layer_does_not_read(
    tmp_path: Path, project: Path, servers: str
) -> None:
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, mcp_servers=servers))
    assert not _relaxed(adapter)


def test_a_hook_script_with_a_second_hard_link(tmp_path: Path, project: Path) -> None:
    hook = project / ".claude" / "hooks" / "h.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("true")
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    os.link(hook, project / "hl.sh")
    assert not _relaxed(adapter)


def test_a_linked_worktrees_git_file(tmp_path: Path, project: Path) -> None:
    import subprocess

    def git(*args: str, cwd: Path) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
        )

    git("init", "-q", cwd=project)
    (project / "a").write_text("a")
    git("add", "a", cwd=project)
    git("commit", "-qm", "a", cwd=project)
    worktree = tmp_path / "wt"
    git("worktree", "add", "-q", str(worktree), cwd=project)
    adapter = _adapter(tmp_path)
    deny = _deny(adapter.wrap_options(_options(worktree)))
    assert f"Edit(/{os.path.realpath(worktree)}/.git)" in deny
    assert _relaxed(adapter)


def test_the_records_of_every_git_directory_are_denied(
    tmp_path: Path, project: Path
) -> None:
    """acs/ of each git directory of the repository is denied: the main
    checkout's, a linked worktree's and a submodule's, whichever checkout
    the session runs in, with the rules and denyWrite paths verified."""
    import subprocess

    def git(*args: str, cwd: Path) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "-c",
                "protocol.file.allow=always",
                *args,
            ],
            cwd=cwd,
            check=True,
            capture_output=True,
        )

    library = tmp_path / "library"
    library.mkdir()
    git("init", "-q", cwd=library)
    (library / "l").write_text("l")
    git("add", "l", cwd=library)
    git("commit", "-qm", "l", cwd=library)
    git("init", "-q", cwd=project)
    (project / "a").write_text("a")
    git("add", "a", cwd=project)
    git("commit", "-qm", "a", cwd=project)
    git("submodule", "add", "-q", str(library), "lib", cwd=project)
    git("commit", "-qm", "lib", cwd=project)
    worktree = tmp_path / "wt"
    git("worktree", "add", "-q", str(worktree), cwd=project)
    common = os.path.realpath(project / ".git")
    expected = [
        f"{common}/acs",
        f"{common}/worktrees/wt/acs",
        f"{common}/modules/lib/acs",
    ]
    # From the submodule's checkout too: its common git directory is its
    # own modules/lib, so the superproject's acs/ is found through it.
    for cwd in (project, worktree, project / "lib"):
        adapter = _adapter(tmp_path)
        wrapped = adapter.wrap_options(_options(cwd))
        deny = _deny(wrapped)
        deny_write = wrapped.sandbox["filesystem"]["denyWrite"]
        for path in expected:
            assert f"Edit(/{path}/**)" in deny
            assert f"Read(/{path}/**)" in deny
            assert path in deny_write
        paths = adapter._wrapped_boundaries[0].paths
        settings = flag_settings(wrapped)
        assert settings is not None
        assert boundary_faults(settings, paths) == []
        assert _relaxed(adapter)
        # A rule or denyWrite path for the worktree's or the submodule's
        # acs/ missing is a fault.
        for path in expected[1:]:
            rule = f"Read(/{path}/**)"
            fewer = copy.deepcopy(settings)
            fewer["permissions"]["deny"].remove(rule)
            assert boundary_faults(fewer, paths) == [f"permissions.deny has no {rule}"]
            fewer = copy.deepcopy(settings)
            fewer["sandbox"]["filesystem"]["denyWrite"].remove(path)
            assert boundary_faults(fewer, paths) == [
                f"the sandbox does not deny writing {path}"
            ]


def test_records_that_cannot_be_named_are_not_verified(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When layer_records cannot give the hooks' records (no git, or a
    path a rule reads as a pattern), every Bash call is the worst case."""

    def fails(project_dir: Any) -> Any:
        raise layer_records.LayerRecordsError("git is not installed")

    monkeypatch.setattr(layer_records, "deny_settings", fails)
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    faults = adapter._wrapped_boundaries[0].faults
    assert "the plugin hooks' records cannot be denied: git is not installed" in faults
    assert not _relaxed(adapter)


# --- credentials -------------------------------------------------------------


def test_the_common_credential_stores_are_denied(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    adapter = _adapter(tmp_path, sandbox_deny_paths=["~/.vault-token", "/opt/k"])
    sandbox = adapter.wrap_options(_options(project)).sandbox
    home = os.path.realpath(_own_home)
    for name in (
        ".netrc",
        ".gnupg",
        ".aws",
        ".config/gcloud",
        ".azure",
        ".kube",
        ".docker/config.json",
        ".npmrc",
        ".pypirc",
        ".cargo/credentials.toml",
        ".local/share/keyrings",
        ".vault-token",
    ):
        assert f"{home}/{name}" in sandbox["filesystem"]["denyRead"]
    assert "/opt/k" in sandbox["filesystem"]["denyRead"]
    assert _relaxed(adapter)


def test_credential_variables_of_the_environment(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOME_SERVICE_SECRET", "x")
    adapter = _adapter(tmp_path, sandbox_deny_env=["MY_PLAIN_NAME"])
    sandbox = adapter.wrap_options(
        _options(project, env={"OTHER_API_KEY": "y"})
    ).sandbox
    unset = {e["name"] for e in sandbox["credentials"]["envVars"]}
    assert {"SOME_SERVICE_SECRET", "OTHER_API_KEY", "MY_PLAIN_NAME"} <= unset
    assert {"SSH_AUTH_SOCK", "GPG_AGENT_INFO"} <= unset
    assert _relaxed(adapter)
    # One set in this process after the wrap would reach a CLI started from
    # these options.
    monkeypatch.setenv("LATER_TOKEN", "z")
    assert not _relaxed(adapter)


def test_a_linked_credential_directory(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    """Both the link and its target are denied, and the target's files are
    checked for hard links."""
    keys = tmp_path / "dotfiles" / "ssh"
    keys.mkdir(parents=True)
    (keys / "id").write_text("k")
    (_own_home / ".ssh").symlink_to(keys)
    adapter = _adapter(tmp_path)
    sandbox = adapter.wrap_options(_options(project)).sandbox
    home = os.path.realpath(_own_home)
    assert f"{home}/.ssh" in sandbox["filesystem"]["denyRead"]
    assert os.path.realpath(keys) in sandbox["filesystem"]["denyRead"]
    assert _relaxed(adapter)
    os.link(keys / "id", project / "id")
    assert not _relaxed(adapter)


def test_a_linked_settings_file(tmp_path: Path, project: Path, _own_home: Path) -> None:
    target = tmp_path / "dotfiles" / "settings.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    (_own_home / ".claude").mkdir()
    (_own_home / ".claude" / "settings.json").symlink_to(target)
    deny = _deny(_adapter(tmp_path).wrap_options(_options(project)))
    assert f"Edit(/{os.path.realpath(_own_home)}/.claude/settings.json)" in deny
    assert f"Edit(/{os.path.realpath(target)})" in deny


def test_the_home_the_cli_is_given(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    """The CLI's home is the options' HOME: its settings are read and its
    credentials denied, and this process's home's credentials stay denied."""
    other = tmp_path / "other"
    _write(other / ".claude" / "settings.json", {"sandbox": {"enabled": False}})
    adapter = _adapter(tmp_path)
    sandbox = adapter.wrap_options(
        _options(project, setting_sources=["user"], env={"HOME": str(other)})
    ).sandbox
    assert f"{os.path.realpath(other)}/.ssh" in sandbox["filesystem"]["denyRead"]
    assert f"{os.path.realpath(_own_home)}/.ssh" in sandbox["filesystem"]["denyRead"]
    assert not _relaxed(adapter)
    # An empty CLAUDE_CONFIG_DIR is unset for the CLI.
    _write(_own_home / ".claude" / "settings.json", {"sandbox": {"enabled": False}})
    adapter = _adapter(tmp_path)
    adapter.wrap_options(
        _options(project, setting_sources=["user"], env={"CLAUDE_CONFIG_DIR": ""})
    )
    assert not _relaxed(adapter)


def test_sandbox_variables_in_a_settings_env(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    env = {"env": {"CLAUDE_CODE_SANDBOX_LEAVE_DENIES_TO_SRT_WIN": "1"}}
    _write(_own_home / ".claude" / "settings.json", env)
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, setting_sources=["user"]))
    assert not _relaxed(adapter)
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project, settings=json.dumps(env)))
    assert not _relaxed(adapter)


def test_a_path_a_rule_reads_as_a_pattern(tmp_path: Path, project: Path) -> None:
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            checkpoint_dir=str(tmp_path / "records [1]" / "checkpoints"),
            audit_log_path=str(tmp_path / "records" / "audit.log"),
        )
    )
    adapter.wrap_options(_options(project))
    assert not _relaxed(adapter)


# --- after the wrap -----------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        lambda o: setattr(o, "sandbox", None),
        lambda o: o.allowed_tools.append("WebFetch"),
        lambda o: o.extra_args.update({"setting-sources": "project"}),
        lambda o: o.add_dirs.append("/"),
        lambda o: o.env.update({"HOME": "/"}),
    ],
)
def test_options_changed_after_the_wrap(
    tmp_path: Path, project: Path, change: Any
) -> None:
    adapter = _adapter(tmp_path)
    wrapped = adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    change(wrapped)
    assert not _relaxed(adapter)


def test_a_large_snapshot_store_is_not_walked(tmp_path: Path, project: Path) -> None:
    """The store's content objects are not walked before each call, so a
    store of many objects, or one with a hard link among them, leaves the
    boundary verified."""
    from grounded_agency.state.snapshots import FileSnapshotStore

    store_dir = tmp_path / "records" / "snapshots"
    store = FileSnapshotStore(project, store_dir)
    adapter = _adapter(tmp_path, snapshots=store)
    adapter.wrap_options(_options(project))
    objects = store_dir / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    for i in range(300):
        (objects / f"o{i}").write_text("x")
    os.link(objects / "o0", objects / "o0-link")
    assert _relaxed(adapter)
    paths = adapter._wrapped_boundaries[0].paths
    assert sandbox_module.linked_files(paths, limit=200) == []


def test_the_hooks_marker_history_is_walked_up_to_the_limit(
    tmp_path: Path, project: Path
) -> None:
    """The hooks' records are walked whole, the marker history included
    (the pre-tool-use hook counts its links too): a hard link there is
    found, and past the limit the boundary is unverified."""
    used = project / ".claude" / "checkpoints" / "used"
    used.mkdir(parents=True)
    for i in range(30):
        (used / f"m{i}").write_text("x")
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    paths = adapter._wrapped_boundaries[0].paths
    assert str(used.parent) in paths.record_deny_write
    over = sandbox_module.linked_files(paths, limit=10)
    assert len(over) == 1 and over[0].endswith("(not checked: too many files)")
    os.link(used / "m0", tmp_path / "outside")
    assert sandbox_module.linked_files(paths) == [os.path.realpath(used / "m0")]
    assert not _relaxed(adapter)


def test_a_hard_link_inside_the_denied_paths(
    tmp_path: Path, project: Path, _own_home: Path
) -> None:
    """A file whose every name is denied, such as the lock GnuPG makes by
    linking a file in ~/.gnupg, reaches nothing new."""
    gnupg = _own_home / ".gnupg"
    gnupg.mkdir()
    (gnupg / "tmp-lock").write_text("1")
    os.link(gnupg / "tmp-lock", gnupg / "pubring.db.lock")
    adapter = _adapter(tmp_path)
    adapter.wrap_options(_options(project))
    assert _relaxed(adapter)
    os.link(gnupg / "tmp-lock", project / "lock")
    assert not _relaxed(adapter)
