"""Estimate quality: assumption register, engineering sanity checks, cross-checks, BOQ completeness, review colours."""
from __future__ import annotations

import re

import openings
import takeoff

DEFAULT_DESC = {
    "floor_height": ("Floor-to-floor height", "m"), "plinth_height": ("Plinth height above ground", "m"),
    "foundation_depth": ("Foundation depth below ground", "m"), "slab_thickness": ("RCC slab thickness", "m"),
    "parapet_height": ("Parapet height", "m"), "sill_height": ("Window sill height", "m"), "lintel_height": ("Lintel / door height", "m"),
    "floors": ("Number of storeys priced", "nos"),
}
BASIS_RULES = [  # (assumption id, pattern in item basis, description)
    ("A-FOOTING", r"footing|80 kg/m³ \(no footing", "Footing sizes / footing steel assumed (no structural drawing)"),
    ("A-COLUMN", r"column|bars 4-16", "Column sizes / column steel assumed"),
    ("A-BEAM", r"beam", "Beams assumed under walls; beam steel assumed"),
    ("A-SLABSTEEL", r"90 kg/m³ slab", "Slab steel 90 kg/m³ assumed (no slab schedule)"),
    ("A-OPENING-H", r"heights assumed", "Door / window heights from lintel & sill defaults (no schedule)"),
    ("A-DADO", r"dado|skirting", "Dado / skirting heights assumed"),
    ("A-SERVICES", r"norm per room", "Electrical / plumbing quantities from room norms (no services drawing)"),
    ("A-STAIR", r"waist 150", "Staircase waist and slope factor assumed"),
    ("A-PCC", r"75 mm thickness", "Floor PCC 75 mm assumed"),
]


def assumptions(p: dict, est: dict) -> list[dict]:
    srcs = (p.get("params") or {}).get("_src", {})
    out = []
    for k, (desc, unit) in DEFAULT_DESC.items():
        src = srcs.get(k, "default")
        cls = "USER INPUT" if src == "user" else "DEFAULT" if src == "default" else "EXPLICIT"
        if cls == "EXPLICIT":
            continue
        out.append(dict(assumption_id=f"P-{k.upper()}", description=desc, value=p["params"].get(k), unit=unit, classification=cls,
                        reason="not stated on the drawings" if cls == "DEFAULT" else "entered by the user", source=src,
                        impact_on_cost=None, confidence=0.5 if cls == "DEFAULT" else 0.9))
    taken = set()
    for aid, rx, desc in BASIS_RULES:
        hit = [i for i in est["items"] if i["key"] not in taken and re.search(rx, str(i.get("basis") or "")) and "assumed" in str(i.get("basis") or "")]
        taken |= {i["key"] for i in hit}
        if hit:
            for i in hit:
                i.setdefault("assumption_ids", []).append(aid)
            out.append(dict(assumption_id=aid, description=desc, value=None, unit=None, classification="ASSUMED",
                            reason="information not available in the uploaded drawings", source="engineering default",
                            impact_on_cost=round(sum(i["amount"] for i in hit), 2), items=[i["key"] for i in hit], confidence=0.4))
    return out


def completeness(est: dict) -> dict:
    st = {"MATCHED": 0, "REVIEW": 0, "NEEDS RATE": 0, "NEEDS RATE ANALYSIS": 0, "UNMAPPED": 0, "ASSUMED": 0}
    for i in est["items"]:
        if i.get("rate") is None:
            g = i.get("rate_gap") or "UNMAPPED"
            st[g if g in st else "UNMAPPED"] += 1
        elif i.get("map_method") == "estimated":
            st["ESTIMATED"] = st.get("ESTIMATED", 0) + 1
        elif i.get("status") == "review":
            st["REVIEW"] += 1
        else:
            st["MATCHED"] += 1
        if str(i.get("basis", "")).startswith("assumed"):
            st["ASSUMED"] += 1
    n = len(est["items"])
    priced = sum(1 for i in est["items"] if i.get("rate") is not None)
    return dict(priced=priced, total=n, unresolved=n - priced, text=f"{priced} / {n} items priced", statuses=st,
                complete=priced == n)


def review_level(i: dict) -> str:
    if i.get("rate") is None or i.get("basis_class") == "missing":
        return "red"
    if i.get("basis_class") in ("assumed", "partly assumed") or i.get("status") in ("review", "unmapped"):
        return "yellow"
    return "green"


