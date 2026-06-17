"""Page registration + drawing-zone grid (SPEC §4 registration; zone is a requested add-on).

``Registration`` aligns the reference page to the candidate page via affine transforms
estimated from unique shared text anchors (RANSAC-filtered). Position-based defects are
meaningless without this.

A single sheet often carries **several drawing views**, and a view may be laid out at a
different position on the candidate (Creo) sheet than on the reference. One global affine
cannot model that — it would flag every label in a moved view as misplaced. So registration
is **multi-model**: sequential RANSAC discovers one local affine per consistently-moving
group of anchors (i.e. per view). Each query point is mapped by the transform of its nearest
view, so a whole view sitting elsewhere is *absorbed*, while a single run that moved relative
to its view still reads as displaced. A separate view-transform requires
``registration_min_view_anchors`` inliers, so a lone shifted run never spawns its own model.

``ZoneGrid`` parses the candidate sheet's border zone labels (numbers along top/bottom =
columns, letters along left/right = rows) and maps a point to a cell like ``"C7"``. The
grid is parsed per sheet (sizes vary), so nothing is hardcoded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .config import Config
from .extract import TextRun
from .normalize import Normalizer

Point = tuple[float, float]
BBox = tuple[float, float, float, float]

_NUM = re.compile(r"^\d{1,3}$")
_LETTER = re.compile(r"^[A-Za-z]$")


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
@dataclass
class _LocalModel:
    """One view's affine plus the reference-space anchor points that voted for it."""

    matrix: np.ndarray
    anchors: np.ndarray  # (N, 2) reference-space points used to route queries to this model


