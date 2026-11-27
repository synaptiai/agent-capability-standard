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
every prerequisite of all of them. ``Skill``, ``Agent`` and ``Task`` are
their own capability (``invoke``, ``delegate``) and Bash's worst case: the
commands a skill's file embeds and a subagent's definition names run with
no hook seeing them. Loading the checkpoint skill takes no checkpoint; the
state-saving call it leads to is classified on its own (section 5.18.6).
"""

from __future__ import annotations

import copy
import logging
import os
import re
import shlex
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from ..errors import ErrorCode, Severity, ValidationError, text_form
from ..remote_writes import binding_records as _remote_write_bindings
from ..utils.git import SAFE_GIT_OPTIONS, git_dir_is_made, safe_git_environment
from .registry import CapabilityNode, CapabilityRegistry

if TYPE_CHECKING:
    from ..profiles import AppliedProfiles
    from .bindings import ApprovalPolicy

logger = logging.getLogger("grounded_agency.capabilities.mapper")

# Risk levels in ascending order; the higher of two levels is the stricter.
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high")
_RISK_ORDER: dict[str, int] = {level: n for n, level in enumerate(RISK_LEVELS)}

# How the Bash classifier reads one simple command (_classify_single_command).
# A class narrower than the worst case (`mutate` and `send`) is given only by
# the command's own program, its first word as the shell passes it: the
# words of _LOCAL_FILE_PROGRAMS and _local_git_change, and the patterns
# below matched from the start of the words joined by spaces. Text that
# matches one further on is an argument (`curl URL -A 'git reset'`), which
# never narrows the class. Redirections are not read here: _simple_commands
# reads them, and gives an output redirection to anything but /dev/null the
# worst case first. (An alternative `\s+(>|>>)\s` of an earlier pattern was
# retried from every blank of a run and backtracked over the whole run, so a
# quoted run of 40,000 blanks took 8 s to classify.)

# Programs that change local files only, whatever their arguments: `mutate`.
# Not here, because they run a command or reach another host: `sed`, whose
# `e` command and `s///e` flag run one (`-i` or not), `docker rm|rmi|prune`
# (the daemon DOCKER_HOST or the docker context names receives the
# request), `tee`, `dd` and `cp` (which take the worst case, as any program
# on no list).
_LOCAL_FILE_PROGRAMS: frozenset[str] = frozenset(
    {"rm", "rmdir", "mv", "chmod", "chown", "ln", "unlink", "shred"}
)


def _local_git_change(words: list[str]) -> bool:
    """Whether a simple command is one of the git commands that change the
    local repository or work tree only (`git reset`, `git checkout --`,
    `git clean`, `git branch -d|-D`, and every `git stash` form), each word
    as the shell passes it: `mutate` in a repository where git neither
    fetches nor runs a program the repository names
    (``ToolCapabilityMapper._git_change``). A git option before the
    subcommand (`git -c ...`) is not recognised."""
    if len(words) < 2 or words[0] != "git":
        return False
    sub, rest = words[1], words[2:]
    if sub in ("reset", "clean", "stash"):
        return True
    if sub == "checkout":
        return rest[:1] == ["--"]
    return sub == "branch" and bool(rest) and rest[0][:2] in ("-d", "-D")


def _writes_tree(words: list[str]) -> bool:
    """Whether a local git change (:func:`_local_git_change`) may write
    files of the work tree from objects, through any smudge filter
    configured (`git reset`, `git checkout --`, `git stash`); `git clean`
    and `git branch -d` write none."""
    return words[1] in ("reset", "checkout", "stash")


# Mutations of a system the command reaches by an argument or its
# configuration (a remote, a registry, a cluster): `mutate`, and `send` as
# well, since the classifier cannot tell which system receives the change
# (STANDARD 1.2.0 section 5.18.3: a request to another system whose effect the
# binding does not know is `send`), so a destination policy applies to it.
_REMOTE_MUTATION_PATTERNS = re.compile(
    r"""
    git\s+push\b |                                                 # Pushes
    npm\s+(publish|unpublish)\b |                                  # Registries
    docker\s+push\b |
    kubectl\s+(delete|apply|patch|edit)\b                          # Clusters
    """,
    re.VERBOSE,
)

# SEC-002: Interpreter invocation patterns that can execute arbitrary code.
# These bypass other checks because the outer command looks benign. Matched
# anywhere in the words (a program that runs another, `env` or `xargs`, may
# run the interpreter): a match puts `execute` first in the worst case, and
# takes nothing from it.
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

# Programs that send, matched from the start of the words: `send` first,
# with `mutate` beside it, since each also changes files or another system
# (`curl -o`, `scp` and `rsync` write local files, `ssh` runs a command
# there).
_NETWORK_SEND_PATTERNS = re.compile(
    r"""
    curl\s+.*(-X\s*(POST|PUT|PATCH|DELETE)|--data|--form|-d\s) |  # curl with data
    wget\s+--post |                                               # wget POST
    ssh\s |                                                       # SSH connections
    scp\s |                                                       # SCP transfers
    rsync\s |                                                     # rsync
    nc\s |                                                        # netcat
    telnet\s |                                                    # telnet
    ftp\s                                                         # ftp
    """,
    re.VERBOSE,
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
# A descriptor number as bash reads one: ASCII digits only.
_FD_NUMBER = re.compile(r"[0-9]+")

# Commands that only read, unless given an option that writes (_writes).
# Not here, because they run another command or can write a file whatever
# their options: env, xargs, sed, awk, tee and the interpreters, and the
# pagers less and more (a lesskey file, which `less -k`, `--lesskey-src` or
# any abbreviation of them names, `/dev/stdin` fed by a pipe included, sets
# LESSOPEN, which less runs; macOS's more is less). Nor commands that reach
# another host whatever their options, which a destination policy must see
# (STANDARD 1.2.0 section 5.18.3): `npm view` and `npm list` (a registry,
# which a project's .npmrc or --registry names: npm's update check sends
# the token the .npmrc gives for it, `${ENV}` expanded, to it),
# `kubectl get|describe|logs` (a server, which --server or --kubeconfig
# names, and a kubeconfig's `exec` runs a command) and `docker
# ps|images|logs` (a daemon, which DOCKER_HOST or the docker context names,
# over tcp or ssh; a container name or filter goes to it). Nor `pip list`
# and `pip show`: pip runs the program the site configuration's `python =`
# names (sys.prefix/pip.conf, read even with --isolated: an in-project
# virtual environment keeps the one a repository ships there), and the
# interpreter it starts runs the `.pth` files of its site-packages, which an
# editable install of the project, or a shipped environment, puts there
# (security round 5). `git` reads local state only where it cannot fetch
# (git_may_fetch), and `git remote` only with the arguments _writes allows.
# `printf` only without an option: `printf -v NAME` sets a shell variable
# that the later commands of the line run with (_writes).
_READ_ONLY_COMMANDS: frozenset[str] = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
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
_COMMIT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# Bash opens a connection for an input redirection from one of these paths
# (`cat < /dev/tcp/host/80`): a request to another host.
_NETWORK_PATHS = ("/dev/tcp/", "/dev/udp/")

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


@dataclass(frozen=True, slots=True)
class _Options:
    """The options with which a command only reads (GNU getopt_long rules:
    short options may share a word, a long option may be any prefix of its
    name, and options may follow operands). Any other option, and any
    prefix of a long option that writes, makes the command write
    (:func:`_option_writes`)."""

    flags: str = ""  # short options without an argument
    with_arg: str = ""  # short options with an argument, attached or the next word
    attached_arg: str = ""  # short options with an optional, attached argument
    long: frozenset[str] = frozenset()  # long options, `=value` allowed
    long_with_arg: frozenset[str] = frozenset()  # value attached or the next word
    writing: frozenset[str] = frozenset()  # long options that write
    max_operands: int | None = None  # None: any number of operands
    operand_prefix: str = ""  # every operand must start with it


# The options with which each of these commands only reads (GNU coreutils,
# file, net-tools hostname). Any other option is taken to write: sort -o,
# -T and --compress-program (which runs a program), date -s and an operand
# that sets the clock, hostname -F, -b and an operand, file -C, uniq's second
# operand. An abbreviation of a writing option (`sort --o=x`, `file --compi`)
# writes too.
_READ_ONLY_OPTIONS: dict[str, _Options] = {
    "sort": _Options(
        flags="bdfgiMhnRrVcCmsuz",
        with_arg="kSt",
        long=frozenset(
            "ignore-leading-blanks dictionary-order ignore-case "
            "general-numeric-sort ignore-nonprinting month-sort "
            "human-numeric-sort numeric-sort random-sort reverse version-sort "
            "check merge stable unique zero-terminated debug help "
            "version".split()
        ),
        long_with_arg=frozenset(
            "random-source sort batch-size files0-from key buffer-size "
            "field-separator parallel".split()
        ),
        writing=frozenset({"output", "temporary-directory", "compress-program"}),
    ),
    "uniq": _Options(
        flags="cdDiuz",
        with_arg="fsw",
        long=frozenset(
            "count repeated all-repeated group ignore-case unique "
            "zero-terminated help version".split()
        ),
        long_with_arg=frozenset({"skip-fields", "skip-chars", "check-chars"}),
        max_operands=1,  # `uniq INPUT OUTPUT` writes OUTPUT
    ),
    "date": _Options(
        flags="uR",
        with_arg="dfr",
        attached_arg="I",
        long=frozenset(
            "date debug file iso-8601 resolution rfc-email rfc-3339 reference "
            "utc universal help version".split()
        ),
        long_with_arg=frozenset({"date", "file", "reference", "rfc-3339"}),
        writing=frozenset({"set"}),
        operand_prefix="+",  # any other operand sets the clock
    ),
    "hostname": _Options(
        flags="aAdfiIsvyhV",
        long=frozenset(
            "alias all-fqdns domain fqdn long ip-address all-ip-addresses "
            "short verbose yp nis help version".split()
        ),
        writing=frozenset({"file", "boot"}),
        max_operands=0,  # an operand sets the host name
    ),
    "file": _Options(
        flags="bcdEhiklLNn0rsSvzZ",
        with_arg="eFfmP",
        long=frozenset(
            "brief checking-printout exclude-quiet extension no-dereference "
            "mime mime-type mime-encoding keep-going list dereference no-pad "
            "no-buffer print0 raw special-files no-sandbox uncompress "
            "uncompress-noreport apple help version".split()
        ),
        long_with_arg=frozenset(
            {"exclude", "separator", "files-from", "magic-file", "parameter"}
        ),
        writing=frozenset({"compile", "preserve-date"}),
    ),
}

# Commands whose arguments can make them write: a word the shell expands
# (an unquoted `*`, `?` or `[`) may become any file name, an option
# included, so such a word makes the command write. Every command whose
# options are read (_writes) is here (security round 3: `pip show *`, when
# pip was listed, became `pip show --log=FILE ...` and wrote the log).
_ARGUMENT_WRITERS: frozenset[str] = frozenset(
    {*_READ_ONLY_OPTIONS, "find", "git", "printf"}
)

# bash's blanks, which end a word: a space and a tab, never another
# character Unicode calls a space (`{a\u3000,-o}` is one word to bash).
_BLANKS = re.compile(r"[ \t]+")


def _brace_expansion(masked: str) -> bool:
    """Whether bash may expand a brace in ``masked``, a line whose quoted
    characters are masked (:func:`_mask_quoted`): whether a word holds an
    unquoted `{`, after it an unquoted `,` or `..`, and after that an
    unquoted `}`. bash replaces such a group with words this reading never
    sees, and closes a group only at a `}` after its first comma
    (`{a},-o}x` is `a}x -ox`), so any such order counts, whatever lies
    between. Linear in the line: each word is searched three times."""
    for word in _BLANKS.split(masked):
        start = word.find("{")
        if start < 0:
            continue
        seps = [p for p in (word.find(",", start), word.find("..", start)) if p >= 0]
        if seps and word.find("}", min(seps)) >= 0:
            return True
    return False


def _names_a_variable(word: str) -> bool:
    """Whether ``word`` (masked) is bash's `{varname}` form: right before a
    redirection, bash opens a descriptor of 10 or more and assigns its
    number to the variable (`echo x {PATH}>/dev/null` sets PATH to 10 for
    the rest of the line: echo, printf and pwd are builtins, run in the
    shell itself). Any word that opens with `{` and closes with `}` counts,
    a name bash would refuse included."""
    return len(word) >= 2 and word[0] == "{" and word[-1] == "}"


@dataclass(frozen=True, slots=True)
class _Command:
    """A simple command: its words, as the shell passes them, and whether
    one of them holds an unquoted `*`, `?` or `[` (a pathname expansion)."""

    words: list[str]
    globbed: bool = False


def _mask_quoted(command: str) -> tuple[str, bool] | None:
    """``command`` with each quoted character (the quotes, a backslash and
    what it escapes, and everything between quotes) replaced by ``x``, and
    whether the shell expands a parameter in it: a `$` outside single
    quotes (`$NAME`, `$'...'`, `$"..."`, `${...}`, `$(...)`), whose value
    this reading cannot know. None for an unbalanced quote."""
    out: list[str] = []
    expands = False
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote == "'":
            out.append("x")
            if ch == "'":
                quote = ""
        elif ch == "\\" and i + 1 < len(command):
            out.append("xx")
            i += 1
        elif quote == '"':
            out.append("x")
            if ch == '"':
                quote = ""
            elif ch == "$":
                expands = True
        elif ch in "'\"":
            out.append("x")
            quote = ch
        else:
            out.append(ch)
            if ch == "$":
                expands = True
        i += 1
    if quote:
        return None
    return "".join(out), expands


# A character outside ASCII right before an ASCII character bash treats
# specially that a double-byte encoding can take as a character's second
# byte (0x30 to 0x7E): in such a locale bash may read the pair as one
# character, so the special character is gone (_simple_commands). Looked for
# in the line as written, quoted text included: a backslash quotes inside
# double quotes too, and an escaped character outside ASCII (`\ぁ|`) is
# masked whole, though its last byte may take the `|` there.
_SPECIAL_AFTER_NON_ASCII = re.compile(r"[^\x00-\x7f][;<>?@\[\\\]^`{|}~]")


def _tokens(command: str) -> list[str] | None:
    """The shell words and operators of a line (POSIX rules, operators as
    their own tokens); None when they cannot be read."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def _simple_commands(command: str) -> list[_Command] | None:
    """
    The simple commands of a shell command line, each as its words.

    Returns None when the line holds something this reading cannot show to be
    harmless: an unbalanced quote, a parameter or brace expansion, a subshell
    or group, a here-document, an output redirection to anything but
    /dev/null or `>&N` (N in ASCII digits), a redirection after a
    `{varname}` word, a redirection in a simple command with no words, or a
    character outside ASCII right before a backslash or another character
    bash treats specially.
    Redirections are dropped from the words. Comments are not recognised, so
    `ls # ; rm x` reads as two commands: a reading that errs splits a command
    into more commands to check, never fewer.

    The line is read as Unicode text; bash reads its bytes in the user's
    locale. In a double-byte locale (GBK, GB18030, BIG5, Shift JIS, JOHAB)
    the last byte of such a character's UTF-8 form can open a character
    whose second byte is the next ASCII byte, so bash sees no such ASCII
    character. A backslash gone unquotes what it escaped (`ls ぁ\\;touch f`
    and `ls "ぁ\\";touch f #"` are two commands there, one here); a `|`
    gone joins two commands into one (`find t1 -name ぁ|ls -o -delete` is
    one find there, which deletes); a `{` gone makes a brace group (`sort
    {-o,ぁ{x}` is `sort -o ぁ{x` there, which writes that file). So such a
    pair takes the worst case, quoted or not. A byte below 0x30 (a quote,
    `$`, `&`, `(`, `)`, `*`, `!`, `#` or a blank) is no second byte in any
    of them, and a letter, a digit, `_`, `:` or `=` taken changes nothing
    bash does (it passes a word's bytes on as they are): with those pairs
    refused, this reading sees at least the commands, expansions and
    redirections bash makes.
    """
    if _SPECIAL_AFTER_NON_ASCII.search(command):
        return None
    masked = _mask_quoted(command)
    if masked is None or masked[1] or _brace_expansion(masked[0]):
        return None
    tokens = _tokens(command)
    if tokens is None:
        return None
    # The same reading of the masked line gives the same words, each with
    # its quoted characters masked: an unquoted glob character is one left,
    # and only a token that is an operator there too is one. shlex gives a
    # quoted or escaped operator (`'<'`, `";"`, `\|`) as the bare operator,
    # but the shell passes it as a word: `find f '<' -execdir sh {} +` runs
    # its -execdir, and `grep ';' f` is one command. Should the two readings
    # ever differ in length, no token can be placed: the worst case.
    shadow = _tokens(masked[0])
    if shadow is None or len(shadow) != len(tokens):
        return None
    commands: list[_Command] = [_Command([])]
    # The simple commands (by index) that hold a redirection.
    redirected: set[int] = set()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not _is_operator(shadow[i]):
            last = commands[-1]
            commands[-1] = _Command(
                [*last.words, token],
                last.globbed or any(c in "*?[" for c in shadow[i]),
            )
        elif token != shadow[i]:
            return None  # an operator the two readings do not agree on
        elif token in _SEPARATORS:
            commands.append(_Command([]))
        elif token == "<" or token in _OUTPUT_REDIRECTS:
            if i + 1 == len(tokens) or _is_operator(shadow[i + 1]):
                return None  # no file named: not a line the shell runs
            if i > 0 and not _is_operator(shadow[i - 1]):
                if _names_a_variable(shadow[i - 1]):
                    return None  # {varname}>...: sets a shell variable
            target = tokens[i + 1]
            if token == "<":
                if target.startswith(_NETWORK_PATHS):
                    return None  # a connection to another host, not a file
            elif target != "/dev/null" and not (
                # bash reads only ASCII digits as a descriptor: `>&١` is
                # `&>١`, a file (str.isdigit takes any Unicode digit).
                token == ">&" and _FD_NUMBER.fullmatch(target)
            ):
                return None
            redirected.add(len(commands) - 1)
            i += 1  # skip the file's name
        else:
            return None  # (, ), <<, <>, ;; and the like
        i += 1
    if any(not commands[n].words for n in redirected):
        # A redirection with no command (`ls; <f`) runs nothing in bash, but
        # zsh, the Bash tool's shell where it is the user's (macOS's
        # default), runs `$READNULLCMD <f` for it, a pager (less on macOS,
        # Debian's `pager`), which a LESSOPEN or lesskey `|-` preprocessor
        # makes run code, and `$NULLCMD` for an output one: the worst case
        # (security round 5). A command with neither words nor a
        # redirection (`ls;`, `ls &`) runs nothing in either.
        return None
    return [c for c in commands if c.words]


