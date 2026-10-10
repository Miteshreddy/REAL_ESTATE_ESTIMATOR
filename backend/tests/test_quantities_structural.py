"""Tasks 5-9, 11, 15 (SYNTHETIC unit tests — software behaviour, not accuracy claims)."""
from __future__ import annotations

import pytest

from conftest import new_project


# ------------------------------------------------------------------ Task 5 areas
def test_area_definitions_are_distinct_and_traceable():
    import areas
    s = dict(source="vector", scale=dict(method=""), metrics=dict(plinth_area=120.0),
             rooms=[dict(id="R1", name="BED", room_type="bedroom", area=12.0), dict(id="R2", name="LOBBY", room_type="lobby", area=8.0)],
             floor_info=dict(floor_occurrences=[1, 2, 3]))
    a = areas.compute(s)
    assert a["carpet_area"]["value_m2"] == 12.0 and a["common_area"]["value_m2"] == 8.0
    assert a["plinth_area"]["value_m2"] == 120.0 and a["gross_floor_area"]["value_m2"] == 360.0
    assert all(a[k]["definition"] for k in ("carpet_area", "common_area", "plinth_area", "built_up_area", "gross_floor_area"))


def test_assumed_scale_never_measured_and_missing_storeys_flagged():
    import areas
    s = dict(scale=dict(method="auto: external wall thickness 9.0px = 230 mm"), metrics=dict(plinth_area=100.0), rooms=[])
    a = areas.compute(s)
    assert a["calibration"]["status"] == "NEEDS REVIEW" and a["plinth_area"]["status"] == "NEEDS REVIEW"
    assert a["gross_floor_area"]["value_m2"] is None and "STOREY COUNT REQUIRED" in a["gross_floor_area"]["note"]
    f = areas.compute(dict(scale=dict(method="fallback 50 px/m (please calibrate)"), metrics=dict(plinth_area=100.0), rooms=[]))
    assert f["calibration"]["status"] == "UNRESOLVED" and "reason" in f["plinth_area"]


@pytest.mark.parametrize("t,occ", [("BASEMENT FLOOR PLAN", [-1]), ("LEVEL 5", [5]), ("FLOORS 10-20", list(range(10, 21)))])
def test_more_floor_labels(t, occ):
    import floors
    assert floors.parse([t])["floor_occurrences"] == occ


def test_terrace_is_not_a_storey():
    import floors
    r = floors.parse(["TERRACE FLOOR PLAN"])
    assert r["floor_kind"] == "terrace" and r["repeat"] == 0


# ------------------------------------------------------------------ Task 7 walls
def test_wall_quantities_formulas_and_status():
    import walls
    s = dict(metrics=dict(L_ext=40.0, L_int=20.0, t_ext=0.23, t_int=0.115),
             openings=[dict(kind="window", w=1.2, h=1.5, ext=True), dict(kind="door", w=0.9, h=2.1, ext=False)])
    w = walls.compute(s, dict(floor_height=3.0, slab_thickness=0.15), {"floor_height": "Section A (drawing)"})
    assert w["wall_face_area_external"]["value"] == round(40 * 2.85, 2)
    assert w["masonry_volume_external"]["value"] == round(40 * 2.85 * 0.23 - 1.2 * 1.5 * 0.23, 3)
    assert w["masonry_volume_external"]["status"] == "MEASURED"
    assert w["plaster_area_external"]["value"] == round(40 * 2.85 - 1.8, 2)
    w2 = walls.compute(s, dict(floor_height=3.0, slab_thickness=0.15), {})
    assert w2["masonry_volume_external"]["status"] == "ASSUMED"  # height is a default, never a fact
    w3 = walls.compute(dict(metrics=dict(L_ext=40.0), openings=[]), dict(floor_height=3.0, slab_thickness=0.15), {})
    assert w3["masonry_volume_external"]["status"] == "UNRESOLVED"


# ------------------------------------------------------------------ Task 8 structural
def test_steel_formula_and_no_invented_inputs():
    import structural
    assert structural.bar_kg(10, 12, 1) == pytest.approx(10 * 144 / 162)
    with pytest.raises(ValueError):
        structural.bar_kg(None, 12, 1)


def test_bbs_parsing_and_no_false_rows():
    import structural
    rows = structural.parse_bbs(["C1 a 16 4 3450", "B2 M3 T12 6 4.20 M", "BED ROOM 3600 X 4200", "SCALE 1:100"])
    assert [(r["member"], r["dia"], r["count"], r["cutting_length_m"]) for r in rows] == [("C1", 16, 4, 3.45), ("B2", 12, 6, 4.2)]
    assert rows[0]["kg"] == round(3.45 * 4 * 256 / 162, 2)


def test_structural_missing_and_schedule_members():
    import structural
    r = structural.compute([dict(kind="floor_plan", texts=[])], dict(floor_height=3.0), {})
    assert r["status"] == "STRUCTURAL INPUT MISSING" and r["missing"]
    sh = dict(kind="structural", texts=["F1 a Y10 12 1450"], structural=dict(footings=[dict(mark="F1", L=1.5, B=1.5, D=0.45, count=4)],
                                                                         columns=[dict(mark="C1", b=0.23, d=0.45, count=None)], beams=[], slabs=[]))
    r = structural.compute([sh], dict(floor_height=3.0), {})
    f = next(m for m in r["members"] if m["id"] == "F1")
    c = next(m for m in r["members"] if m["id"] == "C1")
    assert f["volume"] == round(1.5 * 1.5 * 0.45 * 4, 3) and f["status"] == "SCHEDULE-DERIVED"
    assert c["volume"] is None and c["status"] == "NEEDS ENGINEER REVIEW"
    assert r["steel_by_member_type"]["footing"]["kg"] == round(1.45 * 12 * 100 / 162, 2)


