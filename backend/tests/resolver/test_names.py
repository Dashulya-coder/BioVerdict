import pytest

from bioverdict.resolver.names import (
    Candidate,
    MatchKind,
    choose,
    match_kind,
    normalize,
    rank_candidates,
    strip_form,
)

# Names and synonyms exactly as Open Targets lists them.
KT474 = Candidate("CHEMBL5569030", "KT-474", ("Kt-474", "SAR-444656", "SAR444656"))
HRO761 = Candidate("CHEMBL6068555", "HRO-761", ("HRO-761", "HRO761", "Hro761"))
SONELOKIMAB = Candidate("CHEMBL4298023", "M-1095", ("ALX-0761", "M-1095", "Sonelokimab"))
NAVENIBART = Candidate("CHEMBL6068148", "NAVENIBART", ("Navenibart", "Star-0215"))
DIVARASIB = Candidate("CHEMBL5095236", "DIVARASIB", ("Divarasib", "GDC-6036", "RG6330"))
DIVARASIB_ADIPATE = Candidate("CHEMBL5314604", "DIVARASIB ADIPATE", (), parent_id="CHEMBL5095236")
OBUDANERSEN = Candidate(
    "CHEMBL6068484", "OBUDANERSEN", ("ION-582 FREE ACID", "ION582 free acid", "Obudanersen")
)
OBUDANERSEN_SODIUM = Candidate("CHEMBL6068612", "OBUDANERSEN SODIUM", (), parent_id="CHEMBL6068484")
RMC_5552 = Candidate("CHEMBL5314926", "RMC-5552")


def test_normalize_ignores_case_and_punctuation() -> None:
    assert normalize("HRO-761") == normalize("hro761") == "hro761"
    assert normalize("  Star 0215 ") == "star0215"
    assert normalize("---") == ""


def test_strip_form_removes_salt_words_but_never_the_whole_name() -> None:
    assert strip_form("obudanersensodium") == "obudanersen"
    assert strip_form("ion582freeacid") == "ion582"
    assert strip_form("sodium") == "sodium"


@pytest.mark.parametrize(
    "query, drug, expected",
    [
        ("divarasib", DIVARASIB, MatchKind.NAME),
        ("HRO761", HRO761, MatchKind.NAME),  # the database writes it HRO-761
        ("SAR444656", KT474, MatchKind.SYNONYM),
        ("GDC-6036", DIVARASIB, MatchKind.SYNONYM),
        ("STAR-0215", NAVENIBART, MatchKind.SYNONYM),
        ("sonelokimab", SONELOKIMAB, MatchKind.SYNONYM),
        ("divarasib adipate", DIVARASIB_ADIPATE, MatchKind.NAME),
        ("divarasib", DIVARASIB_ADIPATE, MatchKind.FORM),
        ("ION582", OBUDANERSEN, MatchKind.FORM),
    ],
)
def test_how_a_query_matches_a_drug(query: str, drug: Candidate, expected: MatchKind) -> None:
    assert match_kind(query, drug.name, drug.synonyms) is expected


@pytest.mark.parametrize(
    "query, drug",
    [
        ("RMC-9805", RMC_5552),  # a search for it also returns this other molecule
        ("elisrasib", Candidate("CHEMBL0", "ELIRONRASIB")),
        ("divara", DIVARASIB),
        ("", DIVARASIB),
        ("   ", DIVARASIB),
    ],
)
def test_a_similar_name_is_not_a_match(query: str, drug: Candidate) -> None:
    assert match_kind(query, drug.name, drug.synonyms) is None


def test_the_parent_wins_over_its_salt_for_the_parents_name() -> None:
    ranked = rank_candidates("divarasib", [DIVARASIB_ADIPATE, DIVARASIB])
    assert [r.kind for r in ranked] == [MatchKind.NAME, MatchKind.FORM]
    assert choose(ranked) == DIVARASIB


def test_a_salt_name_chooses_the_salt_record() -> None:
    assert choose(rank_candidates("divarasib adipate", [DIVARASIB, DIVARASIB_ADIPATE])) == (
        DIVARASIB_ADIPATE
    )


def test_a_form_match_of_a_parent_and_its_salt_resolves_to_the_parent() -> None:
    ranked = rank_candidates("ION582", [OBUDANERSEN_SODIUM, OBUDANERSEN])
    assert {r.kind for r in ranked} == {MatchKind.FORM}
    assert choose(ranked) == OBUDANERSEN


def test_unrelated_drugs_at_the_same_rank_are_ambiguous() -> None:
    a = Candidate("CHEMBL1", "ALPHA", ("X-1",))
    b = Candidate("CHEMBL2", "BETA", ("X1",))
    assert choose(rank_candidates("x1", [a, b])) is None


def test_nothing_matching_chooses_nothing() -> None:
    assert choose(rank_candidates("RMC-9805", [RMC_5552, KT474])) is None
    assert choose([]) is None
