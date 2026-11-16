"""Generate the safety-layer conformance fixtures (STANDARD 1.2.0 section 10.4):
tests/conformance/bindings/*.json and tests/conformance/calls/*.json.

Binding fixtures pin what a safety layer reports when it loads tool binding
records and checks the tools a host offers (sections 5.18.1 to 5.18.4), and
the effective flags it computes. Call-sequence fixtures pin what it does with
a sequence of calls in one layer scope (sections 5.18.5 to 5.18.7). Edit the
fixtures here, not the JSON, then regenerate:

    python scripts/gen_call_fixtures.py          # write the fixtures
    python scripts/gen_call_fixtures.py --check  # fail if they differ (CI)

Writing also deletes any top-level JSON file in the two directories that this
script does not generate; their schema/ and statements/ subdirectories are
left alone. Every fixture is checked against its schema
(tests/conformance/{bindings,calls}/schema/fixture.schema.json) before
anything is written. The runners read the fixtures in place:
tests/test_binding_fixtures.py and tests/test_call_fixtures.py (Python), and
packages/acs-core/test/bindings.test.ts and
examples/standard_agents/test/calls.test.ts (TypeScript), which read the
JSON text exactly (parseJsonExact), so an integer literal beyond 2^53 is not
rounded on the way in.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
CONFORMANCE = ROOT / "tests" / "conformance"
BINDINGS_DIR = CONFORMANCE / "bindings"
CALLS_DIR = CONFORMANCE / "calls"
TOOL_BINDING_SCHEMA = ROOT / "schemas" / "interop" / "tool_binding.schema.json"


def _ontology_version() -> str:
    text = (ROOT / "schemas" / "capability_ontology.yaml").read_text(encoding="utf-8")
    return str(yaml.safe_load(text)["meta"]["version"])


ONTOLOGY = _ontology_version()

binding_fixtures: dict[str, dict[str, Any]] = {}
call_fixtures: dict[str, dict[str, Any]] = {}

LOW = {
    "risk": "low",
    "mutation": False,
    "requires_checkpoint": False,
    "requires_approval": False,
}
GATED = {
    "risk": "high",
    "mutation": True,
    "requires_checkpoint": True,
    "requires_approval": True,
}


def rec(tool: str, capability: str | None = None, **members: Any) -> dict[str, Any]:
    """A tool binding record under this ontology."""
    record: dict[str, Any] = {"tool": tool, "ontology": ONTOLOGY}
    if capability is not None:
        record["capability"] = capability
    record.update(members)
    return record


def diag(code: str, tool: str) -> dict[str, str]:
    return {"code": code, "tool": tool}


def flags(
    risk: str, mutation: bool, checkpoint: bool, approval: bool
) -> dict[str, Any]:
    return {
        "risk": risk,
        "mutation": mutation,
        "requires_checkpoint": checkpoint,
        "requires_approval": approval,
    }


def binding(
    name: str,
    description: str,
    records: list[Any],
    *,
    errors: list[dict[str, str]] = (),  # type: ignore[assignment]
    warnings: list[dict[str, str]] = (),  # type: ignore[assignment]
    effective: dict[str, dict[str, Any]] | None = None,
    offered: dict[str, str | None] | None = None,
    host_actions: list[tuple[str, str]] | None = None,
    host_takes_checkpoints: bool | None = None,
) -> None:
    fixture: dict[str, Any] = {"description": description, "ontology": ONTOLOGY}
    if (
        offered is not None
        or host_actions is not None
        or host_takes_checkpoints is not None
    ):
        fixture["needs"] = ["offered_tools"]
    fixture["records"] = records
    if offered is not None:
        fixture["offered"] = offered
    if host_actions is not None:
        fixture["host_actions"] = [{"action": a, "tool": t} for a, t in host_actions]
    if host_takes_checkpoints is not None:
        fixture["host_takes_checkpoints"] = host_takes_checkpoints
    fixture["expect"] = {
        "errors": list(errors),
        "warnings": list(warnings),
        "effective": effective or {},
    }
    if name in binding_fixtures:
        raise ValueError(f"binding fixture {name!r} defined twice")
    binding_fixtures[name] = fixture


# ---------------------------------------------------------------------------
# Binding fixtures (sections 5.18.1 to 5.18.4)
# ---------------------------------------------------------------------------

binding(
    "stricter_flag",
    "A declared flag stricter than the ontology's takes effect, with no diagnostic.",
    [rec("look", "retrieve", flags={"requires_approval": True})],
    effective={"look": flags("low", False, False, True)},
)
binding(
    "weaker_flag",
    "A declared flag weaker than the ontology's has no effect and is W602, one per flag.",
    [rec("write", "mutate", flags={"risk": "low", "requires_checkpoint": False})],
    warnings=[diag("W602", "write"), diag("W602", "write")],
    effective={"write": GATED},
)
binding(
    "mutation_overridable_honoured",
    "mutation: false on a mutation_overridable capability, the only one the record names, is honoured.",
    [rec("log", "audit", flags={"mutation": False})],
    effective={"log": LOW},
)
binding(
    "mutation_overridable_with_additional",
    "mutation: false is not honoured in a record that names another capability: W602, and the call is a mutation.",
    [
        rec(
            "log",
            "audit",
            additional_capabilities=["persist"],
            flags={"mutation": False},
        )
    ],
    warnings=[diag("W602", "log")],
    effective={"log": flags("low", True, False, False)},
)
binding(
    "additional_strictest",
    "A record's effective flags are the strictest across its capability and its additional capabilities.",
    [rec("apply", "plan", additional_capabilities=["mutate"])],
    effective={"apply": GATED},
)
binding(
    "unknown_capability",
    "A capability the ontology does not define is V101, and the record is not loaded.",
    [rec("x", "no_such")],
    errors=[diag("V101", "x")],
)
binding(
    "unknown_additional_capability",
    "An additional capability the ontology does not define is V101, and the record is not loaded.",
    [rec("x", "plan", additional_capabilities=["no_such"])],
    errors=[diag("V101", "x")],
)
binding(
    "invokes_transitive",
    "A composite takes, transitively, the effective flags of every binding it invokes.",
    [
        rec("a", "invoke", invokes=["b"]),
        rec("b", "invoke", invokes=["c"]),
        rec("c", "mutate"),
    ],
    effective={"a": GATED, "b": GATED, "c": GATED},
)
binding(
    "invokes_unresolved",
    "An invokes name that no binding of the set has is V107, and the composite is not loaded.",
    [rec("a", "invoke", invokes=["missing"])],
    errors=[diag("V107", "a")],
)
binding(
    "invokes_cycle",
    "A cycle through invokes is V105, and none of its members is loaded.",
    [rec("a", "invoke", invokes=["b"]), rec("b", "invoke", invokes=["a"])],
    errors=[diag("V105", "a"), diag("V105", "b")],
)
binding(
    "duplicate_binding",
    "Two records for one tool are V110, and neither is loaded.",
    [rec("x", "observe"), rec("x", "mutate")],
    errors=[diag("V110", "x"), diag("V110", "x")],
)
binding(
    "unsupported_ontology",
    "A record written against another ontology major is V109, and is not loaded.",
    [{"tool": "x", "ontology": "3.0.0", "capability": "observe"}],
    errors=[diag("V109", "x")],
)
binding(
    "unsupported_standard",
    "A record that cites a Standard version the layer does not support is V109, and is not loaded.",
    [rec("look", "observe", standard="1.9")],
    errors=[diag("V109", "look")],
)
binding(
    "control_with_capability",
    "A control-only record names no capability: S303, and the record is not loaded.",
    [rec("done", "observe", control=True)],
    errors=[diag("S303", "done")],
)
binding(
    "missing_ontology",
    "A record with no ontology is S304, and is not loaded.",
    [{"tool": "x", "capability": "observe"}],
    errors=[diag("S304", "x")],
)
binding(
    "bad_approval_duration",
    "An approval.expires that is not a duration (section 5.10.1) is S303, and the record is not loaded.",
    [rec("write", "mutate", approval={"expires": "1w"})],
    errors=[diag("S303", "write")],
)
binding(
    "approval_integral_float",
    "An approval.min_approvers written 1.0 is the integer 1, as JSON Schema's integer reads it: the record loads.",
    [rec("write", "mutate", approval={"min_approvers": 1.0})],
    effective={"write": GATED},
)
binding(
    "vendor_member_not_i_json",
    "A member with no I-JSON form (section 5.14), here an integer beyond 2^53 under an x- key, is S303: the record could not be recorded or digested, and is not loaded.",
    [rec("look", "observe", **{"x-build": 2**60})],
    errors=[diag("S303", "look")],
)
binding(
    "vendor_member_beyond_limit_by_one",
    "The integer literal 2^53 + 1 has no I-JSON form, though a binary64 reader rounds it to 2^53: S303, and the record is not loaded.",
    [rec("look", "observe", **{"x-build": 2**53 + 1})],
    errors=[diag("S303", "look")],
)
binding(
    "vendor_member_integral_float",
    "1.8e16 is a number canonical JSON writes as the integer 18000000000000000, beyond 2^53: S303, and the record is not loaded.",
    [rec("look", "observe", **{"x-build": 1.8e16})],
    errors=[diag("S303", "look")],
)
binding(
    "vendor_member_at_limit",
    "2^53 itself, and 1e21, which canonical JSON writes in exponent form, are I-JSON: the record loads.",
    [rec("look", "observe", **{"x-build": 2**53, "x-scale": 1e21})],
    effective={"look": LOW},
)
binding(
    "approval_role_null",
    "approval.role, when present, is a non-empty string: null is S303, and the record is not loaded.",
    [rec("write", "mutate", approval={"role": None})],
    errors=[diag("S303", "write")],
)
binding(
    "approval_expires_at_limit",
    "approval.expires of 2^53 - 1 milliseconds, the longest a binding can state, loads.",
    [rec("write", "mutate", approval={"expires": "PT9007199254740.991S"})],
    effective={"write": GATED},
)
binding(
    "approval_expires_beyond_limit",
    "approval.expires longer than 2^53 - 1 milliseconds is S303, and the record is not loaded.",
    [rec("write", "mutate", approval={"expires": "PT9007199254740.992S"})],
    errors=[diag("S303", "write")],
)
binding(
    "offered_unbound",
    "An offered tool with no binding is W617.",
    [rec("save", "checkpoint")],
    offered={"save": "save", "other": None},
    warnings=[diag("W617", "other")],
    effective={"save": flags("low", True, False, False)},
)
binding(
    "offered_name_mismatch",
    "A binding whose tool is not the name the host offers the tool under is V111.",
    [rec("save", "checkpoint")],
    offered={"save2": "save"},
    errors=[diag("V111", "save2")],
    effective={"save": flags("low", True, False, False)},
)
binding(
    "offered_missing_checkpoint",
    "An offered tool that requires a checkpoint, with no offered tool that takes one, is V102: its calls could never run.",
    [rec("write", "mutate")],
    offered={"write": "write"},
    errors=[diag("V102", "write")],
    effective={"write": GATED},
)
binding(
    "offered_classified_tool_counts",
    "An offered tool with a classifier counts as able to perform any capability, a checkpoint included.",
    [rec("write", "mutate"), rec("shell", "mutate", classifier="shell")],
    offered={"write": "write", "shell": "shell"},
    effective={"write": GATED, "shell": GATED},
)
binding(
    "offered_host_takes_checkpoints",
    "A host that takes checkpoints itself counts as performing checkpoint.",
    [rec("write", "mutate")],
    offered={"write": "write"},
    host_takes_checkpoints=True,
    effective={"write": GATED},
)
binding(
    "gated_control_action",
    "A host action taken whenever a gated tool is called is F506.",
    [rec("write", "mutate"), rec("save", "checkpoint")],
    offered={"write": "write", "save": "save"},
    host_actions=[("stop", "write")],
    errors=[diag("F506", "write")],
    effective={"write": GATED, "save": flags("low", True, False, False)},
)
binding(
    "unbound_control_action",
    "A host action tied to an unbound tool is F506, beside the tool's W617.",
    [],
    offered={"other": None},
    host_actions=[("stop", "other")],
    errors=[diag("F506", "other")],
    warnings=[diag("W617", "other")],
)
binding(
    "ungated_tool_action_ok",
    "A host action may be tied to a bound tool with no prerequisite, checkpoint or approval.",
    [rec("look", "observe")],
    offered={"look": "look"},
    host_actions=[("status", "look")],
    effective={"look": LOW},
)
binding(
    "control_action_ok",
    "A host action tied to a control-only tool is allowed.",
    [{"tool": "done", "ontology": ONTOLOGY, "control": True}],
    offered={"done": "done"},
    host_actions=[("stop", "done")],
    effective={"done": LOW},
)


# ---------------------------------------------------------------------------
# Call-sequence fixtures (sections 5.18.5 to 5.18.7, and the output-contract
# row of section 5.18.10)
# ---------------------------------------------------------------------------

ALICE = ["alice"]
RUN = "run"


def refuse(code: str) -> dict[str, str]:
    return {"refuse": code}


def refuse_output(code: str) -> dict[str, str]:
    """The call ran, and the layer refused its output."""
    return {"refuse_output": code}


# A call that states no `returns` (null is a value a call may return).
_NO_RETURNS: Any = object()


def call(
    tool: str,
    expect: Any,
    args: dict[str, Any] | None = None,
    *,
    approve: list[str] | None = None,
    reject: list[str] | None = None,
    fails: bool = False,
    returns: Any = _NO_RETURNS,
    nested: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    step: dict[str, Any] = {"call": tool}
    if args is not None:
        step["args"] = args
    if approve is not None:
        step["approve"] = approve
    if reject is not None:
        step["reject"] = reject
    if fails:
        step["fails"] = True
    if returns is not _NO_RETURNS:
        step["returns"] = returns
    if nested is not None:
        step["nested"] = nested
    step["expect"] = expect
    return step


BOUNDARY = {"boundary": True}
EXPIRE_CHECKPOINT = {"expire": "checkpoint"}
EXPIRE_DECISION = {"expire": "decision"}


def standard_bindings(write: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The bindings every call fixture loads; `write` adds members to the
    write binding."""
    return [
        rec("save", "checkpoint"),
        rec("write", "mutate", **(write or {})),
        rec("undo", "rollback"),
        {"tool": "done", "ontology": ONTOLOGY, "control": True},
        rec("batch", "invoke", invokes=["write"]),
        rec("fix", "invoke", invokes=["undo"]),
        rec("solo", "invoke"),
        rec("apply", "plan", additional_capabilities=["mutate"]),
    ]


