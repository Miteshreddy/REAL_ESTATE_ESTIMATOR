"""Quantity take-off engine + PWD rate mapping + cost computation.

Every BOQ line carries: the measured basis (formula with numbers), the drawing elements it came from
(traceability), the NLP-mapped PWD SOR item with confidence, and the user's review state.
"""
from __future__ import annotations

import math
from typing import Any

from sor import CATEGORY_ORDER

WET = {"toilet", "utility", "balcony"}
DEFAULT_PARAMS = dict(
    floors=1, floor_height=3.0, plinth_height=0.6, foundation_depth=1.5, slab_thickness=0.125,
    parapet_height=0.9, sill_height=0.9, lintel_height=2.1,
    finish="standard", window_type="aluminium", contingency=3.0, gst=18.0, cess=1.0, cost_index=1.0,
    column_spacing_area=11.0, include_services=True,
    # land (second figure only - never part of the construction cost)
    labour_zone="Z1",
    cement_rate=0.0, steel_rate=0.0,  # ₹/tonne, only where the SOR does not print them (e.g. AP monthly notified rate)  # official labour-rate zone where the SOR defines zones (e.g. Telangana I/II/III)
    land_area=0.0, land_rate=0.0, land_rate_basis="", stamp_duty_pct=0.0,
)
PREMIUM_CATS = {"Flooring", "Painting", "Doors & Windows"}

ROOM_POINTS = {  # light / fan points, power points
    "living": (6, 3), "bedroom": (4, 2), "kitchen": (3, 4), "toilet": (3, 1), "dining": (3, 1), "study": (3, 2),
    "utility": (2, 2), "store": (1, 0), "pooja": (2, 0), "balcony": (1, 0), "stair": (2, 0), "corridor": (2, 0),
    "garage": (2, 1), "unknown": (3, 1),
}


def r2(x):
    return round(float(x), 2)


def bar_kg_per_m(d_mm):
    return d_mm * d_mm / 162.0


def sheet_ref(s):
    return f"{s.get('file', '')} · {s.get('sheet', '')}"


def merge_drawing_data(sheets):
    """Combine what was read from all sheets: levels, opening schedule, structural schedules."""
    levels, sched, st = {}, {}, dict(footings=[], columns=[], beams=[], slabs=[])
    lvl_src, st_src, sched_src = {}, {}, {}
    order = sorted(sheets, key=lambda s: {"section": 0, "elevation": 1, "structural": 2}.get(s.get("kind"), 3))
    for s in order:
        for k, v in (s.get("levels") or {}).items():
            if k not in levels:
                levels[k], lvl_src[k] = v, sheet_ref(s)
        for k, v in (s.get("schedule") or {}).items():
            if k not in sched:
                sched[k], sched_src[k] = v, sheet_ref(s)
        for grp in st:
            for e in (s.get("structural") or {}).get(grp, []) or []:
                if grp == "slabs" and not e.get("main"):
                    continue
                key = (grp, e.get("mark"))
                if e.get("mark") and any(x.get("mark") == e["mark"] for x in st[grp]):
                    continue
                st[grp].append(dict(e, ref=sheet_ref(s)))
                st_src[key] = sheet_ref(s)
    return levels, lvl_src, sched, sched_src, st


def derive_params(sheets):
    """Parameters that can be read from the drawings, with the sheet they came from."""
    levels, lvl_src, *_ = merge_drawing_data(sheets)
    out, src = {}, {}
    m = {"floor_height": "floor_height", "plinth_height": "plinth_height", "foundation_depth": "foundation_depth",
         "slab_thickness": "slab_thickness", "parapet_height": "parapet_height", "sill_height": "sill_height", "lintel_height": "lintel_height"}
    for k, lk in m.items():
        if lk in levels:
            out[k] = levels[lk]
            src[k] = lvl_src.get(lk) or lvl_src.get("floor_heights") or lvl_src.get("plinth_level", "drawing")
    plans = [s for s in sheets if s.get("kind") == "floor_plan"]
    if levels.get("floors_from_levels"):
        out["floors"], src["floors"] = levels["floors_from_levels"], lvl_src.get("floor_heights", "section")
    elif len(plans) > 1 or (plans and int((plans[0].get("floor") or {}).get("repeat") or 1) > 1):  # incl. ONE typical plan × n
        levels = set()
        for s in plans:
            fl = s.get("floor") or {}
            if fl.get("level") is not None:
                levels |= set(range(int(fl["level"]), int(fl["level"]) + max(1, int(fl.get("repeat", 1)))))
        out["floors"] = len(levels) or len(plans)
        src["floors"] = f"{len(plans)} floor plans covering {out['floors']} storey(s)"
    elif plans and (plans[0].get("floor_info") or {}).get("repeated_count"):
        fi = plans[0]["floor_info"]
        out["floors"] = fi["repeated_count"]
        src["floors"] = (f"{sheet_ref(plans[0])}: '{fi['source_text']}' — plan occurs on floor(s) {', '.join(map(str, fi['floor_occurrences']))}"
                         f" (confidence {fi['confidence']:.2f})")
    else:
        for s in sheets:
            if (s.get("notes") or {}).get("floors"):
                out["floors"], src["floors"] = s["notes"]["floors"], sheet_ref(s) + " (note)"
            if (s.get("notes") or {}).get("floor_height") and "floor_height" not in out:
                out["floor_height"], src["floor_height"] = s["notes"]["floor_height"], sheet_ref(s) + " (note)"
    return out, src


def plan_multipliers(plans, n):
    """How many storeys each floor plan stands for.

    One plan = typical floor repeated n times. Several plans: each covers its own level(s) (a "typical
    first & second" plan covers two); a plan whose levels are already covered by another plan is a
    duplicate drawing of the same floor and counts 0. The top plan repeats if more storeys are set."""
    if len(plans) == 1:
        return [n]
    covered, mult = set(), []
    for s in plans:
        fl = s.get("floor") or {}
        lv, rep = fl.get("level"), max(1, int(fl.get("repeat", 1)))
        # the set floor (user correction / matched written area) wins over the raw text reading — same rule as scope.plan_floors
        occ = fl.get("occurrences") or (s.get("floor_info") or {}).get("floor_occurrences")
        if lv is None and not occ:
            mult.append(1)
            continue
        levels = set(occ) if occ else set(range(int(lv), int(lv) + rep))
        new = levels - covered
        mult.append(len(new))
        covered |= levels
    if sum(mult) < n:
        last = max(i for i, m in enumerate(mult) if m > 0)
        mult[last] += n - sum(mult)
    return mult


