"""Check that an evidence quote really occurs in the source text.

A statement whose quote cannot be found is treated as ungrounded: the model may have
invented or paraphrased it. Matching tolerates case, whitespace, quote/dash variants and
small differences (e.g. PDF hyphenation), and maps the match back to source offsets.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", "­": None,
})


@dataclass(frozen=True)
class QuoteMatch:
    start: int
    end: int
    score: float


def _normalize(text: str) -> tuple[str, list[int]]:
    """Lowercase, unify punctuation, collapse whitespace. Returns text + map to original index."""
    out, idx, prev_space = [], [], False
    for i, ch in enumerate(text):
        ch = ch.translate(_TRANSLATE).lower()
        if not ch:
            continue
        if ch.isspace():
            if prev_space or not out:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch)
        idx.append(i)
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def locate_quote(quote: str, text: str, threshold: float = 0.9) -> QuoteMatch | None:
    q, _ = _normalize(quote)
    t, tmap = _normalize(text)
    if not q or not t:
        return None
    pos = t.find(q)
    if pos >= 0:
        return QuoteMatch(tmap[pos], tmap[pos + len(q) - 1] + 1, 1.0)
    if len(q) > len(t) * 1.2:
        return None
    # Fuzzy: compare the quote with windows of the same length starting at word boundaries.
    best, best_pos, n = 0.0, -1, len(q)
    starts = [0] + [i + 1 for i, c in enumerate(t) if c == " "]
    for s in starts:
        window = t[s:s + n]
        m = SequenceMatcher(None, q, window, autojunk=False)
        if m.real_quick_ratio() < threshold or m.quick_ratio() < threshold:
            continue
        r = m.ratio()
        if r > best:
            best, best_pos = r, s
    if best < threshold:
        return None
    end = min(best_pos + n, len(t)) - 1
    return QuoteMatch(tmap[best_pos], tmap[end] + 1, round(best, 4))
