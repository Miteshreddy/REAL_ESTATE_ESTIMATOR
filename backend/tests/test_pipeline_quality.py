"""Dataset tooling (dedup, licence, leakage), opening pipeline, checks, completeness, assumptions, scale, uploads, registry."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
import pytest

from conftest import new_project

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _plan(seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((800, 1000), 255, np.uint8)
    for _ in range(12):
        x0, y0 = rng.integers(50, 700), rng.integers(50, 500)
        cv2.rectangle(img, (int(x0), int(y0)), (int(x0 + rng.integers(80, 250)), int(y0 + rng.integers(80, 250))), 0, 4)
    return img


# ------------------------------------------------------------------ dedup / licence / leakage
def test_dedup_catches_resized_and_cropped_copies_not_other_drawings():
    from tn_data_ingestion import dedup
    a = _plan(1)
    b = cv2.resize(a, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA)
    c = cv2.copyMakeBorder(a, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    d = _plan(2)
    page = lambda img, sha: dict(sha256=sha, page=1, dhash=dedup.dhash(img), text_sig=set())
    assert dedup.near_duplicate(page(a, "x"), page(b, "y"))
    assert dedup.near_duplicate(page(a, "x"), page(c, "z"))
    assert dedup.near_duplicate(page(a, "x"), page(d, "w")) is None


def test_licence_rules():
    from tn_data_ingestion import license_check as L
    assert L.status("tnrera", robots_allowed=False)["status"] == "disallowed"
    assert L.status(None, "https://example.com/a.pdf")["status"] == "review"
    assert not L.usable_for("review", "01_DRAWING_TRAINING") and L.usable_for("client_permission", "01_DRAWING_TRAINING") and not L.usable_for("government_publication_review", "01_DRAWING_TRAINING")


def test_leakage_checker_fails_on_planted_leak():
    ds = tempfile.mkdtemp()
    for d in ("metadata", "train", "validation", "unseen_test"):
        os.makedirs(os.path.join(ds, d))
    pages = {"a-p1": dict(page_id="a-p1", sha256="s1", page=1, file="x.pdf", dhash=1, text_sig=[]),
             "b-p1": dict(page_id="b-p1", sha256="s1", page=1, file="x.pdf", dhash=1, text_sig=[])}
    json.dump(pages, open(os.path.join(ds, "metadata", "pages.json"), "w"))
    json.dump({"P1": {}, "P2": {}}, open(os.path.join(ds, "metadata", "projects.json"), "w"))
    json.dump(dict(projects=["P1"], pages=["a-p1"]), open(os.path.join(ds, "train", "manifest.json"), "w"))
    json.dump(dict(projects=["P2"], pages=["b-p1"]), open(os.path.join(ds, "unseen_test", "manifest.json"), "w"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "ml", "dataset", "check_leakage.py"), ds], capture_output=True, text=True)
    assert r.returncode == 1 and "file hash" in r.stdout


def test_real_dataset_has_no_leakage():
    if not os.path.exists(os.path.join(ROOT, "data", "tn_dataset", "metadata", "pages.json")):
        pytest.skip("dataset not built")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "ml", "dataset", "check_leakage.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-800:]


# ------------------------------------------------------------------ openings
def test_opening_enrichment_and_conflict():
    import openings
    s = dict(sheet="GF", rooms=[dict(id="R1", cx=1, cy=1, room_type="toilet"), dict(id="R2", cx=3, cy=1, room_type="bedroom", unit="U1")],
             openings=[dict(kind="door", x=2, y=1, w=0.75, ext=False), dict(kind="window", x=1, y=0, w=0.6, ext=True)],
             schedule={"D1": dict(w=0.9, h=2.1, count=5, kind="door"), "W1": dict(w=1.2, h=1.2, count=None, kind="window")}, detector_counts=dict(door=1, window=4))
    openings.enrich(s)
    d, w = s["openings"]
    assert d["type"] == "toilet" and d["room_from"] in ("R1", "R2") and d["unit"] == "U1" and d["host_wall"] == "internal"
    assert w["type"] == "ventilator" and w["host_wall"] == "external"
    c = openings.reconcile(s)
    assert {x["kind"] for x in c} == {"door", "window"} and all(x["code"] == "OPENING COUNT CONFLICT" for x in c)


# ------------------------------------------------------------------ checks / completeness / assumptions
def test_quality_checks_completeness_assumptions(env):
    _, c = env
    p = new_project(c, {})
    codes = {x["code"] for x in p["checks"]}
    assert "STRUCTURAL INPUT MISSING" in codes
    comp = p["stats"]["completeness"]
    assert comp["total"] == len(p["estimate"]["items"]) and comp["priced"] + comp["unresolved"] == comp["total"]
    assert comp["text"] == f"{comp['priced']} / {comp['total']} items priced"
    ids = {a["assumption_id"] for a in p["assumptions"]}
    assert "A-FOOTING" in ids and any(a["classification"] == "DEFAULT" for a in p["assumptions"])
    assert all(i["review_level"] in ("green", "yellow", "red") for i in p["estimate"]["items"])
    assert all(i["review_level"] == "red" for i in p["estimate"]["items"] if i["rate"] is None)


def test_storey_count_required_and_room_area_error():
    import quality
    s = dict(kind="floor_plan", sheet="T", floor_info=dict(typical_floor=True, floor_occurrences=[]),
             rooms=[dict(area=200.0, room_type="bedroom")] * 5, metrics=dict(plinth_area=100.0), openings=[])
    p = dict(sheets=[s], params={"floors": 1, "floor_height": 3.0, "_src": {}})
    codes = {x["code"] for x in quality.checks(p, dict(items=[]))}
    assert {"STOREY COUNT REQUIRED", "ROOM AREA > BUILDING AREA", "DOOR COUNT LOW", "NO WINDOWS"} <= codes


def test_room_area_prefers_written_dimensions():
    import rooms
    s = rooms.annotate(dict(rooms=[dict(id="R1", name="BED ROOM", area=10.0, label_dims=(3.0, 4.0), cx=0, cy=0)]))
    r = s["rooms"][0]
    assert r["area"] == 12.0 and r["polygon_area"] == 10.0 and r["area_basis"] == "explicit dimensions"


# ------------------------------------------------------------------ scale / uploads / registry
@pytest.mark.parametrize("txt,den,nts", [("SCALE 1:100", 100, False), ("SCALE = 1/50", 50, False), ("1:125", 125, False), ("NOT TO SCALE", None, True), ("N.T.S", None, True)])
def test_scale_parsing(txt, den, nts):
    import nlp
    n = nlp.parse_project_notes([txt])
    assert n.get("scale_den") == den and bool(n.get("nts")) == nts


def test_upload_validation_rejects_disguised_file(env):
    _, c = env
    r = c.post("/api/projects", data=dict(name="x", loc="{}"), files={"files": ("plan.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")})
    assert r.status_code == 400 and "does not match" in r.text


def test_registry_refuses_downgrade():
    import shutil
    reg = os.path.join(ROOT, "data", "models", "registry.json")
    bak = reg + ".testbak"
    shutil.copy(reg, bak)
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "ml", "training", "register_model.py"), "floorplan_unet", "x.onnx", "miou_fg", "0.10"],
                           capture_output=True, text=True)
        assert "REJECTED" in r.stdout
        assert json.load(open(reg))["models"][0]["file"] == "floorplan_unet.onnx"
    finally:
        shutil.move(bak, reg)


def test_robots_wildcards_respected():
    from tnpwd_ingestion import downloader as d
    d._robots["https://example.test"] = (["/files/public/"], ["/uploads/", "/*.pdf$", "/private"])
    assert not d.allowed("https://example.test/homePageFiles/a.pdf")
    assert not d.allowed("https://example.test/uploads/x.png")
    assert d.allowed("https://example.test/about")
    assert d.allowed("https://example.test/a.pdf?x=1")  # '$' anchors the end of the path+query
    assert d.allowed("https://example.test/files/public/x.png")


def test_detector_model_is_working():
    import glob
    import detector
    if not detector.available():
        pytest.skip("opening detector not installed")
    imgs = sorted(glob.glob(r"G:/velo/real-estate/prepared_det/images/test/*.png"))[:3]
    if not imgs:
        pytest.skip("test images not available on this machine")
    tp = n_gt = n_pr = 0
    for f in imgs:
        im = cv2.imread(f)
        H, W = im.shape[:2]
        gt = [(int(c), float(x) * W, float(y) * H) for c, x, y, *_ in (l.split() for l in open(f.replace("images", "labels")[:-4] + ".txt"))]
        pr = [(0 if d["kind"] == "door" else 1, d["x_px"], d["y_px"]) for d in detector.detect(im, detector.TARGET_PPM)]
        n_gt, n_pr = n_gt + len(gt), n_pr + len(pr)
        used = set()
        for c, x, y in pr:
            m = [i for i, (gc, gx, gy) in enumerate(gt) if gc == c and i not in used and abs(gx - x) < 12 and abs(gy - y) < 12]
            if m:
                used.add(m[0])
                tp += 1
    assert tp / max(1, n_pr) > 0.8 and tp / max(1, n_gt) > 0.8
    reg = json.load(open(os.path.join(ROOT, "data", "models", "registry.json")))
    e = next(m for m in reg["models"] if m["model_name"] == "opening_det")
    assert e["test_score"]["door_f1"] > 0.8 and "NOT MEASURED" in e["unseen_tn_metrics"]


def test_no_control_characters_in_source():
    """Regression: '\b' written through a shell became a literal backspace, silently breaking regexes."""
    import glob
    import re as _re
    bad = []
    for f in glob.glob(os.path.join(ROOT, "backend", "**", "*.py"), recursive=True) + glob.glob(os.path.join(ROOT, "ml", "**", "*.py"), recursive=True):
        if _re.search(rb"[\x01-\x08\x0b\x0c\x0e-\x1f]", open(f, "rb").read()):
            bad.append(f)
    assert not bad, bad
