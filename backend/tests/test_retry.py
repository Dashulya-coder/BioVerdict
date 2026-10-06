import httpx
import pytest

from bioverdict.connectors.retry import MAX_RETRY_AFTER_S, is_transient, retry_after_seconds


def status_error(status: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.org")
    response = httpx.Response(status, headers=headers, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_statuses(status: int) -> None:
    assert is_transient(status_error(status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_transient(status: int) -> None:
    assert not is_transient(status_error(status))


def test_network_errors_are_transient() -> None:
    assert is_transient(httpx.ConnectError("boom"))
    assert is_transient(httpx.ReadTimeout("slow"))


def test_unrelated_errors_are_not_transient() -> None:
    assert not is_transient(ValueError("bug"))


def test_retry_after_is_read_and_capped() -> None:
    assert retry_after_seconds(status_error(429, {"Retry-After": "7"})) == 7.0
    assert retry_after_seconds(status_error(429, {"Retry-After": "9999"})) == MAX_RETRY_AFTER_S


def test_retry_after_ignores_missing_or_date_form() -> None:
    assert retry_after_seconds(status_error(429)) is None
    date = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    assert retry_after_seconds(status_error(503, date)) is None
    assert retry_after_seconds(ValueError("x")) is None