def _is_operator(token: str) -> bool:
    """Whether a token of :func:`_tokens` is an operator: shlex gives one
    as a run of operator characters only."""
    return bool(token) and set(token) <= _OPERATOR_CHARS


def _option_writes(args: list[str], options: _Options) -> bool:
    """Whether ``args`` hold an option or operand outside ``options``."""
    readable_long = options.long | options.long_with_arg
    operands: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            operands.extend(args[i + 1 :])
            break
        if arg.startswith("--"):
            name, eq, _ = arg[2:].partition("=")
            # getopt_long takes any prefix of a long option's name.
            if not name or any(w.startswith(name) for w in options.writing):
                return True
            matches = [o for o in readable_long if o.startswith(name)]
            if not matches:
                return True
            if not eq and any(o in options.long_with_arg for o in matches):
                i += 1  # its value is the next word
        elif arg.startswith("-") and arg != "-":
            for n, letter in enumerate(arg[1:], start=2):
                if letter in options.with_arg:
                    if n == len(arg):
                        i += 1  # its argument is the next word
                    break
                if letter in options.attached_arg:
                    break
                if letter not in options.flags:
                    return True
        else:
            operands.append(arg)
        i += 1
    if options.max_operands is not None and len(operands) > options.max_operands:
        return True
    return any(not o.startswith(options.operand_prefix) for o in operands)


