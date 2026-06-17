"""Per-class defect detection (SPEC §6 ``detect.py``).

Runs the five detectors against one page pair and emits ``Defect`` records carrying the
SPEC §5 schema plus the requested ``zone`` / ``cause`` / ``fix`` fields. Class-5 decisions
go through ``render_compare`` (SPEC §3): a string mismatch is only a defect if the rendered
region also differs — encoding-only artifacts are suppressed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz

from .config import Config
from .extract import TextRun, extract_runs, extract_line_segments
from .match import cluster_runs, match_runs
from .normalize import Normalizer
from .register import Registration, ZoneGrid, build_zone_grid, compute_registration
from .render_compare import RenderComparer

BBox = tuple[float, float, float, float]


@dataclass
class Defect:
    page: int
    defect_class: str
    severity: str
    confidence: float
    status: str
    zone: str | None
    ref_text: str | None
    cand_text: str | None
    bbox_ref: BBox | None
    bbox_cand: BBox | None
    rendered_diff_score: float | None
    cause: str
    fix: str
    message: str
    extra: dict = field(default_factory=dict)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _union_bbox(boxes: list[BBox]) -> BBox:
    xs0 = [b[0] for b in boxes]; ys0 = [b[1] for b in boxes]
    xs1 = [b[2] for b in boxes]; ys1 = [b[3] for b in boxes]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _overlap_ratio(a: BBox, b: BBox) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    if dx <= 0 or dy <= 0:
        return 0.0
    inter = dx * dy
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    m = min(area_a, area_b)
    return inter / m if m > 0 else 0.0


class DefectBuilder:
    """Fills cause/fix/severity templates and computes status from confidence."""

    def __init__(self, config: Config):
        self.config = config

    def build(self, *, page, defect_class, confidence, zone, ref_text, cand_text,
              bbox_ref, bbox_cand, rendered_diff_score, extra=None) -> Defect:
        tpl = self.config.template_for(defect_class)
        slots = {
            "ref_text": ref_text if ref_text is not None else "",
            "cand_text": cand_text if cand_text is not None else "",
            "zone": zone if zone is not None else "—",
        }
        severity = tpl.get("severity", "medium")
        cause = tpl.get("cause", "").format(**slots)
        fix = tpl.get("fix", "").format(**slots)
        status = "defect" if confidence >= self.config.confidence_threshold else "review"
        message = self._message(defect_class, slots)
        return Defect(
            page=page, defect_class=defect_class, severity=severity,
            confidence=round(float(confidence), 3), status=status, zone=zone,
            ref_text=ref_text, cand_text=cand_text, bbox_ref=bbox_ref, bbox_cand=bbox_cand,
            rendered_diff_score=(round(rendered_diff_score, 3) if rendered_diff_score is not None else None),
            cause=cause, fix=fix, message=message, extra=extra or {},
        )

    @staticmethod
    def _message(defect_class: str, s: dict) -> str:
        z = f" (zone {s['zone']})" if s["zone"] != "—" else ""
        if defect_class == "missing_text":
            return f"Text '{s['ref_text']}' missing in candidate{z}."
        if defect_class == "missing_annotation":
            return f"Annotation '{s['ref_text']}' missing in candidate{z}."
        if defect_class == "text_overlap":
            return f"Overlapping candidate text '{s['cand_text']}'{z}."
        if defect_class == "text_misplacement":
            return f"Text '{s['ref_text']}' misplaced{z}."
        if defect_class == "font_glyph_corruption":
            return f"Text '{s['ref_text']}' renders as '{s['cand_text']}'{z}."
        return f"{defect_class}{z}."


def analyze_page(
    page_index: int,
    ref_page: fitz.Page,
    cand_page: fitz.Page,
    normalizer: Normalizer,
    comparer: RenderComparer,
    config: Config,
) -> list[Defect]:
    ref_runs = extract_runs(ref_page, page_index)
    cand_runs = extract_runs(cand_page, page_index)
    ref_segments = extract_line_segments(ref_page)
    cand_segments = extract_line_segments(cand_page)
    ref_size = (ref_page.rect.width, ref_page.rect.height)
    cand_size = (cand_page.rect.width, cand_page.rect.height)

    registration = compute_registration(ref_runs, cand_runs, ref_size, cand_size, normalizer, config)
    zone_grid = build_zone_grid(cand_runs, cand_size, config)
    builder = DefectBuilder(config)

    defects: list[Defect] = []
    result = match_runs(ref_runs, cand_runs, registration, normalizer, config)

    # --- Classes 4 & 5: matched-pair defects (misplacement, font/glyph corruption) ---
    for m in result.matches:
        ref, cand = ref_runs[m.ref_idx], cand_runs[m.cand_idx]
        zone = zone_grid.zone_for_bbox(cand.bbox)
        corruption_flagged = False
        if not m.strings_equal:
            score = comparer.diff_score(ref_page, ref.bbox, cand_page, cand.bbox)
            if comparer.is_different(score):
                conf = _clamp(score / (2 * max(config.pixel_diff_threshold, 1e-6)))
                defects.append(builder.build(
                    page=page_index, defect_class="font_glyph_corruption", confidence=conf,
                    zone=zone, ref_text=ref.text, cand_text=cand.text,
                    bbox_ref=ref.bbox, bbox_cand=cand.bbox, rendered_diff_score=score,
                ))
                corruption_flagged = True
            # else: renders the same -> encoding/ToUnicode artifact -> suppressed (SPEC §3)
        if not corruption_flagged and m.position_distance > config.position_tolerance_pts:
            conf = _clamp(m.position_distance / (2 * max(config.position_tolerance_pts, 1e-6)))
            defects.append(builder.build(
                page=page_index, defect_class="text_misplacement", confidence=conf,
                zone=zone, ref_text=ref.text, cand_text=cand.text,
                bbox_ref=ref.bbox, bbox_cand=cand.bbox, rendered_diff_score=None,
            ))

    # --- Classes 1 & 2: missing text / annotation (unmatched reference runs) ---
    defects.extend(_detect_missing(
        page_index, ref_runs, ref_segments, result, registration, zone_grid, builder, config))

    # --- Class 3: intra-candidate text overlap ---
    defects.extend(_detect_overlap(
        page_index, cand_runs, cand_segments, zone_grid, builder, config))

    return _apply_ignore_regions(defects, config)


def _detect_missing(page_index, ref_runs, ref_segments, result, registration: Registration,
                    zone_grid: ZoneGrid, builder: DefectBuilder, config: Config) -> list[Defect]:
    unmatched = set(result.unmatched_ref)
    if not unmatched:
        return []
    clusters = cluster_runs(ref_runs, ref_segments, config)
    out: list[Defect] = []
    for cluster in clusters:
        missing = [i for i in cluster if i in unmatched]
        if not missing:
            continue
        whole_cluster_missing = len(cluster) > 1 and len(missing) == len(cluster)
        if whole_cluster_missing:
            boxes = [ref_runs[i].bbox for i in cluster]
            ref_bbox = _union_bbox(boxes)
            text = " ".join(ref_runs[i].text for i in sorted(cluster, key=lambda k: ref_runs[k].bbox[1]))
            cand_bbox = registration.map_bbox(ref_bbox)
            conf = _clamp(min(result.min_ref_cost.get(i, config.match_max_cost) for i in cluster)
                          / (2 * max(config.match_max_cost, 1e-6)))
            out.append(builder.build(
                page=page_index, defect_class="missing_annotation", confidence=conf,
                zone=zone_grid.zone_for_bbox(cand_bbox), ref_text=text, cand_text=None,
                bbox_ref=ref_bbox, bbox_cand=cand_bbox, rendered_diff_score=None,
            ))
        else:
            for i in missing:
                ref = ref_runs[i]
                cand_bbox = registration.map_bbox(ref.bbox)
                conf = _clamp(result.min_ref_cost.get(i, config.match_max_cost)
                              / (2 * max(config.match_max_cost, 1e-6)))
                out.append(builder.build(
                    page=page_index, defect_class="missing_text", confidence=conf,
                    zone=zone_grid.zone_for_bbox(cand_bbox), ref_text=ref.text, cand_text=None,
                    bbox_ref=ref.bbox, bbox_cand=cand_bbox, rendered_diff_score=None,
                ))
    return out


def _detect_overlap(page_index, cand_runs, cand_segments, zone_grid: ZoneGrid,
                    builder: DefectBuilder, config: Config) -> list[Defect]:
    # Overlap = significant bbox *intersection* between runs from different source blocks.
    # A single annotation unit is one PDF block (its stacked lines never "intersect"), so
    # skipping same-block pairs avoids intra-annotation false positives while still catching
    # genuine collisions between independent labels.
    out: list[Defect] = []
    n = len(cand_runs)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = cand_runs[i], cand_runs[j]
            if a.block == b.block:
                continue
            ratio = _overlap_ratio(a.bbox, b.bbox)
            if ratio > config.overlap_ratio_threshold:
                union = _union_bbox([a.bbox, b.bbox])
                conf = _clamp(ratio / (2 * max(config.overlap_ratio_threshold, 1e-6)))
                out.append(builder.build(
                    page=page_index, defect_class="text_overlap", confidence=conf,
                    zone=zone_grid.zone_for_bbox(union),
                    ref_text=None, cand_text=f"{a.text} / {b.text}",
                    bbox_ref=None, bbox_cand=union, rendered_diff_score=None,
                    extra={"overlap_ratio": round(ratio, 3)},
                ))
    return out


def _apply_ignore_regions(defects: list[Defect], config: Config) -> list[Defect]:
    if not config.ignore_regions:
        return defects
    kept = []
    for d in defects:
        bbox = d.bbox_cand
        if bbox is not None:
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in config.ignore_regions):
                continue
        kept.append(d)
    return kept
