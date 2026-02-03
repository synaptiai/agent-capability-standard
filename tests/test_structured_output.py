"""
Tests for structured output and budget enforcement in GroundedAgentConfig.

Tests that output_format, max_budget_usd, model, and max_turns are
properly injected into SDK options via wrap_options().
"""

from __future__ import annotations

from pathlib import Path

import pytest

claude_agent_sdk = pytest.importorskip("claude_agent_sdk")
ClaudeAgentOptions = claude_agent_sdk.ClaudeAgentOptions

from grounded_agency import GroundedAgentAdapter, GroundedAgentConfig  # noqa: E402

# =============================================================================
# Config Tests
# =============================================================================


class TestGroundedAgentConfigNewFields:
    """Tests for new config fields."""

    def test_default_config_has_none_values(self, ontology_path: str):
        """Test that new fields default to None."""
        config = GroundedAgentConfig(ontology_path=ontology_path)
        assert config.output_format is None
        assert config.max_budget_usd is None
        assert config.model is None
        assert config.max_turns is None

    def test_config_with_output_format(self, ontology_path: str):
        """Test config with output_format set."""
        schema = {"type": "object", "properties": {"result": {"type": "string"}}}
        config = GroundedAgentConfig(
            ontology_path=ontology_path,
            output_format=schema,
        )
        assert config.output_format == schema

    def test_config_with_budget(self, ontology_path: str):
        """Test config with budget constraints."""
        config = GroundedAgentConfig(
            ontology_path=ontology_path,
            max_budget_usd=5.0,
            model="sonnet",
            max_turns=20,
        )
        assert config.max_budget_usd == 5.0
        assert config.model == "sonnet"
        assert config.max_turns == 20


# =============================================================================
# wrap_options Injection Tests
# =============================================================================


class TestWrapOptionsInjection:
    """Tests that wrap_options injects new config fields into SDK options."""

    def test_inject_output_format(self, ontology_path: str, tmp_path: Path):
        """Test that output_format is injected into options."""
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                output_format=schema,
            )
        )
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)

        assert wrapped.output_format == schema

    def test_inject_max_budget(self, ontology_path: str, tmp_path: Path):
        """Test that max_budget_usd is injected into options."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                max_budget_usd=2.50,
            )
        )
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)

        assert wrapped.max_budget_usd == 2.50

    def test_inject_model(self, ontology_path: str, tmp_path: Path):
        """Test that model is injected into options."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                model="opus",
            )
        )
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)

        assert wrapped.model == "opus"

    def test_inject_max_turns(self, ontology_path: str, tmp_path: Path):
        """Test that max_turns is injected into options."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                max_turns=15,
            )
        )
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)

        assert wrapped.max_turns == 15

    def test_no_override_existing_output_format(
        self, ontology_path: str, tmp_path: Path
    ):
        """Test that existing output_format is not overridden."""
        existing_schema = {"type": "string"}
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                output_format={"type": "integer"},
            )
        )
        base = ClaudeAgentOptions(output_format=existing_schema)
        wrapped = adapter.wrap_options(base)

        # Should keep the existing one, not override
        assert wrapped.output_format == existing_schema

    def test_no_override_existing_budget(self, ontology_path: str, tmp_path: Path):
        """Test that existing max_budget_usd is not overridden."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                max_budget_usd=10.0,
            )
        )
        base = ClaudeAgentOptions(max_budget_usd=5.0)
        wrapped = adapter.wrap_options(base)

        assert wrapped.max_budget_usd == 5.0

    def test_no_injection_when_none(self, ontology_path: str, tmp_path: Path):
        """Test that None config values are not injected."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
            )
        )
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)

        assert wrapped.output_format is None
        assert wrapped.max_budget_usd is None
        assert wrapped.model is None
        assert wrapped.max_turns is None

    def test_inject_all_fields(self, ontology_path: str, tmp_path: Path):
        """Test injecting all new fields at once."""
        adapter = GroundedAgentAdapter(
            GroundedAgentConfig(
                ontology_path=ontology_path,
                checkpoint_dir=str(tmp_path / ".checkpoints"),
                output_format={"type": "object"},
                max_budget_usd=3.0,
                model="haiku",
                max_turns=10,
            )
        )
        base = ClaudeAgentOptions()
        wrapped = adapter.wrap_options(base)

        assert wrapped.output_format == {"type": "object"}
        assert wrapped.max_budget_usd == 3.0
        assert wrapped.model == "haiku"
        assert wrapped.max_turns == 10