def _long_prefix_of(arg: str, names: Iterable[str]) -> bool:
    """Whether ``arg`` is a long option that is, or abbreviates, one of
    ``names`` (getopt_long and git take any prefix of a name)."""
    if not arg.startswith("--"):
        return False
    name = arg[2:].partition("=")[0]
    return bool(name) and any(n.startswith(name) or name.startswith(n) for n in names)


def _writes(words: list[str], globbed: bool = False) -> bool:
    """Whether an allow-listed command is given an option that writes,
    deletes or runs something. ``globbed``: one of its words is expanded
    by the shell, so it may be any option. Errs towards True."""
    name, args = words[0], words[1:]
    if globbed and name in _ARGUMENT_WRITERS:
        return True
    options = _READ_ONLY_OPTIONS.get(name)
    if options is not None:
        return _option_writes(args, options)
    if name == "find":
        return any(a in _FIND_WRITES for a in args)
    if name == "printf":
        # bash's printf takes one option, -v NAME, which assigns its output
        # to the shell variable NAME (PATH, HOME, IFS, an array element whose
        # subscript bash evaluates as arithmetic, running a `$(...)` the
        # format wrote): the later commands of the line run with it. A first
        # argument that starts with `-` is an option (or `--`).
        return bool(args) and args[0].startswith("-")
    if name == "git":
        if any(_long_prefix_of(a, ("output",)) for a in args):
            return True
        sub, rest = args[0], args[1:]
        if sub == "branch":
            return not all(a in _GIT_BRANCH_LISTING for a in rest)
        if sub == "remote":
            # `git remote show NAME|URL` asks that remote: a request to
            # another host. `get-url` only reads the configuration.
            return not (rest in ([], ["-v"], ["--verbose"]) or rest[0] == "get-url")
    return False


# The longest command the classifier reads, in UTF-8 bytes: a longer one is
# the worst case before any pattern runs, so no reading of it can run long
# (the plugin's PreToolUse hook has the same bound).
_MAX_COMMAND_BYTES = 4096

# The git configuration that makes a repository a partial clone: a promisor
# remote, or extensions.partialClone naming one (what `git config
# --get-regexp` matches, keys in lower case).
_PROMISOR_CONFIG = r"^(remote\..+\.promisor|extensions\.partialclone)$"


