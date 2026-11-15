"""The Bash classifier's single-command `git stash` classes and compound
lines (STANDARD 1.2.0 section 5.18.3).

A `git stash` form is recognised only when the line is exactly one simple
command with no option that writes; a line of several commands takes the
strictest flags and every prerequisite of all of them. `git stash pop|apply`
restores a checkpoint (`rollback`) only as `... <commit>` with the full id of
a commit the layer recorded as a checkpoint: git applies any merge commit as
if it were a stash, so anything else is a gated mutation.
"""

from __future__ import annotations

from typing import Any

import pytest

from grounded_agency import GroundedAgentAdapter
from grounded_agency.capabilities.mapper import ToolCapabilityMapper, ToolMapping
from grounded_agency.capabilities.registry import CapabilityRegistry

# A commit a checkpoint recorded, and one it did not (a merge commit, say).
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "89abcdef0123456789abcdef0123456789abcdef"


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
        (f"git stash pop {SHA}", "rollback"),
        (f"git stash apply {SHA}", "rollback"),
    ],
)
def test_single_command_stash_classes(
    mapper: ToolCapabilityMapper, command: str, capability: str
) -> None:
    mapper.is_checkpoint_commit = {SHA}.__contains__
    mapping = _bash(mapper, command)
    assert mapping.capability_id == capability
    assert mapping.capabilities == (capability,)
    assert not mapping.requires_approval


def test_rollback_needs_a_checkpoint_taken_earlier(
    mapper: ToolCapabilityMapper,
) -> None:
    mapper.is_checkpoint_commit = {SHA}.__contains__
    mapping = _bash(mapper, f"git stash apply {SHA}")
    assert mapping.prerequisites == frozenset({"checkpoint"})
    assert not mapping.requires_checkpoint


@pytest.mark.parametrize(
    "command",
    [
        # refs/stash, which `git stash create` never writes
        "git stash pop",
        "git stash apply",
        "git stash apply stash@{0}",
        # a commit no checkpoint recorded: any merge commit applies
        f"git stash apply {OTHER}",
        f"git stash pop {OTHER}",
        # anything but the recorded commit's full id
        f"git stash apply {SHA[:12]}",
        f"git stash apply {SHA.upper()}",
        "git stash apply HEAD",
        "git stash apply main",
        f"git stash apply --index {SHA}",
        f"git stash apply {SHA} {SHA}",
    ],
)
def test_restoring_anything_but_a_recorded_checkpoint_is_gated(
    mapper: ToolCapabilityMapper, command: str
) -> None:
    mapper.is_checkpoint_commit = {SHA}.__contains__
    mapping = _bash(mapper, command)
    assert mapping.capabilities == ("mutate",), command
    assert _gated(mapping), command


def test_without_a_commit_lookup_a_restore_is_gated(
    mapper: ToolCapabilityMapper,
) -> None:
    assert mapper.is_checkpoint_commit is None
    assert _gated(_bash(mapper, f"git stash apply {SHA}"))


def test_a_failing_commit_lookup_is_gated(mapper: ToolCapabilityMapper) -> None:
    def broken(commit: str) -> bool:
        raise OSError("state unreadable")

    mapper.is_checkpoint_commit = broken
    assert _gated(_bash(mapper, f"git stash apply {SHA}"))


class TestAdapterRestore:
    """Through the adapter: the commit lookup is its checkpoint tracker's,
    within its scope."""

    @staticmethod
    async def _pre(adapter: GroundedAgentAdapter, command: str, call: str) -> Any:
        hook = adapter._make_pretooluse_safety_hook()
        return await hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": command},
                "tool_use_id": call,
                "permission_mode": "default",
            },
            call,
            None,
        )

    @pytest.mark.asyncio
    async def test_only_the_recorded_commit_restores_without_approval(
        self, asking_adapter: GroundedAgentAdapter
    ) -> None:
        asking_adapter.checkpoint_tracker.create_checkpoint(
            ["*"], "git stash create", metadata={"commit": SHA}
        )
        # Restoring the checkpoint: a rollback, no approval, nothing used.
        assert await self._pre(asking_adapter, f"git stash apply {SHA}", "r1") == {}
        assert asking_adapter.checkpoint_tracker.has_valid_checkpoint()
        # Applying another commit: a gated mutation, put to the person.
        other = await self._pre(asking_adapter, f"git stash apply {OTHER}", "r2")
        decision = other["hookSpecificOutput"]
        assert decision["permissionDecision"] == "ask"
        assert decision["permissionDecisionReason"].startswith("F502 ")

    @pytest.mark.asyncio
    async def test_a_commit_recorded_before_the_scope_began_is_gated(
        self, ontology_path: str, tmp_path: Any
    ) -> None:
        from grounded_agency import GroundedAgentConfig

        config = GroundedAgentConfig(
            ontology_path=ontology_path, checkpoint_dir=str(tmp_path / "c")
        )
        earlier = GroundedAgentAdapter(config)
        earlier.checkpoint_tracker.create_checkpoint(
            ["*"], "git stash create", metadata={"commit": SHA}
        )
        later = GroundedAgentAdapter(config)
        assert later.checkpoint_tracker.has_commit(SHA)
        assert later.mapper.map_tool(
            "Bash", {"command": f"git stash apply {SHA}"}
        ).capabilities == ("mutate",)


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
