"""Text extraction (SPEC §6 ``extract.py``).

Uses PyMuPDF ``get_text("rawdict")`` to pull text runs (spans) with font, size, flags
and bbox, rotated to user-visible orientation. Also extracts drawing line segments,
used by clustering to detect leader lines.

The extracted string is only a *hint* — the rendered glyph is ground truth (SPEC §3).
Downstream code must never treat the string as authoritative for class-5 decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz

BBox = tuple[float, float, float, float]


@dataclass
class TextRun:
    """One extracted text span in user-visible PDF points."""

    text: str
    bbox: BBox
    font: str
    size: float
    flags: int
    page: int
    origin: tuple[float, float]
    direction: tuple[float, float]
    block: int
    line: int

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _rotate_point(pt, mat: fitz.Matrix) -> tuple[float, float]:
    p = fitz.Point(pt) * mat
    return (p.x, p.y)


def extract_runs(page: fitz.Page, page_index: int) -> list[TextRun]:
    """Extract text runs from a single page, rotated to visible orientation."""
    runs: list[TextRun] = []
    rot = page.rotation_matrix
    vec = fitz.Matrix(rot.a, rot.b, rot.c, rot.d, 0, 0)  # rotation only, no translation
    data = page.get_text("rawdict")

    for b_idx, block in enumerate(data.get("blocks", [])):
        if block.get("type", 0) != 0:  # 0 == text block
            continue
        for l_idx, line in enumerate(block.get("lines", [])):
            line_dir = line.get("dir", (1.0, 0.0))
            for span in line.get("spans", []):
                text = "".join(c.get("c", "") for c in span.get("chars", []))
                text = text.strip() if text else span.get("text", "").strip()
                if not text:
                    continue
                rect = fitz.Rect(span["bbox"]) * rot
                origin = _rotate_point(span.get("origin", (rect.x0, rect.y1)), rot)
                d = _rotate_point(line_dir, vec)
                mag = (d[0] ** 2 + d[1] ** 2) ** 0.5
                direction = (d[0] / mag, d[1] / mag) if mag > 1e-9 else (1.0, 0.0)
                runs.append(TextRun(
                    text=text,
                    bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                    font=span.get("font", ""),
                    size=float(span.get("size", 0.0)),
                    flags=int(span.get("flags", 0)),
                    page=page_index,
                    origin=origin,
                    direction=direction,
                    block=b_idx,
                    line=l_idx,
                ))
    return runs


def extract_line_segments(page: fitz.Page) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Extract straight drawing segments (for leader-line detection), visible-rotated."""
    rot = page.rotation_matrix
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for d in page.get_drawings():
        for item in d.get("items", []):
            kind = item[0]
            if kind == "l":
                segments.append((_rotate_point(item[1], rot), _rotate_point(item[2], rot)))
            elif kind == "re":
                r = item[1] * rot
                corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
                for i in range(4):
                    segments.append((corners[i], corners[(i + 1) % 4]))
    return segments
