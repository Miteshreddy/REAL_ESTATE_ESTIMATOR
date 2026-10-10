"""Room intelligence: normalised labels, room types, habitable flag, table regions and apartment / unit grouping.

Raw OCR text is always kept (raw_label); nothing is deleted — a region that is really part of a printed table is moved
to sheet['rejected_regions'] with the reason, and every unit assignment says how it was made.
"""
from __future__ import annotations

import difflib
import math
import re

VOCAB = ["BED ROOM", "M.BED ROOM", "MASTER BED ROOM", "GUEST BED ROOM", "CHILDREN BED ROOM", "LIVING", "DINING", "DRAWING", "KITCHEN",
         "TOILET", "M.TOILET", "COMMON TOILET", "BATH", "WASH", "UTILITY", "POOJA", "DRESS", "BALCONY", "SIT OUT", "VERANDAH",
         "CORRIDOR", "LOBBY", "FOYER", "PASSAGE", "REFUGE AREA", "SHAFT", "DUCT", "ELECTRICAL ROOM", "STAIRCASE", "LIFT", "GOODS LIFT",
         "STORE", "OFFICE", "HALL", "STUDY", "PARKING", "PORTICO", "SERVICE", "COMMON", "RECEPTION", "WAITING", "CABIN", "CONFERENCE",
         "WARD", "CLASS ROOM", "LAB", "LIBRARY", "PANTRY", "SECURITY"]
TYPE_OF = [(r"BED", "bedroom"), (r"LIVING|FAMILY", "living"), (r"DINING", "dining"), (r"DRAWING", "drawing"), (r"KITCHEN|PANTRY", "kitchen"),
           (r"TOILET|W\.?C|BATH|WASH", "toilet"), (r"UTILITY", "utility"), (r"POOJA", "pooja"), (r"DRESS", "dress"),
           (r"BALCONY|SIT ?OUT|VERANDAH", "balcony"), (r"CORRIDOR|PASSAGE", "corridor"), (r"LOBBY|FOYER|RECEPTION|WAITING", "lobby"),
           (r"REFUGE", "refuge"), (r"SHAFT|DUCT", "shaft"), (r"ELECTRICAL", "electrical"), (r"STAIR", "staircase"), (r"LIFT", "lift"),
           (r"SERVICE|STORE", "service"), (r"COMMON", "common"), (r"OFFICE|CABIN|CONFERENCE|HALL|CLASS|LAB|LIBRARY|WARD|STUDY", "office_zone")]
HABITABLE = {"bedroom", "living", "dining", "drawing", "pooja", "dress", "office_zone"}
COMMON = {"corridor", "lobby", "refuge", "shaft", "electrical", "staircase", "lift", "common", "service"}