# The configuration keys that name a program git runs: core.fsmonitor (to
# refresh the index: `git status`, `git diff`, `git stash`; true and false
# name git's own), a diff driver's textconv or command and diff.external
# (`git diff`, `git log -p`, `git show`), a filter's clean, smudge or process
# (a read hashes a changed file through clean; a restore writes through
# smudge), a merge driver (a restore merges), a signature program (`git log`
# with log.showSignature) and a pager. The plugin's PreToolUse hook holds the
# same pattern (GIT_PROGRAM_KEYS).
_PROGRAM_CONFIG = (
    r"^(core\.fsmonitor|core\.pager|pager\..+|diff\.external"
    r"|diff\..+\.(textconv|command)|filter\..+\.(clean|smudge|process)"
    r"|merge\..+\.driver|gpg\.program|gpg\..+\.program)$"
)
# The configuration keys of a filter git runs when it writes a file of the
# work tree from an object: a filter driver's smudge or process command.
# The plugin's PreToolUse hook holds the same pattern (GIT_SMUDGE_KEYS).
_SMUDGE_CONFIG = r"^filter\..+\.(smudge|process)$"
# The commands `git lfs install --skip-smudge` writes, as they are: they
# write the pointer file and ask no server (a probe logged no request for a
# `git reset --hard` that the plain commands made ask the LFS server). The
# plugin's PreToolUse hook holds the same two (git_filter_runs).
_SKIPPING_SMUDGE = frozenset(
    {b"git-lfs smudge --skip -- %f", b"git-lfs filter-process --skip"}
)
# The configuration scopes a repository's own files give (`git config
# --show-scope`; an included file takes the scope of the file that
# includes it).
_REPOSITORY_SCOPES = (b"local", b"worktree")
# core.fsmonitor values that name git's own daemon or none, not a program.
_GIT_BOOLEANS = frozenset(
    {b"", b"true", b"false", b"yes", b"no", b"on", b"off", b"1", b"0"}
)


def _git(git: str, where: str, *args: str) -> subprocess.CompletedProcess[bytes]:
    """git ``args`` run in ``where`` as the layer runs it on its own behalf:
    no fsmonitor program, no hook, no lazy fetch (:mod:`..utils.git`)."""
    return subprocess.run(
        [git, *SAFE_GIT_OPTIONS, "-C", where, *args],
        capture_output=True,
        timeout=10,
        check=False,
        env=safe_git_environment(),
    )


def _where(cwd: str | None) -> str:
    return cwd if isinstance(cwd, str) and cwd else os.getcwd()


def git_dir_may_be_content(cwd: str | None = None) -> bool:
    """Whether the git directory git finds from ``cwd`` (this process's
    working directory when it is None) may be repository content: one git
    did not make for a work tree (:func:`~..utils.git.git_dir_is_made`), such
    as a directory a repository ships holding ``HEAD``, ``objects/`` and
    ``refs/`` (an embedded bare repository). git run there reads that
    directory's configuration and hooks and runs what they name
    (``core.fsmonitor`` for `git status`, `git ls-files` and `git stash`, a
    ``diff.<driver>.textconv`` for `git log -p`, `git show` and `git diff`).
    No repository there is a no; no git, or git failing in another way, a
    yes. The plugin's PreToolUse hook asks the same (git_dir_is_content)."""
    git = shutil.which("git")
    if git is None:
        return True
    try:
        done = _git(git, _where(cwd), "rev-parse", "--absolute-git-dir")
    except OSError, ValueError, subprocess.SubprocessError:
        return True
    if done.returncode != 0:
        return False
    found = done.stdout.decode("utf-8", "surrogateescape").strip()
    return not git_dir_is_made(found)


def git_may_fetch(cwd: str | None = None) -> bool:
    """Whether git, run in ``cwd`` (this process's working directory when it
    is None), may ask another host for an object it reads:

    - in a partial clone, git fetches each object it lacks from the promisor
      remote, so a read such as `git show <id>` or `git log -p` reaches that
      host, and the object id the agent chose goes to it (STANDARD 1.2.0
      section 5.18.3: a request to another system);
    - in a repository with submodules (``modules/`` in its common git
      directory, or a gitlink in its index), a read that looks into one
      (`--submodule=diff`, the ``diff.submodule`` setting, `git status`)
      reads that submodule's object store, where a partial clone fetches the
      same way.

    Read from the configuration and index git itself reads there; anything
    git does not answer (no git, no such directory, a configuration it
    cannot read) counts as yes. The plugin's PreToolUse hook asks the same
    question."""
    git = shutil.which("git")
    if git is None:
        return True
    where = _where(cwd)
    try:
        done = _git(git, where, "config", "--get-regexp", _PROMISOR_CONFIG)
        if not (done.returncode == 1 and not done.stdout):
            return True
        found = _git(git, where, "rev-parse", "--git-common-dir")
        if found.returncode != 0:
            return False  # no repository: nothing to fetch for
        common = os.path.join(
            where, found.stdout.decode("utf-8", "surrogateescape").strip()
        )
        if os.path.lexists(os.path.join(common, "modules")):
            return True
        index = _git(git, where, "ls-files", "--stage", "--", ":/")
        if index.returncode != 0:
            return True
    except OSError, ValueError, subprocess.SubprocessError:
        return True
    return any(line.startswith(b"160000 ") for line in index.stdout.splitlines())


def _names_program(listing: bytes) -> bool:
    """Whether a `git config --show-scope --get-regexp` listing of
    :data:`_PROGRAM_CONFIG` sets one of its keys in a scope the repository's
    own files give (core.fsmonitor only to a value other than a boolean)."""
    for line in listing.splitlines():
        scope, tab, rest = line.partition(b"\t")
        if not tab or scope not in _REPOSITORY_SCOPES:
            continue
        key, _, value = rest.partition(b" ")
        if key == b"core.fsmonitor" and value.lower() in _GIT_BOOLEANS:
            continue
        return True
    return False


# The hooks git runs on a read that writes the index (`git status`), and
# those it runs on a change of the work tree, the index or a ref: `git
# reset` and `git stash` run post-index-change and reference-transaction,
# `git branch -d` and `git stash drop` reference-transaction, `git checkout
# --` post-checkout and post-index-change (probed with every hook git
# documents present; `git clean` ran none).
_READ_HOOKS: tuple[str, ...] = ("post-index-change",)
_CHANGE_HOOKS: tuple[str, ...] = (
    "post-index-change",
    "reference-transaction",
    "post-checkout",
)


def _repository_runs(cwd: str | None, hooks: tuple[str, ...]) -> bool:
    """Whether git, run in ``cwd`` (this process's working directory when
    it is None), may run a program the repository itself names: its own
    configuration sets a key of :data:`_PROGRAM_CONFIG`, or its hooks
    directory holds one of ``hooks``. No repository there is a no; no git,
    or git failing in another way, a yes."""
    git = shutil.which("git")
    if git is None:
        return True
    where = _where(cwd)
    try:
        if _git(git, where, "rev-parse", "--absolute-git-dir").returncode != 0:
            return False
        done = _git(
            git, where, "config", "--show-scope", "--get-regexp", _PROGRAM_CONFIG
        )
        if done.returncode not in (0, 1):
            return True
        if done.returncode == 0 and _names_program(done.stdout):
            return True
        # Where git looks for hooks (core.hooksPath, else <git dir>/hooks):
        # asked without the layer's options, which point it at /dev/null.
        found = subprocess.run(
            [
                git,
                "-c",
                "core.fsmonitor=false",
                "-C",
                where,
                "rev-parse",
                "--git-path",
                "hooks",
            ],
            capture_output=True,
            timeout=10,
            check=False,
            env=safe_git_environment(),
        )
        if found.returncode != 0 or not found.stdout.strip():
            return True
        path = os.path.join(where, os.fsdecode(found.stdout.strip()))
        return any(os.path.lexists(os.path.join(path, hook)) for hook in hooks)
    except OSError, ValueError, subprocess.SubprocessError:
        return True


