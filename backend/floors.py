"""Floor occurrence / repetition read from drawing text.

A plan sheet often stands for several storeys: "TYPICAL FLOOR PLAN (5TH TO 12TH)", "18TH, 28TH & 38TH FLOOR",
"FLOOR NOS. 3, 5, 7". This module returns WHICH floors the drawn plan occurs on — not how many floors the building
has (a refuge-floor sheet says nothing about the other 35 floors).

    floor_occurrences  list of floor numbers the plan applies to (empty when only "typical" is stated)
    floor_start / floor_end / floor_step / repeated_count
    typical_floor / refuge_floor
    source_text / confidence / sources (which text items agreed)
"""
from __future__ import annotations

import re

WORD_ORD = {"GROUND": 0, "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6, "SEVENTH": 7, "EIGHTH": 8,
            "NINTH": 9, "TENTH": 10, "ELEVENTH": 11, "TWELFTH": 12}
ORD = r"(?:(?<!\d)\d{1,3}\s*(?:ST|ND|RD|TH)?|" + "|".join(WORD_ORD) + r")"
FLOOR = r"FL(?:OO|O|00|0O|O0)?R?S?"


def ocr_fix(t: str) -> str:
    """Common OCR digit confusions inside ordinals: 1STH → 18TH (8 read as S), 2O → 20, l8 → 18, FL0OR → FLOOR."""
    import unicodedata
    t = unicodedata.normalize("NFKC", t).upper()  # full-width OCR punctuation ('，' '＆') → ASCII
    t = re.sub(r"FL[O0]{2}R", "FLOOR", t)
    t = re.sub(r"(\d)S(TH)", r"\g<1>8\2", t)      # '1STH' is not an ordinal; S here is an 8
    t = re.sub(r"(?<=\d)[O](?=\d|TH|ST|ND|RD)", "0", t)
    t = re.sub(r"(?<=\d)(ST|ND|RD|TH)(?=[A-Z0-9&,])", r"\1 ", t)  # '4TH,5TH&6THFLOORS' → '4TH ,5TH &6TH FLOORS'
    t = re.sub(r"\s*([,&])\s*", r" \1 ", t)
    t = re.sub(r"\b[lI](?=\d)", "1", t)
    t = re.sub(r"(\d)\s+(ST|ND|RD|TH)\b", r"\1\2", t)
    return t


def _num(tok: str) -> int | None:
    tok = tok.strip()
    if tok in WORD_ORD:
        return WORD_ORD[tok]
    m = re.match(r"(\d{1,3})", tok)
    return int(m.group(1)) if m else None


def _ords(s: str) -> list[int]:
    return [n for n in (_num(x) for x in re.findall(ORD, s)) if n is not None]


def _candidates(blob: str):
    """(kind, floors, text, strength) found in one normalised text blob."""
    out = []
    # range: 5TH TO 12TH FLOOR / FLOORS 5 - 12 / TYPICAL FLOOR PLAN (5TH-12TH)
    for m in re.finditer(rf"({ORD})\s*(?:TO|UPTO|THRU|-|–)\s*({ORD})\s*(?:{FLOOR}\b)?", blob):
        ctx = blob[max(0, m.start() - 40): m.end() + 25]
        if not re.search(rf"\b{FLOOR}\b|TYPICAL", ctx):
            continue
        # mix ratios / dimensions are not floors: 'P.C.C 1:4:8-100MM THICK' next to a 'FLOOR FINISHING' note
        if re.search(r"[:/.]\s*$", blob[max(0, m.start() - 2): m.start()]) or re.match(r"\s*(?:MM|CM|M|MTR|THK|THICK)\b", blob[m.end():]):
            continue
        ordinal = all(re.search(r"(?:ST|ND|RD|TH)$", g.strip()) or g.strip() in WORD_ORD for g in (m.group(1), m.group(2)))
        near = blob[max(0, m.start() - 15): m.start()] + m.group(0)
        if not ordinal and not re.search(rf"\b{FLOOR}\b|TYPICAL", near):  # bare 'N-M' only with FLOOR(S) right next to it
            continue
        a, b = _num(m.group(1)), _num(m.group(2))
        if a is not None and b is not None and 0 <= a < b <= 200 and not re.search(r"\d\s*[X×]\s*\d|['\"]", m.group(0)):
            out.append(("range", list(range(a, b + 1)), m.group(0).strip(), 0.9))
    # list: 18TH, 28TH & 38TH FLOOR   /  FIRST AND SECOND FLOOR
    for m in re.finditer(rf"((?:{ORD})(?:\s*(?:,|&|AND|/)\s*(?:{ORD}))+)\s*{FLOOR}\b", blob):
        nums = _ords(m.group(1))
        toks = re.findall(ORD, m.group(1))
        has_suffix = all(re.search(r"(?:ST|ND|RD|TH)$", t.strip()) or t.strip() in WORD_ORD for t in toks)  # every element is an ordinal
        if len(nums) >= 2 and has_suffix and all(0 <= n <= 200 for n in nums):
            out.append(("list", sorted(set(nums)), m.group(0).strip(), 0.95))
    # FLOOR NOS. 3, 5, 7
    for m in re.finditer(rf"{FLOOR}\s*(?:NOS?\.?|NUMBERS?)\s*[:.\-]?\s*(\d{{1,3}}(?:\s*(?:,|&|AND)\s*\d{{1,3}})+)", blob):
        nums = [int(x) for x in re.findall(r"\d{1,3}", m.group(1))]
        out.append(("list", sorted(set(nums)), m.group(0).strip(), 0.9))
    # basement / cellar (B1, B2 …) → negative levels; LEVEL n
    for m in re.finditer(r"\b(?:BASEMENT|CELLAR)\s*-?\s*(\d)?\s*(?=FLOOR|PLAN|LEVEL|PARKING)|\bB([1-4])\s*(?:FLOOR|LEVEL)\b", blob):
        out.append(("single", [-int(m.group(1) or m.group(2) or 1)], m.group(0).strip(), 0.75))
    for m in re.finditer(r"\bLEVEL\s*[-:]?\s*(\d{1,3})\b", blob):
        out.append(("single", [int(m.group(1))], m.group(0).strip(), 0.7))
    # single: 18TH FLOOR (PLAN)
    for m in re.finditer(rf"(?<![,&/\d])\b({ORD})\s*{FLOOR}\b(?!\s*(?:,|&|AND|TO|-)\s*{ORD})", blob):
        n = _num(m.group(1))
        if n is not None and re.search(r"\d(?:ST|ND|RD|TH)|" + "|".join(WORD_ORD), m.group(1)):
            out.append(("single", [n], m.group(0).strip(), 0.7))
    return out


