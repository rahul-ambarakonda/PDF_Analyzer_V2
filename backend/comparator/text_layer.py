"""Text Data Layer (Deterministic Verification).

Extracts grid-based tables, clusters text bounding boxes using DBSCAN,
and runs Relative Zone Hashing to identify missing layout zones.
"""

from __future__ import annotations

import hashlib
import numpy as np
import pandas as pd
import fitz

from .config import Config
from .extract import TextRun
from .normalize import Normalizer
from .register import Registration

BBox = tuple[float, float, float, float]


# --------------------------------------------------------------------------- #
# Table Extraction Track
# --------------------------------------------------------------------------- #
def extract_tables_as_dataframes(page: fitz.Page) -> list[tuple[BBox, pd.DataFrame]]:
    """Identify structured grid tables (like BOM blocks) and parse into DataFrames.
    
    Uses PyMuPDF's robust, fast native find_tables method to ensure text inside
    cells is preserved and aligned.
    """
    tables = []
    try:
        tabs = page.find_tables()
        for t in tabs:
            bbox = t.bbox  # (x0, y0, x1, y1)
            raw_data = t.extract()
            if not raw_data:
                continue
            df = pd.DataFrame(raw_data)
            tables.append((bbox, df))
    except Exception:
        # Fallback if find_tables is unavailable or fails
        pass
    return tables


# --------------------------------------------------------------------------- #
# DBSCAN Clustering Track
# --------------------------------------------------------------------------- #
def cluster_runs_dbscan(runs: list[TextRun], config: Config) -> list[list[int]]:
    """Group text runs into logical Information Zones using DBSCAN.
    
    Groups adjacent labels, tolerances, and notes by spatial proximity of centers.
    """
    if not runs:
        return []

    eps = config.dbscan_eps_pts
    min_samples = config.dbscan_min_samples

    # Extract center coordinates for clustering
    coords = np.array([r.center for r in runs], dtype=float)

    try:
        from sklearn.cluster import DBSCAN
        db = DBSCAN(eps=eps, min_samples=min_samples).fit(coords)
        labels = db.labels_
    except ImportError:
        # Robust pure-Python fallback for DBSCAN/Connected Components (min_samples=1)
        labels = _custom_dbscan_fallback(coords, eps)

    # Group runs by label
    label_to_indices = {}
    for idx, label in enumerate(labels):
        if label == -1:
            # Noise in DBSCAN (unclustered). Treat each noise point as its own zone.
            label_to_indices[f"noise_{idx}"] = [idx]
        else:
            label_to_indices.setdefault(label, []).append(idx)

    return list(label_to_indices.values())