def git_config_may_run(cwd: str | None = None) -> bool:
    """Whether git, run in ``cwd`` (this process's working directory when
    it is None), may run a program the repository itself names: its own
    configuration (the local and worktree scopes, with the files they
    include) sets a key of :data:`_PROGRAM_CONFIG`, or its hooks directory
    holds ``post-index-change``, which git runs when a read such as `git
    status` writes the index. A repository delivered with its ``.git`` (an
    archive, a copied checkout) brings that configuration and those hooks,
    and one approved `git config core.fsmonitor ./x` writes it; the user's
    own settings (global, system, the command line) are not repository
    content. No repository there is a no; no git, or git failing in another
    way, a yes. The plugin's PreToolUse hook asks the same
    (git_runs_configured)."""
    return _repository_runs(cwd, _READ_HOOKS)


def git_change_may_run(cwd: str | None = None) -> bool:
    """:func:`git_config_may_run` for a git command that changes the local
    repository or work tree (`git reset`, `git checkout --`, `git branch
    -d`, `git stash`): its hooks directory may also hold
    ``reference-transaction`` or ``post-checkout``, which git runs on such
    a change (:data:`_CHANGE_HOOKS`; git-lfs's ``post-checkout`` fetches
    from the LFS server). No repository there is a no; no git, or git
    failing in another way, a yes."""
    return _repository_runs(cwd, _CHANGE_HOOKS)


def git_filter_may_run(cwd: str | None = None) -> bool:
    """Whether git, writing files of the work tree from objects in ``cwd``
    (this process's working directory when it is None), may run a filter
    that reaches another host: a filter driver's smudge or process command
    configured in any scope, the user's own included. git runs it for each
    file whose attributes name the driver, which the repository chooses
    (its `.gitattributes`, or those of the commit written), and git-lfs,
    whose `git lfs install` writes its filter to the global configuration,
    asks the LFS server the repository's `.lfsconfig` or remote names for
    each object its store lacks, sending the object's id: `git reset --hard`
    to a commit holding an LFS pointer, and a restore of a checkpoint that
    holds one, did (security round 5). Reads run no smudge. Only the
    commands `git lfs install --skip-smudge` writes (:data:`_SKIPPING_SMUDGE`)
    count as none. No repository there is a no; no git, or git failing in
    another way, a yes. The plugin's PreToolUse hook asks the same
    (git_filter_runs)."""
    git = shutil.which("git")
    if git is None:
        return True
    where = _where(cwd)
    try:
        if _git(git, where, "rev-parse", "--absolute-git-dir").returncode != 0:
            return False
        done = _git(git, where, "config", "-z", "--get-regexp", _SMUDGE_CONFIG)
    except OSError, ValueError, subprocess.SubprocessError:
        return True
    if done.returncode == 1 and not done.stdout:
        return False
    if done.returncode != 0:
        return True
    # -z: each entry is the key, a line break, the value, then a NUL.
    for entry in done.stdout.split(b"\0"):
        if entry and entry.partition(b"\n")[2] not in _SKIPPING_SMUDGE:
            return True
    return False


def _home_directory() -> str:
    """The user's home directory as the password database gives it (not
    HOME, as the plugin's hooks read it), physical; ``""`` where there is
    none."""
    try:
        import pwd

        return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
    except ImportError, KeyError, OSError:
        return ""


def command_may_be_content(
    name: str,
    cwd: str | None = None,
    search_path: str | None = None,
    project_dir: str | None = None,
) -> bool:
    """Whether the program the shell runs for the command name ``name`` may
    be repository content (STANDARD 1.2.0 section 5.18.3: a call is
    classified by its effect, and a layer that cannot tell which program
    runs takes the worst case). bash runs a name with no slash as the first
    executable file of that name in a directory of its PATH
    (``search_path``: the PATH the commands run with; None for this
    process's): the repository's own `git`, `cat` or `ls` runs in place of
    the system's when PATH holds an empty or relative entry (read from the
    working directory, ``cwd``: ``PATH=node_modules/.bin:$PATH``, a leading
    colon) under which the name is found, or an entry in the project
    directory (``project_dir``, None for this process's working directory:
    an activated virtual environment, direnv's ``PATH_add``) whose file of
    that name lies, links followed, in the project (not where the project is
    the user's home directory, or holds it). Yes then, when no such file is
    found, and when the lookup fails. The plugin's PreToolUse hook asks the
    same (command_may_be_content)."""
    if not name or "/" in name:
        return True
    path = os.environ.get("PATH", "") if search_path is None else search_path
    if not path:
        return True
    where = _where(cwd)
    found = None
    for entry in path.split(os.pathsep):
        relative = not os.path.isabs(entry)
        candidate = (
            os.path.join(where, entry, name) if relative else os.path.join(entry, name)
        )
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            # The first that bash would run: an empty or relative entry is
            # read from the working directory, repository content.
            if relative:
                return True
            found = candidate
            break
    if found is None:
        return True
    try:
        project = os.path.realpath(project_dir if project_dir else os.getcwd())
        real = os.path.realpath(found, strict=True)
    except OSError, ValueError:
        return True
    within = project.rstrip(os.sep) + os.sep
    home = _home_directory()
    if home and (home + os.sep).startswith(within):
        # A project that is the home directory, or holds it, is no
        # repository's.
        return False
    return real.startswith(within)


def _is_read_only(command: _Command) -> bool:
    """Whether a simple command is on the read-only allow-list (by its exact
    name, or its name and subcommand, each one word) with no option that
    writes. The shell runs the program the first word names as it stands:
    one holding a blank (`"git status"`, quoted) or a slash names a program
    on no list, whatever the list's entries spell."""
    words = command.words
    if any(c.isspace() or c == "/" for c in words[0]):
        return False
    # With no blank in the first word, a two-word entry can only match the
    # first word and the second.
    listed = words[0] in _READ_ONLY_COMMANDS or (
        len(words) > 1 and f"{words[0]} {words[1]}" in _READ_ONLY_COMMANDS
    )
    return listed and not _writes(words, command.globbed)


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
            ``approval`` member, section 5.18.7), joined for a composite
            with that of each binding it invokes, transitively: the most
            approvers, the shortest expiry, a role one of them sets
            (section 5.18.4)
        control: The tool only signals the host and is never refused
            (section 5.18.3)
        classifier: The classifier the binding names (section 5.18.3); this
            mapper applies the worst case to such a tool's calls
        destination: For a ``send`` tool, the RFC 6901 pointer to the
            argument that holds the destination (section 4.4.2)
        person_required: An applied domain profile requires a person's
            approval for the call (``require_human`` or
            ``block_autonomous``, section 5.21.3), or for a binding it
            invokes, transitively
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
    # COORDINATE layer. "AskUserQuestion" is the current Claude Code name
    # of the tool once called "AskUser". Task, Agent and Skill are in
    # _UNSEEN_COMMANDS.
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
    # The plugin's typed remote writes, under the names Claude Code gives its
    # MCP server's tools (grounded_agency/remote_writes.py): each a gated
    # mutate. A host that offers the server under another name loads
    # remote_writes.binding_records(<its prefix>) with load_bindings.
    **{r["tool"]: r["capability"] for r in _remote_write_bindings()},
}

