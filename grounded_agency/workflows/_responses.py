"""What a host's responses carry that no record may hold (STANDARD v1.2
§6.5, §6.7): the evidence anchors of an ``Output`` and of an ``Event``.

The runner submits responses through :func:`redact_anchors`, and the
idempotency log keeps the ``Output`` it replays in the same form, so the
run's state, outputs, trace and snapshots, and the log's file, never hold a
secret an anchor held."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..state.redaction import Redactor


def _anchors(redactor: Redactor, items: Sequence[Any]) -> tuple[list[Any], bool]:
    """Each item redacted as an evidence anchor (its secrets replaced, its
    digest gone), and whether any changed."""
    redacted: list[Any] = []
    changed = False
    for item in items:
        out, pointers = redactor.redact_anchor_data(item)
        redacted.append(out if pointers else item)
        changed = changed or bool(pointers)
    return redacted, changed


def redact_anchors(redactor: Redactor, response: Any) -> Any:
    """``response`` with the evidence anchors it carries redacted as the
    evidence stores redact one (§6.5, §6.7): an ``Output``'s
    ``value.evidence_anchors`` and an ``Event``'s ``event.anchors``, which
    the core copies into a ``receive`` or ``wait`` step's output (its
    ``evidence_anchors``, and the event under ``data`` or ``result``). An
    array of anchors given as a tuple, which the core reads as an array, is
    given back as a list. Any other response is returned as it is.

    An ``Output``'s ``evidence_seen`` is rewritten to match (§5.20): it lists
    an anchor's redacted ``ref`` when the host listed the anchor's own
    ``ref``. When two anchors' refs are one after redaction and the host
    listed only one of them, it lists neither: the core then cannot tell
    them apart, so the one it did not list must not pass as seen. A ``seen``
    that is not an array of strings is left for the core to refuse."""
    if not isinstance(response, dict):
        return response
    kind = response.get("kind")
    if kind == "Event":
        event = response.get("event")
        items = event.get("anchors") if isinstance(event, dict) else None
        if not isinstance(event, dict) or not isinstance(items, (list, tuple)):
            return response
        redacted, changed = _anchors(redactor, items)
        if not changed and isinstance(items, list):
            return response
        return {**response, "event": {**event, "anchors": redacted}}
    if kind != "Output":
        return response
    value = response.get("value")
    items = value.get("evidence_anchors") if isinstance(value, dict) else None
    if not isinstance(value, dict) or not isinstance(items, (list, tuple)):
        return response
    redacted, changed = _anchors(redactor, items)
    if not changed and isinstance(items, list):
        return response
    result = {**response, "value": {**value, "evidence_anchors": redacted}}
    seen = response.get("evidence_seen")
    if (
        changed
        and isinstance(seen, (list, tuple))
        and all(isinstance(s, str) for s in seen)
    ):
        listed = set(seen)
        verdict: dict[str, bool] = {}
        for raw, out in zip(items, redacted, strict=True):
            ref = raw.get("ref") if isinstance(raw, dict) else None
            shown = out.get("ref") if isinstance(out, dict) else None
            if isinstance(ref, str) and isinstance(shown, str):
                verdict[shown] = verdict.get(shown, True) and ref in listed
        result["evidence_seen"] = [r for r, ok in verdict.items() if ok]
    return result