@dataclass
class Registration:
    """Affine map(s) taking reference points into candidate coordinates.

    ``matrix`` is the primary/global transform (back-compatible single-model view). When a
    sheet holds independently-placed views, ``models`` carries one local affine per view and
    each query is routed to the nearest view's transform.
    """

    matrix: np.ndarray
    models: list[_LocalModel] = field(default_factory=list)

    def _matrix_for(self, x: float, y: float) -> np.ndarray:
        if len(self.models) <= 1:
            return self.matrix
        best_m = self.matrix
        best_d = float("inf")
        for mdl in self.models:
            d = float(np.min(((mdl.anchors[:, 0] - x) ** 2 + (mdl.anchors[:, 1] - y) ** 2)))
            if d < best_d:
                best_d = d
                best_m = mdl.matrix
        return best_m

    def map_point(self, x: float, y: float) -> Point:
        m = self._matrix_for(x, y)
        return (
            float(m[0, 0] * x + m[0, 1] * y + m[0, 2]),
            float(m[1, 0] * x + m[1, 1] * y + m[1, 2]),
        )

    def map_bbox(self, bbox: BBox) -> BBox:
        x0, y0, x1, y1 = bbox
        # Route the whole bbox by its center so all four corners share one view transform.
        m = self._matrix_for((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        pts = [(m[0, 0] * px + m[0, 1] * py + m[0, 2], m[1, 0] * px + m[1, 1] * py + m[1, 2])
               for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


def _fit_affine(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    n = len(src)
    a = np.zeros((2 * n, 6))
    b = np.zeros(2 * n)
    a[0::2, 0] = src[:, 0]; a[0::2, 1] = src[:, 1]; a[0::2, 2] = 1.0
    a[1::2, 3] = src[:, 0]; a[1::2, 4] = src[:, 1]; a[1::2, 5] = 1.0
    b[0::2] = dst[:, 0]; b[1::2] = dst[:, 1]
    sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    return sol.reshape(2, 3)


def _ransac_inliers(src: np.ndarray, dst: np.ndarray, thresh: float, iters: int = 200):
    """Return (best_inlier_mask, refit_matrix) for the largest affine-consistent subset."""
    n = len(src)
    if n < 3:
        m = _fit_affine(src, dst)
        return np.ones(n, dtype=bool), m
    rng = np.random.default_rng(0)
    best_inliers = None
    best_count = -1
    for _ in range(iters):
        idx = rng.choice(n, 3, replace=False)
        try:
            m = _fit_affine(src[idx], dst[idx])
        except np.linalg.LinAlgError:
            continue
        proj = (m[:, :2] @ src.T).T + m[:, 2]
        err = np.linalg.norm(proj - dst, axis=1)
        inliers = err < thresh
        count = int(inliers.sum())
        if count > best_count:
            best_count = count
            best_inliers = inliers
    if best_inliers is None or best_count < 3:
        return np.ones(n, dtype=bool), _fit_affine(src, dst)
    return best_inliers, _fit_affine(src[best_inliers], dst[best_inliers])


def _ransac_affine(src: np.ndarray, dst: np.ndarray, thresh: float, iters: int = 200) -> np.ndarray:
    return _ransac_inliers(src, dst, thresh, iters)[1]


def _valid_matrix(m: np.ndarray) -> bool:
    return bool(np.isfinite(m).all()) and abs(np.linalg.det(m[:, :2])) >= 1e-6


def _sequential_models(src: np.ndarray, dst: np.ndarray, thresh: float,
                       min_anchors: int, max_models: int) -> list[_LocalModel]:
    """Peel off one affine per consistently-moving anchor group (one per drawing view).

    Fit the largest-consensus affine, record its inliers as a view model, remove them, and
    repeat on the remainder. A group must have >= ``min_anchors`` inliers to count as a view,
    so a single run that shifted relative to its view never becomes its own model.
    """
    models: list[_LocalModel] = []
    remaining = np.ones(len(src), dtype=bool)
    for _ in range(max(1, max_models)):
        if int(remaining.sum()) < min_anchors:
            break
        idx = np.where(remaining)[0]
        inl, matrix = _ransac_inliers(src[idx], dst[idx], thresh)
        if int(inl.sum()) < min_anchors or not _valid_matrix(matrix):
            break
        models.append(_LocalModel(matrix=matrix, anchors=src[idx][inl].copy()))
        remaining[idx[inl]] = False
    return models


def _scale_fallback(ref_size, cand_size) -> np.ndarray:
    sx = cand_size[0] / max(1.0, ref_size[0])
    sy = cand_size[1] / max(1.0, ref_size[1])
    return np.array([[sx, 0.0, 0.0], [0.0, sy, 0.0]], dtype=float)


def compute_registration(
    ref_runs: list[TextRun],
    cand_runs: list[TextRun],
    ref_size: tuple[float, float],
    cand_size: tuple[float, float],
    normalizer: Normalizer,
    config: Config,
) -> Registration:
    """Estimate ref->candidate affine(s) from unique shared text anchors.

    Returns a single-model registration when all anchors agree on one transform, or a
    multi-model registration (one local affine per view) when the sheet's views are placed
    differently between reference and candidate.
    """
    ref_by_text: dict[str, list[TextRun]] = {}
    cand_by_text: dict[str, list[TextRun]] = {}
    for r in ref_runs:
        ref_by_text.setdefault(normalizer.normalize(r.text), []).append(r)
    for c in cand_runs:
        cand_by_text.setdefault(normalizer.normalize(c.text), []).append(c)

    src, dst = [], []
    for text, rs in ref_by_text.items():
        cs = cand_by_text.get(text)
        if len(rs) == 1 and cs is not None and len(cs) == 1 and len(text) > 0:
            src.append(rs[0].center)
            dst.append(cs[0].center)

    if len(src) < config.registration_min_anchors:
        return Registration(_scale_fallback(ref_size, cand_size))

    src_arr = np.array(src, dtype=float)
    dst_arr = np.array(dst, dtype=float)
    thresh = max(5.0, config.position_tolerance_pts * 2)

    if config.registration_multi_view:
        models = _sequential_models(
            src_arr, dst_arr, thresh,
            min_anchors=config.registration_min_view_anchors,
            max_models=config.registration_max_views,
        )
        if len(models) >= 2:
            # Primary matrix = the model owning the most anchors (largest view).
            primary = max(models, key=lambda m: len(m.anchors)).matrix
            return Registration(primary, models)

    matrix = _ransac_affine(src_arr, dst_arr, thresh=thresh)
    if not _valid_matrix(matrix):
        return Registration(_scale_fallback(ref_size, cand_size))
    return Registration(matrix)


# --------------------------------------------------------------------------- #
# Zone grid
# --------------------------------------------------------------------------- #
@dataclass
class ZoneGrid:
    col_centers: list[tuple[float, str]]   # (x_center, column label) sorted by x
    row_centers: list[tuple[float, str]]   # (y_center, row label) sorted by y
    page_size: tuple[float, float]
    config: Config

    @property
    def valid(self) -> bool:
        return len(self.col_centers) >= 2 and len(self.row_centers) >= 2

    def zone_for_bbox(self, bbox: BBox) -> str | None:
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        return self.zone_for_point(cx, cy)

    def zone_for_point(self, x: float, y: float) -> str | None:
        w, h = self.page_size
        tb = self.config.zone.title_block_frac
        if x > w * (1 - tb) and y > h * (1 - tb):
            return "title-block"
        if not self.valid:
            return None
        col = min(self.col_centers, key=lambda c: abs(c[0] - x))[1]
        row = min(self.row_centers, key=lambda r: abs(r[0] - y))[1]
        return f"{row}{col}" if self.config.zone.row_first else f"{col}{row}"


def build_zone_grid(runs: list[TextRun], page_size: tuple[float, float], config: Config) -> ZoneGrid:
    w, h = page_size
    band = config.zone.margin_band_frac
    left_x, right_x = w * band, w * (1 - band)
    top_y, bot_y = h * band, h * (1 - band)

    num_by_val: dict[str, list[float]] = {}
    let_by_val: dict[str, list[float]] = {}
    for r in runs:
        cx, cy = r.center
        in_top_bot = cy < top_y or cy > bot_y
        in_left_right = cx < left_x or cx > right_x
        if _NUM.match(r.text) and in_top_bot and not in_left_right:
            num_by_val.setdefault(r.text, []).append(cx)
        elif _LETTER.match(r.text) and in_left_right and not in_top_bot:
            let_by_val.setdefault(r.text.upper(), []).append(cy)

    col_centers = sorted(
        ((float(np.median(xs)), val) for val, xs in num_by_val.items()),
        key=lambda c: c[0],
    )
    row_centers = sorted(
        ((float(np.median(ys)), val) for val, ys in let_by_val.items()),
        key=lambda r: r[0],
    )
    return ZoneGrid(col_centers, row_centers, page_size, config)