PLAN_VIEW_RX = re.compile(r"\b(GROUND|FIRST|SECOND|THIRD|FOURTH|FIFTH|TYPICAL|TERRACE|BASEMENT)\s*FLOOR\s*PLAN", re.I)


def multi_plan_views(sheet: dict) -> list[str]:
    """Distinct floor-plan view titles printed on one sheet (OCR may drop the spaces: 'GROUNDFLOORPLAN')."""
    found = {m.group(1).upper() for t in (sheet.get("texts") or []) for m in PLAN_VIEW_RX.finditer(str(t))}
    return [f"{v.title()} floor plan" for v in ("BASEMENT", "GROUND", "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "TYPICAL") if v in found]


def checks(p: dict, est: dict) -> list[dict]:
    out = []
    plans = [s for s in p["sheets"] if s.get("kind") == "floor_plan" and s.get("enabled", True)]
    P = {**takeoff.DEFAULT_PARAMS, **p["params"]}
    for s in plans:
        m = s.get("metrics") or {}
        rooms = s.get("rooms") or []
        ra = sum(r.get("area", 0) for r in rooms)
        if m.get("plinth_area") and ra > 1.02 * m["plinth_area"]:
            out.append(dict(level="ERROR", code="ROOM AREA > BUILDING AREA", sheet=s.get("sheet"),
                            message=f"Σ room area {ra:.1f} m² exceeds plinth area {m['plinth_area']:.1f} m² — rooms overlap or scale is wrong"))
        sg = s.get("scale_guard") or {}
        if sg.get("suspect"):
            out.append(dict(level="ERROR", code="SCALE LOOKS WRONG", sheet=s.get("sheet"),
                            message=f"labelled rooms are implausible for their type ({sg['reason']}); the drawing's scale is probably "
                                    f"wrong — quantities are UNVERIFIED. Calibrate one known dimension or enter the built-up area. "
                                    f"Typical room sizes suggest about {sg['implied_plinth_m2']} m² per floor (budget range only)."))
        views = multi_plan_views(s)
        if len(views) >= 2:
            out.append(dict(level="CONFLICT", code="SEVERAL FLOOR PLANS ON ONE SHEET", sheet=s.get("sheet"),
                            message=f"the sheet holds {', '.join(views)} but only one plan view was measured — the other floor(s) "
                                    "are missing from the quantities; upload each floor separately or enter the storeys and areas"))
        if s.get("plinth_note_override"):
            out.append(dict(level="WARNING", code="PLINTH FROM WRITTEN NOTE", sheet=s.get("sheet"), message=s["plinth_note_override"]))
        hab = sum(1 for r in rooms if (r.get("room_type") or r.get("type")) in ("bedroom", "living", "dining", "kitchen", "toilet", "drawing", "office_zone"))
        doors = sum(1 for o in s.get("openings") or [] if o["kind"] == "door")
        wins = sum(1 for o in s.get("openings") or [] if o["kind"] == "window")
        if hab >= 4 and doors < 0.5 * hab:
            out.append(dict(level="WARNING", code="DOOR COUNT LOW", sheet=s.get("sheet"),
                            message=f"{doors} doors for {hab} rooms — doors are probably missed; review the openings"))
        if hab >= 4 and wins == 0:
            out.append(dict(level="WARNING", code="NO WINDOWS", sheet=s.get("sheet"), message="no windows detected on a plan with habitable rooms"))
        cal = (s.get("areas") or {}).get("calibration") or {}
        if cal.get("status") == "UNRESOLVED":
            out.append(dict(level="ERROR", code="SCALE UNRESOLVED", sheet=s.get("sheet"),
                            message="no reliable scale — areas and quantities from this sheet are UNRESOLVED; calibrate with a known dimension"))
        elif cal.get("status") == "NEEDS REVIEW":
            out.append(dict(level="WARNING", code="SCALE ASSUMED", sheet=s.get("sheet"), message=f"scale basis: {cal.get('basis')} — review"))
        fi = s.get("floor_info") or {}
        if fi.get("typical_floor") and not fi.get("floor_occurrences") and (P.get("_src") or {}).get("floors") != "user":
            out.append(dict(level="WARNING", code="STOREY COUNT REQUIRED", sheet=s.get("sheet"),
                            message="the sheet is a TYPICAL floor plan but does not say which / how many floors — enter the number of storeys"))
        if fi.get("floor_occurrences") and (P.get("_src") or {}).get("floors") == "user" and int(P["floors"]) != len(fi["floor_occurrences"]):
            out.append(dict(level="WARNING", code="FLOOR COUNT CONFLICT", sheet=s.get("sheet"),
                            message=f"floors set to {P['floors']} but the sheet text says floors {fi['floor_occurrences']}"))
        oc = s.get("opening_confirmed") or {}
        for c in openings.reconcile(s):
            if c.get("kind") in oc:  # disagreement resolved by the user's confirmed count
                out.append(dict(level="INFO", code="OPENING COUNT CONFIRMED", sheet=s.get("sheet"),
                                message=f"{c['kind']} count confirmed by user: {oc[c['kind']]} (automatic sources: {c.get('counts')})"))
            else:
                out.append(dict(c, sheet=s.get("sheet")))
        for r in rooms:
            if r.get("label_dims") and r.get("polygon_area"):
                a = r["label_dims"][0] * r["label_dims"][1]
                if abs(r["polygon_area"] / a - 1) > 0.15:
                    out.append(dict(level="INFO", code="DIMENSION vs GEOMETRY", sheet=s.get("sheet"),
                                    message=f"{r.get('name')}: written {a:.1f} m² vs measured polygon {r['polygon_area']:.1f} m² — written dimensions used"))
    # two plans that look like the same floor drawn twice (identical room set and area, no floor label telling them apart)
    # are both counted by the take-off — flag, never silently drop either one
    sig = lambda s: (len(s.get("rooms") or []), round(((s.get("metrics") or {}).get("plinth_area") or 0), 0))
    unlabelled = [s for s in plans if not (s.get("floor") or {}).get("label") and not (s.get("floor_info") or {}).get("floor_occurrences")]
    for i in range(len(unlabelled)):
        for j in range(i + 1, len(unlabelled)):
            a, b = unlabelled[i], unlabelled[j]
            pa, pb = (a.get("metrics") or {}).get("plinth_area") or 0, (b.get("metrics") or {}).get("plinth_area") or 0
            if sig(a)[0] and sig(a)[0] == sig(b)[0] and pa and abs(pa - pb) <= 0.02 * pa:
                out.append(dict(level="CONFLICT", code="POSSIBLE DUPLICATE DRAWING", sheet=b.get("sheet"),
                                message=f"'{a.get('file')}' and '{b.get('file')}' show the same rooms and area ({pa:.1f} m²) and neither has a "
                                        "floor label — both are counted. If they are the same floor, skip one; if different floors, label them."))
    lvl = lambda s: set((s.get("floor_info") or {}).get("floor_occurrences") or ([] if (s.get("floor") or {}).get("level") is None else
                         range(int(s["floor"]["level"]), int(s["floor"]["level"]) + max(1, int(s["floor"].get("repeat", 1))))))
    for i in range(len(plans)):
        for j in range(i + 1, len(plans)):
            common = lvl(plans[i]) & lvl(plans[j])
            if common:
                out.append(dict(level="WARNING", code="SAME FLOOR IN TWO DRAWINGS", sheet=plans[j].get("sheet"),
                                message=f"'{plans[i].get('file')}' and '{plans[j].get('file')}' both cover floor(s) {sorted(common)} — that floor is "
                                        "counted ONCE (the later drawing adds nothing for it). Relabel or skip a drawing if this is wrong."))
    # scope validation: floors the user asked for vs floors the drawings cover (never invents a floor or a drawing)
    import scope as scope_mod
    sc = p.get("scope") or {}
    want = parse_floor_list((sc.get("config") or {}).get("floors_list"))
    have = set(scope_mod.context(p["sheets"])["floors"])
    if want:
        missing, extra = sorted(want - have), sorted(have - want)
        if missing:
            out.append(dict(level="CONFLICT", code="SCOPE FLOOR MISSING",
                            message=f"scope asks for floor(s) {', '.join(map(str, missing))} but no drawing covers them "
                                    f"(drawings cover {sorted(have) or 'no identified floor'}) — upload those floors' plans, or set the floor on an "
                                    "existing plan if it also applies to them; nothing is added automatically"))
        if extra:
            out.append(dict(level="WARNING", code="SCOPE FLOOR EXTRA",
                            message=f"drawings cover floor(s) {', '.join(map(str, extra))} which are not in the requested scope "
                                    f"({sorted(want)}) — check the floor labels or the scope"))
    for s in plans:
        fi = s.get("floor_info") or {}
        if len(fi.get("floor_occurrences") or []) > 1 and not s.get("floor_confirmed"):
            out.append(dict(level="WARNING", code="FLOOR REPEAT NEEDS CONFIRMATION", sheet=s.get("sheet"),
                            message=f"'{s.get('file')}' is applied to floors {fi['floor_occurrences']} because its text says "
                                    f"'{fi.get('source_text')}' — quantities are multiplied by {len(fi['floor_occurrences'])}. Confirm (or change) "
                                    "the floor on the drawing if the layout really repeats on every listed floor"))
    it = {i["key"]: i for i in est["items"]}
    for i in est["items"]:
        if i["qty"] < 0:
            out.append(dict(level="ERROR", code="NEGATIVE QUANTITY", message=f"{i['key']} quantity {i['qty']}"))
    conc = sum(it[k]["qty"] for k in ("rcc_footing", "rcc_column", "rcc_beam", "rcc_slab", "rcc_lintel") if k in it)
    steel = sum(it[k]["qty"] for k in ("steel_footing", "steel_column", "steel_beam", "steel_slab") if k in it)
    if conc > 0 and not 50 <= steel / conc <= 250:
        out.append(dict(level="WARNING", code="STEEL RATIO", message=f"steel {steel / conc:.0f} kg per m³ of RCC is outside 50–250"))
    if "mas_230" in it and plans:
        L = sum((s.get("metrics") or {}).get("L_ext", 0) for s in plans)
        if L > 0 and it["mas_230"]["qty"] > L * 0.23 * float(P["floor_height"]) * max(1, int(P["floors"])) * 1.3 + 1:
            out.append(dict(level="WARNING", code="WALL VOLUME", message="external masonry volume exceeds wall length × thickness × height"))
    if not any(s.get("kind") == "structural" or s.get("structural") for s in p["sheets"]):
        out.append(dict(level="WARNING", code="STRUCTURAL INPUT MISSING",
                        message="no structural drawing — footing / column / beam sizes and steel are ASSUMED"))
    return out


# ------------------------------------------------------------------------------------------------ status model
QTY_STATUS = {
    "MEASURED": "read from a written dimension, schedule or calibrated / CAD geometry",
    "DERIVED": "calculated from measured drawing geometry with a stated rule",
    "PROVISIONAL": "calculated with ASSUMED inputs (defaults / no structural drawing) — preliminary budgeting only, review",
    "UNVERIFIED SCALE": "drawing-derived, but the drawing scale is assumed — quantity scales with the unverified scale",
    "USER-ENTERED": "quantity entered / corrected by the user",
    "UNRESOLVED": "cannot be supported by the evidence under the chosen policy — NOT in the total",
    "EXCLUDED": "outside the selected estimation scope — NOT in the total",
}
RATE_STATUS = {"PWD": "PWD schedule rate / Standard Data analysis", "ESTIMATED": "estimated average rate (not a PWD rate)",
               "USER": "rate entered by the user", "NONE": "no rate — NOT in the total"}
NOT_COVERED = ["Fire-fighting / fire alarm", "HVAC / air-conditioning", "Lift equipment (car, machine, controls)", "Medical gases",
               "External works (roads, drains, compound wall, landscaping)", "Electrical HT / transformer / DG set", "Furniture & equipment"]


def qty_status(it: dict, scale_ok: bool) -> str:
    ex = it.get("exclusion") or {}
    if ex.get("kind") == "scope":
        return "EXCLUDED"
    if ex.get("kind") == "unresolved":
        return "UNRESOLVED"
    if it.get("qty_user") or it.get("custom"):
        return "USER-ENTERED"
    bc = it.get("basis_class")
    if bc in ("assumed", "partly assumed"):
        return "PROVISIONAL"
    geometric = not re.search(r"schedule|bar by bar|bbs", str(it.get("basis") or ""), re.I)
    if geometric and not scale_ok:
        return "UNVERIFIED SCALE"
    return "MEASURED" if bc == "explicit" else "DERIVED"


def rate_status(it: dict) -> str:
    if it.get("rate") is None:
        return "NONE"
    if it.get("rate_user") or it.get("map_method") == "user":
        return "USER"
    if it.get("map_method") == "estimated":
        return "ESTIMATED"
    return "PWD"


def status_summary(p: dict, est: dict, others: list, scale_ok: bool) -> dict:
    """One status model for UI, abstract, detailed estimate and PDF. Counts of overlapping properties are reported
    separately (a line can be PWD-priced AND provisional); 'complete' requires every counted line to have a verified
    quantity and a PWD / user rate, nothing unresolved / unpriced, and no identified element left unquantified."""
    items = est["items"]
    counted = [i for i in items if i.get("in_scope", True)]
    q = {k: [i for i in items if i.get("qty_status") == k] for k in QTY_STATUS}
    r = {k: [i for i in counted if i.get("rate_status") == k] for k in RATE_STATUS}
    amt = lambda L: round(sum(i.get("amount") or 0 for i in L), 2)
    verified_q = [i for i in counted if i["qty_status"] in ("MEASURED", "DERIVED", "USER-ENTERED")]
    reasons = []
    if q["PROVISIONAL"]:
        reasons.append(f"{len(q['PROVISIONAL'])} line(s) use ASSUMED inputs (₹{amt(q['PROVISIONAL']):,.0f})")
    if q["UNVERIFIED SCALE"]:
        reasons.append(f"{len(q['UNVERIFIED SCALE'])} line(s) depend on an unverified drawing scale (₹{amt(q['UNVERIFIED SCALE']):,.0f})")
    if r["ESTIMATED"]:
        reasons.append(f"{len(r['ESTIMATED'])} line(s) priced at estimated (non-PWD) average rates (₹{amt(r['ESTIMATED']):,.0f})")
    if r["NONE"]:
        reasons.append(f"{len(r['NONE'])} line(s) have no rate and are not in the total")
    if q["UNRESOLVED"]:
        reasons.append(f"{len(q['UNRESOLVED'])} line(s) unresolved — not in the total")
    if others:
        reasons.append(f"{len(others)} identified element(s) not quantified — not in the total: " + ", ".join(o["element"] for o in others))
    complete = not reasons
    return dict(
        status="COMPLETE" if complete else "PRELIMINARY",
        headline=("Complete for the selected scope: every counted line has a verified quantity and a PWD / user rate"
                  if complete else "PRELIMINARY estimate — " + "; ".join(reasons)),
        reasons=reasons, lines_total=len(items), lines_counted=len(counted), counted_amount=est["subtotal"],
        quantity={k: dict(lines=len(v), amount=amt(v), meaning=QTY_STATUS[k]) for k, v in q.items()},
        rate={k: dict(lines=len(v), amount=amt(v), meaning=RATE_STATUS[k]) for k, v in r.items()},
        verified_quantity_lines=len(verified_q), verified_quantity_amount=amt(verified_q),
        excluded_scope=[dict(description=i["description"], reason=(i.get("exclusion") or {}).get("reason")) for i in q["EXCLUDED"]],
        unresolved=[dict(description=i["description"], reason=(i.get("exclusion") or {}).get("reason")) for i in q["UNRESOLVED"]],
        identified_not_quantified=[o["element"] for o in others],
        not_covered_by_takeoff=NOT_COVERED,
        note="Statuses overlap by design: a line can be PWD-priced and provisional. A priced line is not a validated line.")


def parse_floor_list(v) -> set:
    """'4,5,6' / '4-6' / 'G,1,2' / [4, 5] → {4, 5, 6}; ground = 0, basement = -1. Empty / invalid → empty set."""
    if v in (None, ""):
        return set()
    parts = v if isinstance(v, list) else re.split(r"[,\s;]+", str(v).strip())
    out = set()
    for x in parts:
        x = str(x).strip().upper()
        if not x:
            continue
        m = re.fullmatch(r"(-?\d+)\s*-\s*(-?\d+)", x)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out |= set(range(min(a, b), max(a, b) + 1))
        elif re.fullmatch(r"-?\d+", x):
            out.add(int(x))
        elif x in ("G", "GF", "GROUND"):
            out.add(0)
        elif x in ("B", "BASEMENT"):
            out.add(-1)
    return out
