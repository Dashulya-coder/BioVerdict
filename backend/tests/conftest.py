"""Tests must not depend on the keys or settings of whoever runs them."""

import pytest

# A developer with a key in the shell must not change what a test sees; a test that needs one
# sets it itself.
MODEL_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "TEAM_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "LLM_PROVIDER",
    "LLM_BASE_URL",
)


@pytest.fixture(autouse=True)
def _no_model_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in MODEL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
