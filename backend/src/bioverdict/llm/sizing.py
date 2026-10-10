"""How the gateway counts the size of a request.

Measured on 2026-10-10: the limit applies to the text as it travels, JSON-encoded and in UTF-8
bytes, not to the number of characters. A quotation mark or a line break counts 2 (`\\"`, `\\n`),
an accented letter 2, a symbol such as the 'greater than or equal' sign 3. Biomedical text is full
of them, so a prompt of 15,000 characters can be over a limit of 16,180.
"""

from __future__ import annotations

import json


def wire_len(text: str) -> int:
    """The size of `text` as the gateway counts it."""
    return len(json.dumps(text, ensure_ascii=False)[1:-1].encode("utf-8"))