def calls(
    name: str,
    description: str,
    sequence: list[dict[str, Any]],
    *,
    needs: list[str] | None = None,
    write: dict[str, Any] | None = None,
    extra: list[dict[str, Any]] | None = None,
) -> None:
    fixture: dict[str, Any] = {"description": description, "ontology": ONTOLOGY}
    if needs:
        fixture["needs"] = needs
    fixture["bindings"] = standard_bindings(write) + (extra or [])
    fixture["sequence"] = sequence
    if name in call_fixtures:
        raise ValueError(f"call fixture {name!r} defined twice")
    call_fixtures[name] = fixture


A = {"path": "a"}
B = {"path": "b"}

calls(
    "checkpoint_single_use",
    "One checkpoint authorises one call that requires one; the next needs a new checkpoint.",
    [
        call("save", RUN),
        call("write", RUN, A, approve=ALICE),
        call("write", refuse("F501"), B, approve=ALICE),
    ],
)
calls(
    "two_checkpoints_two_calls",
    "Once the latest checkpoint is used, an earlier one that is still valid authorises the next call.",
    [
        call("save", RUN),
        call("save", RUN),
        call("write", RUN, A, approve=ALICE),
        call("write", RUN, B, approve=ALICE),
    ],
)
calls(
    "refused_call_keeps_checkpoint",
    "A call refused for want of approval uses no checkpoint.",
    [
        call("save", RUN),
        call("write", refuse("F502"), A),
        call("write", RUN, A, approve=ALICE),
    ],
)
calls(
    "failed_call_uses_checkpoint",
    "A call that started uses its checkpoint whatever its outcome.",
    [
        call("save", RUN),
        call("write", RUN, A, approve=ALICE, fails=True),
        call("write", refuse("F501"), B, approve=ALICE),
    ],
)
calls(
    "checkpoint_stale_after_boundary",
    "A checkpoint authorises nothing after an execution boundary.",
    [call("save", RUN), BOUNDARY, call("write", refuse("F501"), A, approve=ALICE)],
)
calls(
    "checkpoint_stale_after_max_age",
    "A checkpoint authorises nothing once the layer's maximum age has passed.",
    [
        call("save", RUN),
        EXPIRE_CHECKPOINT,
        call("write", refuse("F501"), A, approve=ALICE),
    ],
)
calls(
    "rollback_needs_checkpoint",
    "A rollback call needs a checkpoint taken earlier in the scope (F503 otherwise) and uses none.",
    [
        call("undo", refuse("F503")),
        call("save", RUN),
        call("undo", RUN),
        call("write", RUN, A, approve=ALICE),
    ],
)
calls(
    "rollback_after_use",
    "A used checkpoint can still be restored.",
    [call("save", RUN), call("write", RUN, A, approve=ALICE), call("undo", RUN)],
)
calls(
    "approval_args_not_i_json",
    "A call that needs approval with arguments that are not I-JSON (an integer beyond 2^53) is F502: no decision can bind to them. It uses nothing.",
    [
        call("save", RUN),
        call("write", refuse("F502"), {"path": "a", "n": 2**60}, approve=ALICE),
        call("write", RUN, A, approve=ALICE),
    ],
)
calls(
    "approval_args_beyond_limit_by_one",
    "Arguments holding the integer literal 2^53 + 1, which a binary64 reader rounds to 2^53, are not I-JSON: F502, and the call uses nothing.",
    [
        call("save", RUN),
        call("write", refuse("F502"), {"path": "a", "n": 2**53 + 1}, approve=ALICE),
        call("write", RUN, {"path": "a", "n": 2**53}, approve=ALICE),
    ],
)
calls(
    "approval_args_integral_float",
    "Arguments holding 1.8e16, which canonical JSON writes as an integer beyond 2^53, are not I-JSON: F502, and the call uses nothing.",
    [
        call("save", RUN),
        call("write", refuse("F502"), {"path": "a", "n": 1.8e16}, approve=ALICE),
        call("write", RUN, {"path": "a", "n": 1e21}, approve=ALICE),
    ],
)
calls(
    "decision_single_use",
    "One decision authorises one call: an identical later call needs a new decision.",
    [
        call("save", RUN),
        call("write", RUN, A, approve=ALICE),
        call("save", RUN),
        call("write", refuse("F502"), A),
    ],
)
calls(
    "additional_capability_strictest",
    "A call takes the flags and prerequisites of every capability its binding names.",
    [
        call("apply", refuse("F501"), A, approve=ALICE),
        call("save", RUN),
        call("apply", RUN, A, approve=ALICE),
    ],
)
calls(
    "composite_takes_invoked_flags",
    "A composite takes the flags of the bindings it invokes.",
    [
        call("batch", refuse("F501"), A, approve=ALICE),
        call("save", RUN),
        call("batch", RUN, A, approve=ALICE),
    ],
)
calls(
    "control_tool_ungated",
    "A control-only tool is never refused.",
    [call("done", RUN)],
)
calls(
    "unbound_tool_is_strictest",
    "A call of a tool with no binding needs a checkpoint and approval.",
    [
        call("other", refuse("F501"), A, approve=ALICE),
        call("save", RUN),
        call("other", refuse("F502"), B),
        call("other", RUN, B, approve=ALICE),
    ],
    needs=["unbound_calls"],
)
calls(
    "refused_call_keeps_decision",
    "A call refused for want of a checkpoint uses no recorded decision.",
    [
        call("write", refuse("F501"), A, approve=ALICE),
        call("save", RUN),
        call("write", RUN, A),
    ],
    needs=["recorded_approval"],
)
calls(
    "two_approvers",
    "A binding's approval.min_approvers counts distinct approvers.",
    [
        call("save", RUN),
        call("write", refuse("F502"), A, approve=["alice"]),
        call("write", RUN, A, approve=["alice", "bob"]),
    ],
    needs=["recorded_approval"],
    write={"approval": {"min_approvers": 2}},
)
calls(
    "rejection_wins",
    "Once any approver rejects, the request is rejected.",
    [
        call("save", RUN),
        call("write", refuse("F502"), A, approve=["alice"], reject=["bob"]),
    ],
    needs=["recorded_approval"],
)
calls(
    "decision_expires",
    "A recorded decision expires after the binding's approval.expires.",
    [
        call("write", refuse("F501"), A, approve=ALICE),
        EXPIRE_DECISION,
        call("save", RUN),
        call("write", refuse("F502"), A),
    ],
    needs=["recorded_approval"],
    write={"approval": {"expires": "10m"}},
)
calls(
    "nested_call_covered",
    "A nested call the layer attributes to the running composite is covered by its checkpoint and approval.",
    [
        call("save", RUN),
        call("batch", RUN, A, approve=ALICE, nested=[call("write", RUN, A)]),
    ],
    needs=["nested_calls"],
)
calls(
    "nested_call_outside_invokes",
    "A composite's call to a binding it does not list is F504.",
    [call("solo", RUN, nested=[call("write", refuse("F504"), A)])],
    needs=["nested_calls"],
)
calls(
    "nested_call_keeps_prerequisites",
    "A covered call skips only the checkpoint and the approval: its prerequisites are still checked.",
    [call("fix", RUN, nested=[call("undo", refuse("F503"))])],
    needs=["nested_calls"],
)

