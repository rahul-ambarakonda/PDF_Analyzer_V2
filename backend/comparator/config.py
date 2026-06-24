"""Configuration loading (SPEC §7).

All tunables live in ``config.yaml``; this module loads and validates them into a
typed ``Config`` object. No magic numbers belong in code that this file externalizes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ZoneConfig:
    margin_band_frac: float = 0.06
    row_first: bool = True
    title_block_frac: float = 0.33


@dataclass
class Config:
    render_dpi: int = 300
    position_tolerance_pts: float = 3.0
    overlap_ratio_threshold: float = 0.15
    pixel_diff_threshold: float = 0.12
    confidence_threshold: float = 0.50

    match_max_cost: float = 60.0
    match_position_weight: float = 1.0
    match_string_weight: float = 40.0

    cluster_gap_pts: float = 12.0
    leader_gap_pts: float = 6.0

    registration_min_anchors: int = 3
    registration_multi_view: bool = True      # discover one local affine per drawing view
    registration_min_view_anchors: int = 3    # min inliers for a view to get its own transform
    registration_max_views: int = 16          # cap on local models per sheet

    zone: ZoneConfig = field(default_factory=ZoneConfig)
    ignore_regions: list[list[float]] = field(default_factory=list)

    symbol_equivalences: list[list[str]] = field(default_factory=list)
    strip_trailing_zeros: bool = True
    decimal_separator_equiv: bool = True
    collapse_whitespace: bool = True
    case_insensitive: bool = False

    cv_alignment_method: str = "orb"
    cv_min_contour_area: float = 10.0
    dbscan_eps_pts: float = 50.0
    dbscan_min_samples: int = 1

    templates: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        zone_data = data.get("zone", {}) or {}
        zone = ZoneConfig(
            margin_band_frac=float(zone_data.get("margin_band_frac", 0.06)),
            row_first=bool(zone_data.get("row_first", True)),
            title_block_frac=float(zone_data.get("title_block_frac", 0.33)),
        )
        known = {
            "render_dpi", "position_tolerance_pts", "overlap_ratio_threshold",
            "pixel_diff_threshold", "confidence_threshold", "match_max_cost",
            "match_position_weight", "match_string_weight", "cluster_gap_pts",
            "leader_gap_pts", "registration_min_anchors", "registration_multi_view",
            "registration_min_view_anchors", "registration_max_views", "ignore_regions",
            "symbol_equivalences", "strip_trailing_zeros", "decimal_separator_equiv",
            "collapse_whitespace", "case_insensitive", "templates",
            "cv_alignment_method", "cv_min_contour_area", "dbscan_eps_pts",
            "dbscan_min_samples",
        }
        kwargs = {k: data[k] for k in known if k in data}
        cfg = cls(zone=zone, **kwargs)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.render_dpi <= 0:
            raise ValueError("render_dpi must be positive")
        for name in ("position_tolerance_pts", "overlap_ratio_threshold",
                     "pixel_diff_threshold", "confidence_threshold", "match_max_cost"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        if self.cv_alignment_method not in ("orb", "ecc"):
            raise ValueError("cv_alignment_method must be either 'orb' or 'ecc'")
        if self.cv_min_contour_area < 0:
            raise ValueError("cv_min_contour_area must be non-negative")
        if self.dbscan_eps_pts <= 0:
            raise ValueError("dbscan_eps_pts must be positive")
        if self.dbscan_min_samples <= 0:
            raise ValueError("dbscan_min_samples must be positive")

    def template_for(self, defect_class: str) -> dict[str, str]:
        return self.templates.get(defect_class, {})

