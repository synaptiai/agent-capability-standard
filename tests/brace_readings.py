"""The words whose brace expansion bash versions read differently.

Bash 5.2 reads a group as a list when a comma is anywhere in it, nested
included, and keeps a group that is neither a list nor a sequence as
written. Bash 5.3 reads a group as a list only when a comma is at its own
level: `{a..b{c,d}}` is `a..bc a..bd` to bash 5.2 and `{a..bc} {a..bd}` to
bash 5.3 (GitHub's ubuntu-latest runner, November 2026), the one word of
bash 5.3's seen. Bash 5.3's source was not at hand, and two readings of a
group that is neither give that word:

- ``5.3a``: the `{` kept as written, and all that follows it expanded, the
  rest of the word included;
- ``5.3c``: the group's two braces kept around the words of its own text,
  then the text after the group expanded.

The hooks run under whichever bash the user has, so their readers (the
records guard's brace_words, the send and audit skills' jq) give the words
of all three readings. The table gives each reading's words of a word the
readings make differently, words that tell the readings apart included, so
a runner's bash shows which reading is its own
(``installed_readings``), or that none is.

Only letter sequences: the skills' jq writes a number sequence's elements
as one placeholder character.
"""

from __future__ import annotations

READINGS = ("5.2", "5.3a", "5.3c")

# word: (bash 5.2's words, reading 5.3a's, reading 5.3c's), each sorted.
BY_VERSION: dict[str, tuple[list[str], list[str], list[str]]] = {
    "{a..b{c,d}}": (
        ["a..bc", "a..bd"],
        ["{a..bc}", "{a..bd}"],
        ["{a..bc}", "{a..bd}"],
    ),
    "p{a..b{c,d}}q": (
        ["pa..bcq", "pa..bdq"],
        ["p{a..bc}q", "p{a..bd}q"],
        ["p{a..bc}q", "p{a..bd}q"],
    ),
    "{a..b{c,d}}z{e,f}": (
        ["a..bcze", "a..bczf", "a..bdze", "a..bdzf"],
        ["{a..bc}ze", "{a..bc}zf", "{a..bd}ze", "{a..bd}zf"],
        ["{a..bc}ze", "{a..bc}zf", "{a..bd}ze", "{a..bd}zf"],
    ),
    "{ab..c{d,e}}": (
        ["ab..cd", "ab..ce"],
        ["{ab..cd}", "{ab..ce}"],
        ["{ab..cd}", "{ab..ce}"],
    ),
    "{x..y{a..b}}": (
        ["{x..y{a..b}}"],
        ["{x..ya}", "{x..yb}"],
        ["{x..ya}", "{x..yb}"],
    ),
    "{x..y{a..b}}/key": (
        ["{x..y{a..b}}/key"],
        ["{x..ya}/key", "{x..yb}/key"],
        ["{x..ya}/key", "{x..yb}/key"],
    ),
    "{x..y{c,d}}/key": (
        ["x..yc/key", "x..yd/key"],
        ["{x..yc}/key", "{x..yd}/key"],
        ["{x..yc}/key", "{x..yd}/key"],
    ),
    # Words that tell bash 5.3's two readings apart: 5.3a closes a group at
    # a } past the first group's own close.
    "{a..b{c}},d}": (
        ["{a..b{c}},d}"],
        ["{a..bc}}", "{a..bd"],
        ["{a..b{c}},d}"],
    ),
    "{a..b{c}},d}/key": (
        ["{a..b{c}},d}/key"],
        ["{a..bc}}/key", "{a..bd/key"],
        ["{a..b{c}},d}/key"],
    ),
    "{..{}},}": (
        ["{..{}},}"],
        ["{..", "{..}}"],
        ["{..{}},}"],
    ),
    "{{,}..{}},}": (
        ["..{},}", "..{},}"],
        ["{..", "{..", "{..}}", "{..}}"],
        ["{..{}},}", "{..{}},}"],
    ),
    "{{..c}..{}{{b..b}}},}/key": (
        ["{{..c}..{}{{b..b}}},}/key"],
        ["{{..c}../key", "{{..c}..}{b}}/key"],
        ["{{..c}..{}{b}},}/key"],
    ),
}


def assert_reading(word: str, ours: list[str], installed: list[str]) -> None:
    """``ours`` (sorted, empty words left out) is the hooks' reading of
    ``word``: the installed bash's words exactly, or, for a word the
    readings make differently, the words of all three (each at least once),
    which hold the installed bash's (one reading's, as the table has it)."""
    if word not in BY_VERSION:
        assert ours == installed, word
        return
    readings = BY_VERSION[word]
    assert installed in readings, (word, installed)
    assert set(ours) == set().union(*readings), word
    assert set(installed) <= set(ours), word


def installed_readings(installed: dict[str, list[str]]) -> list[str]:
    """The readings that give, of every word in the table, the words the
    installed bash gives (``installed``: each word's, sorted, the empty
    ones left out)."""
    return [
        name
        for k, name in enumerate(READINGS)
        if all(installed[w] == BY_VERSION[w][k] for w in BY_VERSION)
    ]
