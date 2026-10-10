"""Door / window pipeline: enrich every opening and reconcile schedule vs geometry vs detector counts.

Per opening: id, kind, type, width, height, position, host_wall (external / internal), room_from / room_to, unit, floor,
source_page, bbox, confidence, basis (which detector / rule found it).
"""
from __future__ import annotations

import math

DOOR_TYPES = ("main", "internal", "toilet", "service", "balcony", "sliding", "fire", "double", "other")


def _rooms_near(o, rooms, k=2, max_d=4.0):
    d = sorted(((math.hypot(r["cx"] - o["x"], r["cy"] - o["y"]), r) for r in rooms if "cx" in r), key=lambda t: t[0])
    return [r for dist, r in d[:k] if dist <= max_d]


def enrich(sheet: dict) -> dict:
    rooms = sheet.get("rooms") or []
    fl = (sheet.get("floor_info") or {}).get("floor_occurrences") or ([sheet["floor"]["level"]] if (sheet.get("floor") or {}).get("level") is not None else [])
    for o in sheet.get("openings") or []:
        near = _rooms_near(o, rooms)
        types = [r.get("room_type") or r.get("type") for r in near]
        o["room_from"] = near[0]["id"] if near else None
        o["room_to"] = near[1]["id"] if len(near) > 1 else ("outside" if o.get("ext") else None)
        o["host_wall"] = "external" if o.get("ext") else "internal"
        o["unit"] = next((r.get("unit") for r in near if r.get("unit") and r.get("unit") != "common"), "common" if near else None)
        o["floor"] = fl
        o["source_page"] = sheet.get("sheet")
        o["bbox"] = [round(o["x"] - o["w"] / 2, 2), round(o["y"] - 0.15, 2), round(o["x"] + o["w"] / 2, 2), round(o["y"] + 0.15, 2)]
        o["basis"] = o.get("source") or "symbol / segmentation"
        o.setdefault("confidence", 0.7)
        if o["kind"] == "door":
            o["type"] = ("double" if o["w"] >= 1.4 else "toilet" if "toilet" in types else "balcony" if "balcony" in types
                         else "main" if o.get("ext") or "lobby" in types or "corridor" in types else "service" if "utility" in types
                         else "internal")
        else:
            o["type"] = "ventilator" if o["w"] < 0.75 or "toilet" in types else "large_glazing" if o["w"] >= 2.4 else "window"
    return sheet


def reconcile(sheet: dict, detector_counts: dict | None = None) -> list[dict]:
    """Compare schedule count vs geometric count vs detector count. Disagreement → OPENING COUNT CONFLICT (never auto-resolved)."""
    ops = sheet.get("openings") or []
    geo = dict(door=sum(1 for o in ops if o["kind"] == "door"), window=sum(1 for o in ops if o["kind"] == "window"))
    sched = {}
    sc = sheet.get("schedule") if isinstance(sheet.get("schedule"), dict) else {}
    for mark, row in sc.items():  # docparse: {mark: {w, h, count, kind, text}}
        k = row.get("kind") or ("door" if str(mark)[:1].upper() in "DMSF" else "window")
        if row.get("count"):
            sched[k] = sched.get(k, 0) + int(row["count"])
    # explicit per-mark matching: schedule mark count vs openings tagged with that mark on the plan
    for mark, row in sc.items():
        tagged = sum(1 for o in ops if o.get("tag") == mark)
        if row.get("count") and tagged and tagged != int(row["count"]):
            out_mark = dict(level="CONFLICT", code="OPENING COUNT CONFLICT", kind=row.get("kind"), mark=mark,
                            counts=dict(schedule=int(row["count"]), tagged_on_plan=tagged),
                            message=f"{mark}: schedule says {row['count']}, plan shows {tagged} tagged openings — review")
            sheet.setdefault("_mark_conflicts", []).append(out_mark)
    det = detector_counts or sheet.get("detector_counts") or {}
    out = []
    for kind in ("door", "window"):
        vals = {"geometry": geo[kind]}
        if kind in sched:
            vals["schedule"] = sched[kind]
        if kind in det:
            vals["detector"] = det[kind]
        if len(vals) > 1 and (max(vals.values()) - min(vals.values())) > max(1, 0.1 * max(vals.values())):
            out.append(dict(level="CONFLICT", code="OPENING COUNT CONFLICT", kind=kind, counts=vals,
                            message=f"{kind} count disagrees between sources {vals} — review; no source is chosen automatically"))
    return out + sheet.pop("_mark_conflicts", [])
