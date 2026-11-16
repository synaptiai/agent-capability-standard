"""Answers to an inquiry (STANDARD v1.2 §5.13.1).

``inquire`` returns the questions to put to someone; each has an ``id``
(unique within the inquiry) and an ``answer_type`` (``text``, ``choice``,
``boolean``, ``number``), and the output an ``inquiry_id``. The answers
arrive through ``receive`` as an item that carries ``inquiry_id`` and
``answers``, a list of ``{question_id, value}``. :func:`match_answers` is
the host-side check of what may be delivered;
``tests/conformance/inquiry/answers.json`` pins it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ANSWER_TYPES = ("text", "choice", "boolean", "number")


class AnswerError(ValueError):
    """An item a host must not deliver as answers to an inquiry. ``reason``
    is one of ``other_inquiry``, ``unknown_question``, ``wrong_type``,
    ``duplicate_answer`` and ``malformed``."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(f"{reason}: {message}")


def question_key(question: Mapping[str, Any]) -> str | None:
    """The key an answer names a question by: its ``id``, else its
    ``parameter``."""
    for key in ("id", "parameter"):
        value = question.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _json_equal(a: Any, b: Any) -> bool:
    """Equality of two JSON values: a boolean never equals a number (in
    Python ``True == 1``), numbers compare by value, and lists and objects
    member by member."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            _json_equal(x, y) for x, y in zip(a, b, strict=True)
        )
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _has_type(question: Mapping[str, Any], value: Any) -> bool:
    kind = question.get("answer_type")
    if kind == "text":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if kind == "choice":
        options = question.get("options")
        return isinstance(options, list) and any(
            _json_equal(option, value) for option in options
        )
    return True


def match_answers(
    inquiry_output: Mapping[str, Any], item: Mapping[str, Any]
) -> dict[str, Any]:
    """The answers ``item`` gives to ``inquiry_output``'s questions, by
    question key; unanswered questions are left out.

    Raises:
        AnswerError: When a host must not deliver ``item`` (§5.13.1).
    """
    inquiry_id = inquiry_output.get("inquiry_id")
    if not isinstance(inquiry_id, str) or item.get("inquiry_id") != inquiry_id:
        # Answers correlate on the inquiry's id (§5.13.1): an inquiry with
        # none has no answers to deliver.
        raise AnswerError(
            "other_inquiry",
            f"the item answers inquiry {item.get('inquiry_id')!r}, "
            f"not {inquiry_output.get('inquiry_id')!r}",
        )
    questions: dict[str, Mapping[str, Any]] = {}
    for q in inquiry_output.get("questions") or []:
        if isinstance(q, Mapping) and (key := question_key(q)) is not None:
            questions[key] = q
    answers = item.get("answers")
    if not isinstance(answers, list) or not all(
        isinstance(a, Mapping) and isinstance(a.get("question_id"), str)
        for a in answers
    ):
        raise AnswerError(
            "malformed", "answers must be a list of objects with a string question_id"
        )
    out: dict[str, Any] = {}
    for answer in answers:
        key = answer["question_id"]
        question = questions.get(key)
        if question is None:
            raise AnswerError(
                "unknown_question", f"the inquiry asks no question {key!r}"
            )
        if key in out:
            raise AnswerError("duplicate_answer", f"question {key!r} is answered twice")
        value = answer.get("value")
        if not _has_type(question, value):
            raise AnswerError(
                "wrong_type",
                f"the answer to {key!r} is not a {question.get('answer_type')} answer",
            )
        out[key] = value
    return out
