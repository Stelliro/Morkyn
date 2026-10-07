"""
Out-of-script guard for an English world (playtest #49).

Qwen3 language-mixes at low probability: an English phrase finishes in Chinese
("the stale, warm空气"), and the token ships in the draft, the writer, setup
descriptions, and is then fed back into later prompts.

Two layers, both structural, neither a content judgement:

* ``piece_is_out_of_script`` classifies one vocabulary piece (raw bytes) so the
  in-process provider can mask those tokens at sample time (app/mle.py). The
  model never sees a choice it could take.
* ``repair_out_of_script`` removes whatever still arrives from a provider that
  cannot be masked (an HTTP server, an API). A tiny map turns the runs actually
  seen live into their English word; any other run is dropped and the spacing
  closed up. Each hit is returned so the caller can trace it.

Covered scripts: CJK symbols and punctuation, Hiragana, Katakana, CJK unified
ideographs (and extension A), Hangul, CJK compatibility ideographs, and the
halfwidth/fullwidth forms block. Latin, Greek, Cyrillic and typographic
punctuation (em dash, curly quotes, ellipsis) are untouched.
"""
from __future__ import annotations

import os
import re
from typing import Any

# U+3000-U+30FF (CJK punctuation, kana), U+3400-U+4DBF, U+4E00-U+9FFF, U+AC00-U+D7AF,
# U+F900-U+FAFF, U+FF00-U+FFEF.
_RUN_RE = re.compile(
    "[　-ヿ㄀-ㇿ㐀-䶿一-鿿가-힯豈-﫿＀-￯]+"
)

# Runs seen in live output, and the English word the sentence was reaching for.
# Anything not listed is dropped, never guessed.
_KNOWN_RUNS = {
    "空气": "air",  # 空气
    "罩": "cover",  # 罩
}

# UTF-8 lead bytes of U+3000..U+DFFF (E3..ED). A byte-level BPE vocab can hold a
# Han character split over several tokens; the piece carrying its lead byte is
# the one the mask has to remove. Continuation bytes (80..BF) are shared with
# every other non-ASCII character and are left alone.
_LEAD_BYTES = frozenset(range(0xE3, 0xEE))
# EF lead byte covers U+F000..U+FFFF; only the compatibility-ideograph and
# fullwidth parts of it are out of script, so EF pieces are judged by text.


def guard_enabled() -> bool:
    return str(os.getenv("AI_RPG_SCRIPT_GUARD", "1")).strip().lower() not in {"0", "false", "no", "off"}


def piece_is_out_of_script(raw: bytes) -> bool:
    """True when this vocabulary piece writes (or starts writing) a covered character."""
    data = bytes(raw or b"")
    if not data:
        return False
    if any(byte in _LEAD_BYTES for byte in data):
        return True
    text = data.decode("utf-8", errors="ignore")
    return bool(text and _RUN_RE.search(text))


def repair_out_of_script(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Replace or drop out-of-script runs. Returns the text and one record per run."""
    if not text or not isinstance(text, str) or not _RUN_RE.search(text):
        return text, []
    hits: list[dict[str, Any]] = []

    def _swap(match: re.Match[str]) -> str:
        run = match.group(0)
        word = _KNOWN_RUNS.get(run, "")
        hits.append({"run": run, "replacement": word, "at": match.start()})
        if not word:
            return "\u0000"
        before = text[match.start() - 1] if match.start() > 0 else ""
        after = text[match.end()] if match.end() < len(text) else ""
        lead = " " if before and (before.isalnum() or before in ",;:") else ""
        trail = " " if after and after.isalnum() else ""
        return f"{lead}{word}{trail}"

    out = _RUN_RE.sub(_swap, text)
    if "\u0000" in out:
        # A dropped run: close the gap it leaves ("the \0 voices" -> "the voices",
        # "warm\0." -> "warm.").
        out = re.sub(r"[ \t]*\u0000+[ \t]*(?=[.,;:!?\"'”’)\]}])", "", out)
        out = re.sub(r"[ \t]+\u0000+[ \t]+", " ", out)
        out = out.replace("\u0000", "")
    return out, hits