# ------------------------------------------------------------------ Task 9 site plans
def test_site_plan_never_costed(env):
    A, c = env
    assert A.site_plan_reason(dict(texts=["Site Layout", "Scale - 1:2000"]))
    assert A.site_plan_reason(dict(texts=["MASTER PLAN OF CAMPUS"]))
    assert not A.site_plan_reason(dict(texts=["SITE LAYOUT", "GROUNDFLOORPLAN", "SCALE-1:200"]))  # mixed sheet keeps its floor plan


# ------------------------------------------------------------------ Task 11 mapping review
def test_mapping_review_unit_guard_and_priority(env):
    _, c = env
    p = new_project(c, {})
    q = c.get(f"/api/projects/{p['id']}/mapping-review").json()
    assert q["evaluation"]["status"] == "NOT VALIDATED"
    r = c.post(f"/api/projects/{p['id']}/mapping-review", json=dict(key="door_shutter", unit="sqm", code="M-0398", reviewer="Er. Test", decision="approve"))
    assert r.status_code == 422 and "unit mismatch" in r.text  # M-0398 is per metre
    r = c.post(f"/api/projects/{p['id']}/mapping-review", json=dict(key="door_shutter", unit="sqm", code="M-0387", reviewer="Er. Test", decision="approve"))
    assert r.status_code == 200
    d = next(i for i in c.get(f"/api/projects/{p['id']}").json()["estimate"]["items"] if i["key"] == "door_shutter")
    assert d["sor_code"] == "M-0387" and "engineer-approved" in d["map_check"]
    ev = c.get(f"/api/projects/{p['id']}/mapping-review").json()["evaluation"]
    assert ev["status"] == "INSUFFICIENT DATA" and ev["reviewed_items"] == 1


# ------------------------------------------------------------------ Task 15 confidence
def test_confidence_labels_and_estimate_never_high_when_incomplete(env):
    _, c = env
    p = new_project(c, {})
    labels = {i["confidence_label"] for i in p["estimate"]["items"]}
    assert labels <= {"HIGH CONFIDENCE", "NEEDS REVIEW", "LOW CONFIDENCE", "INSUFFICIENT INPUT"}
    assert all(i["confidence_label"] == "INSUFFICIENT INPUT" for i in p["estimate"]["items"] if i["rate"] is None)
    ec = p["stats"]["estimate_confidence"]
    assert ec["label"] != "HIGH CONFIDENCE" and "NOT CALIBRATED" in ec["calibration"]


def test_report_discloses_confidence_structure_areas(env):
    _, c = env
    p = new_project(c, {})
    html = c.get(f"/api/projects/{p['id']}/report").text
    # "PRICE COMPLETENESS n/n" was replaced by the status model (priced ≠ validated): estimate status + quantity / rate status tables
    for s in ("Estimate status", "Quantity status", "Rate source", "Estimate confidence", "NOT CALIBRATED", "Structural:", "carpet area", "gross floor area"):
        assert s in html, s


def test_standard_data_approval_is_applied(env):
    _, c = env
    p = new_project(c, {})
    it = next(i for i in p["estimate"]["items"] if i["key"] == "plaster_int")
    sd = it["rate_provenance"]["data_no"]
    r = c.post(f"/api/projects/{p['id']}/mapping-review", json=dict(key="plaster_int", unit=it["unit"], code=f"SD:{sd}", code_unit=it["unit"],
                                                                     reviewer="Er. Test", decision="approve"))
    assert r.status_code == 200, r.text
    d = next(i for i in c.get(f"/api/projects/{p['id']}").json()["estimate"]["items"] if i["key"] == "plaster_int")
    assert d["map_method"] == "engineer-approved" and d["rate"] is not None


def test_review_fixes_regressions(env):
    A, c = env
    import areas
    import boq
    import structural
    # locked estimate: mapping review refused until reopened
    p = new_project(c, {})
    assert c.post(f"/api/projects/{p['id']}/confirm", json=dict(by="t")).status_code == 200
    r = c.post(f"/api/projects/{p['id']}/mapping-review", json=dict(key="wc", unit="each", code="M-0647", reviewer="Er. X", decision="approve"))
    assert r.status_code == 409
    # bare 'campus' in a title block is not a site plan
    assert A.site_plan_reason(dict(texts=["ABC College Campus — Block A Plan"])) is None
    # column height covers all storeys + foundation
    sh = dict(kind="structural", texts=[], structural=dict(footings=[], columns=[dict(mark="C1", b=0.3, d=0.3, count=2)], beams=[], slabs=[]))
    col = structural.compute([sh], dict(floor_height=3.0, floors=4, foundation_depth=1.5, plinth_height=0.6), {})["members"][0]
    assert col["volume"] == round(0.3 * 0.3 * (3.0 * 4 + 1.5 + 0.6) * 2, 3)
    # raster sheet without a scale method is not 'measured'
    assert areas.calibration(dict(source="image", scale={}))["status"] == "NEEDS REVIEW"
    # same description, different units are not duplicates
    v = boq.validate([dict(description="Plaster", quantity=1, unit="sqm"), dict(description="Plaster", quantity=1, unit="cum")],
                     dict(approval_status="provisional", currency="INR"))
    assert v["ok"], v["errors"]
