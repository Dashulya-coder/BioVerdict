"""Cutting a long source text into records a model can quote from."""

from __future__ import annotations

import re

CHUNK_CHARS = 6000  # of text per record
_SENTENCE_END = re.compile(r"(?<=[.;]) ")


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """The text in pieces of at most `size` characters, cut between sentences.

    Runs of whitespace become one space first; apart from that no character is lost, added or
    changed, and the pieces joined by a space give the text back. A sentence longer than `size`
    is cut by length.
    """
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(" ".join(text.split())):
        while len(sentence) > size:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:size])
            sentence = sentence[size:]
        if current and len(current) + 1 + len(sentence) > size:
            pieces.append(current)
            current = sentence
        elif sentence:
            current = f"{current} {sentence}" if current else sentence
    if current:
        pieces.append(current)
    return pieces
