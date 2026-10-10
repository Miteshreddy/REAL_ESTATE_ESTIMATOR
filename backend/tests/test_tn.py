"""Tamil Nadu-only scope, TN rate data, ingestion parsers, floors, rooms, scale, feet-inch dimensions."""
from __future__ import annotations

import pytest

from conftest import new_project


# ------------------------------------------------------------------ scope / resolver
def test_only_tn_is_offered_and_resolved(env):
    _, c = env
    L = c.get("/api/locations").json()
    assert [r["name"] for r in L["countries"][0]["regions"]] == ["Tamil Nadu"] and "Chennai" in L["countries"][0]["districts"]
    p = new_project(c, dict(district="Madurai"))
    s = p["rate_source"]["schedule"]
    assert s and s["region"] == "Tamil Nadu" and s["code_system"] == "TN-SOR"
    assert p["loc"]["region"] == "Tamil Nadu"


def test_other_states_rejected(env):
    _, c = env
    r = c.post("/api/projects", data=dict(name="x", sample="compact_home.dxf", loc='{"region": "Telangana"}'))
    assert r.status_code == 400 and "Tamil Nadu" in r.text


def test_non_tn_schedules_inactive(env):
    A, c = env
    act = [s for s in c.get("/api/rate-schedules").json() if s["status"] == "active"]
    assert act and all(s["region"] == "Tamil Nadu" for s in act)


def test_quantities_independent_of_location(env):
    _, c = env
    q = [{i["key"]: i["qty"] for i in new_project(c, dict(district=d))["estimate"]["items"]} for d in ("Chennai", "Salem")]
    assert q[0] == q[1]


def test_rate_provenance_and_amendment(env):
    _, c = env
    p = new_project(c, {})
    fv = next(i for i in p["estimate"]["items"] if i["key"] == "floor_vit")
    assert fv["rate"] is not None and fv["rate_provenance"]["kind"] == "TN Standard Data analysis"
    comps = {x["ref"]: x for x in fv["rate_provenance"]["components"]}
    assert comps["M-0219"]["rate"] == 884.0  # amended tile rate (08.08.2025), not the base 982
    st = c.get("/api/tnpwd/status").json()
    assert st["active"]["financial_year"] == "2025-26" and st["active"]["item_count"] > 3000


def test_tnpwd_search(env):
    _, c = env
    r = c.get("/api/tnpwd/search", params=dict(q="plastering cement mortar 1:6")).json()
    assert isinstance(r, list)


# ------------------------------------------------------------------ ingestion units (no network)
def test_document_classifier():
    from tnpwd_ingestion.document_classifier import classify_title
    a = classify_title("Schedule of rates 2025-26 - Vol - I w.e.f 22 Jul 2025")
    assert a["doc_type"] == "sor" and a["financial_year"] == "2025-26" and a["effective_from"] == "2025-07-22"
    assert classify_title("SOR 2025-26 Tiles Rate Ammendment")["doc_type"] == "sor_amendment"
    assert classify_title("Standard Data Book wef 26.03.2025")["doc_type"] == "standard_data"


def test_version_diff_and_amendment_apply():
    from tnpwd_ingestion import version_manager as V
    old = [dict(code="M-0001", description="Cement", unit="tonne", rate=5600.0), dict(code="M-0002", description="Steel", unit="tonne", rate=55000.0)]
    new = [dict(code="M-0001", description="Cement", unit="tonne", rate=5800.0), dict(code="M-0003", description="Brick", unit="1000 each", rate=7000.0)]
    d = V.diff(old, new)["summary"]
    assert d == dict(added=1, removed=1, rate_changed=1, renamed=0)
    items, ap = V.apply_amendment(old, [dict(code="M-0001", rate=5500.0)])
    assert next(i for i in items if i["code"] == "M-0001")["rate"] == 5500.0 and ap[0]["old"] == 5600.0


def test_validator_rejects_bad_extraction():
    from tnpwd_ingestion.validator import validate_rates
    assert not validate_rates([dict(code="M-0001", description="x", unit="kg", rate=1.0, page=1)])["ok"]


def test_heading_strip():
    from tnpwd_ingestion.rate_parser import strip_heading
    assert strip_heading("Steel A. BRICKS AND TILE PRODUCTS Second Class")[0] == "Steel"
    assert strip_heading("Supply of No. 8 wire")[1] is False


