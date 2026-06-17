"""Reference<->candidate run matching (SPEC §6 ``match.py``).

Bipartite assignment via the Hungarian algorithm (scipy). Cost combines post-registration
position distance with normalized string-edit distance, so a run matches the spatially- and
textually-closest counterpart. Assignments above ``match_max_cost`` are rejected, leaving the
reference run unmatched (a missing-text/annotation candidate).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from .config import Config
from .extract import TextRun
from .normalize import Normalizer
from .register import Registration


@dataclass
class Match:
    ref_idx: int
    cand_idx: int
    cost: float
    position_distance: float
    strings_equal: bool


@dataclass
class MatchResult:
    matches: list[Match]
    unmatched_ref: list[int]
    unmatched_cand: list[int]
    min_ref_cost: dict[int, float]  # ref_idx -> cheapest available cost (for confidence)


def match_runs(
    ref_runs: list[TextRun],
    cand_runs: list[TextRun],
    registration: Registration,
    normalizer: Normalizer,
    config: Config,
) -> MatchResult:
    n_ref, n_cand = len(ref_runs), len(cand_runs)
    if n_ref == 0 or n_cand == 0:
        return MatchResult([], list(range(n_ref)), list(range(n_cand)), {})

    # Map reference centers into candidate coordinates once.
    mapped = [registration.map_point(*r.center) for r in ref_runs]
    norm_ref = [normalizer.normalize(r.text) for r in ref_runs]
    norm_cand = [normalizer.normalize(c.text) for c in cand_runs]

    cost = np.zeros((n_ref, n_cand), dtype=float)
    pos_dist = np.zeros((n_ref, n_cand), dtype=float)
    for i in range(n_ref):
        mx, my = mapped[i]
        for j in range(n_cand):
            cx, cy = cand_runs[j].center
            d = ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5
            pos_dist[i, j] = d
            if norm_ref[i] == norm_cand[j]:
                edit = 0.0
            else:
                edit = normalizer.edit_distance_norm(ref_runs[i].text, cand_runs[j].text)
            cost[i, j] = d * config.match_position_weight + edit * config.match_string_weight

    min_ref_cost = {i: float(cost[i].min()) for i in range(n_ref)}

    row_ind, col_ind = linear_sum_assignment(cost)
    matches: list[Match] = []
    matched_ref, matched_cand = set(), set()
    for i, j in zip(row_ind, col_ind):
        if cost[i, j] <= config.match_max_cost:
            matches.append(Match(
                ref_idx=int(i),
                cand_idx=int(j),
                cost=float(cost[i, j]),
                position_distance=float(pos_dist[i, j]),
                strings_equal=(norm_ref[i] == norm_cand[j]),
            ))
            matched_ref.add(int(i))
            matched_cand.add(int(j))

    unmatched_ref = [i for i in range(n_ref) if i not in matched_ref]
    unmatched_cand = [j for j in range(n_cand) if j not in matched_cand]
    return MatchResult(matches, unmatched_ref, unmatched_cand, min_ref_cost)


# --------------------------------------------------------------------------- #
# Annotation clustering (class 2: missing_annotation)
# --------------------------------------------------------------------------- #
def cluster_runs(
    runs: list[TextRun],
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    config: Config,
) -> list[list[int]]:
    """Union-find grouping of runs into annotation units.

    Two runs merge when they form a stack (close gap, same orientation, overlapping
    perpendicular extent) or share a leader-line endpoint.
    """
    n = len(runs)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    gap = config.cluster_gap_pts
    for i in range(n):
        for j in range(i + 1, n):
            if _is_stack(runs[i], runs[j], gap):
                union(i, j)

    # Leader-line linkage: a segment endpoint near two distinct runs links them.
    lg = config.leader_gap_pts
    for p1, p2 in segments:
        near = [k for k in range(n) if _near_bbox(runs[k].bbox, p1, lg) or _near_bbox(runs[k].bbox, p2, lg)]
        for a in range(len(near)):
            for b in range(a + 1, len(near)):
                union(near[a], near[b])

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _is_stack(a: TextRun, b: TextRun, gap: float) -> bool:
    ax0, ay0, ax1, ay1 = a.bbox
    bx0, by0, bx1, by1 = b.bbox
    # Same orientation (parallel text directions).
    if abs(a.direction[0] * b.direction[0] + a.direction[1] * b.direction[1]) < 0.97:
        return False
    dx = max(0.0, max(ax0, bx0) - min(ax1, bx1))
    dy = max(0.0, max(ay0, by0) - min(ay1, by1))
    x_overlap = min(ax1, bx1) - max(ax0, bx0) > 0
    y_overlap = min(ay1, by1) - max(ay0, by0) > 0
    # Vertical stack: horizontally overlapping, small vertical gap.
    if x_overlap and dy <= gap:
        return True
    # Horizontal run: vertically overlapping, small horizontal gap.
    if y_overlap and dx <= gap:
        return True
    return False


def _near_bbox(bbox, pt, tol: float) -> bool:
    x0, y0, x1, y1 = bbox
    px, py = pt
    nx = min(max(px, x0), x1)
    ny = min(max(py, y0), y1)
    return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5 <= tol