# construction elements recognised in drawing text / room names that the take-off does not quantify automatically
OTHER_ELEMENTS = [
    ("Lift / elevator", r"\bLIFT\b|ELEVATOR"), ("Ramp", r"\bRAMP\b"), ("Sump / underground tank", r"\bSUMP\b|U\.?G\.?\s*TANK|UNDERGROUND"),
    ("Septic tank / soak pit", r"SEPTIC|SOAK\s*PIT"), ("Overhead tank (structure)", r"O\.?H\.?\s*T\b|OVERHEAD\s*TANK"),
    ("Compound wall", r"COMPOUND\s*WALL|BOUNDARY\s*WALL"), ("Sunshade / chajja", r"SUNSHADE|SUN\s*SHADE|CHAJJA"),
    ("Canopy / portico", r"CANOPY|PORTICO"), ("Pergola", r"PERGOLA"), ("False ceiling", r"FALSE\s*CEILING"),
    ("Cladding", r"CLADDING"), ("Railing / handrail", r"RAILING|HAND\s*RAIL"), ("Gate", r"\bGATE\b"),
    ("Solar panels", r"SOLAR"), ("Rain-water harvesting", r"RAIN\s*WATER|RWH"), ("Fire shaft / duct", r"FIRE\s*SHAFT|\bDUCT\b"),
    ("Jali / screen", r"\bJALI\b"), ("Expansion joint", r"EXPANSION\s*JOINT"), ("Swimming pool", r"SWIMMING|POOL\b"),
]


def other_elements(sheets: list[dict]) -> list[dict]:
    """Elements represented in the drawings that are NOT quantified automatically: listed so they are never
    silently ignored — each needs a quantity from the engineer (or a dedicated drawing) before it is priced."""
    import re as _re
    found = {}
    for s in sheets:
        if not s.get("enabled", True):
            continue
        texts = list(s.get("texts") or []) + [r.get("name", "") for r in s.get("rooms", [])]
        for name, rx in OTHER_ELEMENTS:
            for t in texts:
                if _re.search(rx, str(t).upper()):
                    f = found.setdefault(name, dict(element=name, sheets=set(), examples=set()))
                    f["sheets"].add(f"{s.get('file', '')} {s.get('sheet', '')}".strip())
                    f["examples"].add(str(t)[:60])
    return [dict(element=v["element"], status="identified — needs quantity / user input (not in total)",
                 sheets=sorted(v["sheets"])[:6], examples=sorted(v["examples"])[:4]) for v in found.values()]


def sort_plans(plans, sheets):
    return sorted(plans, key=lambda s: ((s.get("floor") or {}).get("level", 0), sheets.index(s)))