def test_rate_analysis_units_and_additions():
    from tnpwd_ingestion.rate_analysis import Resolver, price_variant
    sor = [dict(code="M-0001", description="Cement", unit="tonne", rate=5000.0), dict(code="L-0001", description="Mason I Class", unit="day", rate=1000.0)]
    v = dict(components=[dict(qty=500.0, unit="kg", name="Cement", per="MT"), dict(qty=1.0, unit="Nos.", name="Mason I Class", per="Each")],
             per_qty=10.0, per_unit="sq.m", additions=[dict(text="Add water charges @1% of Sub Total X", pct=1.0)])
    p = price_variant(v, Resolver(sor, []))
    assert p["complete"] and abs(p["rate"] - (500 / 1000 * 5000 + 1000) / 10 * 1.01) < 0.01


def test_wastage_addition_not_applied_blindly():
    from tnpwd_ingestion.rate_analysis import Resolver, price_variant
    v = dict(components=[dict(qty=1.0, unit="kg", name="Cement", per="MT")], per_qty=1, per_unit="sq.m",
             additions=[dict(text="Add 10% wastage 0.46 Kg", pct=10.0)])
    assert not price_variant(v, Resolver([dict(code="M-0001", description="Cement", unit="tonne", rate=5000.0)], []))["complete"]


# ------------------------------------------------------------------ drawing intelligence
@pytest.mark.parametrize("texts,expect", [
    (["BLOCK-A:REFUGEFLOOR(1STH,2STH&3STHFL0OR)"], [18, 28, 38]),
    (["18TH,28TH", "3BHK West 1123", "&38TH", "FLOOR"], [18, 28, 38]),
    (["TYPICAL FLOOR PLAN (5TH TO 12TH)"], list(range(5, 13))),
    (["FLOOR NOS. 3, 5, 7"], [3, 5, 7]),
    (["FIRST AND SECOND FLOOR PLAN"], [1, 2]),
    (["GROUND FLOOR PLAN"], [0]),
])
def test_floor_occurrences(texts, expect):
    import floors
    assert floors.parse(texts)["floor_occurrences"] == expect


def test_typical_without_numbers_and_no_false_floors():
    import floors
    t = floors.parse(["TYPICAL FLOOR PLAN"])
    assert t["typical_floor"] and t["repeated_count"] is None
    assert floors.parse(["3BHK 1711 Sft", "BED ROOM 12'0\" x 13'6\"", "18, 28, 38"]) is None


def test_plan_multiplier_uses_occurrences():
    import takeoff
    plans = [dict(floor=dict(level=0, repeat=1)), dict(floor=dict(level=18, repeat=3), floor_info=dict(floor_occurrences=[18, 28, 38]))]
    assert takeoff.plan_multipliers(plans, 4) == [1, 3]


@pytest.mark.parametrize("raw,label,typ", [("TOIET-2", "TOILET-2", "toilet"), ("TOLET-2", "TOILET-2", "toilet"), ("BED ROOM-1 BEDRO", "BED ROOM-1", "bedroom"),
                                           ("REFUGEAREA", "REFUGE AREA", "refuge"), ("6'6°WIDECORRIDOR", "CORRIDOR", "corridor"), ("1711 Sft. 3BHK", "", "unknown")])
def test_room_normalisation(raw, label, typ):
    import rooms
    l, _ = rooms.normalise(raw)
    assert l == label and rooms.room_type(l) == typ


def test_unit_grouping():
    import rooms
    items = [dict(t="3BHK", x=2, y=2), dict(t="1200 Sft", x=2, y=2.4), dict(t="2BHK", x=20, y=2), dict(t="900 Sft", x=20, y=2.4)]
    rs = [dict(id=f"R{i}", name=n, cx=x, cy=5, area=10) for i, (n, x) in enumerate([("BED ROOM-1", 1), ("KITCHEN", 4), ("BED ROOM-1", 19), ("TOILET", 22), ("LOBBY", 11)])]
    s = rooms.annotate(dict(rooms=rs, text_items=items))
    assert len(s["units"]) == 2 and {u["bhk"] for u in s["units"]} == {3, 2}
    assert next(r for r in s["rooms"] if r["name"] == "LOBBY")["unit"] == "common"


def test_feet_inch_dimensions():
    import nlp
    a, b = nlp.parse_pair("11′ 0* x 12 2*")
    assert abs(a - 3.3528) < 1e-3 and abs(b - 3.7084) < 1e-3
    assert nlp.parse_pair("3.60 X 4.20") == (3.6, 4.2)


def test_downscale_keeps_scale_in_caller_pixels():
    import cv2
    import numpy as np
    import os
    import parsers
    from ml import Models
    img = np.full((1200, 6000), 255, np.uint8)
    cv2.rectangle(img, (500, 200), (5500, 1000), 0, 12)
    cv2.line(img, (3000, 200), (3000, 1000), 0, 12)
    m = Models(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "models"))
    r = parsers.analyze_image_array(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), m, px_per_m=200.0, _words=[])
    assert abs(r["scale"]["px_per_m"] - 200.0) < 0.5 and r["scale"]["analysis_downscale"] < 1
