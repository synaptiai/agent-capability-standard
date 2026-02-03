#!/usr/bin/env python3
"""Workflow validator (publish-ready): schema resolution + inference + consumer-type checking + patch suggestions

This is the final, publish-ready validator. It performs:

1) Structural validation
- Capability exists
- Prerequisites satisfied
- mapping_ref / output_conforms_to exist

2) Reference validation
- `${store.path}` exists
- External input refs (`inputs.*.ref`) resolved

3) Type system
- Inferred type for untyped bindings
- Typed annotations validated against schema
- Typed annotations required only on ambiguity

4) Consumer-side type checking (NEW)
- Validates inferred/annotated binding types against the *consumer capability's input_schema*
- Emits coercion hints and transform suggestions when mismatch occurs

5) Patch suggestions (NEW)
- Writes `tools/validator_suggestions.json` with machine-usable fixes:
  - insert transform step
  - update binding to coerced output
  - mapping_ref chosen from coercion registry when possible
- Optionally writes `tools/validator_patch.diff` (unified diff) when `--emit-patch` is passed

Usage:
- `python3 tools/validate_workflows.py`
- `python3 tools/validate_workflows.py --emit-patch`

"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from yaml_util import (
    DEFAULT_MAX_BYTES,
    ONTOLOGY_MAX_BYTES,
    YAMLSizeExceededError,
    safe_yaml_load,
)

# Standard error codes (Section 9, STANDARD-v1.0.0.md)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grounded_agency.errors import ErrorCode, StandardError, format_errors_response

ROOT = Path(__file__).resolve().parents[1]
ONTO = ROOT / "schemas" / "capability_ontology.yaml"
WF   = ROOT / "schemas" / "workflow_catalog.yaml"
COERCE_REG = ROOT / "schemas" / "transforms" / "transform_coercion_registry.yaml"
SUGGESTIONS_JSON = ROOT / "tools" / "validator_suggestions.json"
PATCH_DIFF = ROOT / "tools" / "validator_patch.diff"

REF_RE = re.compile(r"\$\{([^}]+)\}")

# -------------------- Helpers: type grammar --------------------

def split_top_level(s: str, sep: str) -> list[str]:
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in s:
        if ch == '<':
            depth += 1
        elif ch == '>':
            depth -= 1
        if ch == sep and depth == 0:
            out.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append(''.join(cur).strip())
    return out

def parse_type(t: str) -> dict[str, Any]:
    t = (t or '').strip()
    if not t:
        return {'kind': 'unknown'}
    if t.startswith('nullable<') and t.endswith('>'):
        return {'kind': 'nullable', 'of': parse_type(t[len('nullable<'):-1])}
    if t.startswith('array<') and t.endswith('>'):
        return {'kind': 'array', 'items': parse_type(t[len('array<'):-1])}
    if t.startswith('map<') and t.endswith('>'):
        inner = t[len('map<'):-1]
        parts = split_top_level(inner, ',')
        if len(parts) == 2:
            return {'kind': 'map', 'key': parse_type(parts[0]), 'value': parse_type(parts[1])}
        return {'kind': 'map', 'key': {'kind': 'unknown'}, 'value': {'kind': 'unknown'}}
    if t in {'string', 'number', 'boolean', 'object'}:
        return {'kind': t}
    return {'kind': 'unknown', 'raw': t}

def type_to_str(t: dict[str, Any]) -> str:
    k = t.get('kind', 'unknown')
    if k == 'array':
        return f"array<{type_to_str(t.get('items', {}))}>"
    if k == 'nullable':
        return f"nullable<{type_to_str(t.get('of', {}))}>"
    if k == 'map':
        return f"map<{type_to_str(t.get('key', {}))},{type_to_str(t.get('value', {}))}>"
    if k == 'union':
        opts = ','.join(type_to_str(x) for x in t.get('options', []))
        return f"union<{opts}>"
    return k

def schema_type(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return (type_ast, ambiguous)."""
    if not isinstance(schema, dict):
        return ({'kind': 'unknown'}, True)
    for comb in ('oneOf', 'anyOf', 'allOf'):
        if comb in schema:
            opts = []
            for o in schema.get(comb, []) or []:
                ot, _ = schema_type(o)
                opts.append(ot)
            return ({'kind': 'union', 'options': opts, 'via': comb}, True)
    t = schema.get('type')
    if isinstance(t, list):
        non_null = [x for x in t if x != 'null']
        if len(non_null) == 1 and 'null' in t:
            return ({'kind': 'nullable', 'of': {'kind': non_null[0]}}, False)
        return ({'kind': 'union', 'options': [{'kind': x} for x in non_null]}, True)
    if t == 'array':
        it, amb = schema_type(schema.get('items', {}) or {})
        return ({'kind': 'array', 'items': it}, amb or (it.get('kind') == 'unknown'))
    if t in {'string', 'number', 'boolean', 'object'}:
        return ({'kind': t}, False)
    if 'properties' in schema and isinstance(schema.get('properties'), dict):
        return ({'kind': 'object'}, False)
    if 'additionalProperties' in schema and isinstance(schema['additionalProperties'], dict):
        vt, amb = schema_type(schema['additionalProperties'])
        return ({'kind': 'map', 'key': {'kind': 'string'}, 'value': vt}, amb or (vt.get('kind') == 'unknown'))
    return ({'kind': 'unknown'}, True)