def normalise(raw: str) -> tuple[str, float]:
    """'TOIET-2' → ('TOILET-2', 0.91); 'BED ROOM-1 BEDRO' → ('BED ROOM-1', 1.0); '6'6"WIDECORRIDOR' → ('CORRIDOR', 0.9)."""
    s = (raw or "").upper()
    if UNIT_TAG.search(s) and not re.search(r"BED|TOILET|KITCHEN|LIVING|DINING", s):
        return "", 0.0  # an apartment tag ('3BHK 1711 Sft'), not a room name
    s = re.sub(r"(?<=[A-Z])['’](?=[A-Z])", "", s)
    s = re.sub(r"\d+\s*['′’°\"*]\s*\d*\s*['′’°\"*]?(\s*[X×]\s*\d+\s*['′’°\"*]?\s*\d*\s*['′’°\"*]?)?", " ", s)  # dimensions
    s = re.sub(r"[^A-Z0-9.\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s or re.fullmatch(r"SPACE \d+", s) or not re.search(r"[A-Z]{3}", s):
        return "", 0.0
    m = re.search(r"(?:^|[\s-])(\d{1,2})(?=\s|$)", s)
    suffix = "-" + m.group(1) if m else ""
    words = [w for w in re.split(r"[\s]+", re.sub(r"-?\d{1,2}(?=\s|$)", " ", s)) if w and re.search(r"[A-Z]", w)]
    probes = {" ".join(words), "".join(words)} | set(words) | {" ".join(words[i:i + 2]) for i in range(len(words) - 1)}
    best, score = " ".join(words), 0.0
    flat = "".join(words)
    for cand in VOCAB + ["GOODS LIFT"]:
        c_flat = cand.replace(" ", "").replace(".", "")
        for p_ in probes:
            r = difflib.SequenceMatcher(None, p_.replace(" ", "").replace(".", ""), c_flat).ratio()
            if r > score:
                best, score = cand, r
        if len(c_flat) >= 5 and c_flat[:-1] in flat.replace(".", "") and score < 0.9:  # run-together OCR ('WIDEBALCONY')
            best, score = cand, 0.9
    if score < 0.72:
        return " ".join(words) + suffix, round(score, 2)
    return best + suffix, round(score, 2)


def room_type(label: str) -> str:
    for rx, t in TYPE_OF:
        if re.search(rx, label or ""):
            return t
    return "unknown"


UNIT_TAG = re.compile(r"\b([1-6])\s*BHK\b|\b(\d{3,4}(?:\.\d+)?)\s*(?:SFT|SQ\.?\s*FT|SQFT)\b|\b(?:FLAT|UNIT|APT)\s*[-#:]?\s*([A-Z]?\d{1,4}[A-Z]?)\b"
                     r"|\b([A-Z]-\d{3,4})\b")


def _table_boxes(items):
    """A printed table (area statement, schedule): a dense cluster of numeric cells that are not dimension strings.
    Returns bounding boxes (metres) of clusters with at least 6 such cells within 4 m of each other."""
    num = [it for it in items if not re.search(r"\d\s*['′’°\"*]?\s*[X×]\s*\d", it["t"].upper())
           and (re.fullmatch(r"[\s(]*[\d.,]+\s*(SFT\.?|SQ\.?\s*FT)?[\s)]*", it["t"].upper()) or len(re.findall(r"\d+", it["t"])) >= 3
                or re.fullmatch(r"[\s(]*SFT[\s)]*", it["t"].upper()))]
    boxes, seen = [], set()
    for i, a in enumerate(num):
        if i in seen:
            continue
        cl, stack = {i}, [i]
        while stack:
            j = stack.pop()
            for k, c in enumerate(num):
                if k not in cl and math.hypot(c["x"] - num[j]["x"], c["y"] - num[j]["y"]) < 4.0:
                    cl.add(k)
                    stack.append(k)
        seen |= cl
        if len(cl) >= 6:
            xs, ys = [num[k]["x"] for k in cl], [num[k]["y"] for k in cl]
            # text columns of the same rows (flat type, facing …) belong to the table too
            for it in items:
                if any(abs(it["y"] - num[k]["y"]) < 0.35 for k in cl) and min(xs) - 8 <= it["x"] <= max(xs) + 8:
                    xs.append(it["x"])
                    ys.append(it["y"])
            boxes.append((min(xs) - 1.0, min(ys) - 1.0, max(xs) + 1.0, max(ys) + 1.0))
    return boxes


def _inside(b, x, y):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def annotate(sheet: dict) -> dict:
    rooms = sheet.get("rooms") or []
    items = sheet.get("text_items") or []
    for r in rooms:
        # area hierarchy: written dimensions > calibrated polygon (furniture inside a room must not shrink it)
        if r.get("label_dims") and r.get("area") and "polygon_area" not in r:
            a = float(r["label_dims"][0]) * float(r["label_dims"][1])
            r["polygon_area"] = r["area"]
            if 0.6 <= a / max(r["area"], 0.01) <= 1.6:
                r["area"], r["area_basis"] = round(a, 2), "explicit dimensions"
            else:
                r["area_basis"] = "calibrated geometry (written dimensions implausible for this polygon)"
        else:
            r.setdefault("area_basis", "calibrated geometry")
        raw = r.get("raw_label") or r.get("ocr_text") or r.get("name", "")
        r["raw_label"] = raw
        lab, sim = normalise(raw)
        r["normalized_label"] = lab or None
        r["label_confidence"] = sim
        rt = room_type(lab)
        r["room_type"] = rt if rt != "unknown" else (r.get("type") if r.get("type_source") == "label-nlp" else "unknown")
        if r["room_type"] in ("unknown", None) and (r.get("area") or 0) >= 60:
            r["room_type"] = "open_zone"  # large unlabelled space (hall / open office / atrium) — not split into fake rooms
        r["habitable"] = r["room_type"] in HABITABLE
        if lab and sim >= 0.72 and lab != r.get("name"):
            r["name"] = lab
    if any(r.get("area_basis") == "explicit dimensions" for r in rooms) and isinstance(sheet.get("metrics"), dict):
        sheet["metrics"]["carpet_area_polygon"] = sheet["metrics"].get("carpet_area")
        sheet["metrics"]["carpet_area"] = round(sum(r.get("area", 0) for r in rooms), 2)
    # regions inside a printed table are not rooms
    tables = _table_boxes(items)
    keep, rejected = [], list(sheet.get("rejected_regions") or [])
    for r in rooms:
        if any(_inside(b, r.get("cx", -1e9), r.get("cy", -1e9)) for b in tables) and r["room_type"] == "unknown":
            rejected.append(dict(id=r["id"], area=r.get("area"), reason="inside a printed table (area statement), not a room", raw_label=r["raw_label"]))
        else:
            keep.append(r)
    if len(keep) != len(rooms):
        sheet["rooms"] = keep
        sheet["rejected_regions"] = rejected
        rooms = keep
    # unit anchors: BHK / area / flat tags outside tables, merged when within 3 m of each other
    anchors = []
    for it in items:
        if any(_inside(b, it["x"], it["y"]) for b in tables) or len(re.findall(r"\d+", it["t"])) >= 3:
            continue
        m = UNIT_TAG.search(it["t"].upper())
        if not m:
            continue
        near = next((a for a in anchors if math.hypot(a["x"] - it["x"], a["y"] - it["y"]) < 3.0), None)
        a = near or dict(x=it["x"], y=it["y"], tags=[])
        a["tags"].append(it["t"])
        if not near:
            anchors.append(a)
    units = []
    if len(anchors) >= 2:
        private = [r for r in rooms if r["room_type"] not in COMMON]
        cen = [(a["x"], a["y"]) for a in anchors]
        assign = {}
        for _ in range(4):  # k-means seeded at the unit tags (apartments are spatially compact, separated by the core)
            for r in private:
                assign[r["id"]] = min(range(len(cen)), key=lambda i: math.hypot(cen[i][0] - r["cx"], cen[i][1] - r["cy"]))
            for i in range(len(cen)):
                mem = [r for r in private if assign.get(r["id"]) == i]
                if mem:
                    cen[i] = (sum(r["cx"] for r in mem) / len(mem), sum(r["cy"] for r in mem) / len(mem))
        for i, a in enumerate(anchors):
            mem = [r for r in private if assign.get(r["id"]) == i]
            tag = " ".join(dict.fromkeys(a["tags"]))
            bhk = re.search(r"([1-6])\s*BHK", tag.upper())
            sft = re.search(r"(\d{3,4}(?:\.\d+)?)\s*(?:SFT|SQ\.?\s*FT|SQFT)", tag.upper())
            uid = f"U{i + 1}"
            for r in mem:
                r["unit"] = uid
            units.append(dict(id=uid, label=tag, bhk=int(bhk.group(1)) if bhk else None,
                              stated_area_sft=float(sft.group(1)) if sft else None, rooms=[r["id"] for r in mem],
                              measured_area_m2=round(sum(r.get("area", 0) for r in mem), 2),
                              bedrooms=sum(1 for r in mem if r["room_type"] == "bedroom"),
                              toilets=sum(1 for r in mem if r["room_type"] == "toilet"),
                              basis="rooms assigned to the nearest unit tag (k-means seeded at the BHK / area labels); review"))
        for r in rooms:
            if r["room_type"] in COMMON:
                r["unit"] = "common"
    sheet["units"] = units
    return sheet