def _custom_dbscan_fallback(coords: np.ndarray, eps: float) -> np.ndarray:
    """Pure-Python fallback for density clustering using connected components.
    
    Equivalent to DBSCAN with min_samples=1.
    """
    n = len(coords)
    labels = np.full(n, -1, dtype=int)
    current_label = 0

    # Build adjacency list
    adj = {i: [] for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            dist = np.linalg.norm(coords[i] - coords[j])
            if dist <= eps:
                adj[i].append(j)
                adj[j].append(i)

    # Find connected components (BFS)
    for i in range(n):
        if labels[i] != -1:
            continue
        # New component
        queue = [i]
        labels[i] = current_label
        head = 0
        while head < len(queue):
            curr = queue[head]
            head += 1
            for neighbor in adj[curr]:
                if labels[neighbor] == -1:
                    labels[neighbor] = current_label
                    queue.append(neighbor)
        current_label += 1

    return labels


# --------------------------------------------------------------------------- #
# Relative Zone Hashing & Verification
# --------------------------------------------------------------------------- #
class ZoneSignature:
    """Content and spatial signature for an clustered Information Zone."""

    def __init__(self, idxs: list[int], runs: list[TextRun], normalizer: Normalizer):
        self.indices = idxs
        self.runs = [runs[i] for i in idxs]
        
        # Sort runs in reading order (top-to-bottom, left-to-right) for deterministic hashing
        self.sorted_runs = sorted(self.runs, key=lambda r: (round(r.bbox[1], 1), round(r.bbox[0], 1)))
        
        # Combined normalized text string
        self.normalized_text = " ".join(normalizer.normalize(r.text) for r in self.sorted_runs)
        
        # Bounding box of the entire zone
        xs0 = [r.bbox[0] for r in self.runs]
        ys0 = [r.bbox[1] for r in self.runs]
        xs1 = [r.bbox[2] for r in self.runs]
        ys1 = [r.bbox[3] for r in self.runs]
        self.bbox: BBox = (min(xs0), min(ys0), max(xs1), max(ys1))
        
        # Center of the zone
        self.center = ((self.bbox[0] + self.bbox[2]) / 2.0, (self.bbox[1] + self.bbox[3]) / 2.0)
        
        # Hash signature
        self.hash_signature = hashlib.sha256(self.normalized_text.encode("utf-8")).hexdigest()


def analyze_missing_zones(
    ref_runs: list[TextRun],
    cand_runs: list[TextRun],
    registration: Registration,
    normalizer: Normalizer,
    config: Config,
) -> list[tuple[BBox, BBox, str]]:
    """Compare Reference and Candidate zones to find missing zones.
    
    Generates content signatures for each zone and checks for intersection.
    Returns list of (ref_bbox, cand_bbox_expected, message) for missing zones.
    """
    ref_clusters = cluster_runs_dbscan(ref_runs, config)
    cand_clusters = cluster_runs_dbscan(cand_runs, config)

    ref_sigs = [ZoneSignature(cluster, ref_runs, normalizer) for cluster in ref_clusters]
    cand_sigs = [ZoneSignature(cluster, cand_runs, normalizer) for cluster in cand_clusters]

    missing_zones = []

    # Map candidate signatures by hash for O(1) matching
    cand_by_hash = {c.hash_signature: c for c in cand_sigs}

    for ref_sig in ref_sigs:
        # Check exact hash match
        if ref_sig.hash_signature in cand_by_hash:
            continue

        # Look for partial matches (text similarities)
        matched = False
        best_similarity = 0.0
        best_cand = None
        
        # Also map ref center to candidate coordinates
        mapped_ref_center = registration.map_point(*ref_sig.center)

        for cand_sig in cand_sigs:
            # String similarity using edit distance
            sim = 1.0 - normalizer.edit_distance_norm(ref_sig.normalized_text, cand_sig.normalized_text)
            
            # Check spatial distance (is it in the same region?)
            dist = np.linalg.norm(np.array(mapped_ref_center) - np.array(cand_sig.center))
            
            # If text is extremely similar and within a reasonable distance, consider it matched
            if sim > 0.8 and dist < 100.0:  # within ~1.4 inch
                if sim > best_similarity:
                    best_similarity = sim
                    best_cand = cand_sig

        if best_similarity > 0.8:
            # Considered matched (partial mismatch handled by text comparison elsewhere)
            continue

        # Truly missing zone! Map the reference bbox to candidate coordinates
        expected_cand_bbox = registration.map_bbox(ref_sig.bbox)
        msg = f"Information Zone containing '{ref_sig.normalized_text[:40]}' is missing."
        missing_zones.append((ref_sig.bbox, expected_cand_bbox, msg))

    return missing_zones


# --------------------------------------------------------------------------- #
# Fallback BOM Grid Parser
# --------------------------------------------------------------------------- #
def extract_bom_grid(page: fitz.Page, normalizer: Normalizer) -> list[tuple[BBox, pd.DataFrame]]:
    """Extract a grid table from text blocks when page.find_tables fails."""
    words = page.get_text("words")
    if not words:
        return []
    
    runs = []
    for w in words:
        text = w[4].strip()
        bbox = (w[0], w[1], w[2], w[3])
        center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
        runs.append({"text": text, "bbox": bbox, "center": center})
        
    BOM_KEYWORDS = {"item", "qty", "part", "dwg", "drg", "drawing", "desc", "description", "material", "pcs"}
    header_candidates = []
    for r in runs:
        norm = normalizer.normalize(r["text"]).lower()
        if any(kw in norm for kw in BOM_KEYWORDS):
            header_candidates.append(r)
            
    if not header_candidates:
        return []
        
    header_rows = []
    used = set()
    for i, r1 in enumerate(header_candidates):
        if i in used:
            continue
        row = [r1]
        for j, r2 in enumerate(header_candidates[i+1:]):
            idx = i + 1 + j
            if idx in used:
                continue
            dy = abs(r1["center"][1] - r2["center"][1])
            if dy < 12.0:
                row.append(r2)
                used.add(idx)
        if len(row) >= 2:
            header_rows.append(row)
            
    if not header_rows:
        return []
        
    best_header_row = max(header_rows, key=len)
    best_header_row = sorted(best_header_row, key=lambda r: r["center"][0])
    
    h_xs = [r["bbox"][0] for r in best_header_row] + [r["bbox"][2] for r in best_header_row]
    h_ys = [r["bbox"][1] for r in best_header_row] + [r["bbox"][3] for r in best_header_row]
    header_y_min, header_y_max = min(h_ys), max(h_ys)
    header_x_min, header_x_max = min(h_xs), max(h_xs)
    
    col_borders = []
    for i in range(len(best_header_row)):
        col_borders.append(best_header_row[i]["bbox"][0])
    col_borders.append(header_x_max + 10.0)
    
    table_runs = []
    for r in runs:
        cx, cy = r["center"]
        if header_x_min - 15.0 <= cx <= header_x_max + 15.0:
            table_runs.append(r)
            
    above_count = sum(1 for r in table_runs if r["center"][1] < header_y_min - 5.0)
    below_count = sum(1 for r in table_runs if r["center"][1] > header_y_max + 5.0)
    
    is_upward = above_count >= below_count
    
    if is_upward:
        table_runs = [r for r in table_runs if r["center"][1] <= header_y_max + 5.0]
    else:
        table_runs = [r for r in table_runs if r["center"][1] >= header_y_min - 5.0]
        
    if not table_runs:
        return []
        
    table_runs = sorted(table_runs, key=lambda r: r["center"][1])
    
    rows = []
    current_row = [table_runs[0]]
    for r in table_runs[1:]:
        dy = r["center"][1] - current_row[-1]["center"][1]
        if dy > 12.0:
            rows.append(current_row)
            current_row = [r]
        else:
            current_row.append(r)
    rows.append(current_row)
    
    parsed_rows = []
    for row in rows:
        row_data = [""] * (len(col_borders) - 1)
        for r in row:
            cx = r["center"][0]
            for col_idx in range(len(col_borders) - 1):
                if col_borders[col_idx] - 10.0 <= cx < col_borders[col_idx + 1] + 10.0:
                    if row_data[col_idx]:
                        row_data[col_idx] += " " + r["text"]
                    else:
                        row_data[col_idx] = r["text"]
                    break
        if any(cell for cell in row_data):
            parsed_rows.append(row_data)
            
    if not parsed_rows:
        return []
        
    headers = [r["text"] for r in best_header_row]
    clean_rows = []
    for row in parsed_rows:
        row = row[:len(headers)]
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))
        clean_rows.append(row)
        
    df = pd.DataFrame(clean_rows, columns=headers)
    
    t_xs = [r["bbox"][0] for r in table_runs] + [r["bbox"][2] for r in table_runs]
    t_ys = [r["bbox"][1] for r in table_runs] + [r["bbox"][3] for r in table_runs]
    table_bbox = (min(t_xs), min(t_ys), max(t_xs), max(t_ys))
    
    return [(table_bbox, df)]
