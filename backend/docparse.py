"""Reads the written information on drawing sheets.

Works on text rows from any source (PDF text layer, DXF TEXT/MTEXT, OCR of scans):
  * sheet type     - floor plan / section / elevation / structural / schedule
  * floor label    - ground / first / typical …
  * levels         - plinth, floor-to-floor heights, sill, lintel, parapet, foundation depth, slab thickness
  * door & window schedule        - D1 900 X 2100 6 NOS
  * footing / column / beam / slab schedules from structural drawings
"""
from __future__ import annotations

import re

import nlp

# --------------------------------------------------------------------------- rows
def group_rows(words, tol=3.0):
    """words: [(text, x0, y0, x1, y1)] -> list of (row_text, x, y) grouped by baseline and gaps."""
    rows = []
    for w in sorted(words, key=lambda w: ((w[2] + w[4]) / 2, w[1])):
        yc = (w[2] + w[4]) / 2
        if rows and abs(rows[-1]["y"] - yc) <= tol:
            rows[-1]["w"].append(w)
        else:
            rows.append(dict(y=yc, w=[w]))
    out = []
    for r in rows:
        ws = sorted(r["w"], key=lambda w: w[1])
        # split a baseline into separate phrases where the horizontal gap is large (different labels on one line)
        chunk = [ws[0]]
        for a, b in zip(ws, ws[1:]):
            h = max(1.0, a[4] - a[2])
            if b[1] - a[3] > h * 3.5:
                out.append((" ".join(c[0] for c in chunk), (chunk[0][1] + chunk[-1][3]) / 2, r["y"]))
                chunk = []
            chunk.append(b)
        out.append((" ".join(c[0] for c in chunk), (chunk[0][1] + chunk[-1][3]) / 2, r["y"]))
    return out


# --------------------------------------------------------------------------- sheet type & floor
KIND_RULES = [
    ("structural", r"FOUNDATION\s+PLAN|FOOTING\s+(SCHEDULE|DETAIL|LAYOUT)|COLUMN\s+(SCHEDULE|LAYOUT)|BEAM\s+(SCHEDULE|LAYOUT)|REINFORCEMENT|STRUCTURAL|SLAB\s+DETAIL|BAR\s+BENDING"),
    ("section", r"\bSECTION\b|\bSEC\.?\s*[A-Z]-[A-Z]"),
    ("elevation", r"ELEVATION"),
    ("schedule", r"(DOOR|WINDOW).{0,10}SCHEDULE|SCHEDULE OF OPENINGS"),
    ("floor_plan", r"FLOOR\s+PLAN|\bPLAN\b"),
]


def classify_sheet(texts: list[str], n_rooms: int) -> str:
    blob = " | ".join(texts).upper()
    for kind, pat in KIND_RULES:
        if re.search(pat, blob):
            if kind == "floor_plan" and n_rooms < 2:
                continue
            if kind in ("section", "elevation") and n_rooms >= 3 and re.search(r"FLOOR\s+PLAN", blob):
                return "floor_plan"
            return kind
    return "floor_plan" if n_rooms >= 2 else "other"


FLOOR_WORDS = [("basement", -1), ("stilt", 0), ("ground", 0), ("first", 1), ("second", 2), ("third", 3), ("fourth", 4), ("fifth", 5), ("terrace", 9)]


def parse_floor(texts: list[str]) -> dict | None:
    blob = " ".join(texts).upper()
    m = re.search(r"TYPICAL\s+((?:(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH)\s*(?:&|AND|,|TO)?\s*)+)FLOOR\s+PLAN", blob)
    if m:
        order = ["FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH"]
        lv = [order.index(x) + 1 for x in re.findall(r"FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH", m.group(1))]
        rep = (max(lv) - min(lv) + 1) if " TO " in m.group(1) else len(lv)
        return dict(label="Typical floor", level=min(lv), repeat=max(1, rep))
    m = re.search(r"TYPICAL\s+FLOOR\s+PLAN(?:\s*\(?\s*(\d)\w*\s*(?:-|TO)\s*(\d)\w*)?", blob)
    if m:
        a, b = (int(m.group(1)), int(m.group(2))) if m.group(1) else (1, 1)
        return dict(label="Typical floor", level=a, repeat=max(1, b - a + 1))
    for w, lvl in FLOOR_WORDS:
        if re.search(rf"\b{w.upper()}\s+FLOOR\s+PLAN\b", blob):
            return dict(label=f"{w.title()} floor", level=lvl, repeat=1)
    m = re.search(r"\b(\d)(?:ST|ND|RD|TH)\s+FLOOR\s+PLAN", blob)
    if m:
        return dict(label=f"Floor {m.group(1)}", level=int(m.group(1)), repeat=1)
    return None


# --------------------------------------------------------------------------- levels (sections / elevations)
LVL = r"([+\-±]?\s*\d+\.\d{2,3})"


def _lv(s):
    return float(s.replace("±", "").replace(" ", ""))


