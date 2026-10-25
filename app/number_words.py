"""The number words the money readers know (a leaf: no game imports).

Shared by app/prose_state.py (the prose readers) and app/currency.py (the
coin grammar), so the two read "forty-six gold" alike and neither imports the
other at load (m1, 2026-10-25: prose_state reads every coin of the world's set
through currency).
"""
from __future__ import annotations

import re

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "a hundred": 100, "hundred": 100,
    # "three silver, two copper, and a single gold piece" dropped into the palm
    # read as no stated sum, and GOLD moderate rolled 31 (8B run 150, T52).
    "a single": 1, "single": 1, "a lone": 1, "lone": 1,
}
# "forty-six gold" read as "six gold" and the purse grew by a rolled gain
# while the player paid (8B run 146, T73): tens and units together are one number.
_COMPOUND_AMOUNT = (
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[-\s]+(?:one|two|three|four|five|six|seven|eight|nine)"
)


def _number(token: str | None) -> int | None:
    text = " ".join(str(token or "").lower().split())
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _NUMBER_WORDS:
        return _NUMBER_WORDS[text]
    parts = [p for p in re.split(r"[-\s]+", text) if p]
    if len(parts) == 2 and _NUMBER_WORDS.get(parts[0], 0) in {20, 30, 40, 50, 60, 70, 80, 90} and 1 <= _NUMBER_WORDS.get(parts[1], 0) <= 9:
        return _NUMBER_WORDS[parts[0]] + _NUMBER_WORDS[parts[1]]
    return None
