"""Regression tests from the hospital demo case (synthetic image 'Additional 4th, 5th & 6th Floors'): floor scope, upper-floor
foundation exclusion, assumed-structure policy, opening-count conflicts, scale uncertainty, status model, arithmetic."""
from __future__ import annotations

import json
import os

import pytest

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "demo05_hospital_floors_4_5_6.png")
_cache = {}


def make(c, scope=None):
    data = dict(name="hospital floors", loc='{"district": "Chennai"}')
    if scope:
        data["scope"] = json.dumps(scope)
    p = c.post("/api/projects", data=data).json()
    q = c.post(f"/api/projects/{p['id']}/files", files={"files": ("demo05.png", open(IMG, "rb").read())}).json()
    return q


def plan(q):
    return next(i for i, s in enumerate(q["sheets"]) if s["kind"] == "floor_plan")


def items(q):
    return {i["key"]: i for i in q["estimate"]["items"]}


@pytest.fixture(scope="module")
def hosp(env):
    _, c = env
    if "q" not in _cache:
        _cache["q"] = make(c)
    return c, _cache["q"]


def test_A_fullwidth_ocr_floor_list_and_scope_validation(env, hosp):
    import floors
    assert floors.parse(["Additional 4th，5th&6thFloors-GovernmentPeripheralHospital"])["floor_occurrences"] == [4, 5, 6]
    c, q = hosp
    s = q["sheets"][plan(q)]
    assert s["floor"]["occurrences"] == [4, 5, 6] and q["params"]["floors"] == 3
    assert any(x["code"] == "FLOOR REPEAT NEEDS CONFIRMATION" for x in q["checks"])  # from drawing text, not confirmed
    r = c.patch(f"/api/projects/{q['id']}", json={"scope": {"type": "floors", "config": {"floors_list": "4,5,6,7"}}}).json()
    miss = [x for x in r["checks"] if x["code"] == "SCOPE FLOOR MISSING"]
    assert miss and "7" in miss[0]["message"] and r["params"]["floors"] == 3  # flagged, nothing invented
    r = c.patch(f"/api/projects/{q['id']}/sheets/{plan(r)}", json={"floor": {"label": "Typical floor", "level": 4, "repeat": 3, "occurrences": [4, 5, 6]}}).json()
    assert not any(x["code"] == "FLOOR REPEAT NEEDS CONFIRMATION" for x in r["checks"])
    c.patch(f"/api/projects/{q['id']}", json={"scope": {"type": "property"}})


def test_B_upper_floor_extension_excludes_new_foundation(env, hosp):
    c, q = hosp
    it = items(q)
    for k in ("excavation", "rcc_footing", "pcc_found", "anti_termite", "fw_found", "steel_footing"):
        assert not it[k]["in_scope"] and "upper-floor" in it[k]["exclusion"]["reason"], k
    assert "Earthwork" not in {x["name"] for x in q["estimate"]["categories"]}
    r = c.patch(f"/api/projects/{q['id']}", json={"scope": {"type": "property", "config": {"include_foundation": True}}}).json()
    assert items(r)["excavation"]["in_scope"]  # user explicitly includes foundation work
    c.patch(f"/api/projects/{q['id']}", json={"scope": {"type": "property"}})
    from conftest import new_project
    g = new_project(c, {})  # a ground-floor project keeps its foundation
    assert items(g)["excavation"]["in_scope"]


def test_C_structure_without_structural_drawings_provisional_or_unresolved(env, hosp):
    c, q = hosp
    it = items(q)
    assert it["rcc_column"]["qty_status"] == "PROVISIONAL" and it["rcc_column"]["in_scope"]
    r = c.patch(f"/api/projects/{q['id']}", json={"scope": {"type": "property", "config": {"assumption_policy": "strict"}}}).json()
    ri = items(r)
    assert ri["rcc_column"]["qty_status"] == "UNRESOLVED" and not ri["rcc_column"]["in_scope"]
    assert r["estimate"]["unresolved"] and r["estimate"]["total"] < q["estimate"]["total"]
    assert not r["estimate"]["complete"]
    c.patch(f"/api/projects/{q['id']}", json={"scope": {"type": "property"}})


def test_D_confirmed_opening_counts_flow_into_quantities_and_persist(env, hosp):
    c, q = hosp
    i = plan(q)
    before = items(q)["door_shutter"]["qty"]
    r = c.patch(f"/api/projects/{q['id']}/sheets/{i}", json={"opening_confirmed": {"door": 27, "window": 12}}).json()
    assert r["sheets"][i]["opening_confirmed"] == {"door": 27, "window": 12}
    assert any(x["code"] == "OPENING COUNT CONFIRMED" for x in r["checks"])
    assert not any(x["code"] == "OPENING COUNT CONFLICT" and x.get("kind") in ("door", "window") for x in r["checks"])
    r2 = c.get(f"/api/projects/{q['id']}").json()  # persisted
    assert r2["sheets"][i]["opening_confirmed"] == {"door": 27, "window": 12}
    assert items(r2)["door_shutter"]["qty"] != before or before == 0
    assert c.patch(f"/api/projects/{q['id']}/sheets/{i}", json={"opening_confirmed": {"door": -1}}).status_code == 400
    c.patch(f"/api/projects/{q['id']}/sheets/{i}", json={"opening_confirmed": {}})


