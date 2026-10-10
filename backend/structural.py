"""Structural quantities (Task 8) from what the structural drawings actually state.

* Members come from schedules read by docparse.parse_structural (footings F*, columns C*, beams B*/PB*, slabs).
* Concrete volume of a member is computed ONLY when every dimension needed is written (footing L×B×D; column b×d×height
  needs a storey height → if the height is a default the volume is ASSUMED; beam b×d×length needs a written length).
* Reinforcement: bar bending schedule rows (bar mark, Ø, number, cutting length) → kg = L(m) × n × Ø² / 162.
  BBS steel wins: members covered by a BBS are not counted again from plan schedules (no double counting).
* Anything missing → STRUCTURAL INPUT MISSING / NEEDS ENGINEER REVIEW, never an invented size, bar or spacing.
"""
from __future__ import annotations

import re

STATUS_ORDER = ["SCHEDULE-DERIVED", "DRAWING-DERIVED", "CALCULATED", "ENGINEER-CONFIRMED", "ASSUMED", "NEEDS ENGINEER REVIEW", "STRUCTURAL INPUT MISSING"]


def bar_kg(length_m: float, dia_mm: float, count: int = 1) -> float:
    """IS convention: unit weight (kg/m) = d² / 162 (d in mm)."""
    if length_m is None or dia_mm is None or count is None or length_m < 0 or dia_mm <= 0 or count < 0:
        raise ValueError("bar length, diameter and count are required (no defaults)")
    return length_m * count * dia_mm ** 2 / 162.0


DIAS = {6, 8, 10, 12, 16, 20, 25, 28, 32, 36, 40}


def _bbs_row(u: str):
    toks = re.findall(r"[A-Z]*\d+(?:\.\d+)?|[A-Z]+", u.replace("Φ", "#"))
    for i, t in enumerate(toks):
        m = re.fullmatch(r"(?:Y|T|DIA|#)?(\d{1,2})", t)
        if not m or int(m.group(1)) not in DIAS or i + 2 >= len(toks):
            continue
        if not re.fullmatch(r"\d{1,4}", toks[i + 1]) or not re.fullmatch(r"\d{1,5}(?:\.\d+)?", toks[i + 2]):
            continue
        L = float(toks[i + 2])
        unit = toks[i + 3] if i + 3 < len(toks) and toks[i + 3] in ("MM", "M") else None
        L = L / 1000 if unit == "MM" or (unit is None and L >= 100) else L
        if not 0.1 <= L <= 30:
            continue
        head = toks[:i]
        member = next((x for x in head if re.fullmatch(r"(?:PB|GB|RB|FB|TB|ST|[BCFLS])\d{1,3}[A-Z]?", x)), None)
        mark = next((x for x in reversed(head) if x != member and re.fullmatch(r"[A-Z]{1,2}\d{0,3}", x) and x not in ("BBS", "NO", "NOS")), None)
        return dict(member=member, mark=mark, dia=int(m.group(1)), count=int(toks[i + 1]), cutting_length_m=round(L, 3))
    return None


def parse_bbs(texts: list[str]) -> list[dict]:
    """Bar rows 'C1 a 16 4 3450' / 'B2 M3 T12 6 4.20 M' / 'F1 a Y10 12 1450 MM': member, mark, Ø, number, cutting length.
    A length ≥ 100 without a unit is millimetres. kg = L × n × Ø² / 162."""
    rows = []
    for t in texts:
        r = _bbs_row(t.upper().replace("Ø", "Φ"))
        if r:
            r["kg"] = round(bar_kg(r["cutting_length_m"], r["dia"], r["count"]), 2)
            r["text"] = t.strip()[:120]
            rows.append(r)
    return rows


def _mtype(mark):
    m = (mark or "").upper()
    return "footing" if m.startswith("F") else "column" if m.startswith("C") else "beam" if re.match(r"(PB|GB|RB|FB|TB|B)\d", m) else \
        "slab" if m.startswith("S") else "lintel" if m.startswith("L") else "stair" if m.startswith("ST") else "other"


