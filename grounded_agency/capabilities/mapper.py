"""
Tool-to-Capability Mapper

Maps Claude Agent SDK tool invocations to capability metadata,
enabling safety enforcement based on the Grounded Agency ontology.

A mapping's safety flags are its capability's ontology flags combined with
any stricter declaration (STANDARD 1.2.0 section 5.2.1): booleans are OR-ed
and ``risk`` is the higher level. A declaration weaker than the ontology
has no effect and is reported as W602. A tool the mapper does not know, or
whose binding did not load, is unbound and given the strictest flags
(:data:`UNCLASSIFIED_TOOL`, section 5.18.2).

Tools are bound by tool binding records (section 5.18.1, see
:mod:`grounded_agency.capabilities.bindings`); the static mappings below bind
Claude Code's own tools, and Bash is classified by its command
(section 5.18.3): a line of several commands takes the strictest flags and
every prerequisite of all of them. ``Skill`` is ``invoke`` whatever the
skill: loading a skill's instructions saves and restores nothing; the
state-saving call the skill leads to is classified on its own
(section 5.18.6).
"""

from __future__ import annotations

import copy
import logging
import re
import shlex
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from ..errors import ErrorCode, Severity, ValidationError, text_form
from .registry import CapabilityNode, CapabilityRegistry

if TYPE_CHECKING:
    from ..profiles import AppliedProfiles
    from .bindings import ApprovalPolicy

logger = logging.getLogger("grounded_agency.capabilities.mapper")

# Risk levels in ascending order; the higher of two levels is the stricter.
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high")
_RISK_ORDER: dict[str, int] = {level: n for n, level in enumerate(RISK_LEVELS)}

# Patterns for Bash command classification
_DESTRUCTIVE_PATTERNS = re.compile(
    r"""
    ^\s*(rm|rmdir|mv|cp\s+.*\s+/|chmod|chown|ln|unlink|shred)\s |  # File ops
    \s+(>|>>)\s |                                                   # Redirects
    \|\s*(rm|tee|dd)\s |                                           # Piped destructive
    \bsed\s+-i |                                                   # In-place sed
    \bgit\s+(push|reset|checkout\s+--|clean|stash\s+drop|branch\s+-[dD]) |  # Git mutations
    \bnpm\s+(publish|unpublish) |                                  # npm mutations
    \bdocker\s+(rm|rmi|prune|push) |                               # Docker mutations
    \bkubectl\s+(delete|apply|patch|edit)                          # k8s mutations
    """,
    re.VERBOSE | re.IGNORECASE,
)

