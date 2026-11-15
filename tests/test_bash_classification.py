"""The Bash classifier's single-command `git stash` classes and compound
lines (STANDARD 1.2.0 section 5.18.3).

A `git stash` form is recognised only when the line is exactly one simple
command with no option that writes; a line of several commands takes the
strictest flags and every prerequisite of all of them.
"""

from __future__ import annotations

import pytest

from grounded_agency.capabilities.mapper import ToolCapabilityMapper, ToolMapping
from grounded_agency.capabilities.registry import CapabilityRegistry


@pytest.fixture
def mapper(ontology_path: str) -> ToolCapabilityMapper:
    return ToolCapabilityMapper(CapabilityRegistry(ontology_path))


def _bash(mapper: ToolCapabilityMapper, command: str) -> ToolMapping:
    return mapper.map_tool("Bash", {"command": command})


def _gated(mapping: ToolMapping) -> bool:
    return (
        mapping.risk == "high"
        and mapping.mutation
        and mapping.requires_checkpoint
        and mapping.requires_approval
    )


@pytest.mark.parametrize(
    ("command", "capability"),
    [
        ("git stash create", "checkpoint"),
        ('git stash create "checkpoint:x"', "checkpoint"),
        ("git stash list", "observe"),
        ("git stash show -p", "observe"),
        ("git stash pop", "rollback"),
        ("git stash apply 0123456789abcdef0123456789abcdef01234567", "rollback"),
    ],
)
def test_single_command_stash_classes(
    mapper: ToolCapabilityMapper, command: str, capability: str
) -> None:
    mapping = _bash(mapper, command)
    assert mapping.capability_id == capability
    assert mapping.capabilities == (capability,)
    assert not mapping.requires_approval


def test_rollback_needs_a_checkpoint_taken_earlier(
    mapper: ToolCapabilityMapper,
) -> None:
    mapping = _bash(mapper, "git stash pop")
    assert mapping.prerequisites == frozenset({"checkpoint"})
    assert not mapping.requires_checkpoint


@pytest.mark.parametrize(
    "command",
    [
        "git stash store -m m 0123456789abcdef0123456789abcdef01234567",
        "git stash",
        "git stash push",
        "git stash save x",
        "git stash drop",
        "git stash clear",
        # An option that writes, on any git form
        "git stash show --output=f",
        "git stash list --output=f",
        # A git option before `stash` is not recognised
        "git -C d stash list",
        # The stash classes need a line of one command
        "ls && git stash list",
        "file -bC x",
        "file -C x",
    ],
)
def test_other_forms_are_gated_mutations(
    mapper: ToolCapabilityMapper, command: str
) -> None:
    mapping = _bash(mapper, command)
    assert mapping.capabilities == ("mutate",), command
    assert _gated(mapping), command


def test_a_rollback_in_a_compound_line_is_not_a_rollback(
    mapper: ToolCapabilityMapper,
) -> None:
    mapping = _bash(mapper, "git stash pop && rm -rf x")
    assert mapping.capabilities == ("mutate",)
    assert _gated(mapping)


def test_a_compound_line_takes_every_capability_and_the_strictest_flags(
    mapper: ToolCapabilityMapper,
) -> None:
    mapping = _bash(mapper, "curl -X POST u -d x; rm f")
    assert mapping.capabilities == ("send", "mutate")
    assert mapping.capability_id == "send"
    assert _gated(mapping)
    assert mapping.prerequisites == frozenset({"checkpoint"})


@pytest.mark.parametrize(
    "command", ["git rev-parse HEAD", "git ls-files", "ls && git status"]
)
def test_read_only_lines_observe(mapper: ToolCapabilityMapper, command: str) -> None:
    assert _bash(mapper, command).capabilities == ("observe",)