def compute_quantities(sheets: list[dict], P: dict) -> list[dict[str, Any]]:
    p = {**DEFAULT_PARAMS, **(P or {})}
    n = max(1, int(p["floors"]))
    h = float(p["floor_height"])
    ph = float(p["plinth_height"])
    df = float(p["foundation_depth"])
    ts = float(p["slab_thickness"])
    parapet = float(p.get("parapet_height", 0.9))
    sill_h = float(p.get("sill_height", 0.9))
    lintel_h = float(p.get("lintel_height", 2.1))
    items: list[dict] = []

    plans = [s for s in sheets if s.get("kind") == "floor_plan" and (s.get("rooms") or s.get("area_only"))]
    if not plans:
        return []
    plans = sort_plans(plans, sheets)
    levels, lvl_src, sched, sched_src, st = merge_drawing_data(sheets)
    # how many storeys each plan represents
    mult = plan_multipliers(plans, n)
    keep = [i for i, m in enumerate(mult) if m > 0]  # duplicate drawings of an already covered floor are skipped
    plans, mult = [plans[i] for i in keep], [mult[i] for i in keep]
    n_tot = sum(mult)
    G, T = plans[0], plans[-1]
    refs_all = [sheet_ref(s) for s in plans]

    def add(key, desc, cat, unit, qty, formula, sources, hint, conf=0.9, refs=None, basis="drawing"):
        if qty is None or qty <= 0:
            return
        unit = {"m": "metre"}.get(unit, unit)
        items.append(dict(key=key, description=desc, category=cat, unit=unit, qty=r2(qty), formula=formula, sources=list(sources)[:80],
                          hint=hint, extract_conf=round(conf, 2), drawing_refs=refs or refs_all, basis=basis))

    def M(s, k):
        return s["metrics"][k]

    conf = sum(s.get("confidence", 0.7) for s in plans) / len(plans)
    psrc = (P or {}).get("_src", {})

    def pb(k):
        v = str(psrc.get(k, "default"))
        return "user input" if v == "user" else (f"assumed default ({k})" if v == "default" else f"drawing ({v})")
    fl = lambda i: (plans[i].get("floor") or {}).get("label") or f"Plan {i + 1}"

    # ---------------------------------------------------------------- openings with sizes from the schedule
    def openings(s):
        out = []
        for o in s["openings"]:
            o = dict(o)
            sc = sched.get(o.get("tag") or "")
            if sc:
                o["w"], o["h"], o["src"] = sc["w"], sc["h"], "schedule"
            else:
                o["h"] = lintel_h if o["kind"] == "door" else (0.6 if o["w"] < 0.8 else max(0.6, lintel_h - sill_h))
                o["src"] = "measured"
            out.append(o)
        # user-confirmed counts (sheet["opening_confirmed"] = {"door": n, "window": m}) replace the automatic count:
        # extra automatic openings are dropped (schedule-tagged / highest-confidence kept first); missing ones are added
        # with the median detected size of that kind (or a stated default) — every downstream quantity uses this list
        conf_ = s.get("opening_confirmed") or {}
        for kind, default in (("door", (0.9, lintel_h)), ("window", (1.2, max(0.6, lintel_h - sill_h)))):
            n = conf_.get(kind)
            if n is None:
                continue
            same = sorted([o for o in out if o["kind"] == kind], key=lambda o: (o["src"] != "schedule", -float(o.get("confidence") or 1.0)))
            keep = same[:int(n)]
            if len(keep) < int(n):
                ws = sorted(o["w"] for o in same) or [default[0]]
                hs = sorted(o["h"] for o in same) or [default[1]]
                w_, h_ = ws[len(ws) // 2], hs[len(hs) // 2]
                keep += [dict(kind=kind, id=f"{'D' if kind == 'door' else 'W'}U{k + 1}", w=w_, h=h_, ext=kind == "window", x=0, y=0,
                              src="user-confirmed count (size = median detected" + (")" if same else " — none detected, default size)"))
                         for k in range(int(n) - len(keep))]
            out = [o for o in out if o["kind"] != kind] + keep
        return out

    OP = [openings(s) for s in plans]
    sched_used = sum(1 for ops in OP for o in ops if o["src"] == "schedule")
    n_ops = sum(len(ops) for ops in OP)
    op_note = f"sizes from door/window schedule ({sched_used}/{n_ops} openings tagged)" if sched_used else f"door height {lintel_h} m, windows {lintel_h - sill_h:.2f} m (lintel − sill)"
    op_basis = ("schedule" if sched_used == n_ops else f"drawing widths; heights from schedule for {sched_used}/{n_ops}, others assumed (lintel {lintel_h} m, sill {sill_h} m)"
                if sched_used else f"drawing widths; heights assumed (lintel {lintel_h} m, sill {sill_h} m) — no door/window schedule")

    def a_open(ops, kind=None, ext=None):
        return sum(o["w"] * o["h"] for o in ops if (kind is None or o["kind"] == kind) and (ext is None or bool(o.get("ext")) == ext))

    # ---------------------------------------------------------------- structural members
    walls_g = M(G, "L_ext") + M(G, "L_int")
    Ag, Pg = M(G, "plinth_area"), M(G, "envelope_perimeter")
    st_ref = sorted({e["ref"] for g in st.values() for e in g})
    fts = [f for f in st["footings"] if f.get("count")]
    cols = [c for c in st["columns"] if c.get("count")]
    beams = [b for b in st["beams"] if b.get("length")]
    slab = next((x for x in st["slabs"] if x.get("main")), None)
    if slab and slab.get("thk"):
        ts = slab["thk"]

    # footings
    if fts:
        foot = [(f["mark"], f["count"], f.get("L") or 1.5, f.get("B") or 1.5, f.get("D") or 0.45, f.get("bar")) for f in fts]
        sized = all(f.get("L") for f in fts)
        f_basis = "footing schedule" if sized else "footing count from layout, sizes assumed 1.5×1.5×0.45"
        f_conf, f_refs, f_src = (0.95 if sized else 0.75), st_ref, [f["mark"] for f in fts]
        f_txt = ", ".join(f"{m}: {c} × {L:.2f}×{B:.2f}×{D:.2f}" for m, c, L, B, D, _ in foot)
    else:
        det = sum(len(s.get("columns", [])) for s in plans[:1])
        N = det if det >= 4 else max(4, round(Ag / p["column_spacing_area"]))
        foot = [("F (assumed)", N, 1.5, 1.5, 0.45, None)]
        f_basis, f_conf, f_refs, f_src = "assumed — no footing schedule", 0.6, [sheet_ref(G)], [c["id"] for c in G.get("columns", [])] or ["grid estimate"]
        f_txt = f"{N} footings × 1.50×1.50×0.45 (assumed, {'columns on plan' if det >= 4 else 'grid estimate'})"
    Nf = sum(c for _, c, *_ in foot)
    D_avg = sum(c * D for _, c, _, _, D, _ in foot) / max(1, Nf)

    # columns
    storey_h = h * n_tot
    col_H = (df - D_avg) + ph + storey_h
    if cols:
        colset = [(c["mark"], c["count"], c.get("b") or 0.23, c.get("d") or 0.40, c.get("main") or [(4, 16), (2, 12)], c.get("ties") or (8, 150)) for c in cols]
        sized = all(c.get("b") for c in cols)
        c_basis = "column schedule" if sized else "column count from layout, size assumed 230×400"
        c_conf, c_src = (0.95 if sized else 0.75), [c["mark"] for c in cols]
    else:
        colset = [("C (assumed)", Nf, 0.23, 0.40, [(4, 16), (2, 12)], (8, 150))]
        c_basis, c_conf, c_src = "assumed 230×400 — no column schedule", 0.6, f_src

    # beams
    if beams:
        bset = [(b["mark"], b["b"], b["d"], b["length"] * (b.get("count") or 1), b.get("plinth"), b.get("top") or [], b.get("bot") or [], b.get("stirrup")) for b in beams]
        b_basis, b_conf, b_src = "beam schedule", 0.93, [b["mark"] for b in beams]
    else:
        bset = [("PB (assumed)", 0.23, 0.30, walls_g, True, [(2, 12)], [(2, 12)], (8, 150))]
        for i, s in enumerate(plans):
            bset.append((f"B (assumed, {fl(i)})", 0.23, 0.45, (M(s, "L_ext") + M(s, "L_int")) * mult[i], False, [(2, 12)], [(3, 16)], (8, 150)))
        b_basis, b_conf, b_src = "assumed under all walls — no beam schedule", 0.65, ["walls"]
    beam_d = max((d for _, _, d, _, pl, *_ in bset if not pl), default=0.45)
    wall_h = h - beam_d

    # ---------------------------------------------------------------- EARTHWORK
    add("site_clearance", "Site clearance, clearing jungle, grass and vegetation over plinth area plus 50% working space", "Earthwork", "sqm",
        Ag * 1.5, f"Ground plinth {Ag:.2f} m² × 1.5 (incl. 50% working space)", ["envelope"], "2.1.1", conf, [sheet_ref(G)], "drawing + rule (50% working space)")
    v_exc_f = sum(c * (L + 0.3) * (B + 0.3) * df for _, c, L, B, _, _ in foot)
    v_trench = walls_g * 0.6 * 0.45
    add("excavation", "Earth work excavation in foundation trenches for footings and plinth beams, lift up to 1.5 m including disposal", "Earthwork", "cum",
        v_exc_f + v_trench, f"Footings ({f_basis}): Σ n×(L+0.3)×(B+0.3)×{df} m = {v_exc_f:.2f} + wall trenches {walls_g:.1f} m × 0.6 × 0.45",
        f_src, "2.8.1", f_conf, f_refs + [sheet_ref(G)], f_basis)
    v_pcc = sum(c * (L + 0.2) * (B + 0.2) * 0.1 for _, c, L, B, _, _ in foot) + walls_g * 0.6 * 0.1
    v_foot = sum(c * L * B * D for _, c, L, B, D, _ in foot)
    v_col_below = sum(c * b * d * (df - D_avg) for _, c, b, d, *_ in colset)
    add("backfill", "Back filling excavated earth in trenches and sides of foundations in layers with ramming and watering", "Earthwork", "cum",
        max(0, v_exc_f + v_trench - v_pcc - v_foot - v_col_below - walls_g * 0.23 * 0.45),
        "Excavation − (PCC + footings + columns below GL + plinth walls below GL)", f_src, "2.25", f_conf * 0.95, f_refs, f_basis)
    carpet_g = M(G, "carpet_area")
    add("sand_fill", "Filling sand / murrum under floors in plinth with watering, ramming and consolidation", "Earthwork", "cum",
        carpet_g * max(0.1, ph - 0.2), f"Ground carpet {carpet_g:.2f} m² × ({ph} − 0.20) m", [r["id"] for r in G["rooms"]], "2.33", conf, [sheet_ref(G)], f"drawing area; plinth height: {pb('plinth_height')}")
    add("anti_termite", "Anti termite pre-constructional soil treatment with chlorpyriphos over plinth area", "Earthwork", "sqm",
        Ag, f"Ground plinth area {Ag:.2f} m²", ["envelope"], "2.34", conf, [sheet_ref(G)])

    # ---------------------------------------------------------------- CONCRETE / RCC
    add("pcc_found", "Plain cement concrete 1:4:8 lean concrete bed below footings and plinth beams with 40 mm aggregate", "Concrete Works", "cum",
        v_pcc, "Σ n×(L+0.2)×(B+0.2)×0.10 below footings + 0.6 m wide × 0.10 under plinth beams", f_src, "4.1.8", f_conf, f_refs, f_basis)
    add("pcc_floor", "Providing and laying in position cement concrete 1:2:4 (1 cement : 2 coarse sand : 4 graded stone aggregate 20 mm nominal size) all work up to plinth level, base for ground floor flooring", "Concrete Works", "cum",
        carpet_g * 0.075, f"Ground carpet {carpet_g:.2f} m² × 0.075 m", [r["id"] for r in G["rooms"]], "4.1.3", conf, [sheet_ref(G)], "drawing area; 75 mm thickness assumed")
    add("rcc_footing", "Providing and laying in position reinforced cement concrete 1:1.5:3 (1 cement : 1.5 coarse sand : 3 graded stone aggregate 20 mm nominal size) all work up to plinth level, footings and bases of columns", "RCC Works", "cum",
        v_foot, f"{f_txt}", f_src, "5.1.3", f_conf, f_refs, f_basis)
    col_H_conc = col_H - n_tot * ts  # slab depth at each floor is measured in the slab item, not twice
    v_col = sum(c * b * d * col_H_conc for _, c, b, d, *_ in colset)
    add("rcc_column", "Reinforced cement concrete work in walls, columns, pillars, piers, abutments, posts and struts up to floor five level 1:1.5:3 graded stone aggregate 20 mm nominal size", "RCC Works", "cum",
        v_col, "; ".join(f"{m}: {c} × {b:.2f}×{d:.2f}" for m, c, b, d, *_ in colset) + f" × height {col_H_conc:.2f} m (below GL {df - D_avg:.2f} + plinth {ph} + {n_tot} × {h} m − {n_tot} × slab {ts} m)",
        c_src, "5.3.1", c_conf, st_ref or [sheet_ref(G)], c_basis)
    v_beam = sum(b * (d if pl else d - ts) * L for _, b, d, L, pl, *_ in bset)
    add("rcc_beam", "Reinforced cement concrete work in beams, suspended floors, roofs, landings, lintels, plinth beams up to floor five level 1:1.5:3 graded stone aggregate 20 mm nominal size", "RCC Works", "cum",
        v_beam, "; ".join(f"{m}: {L:.1f} m × {b:.2f} × {(d if pl else d - ts):.3f}" for m, b, d, L, pl, *_ in bset) + (" (floor beams measured below slab)" if any(not x[4] for x in bset) else ""),
        b_src, "5.3.2", b_conf, st_ref or refs_all, b_basis)
    slab_areas = [M(s, "plinth_area") * mult[i] for i, s in enumerate(plans)]
    A_slab = sum(slab_areas)
    add("rcc_slab", "Reinforced cement concrete work in beams, suspended floors, roofs having slope up to 15 degrees, landings up to floor five level 1:1.5:3 graded stone aggregate 20 mm nominal size", "RCC Works", "cum",
        A_slab * ts, " + ".join(f"{fl(i)} {M(s, 'plinth_area'):.1f} m² × {mult[i]}" for i, s in enumerate(plans)) + f" × {ts} m thick" + (" (slab schedule)" if slab else ""),
        ["envelope"], "5.3.3", conf, refs_all + ([slab["ref"]] if slab else []), "drawing area; thickness from slab schedule" if slab else f"drawing area; slab thickness: {pb('slab_thickness')}")
    all_ops = [o for ops in OP for o in ops]
    v_lintel = sum((o["w"] + 0.3) * 0.23 * 0.15 * mult[i] for i, ops in enumerate(OP) for o in ops)
    add("rcc_lintel", "Reinforced cement concrete work in beams, lintels, bressumers over openings up to floor five level 1:1.5:3 graded stone aggregate 20 mm nominal size", "RCC Works", "cum",
        v_lintel, f"Σ (opening width + 0.30 bearing) × 0.23 × 0.15 over {n_ops} openings × floors", [o["id"] for o in all_ops], "5.3.2", conf * 0.95, None, "drawing openings; lintel section 230×150 assumed")

    # ---------------------------------------------------------------- FORMWORK
    add("fw_found", "Centering and shuttering including strutting, propping etc. and removal of form for foundations, footings, bases of columns, etc. for mass concrete", "Formwork", "sqm",
        sum(c * 2 * (L + B) * D for _, c, L, B, D, _ in foot) + sum(2 * d * L for _, b, d, L, pl, *_ in bset if pl),
        "Footing sides Σ n×2(L+B)×D + plinth beam sides 2×d×L", f_src, "5.9.1", f_conf, f_refs, f_basis)
    carpet_tot = sum(M(s, "carpet_area") * mult[i] for i, s in enumerate(plans))
    add("fw_slab", "Centering and shuttering including strutting, propping etc. and removal of form for suspended floors, roofs, landings, balconies and access platform", "Formwork", "sqm",
        carpet_tot, "Slab soffit = Σ carpet area × storeys", ["rooms"], "5.9.3", conf, None, "drawing")
    add("fw_beam", "Centering and shuttering including strutting, propping etc. and removal of form for lintels, beams, plinth beams, girders, bressumers and cantilevers", "Formwork", "sqm",
        sum((b + 2 * (d - ts)) * L for _, b, d, L, pl, *_ in bset if not pl) + v_lintel / 0.15 / 0.23 * (0.23 + 0.3),
        "Floor/roof beams (b + 2×(d − slab)) × L + lintel soffit & sides", b_src, "5.9.5", b_conf, st_ref or refs_all, b_basis)
    add("fw_col", "Centering and shuttering including strutting, propping etc. and removal of form for columns, pillars, piers, abutments, posts and struts", "Formwork", "sqm",
        sum(c * 2 * (b + d) * (col_H - (df - D_avg)) for _, c, b, d, *_ in colset) + sum(c * 2 * (b + d) * (df - D_avg) for _, c, b, d, *_ in colset),
        f"Σ n × perimeter 2(b+d) × {col_H:.2f} m", c_src, "5.9.6", c_conf, st_ref or [sheet_ref(G)], c_basis)

    # ---------------------------------------------------------------- STEEL (bar by bar where schedules exist)
    kg_f = 0.0
    for _, c, L, B, D, bar in foot:
        if bar:
            d, s = bar
            nL, nB = int((B - 0.1) / (s / 1000)) + 1, int((L - 0.1) / (s / 1000)) + 1
            kg_f += c * (nL * (L - 0.1 + 2 * (D - 0.1)) + nB * (B - 0.1 + 2 * (D - 0.1))) * bar_kg_per_m(d)
        else:
            kg_f += c * L * B * D * 80
    add("steel_footing", "Steel reinforcement for R.C.C. work including straightening, cutting, bending, placing in position and binding, Thermo-Mechanically Treated bars of grade Fe-500D, in footings", "Reinforcement", "kg",
        kg_f, "Bottom mesh both ways: bars = (width − cover)/spacing + 1, length = L − cover + 2 bends; weight d²/162 kg/m" if fts and fts[0].get("bar") else "80 kg/m³ of footing concrete (assumed)",
        f_src, "5.22.6", f_conf, f_refs, "bar schedule (bar by bar)" if fts and all(f.get("bar") for f in fts) else "assumed — 80 kg/m³ (no footing bar details)")
    kg_c = 0.0
    for _, c, b, d, main, ties in colset:
        kg_c += c * sum(nb * (col_H + n_tot * 50 * dia / 1000) * bar_kg_per_m(dia) for nb, dia in main)
        if ties:
            dt, s = ties
            kg_c += c * (col_H / (s / 1000) + 1) * (2 * (b + d) - 8 * 0.04 + 24 * dt / 1000) * bar_kg_per_m(dt)
    add("steel_column", "Steel reinforcement for R.C.C. work including straightening, cutting, bending, placing in position and binding, Thermo-Mechanically Treated bars of grade Fe-500D, in columns", "Reinforcement", "kg",
        kg_c, f"Main bars × (height {col_H:.2f} m + lap 50d per storey) + ties (perimeter − cover + hooks) at spacing", c_src, "5.22.6", c_conf, st_ref or [sheet_ref(G)],
        "column schedule bars (bar by bar)" if cols and all(c.get("main") for c in cols) else "assumed bars 4-16 + 2-12, ties 8@150 (no column bar schedule)")
    kg_b = 0.0
    for _, b, d, L, pl, top, bot, stir in bset:
        kg_b += sum(nb * L * 1.12 * bar_kg_per_m(dia) for nb, dia in top + bot)
        if stir:
            dt, s = stir
            kg_b += (L / (s / 1000)) * (2 * (b + d) - 8 * 0.025 + 24 * dt / 1000) * bar_kg_per_m(dt)
    add("steel_beam", "Steel reinforcement for R.C.C. work including straightening, cutting, bending, placing in position and binding, Thermo-Mechanically Treated bars of grade Fe-500D, in beams", "Reinforcement", "kg",
        kg_b, "Top + bottom bars × length × 1.12 (anchorage & laps) + stirrups at spacing", b_src, "5.22.6", b_conf, st_ref or refs_all,
        "beam schedule bars (bar by bar)" if beams and all(b.get("top") or b.get("bot") for b in beams) else "assumed bars 2-12 top / 2-12 or 3-16 bottom, stirrups 8@150 (no beam bar schedule)")
    if slab:
        (dm, sm), (dd, sd) = slab["main"], slab["dist"] or slab["main"]
        kg_s = A_slab * (bar_kg_per_m(dm) / (sm / 1000) + bar_kg_per_m(dd) / (sd / 1000)) * 1.1
        s_txt = f"Slab area {A_slab:.1f} m² × (Y{dm}@{sm} + Y{dd}@{sd}) × 1.10 laps & cranks (slab schedule)"
    else:
        kg_s = A_slab * ts * 90
        s_txt = f"Slab concrete {A_slab * ts:.1f} m³ × 90 kg/m³ (assumed — no slab schedule)"
    kg_l = v_lintel * 80
    add("steel_slab", "Steel reinforcement for R.C.C. work including straightening, cutting, bending, placing in position and binding, Thermo-Mechanically Treated bars of grade Fe-500D, in slabs and lintels", "Reinforcement", "kg",
        kg_s + kg_l, s_txt + f" + lintels {v_lintel:.2f} m³ × 80 kg/m³", ["envelope"], "5.22.6", 0.9 if slab else 0.65, refs_all + ([slab["ref"]] if slab else []), "slab schedule (bars & spacing); lintels assumed 80 kg/m³" if slab else "assumed — 90 kg/m³ slab, 80 kg/m³ lintels (no slab schedule)")

    # ---------------------------------------------------------------- MASONRY (floor by floor)
    add("mas_plinth", "Brick work with common burnt clay F.P.S. (non modular) bricks of class designation 7.5 in foundation and plinth in cement mortar 1:6 (1 cement : 6 coarse sand)", "Masonry", "cum",
        walls_g * 0.23 * (ph + 0.15), f"Ground walls {walls_g:.1f} m × 0.23 × ({ph} + 0.15) m", [w["id"] for w in G["walls"]], "6.1.1", conf, [sheet_ref(G)], f"drawing wall lengths; plinth height: {pb('plinth_height')}")
    v230, a115, t230, t115 = 0.0, 0.0, [], []
    for i, s in enumerate(plans):
        ops, m = OP[i], mult[i]
        te, ti = M(s, "t_ext"), M(s, "t_int")
        v = (M(s, "L_ext") * wall_h - a_open(ops, ext=True)) * te * m
        a = (M(s, "L_int") * wall_h - a_open(ops, kind="door", ext=False)) * m
        if ti >= 0.2:
            v += a * ti
            a = 0
        v230 += v
        a115 += a
        t230.append(f"{fl(i)}: ({M(s, 'L_ext'):.1f} m × {wall_h:.2f} − {a_open(ops, ext=True):.1f} m² openings) × {te} × {m}")
        t115.append(f"{fl(i)}: ({M(s, 'L_int'):.1f} m × {wall_h:.2f} − {a_open(ops, kind='door', ext=False):.1f} m² doors) × {m}")
    a115 += M(T, "envelope_perimeter") * parapet
    add("mas_230", "Brick work with common burnt clay F.P.S. (non modular) bricks of class designation 7.5 in superstructure above plinth level up to floor V level in cement mortar 1:6 (1 cement : 6 coarse sand)", "Masonry", "cum",
        v230, "; ".join(t230) + f" (wall height = floor {h} − beam {beam_d})", [w["id"] for s in plans for w in s["walls"] if w["ext"]], "6.4.1", conf, None, f"drawing wall lengths & openings; floor height: {pb('floor_height')}; beam depth {'schedule' if beams else 'assumed'}")
    add("mas_115", "Half brick masonry with common burnt clay F.P.S. (non modular) bricks of class designation 7.5 in superstructure above plinth level up to floor V level in cement mortar 1:4 (1 cement : 4 coarse sand)", "Masonry", "sqm",
        a115, "; ".join(t115) + f"; parapet {M(T, 'envelope_perimeter'):.1f} m × {parapet} m", [w["id"] for s in plans for w in s["walls"] if not w["ext"]], "6.13.1", conf * 0.95, None, f"drawing wall lengths & doors; parapet {parapet} m: {pb('parapet_height')}")

    # ---------------------------------------------------------------- PLASTER, FLOORING, PAINTING (floor by floor)
    def per_floor(fn):
        return sum(fn(s, OP[i]) * mult[i] for i, s in enumerate(plans))

    def rooms_of(types=None, neg=False):
        return [r for s in plans for r in s["rooms"] if types is None or ((r["type"] in types) != neg)]

    int_pl = per_floor(lambda s, ops: sum(r["perimeter"] for r in s["rooms"]) * (h - ts) - (a_open(ops, kind="door", ext=False) * 2 + a_open(ops, ext=True)))
    add("plaster_int", "12 mm cement plaster of mix 1:6 (1 cement : 6 coarse sand) on internal walls", "Plastering", "sqm",
        int_pl, f"Σ per floor (room perimeters × {h - ts:.3f} m − openings) × storeys", [r["id"] for r in rooms_of()], "13.4.1", conf)
    add("plaster_ceil", "6 mm cement plaster 1:3 to ceiling underside of RCC slab", "Plastering", "sqm",
        carpet_tot, "Σ carpet area × storeys", [r["id"] for r in rooms_of()], "13.16.1", conf)
    ext_pl = per_floor(lambda s, ops: M(s, "envelope_perimeter") * h - a_open(ops, ext=True)) + Pg * ph + M(T, "envelope_perimeter") * parapet * 2
    add("plaster_ext", "15 mm cement plaster on rough side of single or half brick wall of mix 1:4 (1 cement : 4 coarse sand) on external walls", "Plastering", "sqm",
        ext_pl, f"Σ envelope perimeter × {h} m − openings per floor + plinth {ph} m + parapet both faces {parapet} m", [w["id"] for s in plans for w in s["walls"] if w["ext"]], "13.1.1", conf)

    WETR, toilets, kitchens = rooms_of(WET), rooms_of({"toilet"}), rooms_of({"kitchen"})

    def msum(rs, fn):
        return sum(fn(r) * mult[i] for i, s in enumerate(plans) for r in s["rooms"] if r in rs)

    dry = rooms_of(WET, neg=True)
    if p["finish"] == "economy":
        add("floor_kota", "Kota stone flooring 25 mm thick polished in rooms", "Flooring", "sqm",
            msum(dry, lambda r: r["area"]), "Σ dry room areas × storeys", [r["id"] for r in dry], "11.26.1", conf)
    else:
        add("floor_vit", "Providing and laying vitrified floor tiles 600×600 mm on cement mortar in living, bedrooms and kitchen", "Flooring", "sqm",
            msum(dry, lambda r: r["area"]), "Σ dry room areas × storeys", [r["id"] for r in dry], "11.41.2", conf)
    add("floor_antiskid", "Providing and laying ceramic glazed floor tiles of size 300x300 mm in toilets, bathrooms and wet areas", "Flooring", "sqm",
        msum(WETR, lambda r: r["area"]), "Σ wet room areas × storeys", [r["id"] for r in WETR], "11.46.2", conf * 0.9)
    add("dado", "Providing and fixing 1st quality ceramic glazed wall tiles dado in toilets and kitchen", "Flooring", "sqm",
        msum(toilets, lambda r: r["perimeter"] * 2.1) + msum(kitchens, lambda r: r["perimeter"] * 0.6), "Σ toilet perimeters × 2.1 + kitchen perimeters × 0.6", [r["id"] for r in toilets + kitchens], "11.37.1", conf * 0.9, None, "drawing perimeters; dado heights 2.1 m (toilet) / 0.6 m (kitchen) assumed")
    add("skirting", "Providing and laying vitrified floor tiles 600x600 mm as skirting in dry rooms", "Flooring", "sqm",
        msum(dry, lambda r: r["perimeter"] * 0.1) - per_floor(lambda s, ops: sum(o["w"] for o in ops if o["kind"] == "door") * 0.1), "(Σ dry room perimeters − door widths) × 0.10", [r["id"] for r in dry], "11.41.3", conf, None, "drawing perimeters; skirting height 100 mm assumed")
    add("granite", "Providing and fixing granite stone slab with table rubbed, edges rounded for kitchen counter platform", "Flooring", "sqm",
        msum(kitchens, lambda r: 3.0 * 0.6), "3.0 m × 0.6 m per kitchen × storeys", [r["id"] for r in kitchens], "11.27.1", 0.75, None, "assumed — 3.0 m counter per kitchen (norm)")
    paint_int = int_pl + carpet_tot - msum(toilets, lambda r: r["perimeter"] * 2.1)
    add("putty", "Providing and applying white cement based putty over the plastered wall surface", "Painting", "sqm", paint_int, "Internal plaster + ceiling − toilet dado", ["rooms"], "13.80", conf)
    add("paint_int", "Acrylic emulsion paint interior walls and ceilings two coats", "Painting", "sqm", paint_int, "Internal plaster + ceiling − toilet dado", ["rooms"], "13.61.1", conf)
    add("paint_ext", "Finishing walls with Acrylic Smooth exterior paint of required shade new work two or more coats including priming coat of exterior primer", "Painting", "sqm", ext_pl, "= external plaster area", ["external walls"], "13.82.1", conf)
    a_door_t = per_floor(lambda s, ops: a_open(ops, kind="door"))
    a_win_t = per_floor(lambda s, ops: a_open(ops, kind="window"))
    add("paint_enamel", "Painting with synthetic enamel paint of approved brand and manufacture to give an even shade two or more coats on new work, doors and grills", "Painting", "sqm",
        a_door_t * 2 + a_win_t * 0.5, "Door area × 2 faces + grills 0.5 × window area", [o["id"] for o in all_ops if o["kind"] == "door"], "13.43.1", 0.8, None, op_basis)

    # ---------------------------------------------------------------- DOORS & WINDOWS
    def by_mark(kind):
        cnt = {}
        for i, ops in enumerate(OP):
            for o in ops:
                if o["kind"] == kind:
                    k = o.get("tag") or f"{o['w']:.2f}×{o['h']:.2f}"
                    c = cnt.setdefault(k, [0, o["w"], o["h"]])
                    c[0] += mult[i]
        return "; ".join(f"{k}: {v[0]} × {v[1]:.2f}×{v[2]:.2f}" for k, v in sorted(cnt.items()))

    door_ids = [o["id"] for o in all_ops if o["kind"] == "door"]
    win_ids = [o["id"] for o in all_ops if o["kind"] == "window"]
    add("door_shutter", "Providing and fixing ISI marked flush door shutters conforming to IS : 2202 non-decorative type 35 mm thick including stainless steel butt hinges", "Doors & Windows", "sqm",
        a_door_t, by_mark("door") + f" ({op_note})", door_ids, "9.21.1", conf * 0.95, refs_all + sorted(set(sched_src.values())), op_basis)
    add("door_frame", "Providing and fixing door frame 100 mm x 60 mm, measured in running metre", "Doors & Windows", "m",
        per_floor(lambda s, ops: sum(2 * o["h"] + o["w"] for o in ops if o["kind"] == "door")), "Σ (2 × height + width) per door × storeys", door_ids, "9.48.1", conf * 0.95, None, op_basis)
    win_key, win_desc, win_code = ("window_upvc", "UPVC sliding windows with toughened glass and mosquito mesh", "21.4") if p["window_type"] == "upvc" \
        else ("window_alu", "Aluminium sliding windows anodised with 5 mm glass glazing", "21.1.1")
    add(win_key, win_desc, "Doors & Windows", "sqm", a_win_t, by_mark("window") + f" ({op_note})", win_ids, win_code, conf * 0.95, refs_all + sorted(set(sched_src.values())), op_basis)
    add("grills", "Providing and fixing M.S. grills of required pattern in frames of windows fixed to openings with rawl plugs screws", "Doors & Windows", "kg", a_win_t * 12, "Window area × 12 kg/m²", win_ids, "10.25.1", 0.75, None, "drawing window area; grill weight 12 kg/m² assumed")

    # ---------------------------------------------------------------- STAIRS (other construction element)
    stairs = rooms_of({"stair"})
    if stairs:
        add("rcc_stair", "Reinforced cement concrete in staircase waist slab, landings and steps 1:1.5:3 (M20)", "RCC Works", "cum",
            msum(stairs, lambda r: r["area"] * 0.15 * 1.30),
            "Σ stair-room plan area × 0.15 m waist × 1.30 (slope & steps) × storeys",
            [r["id"] for r in stairs], "5.3.3", 0.6, None, "drawing stair area; waist 150 mm and slope factor 1.30 assumed (no stair section)")

    # ---------------------------------------------------------------- WATERPROOFING
    add("wp_roof", "Roof terrace waterproofing with brick bat coba and membrane", "Waterproofing", "sqm",
        M(T, "plinth_area"), f"Roof = top floor plinth {M(T, 'plinth_area'):.2f} m²", ["envelope"], "22.4.1", conf, [sheet_ref(T)])
    add("wp_wet", "Cementitious waterproofing coating in toilets and wet areas floor plus 300 mm upturn", "Waterproofing", "sqm",
        msum(WETR, lambda r: r["area"] + r["perimeter"] * 0.3), "Σ (wet area + perimeter × 0.3) × storeys", [r["id"] for r in WETR], "22.9", conf * 0.9)

    if p.get("include_services", True):
        lp = msum(rooms_of(), lambda r: ROOM_POINTS.get(r["type"], (3, 1))[0])
        pp = msum(rooms_of(), lambda r: ROOM_POINTS.get(r["type"], (3, 1))[1])
        add("elec_light", "Electrical wiring light point fan point with modular switch and copper conductor", "Electrical", "point", lp, "Σ room-type norms (living 6, bedroom 4, kitchen 3 …)", ["rooms"], "1.1.1", 0.7, None, "assumed — norm per room / fixture (no services drawing)")
        add("elec_power", "Electrical wiring power socket outlet 6A/16A points", "Electrical", "point", pp, "Σ room-type norms", ["rooms"], "1.11.1", 0.7, None, "assumed — norm per room / fixture (no services drawing)")
        add("elec_db", "Distribution board with MCB and RCCB per floor", "Electrical", "each", n_tot, f"1 per floor × {n_tot}", [], "1.32", 0.85, None, "assumed — norm per room / fixture (no services drawing)")
        add("wc", "Water closet European WC with cistern sanitary fixture", "Plumbing & Sanitary", "each", msum(toilets, lambda r: 1), "1 per toilet", [r["id"] for r in toilets], "17.1.1", 0.85, None, "assumed — norm per room / fixture (no services drawing)")
        add("basin", "Wash basin with fittings and pillar tap", "Plumbing & Sanitary", "each", msum(toilets, lambda r: 1) + n_tot, "1 per toilet + 1 per floor", [r["id"] for r in toilets], "17.7.1", 0.8, None, "assumed — norm per room / fixture (no services drawing)")
        add("sink", "Stainless steel kitchen sink with drain board", "Plumbing & Sanitary", "each", msum(kitchens, lambda r: 1), "1 per kitchen", [r["id"] for r in kitchens], "17.11", 0.85, None, "assumed — norm per room / fixture (no services drawing)")
        add("cpvc", "Providing and fixing CPVC pipes for hot and cold water supply internal work 20 mm nominal dia pipes", "Plumbing & Sanitary", "m", msum(toilets, lambda r: 12) + msum(kitchens, lambda r: 8), "12 m per toilet + 8 m per kitchen", [r["id"] for r in toilets + kitchens], "18.7.1", 0.65, None, "assumed — norm per room / fixture (no services drawing)")
        add("swr", "UPVC SWR soil and waste pipes 110 mm", "Plumbing & Sanitary", "m", msum(toilets, lambda r: 8) + n_tot * h * 2, "8 m per toilet + 2 vertical stacks", [r["id"] for r in toilets], "19.7.1", 0.65, None, "assumed — norm per room / fixture (no services drawing)")
        beds = max(1, len(rooms_of({"bedroom"})))
        add("tank", "Overhead PVC water storage tank capacity in litres", "Plumbing & Sanitary", "litre",
            max(1000, math.ceil(beds * 2 * 135 * 1.5 / 500) * 500), f"{beds} bedrooms × 2 persons × 135 lpcd × 1.5 day", [], "18.39", 0.7, None, "assumed — norm per room / fixture (no services drawing)")
        if kitchens:
            add("modular_kitchen", "Modular kitchen base cabinets BWP plywood carcass laminate finish with hardware", "Miscellaneous", "m",
                msum(kitchens, lambda r: 3.0), "3.0 running metre per kitchen", [r["id"] for r in kitchens], None, 0.6, None, "assumed — norm per room / fixture (no services drawing)")
    return items


# Expert mapping table: take-off item -> CPWD DSR 2023 (civil) item, in order of preference.
# Used first when the code exists in the loaded rate library with the same unit; otherwise the NLP matcher decides.
DSR_MAP = {
    "site_clearance": ["2.31"], "excavation": ["2.8.1"], "backfill": ["2.25"], "sand_fill": ["2.27"],
    "pcc_found": ["4.1.8"], "pcc_floor": ["4.1.3"],
    "rcc_footing": ["5.1.2"], "rcc_column": ["5.2.2"], "rcc_beam": ["5.3"], "rcc_slab": ["5.3"], "rcc_lintel": ["5.3"],
    "fw_found": ["5.9.1"], "fw_slab": ["5.9.3"], "fw_beam": ["5.9.5"], "fw_col": ["5.9.6"],
    "steel_footing": ["5.22.6"], "steel_column": ["5.22.6"], "steel_beam": ["5.22.6"], "steel_slab": ["5.22.6"], "steel": ["5.22.6"],
    "mas_plinth": ["6.1.2"], "mas_230": ["6.4.2"], "mas_115": ["6.13.2"],
    "plaster_int": ["13.4.2"], "plaster_ceil": ["13.16.1"], "plaster_ext": ["13.5.1"],
    "floor_vit": ["11.41.2"], "floor_antiskid": ["11.37"], "dado": ["8.31"], "skirting": ["11.41.2"], "granite": ["8.10.2"],
    "putty": ["13.80"], "paint_int": ["13.83.2"], "paint_ext": ["13.46.1"], "paint_enamel": ["13.61.1"],
    "door_shutter": ["9.21.1"], "door_frame": ["5.47.2", "9.143"], "grills": ["9.48.2"],
    "wc": ["17.15"], "basin": ["17.7.2"], "sink": ["17.9.1"], "cpvc": ["18.7.2"],
}


PLAUSIBLE = (0.35, 3.0)  # a state item's rate must lie within this ratio of the CPWD rate for the same work


def reference_rates(cpwd_by_code: dict) -> dict:
    """CPWD DSR rate per take-off key (from the expert table) - used only as a sanity reference for other schedules."""
    out = {}
    for key, codes in DSR_MAP.items():
        for c in codes:
            if c in cpwd_by_code:
                out[key] = (cpwd_by_code[c]["rate"], cpwd_by_code[c]["unit"])
                break
    return out


def map_rates(items: list[dict], matcher, sor_by_code: dict, expert: bool = True, ref: dict | None = None) -> None:
    """Map items to rate items of ONE schedule. The expert table (DSR_MAP / hints) holds CPWD DSR codes, so it
    is used only when the schedule uses CPWD DSR numbering (expert=True); otherwise matching is NLP only.
    With no schedule (matcher None) every item stays unmapped — no rate is borrowed from elsewhere."""
    for it in items:
        if matcher is None:
            it.update(candidates=[], sor_code=None, map_score=0, map_method="none", status="unmapped", nlp_agrees_with_rules=False)
            continue
        cands = matcher.search(it["description"], unit=it["unit"], category=it["category"], k=4)
        prefer = [c for c in DSR_MAP.get(it["key"], []) + ([it["hint"]] if it.get("hint") else [])
                  if expert and c in sor_by_code and sor_by_code[c]["unit"] == it["unit"]]
        if prefer:
            r = sor_by_code[prefer[0]]
            it["candidates"] = [dict(code=r["code"], description=r["description"][:140], unit=r["unit"], rate=r["rate"], score=1.0)] +                 [dict(code=c["code"], description=c["description"][:140], unit=c["unit"], rate=c["rate"], score=c["score"]) for c in cands if c["code"] != r["code"]][:3]
            it.update(sor_code=r["code"], map_score=1.0, map_method="table", status="auto")
            it["nlp_agrees_with_rules"] = bool(cands and cands[0]["code"] == r["code"])
            continue
        it["candidates"] = [dict(code=c["code"], description=c["description"][:140], unit=c["unit"], rate=c["rate"], score=c["score"]) for c in cands]
        r_ref = (ref or {}).get(it["key"])

        def plausible(c):
            if c["unit"] != it["unit"] or c["score"] < 0.30:
                return False
            if not expert and r_ref and r_ref[1] == it["unit"] and r_ref[0] > 0:
                q = c["rate"] / r_ref[0]
                return PLAUSIBLE[0] <= q <= PLAUSIBLE[1]
            return True
        top = next((c for c in cands if plausible(c)), None)
        if top and not expert:
            # outside CPWD numbering a text match is only a SUGGESTION: shown first in the picker, not priced
            # until the engineer confirms it (a wrong match must never change the cost silently)
            it["candidates"] = [c for c in it["candidates"] if c["code"] == top["code"]] + [c for c in it["candidates"] if c["code"] != top["code"]]
            it.update(sor_code=None, map_score=top["score"], map_method="suggested", status="review",
                      map_check=f"suggested {top['code']} (rate {top['rate']:,.0f}) — confirm to apply")
            it["nlp_agrees_with_rules"] = False
            continue
        if top:
            it["sor_code"] = top["code"]
            it["map_score"] = top["score"]
            it["map_method"] = "nlp"
            # outside the CPWD expert table a text match is never accepted silently
            it["status"] = "auto" if (expert and top["score"] >= 0.42) else "review"
            if not expert and r_ref:
                it["map_check"] = f"rate {top['rate']:,.0f} vs CPWD {r_ref[0]:,.0f} per {it['unit']} (within {PLAUSIBLE[0]}-{PLAUSIBLE[1]}x)"
        else:
            if cands and not expert and r_ref:
                it["map_check"] = (f"no item of comparable rate (CPWD {r_ref[0]:,.0f} per {it['unit']}); closest text match "
                                   f"{cands[0]['code']} at {cands[0]['rate']:,.0f} rejected")
            it["sor_code"] = None
            it["map_score"] = top["score"] if top else 0
            it["map_method"] = "none"
            it["status"] = "unmapped"
        it["nlp_agrees_with_rules"] = bool(it.get("hint") and it.get("sor_code") == it["hint"])


def price(items: list[dict], sor_by_code: dict, overrides: dict, P: dict, exclude=None) -> dict:
    """Price every line. `exclude(row) -> None | (kind, reason)`: kind 'scope' → listed in `out_of_scope`; kind
    'unresolved' → listed in `unresolved` (quantity not supported by the evidence). Both are still quantified and priced
    for reference but are NOT in category totals, subtotal, taxes, total or the excluded (unpriced) list."""
    p = {**DEFAULT_PARAMS, **(P or {})}
    ci = float(p["cost_index"])
    uplift = {"economy": 0.92, "standard": 1.0, "premium": 1.28}[p["finish"]]
    out = []
    for it in items:
        o = overrides.get(it["key"], {})
        row = dict(it)
        if o.get("sor_code"):
            row["sor_code"] = o["sor_code"]
            row["map_method"] = "user"
        row["qty_auto"] = it["qty"]
        row["qty_user"] = o.get("qty") is not None
        row["rate_user"] = o.get("rate") is not None
        if o.get("qty") is not None:
            row["auto_qty"] = row["qty"]
            row["qty"] = float(o["qty"])
        sor = sor_by_code.get(row.get("sor_code")) if row.get("sor_code") else None
        base_rate = sor["rate"] if sor else None
        if sor is not None and it.get("sor_factor") and not o.get("sor_code"):
            base_rate = sor["rate"] * it["sor_factor"]
            row["rate_note"] = f"SOR rate {sor['rate']:,.2f} per {sor['unit']} × {it['sor_factor']:g}"
        if it.get("included") and not o.get("sor_code") and o.get("rate") is None:
            base_rate = 0.0
            row["sor_desc_override"] = "Included in another item: " + it["included"]
        der = it.get("derived") if not o.get("sor_code") else None
        if sor is None and der and der.get("ok"):
            base_rate = der["rate"]
            row["sor_code"] = ("EST:" if it.get("map_method") == "estimated" else "RA:") + it["key"]
            row["sor_desc_override"] = f"{der['description']} — {der['basis']}"
        if o.get("rate") is not None:
            base_rate = float(o["rate"])
        row["sor_desc"] = sor["description"] if sor else row.pop("sor_desc_override", None)
        row["sor_unit"] = sor["unit"] if sor else None
        f = ci * (uplift if row["category"] in PREMIUM_CATS else 1.0)
        row["rate"] = round(base_rate * f, 2) if base_rate is not None else None
        row["base_rate"] = base_rate
        row["amount"] = round(row["qty"] * row["rate"], 2) if row["rate"] is not None else 0.0
        if o.get("status"):
            row["status"] = o["status"]
        elif o.get("qty") is not None or o.get("rate") is not None or o.get("sor_code"):
            row["status"] = "edited"
        if row["rate"] is None:
            row["status"] = "unmapped"
        row["note"] = o.get("note", "")
        out.append(row)
    out.sort(key=lambda r: (CATEGORY_ORDER.index(r["category"]) if r["category"] in CATEGORY_ORDER else 99))
    for i, r in enumerate(out, 1):
        r["sno"] = i
    for r in out:
        ex = exclude(r) if exclude else None
        r["in_scope"] = ex is None
        r["exclusion"] = dict(kind=ex[0], reason=ex[1]) if ex else None
    out_of_scope = [dict(key=r["key"], description=r["description"], qty=r["qty"], unit=r["unit"], category=r["category"],
                         amount=r["amount"], reason=r["exclusion"]["reason"]) for r in out if r["exclusion"] and r["exclusion"]["kind"] == "scope"]
    unresolved = [dict(key=r["key"], description=r["description"], qty=r["qty"], unit=r["unit"], category=r["category"],
                       amount=r["amount"], reason=r["exclusion"]["reason"]) for r in out if r["exclusion"] and r["exclusion"]["kind"] == "unresolved"]
    cats = {}
    for r in out:
        if not r["in_scope"]:
            continue
        cats.setdefault(r["category"], 0.0)
        cats[r["category"]] += r["amount"]
    subtotal = sum(cats.values())
    cont = subtotal * float(p["contingency"]) / 100
    cess = subtotal * float(p["cess"]) / 100
    gst = (subtotal + cont) * float(p["gst"]) / 100
    total = subtotal + cont + cess + gst
    excluded = [dict(key=r["key"], description=r["description"], qty=r["qty"], unit=r["unit"], category=r["category"],
                     reason=r.get("map_check") or ("needs rate — no usable item in the selected schedule" if r["status"] == "unmapped"
                                                     else "rate suggestion awaiting engineer confirmation"))
                for r in out if r["rate"] is None and r["in_scope"]]
    estimated = [dict(key=r["key"], description=r["description"], unit=r["unit"], rate=r["rate"],
                      basis=(r.get("derived") or {}).get("basis")) for r in out if r.get("map_method") == "estimated" and r["rate"] is not None and r.get("status") != "edited" and r["in_scope"]]
    return dict(items=out, excluded=excluded, estimated=estimated, out_of_scope=out_of_scope, unresolved=unresolved,
                complete=not excluded and not unresolved,
                categories=[dict(name=k, amount=round(v, 2)) for k, v in cats.items()],
                subtotal=round(subtotal, 2), contingency=round(cont, 2), cess=round(cess, 2), gst=round(gst, 2),
                total=round(total, 2))
