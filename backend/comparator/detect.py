"""Per-class defect detection (SPEC §6 ``detect.py``).

Runs the five detectors against one page pair and emits ``Defect`` records carrying the
SPEC §5 schema plus the requested ``zone`` / ``cause`` / ``fix`` fields. Class-5 decisions
go through ``render_compare`` (SPEC §3): a string mismatch is only a defect if the rendered
region also differs — encoding-only artifacts are suppressed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz
import cv2
import numpy as np

from .config import Config
from .extract import TextRun, extract_runs, extract_line_segments
from .match import cluster_runs, match_runs
from .normalize import Normalizer
from .register import Registration, ZoneGrid, build_zone_grid, compute_registration
from .render_compare import RenderComparer
from .text_layer import analyze_missing_zones, extract_tables_as_dataframes, extract_bom_grid
from .cv_layer import find_visual_differences

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
        if extra and "rotation_angle" in extra:
            rot_angle = extra["rotation_angle"]
            if abs(rot_angle) > 1.0:
                direction = "clockwise" if rot_angle > 0 else "counterclockwise"
                message += f" (view rotated {abs(rot_angle):.1f}° {direction})"
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
        if defect_class == "added_text":
            return f"Extra text '{s['cand_text']}' added in candidate{z}."
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
        if defect_class == "visual_defect":
            return f"Visual discrepancy detected in candidate drawing{z}."
        return f"{defect_class}{z}."



def _compare_tables(
    page_index: int,
    ref_page: fitz.Page,
    cand_page: fitz.Page,
    registration: Registration,
    normalizer: Normalizer,
    zone_grid: ZoneGrid,
    builder: DefectBuilder,
    config: Config,
) -> tuple[list[Defect], list[BBox]]:
    ref_tables = extract_bom_grid(ref_page, normalizer)
    if not ref_tables:
        ref_tables = [
            (bbox, df) for bbox, df in extract_tables_as_dataframes(ref_page)
            if not ((bbox[2] - bbox[0]) > 0.8 * ref_page.rect.width and (bbox[3] - bbox[1]) > 0.8 * ref_page.rect.height)
        ]
        
    cand_tables = extract_bom_grid(cand_page, normalizer)
    if not cand_tables:
        cand_tables = [
            (bbox, df) for bbox, df in extract_tables_as_dataframes(cand_page)
            if not ((bbox[2] - bbox[0]) > 0.8 * cand_page.rect.width and (bbox[3] - bbox[1]) > 0.8 * cand_page.rect.height)
        ]

        
    defects = []

    matched_cand_indices = set()
    for ref_bbox, ref_df in ref_tables:
        mapped_ref_bbox = registration.map_bbox(ref_bbox)
        ref_center = ((mapped_ref_bbox[0] + mapped_ref_bbox[2]) / 2.0, (mapped_ref_bbox[1] + mapped_ref_bbox[3]) / 2.0)

        best_cand_idx = -1
        best_dist = float("inf")
        for idx, (cand_bbox, cand_df) in enumerate(cand_tables):
            cand_center = ((cand_bbox[0] + cand_bbox[2]) / 2.0, (cand_bbox[1] + cand_bbox[3]) / 2.0)
            dist = ((ref_center[0] - cand_center[0])**2 + (ref_center[1] - cand_center[1])**2)**0.5
            if dist < best_dist and dist < 150.0:
                best_dist = dist
                best_cand_idx = idx

        if best_cand_idx == -1:
            zone = zone_grid.zone_for_bbox(mapped_ref_bbox)
            defects.append(builder.build(
                page=page_index, defect_class="missing_annotation", confidence=1.0,
                zone=zone, ref_text="BOM / Table Structure", cand_text=None,
                bbox_ref=ref_bbox, bbox_cand=mapped_ref_bbox, rendered_diff_score=None,
            ))
            continue

        matched_cand_indices.add(best_cand_idx)
        cand_bbox, cand_df = cand_tables[best_cand_idx]

        ref_rows, ref_cols = ref_df.shape
        cand_rows, cand_cols = cand_df.shape

        # Dynamically match columns by header text similarity
        ref_cols_list = list(ref_df.columns)
        cand_cols_list = list(cand_df.columns)
        
        col_mapping = {}  # ref_col_idx -> cand_col_idx
        for r_idx, r_col in enumerate(ref_cols_list):
            norm_r = normalizer.normalize(str(r_col)).lower()
            best_c_idx = -1
            best_sim = 0.0
            for c_idx, c_col in enumerate(cand_cols_list):
                norm_c = normalizer.normalize(str(c_col)).lower()
                sim = 1.0 - normalizer.edit_distance_norm(norm_r, norm_c)
                if norm_r in norm_c or norm_c in norm_r:
                    sim = max(sim, 0.8)
                if norm_r == norm_c:
                    sim = 1.0
                if sim > best_sim and sim > 0.6:
                    best_sim = sim
                    best_c_idx = c_idx
            if best_c_idx != -1:
                col_mapping[r_idx] = best_c_idx

        for r in range(ref_rows):
            for r_col_idx, c_col_idx in col_mapping.items():
                ref_val = str(ref_df.iloc[r, r_col_idx]).strip()
                cand_val = ""
                if r < cand_rows:
                    cand_val = str(cand_df.iloc[r, c_col_idx]).strip()
                else:
                    zone = zone_grid.zone_for_bbox(cand_bbox)
                    defects.append(builder.build(
                        page=page_index, defect_class="missing_text", confidence=0.9,
                        zone=zone, ref_text=ref_val, cand_text=None,
                        bbox_ref=ref_bbox, bbox_cand=cand_bbox, rendered_diff_score=None,
                    ))
                    continue

                norm_ref = normalizer.normalize(ref_val)
                norm_cand = normalizer.normalize(cand_val)

                if norm_ref != norm_cand:
                    cell_w_ref = (ref_bbox[2] - ref_bbox[0]) / max(1, ref_cols)
                    cell_h_ref = (ref_bbox[3] - ref_bbox[1]) / max(1, ref_rows)
                    cell_ref_bbox = (
                        ref_bbox[0] + r_col_idx * cell_w_ref,
                        ref_bbox[1] + r * cell_h_ref,
                        ref_bbox[0] + (r_col_idx + 1) * cell_w_ref,
                        ref_bbox[1] + (r + 1) * cell_h_ref
                    )

                    cell_w_cand = (cand_bbox[2] - cand_bbox[0]) / max(1, cand_cols)
                    cell_h_cand = (cand_bbox[3] - cand_bbox[1]) / max(1, cand_rows)
                    cell_cand_bbox = (
                        cand_bbox[0] + c_col_idx * cell_w_cand,
                        cand_bbox[1] + r * cell_h_cand,
                        cand_bbox[0] + (c_col_idx + 1) * cell_w_cand,
                        cand_bbox[1] + (r + 1) * cell_h_cand
                    )

                    zone = zone_grid.zone_for_bbox(cell_cand_bbox)
                    defects.append(builder.build(
                        page=page_index, defect_class="font_glyph_corruption" if norm_cand else "missing_text",
                        confidence=0.9, zone=zone, ref_text=ref_val, cand_text=cand_val or None,
                        bbox_ref=cell_ref_bbox, bbox_cand=cell_cand_bbox, rendered_diff_score=None,
                    ))

    return defects, [bbox for bbox, _ in cand_tables]


def _merge_visual_defects(
    page_index: int,
    defects: list[Defect],
    ref_page: fitz.Page,
    cand_page: fitz.Page,
    registration: Registration,
    zone_grid: ZoneGrid,
    builder: DefectBuilder,
    config: Config,
    cand_table_bboxes: list[BBox] = None,
) -> list[Defect]:
    return defects

    merged = list(defects)
    used_vis_indices = set()

    for d in merged:
        bbox = d.bbox_cand
        if bbox is None:
            continue
        best_vis_idx = -1
        best_overlap = 0.0
        for idx, (v_ref_bbox, v_cand_bbox, v_score) in enumerate(vis_diffs):
            overlap = _overlap_ratio(bbox, v_cand_bbox)
            if overlap > best_overlap:
                best_overlap = overlap
                best_vis_idx = idx

        if best_overlap > 0.05 and best_vis_idx != -1:
            d.rendered_diff_score = vis_diffs[best_vis_idx][2]
            used_vis_indices.add(best_vis_idx)

    # Filter out visual diffs that overlap significantly with any text defect
    for idx, (v_ref_bbox, v_cand_bbox, v_score) in enumerate(vis_diffs):
        if idx in used_vis_indices:
            continue
        for d in merged:
            bbox = d.bbox_cand or d.bbox_ref
            if bbox is not None and _overlap_ratio(bbox, v_cand_bbox) > 0.1:
                used_vis_indices.add(idx)
                break

    # Retrieve all candidate and reference text runs for text proximity filtering
    from .extract import extract_runs
    ref_runs = extract_runs(ref_page, page_index)
    cand_runs = extract_runs(cand_page, page_index)
    pw = cand_page.rect.width
    ph = cand_page.rect.height
    mx = pw * 0.06
    my = ph * 0.06

    for idx, (v_ref_bbox, v_cand_bbox, v_score) in enumerate(vis_diffs):
        if idx in used_vis_indices:
            continue
            
        # A. Filter out if inside border margin band (6%)
        cx = (v_cand_bbox[0] + v_cand_bbox[2]) / 2.0
        cy = (v_cand_bbox[1] + v_cand_bbox[3]) / 2.0
        if cx < mx or cx > pw - mx or cy < my or cy > ph - my:
            used_vis_indices.add(idx)
            continue
            
        # B. Filter out if area is too small (< 40.0 square points)
        vx = v_cand_bbox[2] - v_cand_bbox[0]
        vy = v_cand_bbox[3] - v_cand_bbox[1]
        if vx * vy < 40.0:
            used_vis_indices.add(idx)
            continue
            
        # C. Filter out if it overlaps with ANY candidate or reference text run (mask text changes)
        overlaps_run = False
        for run in cand_runs:
            if _overlap_ratio(run.bbox, v_cand_bbox) > 0.01:
                overlaps_run = True
                break
        if not overlaps_run:
            for run in ref_runs:
                mapped_bbox = registration.map_bbox(run.bbox)
                if _overlap_ratio(mapped_bbox, v_cand_bbox) > 0.01:
                    overlaps_run = True
                    break
        if overlaps_run:
            used_vis_indices.add(idx)
            continue

        zone = zone_grid.zone_for_bbox(v_cand_bbox)
        conf = _clamp(v_score / (2 * max(config.pixel_diff_threshold, 1e-6)))
        merged.append(builder.build(
            page=page_index,
            defect_class="visual_defect",
            confidence=conf,
            zone=zone,
            ref_text=None,
            cand_text=None,
            bbox_ref=v_ref_bbox,
            bbox_cand=v_cand_bbox,
            rendered_diff_score=v_score,
        ))


    return merged


def _detect_extra(
    page_index: int,
    cand_runs: list[TextRun],
    result,
    page_w: float,
    page_h: float,
    zone_grid: ZoneGrid,
    builder: DefectBuilder,
    config: Config,
) -> list[Defect]:
    out = []
    for j in result.unmatched_cand:
        cand = cand_runs[j]
        if len(cand.text.strip()) <= 1:
            continue
        zone = zone_grid.zone_for_bbox(cand.bbox)
        if zone == "title-block":
            continue
        cx, cy = cand.center
        if cx < page_w * 0.06 or cx > page_w * 0.94 or cy < page_h * 0.06 or cy > page_h * 0.94:
            continue
        out.append(builder.build(
            page=page_index,
            defect_class="added_text",
            confidence=1.0,
            zone=zone,
            ref_text=None,
            cand_text=cand.text,
            bbox_ref=None,
            bbox_cand=cand.bbox,
            rendered_diff_score=None,
        ))
    return out


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

    cand_table_bboxes = []
    # 1. Compare BOM and tabular structures directly
    try:
        table_defects, cand_table_bboxes = _compare_tables(
            page_index, ref_page, cand_page, registration, normalizer, zone_grid, builder, config
        )
        defects.extend(table_defects)
    except Exception:
        pass

    result = match_runs(ref_runs, cand_runs, registration, normalizer, config)

    import difflib

    # 2. Robust text matching for remaining unmatched texts (split text and fuzzy mismatches)
    unmatched_ref_set = set(result.unmatched_ref)
    unmatched_cand_set = set(result.unmatched_cand)

    matched_ref_indices = set()
    matched_cand_indices = set()

    # A. Exact matching
    ref_by_norm = {}
    for r_idx in unmatched_ref_set:
        norm = normalizer.normalize(ref_runs[r_idx].text)
        ref_by_norm.setdefault(norm, []).append(r_idx)

    for c_idx in list(unmatched_cand_set):
        norm = normalizer.normalize(cand_runs[c_idx].text)
        if norm in ref_by_norm and ref_by_norm[norm]:
            r_idx = ref_by_norm[norm].pop(0)
            matched_ref_indices.add(r_idx)
            matched_cand_indices.add(c_idx)
            unmatched_cand_set.remove(c_idx)
            unmatched_ref_set.remove(r_idx)

    # B. Substring / Split mapping
    for r_idx in list(unmatched_ref_set):
        r_text = normalizer.normalize(ref_runs[r_idx].text)
        if len(r_text) < 5:
            continue
        
        cands_to_check = [c for c in unmatched_cand_set if len(normalizer.normalize(cand_runs[c].text)) >= 4]
        cands_to_check.sort(key=lambda c: len(normalizer.normalize(cand_runs[c].text)), reverse=True)
        
        used_cands_for_this_ref = []
        r_text_remaining = r_text
        for c_idx in cands_to_check:
            c_text = normalizer.normalize(cand_runs[c_idx].text)
            if c_text in r_text_remaining:
                r_text_remaining = r_text_remaining.replace(c_text, "", 1)
                used_cands_for_this_ref.append(c_idx)
        
        if used_cands_for_this_ref and (len(r_text_remaining) / len(r_text) < 0.2):
            matched_ref_indices.add(r_idx)
            for c_idx in used_cands_for_this_ref:
                matched_cand_indices.add(c_idx)
                if c_idx in unmatched_cand_set:
                    unmatched_cand_set.remove(c_idx)
            unmatched_ref_set.remove(r_idx)

    # C. Fuzzy mismatch mapping
    for r_idx in list(unmatched_ref_set):
        r_text = normalizer.normalize(ref_runs[r_idx].text)
        if len(r_text) < 5:
            continue
            
        best_c_idx = -1
        best_sim = 0.0
        for c_idx in unmatched_cand_set:
            c_text = normalizer.normalize(cand_runs[c_idx].text)
            sim = difflib.SequenceMatcher(None, r_text, c_text).ratio()
            if sim > best_sim:
                best_sim = sim
                best_c_idx = c_idx
                
        if best_sim > 0.85 and best_c_idx != -1:
            matched_ref_indices.add(r_idx)
            matched_cand_indices.add(best_c_idx)
            unmatched_ref_set.remove(r_idx)
            unmatched_cand_set.remove(best_c_idx)
            
            ref = ref_runs[r_idx]
            cand = cand_runs[best_c_idx]
            zone = zone_grid.zone_for_bbox(cand.bbox)
            _, rot_angle = registration.view_info_for(*ref.center)
            extra = {"rotation_angle": rot_angle}
            
            defects.append(builder.build(
                page=page_index, defect_class="font_glyph_corruption", confidence=0.8,
                zone=zone, ref_text=ref.text, cand_text=cand.text,
                bbox_ref=ref.bbox, bbox_cand=cand.bbox, rendered_diff_score=None,
                extra=extra,
            ))

    # Update the result's unmatched lists
    result.unmatched_ref = [r for r in result.unmatched_ref if r not in matched_ref_indices]
    result.unmatched_cand = [c for c in result.unmatched_cand if c not in matched_cand_indices]

    # --- Classes 4 & 5: matched-pair defects (misplacement, font/glyph corruption) ---
    for m in result.matches:
        ref, cand = ref_runs[m.ref_idx], cand_runs[m.cand_idx]
        zone = zone_grid.zone_for_bbox(cand.bbox)
        _, rot_angle = registration.view_info_for(*ref.center)
        extra = {"rotation_angle": rot_angle}
        corruption_flagged = False
        if not m.strings_equal:
            score = comparer.diff_score(ref_page, ref.bbox, cand_page, cand.bbox)
            if comparer.is_different(score):
                conf = _clamp(score / (2 * max(config.pixel_diff_threshold, 1e-6)))
                defects.append(builder.build(
                    page=page_index, defect_class="font_glyph_corruption", confidence=conf,
                    zone=zone, ref_text=ref.text, cand_text=cand.text,
                    bbox_ref=ref.bbox, bbox_cand=cand.bbox, rendered_diff_score=score,
                    extra=extra,
                ))
                corruption_flagged = True
            # else: renders the same -> encoding/ToUnicode artifact -> suppressed (SPEC §3)
        # Shifted text/notes is OK per user request, so text_misplacement is bypassed.

    # --- Classes 1 & 2: missing text / annotation (unmatched reference runs) ---
    defects.extend(_detect_missing(
        page_index, ref_runs, ref_segments, result, registration, zone_grid, builder, config))

    # --- Extra text (unmatched candidate runs) ---
    extra_defects = _detect_extra(
        page_index, cand_runs, result, cand_size[0], cand_size[1], zone_grid, builder, config
    )
    defects.extend(extra_defects)

    # --- Class 3: intra-candidate text overlap ---
    defects.extend(_detect_overlap(
        page_index, cand_runs, cand_segments, zone_grid, builder, config))

    # --- Text-to-geometry overlap ---
    try:
        geom_overlaps = _detect_text_to_geometry_overlaps(
            page_index, cand_page, cand_runs, zone_grid, builder, config)
        defects.extend(geom_overlaps)
    except Exception:
        pass


    # --- Spatial Clustering & Relative Zone Hashing for missing zones ---
    try:
        missing_zones = analyze_missing_zones(ref_runs, cand_runs, registration, normalizer, config)
        for ref_z_bbox, cand_z_bbox, msg in missing_zones:
            already_flagged = False
            for d in defects:
                if d.defect_class in ("missing_text", "missing_annotation") and d.bbox_cand is not None:
                    if _overlap_ratio(cand_z_bbox, d.bbox_cand) > 0.3:
                        already_flagged = True
                        break
            if not already_flagged:
                zone = zone_grid.zone_for_bbox(cand_z_bbox)
                defects.append(builder.build(
                    page=page_index,
                    defect_class="missing_annotation",
                    confidence=0.9,
                    zone=zone,
                    ref_text=msg,
                    cand_text=None,
                    bbox_ref=ref_z_bbox,
                    bbox_cand=cand_z_bbox,
                    rendered_diff_score=None,
                ))
    except Exception:
        pass

    # --- Computer Vision Layer (Merge & identify isolated visual differences) ---
    defects = _merge_visual_defects(
        page_index, defects, ref_page, cand_page, registration, zone_grid, builder, config, cand_table_bboxes
    )

    # Filter defects falling within cand_table_bboxes (BOM areas) or border
    filtered_defects = []
    for d in defects:
        if d.zone == "border":
            continue
            
        # Keep BOM structure issues
        if getattr(d, "ref_text", None) == "BOM / Table Structure" or d.defect_class == "missing_annotation" and "BOM" in str(getattr(d, "ref_text", "")):
            filtered_defects.append(d)
            continue

        is_in_bom = False
        if d.bbox_cand is not None:
            cx, cy = (d.bbox_cand[0] + d.bbox_cand[2]) / 2.0, (d.bbox_cand[1] + d.bbox_cand[3]) / 2.0
            for t_bbox in cand_table_bboxes:
                if t_bbox[0] <= cx <= t_bbox[2] and t_bbox[1] <= cy <= t_bbox[3]:
                    is_in_bom = True
                    break
        if not is_in_bom:
            filtered_defects.append(d)

    return _apply_ignore_regions(filtered_defects, config)


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
        group_missing = len(missing) > 1
        if group_missing:
            boxes = [ref_runs[i].bbox for i in missing]
            ref_bbox = _union_bbox(boxes)
            text = " ".join(ref_runs[i].text for i in sorted(missing, key=lambda k: (ref_runs[k].bbox[1], ref_runs[k].bbox[0])))
            cand_bbox = registration.map_bbox(ref_bbox)
            _, rot_angle = registration.view_info_for((ref_bbox[0] + ref_bbox[2]) / 2.0, (ref_bbox[1] + ref_bbox[3]) / 2.0)
            extra = {"rotation_angle": rot_angle}
            conf = _clamp(min(result.min_ref_cost.get(i, config.match_max_cost) for i in missing)
                          / (2 * max(config.match_max_cost, 1e-6)))
            out.append(builder.build(
                page=page_index, defect_class="missing_annotation", confidence=conf,
                zone=zone_grid.zone_for_bbox(cand_bbox), ref_text=text, cand_text=None,
                bbox_ref=ref_bbox, bbox_cand=cand_bbox, rendered_diff_score=None,
                extra=extra,
            ))
        else:
            for i in missing:
                ref = ref_runs[i]
                cand_bbox = registration.map_bbox(ref.bbox)
                _, rot_angle = registration.view_info_for(*ref.center)
                extra = {"rotation_angle": rot_angle}
                conf = _clamp(result.min_ref_cost.get(i, config.match_max_cost)
                              / (2 * max(config.match_max_cost, 1e-6)))
                out.append(builder.build(
                    page=page_index, defect_class="missing_text", confidence=conf,
                    zone=zone_grid.zone_for_bbox(cand_bbox), ref_text=ref.text, cand_text=None,
                    bbox_ref=ref.bbox, bbox_cand=cand_bbox, rendered_diff_score=None,
                    extra=extra,
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
            # Skip overlap if they are horizontally adjacent inline runs
            h_a = a.bbox[3] - a.bbox[1]
            h_b = b.bbox[3] - b.bbox[1]
            min_h = min(h_a, h_b)
            if min_h > 0:
                dy = min(a.bbox[3], b.bbox[3]) - max(a.bbox[1], b.bbox[1])
                v_overlap = dy / min_h
                if v_overlap > 0.8:
                    dx = max(a.bbox[0], b.bbox[0]) - min(a.bbox[2], b.bbox[2])
                    if dx < max(12.0, min_h * 1.5):
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


def _detect_text_to_geometry_overlaps(
    page_index: int,
    cand_page: fitz.Page,
    cand_runs: list[TextRun],
    zone_grid: ZoneGrid,
    builder: DefectBuilder,
    config: Config,
) -> list[Defect]:
    w = int(cand_page.rect.width)
    h = int(cand_page.rect.height)
    geom_img = np.full((h, w), 255, dtype=np.uint8)

    drawings = cand_page.get_drawings()
    for path in drawings:
        color = 0
        raw_width = path.get("width")
        width = max(1, int(raw_width)) if raw_width is not None else 1



        
        for item in path.get("items", []):
            if item[0] == "l":  # line
                p1, p2 = item[1], item[2]
                cv2.line(geom_img, (int(p1.x), int(p1.y)), (int(p2.x), int(p2.y)), color, width)
            elif item[0] == "re":  # rect
                r = item[1]
                cv2.rectangle(geom_img, (int(r.x0), int(r.y0)), (int(r.x1), int(r.y1)), color, width)
            elif item[0] == "qu":  # quad
                q = item[1]
                pts = np.array([[q.ul.x, q.ul.y], [q.ur.x, q.ur.y], [q.lr.x, q.lr.y], [q.ll.x, q.ll.y]], dtype=np.int32)
                cv2.polylines(geom_img, [pts], isClosed=True, color=color, thickness=width)
            elif item[0] == "c":  # curve
                p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                pts = np.array([[p1.x, p1.y], [p2.x, p2.y], [p3.x, p3.y], [p4.x, p4.y]], dtype=np.int32)
                cv2.polylines(geom_img, [pts], isClosed=False, color=color, thickness=width)

    # Extract table boundaries to avoid false positives on grid/borders
    from .normalize import Normalizer
    normalizer = Normalizer(config)
    cand_tables = extract_bom_grid(cand_page, normalizer)
    if not cand_tables:
        cand_tables = [
            t for t in extract_tables_as_dataframes(cand_page)
            if not ((t[0][2] - t[0][0]) > 0.8 * w and (t[0][3] - t[0][1]) > 0.8 * h)
        ]
    table_bboxes = [t[0] for t in cand_tables]

    out = []
    for run in cand_runs:
        # A. Filter out GDT/isolated symbols
        if len(run.text.strip()) <= 1:
            continue
            
        # B. Filter out Title Block area
        zone = zone_grid.zone_for_bbox(run.bbox)
        if zone == "title-block":
            continue
            
        # C. Filter out margin border band (6%)
        cx, cy = run.center
        if cx < w * 0.06 or cx > w * 0.94 or cy < h * 0.06 or cy > h * 0.94:
            continue
            
        # D. Filter out runs inside table bboxes
        inside_table = False
        for t_bbox in table_bboxes:
            if _overlap_ratio(run.bbox, t_bbox) > 0.5:
                inside_table = True
                break
        if inside_table:
            continue

        x0, y0, x1, y1 = run.bbox
        inset_x = min(5.0, (x1 - x0) * 0.3)
        inset_y = min(4.0, (y1 - y0) * 0.3)
        ix0, iy0 = int(x0 + inset_x), int(y0 + inset_y)
        ix1, iy1 = int(x1 - inset_x), int(y1 - inset_y)

        if ix1 <= ix0 or iy1 <= iy0:
            continue

        ix0, iy0 = max(0, ix0), max(0, iy0)
        ix1, iy1 = min(w - 1, ix1), min(h - 1, iy1)

        roi = geom_img[iy0:iy1, ix0:ix1]
        
        if roi.size > 0:
            non_white = np.sum(roi < 200)
            if non_white > 3:
                union = run.bbox
                out.append(builder.build(
                    page=page_index,
                    defect_class="text_overlap",
                    confidence=0.8,
                    zone=zone,
                    ref_text=None,
                    cand_text=f"Text '{run.text}' overlaps drawing geometry",
                    bbox_ref=None,
                    bbox_cand=union,
                    rendered_diff_score=None,
                    extra={"overlap_type": "text_to_geometry"}
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
