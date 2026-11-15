"""
Tool-to-Capability Mapper

Maps Claude Agent SDK tool invocations to capability metadata,
enabling safety enforcement based on the Grounded Agency ontology.

A mapping's safety flags are its capability's ontology flags combined with
any stricter declaration (STANDARD v1.1 section 5.2.1): booleans are OR-ed
and ``risk`` is the higher level. A declaration weaker than the ontology
has no effect and is reported as W602. A tool the mapper does not know is
given the strictest flags (:data:`UNCLASSIFIED_TOOL`).
"""

from __future__ import annotations

import logging
import re
import shlex
import threading
from dataclasses import dataclass
from typing import Any

from ..errors import ErrorCode, ValidationError
from .registry import CapabilityNode, CapabilityRegistry

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
        return any(a in ("-C", "--compile") for a in args)
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

    The flags are effective flags (STANDARD v1.1 section 5.2.1): never
    weaker than the ontology's for ``capability_id``.

    Attributes:
        capability_id: The ontology capability ID (e.g., "mutate", "retrieve")
        risk: Risk level ("low", "medium", "high")
        mutation: Whether this tool modifies persistent state
        requires_checkpoint: Whether a checkpoint is required before use
        requires_approval: Whether the call needs approval before it runs
        domain: The capability's domain parameter (e.g., "config"), if the
            registration declared one
    """

    capability_id: str
    risk: str
    mutation: bool
    requires_checkpoint: bool
    requires_approval: bool
    domain: str | None = None

    def __str__(self) -> str:
        checkpoint_marker = " [CHECKPOINT REQUIRED]" if self.requires_checkpoint else ""
        approval_marker = " [APPROVAL REQUIRED]" if self.requires_approval else ""
        return (
            f"{self.capability_id} (risk={self.risk})"
            f"{checkpoint_marker}{approval_marker}"
        )


# What a safety layer assumes about a tool that has no classification: an
# unknown mutation, so the rate limit, the checkpoint rule and the approval
# rule all apply. The mapper returns it for a tool name it does not know,
# and the adapter's PreToolUse hook uses it when classification fails.
# Callers that need to tell "unclassified" from a real ``mutate`` mapping
# compare by identity (``mapping is UNCLASSIFIED_TOOL``).
UNCLASSIFIED_TOOL = ToolMapping(
    capability_id="mutate",
    risk="high",
    mutation=True,
    requires_checkpoint=True,
    requires_approval=True,
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
    "Skill": "invoke",  # a skill may mutate; that is checked at skill level
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
    and the declaration's (STANDARD v1.1 section 5.2.1). A tool the mapper
    does not know maps to :data:`UNCLASSIFIED_TOOL`.

    For Bash commands, performs additional analysis to determine
    if the command is read-only or mutating.

    Supports dynamic registration of MCP tool mappings via
    :meth:`register_mcp_tool`.

    Example:
        mapper = ToolCapabilityMapper(registry)
        mapping = mapper.map_tool("Write", {"file_path": "/tmp/test.txt"})
        assert mapping.requires_checkpoint is True
        assert mapping.requires_approval is True
    """

    def __init__(
        self, ontology: CapabilityRegistry | dict[str, Any] | None = None
    ) -> None:
        """
        Initialize the mapper.

        Args:
            ontology: Where capability flags come from: a
                :class:`CapabilityRegistry`, or a raw ontology dict. With
                ``None`` the packaged ontology is loaded on first use.

        Raises:
            ValueError: If a raw ontology dict holds a node the registry
                would refuse (see :meth:`CapabilityNode.from_dict`).
            KeyError: If a node of a raw ontology dict has no ``id`` or
                ``layer``.
        """
        self._registry: CapabilityRegistry | None = None
        self._nodes: dict[str, CapabilityNode] | None = None
        if isinstance(ontology, CapabilityRegistry):
            self._registry = ontology
        elif ontology is not None:
            self._nodes = {
                node["id"]: CapabilityNode.from_dict(node)
                for node in ontology.get("nodes", [])
            }
        self._dynamic_mappings: dict[str, ToolMapping] = {}
        # Effective mappings of the static and Bash classifications, built
        # on first use (ToolMapping is immutable, so they can be shared).
        self._builtin_mappings: dict[tuple[str, bool], ToolMapping] = {}
        # W602 reports of register_mcp_tool, per tool name.
        self._warnings: dict[str, list[ValidationError]] = {}

    @property
    def warnings(self) -> list[ValidationError]:
        """W602 reports for the registered tools: each declaration weaker
        than the ontology, which had no effect.

        ``location`` holds ``tool``, ``capability`` and ``field``.
        Registering a tool again replaces its reports.
        """
        return [w for reports in self._warnings.values() for w in reports]

    def _capability(self, capability_id: str) -> CapabilityNode | None:
        """The ontology node for a capability ID, or None."""
        if self._nodes is not None:
            return self._nodes.get(capability_id)
        if self._registry is None:
            self._registry = _get_default_registry()
        return self._registry.get_capability(capability_id)

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
    ) -> tuple[ToolMapping, list[ValidationError]]:
        """Combine a declaration with the ontology (section 5.2.1).

        Returns the effective mapping and one W602 report per declared flag
        that is weaker than the ontology's. ``None`` declares nothing.

        Raises:
            ValueError: For a capability ID the ontology does not define
                (V101), a risk level outside :data:`RISK_LEVELS`, a flag
                that is not a boolean, or a domain that is not a string.
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
        # Declarations can come from tool metadata, so their types are
        # checked: a flag that is neither true nor false declares nothing
        # that can be combined with the ontology.
        if risk is not None and (not isinstance(risk, str) or risk not in _RISK_ORDER):
            raise ValueError(
                f"tool '{tool_name}' declares risk {risk!r}; "
                f"expected one of {', '.join(RISK_LEVELS)}"
            )
        for flag, value in (
            ("mutation", mutation),
            ("requires_checkpoint", requires_checkpoint),
            ("requires_approval", requires_approval),
        ):
            if value is not None and not isinstance(value, bool):
                raise ValueError(
                    f"tool '{tool_name}' declares {flag}={value!r}; "
                    f"expected true or false"
                )
        if domain is not None and not isinstance(domain, str):
            raise ValueError(
                f"tool '{tool_name}' declares domain {domain!r}; expected a string"
            )
        if node.risk not in _RISK_ORDER:
            raise ValueError(
                f"capability '{capability_id}' has risk {node.risk!r} in the "
                f"ontology; expected one of {', '.join(RISK_LEVELS)}"
            )

        reports: list[ValidationError] = []

        def downgrade(flag: str, message: str) -> None:
            reports.append(
                ValidationError(
                    code=ErrorCode.SAFETY_FLAG_DOWNGRADE,
                    message=message,
                    location={
                        "tool": tool_name,
                        "capability": capability_id,
                        "field": flag,
                    },
                )
            )

        def boolean(flag: str, declared: bool | None, ontology: bool, why: str) -> bool:
            if declared is False and ontology:
                downgrade(
                    flag,
                    f"ontology declares {flag}=true but the tool declares "
                    f"{flag}=false; the ontology value applies ({why})",
                )
            return ontology or declared is True

        effective_risk = node.risk
        if risk is not None:
            if _RISK_ORDER[risk] > _RISK_ORDER[node.risk]:
                effective_risk = risk
            elif _RISK_ORDER[risk] < _RISK_ORDER[node.risk]:
                downgrade(
                    "risk",
                    f"ontology declares risk={node.risk} but the tool declares "
                    f"risk={risk}; the ontology value applies",
                )

        if mutation is False and node.mutation and node.mutation_overridable:
            # The one weaker declaration that is honoured (section 4.4).
            effective_mutation = False
        else:
            effective_mutation = boolean(
                "mutation", mutation, node.mutation, "the call is treated as a mutation"
            )

        mapping = ToolMapping(
            capability_id=capability_id,
            risk=effective_risk,
            mutation=effective_mutation,
            requires_checkpoint=boolean(
                "requires_checkpoint",
                requires_checkpoint,
                node.requires_checkpoint,
                "F501 if no checkpoint precedes it",
            ),
            requires_approval=boolean(
                "requires_approval",
                requires_approval,
                node.requires_approval,
                "F502 if it is not approved",
            ),
            domain=domain,
        )
        return mapping, reports

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
                mapping, _ = self._effective_mapping(
                    tool_name,
                    capability_id,
                    risk="high",
                    mutation=True,
                    requires_checkpoint=True,
                )
            else:
                mapping, _ = self._effective_mapping(tool_name, capability_id)
            self._builtin_mappings[key] = mapping
        return mapping

    def register_mcp_tool(
        self,
        tool_name: str,
        capability_id: str = "execute",
        risk: str | None = None,
        mutation: bool | None = None,
        requires_checkpoint: bool | None = None,
        requires_approval: bool | None = None,
        domain: str | None = None,
    ) -> ToolMapping:
        """Register a dynamic tool-to-capability mapping.

        Used by :func:`grounded_agency.mcp.create_grounded_mcp_server`
        to register MCP-provided tools so that safety enforcement
        applies to them.

        The stored flags are the stricter of the ontology's flags for
        ``capability_id`` and the declared ones (STANDARD v1.1 section
        5.2.1). A declared flag weaker than the ontology's has no effect:
        it is logged and kept in :attr:`warnings` as W602
        (SAFETY_FLAG_DOWNGRADE). The one exception is ``mutation=False`` on
        a capability the ontology marks ``mutation_overridable``.

        Args:
            tool_name: The tool identifier (e.g., ``mcp__server__tool``).
            capability_id: Ontology capability ID.
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

        Returns:
            The effective mapping that was stored.

        Raises:
            ValueError: If the ontology does not define ``capability_id``
                (V101 UNKNOWN_CAPABILITY), ``risk`` is not a risk level, a
                flag is not a boolean, or ``domain`` is not a string.
                Nothing is registered.
        """
        if mutation is None and risk == "high":
            mutation = True
        if requires_checkpoint is None and risk == "high":
            requires_checkpoint = True

        mapping, reports = self._effective_mapping(
            tool_name,
            capability_id,
            risk=risk,
            mutation=mutation,
            requires_checkpoint=requires_checkpoint,
            requires_approval=requires_approval,
            domain=domain,
        )
        for report in reports:
            logger.warning(
                "%s %s: tool '%s': %s",
                report.code_str,
                report.name,
                tool_name,
                report.message,
            )
        self._dynamic_mappings[tool_name] = mapping
        self._warnings[tool_name] = reports
        return mapping

    def map_tool(self, tool_name: str, tool_input: dict[str, Any]) -> ToolMapping:
        """
        Map a tool invocation to its capability metadata.

        Bash is classified by its command. Any other name is looked up in
        the dynamic mappings (registered via :meth:`register_mcp_tool`),
        then the static mappings. A name found in neither is unclassified
        and maps to :data:`UNCLASSIFIED_TOOL`.

        Args:
            tool_name: SDK tool name (e.g., "Write", "Bash", "Read")
            tool_input: Tool input parameters

        Returns:
            ToolMapping with capability metadata
        """
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

    def _classify_bash_command(self, tool_input: dict[str, Any]) -> ToolMapping:
        """
        Classify a Bash command based on its content.

        1. Always-dangerous patterns (command substitution, backticks,
           variable expansion, eval, exec, source, control characters) and
           process substitution make the command a mutation at once.
        2. The line is split into simple commands (`_simple_commands`); one
           it cannot read is a mutation.
        3. Each simple command is classified; the first that is not low risk
           decides. Only a line whose every command is allow-listed as
           read-only is an observation.

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
        for words in commands:
            result = self._classify_single_command(words)
            if result.risk != "low":
                return result
        return self._builtin("Bash", "observe")

    def _classify_single_command(self, words: list[str]) -> ToolMapping:
        """
        Classify one simple command, given as its words.

        Checks in order: interpreter → network → destructive → read-only
        allowlist → secure default-deny.
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
