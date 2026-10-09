"""Provider-neutral request and response shapes shared by the client and the adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(frozen=True)
class ProviderRequest:
    model: str  # provider-local model id, for example "claude-sonnet-5-5"
    prompt: str
    schema: type[BaseModel]
    system: str | None = None
    effort: str | None = None  # low | medium | high ...; adapters ignore what a model lacks
    temperature: float | None = None  # adapters omit it for models that reject sampling params
    max_tokens: int = 8000
    timeout_s: float = 90.0


@dataclass(frozen=True)
class ProviderResponse:
    text: str  # the JSON answer
    input_tokens: int
    output_tokens: int
    model: str  # the model that actually answered


@runtime_checkable
class Provider(Protocol):
    """One vendor. Raises the classified errors of `llm.errors`, never a vendor exception."""

    name: str

    def complete(self, request: ProviderRequest) -> ProviderResponse: ...


@runtime_checkable
class SizedProvider(Protocol):
    """An adapter whose endpoint limits the size of a request and can say how big one would be."""

    def input_chars(self, request: ProviderRequest) -> int: ...


def split_model_ref(ref: str) -> tuple[str, str]:
    """'anthropic:claude-haiku-4-5' -> ('anthropic', 'claude-haiku-4-5')."""
    provider, sep, model = ref.partition(":")
    if not sep or not provider or not model:
        raise ValueError(f"model reference must look like 'provider:model', got {ref!r}")
    return provider, model