# The output-contract row of section 5.18.10: a call's output satisfies its
# capability's output contract (section 5.18.9), else the call that ran fails
# with R402.
FIND = [rec("find", "search")]
FOUND = {"results": [], "evidence_anchors": [], "confidence": 1}
calls(
    "output_breaks_contract",
    "An output that is not an object (a string, null), lacks a field its capability's output contract requires, has evidence_anchors that are not an array, or a required confidence outside 0 to 1 is refused with R402 (section 5.18.9).",
    [
        call("find", refuse_output("R402"), returns="found"),
        call("find", refuse_output("R402"), returns=None),
        call("find", refuse_output("R402"), returns={"results": []}),
        call(
            "find",
            refuse_output("R402"),
            returns={"results": [], "evidence_anchors": "file:a", "confidence": 1},
        ),
        call(
            "find",
            refuse_output("R402"),
            returns={"results": [], "evidence_anchors": [], "confidence": 2},
        ),
        call("find", RUN, returns=FOUND),
        call("find", RUN),
    ],
    extra=FIND,
)
calls(
    "nested_output_breaks_contract",
    "A nested call's output is checked as its own: what the nested call returns, not what an earlier call of the same tool returned.",
    [
        call(
            "gather",
            RUN,
            nested=[call("find", refuse_output("R402"), returns="found")],
        ),
        call("find", refuse_output("R402"), returns={"results": []}),
        call("gather", RUN, nested=[call("find", RUN)]),
    ],
    needs=["nested_calls"],
    extra=[*FIND, rec("gather", "invoke", invokes=["find"])],
)
calls(
    "output_not_i_json",
    "An output holding an integer beyond 2^53, which has no exact I-JSON form, is refused with R402.",
    [
        call(
            "find",
            refuse_output("R402"),
            returns={
                "results": [9007199254740993],
                "evidence_anchors": [],
                "confidence": 1,
            },
        ),
        call(
            "find",
            RUN,
            returns={
                "results": [9007199254740992],
                "evidence_anchors": [],
                "confidence": 1,
            },
        ),
    ],
    extra=FIND,
)
calls(
    "refused_output_uses_checkpoint",
    "A call whose output is refused has run: it used its checkpoint, and the next call needs a new one.",
    [
        call("save", RUN),
        call(
            "write", refuse_output("R402"), A, approve=ALICE, returns={"success": True}
        ),
        call("write", refuse("F501"), B, approve=ALICE),
        call("save", RUN),
        call("write", RUN, B, approve=ALICE),
    ],
)
calls(
    "refused_checkpoint_output_takes_none",
    "A call of a checkpoint tool whose output is refused has failed: it takes no checkpoint (section 5.18.6), so the next call that requires one is F501 and a rollback is F503, until a checkpoint call whose output passes.",
    [
        call("save", refuse_output("R402"), returns="saved"),
        call("write", refuse("F501"), A, approve=ALICE),
        call("undo", refuse("F503")),
        call("save", RUN),
        call("write", RUN, A, approve=ALICE),
        call("undo", RUN),
    ],
)


