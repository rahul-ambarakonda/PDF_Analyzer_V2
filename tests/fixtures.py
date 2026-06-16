"""Synthetic fixture generator (SPEC §9).

Builds a clean vector drawing PDF entirely in code (no committed source PDF needed), then
produces a reference + candidate pair for each defect class with known ground-truth labels.
The headline case is ``encoding_only``: the candidate renders identically to the reference but
extracts a wrong string (ToUnicode surgery via pikepdf) — it must yield ZERO defects.

Each scenario returns (ref_path, cand_path, expected) where ``expected`` is the list of defect
classes that should be reported (empty list = a must-not-flag case).
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz
import pikepdf

SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"

W, H = 1190.0, 842.0          # A3 landscape, points
INSET = 36.0
NCOLS, NROWS = 8, 6
TARGET_TEXT = "1/2"           # rendered on SERIF so its ToUnicode can be edited in isolation


def fonts_available() -> bool:
    return Path(SANS).exists() and Path(SERIF).exists()


# --- grid geometry -------------------------------------------------------- #
def _col_x(c: int) -> float:
    fw = (W - 2 * INSET) / NCOLS
    return INSET + (c + 0.5) * fw


def _row_y(r: int) -> float:
    fh = (H - 2 * INSET) / NROWS
    return INSET + (r + 0.5) * fh


def zone_of(c: int, r: int) -> str:
    return f"{chr(ord('A') + r)}{c + 1}"


# --- body content (reference truth) --------------------------------------- #
# Each: id -> (text, col, row, font, size)
BODY = {
    "dim":     ("12.50", 1, 2, "S", 13),
    "rad":     ("R5.00", 4, 1, "S", 13),
    "target":  (TARGET_TEXT, 3, 3, "T", 16),   # serif
    "dia":     ("Ø10", 5, 4, "S", 13),     # Ø10
    "section": ("SECTION A-A", 3, 5, "S", 12),
}
# Annotation cluster (two stacked runs) used for missing_annotation.
CLUSTER = [("NOTE 1", 1, 4, -7), ("SEE DETAIL", 1, 4, 7)]
TITLE = ("DWG NO 123", 1040.0, 782.0)


def _insert(page, text, x, y, font_key, size):
    file = SERIF if font_key == "T" else SANS
    name = "T0" if font_key == "T" else "S0"
    page.insert_text((x, y), text, fontname=name, fontfile=file, fontsize=size)


def _draw_border(page, tx=0.0, ty=0.0):
    page.draw_rect(fitz.Rect(INSET + tx, INSET + ty, W - INSET + tx, H - INSET + ty), width=1.0)
    for c in range(NCOLS):
        x = _col_x(c) + tx
        _insert(page, str(c + 1), x, INSET - 8 + ty, "S", 8)        # top
        _insert(page, str(c + 1), x, H - INSET + 14 + ty, "S", 8)   # bottom
    for r in range(NROWS):
        y = _row_y(r) + ty
        _insert(page, chr(ord("A") + r), INSET - 26 + tx, y, "S", 8)   # left
        _insert(page, chr(ord("A") + r), W - INSET + 6 + tx, y, "S", 8)  # right


def build_drawing(path: str, *, omit: set[str] = frozenset(),
                  shift: dict[str, tuple[float, float]] | None = None,
                  corrupt_target: bool = False, extra_overlap: bool = False,
                  translate: tuple[float, float] = (0.0, 0.0),
                  drop_cluster: bool = False) -> None:
    shift = shift or {}
    tx, ty = translate
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    _draw_border(page, tx, ty)

    for key, (text, c, r, font, size) in BODY.items():
        if key in omit:
            continue
        if key == "target" and corrupt_target:
            text = "1#8"  # renders different glyphs -> real corruption
        dx, dy = shift.get(key, (0.0, 0.0))
        _insert(page, text, _col_x(c) - 24 + tx + dx, _row_y(r) + size * 0.35 + ty + dy, font, size)

    if not drop_cluster:
        for text, c, r, off in CLUSTER:
            _insert(page, text, _col_x(c) - 24 + tx, _row_y(r) + off + ty, "S", 11)

    if extra_overlap:
        text, c, r, _, size = BODY["dia"]
        _insert(page, "EXTRA", _col_x(c) - 20 + tx, _row_y(r) + 2 + ty, "S", 13)

    _insert(page, TITLE[0], TITLE[1] + tx, TITLE[2] + ty, "S", 12)
    doc.save(path)
    doc.close()


# --- multi-view sheet (independently-placed drawing views) ---------------- #
# Two drawing views on one sheet, each with its own block of unique labels. The candidate may
# relocate an entire view (different layout on the Creo sheet) and/or perturb a single label
# inside a view. A relocated view must be absorbed by per-view registration; a single label
# moved relative to its view must still be caught.
VIEW_A = [("A12.50", 120.0, 200.0), ("AR8.00", 120.0, 260.0),
          ("AOD25", 220.0, 200.0), ("ASLOT", 220.0, 260.0)]
VIEW_B = [("B7.25", 760.0, 200.0), ("BR3.50", 760.0, 260.0),
          ("BTHRU", 860.0, 200.0), ("BCBORE", 860.0, 260.0)]


def build_multiview(path: str, *, view_b_shift: tuple[float, float] = (0.0, 0.0),
                    omit: set[str] = frozenset(),
                    run_shift: dict[str, tuple[float, float]] | None = None) -> None:
    """Sheet with view A (left) and view B (right).

    ``view_b_shift`` relocates the whole of view B (a legitimate layout difference).
    ``omit`` drops a label by text; ``run_shift`` nudges a single label relative to its view.
    """
    run_shift = run_shift or {}
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    for text, x, y in VIEW_A:
        if text in omit:
            continue
        dx, dy = run_shift.get(text, (0.0, 0.0))
        _insert(page, text, x + dx, y + dy, "S", 12)
    bx, by = view_b_shift
    for text, x, y in VIEW_B:
        if text in omit:
            continue
        dx, dy = run_shift.get(text, (0.0, 0.0))
        _insert(page, text, x + bx + dx, y + by + dy, "S", 12)
    doc.save(path)
    doc.close()


# --- encoding-only surgery ------------------------------------------------ #
def _reverse_cmap(data: str) -> dict[int, int]:
    rev: dict[int, int] = {}
    for lo, hi, us in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", data):
        lo, hi, us = int(lo, 16), int(hi, 16), int(us, 16)
        for cid in range(lo, hi + 1):
            rev.setdefault(us + (cid - lo), cid)
    return rev


def break_tounicode(path: str, remap: dict[str, str]) -> None:
    """Rewrite the SERIF font's ToUnicode so target chars extract wrong, rendering unchanged.

    ``remap`` maps source char -> wrong char (e.g. {"/": "#", "2": "8"}).
    """
    pdf = pikepdf.open(path, allow_overwriting_input=True)
    target = next(f for pg in pdf.pages
                  for f in pg["/Resources"]["/Font"].values()
                  if "Serif" in str(f.get("/BaseFont")))
    data = target["/ToUnicode"].read_bytes().decode("latin-1")
    rev = _reverse_cmap(data)
    lines = []
    for src, dst in remap.items():
        cid = rev[ord(src)]
        lines.append(f"<{cid:04x}> <{ord(dst):04x}>")
    override = f"{len(lines)} beginbfchar\n" + "\n".join(lines) + "\nendbfchar\n"
    target["/ToUnicode"] = pdf.make_stream(data.replace("endcmap", override + "endcmap").encode("latin-1"))
    pdf.save(path)
    pdf.close()


# --- scenarios ------------------------------------------------------------ #
def make_scenarios(tmp: Path) -> dict[str, dict]:
    """Build all reference/candidate pairs under ``tmp``; return scenario metadata."""
    ref = str(tmp / "reference.pdf")
    build_drawing(ref)
    scen: dict[str, dict] = {}

    def add(name, build_fn, expected, expected_zone=None, ref_text=None):
        cand = str(tmp / f"cand_{name}.pdf")
        build_fn(cand)
        scen[name] = {"ref": ref, "cand": cand, "expected": expected,
                      "expected_zone": expected_zone, "ref_text": ref_text}

    add("identical", lambda p: build_drawing(p), [])
    add("missing_text", lambda p: build_drawing(p, omit={"rad"}),
        ["missing_text"], expected_zone=zone_of(4, 1), ref_text="R5.00")
    add("missing_annotation", lambda p: build_drawing(p, drop_cluster=True),
        ["missing_annotation"], expected_zone=zone_of(1, 4))
    add("misplacement", lambda p: build_drawing(p, shift={"dim": (45.0, 0.0)}),
        ["text_misplacement"], ref_text="12.50")
    add("overlap", lambda p: build_drawing(p, extra_overlap=True), ["text_overlap"])
    add("corruption", lambda p: build_drawing(p, corrupt_target=True),
        ["font_glyph_corruption"], expected_zone=zone_of(3, 3), ref_text=TARGET_TEXT)
    add("offset", lambda p: build_drawing(p, translate=(25.0, 18.0)), [])

    def build_encoding(p):
        build_drawing(p)  # identical render to reference
        break_tounicode(p, {"/": "#", "2": "8"})  # extracts "1#8", renders "1/2"
    add("encoding_only", build_encoding, [])

    return scen
