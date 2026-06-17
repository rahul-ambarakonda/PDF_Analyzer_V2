"""Rendered-region comparison — the non-negotiable core (SPEC §3).

"The rendered glyph is ground truth; the extracted text string is only a hint."

A text mismatch escalates to a class-5 (font/glyph corruption) defect *only when the
rendered region also differs*. This module clip-renders a bbox from each PDF, aligns
them to a common shape, and returns ``rendered_diff_score = 1 - SSIM`` in [0, 1]:

  * score <  pixel_diff_threshold  -> regions render the same -> encoding/ToUnicode
                                       artifact -> NOT a defect (suppress).
  * score >= pixel_diff_threshold  -> regions render differently -> real defect (flag).

A string-only comparison is explicitly forbidden as the sole test for class 5.
"""

from __future__ import annotations

import fitz
import numpy as np
from skimage.metrics import structural_similarity
from skimage.transform import resize

from .config import Config

BBox = tuple[float, float, float, float]


class RenderComparer:
    def __init__(self, config: Config):
        self.config = config
        self.dpi = config.render_dpi

    def render_clip(self, page: fitz.Page, bbox: BBox, pad_pts: float = 1.0) -> np.ndarray:
        """Render a padded bbox region to a grayscale uint8 array."""
        x0, y0, x1, y1 = bbox
        clip = fitz.Rect(x0 - pad_pts, y0 - pad_pts, x1 + pad_pts, y1 + pad_pts)
        clip = clip & page.rect  # keep inside the page
        if clip.is_empty or clip.width < 1 or clip.height < 1:
            return np.full((2, 2), 255, dtype=np.uint8)
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csGRAY, alpha=False)
        if pix.width == 0 or pix.height == 0:
            return np.full((2, 2), 255, dtype=np.uint8)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)

    def diff_score(
        self,
        ref_page: fitz.Page,
        ref_bbox: BBox,
        cand_page: fitz.Page,
        cand_bbox: BBox,
    ) -> float:
        """Return 1 - SSIM between the two rendered regions, in [0, 1]."""
        a = self.render_clip(ref_page, ref_bbox)
        b = self.render_clip(cand_page, cand_bbox)
        return _region_diff(a, b)

    def is_different(self, score: float) -> bool:
        return score >= self.config.pixel_diff_threshold


def _region_diff(a: np.ndarray, b: np.ndarray) -> float:
    """1 - SSIM after resizing both regions to a shared shape. Robust to tiny clips."""
    h = max(int(a.shape[0]), int(b.shape[0]), 8)
    w = max(int(a.shape[1]), int(b.shape[1]), 8)
    af = _to_shape(a, h, w)
    bf = _to_shape(b, h, w)

    # SSIM needs an odd window <= the smaller side; fall back to mean abs diff if too small.
    win = min(7, h if h % 2 == 1 else h - 1, w if w % 2 == 1 else w - 1)
    if win < 3:
        return float(np.clip(np.mean(np.abs(af - bf)), 0.0, 1.0))

    ssim = structural_similarity(af, bf, win_size=win, data_range=1.0)
    return float(np.clip(1.0 - ssim, 0.0, 1.0))


def _to_shape(img: np.ndarray, h: int, w: int) -> np.ndarray:
    """Resize to (h, w) float32 in [0, 1]."""
    f = img.astype(np.float32) / 255.0
    if f.shape == (h, w):
        return f
    return resize(f, (h, w), order=1, mode="edge", anti_aliasing=True).astype(np.float32)