def test_E_assumed_scale_propagates_and_can_be_confirmed_or_calibrated(env, hosp):
    c, q = hosp
    i = plan(q)
    assert q["sheets"][i]["areas"]["calibration"]["status"] == "NEEDS REVIEW"
    assert any(x["qty_status"] == "UNVERIFIED SCALE" for x in q["estimate"]["items"])
    r = c.patch(f"/api/projects/{q['id']}/sheets/{i}", json={"scale_confirmed": True}).json()
    assert r["sheets"][i]["areas"]["calibration"]["status"] == "USER-CONFIRMED"
    assert any(x["qty_status"] == "UNVERIFIED SCALE" for x in r["estimate"]["items"])  # accepted ≠ measured
    c.patch(f"/api/projects/{q['id']}/sheets/{i}", json={"scale_confirmed": False})
    import areas
    assert areas.calibration(dict(source="image", scale=dict(method="calibrated by user — auto: x")))["status"] == "MEASURED"


def test_F_priced_is_not_complete_and_lift_is_visible(env, hosp):
    _, q = hosp
    ss = q["stats"]["status_summary"]
    assert ss["status"] == "PRELIMINARY"
    assert any("Lift" in r for r in ss["reasons"]) and "Lift / elevator" in ss["identified_not_quantified"]
    assert ss["quantity"]["PROVISIONAL"]["lines"] > 0 and ss["rate"]["ESTIMATED"]["lines"] > 0


def test_H_arithmetic_reconciles(env, hosp):
    _, q = hosp
    e = q["estimate"]
    for i in e["items"]:
        if i["rate"] is not None:
            assert abs(i["amount"] - round(i["qty"] * i["rate"], 2)) <= 0.02, i["key"]
    counted = [i for i in e["items"] if i["in_scope"]]
    assert abs(sum(i["amount"] for i in counted) - e["subtotal"]) < 0.05
    assert abs(sum(x["amount"] for x in e["categories"]) - e["subtotal"]) < 0.05
    assert abs(e["total"] - (e["subtotal"] + e["contingency"] + e["cess"] + e["gst"])) < 0.05


def test_legend_artefacts_and_detector_traceability(env, hosp):
    _, q = hosp
    s = q["sheets"][plan(q)]
    assert len(s["rooms"]) == 18 and len(s.get("discarded_rooms") or []) == 2
    assert s.get("detector_model", "").endswith(".onnx")


def test_mix_ratio_next_to_floor_note_is_not_a_floor_range():
    """TNRD school sheet: 'P.C.C 1:4:8-100mm THICK' beside 'FLOOR FINISHING' was read as floors 8-100 (93 storeys)."""
    import floors
    texts = ["GLPC.C1:4:8-100mm THICK BRICK WORK IN C.M 1:5", "P.C.C 1:4:8-100mm THICK", "DATE",
             "2.FLOOR FINISHING SHOULD BE DONE USING CERAMIC TILES(FOR CLASS ROOMS ONLY)."]
    assert floors.parse(texts) is None
    assert floors.parse(["FLOORS 5 - 12"])["floor_occurrences"] == list(range(5, 13))
    assert floors.parse(["TYPICAL FLOOR PLAN (5TH TO 12TH)"])["floor_occurrences"] == list(range(5, 13))


def test_basement_fill_note_is_not_a_basement_floor():
    import floors
    assert floors.parse(["BASEMENT CONCRETE 1:5:10", "BASEMENT HEIGHT 600"]) is None
    assert floors.parse(["BASEMENT FLOOR PLAN"])["floor_occurrences"] == [-1]


def test_reinforcement_detail_sheet_is_not_a_floor_plan():
    import app
    det = dict(texts=["COLUMN BARS STRAIGHT", "STIRRUP HANGER", "BEAM BARS PLACED", "BARS STOP SHORT", "BOTTOM BARS",
                      "TOP BARS", "Beam- Column Joint Details"], rooms=[dict(name="SPACE 1")])
    assert app.structural_detail_reason(det)
    assert app.structural_detail_reason(dict(texts=["GROUND FLOOR PLAN", "BARS"] * 4, rooms=[dict(name="KITCHEN")])) is None


def test_sheet_with_two_floor_plan_views_is_flagged():
    """TNRD community hall III: GROUND and FIRST floor plans on one sheet, only one view measured."""
    import quality
    s = dict(texts=["FIRST FLOOR PLAN", "GROUNDFLOORPLAN", "FIRST FLOOR -202.43SQ.M"])
    assert quality.multi_plan_views(s) == ["Ground floor plan", "First floor plan"]
    assert quality.multi_plan_views(dict(texts=["GROUND FLOOR PLAN", "SECTION A-A"])) == ["Ground floor plan"]