# ---------------------------------------------------------------------------


def _validator(schema_path: Path) -> jsonschema.Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    tool_binding = json.loads(TOOL_BINDING_SCHEMA.read_text(encoding="utf-8"))
    registry: Registry = Registry().with_resource(
        tool_binding["$id"], Resource.from_contents(tool_binding)
    )
    return jsonschema.Draft202012Validator(schema, registry=registry)


def check_format() -> None:
    """Every fixture conforms to its schema."""
    for directory, fixtures in (
        (BINDINGS_DIR, binding_fixtures),
        (CALLS_DIR, call_fixtures),
    ):
        validator = _validator(directory / "schema" / "fixture.schema.json")
        for name, fixture in fixtures.items():
            errors = sorted(validator.iter_errors(fixture), key=lambda e: list(e.path))
            if errors:
                where = "/".join(str(p) for p in errors[0].path)
                raise ValueError(
                    f"{directory.name}/{name}: {where}: {errors[0].message}"
                )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the fixtures on disk differ"
    )
    check = parser.parse_args(argv).check
    check_format()
    failed = False
    for directory, fixtures in (
        (BINDINGS_DIR, binding_fixtures),
        (CALLS_DIR, call_fixtures),
    ):
        rendered = {
            f"{name}.json": json.dumps(f, indent=2) + "\n"
            for name, f in fixtures.items()
        }
        on_disk = {
            p.name: p.read_text(encoding="utf-8") for p in directory.glob("*.json")
        }
        stale = sorted(n for n in rendered if on_disk.get(n) != rendered[n])
        extra = sorted(set(on_disk) - set(rendered))
        if check:
            for n in stale:
                print(f"out of date: {directory / n}")
            for n in extra:
                print(f"not generated by this script: {directory / n}")
            failed = failed or bool(stale or extra)
            if not (stale or extra):
                print(f"{len(rendered)} {directory.name} fixtures up to date")
            continue
        directory.mkdir(parents=True, exist_ok=True)
        for n in stale:
            (directory / n).write_text(rendered[n], encoding="utf-8")
        for n in extra:
            (directory / n).unlink()
        print(
            f"{len(rendered)} {directory.name} fixtures ({len(stale)} written, {len(extra)} removed)"
        )
    if failed:
        print("run: python scripts/gen_call_fixtures.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
