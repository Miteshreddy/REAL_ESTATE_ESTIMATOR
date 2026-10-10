"""Regression tests for defects found on the TNRD 10 official layouts (no drawings needed; shared logic only)."""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("EST_DATA_DIR", tempfile.mkdtemp(prefix="tnrd10_test_"))
os.environ["EST_NO_DOTENV"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # noqa: E402
import quality  # noqa: E402
import scale_guard  # noqa: E402
import scope  # noqa: E402
import takeoff  # noqa: E402


def test_empty_estimate_is_never_complete():
    """Cremation shed / threshing floor: no plan read, ₹0, and the estimate said COMPLETE."""
    st = quality.status_summary(dict(sheets=[]), dict(items=[], subtotal=0), [], True)
    assert st["status"] == "PRELIMINARY" and "no floor plan was measured" in st["reasons"][0]


def test_open_structure_uses_written_plinth_area_and_invents_nothing():
    sheet = dict(kind="section", rooms=[], texts=["TYPE DESIGN FOR CREMATION SHED", "PLINTH AREA 60 sq.m/645.6 sq.ft", "PLAN"])
    a = app.area_only_plan(sheet)
    assert abs(a - 60.0) < 0.01
    app.apply_area_only(sheet, a)
    assert sheet["kind"] == "floor_plan" and sheet["area_only"] and sheet["rooms"] == [] and sheet["openings"] == []
    m = sheet["metrics"]
    assert m["plinth_area"] == 60.0 and m["L_ext"] == 0 and m["L_int"] == 0 and m["envelope_perimeter"] == 0
    assert "plinth area note" in sheet["scale"]["method"]
    # only plinth-area work counts; roof / walls / frame are unresolved, with the reason
    ctx = scope.context([sheet])
    sc = scope.default()
    assert scope.exclusion(dict(key="pcc_floor", category="Concrete Works"), sc, ctx) is None
    ex = scope.exclusion(dict(key="rcc_slab", category="RCC Works"), sc, ctx)
    assert ex[0] == "unresolved" and "area-only" in ex[1]


def test_area_only_needs_a_plan_label_and_a_written_area():
    assert app.area_only_plan(dict(kind="section", texts=["SECTION A-A", "PLINTH AREA 60 sq.m/645.6 sq.ft"])) is None
    assert app.area_only_plan(dict(kind="section", texts=["PLAN", "ELEVATION"])) is None
    assert app.area_only_plan(dict(kind="floor_plan", rooms=[dict(name="HALL")], texts=["PLAN", "PLINTH AREA 60 sq.m"])) is None


def test_area_only_sheet_set_aside_next_to_a_measured_plan():
    real = dict(kind="floor_plan", rooms=[dict(name="HALL", area=20)], enabled=True)
    ao = dict(kind="floor_plan", area_only=True, rooms=[], enabled=True)
    p = dict(sheets=[real, ao])
    app.reconcile_area_only(p)
    assert ao["kind"] == "other" and "set aside" in ao["area_only_reason"]


def test_written_floor_areas_and_derived_floor():
    """Community hall III: ground and first floor on one sheet; one plan measured; both areas printed."""
    texts = ["PLINTHAREA:GROUNDFL00R-233.83SQ.M/2516.01sq.ft", "FIRST FLOOR -202.43 SQ.M/2178.1497 sq.ft", "FIRST FLOOR PLAN", "GROUNDFLOORPLAN"]
    assert app.written_floor_areas(texts) == {0: 233.83, 1: 202.43}
    r = dict(kind="floor_plan", sheet="Page 1", texts=texts, rooms=[dict(name="HALL", area=100.0, perimeter=40.0)],
             metrics=dict(plinth_area=233.83, carpet_area=200.0, envelope_perimeter=62.0, L_ext=62.0, L_int=30.0, t_ext=0.23, t_int=0.115),
             floor_info=dict(floor_occurrences=[1], label="First floor"), scale=dict(method="from the plinth area note (233.83 m²)"))
    extra = app.derived_floors(r)
    assert r["floor"]["level"] == 0 and r["floor_info"]["floor_occurrences"] == [0]  # matched by area, not by the "FIRST FLOOR" text
    assert len(extra) == 1 and extra[0]["floor"]["level"] == 1 and extra[0]["metrics"]["plinth_area"] == 202.43
    k2 = 202.43 / 233.83
    assert abs(extra[0]["rooms"][0]["area"] - 100 * k2) < 0.01 and abs(extra[0]["metrics"]["L_ext"] - 62 * k2 ** 0.5) < 0.01
    assert extra[0]["scale"]["method"].startswith("derived floor:")
    # a derived floor is never presented as measured
    import areas
    assert areas.calibration(extra[0])["status"] == "NEEDS REVIEW"
    # each floor counted once
    assert takeoff.plan_multipliers([r, extra[0]], 2) == [1, 1]


def test_derived_floor_needs_an_area_match():
    r = dict(kind="floor_plan", texts=["GROUND FLOOR - 233.83 SQ.M", "FIRST FLOOR - 202.43 SQ.M"], rooms=[dict(name="X", area=10)],
             metrics=dict(plinth_area=150.0))
    assert app.derived_floors(r) == [] and "floor" not in r  # no written area matches the measured plan: do not guess


def test_user_set_floor_wins_over_text_reading_in_quantities():
    a = dict(floor=dict(level=0, occurrences=[0]), floor_info=dict(floor_occurrences=[1]))
    b = dict(floor=dict(level=1, occurrences=[1]), floor_info=dict(floor_occurrences=[1]))
    assert takeoff.plan_multipliers([a, b], 2) == [1, 1]  # was [2, 0]: the text reading overrode the set floor


def test_room_size_check_ignores_large_public_rooms():
    """A community hall's 150 m² HALL is not a wrong scale; only implausibly small rooms are."""
    big = dict(rooms=[dict(name="HALL", area=150), dict(name="KITCHEN", area=20), dict(name="TOILET", area=8), dict(name="DINING", area=40)])
    assert scale_guard.prior_factor(big) is None
    tiny = dict(rooms=[dict(name="BED-1", area=4), dict(name="KITCHEN", area=2.5), dict(name="HALL", area=4.3), dict(name="BED-2", area=3.9)])
    assert scale_guard.prior_factor(tiny) is not None


def test_area_only_needs_agreeing_units():
    """Kitchen shed at low resolution: OCR read only 'PLINTH AREA :2' and the area-only rule used 2 m²."""
    assert app.area_only_plan(dict(kind="section", texts=["PLAN", "450 2100 HEIGHT PLINTH AREA :2"])) is None
    assert app.area_only_plan(dict(kind="section", texts=["PLAN", "PLINTH AREA : 20.62 SQM/221.87 SFT."])) == 20.62
