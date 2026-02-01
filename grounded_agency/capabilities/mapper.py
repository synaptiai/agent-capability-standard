"""
Tool-to-Capability Mapper

Maps Claude Agent SDK tool invocations to capability metadata,
enabling safety enforcement based on the Grounded Agency ontology.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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
    \bpython[23]?\s+(?!-[Vh])(?!--version)\S    # Python script execution (not --version)
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

# Patterns that indicate shell injection attempts or obfuscation
# These should always be treated as high-risk
_SHELL_INJECTION_PATTERNS = re.compile(
    r"""
    \$\( |                                # Command substitution $(...)
    ` |                                   # Backtick command substitution
    \$\{ |                                # Variable expansion ${...}
    ;\s*[a-zA-Z] |                         # Command chaining with semicolon
    \|\| |                                # OR chaining
    && |                                  # AND chaining (could be benign, but risky)
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
        "env",
        "printenv",
        "echo",
        "printf",
        "which",
        "whereis",
        "locate",
        "find",
        "grep",
        "awk",
        "sed",
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


@dataclass(slots=True)
class ToolMapping:
    """
    Maps a tool invocation to its Grounded Agency capability.

    Attributes:
        capability_id: The ontology capability ID (e.g., "mutate", "retrieve")
        risk: Risk level from ontology ("low", "medium", "high")
        mutation: Whether this tool modifies persistent state
        requires_checkpoint: Whether a checkpoint is required before use
    """

    capability_id: str
    risk: str
    mutation: bool
    requires_checkpoint: bool

    def __str__(self) -> str:
        checkpoint_marker = " [CHECKPOINT REQUIRED]" if self.requires_checkpoint else ""
        return f"{self.capability_id} (risk={self.risk}){checkpoint_marker}"


# Static mappings for SDK tools
_TOOL_MAPPINGS: dict[str, ToolMapping] = {
    # PERCEIVE layer - read-only tools
    "Read": ToolMapping(
        capability_id="retrieve",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    "Glob": ToolMapping(
        capability_id="search",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    "Grep": ToolMapping(
        capability_id="search",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    "LS": ToolMapping(
        capability_id="observe",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    "WebFetch": ToolMapping(
        capability_id="retrieve",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    "WebSearch": ToolMapping(
        capability_id="search",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    # EXECUTE layer - mutation tools
    "Write": ToolMapping(
        capability_id="mutate",
        risk="high",
        mutation=True,
        requires_checkpoint=True,
    ),
    "Edit": ToolMapping(
        capability_id="mutate",
        risk="high",
        mutation=True,
        requires_checkpoint=True,
    ),
    "MultiEdit": ToolMapping(
        capability_id="mutate",
        risk="high",
        mutation=True,
        requires_checkpoint=True,
    ),
    "NotebookEdit": ToolMapping(
        capability_id="mutate",
        risk="high",
        mutation=True,
        requires_checkpoint=True,
    ),
    # COORDINATE layer
    "Task": ToolMapping(
        capability_id="delegate",
        risk="medium",
        mutation=False,
        requires_checkpoint=False,
    ),
    "Skill": ToolMapping(
        capability_id="invoke",
        risk="medium",
        mutation=False,  # Skills may mutate but we check at skill level
        requires_checkpoint=False,
    ),
    "AskUser": ToolMapping(
        capability_id="inquire",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    "TodoRead": ToolMapping(
        capability_id="recall",
        risk="low",
        mutation=False,
        requires_checkpoint=False,
    ),
    "TodoWrite": ToolMapping(
        capability_id="persist",
        risk="low",
        mutation=True,
        requires_checkpoint=False,  # Low-risk mutation
    ),
}


class ToolCapabilityMapper:
    """
    Maps SDK tool invocations to Grounded Agency capabilities.

    Analyzes tool name and input to determine:
    - Which capability from the ontology is being exercised
    - Risk level (low, medium, high)
    - Whether mutation is occurring
    - Whether a checkpoint is required

    For Bash commands, performs additional analysis to determine
    if the command is read-only or mutating.

    Example:
        mapper = ToolCapabilityMapper(ontology)
        mapping = mapper.map_tool("Write", {"file_path": "/tmp/test.txt"})
        assert mapping.requires_checkpoint is True
    """

    def __init__(self, ontology: dict[str, Any] | None = None) -> None:
        """
        Initialize the mapper.

        Args:
            ontology: Raw ontology dict (optional, for validation)
        """
        self._ontology = ontology

    def map_tool(self, tool_name: str, tool_input: dict[str, Any]) -> ToolMapping:
        """
        Map a tool invocation to its capability metadata.

        Args:
            tool_name: SDK tool name (e.g., "Write", "Bash", "Read")
            tool_input: Tool input parameters

        Returns:
            ToolMapping with capability metadata
        """
        # Handle Bash specially - analyze command content
        if tool_name == "Bash":
            return self._classify_bash_command(tool_input)

        # Static mapping for known tools
        if tool_name in _TOOL_MAPPINGS:
            return _TOOL_MAPPINGS[tool_name]

        # Unknown tool - default to medium risk observe
        return ToolMapping(
            capability_id="observe",
            risk="medium",
            mutation=False,
            requires_checkpoint=False,
        )

    def _classify_bash_command(self, tool_input: dict[str, Any]) -> ToolMapping:
        """
        Classify a Bash command based on its content.

        Security principle: Fail-safe defaults. Unknown commands are treated
        as high-risk until explicitly allowlisted as read-only.

        Args:
            tool_input: Bash tool input with 'command' key

        Returns:
            ToolMapping based on command analysis
        """
        command = tool_input.get("command", "")

        # Empty command is suspicious - fail-safe
        if not command or not command.strip():
            return ToolMapping(
                capability_id="mutate",
                risk="high",
                mutation=True,
                requires_checkpoint=True,
            )

        # FIRST: Check for shell injection/obfuscation patterns
        # These bypass all other checks and are always high-risk
        if _SHELL_INJECTION_PATTERNS.search(command):
            return ToolMapping(
                capability_id="mutate",
                risk="high",
                mutation=True,
                requires_checkpoint=True,
            )

        # SEC-002: Check for interpreter invocations (python -c, node -e, etc.)
        if _INTERPRETER_PATTERNS.search(command):
            return ToolMapping(
                capability_id="execute",
                risk="high",
                mutation=True,
                requires_checkpoint=True,
            )

        # SEC-002: Check for process substitution and here-strings
        if _PROCESS_SUBSTITUTION_PATTERNS.search(command):
            return ToolMapping(
                capability_id="mutate",
                risk="high",
                mutation=True,
                requires_checkpoint=True,
            )

        # Check for network send operations
        if _NETWORK_SEND_PATTERNS.search(command):
            return ToolMapping(
                capability_id="send",
                risk="high",
                mutation=True,
                requires_checkpoint=True,
            )

        # Check for destructive operations
        if _DESTRUCTIVE_PATTERNS.search(command):
            return ToolMapping(
                capability_id="mutate",
                risk="high",
                mutation=True,
                requires_checkpoint=True,
            )

        # Check if it's a known read-only command (allowlist approach)
        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word.lower() in _READ_ONLY_COMMANDS:
            return ToolMapping(
                capability_id="observe",
                risk="low",
                mutation=False,
                requires_checkpoint=False,
            )

        # Check for two-word read-only commands
        first_two = " ".join(command.strip().split()[:2]).lower()
        if first_two in _READ_ONLY_COMMANDS:
            return ToolMapping(
                capability_id="observe",
                risk="low",
                mutation=False,
                requires_checkpoint=False,
            )

        # SECURE DEFAULT: Unknown commands are high-risk
        # This is fail-safe - we require checkpoint for anything not
        # explicitly allowlisted as read-only
        return ToolMapping(
            capability_id="mutate",
            risk="high",
            mutation=True,
            requires_checkpoint=True,
        )

    def is_high_risk(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if a tool invocation is high risk."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.risk == "high"

    def requires_checkpoint(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if a tool invocation requires a checkpoint."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.requires_checkpoint

    def is_mutation(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if a tool invocation is a mutation."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.mutation

    def get_capability_id(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Get the capability ID for a tool invocation."""
        mapping = self.map_tool(tool_name, tool_input)
        return mapping.capability_id
