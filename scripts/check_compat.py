"""Smoke test: do BioVerdict's dependencies import and work on THIS interpreter?

Run:  uv run python scripts/check_compat.py
Exit code 0 = all checks passed. No network calls, no real API keys.
"""
import importlib
import importlib.metadata as md
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

PACKAGES = [  # (import name, distribution name)
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("pydantic_core", "pydantic-core"),
    ("httpx", "httpx"),
    ("tenacity", "tenacity"),
    ("numpy", "numpy"),
    ("langgraph", "langgraph"),
    ("anthropic", "anthropic"),
    ("openai", "openai"),
    ("google.genai", "google-genai"),
]

results: list[tuple[str, bool, str]] = []


def check(name):
    def deco(fn):
        try:
            detail = fn() or ""
            results.append((name, True, str(detail)))
        except Exception as exc:  # noqa: BLE001
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            traceback.print_exc()
        return fn
    return deco


for mod, dist in PACKAGES:
    @check(f"import {mod}")
    def _(mod=mod, dist=dist):
        importlib.import_module(mod)
        return md.version(dist)


@check("pydantic: validate and JSON schema")
def _():
    from pydantic import BaseModel, Field

    class Claim(BaseModel):
        id: str
        text: str
        confidence: float = Field(ge=0, le=1)

    c = Claim.model_validate({"id": "C-1", "text": "x", "confidence": 0.5})
    assert "confidence" in Claim.model_json_schema()["properties"]
    return c.model_dump_json()


@check("langgraph: tiny DAG with parallel nodes")
def _():
    import operator
    from typing import Annotated, TypedDict

    from langgraph.graph import END, START, StateGraph

    class S(TypedDict):
        items: Annotated[list, operator.add]

    g = StateGraph(S)
    g.add_node("a", lambda s: {"items": ["a"]})
    g.add_node("b", lambda s: {"items": ["b"]})
    g.add_edge(START, "a")
    g.add_edge(START, "b")
    g.add_edge("a", END)
    g.add_edge("b", END)
    out = g.compile().invoke({"items": []})
    assert sorted(out["items"]) == ["a", "b"]
    return sorted(out["items"])


@check("sqlite3: WAL mode")
def _():
    with tempfile.TemporaryDirectory() as d:
        con = sqlite3.connect(Path(d) / "t.sqlite")
        mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        con.execute("CREATE TABLE t(x)")
        con.execute("INSERT INTO t VALUES (1)")
        con.commit()
        con.close()
    return f"sqlite {sqlite3.sqlite_version}, journal_mode={mode}"


@check("fastapi: app + TestClient")
def _():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    assert TestClient(app).get("/ping").json() == {"ok": True}


@check("SDK clients construct offline (dummy keys)")
def _():
    import anthropic
    import openai
    from google import genai

    anthropic.Anthropic(api_key="x")
    openai.OpenAI(api_key="x")
    genai.Client(api_key="x")


@check("numpy: basic Monte Carlo draw")
def _():
    import numpy as np

    rng = np.random.default_rng(0)
    x = rng.lognormal(0, 1, 10_000)
    return f"P10/P50/P90 = {np.percentile(x, [10, 50, 90]).round(2).tolist()}"


print(f"Python {sys.version.split()[0]} on {sys.platform}\n")
width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
