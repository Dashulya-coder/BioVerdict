import pytest

from bioverdict.connectors.sponsors import sponsor_group


@pytest.mark.parametrize(
    "name",
    [
        "Hoffmann-La Roche",
        "F. Hoffmann-La Roche Ltd",
        "Genentech, Inc.",
        "Roche",
        "Chugai Pharmaceutical Co., Ltd.",
    ],
)
def test_the_roche_family_is_one_group(name: str) -> None:
    assert sponsor_group(name) == "sponsor:Roche"


@pytest.mark.parametrize("name", ["Eli Lilly and Company", "Lilly", "ELI LILLY"])
def test_lilly_spellings_are_one_group(name: str) -> None:
    assert sponsor_group(name) == "sponsor:Eli Lilly"


def test_unknown_sponsors_lose_only_the_legal_form() -> None:
    assert sponsor_group("Verastem, Inc.") == "sponsor:Verastem"
    assert sponsor_group("Mirati Therapeutics Inc.") == "sponsor:Mirati Therapeutics"
    assert sponsor_group("M.D. Anderson Cancer Center") == "sponsor:M D Anderson Cancer Center"


def test_distinct_sponsors_stay_distinct() -> None:
    assert sponsor_group("Amgen") != sponsor_group("Mirati Therapeutics Inc.")


@pytest.mark.parametrize("name", [None, "", "   ", "Inc."])
def test_a_missing_name_is_unknown(name: str | None) -> None:
    assert sponsor_group(name) == "sponsor:unknown"


@pytest.mark.parametrize("name", ["Genentech, Inc.", "Amgen", "Verastem, Inc."])
def test_the_label_is_stable_when_applied_again(name: str) -> None:
    label = sponsor_group(name).removeprefix("sponsor:")
    assert sponsor_group(label) == sponsor_group(name)
