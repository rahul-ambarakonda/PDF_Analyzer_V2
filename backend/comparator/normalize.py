"""String normalization & equivalence (SPEC §4).

Known CAD symbol/format equivalences are treated as equal at the *string* layer so they
never become false-positive defects. All equivalence data comes from config, never code.
"""

from __future__ import annotations

import re

from .config import Config

_TRAILING_ZERO = re.compile(r"(\d+\.\d*?)0+\b")
_BARE_DOT = re.compile(r"(\d+)\.(?=\D|$)")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


class Normalizer:
    """Normalizes text per the configured equivalences and format rules."""

    def __init__(self, config: Config):
        self.config = config
        # Build longest-first replacement pairs (member -> canonical = group[0]).
        pairs: list[tuple[str, str]] = []
        for group in config.symbol_equivalences:
            if not group:
                continue
            canonical = group[0]
            for member in group[1:]:
                if member and member != canonical:
                    pairs.append((member, canonical))
        # Replace longer members first so multi-char tokens win over single chars.
        self._pairs = sorted(pairs, key=lambda p: len(p[0]), reverse=True)

    def normalize(self, text: str) -> str:
        s = text
        if self.config.collapse_whitespace:
            s = " ".join(s.split())
        if self.config.case_insensitive:
            s = s.upper()
        if self.config.decimal_separator_equiv:
            s = _DECIMAL_COMMA.sub(".", s)
        if self.config.strip_trailing_zeros:
            s = _TRAILING_ZERO.sub(r"\1", s)
            s = _BARE_DOT.sub(r"\1", s)  # "1." -> "1"
        for member, canonical in self._pairs:
            if member in s:
                s = s.replace(member, canonical)
        return s

    def equal(self, a: str, b: str) -> bool:
        return self.normalize(a) == self.normalize(b)

    def edit_distance_norm(self, a: str, b: str) -> float:
        """Levenshtein distance between normalized strings, scaled to [0, 1]."""
        na, nb = self.normalize(a), self.normalize(b)
        if na == nb:
            return 0.0
        d = _levenshtein(na, nb)
        return d / max(len(na), len(nb), 1)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]