def parse_levels(texts: list[str]) -> dict:
    out, ffl = {}, []
    for t in texts:
        u = t.upper()
        if re.match(r"\s*(?:[A-Z]{1,2}\d{1,2}[A-Z]?)\b", u) or re.search(r"\d{3}\s*[X×]\s*\d{3}", u) or re.search(r"AREA|SQ\.?\s*M|SQ\.?\s*FT", u):
            continue  # schedule rows (F1, C1, PB1, D1 …) are not levels
        vals = re.findall(LVL, u)
        if not vals:
            m = re.search(r"SLAB\D{0,20}(\d{3})\s*(?:MM)?\s*TH", u)
            if m:
                out["slab_thickness"] = int(m.group(1)) / 1000
            m = re.search(r"PARAPET\D{0,20}(\d+(?:\.\d+)?)\s*(M|MM)?\b", u)
            if m and "PARAPET" in u:
                v = float(m.group(1))
                out["parapet_height"] = v / 1000 if v > 20 else v
            continue
        v = _lv(vals[0])
        if re.search(r"PLINTH|\bGFL\b|GROUND\s+FLOOR\s+(LVL|LEVEL|FFL)", u):
            out["plinth_level"] = v
            ffl.append(v)
        elif re.search(r"FOOTING|FOUNDATION|\bFDN\b|P\.?C\.?C", u) and v < 0:
            out["foundation_depth"] = abs(v)
        elif re.search(r"LINTEL", u):
            out["lintel_level"] = v
        elif re.search(r"\bSILL", u):
            out["sill_level"] = v
        elif re.search(r"PARAPET", u):
            out["parapet_top"] = v
        elif re.search(r"FFL|FLOOR\s+(LVL|LEVEL)|TOP\s+OF\s+SLAB|\bTOS\b|ROOF|TERRACE", u):
            ffl.append(v)
        m = re.search(r"SLAB\D{0,20}(\d{3})\s*(?:MM)?\s*TH", u)
        if m:
            out["slab_thickness"] = int(m.group(1)) / 1000
    ffl = sorted(set(ffl))
    if len(ffl) >= 2:
        hs = [round(b - a, 3) for a, b in zip(ffl, ffl[1:]) if 2.4 <= b - a <= 6]
        if hs:
            out["floor_heights"] = hs
            out["floor_height"] = round(sum(hs) / len(hs), 3)
            out["floors_from_levels"] = len(hs)
            if out.get("parapet_top"):
                out["parapet_height"] = round(out["parapet_top"] - ffl[-1], 3)
    if "plinth_level" in out:
        out["plinth_height"] = round(out["plinth_level"], 3)
        if out.get("sill_level"):
            out["sill_height"] = round(out["sill_level"] - out["plinth_level"], 3)
        if out.get("lintel_level"):
            out["lintel_height"] = round(out["lintel_level"] - out["plinth_level"], 3)
    return out


# --------------------------------------------------------------------------- door / window schedule & tags
OPEN_MARK = r"\b((?:D|W|V|KW|DW|MD|SD|FD)\d{1,2}[A-Z]?)\b"
DIM2 = r"(\d+(?:\.\d+)?)\s*(?:MM|M)?\s*[X×\*]\s*(\d+(?:\.\d+)?)"
COUNT = r"(\d{1,3})\s*(?:NOS|NO\.?|NUMBERS|QTY)\b(?!\.?\s*-\s*\d)"  # "13 NOS.-12" is a bar callout, not a count


def _m(v):
    v = float(v)
    return v / 1000 if v > 20 else v


def parse_opening_schedule(texts: list[str]) -> dict:
    sched = {}
    for t in texts:
        u = t.upper()
        mk = re.match(r"\s*" + OPEN_MARK, u)
        dm = re.search(DIM2, u)
        if not (mk and dm):
            continue
        w, h = _m(dm.group(1)), _m(dm.group(2))
        if not (0.3 <= w <= 4 and 0.3 <= h <= 3.5):
            continue
        c = re.search(COUNT, u)
        kind = "door" if mk.group(1)[0] in "DMSF" else "window"
        sched[mk.group(1)] = dict(w=round(w, 3), h=round(h, 3), count=int(c.group(1)) if c else None, kind=kind, text=t.strip()[:120])
    return sched


def opening_tags(labels) -> list:
    """labels: [(text,x,y)] in any frame -> [(mark,x,y)] for short tags like 'D1', 'W2'."""
    return [(t.strip().upper(), x, y) for t, x, y in labels if re.fullmatch(r"\s*" + OPEN_MARK + r"\s*", t.strip().upper())]


# --------------------------------------------------------------------------- structural schedules
BAR = r"(?:[YT#Φφ]\s*(\d{1,2})|(\d{1,2})\s*(?:MM\s*)?(?:Φ|φ|#|DIA|TOR|TMT))"
# "4-Y16", "4 NOS Y16", and the common drawing notation "13 NOS.-12" (13 bars of 12 mm)
NBAR = r"(\d{1,2})\s*(?:-|NOS\.?\s*|NO\.?\s*)(?:" + BAR + r"|-\s*(\d{1,2})\b)"
SPC = r"(?:" + BAR + r"|(\d{1,2}))\s*@\s*(\d{2,3})"
DIM3 = r"(\d{3,4})\s*[X×\*]\s*(\d{3,4})\s*[X×\*]\s*(\d{3,4})"


