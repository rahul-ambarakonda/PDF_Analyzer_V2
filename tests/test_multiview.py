"""Multi-view registration: a whole drawing view placed differently on the candidate sheet
must be absorbed (matched, not flagged), while text defects *inside* a view are still caught.

This guards the per-view (multi-model) registration in ``register.py``: one global affine
would report every label in a relocated view as misplaced.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from comparator.config import Config
from comparator.detect import analyze_page
from comparator.normalize import Normalizer
from comparator.render_compare import RenderComparer
from tests import fixtures

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

pytestmark = pytest.mark.skipif(not fixtures.fonts_available(), reason="DejaVu fonts unavailable")


@pytest.fixture(scope="module")
def config() -> Config:
    return Config.load(CONFIG_PATH)


def _classes(ref: str, cand: str, config: Config) -> list[str]:
    normalizer = Normalizer(config)
    comparer = RenderComparer(config)
    ref_doc, cand_doc = fitz.open(ref), fitz.open(cand)
    try:
        defects = analyze_page(1, ref_doc[0], cand_doc[0], normalizer, comparer, config)
    finally:
        ref_doc.close()
        cand_doc.close()
    return sorted(d.defect_class for d in defects)


def test_relocated_view_is_absorbed(tmp_path, config):
    """View B moved far on the candidate sheet, otherwise identical => ZERO defects."""
    ref = str(tmp_path / "ref.pdf")
    cand = str(tmp_path / "cand.pdf")
    fixtures.build_multiview(ref)
    fixtures.build_multiview(cand, view_b_shift=(120.0, 260.0))
    assert _classes(ref, cand, config) == []


def test_missing_label_inside_relocated_view(tmp_path, config):
    """A label dropped from a view that *also* moved => exactly one missing_text."""
    ref = str(tmp_path / "ref.pdf")
    cand = str(tmp_path / "cand.pdf")
    fixtures.build_multiview(ref)
    fixtures.build_multiview(cand, view_b_shift=(120.0, 260.0), omit={"BCBORE"})
    assert _classes(ref, cand, config) == ["missing_text"]


def test_run_shifted_within_relocated_view(tmp_path, config):
    """One label nudged relative to its (also-relocated) view => text_misplacement, not absorbed."""
    ref = str(tmp_path / "ref.pdf")
    cand = str(tmp_path / "cand.pdf")
    fixtures.build_multiview(ref)
    fixtures.build_multiview(cand, view_b_shift=(120.0, 260.0), run_shift={"B7.25": (40.0, 0.0)})
    assert _classes(ref, cand, config) == ["text_misplacement"]


def test_single_global_affine_would_misfire(tmp_path, config):
    """Sanity: with multi-view disabled, a relocated view produces a flurry of false defects
    (its labels map far off => misplaced or unmatched), confirming the multi-model path is
    what suppresses them."""
    ref = str(tmp_path / "ref.pdf")
    cand = str(tmp_path / "cand.pdf")
    fixtures.build_multiview(ref)
    fixtures.build_multiview(cand, view_b_shift=(120.0, 260.0))
    cfg = Config.load(CONFIG_PATH)
    cfg.registration_multi_view = False
    legacy = _classes(ref, cand, cfg)
    assert legacy, "single global affine should false-flag the relocated view"
    assert _classes(ref, cand, config) == []  # multi-view absorbs them all
