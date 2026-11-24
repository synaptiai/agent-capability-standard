"""The words whose brace expansion bash 5.2 and bash 5.3 read differently.

Bash 5.2 reads a group as a list when a comma is anywhere in it, nested
included, and keeps a group that is neither a list nor a sequence as
written; bash 5.3 reads a group as a list only when a comma is at its own
level, and of a group that is neither keeps the `{` as written and expands
what follows it. So `{a..b{c,d}}` is `a..bc a..bd` to bash 5.2 and
`{a..bc} {a..bd}` to bash 5.3 (GitHub's ubuntu-latest runner, November
2026). The hooks run under whichever bash the user has, so their readers
(the records guard's brace_words, the send and audit skills' jq) give both
versions' words. The 5.3 words here are that reading of the runner's
evidence: bash 5.3's source was not at hand.

Only letter sequences: the skills' jq writes a number sequence's elements
as one placeholder character.
"""

from __future__ import annotations

BY_VERSION: dict[str, tuple[list[str], list[str]]] = {
    "{a..b{c,d}}": (["a..bc", "a..bd"], ["{a..bc}", "{a..bd}"]),
    "p{a..b{c,d}}q": (["pa..bcq", "pa..bdq"], ["p{a..bc}q", "p{a..bd}q"]),
    "{a..b{c,d}}z{e,f}": (
        ["a..bcze", "a..bczf", "a..bdze", "a..bdzf"],
        ["{a..bc}ze", "{a..bc}zf", "{a..bd}ze", "{a..bd}zf"],
    ),
    "{ab..c{d,e}}": (["ab..cd", "ab..ce"], ["{ab..cd}", "{ab..ce}"]),
    "{x..y{a..b}}": (["{x..y{a..b}}"], ["{x..ya}", "{x..yb}"]),
    "{x..y{a..b}}/key": (["{x..y{a..b}}/key"], ["{x..ya}/key", "{x..yb}/key"]),
    "{x..y{c,d}}/key": (["x..yc/key", "x..yd/key"], ["{x..yc}/key", "{x..yd}/key"]),
}


def assert_reading(word: str, ours: list[str], installed: list[str]) -> None:
    """``ours`` (sorted, empty words left out) is the hooks' reading of
    ``word``: the installed bash's words exactly, or, for a word the two
    versions read differently, both versions' words, each once, which
    holds the installed bash's (one version's, as the table has it)."""
    if word not in BY_VERSION:
        assert ours == installed, word
        return
    v52, v53 = BY_VERSION[word]
    assert installed in (sorted(v52), sorted(v53)), (word, installed)
    assert ours == sorted(set(v52) | set(v53)), word
    assert set(installed) <= set(ours), word