def compute(sheets: list[dict], params: dict, src: dict | None = None) -> dict:
    src = src or {}
    st = {"footings": [], "columns": [], "beams": [], "slabs": []}
    texts = []
    for s in sheets:
        if not s.get("enabled", True):
            continue
        for k in st:
            st[k] += ((s.get("structural") or {}).get(k) or [])
        if s.get("kind") in ("structural", "schedule") or s.get("structural"):
            texts += s.get("texts") or []
    has = any(st.values())
    bbs = parse_bbs(texts)
    members, missing = [], []
    storeys = max(1, int(params.get("floors") or 1))
    H = (params.get("floor_height") or 0) * storeys + (params.get("foundation_depth") or 0) + (params.get("plinth_height") or 0) or None
    h_assumed = any(src.get(k) in (None, "default") for k in ("floor_height", "floors", "foundation_depth"))
    for f in st["footings"]:
        ok = all(f.get(k) for k in ("L", "B", "D"))
        n = f.get("count")
        members.append(dict(id=f["mark"], type="footing", dims=dict(L=f.get("L"), B=f.get("B"), D=f.get("D")), count=n,
                            volume_each=round(f["L"] * f["B"] * f["D"], 3) if ok else None,
                            volume=round(f["L"] * f["B"] * f["D"] * n, 3) if ok and n else None,
                            status="SCHEDULE-DERIVED" if ok and n else "NEEDS ENGINEER REVIEW",
                            note=None if n else "count of this footing not stated — count the marks on the foundation plan", source=f.get("text")))
    for c in st["columns"]:
        n = c.get("count")
        vol = round(c["b"] * c["d"] * H * n, 3) if (c.get("b") and c.get("d") and H and n) else None
        members.append(dict(id=c["mark"], type="column", dims=dict(b=c.get("b"), d=c.get("d"), height=H), count=n, volume=vol,
                            status=("ASSUMED" if h_assumed else "CALCULATED") if vol is not None else "NEEDS ENGINEER REVIEW",
                            note=(f"column height {H:.2f} m = {storeys} storey(s) × floor height + foundation depth + plinth"
                                  + (" — includes defaults, confirm from sections" if h_assumed else "")) if vol else "count or height missing",
                            source=c.get("text")))
    for b in st["beams"]:
        ok = b.get("b") and b.get("d") and b.get("length")
        members.append(dict(id=b["mark"], type="beam", dims=dict(b=b.get("b"), d=b.get("d"), length=b.get("length")), count=b.get("count"),
                            volume=round(b["b"] * b["d"] * b["length"] * (b.get("count") or 1), 3) if ok else None,
                            status="SCHEDULE-DERIVED" if ok else "NEEDS ENGINEER REVIEW", note=None if ok else "beam length not written in the schedule",
                            source=b.get("text")))
    for i, sl in enumerate(st["slabs"]):
        members.append(dict(id=f"S{i + 1}", type="slab", dims=dict(thickness=sl.get("thk")), count=None, volume=None,
                            status="DRAWING-DERIVED" if sl.get("thk") else "NEEDS ENGINEER REVIEW",
                            note="slab volume = slab area (from plans) × thickness — computed in the take-off", source=sl.get("text")))
    steel = {}
    bbs_members = {r["member"] for r in bbs if r["member"]}
    for r in bbs:
        t = _mtype(r["member"] or r["mark"])
        steel.setdefault(t, dict(kg=0.0, rows=0, basis="bar bending schedule (L × n × Ø²/162)"))
        steel[t]["kg"] = round(steel[t]["kg"] + r["kg"], 2)
        steel[t]["rows"] += 1
    unmapped = sorted(t for t in steel if t not in ("footing", "column", "beam", "slab"))
    if unmapped:
        missing.append(f"NEEDS ENGINEER REVIEW — BBS steel for {', '.join(unmapped)} has no matching take-off line: "
                       ", ".join(f"{t} {steel[t]['kg']} kg" for t in unmapped) + " must be added as an item")
    if not has and not bbs:
        missing.append("STRUCTURAL INPUT MISSING — no structural drawings / schedules: concrete member sizes and reinforcement cannot be derived")
    if has and not bbs:
        missing.append("NEEDS ENGINEER REVIEW — no bar bending schedule: reinforcement weight cannot be verified from the drawings")
    concrete = {}
    for mbr in members:
        if mbr["volume"] is not None:
            concrete.setdefault(mbr["type"], 0.0)
            concrete[mbr["type"]] = round(concrete[mbr["type"]] + mbr["volume"], 3)
    return dict(members=members, bbs_rows=bbs, steel_by_member_type=steel, concrete_by_member_type=concrete, missing=missing,
                bbs_members=sorted(bbs_members), status="STRUCTURAL INPUT MISSING" if not has and not bbs else
                ("COMPLETE FROM DRAWINGS" if all(m["status"] in ("SCHEDULE-DERIVED", "DRAWING-DERIVED", "CALCULATED") for m in members) and bbs
                 else "PARTIAL — NEEDS ENGINEER REVIEW"))
