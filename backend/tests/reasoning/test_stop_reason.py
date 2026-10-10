import pytest

from bioverdict.reasoning.stop_reason import (
    StopReason,
    classify_stop_reason,
    overall_status,
    why_stopped,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # the two real reasons recorded from ClinicalTrials.gov
        ("Futility", StopReason.EFFICACY),
        (
            "Trial terminated due to business decision, not based on any safety or efficacy concerns.",
            StopReason.BUSINESS,
        ),
        ("Lack of efficacy at the interim analysis", StopReason.EFFICACY),
        ("The study did not meet its primary endpoint", StopReason.EFFICACY),
        ("Sponsor decision after a clinical hold for liver injury", StopReason.MIXED),
        ("Unacceptable toxicity and two treatment-related deaths", StopReason.SAFETY),
        ("Slow enrollment", StopReason.BUSINESS),
        ("Funding withdrawn due to COVID-19", StopReason.BUSINESS),
        ("Business decision following futility analysis", StopReason.MIXED),
        ("Study design was revised", StopReason.OTHER),
        # how papers word a failed active-comparator trial (PMID 39307151, PMID 40202623)
        (
            "The efficacy of evobrutinib was not superior to that of teriflunomide.",
            StopReason.EFFICACY,
        ),
        ("The primary endpoint was not met.", StopReason.EFFICACY),
        ("PERSEUS missed its primary endpoint.", StopReason.EFFICACY),
        # a noninferiority trial is meant not to be superior
        ("Fenebrutinib was noninferior to ocrelizumab but not superior to it.", StopReason.OTHER),
        # a lifted hold is no safety action in force
        ("The FDA lifted the partial clinical hold on the program.", StopReason.OTHER),
        ("", StopReason.UNKNOWN),
        (None, StopReason.UNKNOWN),
    ],
)
def test_stop_reasons(text: str | None, expected: StopReason) -> None:
    assert classify_stop_reason(text) is expected


def test_a_negated_scientific_word_does_not_count() -> None:
    assert classify_stop_reason("Stopped, unrelated to safety") is StopReason.OTHER
    assert classify_stop_reason("No safety concerns; stopped for strategic reasons") is (
        StopReason.BUSINESS
    )


def test_fields_are_read_from_a_registry_status_record_only() -> None:
    record = '{"overallStatus": "TERMINATED", "whyStopped": "Futility"}'
    assert why_stopped(record) == "Futility" and overall_status(record) == "TERMINATED"
    assert why_stopped("Plain text, not JSON") is None and overall_status("[1, 2]") is None
    assert why_stopped('{"overallStatus": "COMPLETED"}') is None


@pytest.mark.parametrize(
    "text",
    [
        "There was no clinical hold",
        "No deaths were reported and the study was stopped",
        "The trial did not fail for futility",
    ],
)
def test_a_negated_reason_is_not_that_reason(text: str) -> None:
    assert classify_stop_reason(text) in (StopReason.OTHER, StopReason.UNKNOWN)