def is_type_compatible(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    ek, ak = expected.get('kind'), actual.get('kind')
    if ek == 'unknown' or ak == 'unknown':
        return True
    if ek == 'union':
        return any(is_type_compatible(opt, actual) for opt in expected.get('options', []))
    if ak == 'union':
        return any(is_type_compatible(expected, opt) for opt in actual.get('options', []))
    if ek == 'nullable':
        return is_type_compatible(expected['of'], actual) or ak == 'nullable'
    if ak == 'nullable':
        return is_type_compatible(expected, actual['of'])
    if ek != ak:
        return False
    if ek == 'array':
        return is_type_compatible(expected['items'], actual['items'])
    if ek == 'map':
        return is_type_compatible(expected['key'], actual['key']) and is_type_compatible(expected['value'], actual['value'])
    return True

# -------------------- $ref resolution --------------------

def load_schema_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if path.suffix.lower() in {'.yaml', '.yml'}:
        return safe_yaml_load(path) or {}
    if path.suffix.lower() == '.json':
        # Apply same size limit as YAML to prevent memory exhaustion (SEC-003).
        with open(path, encoding='utf-8') as f:
            file_size = os.fstat(f.fileno()).st_size
            if file_size > DEFAULT_MAX_BYTES:
                print(f"WARNING: JSON schema too large ({file_size:,} bytes): {path}", file=sys.stderr)
                return {}
            return json.loads(f.read())
    return {}

def resolve_json_pointer(doc: dict[str, Any], pointer: str) -> Any:
    if not pointer or pointer == '#':
        return doc
    if pointer.startswith('#'):
        pointer = pointer[1:]
    if pointer.startswith('/'):
        pointer = pointer[1:]
    if not pointer:
        return doc
    cur: Any = doc
    for part in pointer.split('/'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur

def resolve_ref(root: Path, ref: str) -> Any:
    if not ref:
        return None
    if '#/' in ref:
        file_part, ptr = ref.split('#',1)
        ptr = '#'+ptr
    else:
        file_part, ptr = ref, '#'
    doc = load_schema_file(root / file_part)
    return resolve_json_pointer(doc, ptr)

def resolve_schema_node(root: Path, node: Any, depth: int=0) -> Any:
    if depth>12:
        return node
    if isinstance(node, dict) and '$ref' in node:
        target = resolve_ref(root, node['$ref'])
        if isinstance(target, dict):
            merged = dict(target)
            for k,v in node.items():
                if k != '$ref':
                    merged[k]=v
            return resolve_schema_node(root, merged, depth+1)
        return node
    if isinstance(node, dict):
        return {k: resolve_schema_node(root,v,depth+1) for k,v in node.items()}
    if isinstance(node, list):
        return [resolve_schema_node(root,x,depth+1) for x in node]
    return node

# -------------------- Schema navigation --------------------

def schema_path_exists(schema: dict[str, Any], path: list[str]) -> bool:
    cur=schema or {}
    for key in path:
        if cur.get('type')=='array':
            cur=(cur.get('items',{}) or {})
        props=cur.get('properties',{}) or {}
        if key not in props:
            return False
        cur=props[key] or {}
    return True

def schema_node_at(schema: dict[str, Any], path: list[str]) -> dict[str, Any]:
    cur=schema or {}
    for key in path:
        if cur.get('type')=='array':
            cur=(cur.get('items',{}) or {})
        cur=(cur.get('properties',{}) or {}).get(key,{}) or {}
    return cur if isinstance(cur, dict) else {}

# -------------------- Binding parsing --------------------

def parse_ref_expr(expr: str) -> tuple[str, list[str], str | None]:
    expr=(expr or '').strip()
    if ': ' in expr:
        left, typ = expr.split(': ',1)
        typ=typ.strip()
    else:
        left, typ = expr, None
    left=left.strip()
    parts=left.split('.')
    store=parts[0]
    path=parts[1:] if len(parts)>1 else []
    return store, path, typ

def infer_binding_type(raw: str, schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    store, path, _typ = parse_ref_expr(raw)
    node=schema_node_at(schema, path)
    return schema_type(node)

# -------------------- Coercion registry --------------------

def load_coercions() -> dict[tuple[str,str], str]:
    reg = load_schema_file(COERCE_REG)
    out={}
    for c in reg.get('coercions',[]) or []:
        out[(c.get('from'), c.get('to'))] = c.get('mapping_ref')
    return out

COERCIONS = load_coercions()

# -------------------- Validation core --------------------

def validate_refs_in_string(s: str, schemas_by_store: dict[str, Any], external_inputs: dict[str, Any], errors: list[str], suggestions: list[dict[str, Any]], structured_errors: list[StandardError]):
    for m in REF_RE.finditer(s or ''):
        raw = m.group(1)
        store, path, typ_anno = parse_ref_expr(raw)

        # choose producer schema
        if store in schemas_by_store:
            schema = schemas_by_store[store]
            if path and not schema_path_exists(schema, path):
                errors.append(f"Bad reference ${{{raw}}}: path {'.'.join(path)} not in schema for {store}")
                structured_errors.append(StandardError(
                    code=ErrorCode.INVALID_BINDING_PATH,
                    message=f"Bad reference ${{{raw}}}: path {'.'.join(path)} not in schema for {store}",
                    location={"store": store, "path": ".".join(path), "ref": raw},
                ))
                continue
            actual_t, ambiguous = infer_binding_type(raw, schema)
            if typ_anno:
                expected = parse_type(typ_anno)
                if not is_type_compatible(expected, actual_t):
                    errors.append(f"Type mismatch ${{{raw}}}: expected {type_to_str(expected)} but schema has {type_to_str(actual_t)}")
                    structured_errors.append(StandardError(
                        code=ErrorCode.TYPE_MISMATCH,
                        message=f"Type mismatch ${{{raw}}}: expected {type_to_str(expected)} but schema has {type_to_str(actual_t)}",
                        location={"store": store, "ref": raw},
                    ))
                    suggestions.append({
                        "kind":"binding_type_mismatch",
                        "ref": raw,
                        "expected": type_to_str(expected),
                        "actual": type_to_str(actual_t),
                        "hint": "insert_transform",
                    })
            else:
                if ambiguous:
                    errors.append(f"Ambiguous type for ${{{raw}}}: inferred {type_to_str(actual_t)} is ambiguous/unknown. Add a typed annotation.")
                    structured_errors.append(StandardError(
                        code=ErrorCode.AMBIGUOUS_TYPE,
                        message=f"Ambiguous type for ${{{raw}}}: inferred {type_to_str(actual_t)} is ambiguous/unknown. Add a typed annotation.",
                        location={"store": store, "ref": raw},
                    ))
        elif store in external_inputs:
            schema = external_inputs[store]
            if path and isinstance(schema, dict) and 'properties' in schema and not schema_path_exists(schema, path):
                errors.append(f"Bad external reference ${{{raw}}}: path {'.'.join(path)} not in inputs schema for {store}")
                structured_errors.append(StandardError(
                    code=ErrorCode.INVALID_BINDING_PATH,
                    message=f"Bad external reference ${{{raw}}}: path {'.'.join(path)} not in inputs schema for {store}",
                    location={"store": store, "path": ".".join(path), "ref": raw},
                ))
                continue
            actual_t, ambiguous = infer_binding_type(raw, schema) if isinstance(schema, dict) else ({'kind':'unknown'}, True)
            if typ_anno:
                expected=parse_type(typ_anno)
                if not is_type_compatible(expected, actual_t):
                    errors.append(f"Type mismatch ${{{raw}}} (external): expected {type_to_str(expected)} but schema has {type_to_str(actual_t)}")
                    structured_errors.append(StandardError(
                        code=ErrorCode.TYPE_MISMATCH,
                        message=f"Type mismatch ${{{raw}}} (external): expected {type_to_str(expected)} but schema has {type_to_str(actual_t)}",
                        location={"store": store, "ref": raw, "source": "external"},
                    ))
                    suggestions.append({
                        "kind":"external_binding_type_mismatch",
                        "ref": raw,
                        "expected": type_to_str(expected),
                        "actual": type_to_str(actual_t),
                        "hint": "update_inputs_schema_or_transform",
                    })
            else:
                if ambiguous:
                    errors.append(f"Ambiguous external type for ${{{raw}}}: inferred {type_to_str(actual_t)} is ambiguous/unknown. Add typed annotation or refine inputs schema.")
                    structured_errors.append(StandardError(
                        code=ErrorCode.AMBIGUOUS_TYPE,
                        message=f"Ambiguous external type for ${{{raw}}}: inferred {type_to_str(actual_t)} is ambiguous/unknown. Add typed annotation or refine inputs schema.",
                        location={"store": store, "ref": raw, "source": "external"},
                    ))
        else:
            errors.append(f"Unknown reference store '{store}' in ${{{raw}}}")
            structured_errors.append(StandardError(
                code=ErrorCode.MISSING_PRODUCER,
                message=f"Unknown reference store '{store}' in ${{{raw}}}",
                location={"store": store, "ref": raw},
            ))

def scan_refs(val: Any, schemas_by_store: dict[str, Any], external_inputs: dict[str, Any], errors: list[str], suggestions: list[dict[str, Any]], structured_errors: list[StandardError]):
    if isinstance(val, str):
        validate_refs_in_string(val, schemas_by_store, external_inputs, errors, suggestions, structured_errors)
    elif isinstance(val, list):
        for x in val:
            scan_refs(x, schemas_by_store, external_inputs, errors, suggestions, structured_errors)
    elif isinstance(val, dict):
        for x in val.values():
            scan_refs(x, schemas_by_store, external_inputs, errors, suggestions, structured_errors)

def consumer_type_check(step: dict[str, Any], cap_node: dict[str, Any], schemas_by_store: dict[str, Any], external_inputs: dict[str, Any], errors: list[str], suggestions: list[dict[str, Any]], workflow_name: str, step_index: int, structured_errors: list[StandardError]):
    """Compare binding inferred type vs consumer input_schema expected type."""
    input_schema = cap_node.get('input_schema') or {}
    input_schema = resolve_schema_node(ROOT, input_schema)
    if not isinstance(input_schema, dict):
        return

    bindings = step.get('input_bindings', {}) or {}
    for key, val in bindings.items():
        # only check scalar string refs in this pass
        if isinstance(val, str):
            for m in REF_RE.finditer(val):
                raw = m.group(1)
                store, path, typ_anno = parse_ref_expr(raw)

                # actual type from producer/external schema
                if store in schemas_by_store:
                    prod_schema = schemas_by_store[store]
                elif store in external_inputs and isinstance(external_inputs[store], dict):
                    prod_schema = external_inputs[store]
                else:
                    continue

                actual_t, _amb = infer_binding_type(raw, prod_schema)

                # expected type from consumer input_schema at key
                expected_node = (input_schema.get('properties', {}) or {}).get(key, {})
                expected_t, expected_amb = schema_type(expected_node)

                # If consumer expects ambiguous type, do not enforce, but recommend annotation
                if expected_amb:
                    continue

                if not is_type_compatible(expected_t, actual_t):
                    errors.append(
                        f"Consumer input type mismatch in workflow '{workflow_name}' step {step_index} ({step.get('capability')}): input '{key}' expects {type_to_str(expected_t)} but got {type_to_str(actual_t)} from ${{{raw}}}"
                    )
                    structured_errors.append(StandardError(
                        code=ErrorCode.TYPE_MISMATCH,
                        message=f"Consumer input type mismatch: input '{key}' expects {type_to_str(expected_t)} but got {type_to_str(actual_t)} from ${{{raw}}}",
                        location={"workflow": workflow_name, "step": step_index, "capability": step.get('capability'), "input_key": key},
                    ))

                    # Suggest transform insertion if coercion exists
                    from_t = type_to_str(actual_t)
                    to_t = type_to_str(expected_t)
                    mapping = COERCIONS.get((from_t, to_t)) or COERCIONS.get((from_t.replace('union<','').replace('>',''), to_t))
                    suggestions.append({
                        "kind":"consumer_input_type_mismatch",
                        "workflow": workflow_name,
                        "step_index": step_index,
                        "capability": step.get('capability'),
                        "input_key": key,
                        "binding_ref": raw,
                        "from_type": from_t,
                        "to_type": to_t,
                        "suggested_mapping_ref": mapping,
                        "patch": build_transform_patch(workflow_name, step_index, key, raw, mapping, to_t)
                    })

def build_transform_patch(workflow_name: str, step_index: int, input_key: str, raw_ref: str, mapping_ref: str | None, to_type: str) -> dict[str, Any]:
    """Return a patch plan (not directly applied)"""
    transform_store = f"coerce_{workflow_name}_{step_index}_{input_key}"
    return {
        "action":"insert_transform_before_step",
        "insert_at_step_index": step_index,
        "new_step": {
            "capability":"transform",
            "purpose": f"Coerce {input_key} to {to_type} for consumer input contract",
            "mapping_ref": mapping_ref or "docs/schemas/transform_mapping_<custom>.yaml",
            "input_bindings": {"source": f"${{{raw_ref}}}"},
            "store_as": transform_store
        },
        "update_step": {
            "step_index": step_index,
            "input_bindings_update": {
                input_key: f"${{{transform_store}.transformed: {to_type}}}"
            }
        }
    }

def check_workflow(name: str, wf: dict[str, Any], nodes: dict[str, Any], errors: list[str], suggestions: list[dict[str, Any]], structured_errors: list[StandardError]):
    steps = wf.get('steps',[]) or []
    inputs_decl = wf.get('inputs',{}) or {}

    external_inputs={}
    for key, spec in inputs_decl.items():
        if isinstance(spec, dict) and 'ref' in spec:
            resolved = resolve_ref(ROOT, spec['ref'])
            if isinstance(resolved, dict):
                external_inputs[key] = resolve_schema_node(ROOT, resolved)
            else:
                external_inputs[key] = {'type':'object','properties':{}}
                errors.append(f"[{name}] inputs.{key} ref could not be resolved: {spec['ref']}")
                structured_errors.append(StandardError(
                    code=ErrorCode.INVALID_REF,
                    message=f"inputs.{key} ref could not be resolved: {spec['ref']}",
                    location={"workflow": name, "field": f"inputs.{key}.ref"},
                ))
        elif isinstance(spec, dict):
            external_inputs[key] = resolve_schema_node(ROOT, spec)
        else:
            external_inputs[key] = {'type':'object','properties':{}}

    seen=set()
    schemas_by_store={}
    for i, st in enumerate(steps):
        cap = st.get('capability')
        if cap not in nodes:
            errors.append(f"[{name}] step {i}: unknown capability '{cap}'")
            structured_errors.append(StandardError(
                code=ErrorCode.UNKNOWN_CAPABILITY,
                message=f"Capability '{cap}' not found in ontology",
                location={"workflow": name, "step": i, "field": "capability"},
            ))
            continue
        node = nodes[cap]

        for r in node.get('requires',[]):
            if r not in seen:
                errors.append(f"[{name}] step {i} '{cap}' missing required prereq '{r}' before it")
                structured_errors.append(StandardError(
                    code=ErrorCode.MISSING_PREREQUISITE,
                    message=f"Capability '{cap}' missing required prerequisite '{r}' before it",
                    location={"workflow": name, "step": i, "capability": cap, "prerequisite": r},
                ))

        mref = st.get('mapping_ref')
        if mref and not (ROOT / mref).exists():
            errors.append(f"[{name}] step {i} '{cap}' mapping_ref missing file: {mref}")
            structured_errors.append(StandardError(
                code=ErrorCode.SCHEMA_NOT_FOUND,
                message=f"mapping_ref missing file: {mref}",
                location={"workflow": name, "step": i, "capability": cap, "field": "mapping_ref"},
            ))
        cref = st.get('output_conforms_to')
        if cref:
            file_part = cref.split('#')[0]
            if not (ROOT / file_part).exists():
                errors.append(f"[{name}] step {i} '{cap}' output_conforms_to missing file: {file_part}")
                structured_errors.append(StandardError(
                    code=ErrorCode.SCHEMA_NOT_FOUND,
                    message=f"output_conforms_to missing file: {file_part}",
                    location={"workflow": name, "step": i, "capability": cap, "field": "output_conforms_to"},
                ))

        store = st.get('store_as')
        if store:
            out_schema = node.get('output_schema') or {'type':'object','properties':{}}
            schemas_by_store[store] = resolve_schema_node(ROOT, out_schema)

        scan_refs(st.get('input_bindings',{}), schemas_by_store, external_inputs, errors, suggestions, structured_errors)
        validate_refs_in_string(st.get('condition',''), schemas_by_store, external_inputs, errors, suggestions, structured_errors)
        for g in st.get('gates',[]) or []:
            validate_refs_in_string(g.get('when',''), schemas_by_store, external_inputs, errors, suggestions, structured_errors)

        # consumer-side type checking
        consumer_type_check(st, node, schemas_by_store, external_inputs, errors, suggestions, name, i, structured_errors)

        seen.add(cap)

def apply_patch_suggestions_to_yaml(workflows: dict[str, Any], suggestions: list[dict[str, Any]]) -> str:
    """Return a modified YAML string applying transform insertion patches (best-effort)."""
    wf_copy = json.loads(json.dumps(workflows))
    # apply only consumer_input_type_mismatch patches
    grouped = {}
    for s in suggestions:
        if s.get("kind")=="consumer_input_type_mismatch":
            p = s.get("patch")
            if not p:
                continue
            grouped.setdefault(s["workflow"], []).append(p)

    for wf_name, patches in grouped.items():
        if wf_name not in wf_copy:
            continue
        steps = wf_copy[wf_name].get("steps", [])
        # apply in descending index order to keep indices stable
        patches_sorted = sorted(patches, key=lambda x: x["insert_at_step_index"], reverse=True)
        for p in patches_sorted:
            idx = p["insert_at_step_index"]
            new_step = p["new_step"]
            steps.insert(idx, new_step)
            # update binding
            upd = p["update_step"]["input_bindings_update"]
            target_idx = p["update_step"]["step_index"] + 1  # shifted by insertion
            if 0 <= target_idx < len(steps):
                steps[target_idx].setdefault("input_bindings", {})
                steps[target_idx]["input_bindings"].update(upd)
        wf_copy[wf_name]["steps"] = steps

    return yaml.safe_dump(wf_copy, sort_keys=False, allow_unicode=True)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-patch", action="store_true", help="Write a unified diff patch for suggested transform insertions.")
    ap.add_argument("--catalog", default=None, help="Override workflow catalog path.")
    args = ap.parse_args()

    try:
        onto = safe_yaml_load(ONTO, max_size=ONTOLOGY_MAX_BYTES)
    except (FileNotFoundError, YAMLSizeExceededError, yaml.YAMLError) as e:
        print(f"ERROR: Cannot load ontology: {e}", file=sys.stderr)
        sys.exit(1)

    wf_path = Path(args.catalog) if args.catalog else WF
    try:
        workflows = safe_yaml_load(wf_path) or {}
    except (FileNotFoundError, YAMLSizeExceededError, yaml.YAMLError) as e:
        print(f"ERROR: Cannot load workflow catalog: {e}", file=sys.stderr)
        sys.exit(1)
    nodes = {n['id']: n for n in onto['nodes']}

    errors: list[str] = []
    suggestions: list[dict[str, Any]] = []
    structured_errors: list[StandardError] = []

    for name, wf in workflows.items():
        check_workflow(name, wf, nodes, errors, suggestions, structured_errors)

    # Always write suggestions JSON (even on pass)
    output = {
        "errors": errors,
        "structured_errors": format_errors_response(structured_errors).get("errors", []),
        "suggestions": suggestions,
    }
    SUGGESTIONS_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")

    if args.emit_patch and suggestions:
        modified = apply_patch_suggestions_to_yaml(workflows, suggestions)
        original = wf_path.read_text(encoding="utf-8")
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile="workflow_catalog.yaml",
            tofile="workflow_catalog.yaml (suggested)",
        )
        PATCH_DIFF.write_text("".join(diff), encoding="utf-8")

    if errors:
        print("VALIDATION FAIL:")
        for e in errors:
            print(" -", e)
        print(f"\nSuggestions written to: {SUGGESTIONS_JSON}")
        if args.emit_patch:
            print(f"Patch diff written to: {PATCH_DIFF}")
        sys.exit(1)

    print("VALIDATION PASS")
    print(f"Suggestions written to: {SUGGESTIONS_JSON}")

if __name__ == '__main__':
    main()
