"""Checks of a freshly downloaded body, run before it is cached (`CachedHttpClient`).

Public sources report trouble inside an HTTP 200 answer: an error object, a maintenance page, a
download cut short. The cache never expires by default, so such a body would be replayed in every
later run as "this source has nothing". A validator refuses it; the request then fails like any
other, the section says so, and the next run asks again.

A check looks at the shape only (is this the kind of document that was asked for), never at
whether it holds results: an empty result list is a valid answer.
"""

from __future__ import annotations

import json

from bioverdict.connectors.http import Validator


class BodyError(ValueError):
    """A source answered HTTP 200 with something that is not the data that was asked for."""


def _decoded(body: bytes) -> object:
    try:
        return json.loads(body)
    except ValueError as exc:
        raise BodyError("the answer is not JSON") from exc


def json_object(*required: str) -> Validator:
    """A JSON object that has every one of the `required` keys."""

    def check(body: bytes) -> None:
        answer = _decoded(body)
        if not isinstance(answer, dict):
            raise BodyError("the answer is not a JSON object")
        missing = [key for key in required if key not in answer]
        if missing:
            raise BodyError(f"the answer has no {', '.join(missing)}")

    return check


def json_rows(body: bytes) -> None:
    """A JSON list of row objects; an empty list is a valid "nothing matched"."""
    answer = _decoded(body)
    if not isinstance(answer, list) or not all(isinstance(row, dict) for row in answer):
        raise BodyError("the answer is not a list of rows")


def world_bank_page(body: bytes) -> None:
    """The World Bank answers `[page, rows]`, and an error as `[{"message": ...}]`."""
    answer = _decoded(body)
    if (
        not isinstance(answer, list)
        or len(answer) != 2
        or not isinstance(answer[0], dict)
        or "message" in answer[0]
        or not isinstance(answer[1], list | None)
    ):
        raise BodyError("the answer is not a page of indicator values")


def contains(*markers: bytes) -> Validator:
    """A document that holds every marker. For large or non-JSON downloads (a CSV report, a
    16 MB XML file), where the marker is what the parser will look for."""

    def check(body: bytes) -> None:
        if not all(marker in body for marker in markers):
            raise BodyError("the document does not have the expected content")

    return check
