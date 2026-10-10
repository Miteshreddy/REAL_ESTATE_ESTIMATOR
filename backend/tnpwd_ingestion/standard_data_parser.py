"""TN PWD Standard Data Book (civil) → analysis items.

Layout (columns located from each page's header row  Sl.No | Qty. | Unit | Description | Rate | Per | Amount):
    description lines …  (the serial number is printed beside one of them, often the middle line)
    [variant heading, e.g. 'M 20 CONCRETE' or 'A. For footing depth …']
    qty | unit | resource / sub-data name | per        component lines (names may wrap to a second line)
    Total for N <unit>   /  Rate for 1 <unit>          the quantities above are for N units
    Add … @x% …                                         percentage additions (water charges 1% …)
The book prints NO rates — they come from the SOR basic rates of the same year (rate_analysis.py).
"""
from __future__ import annotations

import re

import pymupdf

NUM = re.compile(r"^\d{1,6}(\.\d{1,4})?$")
UNIT_TOK = re.compile(r"^(cu\.?\s?m\.?|sq\.?\s?m\.?|sqm|cum|kg\.?|kgs|nos?\.?|no\.|each|lit(re)?s?\.?|ltr|mt\.?|m|rm|rmt|metre|qtl|"
                      r"quintal|tonne|ls|l\.s\.|set|day|hour|hrs?|km|bag|pair|r\.?m\.?|kl|km\.?)$", re.I)
HEADING = re.compile(r"^([A-H]\s*[.)]|\(?[ivx]{1,4}\)|M[\s-]?\d\d\b|for\s|using\s|with\s|in\s)|^[A-Z0-9 :./&()-]{4,60}$")


def _lines(page):
    ws = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, y = [], [], None
    for w in ws:
        yc = (w[1] + w[3]) / 2
        if y is not None and yc - y > 3.0:
            lines.append(sorted(cur, key=lambda v: v[0]))
            cur = []
        cur.append(w)
        y = yc if y is None or not cur[:-1] else (y + yc) / 2 if abs(yc - y) <= 3.0 else yc
    if cur:
        lines.append(sorted(cur, key=lambda v: v[0]))
    return lines


def _header(lines):
    for ws in lines[:14]:
        t = {w[4].lower().rstrip("."): w[0] for w in ws}
        if "qty" in t and "unit" in t and "per" in t:
            return dict(qty=t["qty"], unit=t["unit"], desc=t["unit"] + 26, per=t["per"])  # names start ~26 pt right of the unit column (the header word is centred)
    return None


