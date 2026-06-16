"""Acceptance tests (SPEC §9): per-class recall/precision + the encoding-only FP gate."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from comparator.config import Config
from comparator.detect import analyze_page
from comparator.normalize import Normalizer
from comparator.render_compare import RenderComparer
from comparator.report import build_report
from tests import fixtures

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

pytestmark = pytest.mark.skipif(not fixtures.fonts_available(), reason="DejaVu fonts unavailable")


def _run_pair(ref: str, cand: str, config: Config) -> dict:
    normalizer = Normalizer(config)
    comparer = RenderComparer(config)
    ref_doc, cand_doc = fitz.open(ref), fitz.open(cand)
    try:
        defects = []
        for i in range(min(len(ref_doc), len(cand_doc))):
            defects.extend(analyze_page(i + 1, ref_doc[i], cand_doc[i], normalizer, comparer, config))
        return build_report(defects, {"reference": ref, "candidate": cand})
    finally:
        ref_doc.close()
        cand_doc.close()


@pytest.fixture(scope="module")
def config() -> Config:
    return Config.load(CONFIG_PATH)


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory) -> dict:
    return fixtures.make_scenarios(tmp_path_factory.mktemp("fixtures"))


@pytest.fixture(scope="module")
def reports(scenarios, config) -> dict:
    return {name: _run_pair(s["ref"], s["cand"], config) for name, s in scenarios.items()}


@pytest.mark.parametrize("name", [
    "identical", "missing_text", "missing_annotation", "misplacement",
    "overlap", "corruption", "offset", "encoding_only",
])
def test_scenario_exact_classes(name, scenarios, reports):
    expected = sorted(scenarios[name]["expected"])
    got = sorted(d["class"] for d in reports[name]["defects"])
    assert got == expected, f"{name}: expected {expected}, got {got}"


def test_encoding_only_zero_defects(reports):
    """Headline false-positive gate: renders fine, extracts wrong => ZERO defects (SPEC §3/§9)."""
    assert reports["encoding_only"]["defects"] == []


def test_offset_zero_misplacement(reports):
    """Registration must absorb a uniform translation (SPEC §9)."""
    classes = [d["class"] for d in reports["offset"]["defects"]]
    assert "text_misplacement" not in classes
    assert reports["offset"]["defects"] == []


def test_zone_assignment(scenarios, reports):
    for name in ("missing_text", "corruption"):
        exp_zone = scenarios[name]["expected_zone"]
        zones = [d["zone"] for d in reports[name]["defects"]]
        assert exp_zone in zones, f"{name}: expected zone {exp_zone} in {zones}"


def test_zone_and_text_fields_present(reports):
    d = reports["corruption"]["defects"][0]
    assert d["class"] == "font_glyph_corruption"
    assert d["zone"] and d["cause"] and d["fix"]
    assert d["ref_text"] == "1/2" and d["cand_text"] == "1#8"
    assert d["rendered_diff_score"] is not None and d["rendered_diff_score"] >= 0.0


def test_golden_corruption(reports):
    """Committed snapshot guards against silent regressions (SPEC §9 golden tests)."""
    import json
    golden_path = Path(__file__).resolve().parent / "golden" / "corruption.json"
    golden = json.loads(golden_path.read_text())
    assert reports["corruption"]["defects"] == golden


def test_recall_precision_gates(scenarios, reports):
    positives = ["missing_text", "missing_annotation", "misplacement", "overlap", "corruption"]
    tp = fp = fn = 0
    for name, rep in reports.items():
        expected = set(scenarios[name]["expected"])
        got = [d["class"] for d in rep["defects"]]
        for cls in got:
            if cls in expected:
                tp += 1
                expected.discard(cls)  # count one TP per expected class
            else:
                fp += 1
        fn += len(expected)
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    assert recall >= 0.98, f"recall {recall:.3f}"
    assert precision >= 0.99, f"precision {precision:.3f}"
    assert len(positives) == 5