def _bar(m, i=1):
    return int(m.group(i) or m.group(i + 1))


def _bars(u):
    out = []
    for m in re.finditer(NBAR, u):
        d = m.group(2) or m.group(3) or m.group(4)
        if d and 6 <= int(d) <= 40:
            out.append((int(m.group(1)), int(d)))
    return out


def _spacing(u, after=None):
    s = u if after is None else u[u.find(after):] if after in u else ""
    m = re.search(SPC, s)
    if not m:
        return None
    d = m.group(1) or m.group(2) or m.group(3)
    return (int(d), int(m.group(4))) if d and 6 <= int(d) <= 32 else None


def parse_structural(texts: list[str]) -> dict:
    res = dict(footings=[], columns=[], beams=[], slabs=[])
    for t in texts:
        u = t.upper().replace("Ø", "Φ")
        c = re.search(COUNT, u)
        cnt = int(c.group(1)) if c else None
        m = re.match(r"\s*(F\d{1,2}[A-Z]?)\b", u)
        if m and re.search(DIM3, u):
            L, B, D = (int(x) / 1000 for x in re.search(DIM3, u).groups())
            sp = _spacing(u)
            res["footings"].append(dict(mark=m.group(1), L=L, B=B, D=D, count=cnt, bar=sp, text=t.strip()[:140]))
            continue
        m = re.match(r"\s*(C\d{1,2}[A-Z]?)\b", u)
        d2 = re.search(r"(\d{3})\s*[X×\*]\s*(\d{3})", u)
        if m and d2:
            ties = _spacing(u, "TIE") or _spacing(u, "RING") or _spacing(u, "STIR") or _spacing(u)
            res["columns"].append(dict(mark=m.group(1), b=int(d2.group(1)) / 1000, d=int(d2.group(2)) / 1000, count=cnt,
                                       main=_bars(u), ties=ties, text=t.strip()[:140]))
            continue
        m = re.match(r"\s*((?:PB|GB|RB|FB|TB|B)\d{1,2}[A-Z]?)\b", u)
        if m and d2:
            Lm = re.search(r"(?:\bL\s*=|LENGTH|TOTAL\s+LENGTH)\s*(\d+(?:\.\d+)?)\s*(M|MM)?", u)
            top = _bars(u[u.find("TOP"):]) if "TOP" in u else []
            bot = _bars(u[u.find("BOT"):]) if "BOT" in u else []
            if not top and not bot:
                bb = _bars(u)
                top, bot = bb[:1], bb[1:2]
            res["beams"].append(dict(mark=m.group(1), b=int(d2.group(1)) / 1000, d=int(d2.group(2)) / 1000, count=cnt or 1,
                                     length=None if not Lm else (float(Lm.group(1)) / 1000 if Lm.group(2) == "MM" or (not Lm.group(2) and float(Lm.group(1)) > 400) else float(Lm.group(1))),
                                     top=top[:1], bot=bot[:1], stirrup=_spacing(u, "STR") or _spacing(u, "STIR") or _spacing(u),
                                     plinth=m.group(1).startswith(("PB", "GB", "FB")), text=t.strip()[:140]))
            continue
        if re.search(r"\bSLAB\b|\bS\d\b", u):
            th = re.search(r"(\d{3})\s*(?:MM)?\s*TH", u) or re.search(r"THICK(?:NESS)?\W{0,6}(\d{3})", u)
            main = _spacing(u, "MAIN") or _spacing(u)
            dist = _spacing(u, "DIST")
            if th or main:
                res["slabs"].append(dict(thk=int(th.group(1)) / 1000 if th else None, main=main, dist=dist or main, text=t.strip()[:140]))
    return res


def count_marks(labels, marks) -> dict:
    """How many times each structural mark (F1, C1 …) is written on a layout drawing."""
    out = {}
    for t, _, _ in labels:
        u = t.strip().upper()
        if u in marks:
            out[u] = out.get(u, 0) + 1
    return out


def read_sheet_text(rows, labels, n_rooms):
    texts = [r[0] for r in rows]
    kind = classify_sheet(texts, n_rooms)
    info = dict(kind=kind, floor=parse_floor(texts), levels=parse_levels(texts), schedule=parse_opening_schedule(texts),
                structural=parse_structural(texts) if kind in ("structural", "schedule", "other") or re.search(r"FOOTING|COLUMN|BEAM", " ".join(texts).upper()) else None,
                notes=nlp.parse_project_notes(texts))
    st = info["structural"]
    if st:
        marks = {f["mark"] for f in st["footings"]} | {c["mark"] for c in st["columns"]}
        placed = count_marks(labels, marks)
        for grp in ("footings", "columns"):
            for e in st[grp]:
                if not e.get("count") and placed.get(e["mark"]):
                    e["count"], e["count_src"] = placed[e["mark"]], "counted on layout"
                elif e.get("count"):
                    e["count_src"] = "schedule"
        if not any(st.values()):
            info["structural"] = None
    return info
