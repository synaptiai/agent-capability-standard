"""V102 as a safety layer's refusal of a call (STANDARD 1.2.0 sections
5.18.5 and 9.1): a prerequisite other than a checkpoint that has not run in
the scope. Ontology 2.x has only `checkpoint` requires-edges, so the rule is
tested with a test ontology that adds `observe -> generate`."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig


@pytest.fixture
def adapter(ontology_path: str, tmp_path: Path) -> GroundedAgentAdapter:
    ontology = yaml.safe_load(Path(ontology_path).read_text(encoding="utf-8"))
    ontology["edges"].append({"from": "observe", "to": "generate", "type": "requires"})
    path = tmp_path / "capability_ontology.yaml"
    path.write_text(yaml.safe_dump(ontology, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".yaml.sha256").write_text(f"{digest}  {path.name}\n")
    adapter = GroundedAgentAdapter(
        GroundedAgentConfig(
            ontology_path=str(path),
            # The copy's contract $refs are relative to the repository.
            schema_root=str(Path(ontology_path).parent.parent),
            checkpoint_dir=str(tmp_path / ".cp"),
            approval="off",
        )
    )
    adapter.mapper.register_mcp_tool("mcp__s__write_text", capability_id="generate")
    adapter.mapper.register_mcp_tool("mcp__s__look", capability_id="observe")
    return adapter


@pytest.mark.asyncio
async def test_a_missing_prerequisite_is_v102_until_it_runs(
    adapter: GroundedAgentAdapter,
) -> None:
    assert adapter.mapper.map_tool("mcp__s__write_text", {}).prerequisites == {
        "observe"
    }
    pre = adapter._make_pretooluse_safety_hook()
    post = adapter._make_mutation_consumer()

    refused = await pre(
        {"tool_name": "mcp__s__write_text", "tool_input": {}}, "g1", None
    )
    reason = refused["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason.startswith("V102 MISSING_PREREQUISITE:")
    diagnostic = adapter.diagnostics[-1]
    assert diagnostic.location == {
        "tool": "mcp__s__write_text",
        "capability": "generate",
        "call": "g1",
    }

    assert await pre({"tool_name": "mcp__s__look", "tool_input": {}}, "o1", None) == {}
    await post(
        {"tool_name": "mcp__s__look", "tool_input": {}, "tool_response": {}}, "o1", None
    )

    assert (
        await pre({"tool_name": "mcp__s__write_text", "tool_input": {}}, "g2", None)
        == {}
    )


@pytest.mark.asyncio
async def test_a_failed_call_does_not_count(adapter: GroundedAgentAdapter) -> None:
    pre = adapter._make_pretooluse_safety_hook()
    post = adapter._make_mutation_consumer()
    await post(
        {
            "tool_name": "mcp__s__look",
            "tool_input": {},
            "tool_response": {"is_error": True},
        },
        "o1",
        None,
    )
    refused = await pre(
        {"tool_name": "mcp__s__write_text", "tool_input": {}}, "g1", None
    )
    assert refused["hookSpecificOutput"]["permissionDecisionReason"].startswith("V102 ")
