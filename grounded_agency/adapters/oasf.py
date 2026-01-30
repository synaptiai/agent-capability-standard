"""
OASF Adapter — Translates OASF skill invocations to Grounded Agency capabilities.

Enables systems using the Open Agentic Schema Framework (OASF) to invoke
Grounded Agency capabilities with full safety guarantees: evidence anchors,
checkpoint enforcement, and audit trails.

Usage:
    from grounded_agency.adapters import OASFAdapter

    adapter = OASFAdapter("schemas/interop/oasf_mapping.yaml")
    result = adapter.translate("109")  # Text Classification -> classify
    print(result.mapping.capabilities)  # ("classify",)
    print(result.mapping.domain_hint)   # "text"

OASF Reference: https://schema.oasf.outshift.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from ..capabilities.registry import CapabilityNode, CapabilityRegistry

logger = logging.getLogger("grounded_agency.adapters.oasf")


class UnknownSkillError(KeyError):
    """Raised when an OASF skill code has no mapping."""

    def __init__(self, skill_code: str) -> None:
        self.skill_code = skill_code
        super().__init__(
            f"Unknown OASF skill code: '{skill_code}'. "
            f"Check schemas/interop/oasf_mapping.yaml for valid codes."
        )


@dataclass(frozen=True, slots=True)
class OASFMapping:
    """A resolved mapping from an OASF skill code to Grounded Agency capabilities."""

    skill_code: str
    skill_name: str
    capabilities: tuple[str, ...]
    mapping_type: Literal["direct", "domain", "composition", "workflow"]
    domain_hint: str | None = None
    workflow: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class OASFSkillResult:
    """Result of translating an OASF skill invocation."""

    mapping: OASFMapping
    capability_nodes: list[CapabilityNode]
    requires_checkpoint: bool
    max_risk: str  # highest risk level among mapped capabilities
    evidence_anchors: list[dict[str, Any]] = field(default_factory=list)


class OASFAdapter:
    """
    Adapts OASF skill invocations to Grounded Agency capabilities.

    Loads the OASF-to-Grounded-Agency mapping file and provides translation
    between OASF skill codes and our 36 atomic capabilities, enriched with
    safety metadata from the capability registry.

    Args:
        mapping_path: Path to schemas/interop/oasf_mapping.yaml
        registry: Optional CapabilityRegistry instance. If not provided,
            defaults to loading from schemas/capability_ontology.yaml
            relative to the mapping file.
    """

    _RISK_ORDER = {"low": 0, "medium": 1, "high": 2}

    def __init__(
        self,
        mapping_path: str | Path,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self._mapping_path = Path(mapping_path)
        self._raw: dict[str, Any] | None = None
        self._index: dict[str, OASFMapping] | None = None
        self._computed_reverse: dict[str, list[str]] | None = None

        if registry is not None:
            self._registry = registry
        else:
            # Default: assume mapping is at schemas/interop/ relative to repo root
            ontology_path = (
                self._mapping_path.parent.parent / "capability_ontology.yaml"
            )
            self._registry = CapabilityRegistry(ontology_path)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._raw is not None:
            return

        if not self._mapping_path.exists():
            raise FileNotFoundError(f"OASF mapping not found: {self._mapping_path}")

        with open(self._mapping_path, encoding="utf-8") as f:
            self._raw = yaml.safe_load(f)

        self._build_index()

    def _build_index(self) -> None:
        """Build a flat lookup index from all categories and subcategories."""
        assert self._raw is not None
        self._index = {}
        categories: dict[str, Any] = self._raw.get("categories", {})

        for cat_code, cat_data in categories.items():
            # Index the category itself
            self._index_entry(cat_code, cat_data)
            # Index subcategories
            for sub_code, sub_data in cat_data.get("subcategories", {}).items():
                self._index_entry(str(sub_code), sub_data)

    def _index_entry(self, code: str, data: dict[str, Any]) -> None:
        """Index a single category or subcategory entry."""
        assert self._index is not None
        capabilities = data.get("capabilities", [])
        if not capabilities:
            logger.warning("OASF code '%s' has no mapped capabilities", code)
        self._index[str(code)] = OASFMapping(
            skill_code=str(code),
            skill_name=data.get("name", f"OASF-{code}"),
            capabilities=tuple(capabilities),
            mapping_type=data.get("mapping_type", "composition"),
            domain_hint=data.get("domain_hint"),
            workflow=data.get("workflow"),
            notes=data.get("notes"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def translate(self, skill_code: str) -> OASFSkillResult:
        """
        Translate an OASF skill code to Grounded Agency capabilities.

        Returns an OASFSkillResult with the mapped capabilities, their
        safety metadata, and the highest risk level.

        Args:
            skill_code: OASF skill code (e.g., "109", "801", "6")

        Returns:
            OASFSkillResult with mapping and safety information

        Raises:
            UnknownSkillError: If skill_code has no mapping
        """
        self._ensure_loaded()
        assert self._index is not None

        mapping = self._index.get(str(skill_code))
        if mapping is None:
            raise UnknownSkillError(str(skill_code))

        nodes: list[CapabilityNode] = []
        requires_checkpoint = False
        max_risk = "low"

        for cap_id in mapping.capabilities:
            node = self._registry.get_capability(cap_id)
            if node is not None:
                nodes.append(node)
                if node.requires_checkpoint:
                    requires_checkpoint = True
                if self._RISK_ORDER.get(node.risk, 0) > self._RISK_ORDER.get(
                    max_risk, 0
                ):
                    max_risk = node.risk
            else:
                logger.warning("Capability '%s' not found in registry", cap_id)

        logger.debug(
            "Translated OASF %s (%s) -> %s [risk=%s, checkpoint=%s]",
            skill_code,
            mapping.skill_name,
            mapping.capabilities,
            max_risk,
            requires_checkpoint,
        )

        return OASFSkillResult(
            mapping=mapping,
            capability_nodes=nodes,
            requires_checkpoint=requires_checkpoint,
            max_risk=max_risk,
        )

    def get_mapping(self, skill_code: str) -> OASFMapping | None:
        """
        Get the mapping for an OASF skill code without resolving capability nodes.

        Args:
            skill_code: OASF skill code

        Returns:
            OASFMapping or None if not found
        """
        self._ensure_loaded()
        assert self._index is not None
        return self._index.get(str(skill_code))

    def list_categories(self) -> list[OASFMapping]:
        """List all top-level OASF category mappings."""
        self._ensure_loaded()
        assert self._raw is not None
        assert self._index is not None
        return [
            self._index[str(code)]
            for code in self._raw.get("categories", {})
            if str(code) in self._index
        ]

    def list_all_mappings(self) -> list[OASFMapping]:
        """List all mappings (categories and subcategories).

        Returns mappings in YAML source order (categories first, then
        subcategories within each category). Order is deterministic on
        Python 3.7+.
        """
        self._ensure_loaded()
        assert self._index is not None
        return list(self._index.values())

    def _compute_reverse_mapping(self) -> dict[str, list[str]]:
        """
        Compute the reverse mapping programmatically from the forward mapping.

        Iterates over all indexed entries and inverts the mapping so that each
        capability ID maps to the list of OASF skill codes that reference it.

        The result is cached after the first computation.

        Returns:
            Dict mapping capability IDs to lists of OASF skill codes
        """
        if self._computed_reverse is not None:
            return self._computed_reverse
        assert self._index is not None
        reverse: dict[str, list[str]] = {}
        for code, mapping in self._index.items():
            for cap_id in mapping.capabilities:
                reverse.setdefault(cap_id, []).append(code)
        self._computed_reverse = reverse
        return reverse

    def reverse_lookup(self, capability_id: str) -> list[str]:
        """
        Find all OASF skill codes that map to a Grounded Agency capability.

        Always uses the computed reverse mapping derived from the forward
        mapping as the source of truth.

        Args:
            capability_id: Grounded Agency capability ID (e.g., "detect")

        Returns:
            List of OASF skill codes that include this capability
        """
        self._ensure_loaded()
        assert self._index is not None

        computed = self._compute_reverse_mapping()
        return list(computed.get(capability_id, []))

    @property
    def oasf_version(self) -> str:
        """OASF version this mapping was built for."""
        self._ensure_loaded()
        assert self._raw is not None
        meta: dict[str, Any] = self._raw.get("meta", {})
        return meta.get("oasf_version", "unknown")

    @property
    def mapping_version(self) -> str:
        """Version of this mapping file."""
        self._ensure_loaded()
        assert self._raw is not None
        meta: dict[str, Any] = self._raw.get("meta", {})
        return meta.get("version", "unknown")

    @property
    def category_count(self) -> int:
        """Number of top-level OASF categories mapped."""
        self._ensure_loaded()
        assert self._raw is not None
        return len(self._raw.get("categories", {}))

    @property
    def total_mapping_count(self) -> int:
        """Total number of mapped entries (categories + subcategories)."""
        self._ensure_loaded()
        assert self._index is not None
        return len(self._index)
