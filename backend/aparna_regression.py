"""Aparna regression (mandatory fixture): the same drawing before (stored project, old pipeline) and after (current
pipeline). Expected values are NOT hard-coded here — the reference is what the drawing itself prints (the area-statement
table: flat count and carpet areas, the floor list), and every number is reported as measured.

Usage: python aparna_regression.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

import floors
import parsers
import rooms as rooms_mod
import takeoff
import tn_pricing
from ml import Models

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PID = "cb7ba5a5cf"
IMG = os.path.join(ROOT, "data", "uploads", PID, "3 - Block-A-Refuge-Floor-Plan-1780466106344-46de52dc.jpg")
# reference printed ON the drawing (area statement table, bottom right): flats 2-6 are 3BHK with these carpet areas (sq ft);
# flat 1 is the refuge unit. Used only to report agreement — never fed to the pipeline.
PRINTED = dict(floor_text="18TH, 28TH & 38TH FLOOR", floors=[18, 28, 38], flats_3bhk=5,
               carpet_sft={2: 1341, 3: 1123, 4: 1115, 5: 1242, 6: 1222}, saleable_sft={2: 2001, 3: 1723, 4: 1711, 5: 1882, 6: 1858})


def summarise(sheets, params, label):
    plans = [s for s in sheets if s.get("kind") == "floor_plan"]
    s = plans[0] if plans else sheets[0]
    ops = s.get("openings") or []
    m = s.get("metrics") or {}
    return dict(label=label, floors_param=params.get("floors"), floor_info=s.get("floor_info"), floor=s.get("floor"),
                scale=s.get("scale"), rooms=len(s.get("rooms") or []),
                rooms_named=sum(1 for r in s.get("rooms") or [] if not str(r.get("name", "")).startswith("SPACE")),
                room_types={t: sum(1 for r in s.get("rooms") or [] if r.get("room_type") == t) for t in
                            sorted({r.get("room_type") for r in s.get("rooms") or [] if r.get("room_type")})},
                rejected_regions=len(s.get("rejected_regions") or []), units=s.get("units"),
                doors=sum(1 for o in ops if o["kind"] == "door"), windows=sum(1 for o in ops if o["kind"] == "window"),
                plinth_area_m2=m.get("plinth_area"), carpet_area_m2=m.get("carpet_area"), wall_length_m=round((m.get("L_ext") or 0) + (m.get("L_int") or 0), 1))


def main():
    con = sqlite3.connect(os.path.join(ROOT, "data", "estimate.db"))
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM projects WHERE id=?", (PID,)).fetchone()
    before = summarise(json.loads(row["sheets"]), json.loads(row["params"]), "BEFORE (stored project, previous pipeline)") if row else None
    t0 = time.time()
    sheets = parsers.parse_any(IMG, Models(os.path.join(ROOT, "data", "models")))
    for r in sheets:
        fi = floors.parse(r.get("texts") or [], r.get("title"))
        if fi:
            r["floor_info"] = fi
            if fi.get("floor_occurrences"):
                r["floor"] = dict(label=fi["label"], level=fi["level"], repeat=fi["repeat"], occurrences=fi["floor_occurrences"])
        r.setdefault("kind", "floor_plan" if len(r.get("rooms", [])) >= 2 else "other")
        rooms_mod.annotate(r)
    vals, src = takeoff.derive_params([s for s in sheets if s.get("kind") == "floor_plan"])
    P = {**takeoff.DEFAULT_PARAMS, **vals}
    after = summarise(sheets, P, "AFTER (current pipeline)")
    after["floors_source"] = src.get("floors")
    after["seconds"] = round(time.time() - t0, 1)
    # quantities and TN pricing completeness
    items = takeoff.compute_quantities([s for s in sheets if s.get("kind") == "floor_plan"], P)
    sid = con.execute("SELECT id FROM rate_schedules WHERE region='Tamil Nadu' AND status='active'").fetchone()[0]
    by = {r["code"]: dict(r) for r in con.execute("SELECT code, description, unit, rate FROM rate_items WHERE schedule_id=?", (sid,))}
    tn_pricing.price_items(con, items, by, dict(financial_year="2025-26"))
    est = takeoff.price(items, by, {}, P)
    after["items"] = len(est["items"])
    after["priced_items"] = sum(1 for i in est["items"] if i["rate"] is not None)
    after["excluded_items"] = len(est["excluded"])
    after["assumed_items"] = sum(1 for i in items if str(i.get("basis", "")).startswith("assumed"))
    after["total_priced_inr"] = est["total"]
    # agreement with what the drawing prints
    u = after["units"] or []
    agree = dict(floor_occurrences_match=(after.get("floor_info") or {}).get("floor_occurrences") == PRINTED["floors"],
                 units_found=len(u), units_printed=PRINTED["flats_3bhk"],
                 unit_bhk_found=[x.get("bhk") for x in u], unit_area_tags=[x.get("stated_area_sft") for x in u])
    out = dict(printed_reference=PRINTED, before=before, after=after, agreement=agree,
               note="Door / window ground truth is not printed on this drawing (no schedule); counts are reported, not scored.")
    json.dump(out, open(os.path.join(ROOT, "data", "evaluation", "tn", "aparna_regression.json"), "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items()}, indent=1, default=str)[:6000])


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "data", "evaluation", "tn"), exist_ok=True)
    main()
