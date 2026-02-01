#!/usr/bin/env python3
"""CLI scaffolder for capabilities, workflows, and domain profiles.

Usage:
    python tools/scaffold.py capability <name> --layer <LAYER> [--risk <RISK>] [--mutation] [--dry-run]
    python tools/scaffold.py workflow <name> [--dry-run]
    python tools/scaffold.py profile <name> [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Ensure tools/ is importable so we can use yaml_util.safe_yaml_load
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from yaml_util import safe_yaml_load  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

LAYERS = [
    "PERCEIVE",
    "UNDERSTAND",
    "REASON",
    "MODEL",
    "SYNTHESIZE",
    "EXECUTE",
    "VERIFY",
    "REMEMBER",
    "COORDINATE",
]

RISK_LEVELS = ["low", "medium", "high"]

NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
NAME_MIN = 2
NAME_MAX = 40

# ANSI colour helpers
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_name(name: str) -> str | None:
    """Return an error message if *name* is invalid, else None."""
    if len(name) < NAME_MIN:
        return f"Name must be at least {NAME_MIN} characters (got {len(name)})"
    if len(name) > NAME_MAX:
        return f"Name must be at most {NAME_MAX} characters (got {len(name)})"
    if not NAME_RE.match(name):
        return (
            "Name must be kebab-case (lowercase a-z, digits, hyphens; "
            "must start and end with alphanumeric)"
        )
    return None


def _die(msg: str) -> None:
    print(f"{RED}Error: {msg}{RESET}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: capability
# ---------------------------------------------------------------------------

def scaffold_capability(args: argparse.Namespace) -> None:
    """Scaffold a new capability in the ontology and create a skill stub."""
    name: str = args.name
    layer: str = args.layer
    risk: str = args.risk
    mutation: bool = args.mutation
    dry_run: bool = args.dry_run

    # --- validate ---
    err = validate_name(name)
    if err:
        _die(err)
    if layer not in LAYERS:
        _die(f"Invalid layer '{layer}'. Must be one of: {', '.join(LAYERS)}")
    if risk not in RISK_LEVELS:
        _die(f"Invalid risk '{risk}'. Must be one of: {', '.join(RISK_LEVELS)}")

    # --- load ontology ---
    ontology_path = REPO_ROOT / "schemas" / "capability_ontology.yaml"
    ontology = safe_yaml_load(ontology_path)

    existing_ids = {n["id"] for n in ontology.get("nodes", [])}
    if name in existing_ids:
        _die(f"Capability '{name}' already exists in the ontology")

    # --- build new node ---
    new_node = {
        "id": name,
        "layer": layer,
        "description": "Placeholder -- update with specific description",
        "risk": risk,
        "mutation": mutation,
        "requires_checkpoint": mutation,
        "input_schema": {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Primary input",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["result", "evidence_anchors", "confidence"],
            "properties": {
                "result": {
                    "type": "any",
                    "description": "Primary output",
                },
                "evidence_anchors": {
                    "type": "array",
                    "description": "Source references",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
            },
        },
    }

    # --- build skill content ---
    template_path = REPO_ROOT / "templates" / "SKILL_TEMPLATE_ENHANCED.md"
    skill_dir = REPO_ROOT / "skills" / name
    skill_path = skill_dir / "SKILL.md"

    if mutation or risk == "high":
        agent = "general-purpose"
        allowed_tools = "Read, Grep, Edit, Bash"
    elif risk == "medium":
        agent = "general-purpose"
        allowed_tools = "Read, Grep"
    else:
        agent = "explore"
        allowed_tools = "Read, Grep"

    # Read template and fill placeholders
    template_text = template_path.read_text(encoding="utf-8")
    # Extract just the markdown between the triple-backtick fences
    fence_start = template_text.find("```markdown")
    fence_end = template_text.find("```\n\n---", fence_start)
    if fence_start != -1 and fence_end != -1:
        skill_content = template_text[fence_start + len("```markdown\n"):fence_end]
    else:
        # Fallback: use the whole template
        skill_content = template_text

    # Replace template placeholders
    skill_content = skill_content.replace("<capability-name>", name)
    skill_content = skill_content.replace(
        "<verb phrase describing what this capability does>",
        "TODO: Add description",
    )
    skill_content = skill_content.replace(
        "<explore|general-purpose>", agent
    )
    skill_content = skill_content.replace(
        "<comma-separated list from ontology default_tools>", allowed_tools
    )
    # Safety constraints
    skill_content = skill_content.replace(
        "`mutation`: <true|false from ontology>",
        f"`mutation`: {str(mutation).lower()}",
    )
    skill_content = skill_content.replace(
        "`requires_checkpoint`: <true|false from ontology>",
        f"`requires_checkpoint`: {str(mutation).lower()}",
    )
    skill_content = skill_content.replace(
        "`requires_approval`: <true|false from ontology>",
        f"`requires_approval`: {str(risk in ('medium', 'high')).lower()}",
    )
    skill_content = skill_content.replace(
        "`risk`: <low|medium|high from ontology>",
        f"`risk`: {risk}",
    )

    # --- dry-run reporting ---
    if dry_run:
        print(f"{YELLOW}[DRY-RUN] Would add capability node '{name}' to ontology{RESET}")
        print(f"{YELLOW}[DRY-RUN]   layer: {layer}, risk: {risk}, mutation: {mutation}{RESET}")
        print(f"{YELLOW}[DRY-RUN] Would append '{name}' to layers.{layer}.capabilities{RESET}")
        print(f"{YELLOW}[DRY-RUN] Would write ontology back to {ontology_path}{RESET}")
        print(f"{YELLOW}[DRY-RUN] Would create skill directory {skill_dir}/{RESET}")
        print(f"{YELLOW}[DRY-RUN] Would create skill file {skill_path}{RESET}")
        return

    # --- apply changes ---
    ontology["nodes"].append(new_node)

    # Add to layer capabilities list
    layer_caps = ontology["layers"][layer].get("capabilities", [])
    layer_caps.append(name)
    ontology["layers"][layer]["capabilities"] = layer_caps

    # Write ontology
    with open(ontology_path, "w", encoding="utf-8") as f:
        yaml.dump(ontology, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Create skill directory and file
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill_content, encoding="utf-8")

    print(f"{GREEN}Created capability '{name}':{RESET}")
    print(f"{GREEN}  - Added node to {ontology_path}{RESET}")
    print(f"{GREEN}  - Added to layers.{layer}.capabilities{RESET}")
    print(f"{GREEN}  - Created {skill_path}{RESET}")


# ---------------------------------------------------------------------------
# Subcommand: workflow
# ---------------------------------------------------------------------------

def scaffold_workflow(args: argparse.Namespace) -> None:
    """Scaffold a new workflow stub in the catalog."""
    name: str = args.name
    dry_run: bool = args.dry_run

    err = validate_name(name)
    if err:
        _die(err)

    catalog_path = REPO_ROOT / "schemas" / "workflow_catalog.yaml"
    catalog = safe_yaml_load(catalog_path)

    # The catalog is a dict of workflow_name -> workflow_def
    if catalog is None:
        catalog = {}

    # Convert hyphens to underscores for the YAML key (matching existing convention)
    key = name.replace("-", "_")
    if key in catalog:
        _die(f"Workflow '{name}' (key '{key}') already exists in the catalog")

    stub = {
        "goal": "TODO: Define workflow goal",
        "risk": "low",
        "steps": [
            {
                "capability": "retrieve",
                "purpose": "TODO: Define first step purpose",
                "risk": "low",
                "mutation": False,
                "requires_checkpoint": False,
                "requires_approval": False,
                "store_as": "step_1_result",
                "failure_modes": [
                    {
                        "type": "retrieval_failure",
                        "recovery": "retry",
                    },
                ],
            },
        ],
        "success": {
            "condition": "TODO: Define success condition",
            "evidence": "TODO: Define required evidence",
        },
    }

    if dry_run:
        print(f"{YELLOW}[DRY-RUN] Would add workflow '{key}' to {catalog_path}{RESET}")
        print(f"{YELLOW}[DRY-RUN]   goal: TODO: Define workflow goal{RESET}")
        print(f"{YELLOW}[DRY-RUN]   risk: low{RESET}")
        print(f"{YELLOW}[DRY-RUN]   steps: 1 (retrieve){RESET}")
        return

    catalog[key] = stub

    with open(catalog_path, "w", encoding="utf-8") as f:
        yaml.dump(catalog, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"{GREEN}Created workflow '{key}':{RESET}")
    print(f"{GREEN}  - Added to {catalog_path}{RESET}")


# ---------------------------------------------------------------------------
# Subcommand: profile
# ---------------------------------------------------------------------------

def scaffold_profile(args: argparse.Namespace) -> None:
    """Scaffold a new domain profile YAML file."""
    name: str = args.name
    dry_run: bool = args.dry_run

    err = validate_name(name)
    if err:
        _die(err)

    profile_path = REPO_ROOT / "schemas" / "profiles" / f"{name}.yaml"

    if profile_path.exists():
        _die(f"Profile '{name}' already exists at {profile_path}")

    # Title-case for comment header
    title = name.replace("-", " ").title()

    content = f"""\
