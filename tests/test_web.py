"""Web UI: folder-batch pairing, report serving, and unmatched handling."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from comparator import web
from tests import fixtures

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

pytestmark = pytest.mark.skipif(not fixtures.fonts_available(), reason="DejaVu fonts unavailable")


@pytest.fixture()
def client(tmp_path):
    # Build a reference + two candidates (one corrupted, one clean), plus an unmatched extra.
    fixtures.build_drawing(str(tmp_path / "ref.pdf"))
    fixtures.build_drawing(str(tmp_path / "good.pdf"))
    fixtures.build_drawing(str(tmp_path / "bad.pdf"), corrupt_target=True)
    app = web.create_app(CONFIG_PATH)
    app.config["TESTING"] = True
    return app.test_client(), tmp_path


def _file(path: Path, name: str):
    return (io.BytesIO(path.read_bytes()), name)


def test_index_serves(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200 and b"Text-Fidelity Comparator" in r.data


def test_compare_pairs_and_serves_report(client):
    c, tmp = client
    data = {
        "reference": [_file(tmp / "ref.pdf", "A.pdf"), _file(tmp / "ref.pdf", "B.pdf")],
        "candidate": [_file(tmp / "good.pdf", "A.pdf"), _file(tmp / "bad.pdf", "B.pdf"),
                      _file(tmp / "good.pdf", "ORPHAN.pdf")],
    }
    r = c.post("/compare", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()

    pairs = {p["name"]: p for p in body["pairs"]}
    assert set(pairs) == {"A.pdf", "B.pdf"}
    assert pairs["A.pdf"]["status"] == "clean" and pairs["A.pdf"]["defect"] == 0
    assert pairs["B.pdf"]["status"] == "defect" and pairs["B.pdf"]["defect"] >= 1
    assert body["unmatched_candidate"] == ["ORPHAN.pdf"]
    assert body["unmatched_reference"] == []

    # The served report HTML is reachable.
    rep = c.get(pairs["B.pdf"]["report_url"])
    assert rep.status_code == 200 and b"Engineering Drawing QA Compliance Report" in rep.data


def test_compare_requires_matching_names(client):
    c, tmp = client
    data = {
        "reference": [_file(tmp / "ref.pdf", "X.pdf")],
        "candidate": [_file(tmp / "good.pdf", "Y.pdf")],
    }
    r = c.post("/compare", data=data, content_type="multipart/form-data")
    assert r.status_code == 400 and "match" in r.get_json()["error"].lower()