def parse(path: str, pages=None) -> list[dict]:
    doc = pymupdf.open(path)
    items = []
    cur = None          # current data item
    var = None          # current variant (receiving components)
    pending, pending_no, pending_page = [], None, None
    last_was_comp = False
    last_add = False
    hdr = None

    def flush_variant():
        nonlocal var
        if var is not None and var["components"] and cur is not None:
            cur["variants"].append(var)
        var = None

    def start_block(pno):
        """First component line after descriptive text: decide new item vs new variant."""
        nonlocal cur, var, pending, pending_no
        flush_variant()
        text = " ".join(pending).strip()
        label = None
        if pending and HEADING.match(pending[-1].strip()) and len(pending) > 1:
            label = pending[-1].strip()
            text = " ".join(pending[:-1]).strip()
        if pending_no is not None:
            cur = dict(data_no=pending_no, page=pending_page or pno + 1, description=text, variants=[])
            items.append(cur)
            var = dict(label=label, components=[], per_qty=None, per_unit=None, additions=[])
        elif cur is not None:
            var = dict(label=(text or None), components=[], per_qty=None, per_unit=None, additions=[])
        pending, pending_no = [], None

    for pno in (pages or range(len(doc))):
        lines = _lines(doc[pno])
        hdr = _header(lines) or hdr
        if not hdr:
            continue
        sl_max = hdr["qty"] - 8
        for ws in lines:
            txt = " ".join(w[4] for w in ws)
            low = txt.lower()
            if len(ws) <= 8 and re.match(r"^(sl\.?|no\.?|qty\.?|unit|description|rate|per|amount)(\s|$)", low):
                continue
            if len(ws) == 1 and re.fullmatch(r"\d{1,4}", ws[0][4]) and ws[0][0] > sl_max:
                continue  # printed page number
            if last_add and (txt.startswith("(") or "sub-total" in low or "sub total" in low) and var is not None:
                var["additions"][-1]["text"] += " " + txt
                continue
            last_add = False
            # serial number (left margin) — belongs to the description being collected
            if ws[0][0] < sl_max and re.fullmatch(r"\d{1,4}[A-Za-z]?", ws[0][4]):
                pending_no, pending_page = ws[0][4], pno + 1
                ws = ws[1:]
                if not ws:
                    continue
                txt = " ".join(w[4] for w in ws)
                low = txt.lower()
            if ws[0][4].upper() == "LS" and ws[0][0] < hdr["desc"] - 6 and var is not None and var["components"] and not var.get("per_qty"):
                var["components"].append(dict(qty=None, unit="LS", name=" ".join(w[4] for w in ws[1:] if w[0] < hdr["per"] - 14),
                                              per="LS", lump_sum=True))
                continue
            qty_tok = next((w for w in ws if hdr["qty"] - 30 <= w[0] < hdr["unit"] - 4
                            and (NUM.match(w[4].replace(",", "")) or w[4].upper() == "LS")), None)
            unit_tok = next((w for w in ws if hdr["unit"] - 8 <= w[0] < hdr["desc"] - 6 and UNIT_TOK.match(w[4])), None) if qty_tok else None
            if qty_tok is not None and (unit_tok is not None or qty_tok[4].upper() == "LS"):
                if var is None or pending_no is not None or var.get("per_qty"):
                    start_block(pno)
                elif pending:  # text between components of one block: name printed above its qty line, or a sub-heading
                    pre = [t for t in pending if not HEADING.match(t.strip())]
                    var.setdefault("notes", []).extend(t for t in pending if HEADING.match(t.strip()))
                    pending.clear()
                    if pre:
                        var["_prefix"] = " ".join(pre)
                if var is None:
                    last_was_comp = False
                    continue
                name = " ".join(w[4] for w in ws if w[0] > (unit_tok or qty_tok)[0] and w[0] < hdr["per"] - 14)
                per = " ".join(w[4] for w in ws if w[0] >= hdr["per"] - 14).strip() or None
                q = None if qty_tok[4].upper() == "LS" else float(qty_tok[4].replace(",", ""))
                name = (var.pop("_prefix", "") + " " + name).strip()
                var["components"].append(dict(qty=q, unit=(unit_tok[4] if unit_tok else "LS"), name=name, per=per, lump_sum=q is None))
                last_was_comp = True
                continue
            m = re.search(r"(total|rate)\s+for\s+([\d.]+)\s*(.*)$", low)
            if m and var is not None and var["components"]:
                if var.get("per_qty") is None:
                    var["per_qty"] = float(m.group(2).rstrip(".") or 1)
                    var["per_unit"] = m.group(3).strip()[:20] or None
                last_was_comp = False
                continue
            if low.startswith("add") and var is not None and var["components"]:
                p = re.search(r"@\s*([\d.]+)\s*%", low)
                var["additions"].append(dict(text=txt[:140], pct=float(p.group(1)) if p else None))
                last_was_comp = False
                last_add = True
                continue
            if re.match(r"^(sub[\s-]*total|total\b|for\s+1\s*\S*$|rate\b)", low):
                last_was_comp = False
                continue
            # wrapped component name
            if last_was_comp and var is not None and ws[0][0] >= hdr["desc"] - 14 and len(ws) <= 7 and (
                    txt[:1].islower() or re.search(r"(,|\bof|\band|\bother|\bincluding|\bwith|\bfor)$", var["components"][-1]["name"])):
                var["components"][-1]["name"] += " " + txt
                continue
            last_was_comp = False
            pending.append(txt)
    flush_variant()
    for it in items:
        it["description"] = re.sub(r"\s+", " ", it["description"]).strip()
        for v in it["variants"]:
            v["per_qty"] = v["per_qty"] or 1.0
    return [it for it in items if it["variants"]]
