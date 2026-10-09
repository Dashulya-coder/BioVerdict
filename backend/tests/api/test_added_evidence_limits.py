import pytest
from pydantic import ValidationError

from bioverdict.api.schemas import MAX_ADDED_TEXT, AddedEvidence, AddEvidenceRequest


def doc(**kw) -> dict:
    base = {
        "text": "A verbatim excerpt of at least twenty characters.",
        "url": "https://example.org/paper",
        "source": "Journal",
        "source_kind": "peer_reviewed",
        "level": "human_interventional",
    }
    return base | kw


def test_a_document_of_the_largest_size_is_accepted() -> None:
    AddedEvidence.model_validate(doc(text="x" * MAX_ADDED_TEXT))


@pytest.mark.parametrize(
    "bad",
    [
        {"text": "x" * (MAX_ADDED_TEXT + 1)},
        {"url": "https://example.org/" + "a" * 500},
        {"source": "S" * 201},
        {"text": "too short"},
    ],
)
def test_an_oversized_or_undersized_document_is_refused(bad: dict) -> None:
    with pytest.raises(ValidationError):
        AddedEvidence.model_validate(doc(**bad))


def test_ten_documents_stay_inside_a_known_total() -> None:
    request = AddEvidenceRequest.model_validate(
        {"evidence": [doc(text="x" * MAX_ADDED_TEXT) for _ in range(10)]}
    )
    assert sum(len(e.text) for e in request.evidence) <= 10 * MAX_ADDED_TEXT
    with pytest.raises(ValidationError):
        AddEvidenceRequest.model_validate({"evidence": [doc()] * 11})