# Tools whose call loads a definition that runs commands no hook sees, with
# their own capability:
# Claude Code runs the shell commands a skill's file embeds (!`cmd` and ```!
# blocks, the call's arguments substituted into them) as the skill loads,
# under its allowed-tools, and starts the hooks and MCP servers a subagent's
# definition names as the subagent runs, with no PreToolUse or PostToolUse
# event for any of them; and a project's skill or agent can take any name,
# a built-in one's included. A call of one is its own capability and Bash's
# worst case, a gated `mutate` and `send` (STANDARD 1.2.0 section
# 5.18.3: what the classifier cannot see). Loading the checkpoint skill
# takes no checkpoint: the `git stash create` it leads to does (section
# 5.18.6). The plugin's PreToolUse hook gates them too. "Agent" is the
# current Claude Code name of the tool once called "Task".
_UNSEEN_COMMANDS: dict[str, str] = {
    "Task": "delegate",
    "Agent": "delegate",
    "Skill": "invoke",
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
        self._profiled_revision = 0
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
        # Whether git, run in a directory (the call's, or None for this
        # process's), may ask another host for an object it reads: a git
        # command the allow-list reads as `observe` takes the worst case
        # there (:func:`git_may_fetch`: a partial clone, or a repository
        # with submodules). A lookup that fails is a yes.
        self.git_may_fetch: Callable[[str | None], bool] = git_may_fetch
        # Whether the git directory git finds from a directory may be
        # repository content, whose configuration names programs git runs:
        # every git command the classifier would let pass (a read, `git
        # stash create`, a restore) takes the worst case there
        # (:func:`git_dir_may_be_content`). A lookup that fails is a yes.
        self.git_dir_may_be_content: Callable[[str | None], bool] = (
            git_dir_may_be_content
        )
        # Whether git, run in a directory, may run a program the
        # repository's own configuration or hooks name: a git read takes the
        # worst case there, `git stash create` the worst case beside its
        # checkpoint, and a restore the worst case
        # (:func:`git_config_may_run`). A lookup that fails is a yes.
        self.git_config_may_run: Callable[[str | None], bool] = git_config_may_run
        # The same for a git command that changes the local repository or
        # work tree (`git reset`, `git checkout --`, `git branch -d`, `git
        # stash`), whose hooks are more (:func:`git_change_may_run`): it
        # takes the worst case there. A lookup that fails is a yes.
        self.git_change_may_run: Callable[[str | None], bool] = git_change_may_run
        # Whether git, writing files of the work tree in a directory, may
        # run a filter configured in any scope, the user's git-lfs included,
        # which asks the LFS server the repository names for an object it
        # lacks: a git change that writes the tree (`git reset`, `git
        # checkout --`, `git stash`) and a restore of a recorded checkpoint
        # take the worst case there (:func:`git_filter_may_run`). A lookup
        # that fails is a yes.
        self.git_filter_may_run: Callable[[str | None], bool] = git_filter_may_run
        # The PATH the classified commands run with (None: this process's)
        # and the project's directory (None: this process's working
        # directory). The adapter sets them from the options it wraps (the
        # CLI's ``env`` and ``cwd``). A command the allow-list would let pass
        # takes the worst case where its program may be the repository's own
        # (:func:`command_may_be_content`: a relative or empty PATH entry,
        # or one in the project, that holds a file of its name).
        self.command_path: str | None = None
        self.project_dir: str | None = None
        self.command_may_be_content: Callable[
            [str, str | None, str | None, str | None], bool
        ] = command_may_be_content
        # Whether an operating-system boundary holds for a Bash call now
        # (STANDARD 1.2.0 section 5.18.3, as RFC-0011 proposes it): Bash is
        # a shell-like tool, and its classifier relaxes a call below the
        # worst case only while this returns True. The adapter sets it from
        # the sandbox of the options it wraps (``wrap_options``). None, a
        # False, or a check that raises: every Bash call is its worst case.
        self.os_boundary: Callable[[], bool] | None = None

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
        names resolve within the set and among the bound tools registered
        before. A tool whose record does not load is unbound
        (:data:`UNCLASSIFIED_TOOL`).

        A composite's effective flags include those of the bindings it
        invokes (section 5.18.4), so every loaded composite that invokes,
        transitively, a tool of the set is loaded again from its record,
        with the set: it takes the flags they now have, and one that now
        invokes an unbound tool does not load (V107) and is unbound itself.
        Nothing is raised: every diagnostic, the composites' included, is
        returned and kept in :attr:`diagnostics` (warnings also in
        :attr:`warnings`).
        """
        own, dependents = self._load(records)
        return own + dependents

    def _load(
        self, records: Iterable[Mapping[str, Any]], *, again: bool = True
    ) -> tuple[list[ValidationError], list[ValidationError]]:
        """:meth:`load_bindings`: the set's diagnostics, and those of the
        composites loaded again (none when ``again`` is false)."""
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
        return diagnostics, (self._load_composites_again(names) if again else [])

    def _load_composites_again(self, changed: set[str]) -> list[ValidationError]:
        """Load again, as one set, every loaded composite that invokes a
        tool in ``changed``, transitively (section 5.18.4): what a layer
        loading the records it now holds would compute. Its diagnostics.
        ``invokes`` has no cycle among loaded bindings (V105 counts those
        loaded before), so the set is finite and loads once."""
        again: set[str] = set()
        reached = set(changed)
        while reached:
            reached = {
                name
                for name, mapping in self._dynamic_mappings.items()
                if name in self._records
                and name not in changed
                and name not in again
                and reached.intersection(mapping.invokes)
            }
            again |= reached
        if not again:
            return []
        diagnostics, _ = self._load(
            [self._records[name] for name in sorted(again)], again=False
        )
        return diagnostics

    def register_binding(self, record: Mapping[str, Any]) -> ToolMapping:
        """Load one tool binding record and return its effective mapping.

        Raises:
            ValueError: If the record does not load (S303, S304, V101, V105,
                V107, V109, V110). The message opens with each error's code
                and name; the tool stays unbound. A composite loaded again
                with it (:meth:`load_bindings`) raises nothing here: its
                diagnostics are in :attr:`diagnostics`.
        """
        diagnostics, _ = self._load([record])
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
            # A composite that invokes it no longer loads (V107).
            self._load_composites_again({tool_name})
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

    def map_tool(
        self, tool_name: str, tool_input: dict[str, Any], cwd: str | None = None
    ) -> ToolMapping:
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
            cwd: The directory the call runs in (a hook input's ``cwd``);
                None: this process's working directory. Only a git
                command's class depends on it (:attr:`git_may_fetch`,
                :attr:`git_dir_may_be_content`).

        Returns:
            ToolMapping with capability metadata, raised by the applied
            domain profiles (section 5.21.3)
        """
        return self._apply_profiles(self._map_tool(tool_name, tool_input, cwd))

    def _map_tool(
        self, tool_name: str, tool_input: dict[str, Any], cwd: str | None = None
    ) -> ToolMapping:
        """:meth:`map_tool` before domain profiles."""
        # Handle Bash specially - analyze command content. Input that is
        # not a dict has no command to read: classify it as an empty one,
        # which is fail-safe high risk.
        if tool_name == "Bash":
            if not isinstance(tool_input, dict):
                tool_input = {}
            if not self.boundary_holds(tool_input):
                return self._worst_case()
            return self._classify_bash_command(tool_input, cwd)

        # Check dynamic mappings (MCP tools, etc.)
        if tool_name in self._dynamic_mappings:
            return self._dynamic_mappings[tool_name]

        # A call that loads a definition whose commands no hook sees: its
        # own capability, and the worst case of what it may run.
        if tool_name in _UNSEEN_COMMANDS:
            return self._unseen(tool_name)

        # Static mapping for known tools
        if tool_name in _TOOL_MAPPINGS:
            return self._builtin(tool_name, _TOOL_MAPPINGS[tool_name])

        # Unknown tool: nothing says what it does, so assume the strictest
        # case instead of a read.
        return UNCLASSIFIED_TOOL

    def boundary_holds(self, tool_input: dict[str, Any]) -> bool:
        """Whether the Bash call with ``tool_input`` runs under a verified
        operating-system boundary (:attr:`os_boundary`), so that its
        classifier may relax it. Never for a call that asks to run outside
        the sandbox (``dangerouslyDisableSandbox`` set to anything but
        false): whether the host honours that argument is the host's
        configuration, which a call cannot settle (STANDARD 1.2.0 section
        5.18.3)."""
        if tool_input.get("dangerouslyDisableSandbox", False) is not False:
            return False
        check = self.os_boundary
        if check is None:
            return False
        try:
            return check() is True
        except Exception:
            logger.exception("Could not verify the operating-system boundary")
            return False

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

    def invoked_senders(self, mapping: ToolMapping) -> list[str]:
        """The tools ``mapping`` invokes, transitively, that may perform
        ``send`` (sections 4.4.2, 5.18.4), in the order found: each binding
        that performs it, and each tool that is unbound, which may send
        anywhere (section 5.18.2; a composite does not load with one, V107,
        so this is the fail-closed answer should one be reached). This
        mapper's layer does not see a composite's nested calls, so it cannot
        tell where they send."""
        found: list[str] = []
        seen: set[str] = set()
        queue = list(mapping.invokes)
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            invoked = self._dynamic_mappings.get(name, UNCLASSIFIED_TOOL)
            if invoked is UNCLASSIFIED_TOOL or "send" in invoked.capabilities:
                found.append(name)
            queue.extend(invoked.invokes)
        return found

    def _apply_profiles(self, mapping: ToolMapping) -> ToolMapping:
        """``mapping`` with the flags the applied profiles raise for each of
        its capabilities at its risk, and ``person_required`` when one of
        them requires a person (section 5.21.3). The core computes them, as
        it does for the executor. A control-only tool has no capability, and
        :data:`UNCLASSIFIED_TOOL` already needs a checkpoint and approval,
        so both stay as they are and keep their identity; whether a profile
        requires a person for an unbound tool is :meth:`person_required`'s
        answer.

        A composite also takes the raised flags and the person requirement
        of each binding it ``invokes``, transitively: those are effective
        flags (section 5.21.3), a composite's effective flags include those
        of every binding it lists (section 5.18.4), and its checkpoint and
        approval are the only gate on its nested calls, which this layer
        does not see. ``invokes`` has no cycle (V105 at load)."""
        if self._profiles is None or mapping.control or mapping is UNCLASSIFIED_TOOL:
            return mapping
        if self._profiled_revision != self.records_revision:
            # A binding registered again changes what the composites that
            # invoke it take from it: no cached mapping is current.
            self._profiled.clear()
            self._profiled_revision = self.records_revision
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
        for name in mapping.invokes:
            invoked = self._apply_profiles(
                self._dynamic_mappings.get(name, UNCLASSIFIED_TOOL)
            )
            checkpoint |= invoked.requires_checkpoint
            approval |= invoked.requires_approval
            person |= self.person_required(invoked)
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

    def _classify_bash_command(
        self, tool_input: dict[str, Any], cwd: str | None = None
    ) -> ToolMapping:
        """
        Classify a Bash command based on its content (STANDARD 1.2.0
        section 5.18.3).

        0. A command over 4096 UTF-8 bytes is not read: the worst case, before
           any pattern runs (some take time that grows faster than the line).
        1. Always-dangerous patterns (command substitution, backticks,
           variable expansion, eval, exec, source, control characters) and
           process substitution give the line the worst case at once
           (:meth:`_worst_case`: a gated `mutate` and `send`). So does a
           line `_simple_commands` cannot read, one with a parameter or
           brace expansion included.
        2. Only when the line is exactly one simple command with no option
           that writes (`_writes`), a `git stash <sub>` form is classified
           by `_GIT_STASH_CLASSES`: `create` takes a checkpoint, `list` and
           `show` observe, and `pop <commit>` and `apply <commit>` roll back
           when <commit> is the full id of a commit the layer recorded as a
           checkpoint (:attr:`is_checkpoint_commit`); any other `pop` or
           `apply` is a gated mutation, since git applies any merge commit
           as if it were a stash. Where the repository's own configuration
           or hooks name a program git runs (:attr:`git_config_may_run`),
           `create` takes a checkpoint beside the worst case (a host takes
           the first checkpoint with ``create_checkpoint``) and a restore
           takes the worst case; so does a restore where a smudge filter is
           configured in any scope (:attr:`git_filter_may_run`: git-lfs's
           asks the LFS server for an object the store lacks). Any other
           restore is the worst case where git may fetch or run what the
           repository names (`_git_change_gated`), or run such a filter. A
           git option before `stash` (`git -C dir stash ...`) is not
           recognised.
        3. Otherwise each simple command is classified on its own. A line
           whose every command is allow-listed as read-only is an
           observation; any other line takes the strictest flags and every
           prerequisite of all the commands that are not read-only, with
           their capabilities in order (`_combine`). A git command that would
           observe takes the worst case where git may fetch from another
           host (:attr:`git_may_fetch` for ``cwd``: a partial clone) or run
           a program the repository names (:attr:`git_dir_may_be_content`,
           :attr:`git_config_may_run`). `printf` with an option (`-v NAME`
           sets a shell variable the later commands of the line run with)
           is not read-only (`_writes`). A class narrower than the worst
           case comes only from the command's program, never from text in
           its arguments (:meth:`_classify_single_command`), and only where
           the program the shell finds for its name, on
           :attr:`command_path`, cannot be the repository's own
           (:func:`command_may_be_content`; the `git stash` forms of step 2
           alike).

        Security principle: fail-safe defaults. A command is high-risk until
        it is shown to be on the read-only allow-list, and a command the
        classifier does not recognise gets the worst case, `send` included
        (section 5.18.3), so that a destination policy refuses it rather
        than skip it.

        Args:
            tool_input: Bash tool input with 'command' key
            cwd: The directory the command runs in (None: this process's)

        Returns:
            ToolMapping based on command analysis
        """
        command = tool_input.get("command", "")
        worst = self._worst_case()

        # Empty, non-string or over-long command is suspicious - fail-safe.
        # The length is checked first: a pattern below can take time that
        # grows faster than the line.
        if (
            not isinstance(command, str)
            or len(command) > _MAX_COMMAND_BYTES
            or len(command.encode("utf-8", "surrogatepass")) > _MAX_COMMAND_BYTES
            or not command.strip()
        ):
            return worst

        # SEC-002: These bypass all other checks and are always high-risk.
        if _ALWAYS_DANGEROUS_PATTERNS.search(
            command
        ) or _PROCESS_SUBSTITUTION_PATTERNS.search(command):
            return worst

        commands = _simple_commands(command)
        if not commands:
            return worst

        if len(commands) == 1:
            words = commands[0].words
            if (
                len(words) >= 3
                and words[0] == "git"
                and words[1] == "stash"
                and words[2] in _GIT_STASH_CLASSES
                and not _writes(words, commands[0].globbed)
            ):
                # `git stash create` refreshes the index (core.fsmonitor)
                # and a restore writes the tree (filters): in a git
                # directory the repository ships, each runs what its
                # configuration names. And the git the shell finds may be
                # the repository's own.
                if self._git_dir_may_be_content(cwd) or self._program_may_be_content(
                    "git", cwd
                ):
                    return worst
                capability = _GIT_STASH_CLASSES[words[2]]
                if capability == "observe":
                    if self._git_read_gated(cwd):
                        return worst
                    return self._builtin("Bash", capability)
                if self._git_config_may_run(cwd):
                    # It runs what the repository's own configuration names,
                    # which may do anything, sending included: a checkpoint
                    # taken with the worst case beside it (a host takes the
                    # first with create_checkpoint), and a restore that is
                    # the worst case.
                    if capability == "checkpoint":
                        return self._combine(
                            [
                                self._builtin("Bash", "checkpoint"),
                                self._worst_case("execute"),
                            ]
                        )
                    return worst
                if capability == "checkpoint":
                    # It reads no object the local state lacks (a probe in a
                    # partial clone fetched nothing), and writes no file.
                    return self._builtin("Bash", capability)
                if self._restores_checkpoint(words):
                    # It writes the tree, through any smudge filter
                    # configured: git-lfs's asks the LFS server for each
                    # object of a pointer the store lacks.
                    if self._git_filter_may_run_in(cwd):
                        return worst
                    return self._builtin("Bash", capability)
                return self._git_change(cwd, writes_tree=True)

        results = [self._classify_single_command(c, cwd) for c in commands]
        gated = [r for r in results if r.risk != "low"]
        if not gated:
            return self._builtin("Bash", "observe")
        return self._combine(gated)

    def _program_may_be_content(self, name: str, cwd: str | None) -> bool:
        """:attr:`command_may_be_content` for the command name ``name`` run
        in ``cwd`` with :attr:`command_path` in :attr:`project_dir`; a
        lookup that fails is a yes."""
        try:
            return bool(
                self.command_may_be_content(
                    name, cwd, self.command_path, self.project_dir
                )
            )
        except Exception:
            logger.exception("Could not tell which program %s names", name)
            return True

    def _git_dir_may_be_content(self, cwd: str | None) -> bool:
        """:attr:`git_dir_may_be_content` for ``cwd``; a lookup that fails is
        a yes."""
        try:
            return bool(self.git_dir_may_be_content(cwd))
        except Exception:
            logger.exception("Could not tell which git directory serves %s", cwd)
            return True

    def _git_config_may_run(self, cwd: str | None) -> bool:
        """:attr:`git_config_may_run` for ``cwd``; a lookup that fails is a
        yes."""
        try:
            return bool(self.git_config_may_run(cwd))
        except Exception:
            logger.exception(
                "Could not tell whether git runs configured programs in %s", cwd
            )
            return True

    def _git_change_gated(self, cwd: str | None) -> bool:
        """Whether a git command that changes the local repository or work
        tree may do more in ``cwd``: what :meth:`_git_read_gated` asks, or
        run a hook git runs on such a change (:attr:`git_change_may_run`:
        `reference-transaction` on `git reset`, `git branch -d` and `git
        stash drop`, `post-checkout` on `git checkout --`). A lookup that
        fails is a yes."""
        if self._git_read_gated(cwd):
            return True
        try:
            return bool(self.git_change_may_run(cwd))
        except Exception:
            logger.exception("Could not tell which hooks git runs in %s", cwd)
            return True

    def _git_filter_may_run_in(self, cwd: str | None) -> bool:
        """:attr:`git_filter_may_run` for ``cwd``; a lookup that fails is a
        yes."""
        try:
            return bool(self.git_filter_may_run(cwd))
        except Exception:
            logger.exception("Could not tell which filters git runs in %s", cwd)
            return True

    def _git_change(self, cwd: str | None, writes_tree: bool) -> ToolMapping:
        """The class of a git command that changes the local repository or
        work tree: a gated `mutate`, or the worst case where git may fetch
        an object it lacks (`git reset` in a partial clone fetched the
        objects of the commit it moved to), run a program the repository
        names (:meth:`_git_change_gated`) or, for one that writes files of
        the work tree (``writes_tree``), run a smudge filter configured in
        any scope (:attr:`git_filter_may_run`: git-lfs's asked the LFS
        server for the objects of `git reset --hard`'s commit)."""
        if self._git_change_gated(cwd) or (
            writes_tree and self._git_filter_may_run_in(cwd)
        ):
            return self._worst_case()
        return self._builtin("Bash", "mutate", checkpoint_gated=True)

    def _git_read_gated(self, cwd: str | None) -> bool:
        """Whether a git command that only reads may do more in ``cwd``: run
        what repository content names (:attr:`git_dir_may_be_content`,
        :attr:`git_config_may_run`) or fetch from another host
        (:attr:`git_may_fetch`). A lookup that fails is a yes."""
        if self._git_dir_may_be_content(cwd) or self._git_config_may_run(cwd):
            return True
        try:
            return bool(self.git_may_fetch(cwd))
        except Exception:
            logger.exception("Could not tell whether git may fetch in %s", cwd)
            return True

    def _unseen(self, tool_name: str) -> ToolMapping:
        """A ``Skill``, ``Agent`` or ``Task`` call: its own capability
        (``invoke``, ``delegate``) and Bash's worst case (a gated ``mutate``
        and ``send``), since the commands the skill's file embeds or the
        subagent's definition names run with no hook seeing them (section
        5.18.3)."""
        return self._combine(
            [
                self._builtin(tool_name, _UNSEEN_COMMANDS[tool_name]),
                self._builtin(tool_name, "mutate", checkpoint_gated=True),
                self._builtin(tool_name, "send", checkpoint_gated=True),
            ]
        )

    def _restores_checkpoint(self, words: list[str]) -> bool:
        """Whether `git stash pop|apply <commit>` (``words``) names, as its
        only argument, the full id of a commit the layer recorded as a
        checkpoint. A lookup that fails is a no."""
        if len(words) != 4 or not _COMMIT_ID.fullmatch(words[3]):
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

    def _worst_case(self, capability: str = "mutate") -> ToolMapping:
        """Bash's worst case (section 5.18.3): a gated ``mutate`` and
        ``send``, for a command whose effect the classifier does not know,
        with ``capability`` first (`execute` for an interpreter, `send` for
        a program that sends). It may transmit anywhere, so a destination
        policy in force refuses it: this layer cannot tell where (section
        4.4.2)."""
        return self._combine(
            [
                self._builtin("Bash", capability, checkpoint_gated=True),
                self._builtin("Bash", "mutate", checkpoint_gated=True),
                self._builtin("Bash", "send", checkpoint_gated=True),
            ]
        )

    def _classify_single_command(
        self, command: _Command, cwd: str | None = None
    ) -> ToolMapping:
        """
        Classify one simple command.

        Checks in order: interpreter → network → remote mutation → local
        change → `git stash` → read-only allowlist → the worst case. Every
        class but the last two is the worst case with a capability first,
        or a gated `mutate`; only the command's program gives one narrower
        than the worst case (a gated `mutate` for `rm` and the local git
        changes, `observe` for the allow-list), never text in its
        arguments: `curl URL -A 'git reset'` is curl. An interpreter found
        anywhere in the words puts `execute` first, and takes nothing away.
        It never returns a `git stash` class: those need a line of one
        command (`_classify_bash_command`), so here every `git stash` form
        is a change of the local repository. A git command takes the worst
        case where git may fetch from another host (``cwd`` in a partial
        clone) or run a program the repository names.
        """
        words = command.words
        text = " ".join(words)
        # SEC-002: an interpreter runs code this classifier does not see,
        # which may transmit (python -c, node -e, a script).
        if _INTERPRETER_PATTERNS.search(text):
            return self._worst_case("execute")

        # A program that sends, from the start of the words.
        if _NETWORK_SEND_PATTERNS.match(text):
            return self._worst_case("send")

        # A change to a system the command names: it cannot tell which.
        if _REMOTE_MUTATION_PATTERNS.match(text):
            return self._worst_case()

        # A local change, by the program's own words.
        if len(words) > 1 and words[0] in _LOCAL_FILE_PROGRAMS:
            return self._builtin("Bash", "mutate", checkpoint_gated=True)
        if _local_git_change(words):
            return self._git_change(cwd, writes_tree=_writes_tree(words))

        if _is_read_only(command):
            if self._program_may_be_content(command.words[0], cwd):
                # The shell may run the repository's own program of that
                # name: what it does is unknown.
                return self._worst_case()
            if command.words[0] == "git" and self._git_read_gated(cwd):
                # A read of an object a partial clone lacks fetches it from
                # the promisor remote: a request to another host, carrying
                # the object id the command names.
                return self._worst_case()
            return self._builtin("Bash", "observe")

        # SECURE DEFAULT: a command not shown to be read-only is high-risk,
        # and its effect, a transmission included, is unknown.
        return self._worst_case()

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
