"""The host protocol's actions and responses (STANDARD v1.2 §5.19.1), as
typed dicts.

`schemas/host_protocol.schema.json` defines each exactly; these are its
shapes for type checkers (`tests/test_host_protocol_schema.py` checks the
keys against the schema). At run time actions and responses are plain dicts:
a host ignores an action member it does not know, and the executor ignores a
response member the protocol does not define (§5.19.1).
"""

from typing import Any, Literal, NotRequired, TypedDict

# The record modes of a run (§6.4): the 1.1 records of approval steps, or a
# record of every step that runs.
RECORD_MODES = ("approvals", "actions")


class _Head(TypedDict):
    run_id: str
    id: int
    frame: list[str]


class InvokeCapabilityAction(_Head):
    kind: Literal["InvokeCapability"]
    step: int
    capability: str
    store_as: str | None
    domain: str | None
    inputs: dict[str, Any]
    deadline: int | None
    attempt: int
    replaces: NotRequired[Any]
    idempotency_key: NotRequired[str]


class CreateCheckpointAction(_Head):
    kind: Literal["CreateCheckpoint"]
    step: int


class RollbackAction(_Head):
    kind: Literal["Rollback"]
    step: int
    checkpoint_id: str


class RequestApprovalAction(_Head):
    kind: Literal["RequestApproval"]
    step: int
    approver: dict[str, Any]
    mode: str
    shown: list[Any]
    digest: str
    expires_at: int | None
    queued_action_id: NotRequired[str]


class RecheckSourceAction(_Head):
    kind: Literal["RecheckSource"]
    step: int
    source: str
    compare: str


class AwaitEventAction(_Head):
    kind: Literal["AwaitEvent"]
    step: int
    event_type: str
    source_kind: str | None
    correlate: dict[str, Any]
    accept_from: list[str] | None
    sender_check: list[str] | None
    accept_trust_classes: list[str] | None
    delegate_principal: NotRequired[str]
    liveness: dict[str, Any] | None
    deadline: int | None


class SleepAction(_Head):
    kind: Literal["Sleep"]
    until: int


class CompletedAction(_Head):
    kind: Literal["Completed"]
    outcome: str
    cause: str | None
    ended: NotRequired[dict[str, Any]]
    outputs: dict[str, Any]
    action_records: list[dict[str, Any]]
    deferred: list[dict[str, Any]]


class FailedAction(_Head):
    kind: Literal["Failed"]
    code: str
    step: int | None
    message: str
    reason: NotRequired[str]
    checkpoint_id: NotRequired[str]
    action_records: list[dict[str, Any]]
    deferred: list[dict[str, Any]]


Action = (
    InvokeCapabilityAction
    | CreateCheckpointAction
    | RollbackAction
    | RequestApprovalAction
    | RecheckSourceAction
    | AwaitEventAction
    | SleepAction
    | CompletedAction
    | FailedAction
)


class OutputResponse(TypedDict):
    kind: Literal["Output"]
    value: Any
    evidence_seen: NotRequired[list[str]]


class ErrorResponse(TypedDict):
    kind: Literal["Error"]
    code: str
    message: NotRequired[str]
    # A token of §5.19.7; any other value is ignored, as if absent.
    reason: NotRequired[str]


class CheckpointResponse(TypedDict):
    kind: Literal["Checkpoint"]
    checkpoint_id: str


class RolledBackResponse(TypedDict):
    kind: Literal["RolledBack"]
    not_covered: NotRequired[list[dict[str, Any]]]


class DecisionResponse(TypedDict):
    kind: Literal["Decision"]
    decision_id: str
    decision: str
    approvers: NotRequired[list[str]]
    digest: str
    approver_identities: NotRequired[list[dict[str, Any]] | None]


class CurrentResponse(TypedDict):
    kind: Literal["Current"]
    value: Any


class EventResponse(TypedDict):
    kind: Literal["Event"]
    event: dict[str, Any]
    principal: NotRequired[str | None]
    identity: NotRequired[dict[str, Any] | None]


class LivenessLostResponse(TypedDict):
    kind: Literal["LivenessLost"]


Response = (
    OutputResponse
    | ErrorResponse
    | CheckpointResponse
    | RolledBackResponse
    | DecisionResponse
    | CurrentResponse
    | EventResponse
    | LivenessLostResponse
)

# The typed dict of each kind, as the schema names it.
ACTIONS: dict[str, type] = {
    "InvokeCapability": InvokeCapabilityAction,
    "CreateCheckpoint": CreateCheckpointAction,
    "Rollback": RollbackAction,
    "RequestApproval": RequestApprovalAction,
    "RecheckSource": RecheckSourceAction,
    "AwaitEvent": AwaitEventAction,
    "Sleep": SleepAction,
    "Completed": CompletedAction,
    "Failed": FailedAction,
}
RESPONSES: dict[str, type] = {
    "Output": OutputResponse,
    "Error": ErrorResponse,
    "Checkpoint": CheckpointResponse,
    "RolledBack": RolledBackResponse,
    "Decision": DecisionResponse,
    "Current": CurrentResponse,
    "Event": EventResponse,
    "LivenessLost": LivenessLostResponse,
}