# SEC-002: Interpreter invocation patterns that can execute arbitrary code.
# These bypass other checks because the outer command looks benign.
_INTERPRETER_PATTERNS = re.compile(
    r"""
    \bpython[23]?\s+(-c|--command)\s |          # Python one-liners
    \bruby\s+(-e|--eval)\s |                    # Ruby eval
    \bnode\s+(-e|--eval)\s |                    # Node.js eval
    \bperl\s+(-e|-E|--eval)\s |                 # Perl eval
    \bphp\s+(-r|--run)\s |                      # PHP eval
    \blua\s+(-e)\s |                            # Lua eval
    \bawk\s+.*\bsystem\s*\( |                   # awk system() calls
    \bpython[23]?\s+(?!-[Vh])(?!--version)(?!--help)\S    # Python script execution (not --version/--help)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# SEC-002: Process substitution and here-strings
_PROCESS_SUBSTITUTION_PATTERNS = re.compile(
    r"""
    <\( |               # Process substitution <(...)
    >\( |               # Process substitution >(...)
    <<<                 # Here-string
    """,
    re.VERBOSE,
)

_NETWORK_SEND_PATTERNS = re.compile(
    r"""
    \bcurl\s+.*(-X\s*(POST|PUT|PATCH|DELETE)|--data|--form|-d\s) |  # curl with data
    \bwget\s+--post |                                               # wget POST
    \bssh\s |                                                       # SSH connections
    \bscp\s |                                                       # SCP transfers
    \brsync\s |                                                     # rsync
    \bnc\s |                                                        # netcat
    \btelnet\s |                                                    # telnet
    \bftp\s                                                         # ftp
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Patterns that are ALWAYS dangerous regardless of context.
# These bypass compound-command analysis and are always high-risk.
_ALWAYS_DANGEROUS_PATTERNS = re.compile(
    r"""
    \$\( |                                # Command substitution $(...)
    ` |                                   # Backtick command substitution
    \$\{ |                                # Variable expansion ${...}
    \beval\s |                            # eval command
    \bexec\s |                            # exec command
    \bsource\s |                          # source command
    \bxargs\s.*-I |                       # xargs with command injection
    [\x00-\x1f\x7f-\x9f] |                 # Control characters
    \\x[0-9a-fA-F]{2} |                   # Hex escape sequences
    \\u[0-9a-fA-F]{4}                     # Unicode escape sequences
    """,
    re.VERBOSE,
)

# The shell is read with shlex (POSIX rules, operators as their own tokens), so
# quoted text stays one word: `grep "a|b" f` is one command. These control
# operators separate simple commands; a list or pipeline is read-only only when
# every command in it is.
_SEPARATORS: frozenset[str] = frozenset({"&&", "||", ";", "|", "&", "|&"})
# Output redirections. One is harmless only to /dev/null, or as `>&N`, which
# duplicates a descriptor; anything else writes a file.
_OUTPUT_REDIRECTS: frozenset[str] = frozenset({">", ">>", ">|", "&>", "&>>", ">&"})
_OPERATOR_CHARS = frozenset("();<>|&")

# Commands that only read, unless given an option that writes (_writes).
# Not here, because they run another command or can write a file whatever
# their options: env, xargs, sed, awk, tee and the interpreters.
_READ_ONLY_COMMANDS: frozenset[str] = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "file",
        "stat",
        "du",
        "df",
        "pwd",
        "whoami",
        "hostname",
        "uname",
        "date",
        "cal",
        "printenv",
        "echo",
        "printf",
        "which",
        "whereis",
        "locate",
        "find",
        "grep",
        "cut",
        "sort",
        "uniq",
        "wc",
        "diff",
        "cmp",
        "comm",
        "tr",
        "git status",
        "git log",
        "git show",
        "git diff",
        "git rev-parse",
        "git ls-files",
        "git branch",
        "git remote",
        "npm list",
        "npm view",
        "pip list",
        "pip show",
        "docker ps",
        "docker images",
        "docker logs",
        "kubectl get",
        "kubectl describe",
        "kubectl logs",
    }
)

# `git stash <sub>` forms that the Bash classifier recognises when the line is
# exactly one simple command with no option that writes (STANDARD 1.2.0
# section 5.18.3): `create` saves the current tracked state and takes a
# checkpoint; `list` and `show` only read; `pop` and `apply` restore one,
# but only as `git stash pop|apply <commit>` where <commit> is the full id of
# a commit the layer recorded as a checkpoint (`_RESTORES_CHECKPOINT`): git
# applies any merge commit as if it were a stash, so any other revision, and
# a bare `pop`/`apply` (refs/stash, which `git stash create` never writes),
# is a gated mutation. Every other form (`store`, `push`, `save`, `drop`,
# `clear`, none) is a gated mutation. The plugin's PreToolUse hook keeps the
# same table, and a test compares the two.
_GIT_STASH_CLASSES: dict[str, str] = {
    "create": "checkpoint",
    "list": "observe",
    "show": "observe",
    "pop": "rollback",
    "apply": "rollback",
}
# A commit id as `git stash create` prints it (SHA-1 or SHA-256). A full id
# names an object, never a ref, so no branch or tag can stand in for it.
_COMMIT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

# find actions that delete, run a command or write a file.
_FIND_WRITES: frozenset[str] = frozenset(
    {
        "-delete",
        "-exec",
        "-execdir",
        "-ok",
        "-okdir",
        "-fprint",
        "-fprint0",
        "-fprintf",
        "-fls",
    }
)
# The only arguments with which `git branch` lists and changes nothing.
_GIT_BRANCH_LISTING: frozenset[str] = frozenset(
    {
        "-a",
        "--all",
        "-r",
        "--remotes",
        "-v",
        "-vv",
        "--verbose",
        "-l",
        "--list",
        "--show-current",
        "--color",
        "--no-color",
    }
)


def _simple_commands(command: str) -> list[list[str]] | None:
    """
    The simple commands of a shell command line, each as its words.

    Returns None when the line holds something this reading cannot show to be
    harmless: an unbalanced quote, a subshell or group, a here-document, or an
    output redirection to anything but /dev/null. Redirections are dropped
    from the words. Comments are not recognised, so `ls # ; rm x` reads as two
    commands: a reading that errs splits a command into more commands to
    check, never fewer.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    commands: list[list[str]] = [[]]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _SEPARATORS:
            commands.append([])
        elif token == "<":
            i += 1  # reads a file: skip its name
        elif token in _OUTPUT_REDIRECTS:
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            if target != "/dev/null" and not (token == ">&" and target.isdigit()):
                return None
            i += 1
        elif token and set(token) <= _OPERATOR_CHARS:
            return None  # (, ), <<, <>, ;; and the like
        else:
            commands[-1].append(token)
        i += 1
    return [words for words in commands if words]


def _writes(words: list[str]) -> bool:
    """Whether an allow-listed command is given an option that writes,
    deletes or runs something. Errs towards True."""
    name, args = words[0], words[1:]
    short = [a for a in args if a.startswith("-") and not a.startswith("--")]
    if name == "find":
        return any(a in _FIND_WRITES for a in args)
    if name == "sort":
        return any(a.startswith("--output") for a in args) or any(
            "o" in a[1:] for a in short
        )
    if name == "uniq":
        # `uniq INPUT OUTPUT` writes OUTPUT.
        return len([a for a in args if not a.startswith("-")]) > 1
    if name == "date":
        return any(a.startswith("--set") for a in args) or any(
            "s" in a[1:] for a in short
        )
    if name == "hostname":
        return any(not a.startswith("-") for a in args)
    if name == "file":
        # -C, or C inside a short-option cluster such as -bC, compiles a
        # magic file and writes it.
        return "--compile" in args or any("C" in a[1:] for a in short)
    if name in ("less", "more"):
        return any(a.startswith("+") for a in args)  # runs a pager command
    if name == "git":
        if any(a.startswith("--output") for a in args):
            return True
        sub, rest = args[0], args[1:]
        if sub == "branch":
            return not all(a in _GIT_BRANCH_LISTING for a in rest)
        if sub == "remote":
            return not (
                rest in ([], ["-v"], ["--verbose"]) or rest[0] in ("show", "get-url")
            )
    return False


def _is_read_only(words: list[str]) -> bool:
    """Whether a simple command is on the read-only allow-list (by its exact
    name, or its name and subcommand) with no option that writes."""
    listed = (
        words[0] in _READ_ONLY_COMMANDS or " ".join(words[:2]) in _READ_ONLY_COMMANDS
    )
    return listed and not _writes(words)


@dataclass(frozen=True, slots=True)
class ToolMapping:
    """
    Maps a tool invocation to its Grounded Agency capability.

    The flags are effective flags (STANDARD 1.2.0 sections 5.2.1 and
    5.18.1): never weaker than the ontology's for any capability the
    mapping names, nor than those of the bindings it invokes.

    Attributes:
        capability_id: The ontology capability ID (e.g., "mutate", "retrieve");
            the primary one when the call performs several; ``""`` for a
            control-only tool
        risk: Risk level ("low", "medium", "high")
        mutation: Whether this tool modifies persistent state
        requires_checkpoint: Whether a checkpoint is required before use
        requires_approval: Whether the call needs approval before it runs
        domain: The capability's domain parameter (e.g., "config"), if the
            registration declared one
        capabilities: Every capability the call performs, primary first
            (``additional_capabilities``, section 5.18.3). Defaults to
            ``(capability_id,)``; empty for a control-only tool.
        invokes: The bindings a composite may call while it runs
            (section 5.18.4)
        prerequisites: The ``from`` capabilities of the ``requires`` edges
            into every capability in ``capabilities`` (section 5.18.5)
        approval: How approval of a call is counted (the binding's
            ``approval`` member, section 5.18.7)
        control: The tool only signals the host and is never refused
            (section 5.18.3)
        classifier: The classifier the binding names (section 5.18.3); this
            mapper applies the worst case to such a tool's calls
        destination: For a ``send`` tool, the RFC 6901 pointer to the
            argument that holds the destination (section 4.4.2)
        person_required: An applied domain profile requires a person's
            approval for the call (``require_human`` or
            ``block_autonomous``, section 5.21.3)
    """

    capability_id: str
    risk: str
    mutation: bool
    requires_checkpoint: bool
    requires_approval: bool
    domain: str | None = None
    capabilities: tuple[str, ...] = ()
    invokes: tuple[str, ...] = ()
    prerequisites: frozenset[str] = frozenset()
    approval: ApprovalPolicy | None = None
    control: bool = False
    classifier: str | None = None
    destination: str | None = None
    person_required: bool = False

    def __post_init__(self) -> None:
        if not self.capabilities and not self.control and self.capability_id:
            object.__setattr__(self, "capabilities", (self.capability_id,))

    def __str__(self) -> str:
        if self.control:
            return "control-only"
        checkpoint_marker = " [CHECKPOINT REQUIRED]" if self.requires_checkpoint else ""
        approval_marker = " [APPROVAL REQUIRED]" if self.requires_approval else ""
        return (
            f"{self.capability_id} (risk={self.risk})"
            f"{checkpoint_marker}{approval_marker}"
        )


# What a safety layer assumes about an unbound tool (STANDARD 1.2.0 section
# 5.18.2): an unknown mutation, so the rate limit, the checkpoint rule and
# the approval rule all apply. The mapper returns it for a tool name it does
# not know or whose binding did not load, and the adapter's PreToolUse hook
# uses it when classification fails. It has no prerequisites. Callers that
# need to tell "unbound" from a real ``mutate`` mapping compare by identity
# (``mapping is UNCLASSIFIED_TOOL``).
UNCLASSIFIED_TOOL = ToolMapping(
    capability_id="mutate",
    risk="high",
    mutation=True,
    requires_checkpoint=True,
    requires_approval=True,
)

# The mapping of a control-only tool (section 5.18.3): no capability, never
# refused, recorded.
CONTROL_TOOL = ToolMapping(
    capability_id="",
    risk="low",
    mutation=False,
    requires_checkpoint=False,
    requires_approval=False,
    control=True,
)


# Static mappings for SDK tools: tool name -> ontology capability ID. Each
# tool's flags are the capability's ontology flags.
_TOOL_MAPPINGS: dict[str, str] = {
    # PERCEIVE layer - read-only tools
    "Read": "retrieve",
    "Glob": "search",
    "Grep": "search",
    "LS": "observe",
    "WebFetch": "retrieve",
    "WebSearch": "search",
    # EXECUTE layer - mutation tools
    "Write": "mutate",
    "Edit": "mutate",
    "MultiEdit": "mutate",
    "NotebookEdit": "mutate",
    # COORDINATE layer. "Agent" and "AskUserQuestion" are the current
    # Claude Code names of the tools once called "Task" and "AskUser".
    "Task": "delegate",
    "Agent": "delegate",
    # A skill's instructions save and restore nothing: the calls the skill
    # leads to are classified on their own (STANDARD 1.2.0 section 5.18.6).
    "Skill": "invoke",
    "AskUser": "inquire",
    "AskUserQuestion": "inquire",
    # REMEMBER layer
    "TodoRead": "recall",
    "TodoWrite": "persist",  # a mutation that needs no checkpoint
    "TaskList": "recall",  # the task list that replaced TodoRead/TodoWrite
    "TaskGet": "recall",
    "TaskCreate": "persist",
    "TaskUpdate": "persist",
    # Other Claude Code tools that only read or ask. Tools that run a command
    # or stop a process (Monitor, KillShell, TaskStop) are left out on
    # purpose: they keep the unclassified (strictest) mapping.
    "ToolSearch": "search",
    "BashOutput": "observe",
    "TaskOutput": "observe",
    "ListMcpResourcesTool": "observe",
    "ReadMcpResourceTool": "retrieve",
    "ExitPlanMode": "inquire",
}

# The registry behind a mapper constructed without an ontology: the
# packaged ontology, loaded once per process.
_default_registry_lock = threading.Lock()
_default_registry: CapabilityRegistry | None = None


def _get_default_registry() -> CapabilityRegistry:
    """Load the default ontology once, after the SEC-012 integrity check."""
    global _default_registry
    with _default_registry_lock:
        if _default_registry is None:
            # Imported here: the adapter module imports this one.
            from ..adapter import get_default_ontology_path, verify_ontology_integrity

            path = get_default_ontology_path()
            if not verify_ontology_integrity(path):
                raise ValueError(
                    f"SEC-012: Ontology integrity check failed for {path}. "
                    f"File may have been tampered with."
                )
            _default_registry = CapabilityRegistry(path)
        return _default_registry


class ToolCapabilityMapper:
    """
    Maps SDK tool invocations to Grounded Agency capabilities.

    Analyzes tool name and input to determine:
    - Which capability from the ontology is being exercised
    - Risk level (low, medium, high)
    - Whether mutation is occurring
    - Whether a checkpoint is required
    - Whether approval is required

    Every flag is the stricter of the ontology's value for the capability
    and the declaration's (STANDARD 1.2.0 section 5.2.1). A tool the mapper
    does not know, or whose binding did not load, maps to
    :data:`UNCLASSIFIED_TOOL` (unbound, section 5.18.2).

    For Bash commands, performs additional analysis to determine
    if the command is read-only or mutating.

    Tools are bound by tool binding records (:meth:`register_binding`,
    :meth:`load_bindings`, section 5.18.1); :meth:`register_mcp_tool` builds
    a record from its arguments.

    Example:
        mapper = ToolCapabilityMapper(registry)
        mapping = mapper.map_tool("Write", {"file_path": "/tmp/test.txt"})
        assert mapping.requires_checkpoint is True
        assert mapping.requires_approval is True
    """

    def __init__(
        self,
        ontology: CapabilityRegistry | dict[str, Any] | None = None,
        *,
        profiles: AppliedProfiles | None = None,
    ) -> None:
        """
        Initialize the mapper.

        Args:
            ontology: Where capability flags come from: a
                :class:`CapabilityRegistry`, or a raw ontology dict. With
                ``None`` the packaged ontology is loaded on first use.
            profiles: Domain profiles the layer applies to every call it
                covers (STANDARD 1.2.0 section 5.21): :meth:`map_tool`
                returns each call's flags raised by them, and
                ``person_required`` for a call they require a person for.

        Raises:
            ValueError: If a raw ontology dict holds a node the registry
                would refuse (see :meth:`CapabilityNode.from_dict`).
            KeyError: If a node of a raw ontology dict has no ``id`` or
                ``layer``.
        """
        self._registry: CapabilityRegistry | None = None
        self._nodes: dict[str, CapabilityNode] | None = None
        self._raw_requires: list[tuple[str, str]] | None = None
        self._raw_version: str = "unknown"
        if isinstance(ontology, CapabilityRegistry):
            self._registry = ontology
        elif ontology is not None:
            self._nodes = {
                node["id"]: CapabilityNode.from_dict(node)
                for node in ontology.get("nodes", [])
            }
            self._raw_requires = [
                (edge["from"], edge["to"])
                for edge in ontology.get("edges", [])
                if edge.get("type") == "requires"
            ]
            meta = ontology.get("meta") or {}
            self._raw_version = str(meta.get("version", "unknown"))
        self._profiles = profiles if profiles else None
        self._profiled: dict[ToolMapping, ToolMapping] = {}
        self._dynamic_mappings: dict[str, ToolMapping] = {}
        # Effective mappings of the static and Bash classifications, built
        # on first use (ToolMapping is immutable, so they can be shared).
        self._builtin_mappings: dict[tuple[str, bool], ToolMapping] = {}
        self._combined_mappings: dict[tuple[ToolMapping, ...], ToolMapping] = {}
        # Diagnostics of the bindings registered, per tool name.
        self._diagnostics: dict[str, list[ValidationError]] = {}
        # The records registered, per tool name, for the layer's
        # configuration digest; `records_revision` counts their changes.
        self._records: dict[str, dict[str, Any]] = {}
        self.records_revision = 0
        # Whether a commit id is one the layer recorded as a checkpoint: a
        # `git stash pop|apply <commit>` restores a checkpoint (`rollback`)
        # only then. The adapter sets it from its checkpoint tracker; with
        # None, every such command is a gated mutation.
        self.is_checkpoint_commit: Callable[[str], bool] | None = None

    @property
    def warnings(self) -> list[ValidationError]:
        """Warnings for the registered tools: W602 for each declaration
        weaker than the ontology, which had no effect, and W617 for each
        tool registered with no capability (unbound).

        ``location`` holds ``tool`` and, for W602, ``capability`` and
        ``field``. Registering a tool again replaces its reports.
        """
        return [d for d in self.diagnostics if d.severity is Severity.WARNING]

    @property
    def diagnostics(self) -> list[ValidationError]:
        """Every diagnostic of the bindings registered or loaded: errors for
        records that were not loaded, warnings for the rest."""
        return [d for reports in self._diagnostics.values() for d in reports]

    @property
    def records(self) -> list[dict[str, Any]]:
        """The binding records registered, in tool-name order. Each loaded
        record is I-JSON (section 5.14): one that is not does not load."""
        return [self._records[name] for name in sorted(self._records)]

    @property
    def ontology_version(self) -> str:
        """The ``meta.version`` of the ontology this mapper reads."""
        if self._nodes is not None:
            return self._raw_version
        return self._get_registry().version

    def _get_registry(self) -> CapabilityRegistry:
        if self._registry is None:
            self._registry = _get_default_registry()
        return self._registry

    def _all_nodes(self) -> Mapping[str, CapabilityNode]:
        if self._nodes is not None:
            return self._nodes
        return {node.id: node for node in self._get_registry().all_capabilities()}

    def _requires(self) -> list[tuple[str, str]]:
        """The ontology's ``requires`` edges as ``(from, to)``."""
        if self._raw_requires is not None:
            return self._raw_requires
        return [
            (edge.from_cap, edge.to_cap)
            for edge in self._get_registry().all_edges()
            if edge.edge_type == "requires"
        ]

    def _prerequisites(self, capabilities: Iterable[str]) -> frozenset[str]:
        caps = set(capabilities)
        return frozenset(src for src, dst in self._requires() if dst in caps)

    def _capability(self, capability_id: str) -> CapabilityNode | None:
        """The ontology node for a capability ID, or None."""
        if self._nodes is not None:
            return self._nodes.get(capability_id)
        return self._get_registry().get_capability(capability_id)

    def _effective_mapping(
        self,
        tool_name: str,
        capability_id: str,
        *,
        risk: str | None = None,
        mutation: bool | None = None,
        requires_checkpoint: bool | None = None,
        requires_approval: bool | None = None,
        domain: str | None = None,
    ) -> ToolMapping:
        """Combine a built-in declaration with the ontology (section 5.2.1).

        ``None`` declares nothing. Built-in declarations are never weaker
        than the ontology, so no W602 can arise here.

        Raises:
            ValueError: For a capability ID the ontology does not define
                (V101), or one whose ontology risk is not a risk level.
        """
        node = (
            self._capability(capability_id) if isinstance(capability_id, str) else None
        )
        if node is None:
            raise ValueError(
                f"{ErrorCode.UNKNOWN_CAPABILITY.value} "
                f"{ErrorCode.UNKNOWN_CAPABILITY.name}: tool '{tool_name}' "
                f"declares capability {capability_id!r}, which the ontology "
                f"does not define"
            )
        if node.risk not in _RISK_ORDER:
            raise ValueError(
                f"capability '{capability_id}' has risk {node.risk!r} in the "
                f"ontology; expected one of {', '.join(RISK_LEVELS)}"
            )
        effective_risk = node.risk
        if risk is not None and _RISK_ORDER[risk] > _RISK_ORDER[node.risk]:
            effective_risk = risk
        return ToolMapping(
            capability_id=capability_id,
            risk=effective_risk,
            mutation=node.mutation or mutation is True,
            requires_checkpoint=node.requires_checkpoint or requires_checkpoint is True,
            requires_approval=node.requires_approval or requires_approval is True,
            domain=domain,
            prerequisites=self._prerequisites((capability_id,)),
        )

    def _builtin(
        self, tool_name: str, capability_id: str, checkpoint_gated: bool = False
    ) -> ToolMapping:
        """Effective mapping of a static or Bash classification.

        ``checkpoint_gated`` is the Bash classifier's declaration for a
        command it cannot show to be read-only: a high-risk mutation that
        needs a checkpoint, whatever its capability.
        """
        key = (capability_id, checkpoint_gated)
        mapping = self._builtin_mappings.get(key)
        if mapping is None:
            if checkpoint_gated:
                mapping = self._effective_mapping(
                    tool_name,
                    capability_id,
                    risk="high",
                    mutation=True,
                    requires_checkpoint=True,
                )
            else:
                mapping = self._effective_mapping(tool_name, capability_id)
            self._builtin_mappings[key] = mapping
        return mapping

    def load_bindings(
        self, records: Iterable[Mapping[str, Any]]
    ) -> list[ValidationError]:
        """Load a set of tool binding records (STANDARD 1.2.0 section 5.18.1).

        Each record that loads is stored under its ``tool``; ``invokes``
        names resolve within the set and among the tools registered before.
        A tool whose record does not load is unbound (:data:`UNCLASSIFIED_TOOL`).
        Nothing is raised: every diagnostic is returned and kept in
        :attr:`diagnostics` (warnings also in :attr:`warnings`).
        """
        from .bindings import load_bindings

        records = [dict(r) if isinstance(r, Mapping) else r for r in records]
        loaded, diagnostics = load_bindings(
            records,
            self._all_nodes(),
            self._requires(),
            self.ontology_version,
            known=self._dynamic_mappings,
        )
        names = {
            r["tool"]
            for r in records
            if isinstance(r, Mapping) and isinstance(r.get("tool"), str) and r["tool"]
        }
        for name in names:
            self._diagnostics[name] = []
            self._records.pop(name, None)
        self.records_revision += 1
        for d in diagnostics:
            self._diagnostics.setdefault(str(d.location.get("tool", "")), []).append(d)
            if d.severity is Severity.WARNING:
                logger.warning("%s: %s", d.code_str, text_form(d))
        for name in names:
            mapping = loaded.get(name)
            if mapping is None:
                self._dynamic_mappings[name] = UNCLASSIFIED_TOOL
            else:
                self._dynamic_mappings[name] = mapping
        for r in records:
            if isinstance(r, Mapping) and r.get("tool") in loaded:
                # A copy the caller cannot change under the digest.
                self._records[r["tool"]] = copy.deepcopy(dict(r))
        return diagnostics

    def register_binding(self, record: Mapping[str, Any]) -> ToolMapping:
        """Load one tool binding record and return its effective mapping.

        Raises:
            ValueError: If the record does not load (S303, S304, V101, V105,
                V107, V109, V110). The message opens with each error's code
                and name; the tool stays unbound.
        """
        diagnostics = self.load_bindings([record])
        errors = [d for d in diagnostics if d.severity is Severity.ERROR]
        if errors:
            raise ValueError("; ".join(text_form(e) for e in errors))
        return self._dynamic_mappings[record["tool"]]

    def register_mcp_tool(
        self,
        tool_name: str,
        capability_id: str | None = None,
        risk: str | None = None,
        mutation: bool | None = None,
        requires_checkpoint: bool | None = None,
        requires_approval: bool | None = None,
        domain: str | None = None,
        *,
        additional_capabilities: list[str] | None = None,
        invokes: list[str] | None = None,
        approval: Mapping[str, Any] | None = None,
        control: bool = False,
    ) -> ToolMapping:
        """Register a dynamic tool-to-capability mapping.

        Used by :func:`grounded_agency.mcp.create_grounded_mcp_server`
        to register MCP-provided tools so that safety enforcement
        applies to them. The arguments are a tool binding record
        (STANDARD 1.2.0 section 5.18.1) with ``tool=tool_name`` and the
        ontology's version, loaded by :meth:`register_binding`.

        The stored flags are the stricter of the ontology's flags for every
        capability named and the declared ones (section 5.2.1). A declared
        flag weaker than the ontology's has no effect: it is logged and kept
        in :attr:`warnings` as W602 (SAFETY_FLAG_DOWNGRADE). The one
        exception is ``mutation=False`` on a capability the ontology marks
        ``mutation_overridable``, when no other capability is named.

        A tool registered with no ``capability_id`` and not ``control`` is
        unbound (section 5.18.2): it is the strictest case
        (:data:`UNCLASSIFIED_TOOL`), and a W617 (UNBOUND_TOOL) is kept in
        :attr:`warnings`.

        Args:
            tool_name: The tool identifier (e.g., ``mcp__server__tool``).
            capability_id: Ontology capability ID; ``None`` leaves the tool
                unbound.
            risk: Risk level — ``"low"``, ``"medium"``, or ``"high"``.
                Defaults to the capability's.
            mutation: Whether the tool mutates state. When omitted, the
                capability's value, or ``True`` if ``risk`` is ``"high"``.
            requires_checkpoint: Whether a checkpoint is needed. When
                omitted, the capability's value, or ``True`` if ``risk``
                is ``"high"``.
            requires_approval: Whether the call needs approval. Defaults
                to the capability's.
            domain: The capability's domain parameter, e.g. ``"config"``.
            additional_capabilities: Other capabilities the same call
                performs (section 5.18.3).
            invokes: Names of the bindings the tool may call while it runs
                (section 5.18.4).
            approval: The binding's ``approval`` member: ``min_approvers``,
                ``role``, ``expires`` (section 5.18.7).
            control: The tool only signals the host (section 5.18.3).

        Returns:
            The effective mapping that was stored.

        Raises:
            ValueError: If the record does not load: the ontology does not
                define a capability (V101 UNKNOWN_CAPABILITY), ``risk`` is
                not a risk level or a flag not a boolean (S303), an
                ``invokes`` name does not resolve (V107) or forms a cycle
                (V105). Nothing is registered.
        """
        if capability_id is None and not control:
            self._dynamic_mappings[tool_name] = UNCLASSIFIED_TOOL
            self._records.pop(tool_name, None)
            self.records_revision += 1
            report = ValidationError(
                code=ErrorCode.UNBOUND_TOOL,
                message=(
                    f"tool '{tool_name}' was registered with no capability; "
                    f"its calls are treated as the strictest case (high "
                    f"risk, mutation, checkpoint and approval). Bind it to "
                    f"the capability it performs."
                ),
                location={"tool": tool_name},
            )
            logger.warning("%s", text_form(report))
            self._diagnostics[tool_name] = [report]
            return UNCLASSIFIED_TOOL

        if mutation is None and risk == "high":
            mutation = True
        if requires_checkpoint is None and risk == "high":
            requires_checkpoint = True
        record: dict[str, Any] = {
            "tool": tool_name,
            "ontology": self.ontology_version,
        }
        if control:
            record["control"] = True
        if capability_id is not None:
            record["capability"] = capability_id
        if domain is not None:
            record["domain"] = domain
        flags = {
            name: value
            for name, value in (
                ("risk", risk),
                ("mutation", mutation),
                ("requires_checkpoint", requires_checkpoint),
                ("requires_approval", requires_approval),
            )
            if value is not None
        }
        if flags:
            record["flags"] = flags
        if additional_capabilities is not None:
            record["additional_capabilities"] = list(additional_capabilities)
        if invokes is not None:
            record["invokes"] = list(invokes)
        if approval is not None:
            record["approval"] = dict(approval)
        return self.register_binding(record)

    def map_tool(self, tool_name: str, tool_input: dict[str, Any]) -> ToolMapping:
        """
        Map a tool invocation to its capability metadata.

        Bash is classified by its command. Any other name is looked up in
        the dynamic mappings (registered via :meth:`register_mcp_tool` or
        :meth:`load_bindings`), then the static mappings. A name found in
        neither is unbound and maps to :data:`UNCLASSIFIED_TOOL`. A bound
        tool's mapping is its worst case; this mapper applies no classifier
        to it.

        Args:
            tool_name: SDK tool name (e.g., "Write", "Bash", "Read")
            tool_input: Tool input parameters

        Returns:
            ToolMapping with capability metadata, raised by the applied
            domain profiles (section 5.21.3)
        """
        return self._apply_profiles(self._map_tool(tool_name, tool_input))

    def _map_tool(self, tool_name: str, tool_input: dict[str, Any]) -> ToolMapping:
        """:meth:`map_tool` before domain profiles."""
        # Handle Bash specially - analyze command content. Input that is
        # not a dict has no command to read: classify it as an empty one,
        # which is fail-safe high risk.
        if tool_name == "Bash":
            if not isinstance(tool_input, dict):
                tool_input = {}
            return self._classify_bash_command(tool_input)

        # Check dynamic mappings (MCP tools, etc.)
        if tool_name in self._dynamic_mappings:
            return self._dynamic_mappings[tool_name]

        # Static mapping for known tools
        if tool_name in _TOOL_MAPPINGS:
            return self._builtin(tool_name, _TOOL_MAPPINGS[tool_name])

        # Unknown tool: nothing says what it does, so assume the strictest
        # case instead of a read.
        return UNCLASSIFIED_TOOL

    def person_required(self, mapping: ToolMapping) -> bool:
        """Whether the applied profiles require a person for a call with
        ``mapping`` (section 5.21.3): what its record's ``person_required``
        and its approval request say. :data:`UNCLASSIFIED_TOOL` keeps its
        identity under profiles (see :meth:`_apply_profiles`), so for an
        unbound tool the requirement is computed here, for the ``mutate``
        it is treated as (section 5.18.2)."""
        if mapping is UNCLASSIFIED_TOOL:
            return (
                self._profiles is not None
                and self._profiles.flags(
                    mapping.capability_id, {"risk": mapping.risk}
                ).person
            )
        return mapping.person_required

    def _apply_profiles(self, mapping: ToolMapping) -> ToolMapping:
        """``mapping`` with the flags the applied profiles raise for each of
        its capabilities at its risk, and ``person_required`` when one of
        them requires a person (section 5.21.3). The core computes them, as
        it does for the executor. A control-only tool has no capability, and
        :data:`UNCLASSIFIED_TOOL` already needs a checkpoint and approval,
        so both stay as they are and keep their identity; whether a profile
        requires a person for an unbound tool is :meth:`person_required`'s
        answer."""
        if self._profiles is None or mapping.control or mapping is UNCLASSIFIED_TOOL:
            return mapping
        hit = self._profiled.get(mapping)
        if hit is not None:
            return hit
        checkpoint = mapping.requires_checkpoint
        approval = mapping.requires_approval
        person = mapping.person_required
        for capability in mapping.capabilities:
            flags = self._profiles.flags(capability, {"risk": mapping.risk})
            checkpoint |= flags.requires_checkpoint
            approval |= flags.requires_approval
            person |= flags.person
        raised = mapping
        if (checkpoint, approval, person) != (
            mapping.requires_checkpoint,
            mapping.requires_approval,
            mapping.person_required,
        ):
            raised = replace(
                mapping,
                requires_checkpoint=checkpoint,
                requires_approval=approval,
                person_required=person,
            )
        self._profiled[mapping] = raised
        return raised

    def _classify_bash_command(self, tool_input: dict[str, Any]) -> ToolMapping:
        """
        Classify a Bash command based on its content (STANDARD 1.2.0
        section 5.18.3).

        1. Always-dangerous patterns (command substitution, backticks,
           variable expansion, eval, exec, source, control characters) and
           process substitution make the command a gated mutation at once.
           So does a line `_simple_commands` cannot read.
        2. Only when the line is exactly one simple command with no option
           that writes (`_writes`), a `git stash <sub>` form is classified
           by `_GIT_STASH_CLASSES`: `create` takes a checkpoint, `list` and
           `show` observe, and `pop <commit>` and `apply <commit>` roll back
           when <commit> is the full id of a commit the layer recorded as a
           checkpoint (:attr:`is_checkpoint_commit`); any other `pop` or
           `apply` is a gated mutation, since git applies any merge commit
           as if it were a stash. A git option before `stash` (`git -C dir
           stash ...`) is not recognised.
        3. Otherwise each simple command is classified on its own. A line
           whose every command is allow-listed as read-only is an
           observation; any other line takes the strictest flags and every
           prerequisite of all the commands that are not read-only, with
           their capabilities in order (`_combine`).

        Security principle: fail-safe defaults. A command is high-risk until
        it is shown to be on the read-only allow-list.

        Args:
            tool_input: Bash tool input with 'command' key

        Returns:
            ToolMapping based on command analysis
        """
        command = tool_input.get("command", "")
        mutation = self._builtin("Bash", "mutate", checkpoint_gated=True)

        # Empty or non-string command is suspicious - fail-safe
        if not isinstance(command, str) or not command.strip():
            return mutation

        # SEC-002: These bypass all other checks and are always high-risk.
        if _ALWAYS_DANGEROUS_PATTERNS.search(
            command
        ) or _PROCESS_SUBSTITUTION_PATTERNS.search(command):
            return mutation

        commands = _simple_commands(command)
        if not commands:
            return mutation

        if len(commands) == 1:
            words = commands[0]
            if (
                len(words) >= 3
                and words[0] == "git"
                and words[1] == "stash"
                and words[2] in _GIT_STASH_CLASSES
                and not _writes(words)
            ):
                capability = _GIT_STASH_CLASSES[words[2]]
                if capability != "rollback" or self._restores_checkpoint(words):
                    return self._builtin("Bash", capability)
                return mutation

        results = [self._classify_single_command(words) for words in commands]
        gated = [r for r in results if r.risk != "low"]
        if not gated:
            return self._builtin("Bash", "observe")
        return self._combine(gated)

    def _restores_checkpoint(self, words: list[str]) -> bool:
        """Whether `git stash pop|apply <commit>` (``words``) names, as its
        only argument, the full id of a commit the layer recorded as a
        checkpoint. A lookup that fails is a no."""
        if len(words) != 4 or not _COMMIT_ID.match(words[3]):
            return False
        recorded = self.is_checkpoint_commit
        if recorded is None:
            return False
        try:
            return bool(recorded(words[3]))
        except Exception:
            logger.exception("Could not look up checkpoint commit %s", words[3])
            return False

    def _combine(self, results: list[ToolMapping]) -> ToolMapping:
        """One mapping for a line of several actions (section 5.18.3): every
        distinct capability in order, the strictest flags, and the union of
        the prerequisites."""
        distinct: list[ToolMapping] = []
        for r in results:
            if r not in distinct:
                distinct.append(r)
        if len(distinct) == 1:
            return distinct[0]
        key = tuple(distinct)
        combined = self._combined_mappings.get(key)
        if combined is None:
            capabilities: list[str] = []
            for r in distinct:
                for cap in r.capabilities:
                    if cap not in capabilities:
                        capabilities.append(cap)
            combined = ToolMapping(
                capability_id=capabilities[0],
                risk=max((r.risk for r in distinct), key=_RISK_ORDER.__getitem__),
                mutation=any(r.mutation for r in distinct),
                requires_checkpoint=any(r.requires_checkpoint for r in distinct),
                requires_approval=any(r.requires_approval for r in distinct),
                capabilities=tuple(capabilities),
                prerequisites=frozenset().union(*(r.prerequisites for r in distinct)),
            )
            self._combined_mappings[key] = combined
        return combined

    def _classify_single_command(self, words: list[str]) -> ToolMapping:
        """
        Classify one simple command, given as its words.

        Checks in order: interpreter → network → destructive → read-only
        allowlist → secure default-deny. It never returns a `git stash`
        class: those need a line of one command (`_classify_bash_command`).
        """
        text = " ".join(words)
        # SEC-002: Check for interpreter invocations (python -c, node -e, etc.)
        if _INTERPRETER_PATTERNS.search(text):
            return self._builtin("Bash", "execute", checkpoint_gated=True)

        # Check for network send operations
        if _NETWORK_SEND_PATTERNS.search(text):
            return self._builtin("Bash", "send", checkpoint_gated=True)

        # Check for destructive operations
        if _DESTRUCTIVE_PATTERNS.search(text):
            return self._builtin("Bash", "mutate", checkpoint_gated=True)

        if _is_read_only(words):
            return self._builtin("Bash", "observe")

        # SECURE DEFAULT: a command not shown to be read-only is high-risk.
        return self._builtin("Bash", "mutate", checkpoint_gated=True)

    def is_high_risk(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if a tool invocation is high risk."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.risk == "high"

    def requires_checkpoint(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if a tool invocation requires a checkpoint."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.requires_checkpoint

    def requires_approval(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if a tool invocation requires approval."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.requires_approval

    def is_mutation(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if a tool invocation is a mutation."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.mutation

    def get_capability_id(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Get the capability ID for a tool invocation."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.capability_id