def parse(texts: list[str], title: str | None = None) -> dict | None:
    items = [t for t in ([title] if title else []) + list(texts or []) if t]
    norm = [ocr_fix(t) for t in items]
    blob_all = " ".join(norm)
    found = []
    # each text alone and windows of up to 4 consecutive texts (labels stacked over lines); then the same over only the
    # 'floor-ish' fragments, because OCR reading order interleaves the lines of a table cell with neighbouring cells
    fragment = re.compile(rf"[\s,&/()\-]*(?:(?:{ORD}|{FLOOR}|AND|TO)[\s,&/()\-]*)+")
    seqs = [list(enumerate(norm)), [(i, t) for i, t in enumerate(norm) if fragment.fullmatch(t)]]
    for seq in seqs:
        for a in range(len(seq)):
            for w in range(1, 5):
                if a + w > len(seq):
                    break
                seg = " ".join(t for _, t in seq[a:a + w])
                for kind, fl, txt, s in _candidates(seg):
                    found.append((kind, tuple(fl), txt, s, seq[a][0]))
    typical = bool(re.search(r"\bTYPICAL\b", blob_all))
    refuge = bool(re.search(r"\bREFUGE\b", blob_all))
    if not found and re.search(r"\bTERRACE\s+(?:FLOOR\s+)?PLAN\b|\bROOF\s+PLAN\b", blob_all):
        return dict(floor_occurrences=[], floor_start=None, floor_end=None, floor_step=None, repeated_count=None, typical_floor=False,
                    refuge_floor=False, floor_kind="terrace", source_text="TERRACE / ROOF PLAN", confidence=0.7, sources=1,
                    label="Terrace / roof plan", level=None, repeat=0, note="terrace / roof plan — not an additional storey")
    if not found:
        if typical:
            return dict(floor_occurrences=[], floor_start=None, floor_end=None, floor_step=None, repeated_count=None, typical_floor=True,
                        refuge_floor=refuge, source_text="TYPICAL FLOOR", confidence=0.4, sources=1,
                        label="Typical floor (floors not stated)", level=None, repeat=1,
                        note="the sheet is a typical floor but does not say which floors — enter the number of storeys")
        return None
    # agreement between independent text items raises confidence; prefer multi-floor statements over singles
    by = {}
    for kind, fl, txt, s, i in found:
        k = fl
        e = by.setdefault(k, dict(kind=kind, floors=list(fl), texts=set(), idx=set(), strength=s))
        e["texts"].add(txt)
        e["idx"].add(i)
        e["strength"] = max(e["strength"], s)
    # a candidate that is a subset of another is a partial read of the same statement → it supports the larger one
    for a in by.values():
        for b in by.values():
            if a is not b and set(a["floors"]) < set(b["floors"]) and len(a["floors"]) > 1:
                b["idx"] |= a["idx"]
                b["texts"] |= a["texts"]
    best = max(by.values(), key=lambda e: (len(e["floors"]) > 1, len(e["idx"]), e["strength"], len(e["floors"])))
    fl = best["floors"]
    step = (fl[1] - fl[0]) if len(fl) > 1 and all(fl[j + 1] - fl[j] == fl[1] - fl[0] for j in range(len(fl) - 1)) else None
    conf = min(0.98, best["strength"] + 0.03 * (len(best["idx"]) - 1))
    lab = ("Refuge floor" if refuge else "Typical floor" if typical or len(fl) > 1 else "Floor") + \
          (f" — floors {', '.join(map(str, fl))}" if len(fl) <= 12 else f" — floors {fl[0]} to {fl[-1]}")
    return dict(floor_occurrences=fl, floor_start=fl[0], floor_end=fl[-1], floor_step=step, repeated_count=len(fl),
                typical_floor=typical or len(fl) > 1, refuge_floor=refuge, source_text=sorted(best["texts"], key=len)[-1],
                confidence=round(conf, 2), sources=len(best["idx"]), label=lab, level=fl[0], repeat=len(fl),
                note=("this plan occurs on the listed floors; the total number of storeys of the building is NOT stated by this sheet"
                      if len(fl) > 1 else None))