# {title} Domain Profile
# TODO: Add description of this domain profile

domain: {name}
version: "1.0.0"
description: |
  TODO: Describe the {name} domain profile.

trust_weights:
  primary_source: 0.90
  secondary_source: 0.75
  external_source: 0.60

risk_thresholds:
  auto_approve: low
  require_review: medium
  require_human: high
  block_autonomous:
    - mutate
    - send

checkpoint_policy:
  before_mutation: always
  before_send: always
  before_modification: high_risk

evidence_policy:
  required_anchor_types:
    - file
    - tool_output
  minimum_confidence: 0.7
  require_grounding:
    - generate
    - predict
    - explain

trust_model_reviewed: false
"""

    if dry_run:
        print(f"{YELLOW}[DRY-RUN] Would create profile at {profile_path}{RESET}")
        print(f"{YELLOW}[DRY-RUN]   domain: {name}{RESET}")
        print(f"{YELLOW}[DRY-RUN]   version: 1.0.0{RESET}")
        return

    profile_path.write_text(content, encoding="utf-8")

    print(f"{GREEN}Created profile '{name}':{RESET}")
    print(f"{GREEN}  - Written to {profile_path}{RESET}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="scaffold",
        description="CLI scaffolder for capabilities, workflows, and domain profiles.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to run")

    # --- capability ---
    cap_parser = subparsers.add_parser(
        "capability", help="Scaffold a new capability in the ontology"
    )
    cap_parser.add_argument("name", help="Kebab-case capability name")
    cap_parser.add_argument(
        "--layer",
        required=True,
        choices=LAYERS,
        help="Cognitive layer for this capability",
    )
    cap_parser.add_argument(
        "--risk",
        default="low",
        choices=RISK_LEVELS,
        help="Risk level (default: low)",
    )
    cap_parser.add_argument(
        "--mutation",
        action="store_true",
        default=False,
        help="Mark as mutation capability (sets requires_checkpoint=true)",
    )
    cap_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without writing any files",
    )

    # --- workflow ---
    wf_parser = subparsers.add_parser(
        "workflow", help="Scaffold a new workflow in the catalog"
    )
    wf_parser.add_argument("name", help="Kebab-case workflow name")
    wf_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without writing any files",
    )

    # --- profile ---
    prof_parser = subparsers.add_parser(
        "profile", help="Scaffold a new domain profile"
    )
    prof_parser.add_argument("name", help="Kebab-case profile name")
    prof_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without writing any files",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the scaffolder CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "capability": scaffold_capability,
        "workflow": scaffold_workflow,
        "profile": scaffold_profile,
    }

    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()
