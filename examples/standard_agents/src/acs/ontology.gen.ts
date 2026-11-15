// Generated from schemas/capability_ontology.yaml by
// scripts/gen_standard_agents_binding.py. DO NOT EDIT: regenerate with
//   python scripts/gen_standard_agents_binding.py

export const ONTOLOGY_VERSION = "2.2.0";

export const CAPABILITIES = {
  "retrieve": {"layer": "PERCEIVE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["data", "evidence_anchors", "confidence"]},
  "search": {"layer": "PERCEIVE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["results", "evidence_anchors", "confidence"]},
  "observe": {"layer": "PERCEIVE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["observation", "evidence_anchors", "confidence"]},
  "receive": {"layer": "PERCEIVE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["data", "evidence_anchors"]},
  "detect": {"layer": "UNDERSTAND", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["detected", "evidence_anchors", "confidence"]},
  "classify": {"layer": "UNDERSTAND", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["labels", "evidence_anchors", "confidence"]},
  "measure": {"layer": "UNDERSTAND", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["value", "uncertainty", "evidence_anchors", "confidence"]},
  "predict": {"layer": "UNDERSTAND", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["prediction", "probability", "evidence_anchors", "confidence"]},
  "compare": {"layer": "UNDERSTAND", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["ranking", "evidence_anchors", "confidence"]},
  "discover": {"layer": "UNDERSTAND", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["patterns", "evidence_anchors", "confidence"]},
  "plan": {"layer": "REASON", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["steps", "evidence_anchors", "confidence"]},
  "decompose": {"layer": "REASON", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["subproblems", "evidence_anchors", "confidence"]},
  "critique": {"layer": "REASON", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["issues", "evidence_anchors", "confidence"]},
  "explain": {"layer": "REASON", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["explanation", "evidence_anchors", "confidence"]},
  "state": {"layer": "MODEL", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["state", "evidence_anchors", "confidence"]},
  "transition": {"layer": "MODEL", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["rules", "evidence_anchors", "confidence"]},
  "attribute": {"layer": "MODEL", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["causes", "evidence_anchors", "confidence"]},
  "ground": {"layer": "MODEL", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["grounded", "evidence_anchors", "confidence"]},
  "simulate": {"layer": "MODEL", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["outcomes", "evidence_anchors", "confidence"]},
  "generate": {"layer": "SYNTHESIZE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["content", "evidence_anchors", "confidence"]},
  "transform": {"layer": "SYNTHESIZE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["output", "evidence_anchors", "confidence"]},
  "integrate": {"layer": "SYNTHESIZE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["merged", "evidence_anchors", "confidence"]},
  "execute": {"layer": "EXECUTE", "risk": "medium", "mutation": false, "requires_checkpoint": false, "requires_approval": true, "mutation_overridable": false, "output_required": ["result", "evidence_anchors"]},
  "mutate": {"layer": "EXECUTE", "risk": "high", "mutation": true, "requires_checkpoint": true, "requires_approval": true, "mutation_overridable": false, "output_required": ["success", "evidence_anchors"]},
  "send": {"layer": "EXECUTE", "risk": "high", "mutation": true, "requires_checkpoint": true, "requires_approval": true, "mutation_overridable": false, "output_required": ["sent", "evidence_anchors"]},
  "verify": {"layer": "VERIFY", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["passed", "evidence_anchors", "confidence"]},
  "checkpoint": {"layer": "VERIFY", "risk": "low", "mutation": true, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["checkpoint_id", "evidence_anchors"]},
  "rollback": {"layer": "VERIFY", "risk": "medium", "mutation": true, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["restored", "evidence_anchors"]},
  "constrain": {"layer": "VERIFY", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["compliant", "evidence_anchors"]},
  "audit": {"layer": "VERIFY", "risk": "low", "mutation": true, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": true, "output_required": ["recorded", "evidence_anchors"]},
  "persist": {"layer": "REMEMBER", "risk": "low", "mutation": true, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["stored", "evidence_anchors"]},
  "recall": {"layer": "REMEMBER", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["data", "evidence_anchors"]},
  "delegate": {"layer": "COORDINATE", "risk": "medium", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["accepted", "evidence_anchors"]},
  "synchronize": {"layer": "COORDINATE", "risk": "medium", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["synchronized", "evidence_anchors"]},
  "invoke": {"layer": "COORDINATE", "risk": "medium", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["result", "evidence_anchors"]},
  "inquire": {"layer": "COORDINATE", "risk": "low", "mutation": false, "requires_checkpoint": false, "requires_approval": false, "mutation_overridable": false, "output_required": ["questions", "ambiguity_analysis", "evidence_anchors", "confidence"]},
} as const;

/** `requires` edges as [from, to]: `from` must have run before `to`. */
export const REQUIRES = [
  ["checkpoint", "mutate"],
  ["checkpoint", "send"],
  ["checkpoint", "rollback"],
] as const;
