"""Extract item rates from official State SOR PDFs into the app's import format.

Output per schedule:  <out>.csv  (code, description, unit, rate, category)  +  <out>.meta.json (provenance)
The CSV is then imported through the app's validated importer (POST /api/rate-schedules/{id}/import).

Each source is described by a small spec (pages, column x-ranges, item-code pattern). Rates are copied exactly as
printed; nothing is computed or adjusted. Rows that cannot be read unambiguously are dropped and counted in the
meta file (`skipped`), so the extraction can be audited against the PDF.

Usage:  python import_state_sor.py <spec-name>
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys

import pymupdf

SRC = r"G:\velo\real-estate\sor\official"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "sor", "states")

UNIT_MAP = [(r"^(sq\.?\s*m(tr|etre|eter)?s?|sqm|m2|sq\.?m\.?)$", "sqm"), (r"^(cu\.?\s*m(tr|etre|eter)?s?|cum|m3|cu\.?m\.?)$", "cum"),
            (r"^(r\.?\s*m(t|tr)?|rmt|metre|meter|m|mtr|rm|running\s*m(etre)?|lm)$", "metre"), (r"^(kg|kgs|kilogram)$", "kg"),
            (r"^(no|nos|no\.|each|number|ea|unit)$", "each"), (r"^(litre|ltr|lit|l)$", "litre"), (r"^(quintal|qtl)$", "quintal"),
            (r"^(tonne|ton|mt|t)$", "tonne"), (r"^(set)$", "each set"), (r"^(point|pt)$", "point")]

CATS = [("Earthwork", r"earth\s*work|excavat|filling|back\s*fill|anti.?termite|site clearance|surface dressing"),
        ("Reinforcement", r"reinforcement|tor steel|tmt|thermo.?mechanically|steel bars?\b.*(rcc|reinforc)"),
        ("Formwork", r"centering|shuttering|form\s*work"),
        ("RCC Works", r"reinforced cement concrete|\brcc\b|r\.c\.c"),
        ("Concrete Works", r"cement concrete|plain cement concrete|\bpcc\b|p\.c\.c|lean concrete|concrete"),
        ("Masonry", r"brick\s*work|masonry|block\s*work|solid block|aac block|fly ash brick|stone masonry"),
        ("Plastering", r"plaster|pointing|rendering"),
        ("Flooring", r"floor|tiles?|skirting|dado|granite|marble|kota|vitrified|terrazzo|ips"),
        ("Painting", r"paint|distemper|emulsion|putty|primer|white\s*wash|colour\s*wash|varnish|polish"),
        ("Doors & Windows", r"door|window|shutter|ventilator|frame|glazing|aluminium|upvc|grill"),
        ("Waterproofing", r"water\s*proof|damp proof|dpc|bitumen"),
        ("Electrical", r"wiring|conduit|switch|cable|light point|fan|mcb|db\b|earthing|electric"),
        ("Plumbing & Sanitary", r"pipe|water closet|\bwc\b|wash basin|sink|tap|valve|sanitary|plumbing|gully|manhole|cistern|urinal|trap"),
        ("Roofing", r"roof|weathering course|sheet roofing|tiles? for roof")]


WORDNUM = {"one": "1", "ten": "10", "hundred": "100", "thousand": "1000"}
UNIT_WORDS = [(r"^(square|sq\.?)\s*(metre|meter|mtr|m)s?$", "sqm"), (r"^(cubic|cu\.?)\s*(metre|meter|mtr|m)s?$", "cum"),
              (r"^(running|r\.?)\s*(metre|meter|mtr|m)s?$", "metre"), (r"^(metre|meter)s?$", "metre"), (r"^numbers?$", "each"),
              (r"^kilo\s*grams?$", "kg"), (r"^(metric\s*)?tonnes?$", "tonne"), (r"^kilo\s*metres?$", "km"), (r"^litres?$", "litre")]


def unit_norm(u):
    u = re.sub(r"\s+", " ", u.strip()).strip(". ")
    u = u.replace("m²", "sqm").replace("m2", "sqm").replace("m³", "cum").replace("m3", "cum").replace("Rm", "metre")
    w = u.lower().split(" ", 1)
    if w and w[0] in WORDNUM:
        u = WORDNUM[w[0]] + (" " + w[1] if len(w) > 1 else "")
    m0 = re.match(r"^(\d+(?:\.\d+)?)?\s*(.*)$", u)
    for rx, std in UNIT_WORDS:
        if re.match(rx, (m0.group(2) or "").strip().lower()):
            u = ((m0.group(1) + " ") if m0.group(1) else "") + std
            break
    m = re.match(r"^(?:per\s+)?(\d+(?:\.\d+)?)\s*(.*)$", u, re.I)
    qty, base = (m.group(1), m.group(2)) if m else ("1", u)
    b = base.strip().lower()
    for rx, std in UNIT_MAP:
        if re.match(rx, b, re.I):
            b = std
            break
    if qty in ("1", "1.0", "1.00"):
        return b
    return f"{qty.rstrip('0').rstrip('.') if '.' in qty else qty} {b}"


def category(desc):
    d = desc.lower()
    for name, rx in CATS:
        if re.search(rx, d[:220]):
            return name
    return "Miscellaneous"


RATE = re.compile(r"^\d{1,3}(,\d{2,3})*(\.\d{1,2})?$|^\d+(\.\d{1,2})?$")


def extract_table(pdf, pages, cols, code_rx, sl_rx=r"^\d{1,5}[a-z]?$", unit_rx=None):
    """cols: dict of x-ranges {'sl': (x0,x1), 'code': ..., 'desc': ..., 'unit': ..., 'rate': ...} in PDF points.
    An item starts at a row whose code-column word matches code_rx; its description runs until the next item."""
    doc = pymupdf.open(pdf)
    items, cur, skipped = [], None, []
    inx = lambda w, k: cols[k][0] <= (w[0] + w[2]) / 2 <= cols[k][1]
    for pno in pages:
        page = doc[pno]
        words = sorted(page.get_text("words"), key=lambda w: (round(w[1] / 3), w[0]))
        top = cols.get("top", 60)
        bottom = page.rect.height - cols.get("bottom", 30)
        words = [w for w in words if top <= w[1] <= bottom]
        if cols.get("anchor") == "sl":
            # anchor on the serial number; the item code may wrap over two lines ("TBSC-A.II-" / "15")
            anchors = []
            for w in words:
                if inx(w, "sl") and re.match(sl_rx, w[4]):
                    parts = sorted([c for c in words if inx(c, "code") and -3 <= c[1] - w[1] <= 22], key=lambda c: c[1])
                    code = ""
                    for c in parts:
                        if not code:
                            code = c[4]
                        elif code.endswith(("-", ".")) or re.fullmatch(r"\d+[A-Za-z]?", c[4]):
                            code += c[4]
                        else:
                            break
                    if re.match(code_rx, code):
                        anchors.append((w[0], w[1], w[2], w[3], code))
        else:
            anchors = [w for w in words if inx(w, "code") and re.match(code_rx, w[4])]
        anchors.sort(key=lambda w: w[1])
        # text before the first anchor continues the previous item
        first_y = anchors[0][1] - 2 if anchors else bottom + 1
        if cur is not None:
            cur["desc"] += [w[4] for w in words if w[1] < first_y and inx(w, "desc")]
        for i, a in enumerate(anchors):
            y0 = a[1] - 2
            y1 = anchors[i + 1][1] - 2 if i + 1 < len(anchors) else bottom + 1
            if cur is not None:
                items.append(cur)
            row = [w for w in words if abs(w[1] - a[1]) < 6]
            unit = " ".join(w[4] for w in row if inx(w, "unit"))
            rate = " ".join(w[4] for w in row if inx(w, "rate"))
            cur = dict(code=a[4], page=pno + 1, unit=unit, rate=rate,
                       desc=[w[4] for w in words if y0 <= w[1] < y1 and inx(w, "desc")])
            # unit / rate printed on a later line of the same item (common when the description is long)
            if not cur["rate"] or not RATE.match(cur["rate"].split()[-1]):
                later = [w for w in words if y0 <= w[1] < y1 and inx(w, "rate") and RATE.match(w[4])]
                cur["rate"] = later[0][4] if later else cur["rate"]
                if later and not cur["unit"]:
                    cur["unit"] = " ".join(w[4] for w in words if abs(w[1] - later[0][1]) < 6 and inx(w, "unit"))
    if cur is not None:
        items.append(cur)
    out = []
    for it in items:
        desc = re.sub(r"\s+", " ", " ".join(it["desc"])).strip()
        rate = (it["rate"].split() or [""])[-1]
        if not desc or not it["unit"] or not RATE.match(rate):
            skipped.append(dict(code=it["code"], page=it["page"], unit=it["unit"], rate=it["rate"], why="no unit / rate on the item row"))
            continue
        out.append(dict(code=it["code"], description=desc, unit=unit_norm(it["unit"]), rate=float(rate.replace(",", "")),
                        category=category(desc), page=it["page"]))
    # duplicate codes (an item split across a page break printed twice): keep the first
    seen, uniq = set(), []
    for r in out:
        if r["code"] in seen:
            skipped.append(dict(code=r["code"], page=r["page"], why="duplicate code"))
            continue
        seen.add(r["code"])
        uniq.append(r)
    return uniq, skipped


HEAD = dict(sl=r"^(sl|s\.?\s*no|si\.?\s*no|item\s*no|s\.?no)", code=r"(item\s*code|code|ss\s*item|s\.?\s*s\.?\s*item|sor\s*no|item\s*no\.?\s*$)",
            desc=r"(description|particulars|item of work|name of item)", unit=r"^(unit|units|per)\b", rate=r"(rate|amount|rs\.?)")


def _cols(header, overrides=None):
    """Map table columns to sl / code / desc / unit / rate from the header row text."""
    out = {}
    for i, h in enumerate(header):
        t = re.sub(r"\s+", " ", (h or "")).strip().lower()
        for k, rx in HEAD.items():
            if k not in out and t and re.search(rx, t):
                out[k] = i
                break
    out.update(overrides or {})
    return out


def extract_grid(pdf, pages, code_rx=r".+", overrides=None, need=("desc", "unit", "rate"), fixed=None, hier=False, letter_sub=False, strip_margin=False):
    """Ruled tables (PyMuPDF find_tables). A row with a serial number / code starts an item; rows with an empty
    serial-number cell continue the previous item's description (multi-line cells split over rows or pages)."""
    doc = pymupdf.open(pdf)
    items, skipped, cur, cols, parent = [], [], None, None, ""
    for pno in pages:
        page = doc[pno]
        # rotated text (margin labels, watermarks) must not leak into cells: cell text is rebuilt from the
        # horizontal words only (word -> (block, line) -> line direction)
        dirs = {}
        for b_ in page.get_text("dict")["blocks"]:
            for li, l in enumerate(b_.get("lines", [])):
                dirs[(b_["number"], li)] = abs(l.get("dir", (1, 0))[1]) <= 0.2
        words = [w for w in page.get_text("words") if dirs.get((w[5], w[6]), True)]

        def cell_text(rect):
            if rect is None:
                return None
            x0, y0, x1, y1 = rect
            ws = [w for w in words if x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1]
            ws.sort(key=lambda w: (round(w[1] / 4), w[0]))
            return " ".join(w[4] for w in ws)
        for t in page.find_tables().tables:
            rows = [[cell_text(c) for c in r.cells] for r in t.rows]
            if not rows:
                continue
            c = _cols(rows[0], overrides)
            start = 1
            if fixed and t.col_count == fixed:
                cols, start = dict(overrides), 0  # known layout: header / heading rows are rejected by the code pattern
            elif all(k in c for k in need):
                cols = c
            elif cols is None or t.col_count != max(cols.values()) + 1 and t.col_count < max(cols.values()) + 1:
                continue  # not an item table
            else:
                start = 0  # continuation table without header row
            for r in rows[start:]:
                cell = lambda k: re.sub(r"\s+", " ", (r[cols[k]] or "")).strip() if k in cols and cols[k] < len(r) else ""
                sl, code, desc, unit, rate = cell("sl"), cell("code"), cell("desc"), cell("unit"), cell("rate")
                if strip_margin:  # stacked margin letters ("K", "L O", "1 -") printed down the description column
                    desc = re.sub(r"^(?:[A-Z]\s+|\d\s+-\s+|-\s+){1,3}(?=[A-Z0-9(])", "", desc)
                code = code.replace(" ", "")
                if letter_sub and re.fullmatch(r"\(?[a-z]{1,2}\)?\.?|\(?[ivx]{1,4}\)?\.?", code):
                    code = code.strip("().")
                if letter_sub:
                    if re.fullmatch(r"[a-z]{1,2}|\([a-z]{1,2}\)|[ivx]{1,4}", code):
                        if cur is not None:
                            code = cur.get("parent", cur["code"]) + "." + code.strip("()")
                    elif code:
                        parent = code
                key = code or sl
                if "code" in cols and not re.match(code_rx, code or "-"):
                    if key:
                        continue  # section heading / header row
                if key and (not code or re.match(code_rx, code)):
                    if cur:
                        items.append(cur)
                    cur = dict(code=code or f"S{sl}", page=pno + 1, desc=[desc], unit=unit, rate=rate)
                    if letter_sub:
                        cur["parent"] = parent if "." in code and code.split(".")[-1].isalpha() and parent != code else code
                        if cur["parent"] != code and items:
                            pd = next((x for x in reversed(items) if x["code"] == cur["parent"]), None)
                            if pd:
                                cur["desc"] = [" ".join(pd["desc"]).strip(), "—"] + cur["desc"]
                elif cur and desc and not key:
                    cur["desc"].append(desc)
                    if not cur["rate"] and rate:
                        cur["rate"], cur["unit"] = rate, unit or cur["unit"]
    if cur:
        items.append(cur)
    out, seen = [], set()
    heads = {}
    if hier:  # hierarchical codes (13.64 heading -> 13.64.1 item): headings carry the description of their sub-items
        for it in items:
            if not re.search(r"\d", it["rate"] or ""):
                heads[it["code"]] = re.sub(r"\s+", " ", " ".join(it["desc"])).strip()
    for it in items:
        desc = re.sub(r"\s+", " ", " ".join(it["desc"])).strip()
        if hier and "." in it["code"]:
            parts = it["code"].split(".")
            pre = [heads[".".join(parts[:k])] for k in range(1, len(parts)) if ".".join(parts[:k]) in heads]
            if pre:
                desc = " — ".join(pre[-2:] + [desc])
        toks = [t for t in it["rate"].split() if RATE.match(t)]
        if len(toks) > 1:  # two figures in one cell = cells merged across rows: never glue them, flag instead
            skipped.append(dict(code=it["code"], page=it["page"], rate=it["rate"][:30], why="ambiguous rate cell (several figures)"))
            continue
        rate = toks[0] if toks else ""
        if not desc or not it["unit"] or not RATE.match(rate):
            skipped.append(dict(code=it["code"], page=it["page"], unit=it["unit"], rate=it["rate"][:30], why="no unit / numeric rate (heading, note or rate on request)"))
            continue
        if it["code"] in seen:
            skipped.append(dict(code=it["code"], page=it["page"], why="duplicate code"))
            continue
        if float(rate.replace(",", "")) <= 0:
            skipped.append(dict(code=it["code"], page=it["page"], rate=rate, why="rate printed as 0 (no scheduled rate)"))
            continue
        if not re.search(r"[A-Za-z]", unit_norm(it["unit"])):
            skipped.append(dict(code=it["code"], page=it["page"], unit=it["unit"], why="unit not printed in the source (only a quantity)"))
            continue
        seen.add(it["code"])
        out.append(dict(code=it["code"], description=desc, unit=unit_norm(it["unit"]), rate=float(rate.replace(",", "")),
                        category=category(desc), page=it["page"]))
    return out, skipped


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write(name, rows, skipped, meta, pdf):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "description", "unit", "rate", "category"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})
    meta = dict(meta, source_file=os.path.basename(pdf), source_sha256=sha256(pdf), items=len(rows), skipped=len(skipped),
                skipped_rows=skipped[:500])
    json.dump(meta, open(os.path.join(OUT, name + ".meta.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(name, "items", len(rows), "skipped", len(skipped))


# ------------------------------------------------------------------------------------------------ specs
def telangana_2026_27():
    pdf = os.path.join(SRC, "telangana_2026_27", "ts_csr_2026_27.pdf")
    doc = pymupdf.open(pdf)
    # Part-III Buildings: find its pages by the running header
    pages = [i for i in range(len(doc)) if "Buildings (Part-III) SoR 2026-27" in doc[i].get_text()[:400]
             and doc[i].get_text().lstrip().startswith(("CIVIL ITEMS", "Centering & Scaffolding"))]
    rows, skipped = extract_grid(pdf, pages, code_rx=r"^[A-Z]{2,6}-[A-Z0-9.]+-\d+[A-Za-z]?$")
    meta = dict(name="Telangana Common Schedule of Rates 2026-27 — Part III (Building Works)", authority="Telangana R&B Department",
                department="Board of Chief Engineers (I&CAD, R&B, Buildings, Public Health), Government of Telangana",
                country="India", region="Telangana", authority_level="state", schedule_type="SOR", code_system="TS-CSR",
                year="2026", financial_year="2026-27", effective_from="2026-06-01", currency="INR",
                source="Official government document",
                source_ref="Government of Telangana, Common Schedule of Rates for the year 2026-27 (effective 1 June 2026), "
                           "finalised by the Board of Chief Engineers on 25.05.2026 & 31.05.2026 — "
                           "https://www.pred.telangana.gov.in/uploads/documents/doc-1786011352680-dce1d071-2aba-40d8-92c2-5dc6ef1cd301.pdf",
                notes="Part III (Building Works) item rates as printed (pages " + f"{pages[0] + 1}-{pages[-1] + 1}" + "). Rates include "
                      "contractor's profit & overheads as stated in the SOR. Area allowances on the LABOUR component apply by "
                      "location (Common Preamble 1): Greater Hyderabad +40%, other Municipal Corporations +25%, District "
                      "Headquarters / other municipalities +20%, notified industrial areas +20%, agency/tribal areas per GO. "
                      "Labour shares are not printed per item, so these allowances are not applied automatically.")
    write("telangana_csr_2026_27_buildings", rows, skipped, meta, pdf)


SPECS = {"telangana_2026_27": telangana_2026_27}

def andhra_2025_26():
    pdf = os.path.join(SRC, "andhra_2025_26", "ap_buildings_sor_2025_26.pdf")
    doc = pymupdf.open(pdf)
    rows, skipped = extract_grid(pdf, range(8, len(doc)), code_rx=r"^[A-Z]{2,4}-[A-Z]{1,3}\.?\d+[A-Za-z]?$",
                                 overrides=dict(sl=0, code=2, desc=3, unit=4, rate=5), fixed=6)
    meta = dict(name="Andhra Pradesh Buildings SoR 2025-26 (Civil, Water Supply & Sanitary, Electrical)",
                authority="Andhra Pradesh R&B Department",
                department="Committee of Chief Engineers — Buildings SoR, Office of the Engineer-in-Chief (R&B) Buildings & RSW, Government of Andhra Pradesh",
                country="India", region="Andhra Pradesh", authority_level="state", schedule_type="SOR", code_system="AP-BSOR",
                year="2025", financial_year="2025-26", currency="INR", source="Official government document",
                source_ref="Government of Andhra Pradesh, Buildings SoR 2025-26, finalised by the Committee of Chief Engineers on "
                           "16.04.2025, communicated vide Procs.No.20938/SOR/DCE(B)/EE(B)/DEE(B)/AEE/2021 dt 06.05.2025. Copy obtained "
                           "from a non-government host (img1.wsimg.com) — verify against the R&B department copy.",
                notes="Building item, material (MAT-) and labour (LAB-) rates as printed. Labour, common material/work items, "
                      "conveyance and hire charges are in the separate Common SoR 2025-26, not included here.")
    write("andhra_buildings_sor_2025_26", rows, skipped, meta, pdf)


def tamilnadu_2025_26():
    pdf = os.path.join(SRC, "tamilnadu_2025_26", "tn_sor_2025_26_vol1.pdf")
    doc = pymupdf.open(pdf)
    rows, skipped = extract_grid(pdf, range(len(doc)), code_rx=r"^[A-Z]{1,3}-\d{3,5}[A-Za-z]?$")
    meta = dict(name="Tamil Nadu Schedule of Rates 2025-26 — Volume I (PWD, Highways, Water Resources)",
                authority="Tamil Nadu PWD",
                department="Public Works Department / Highways / Water Resources Department, Government of Tamil Nadu",
                country="India", region="Tamil Nadu", authority_level="state", schedule_type="SOR", code_system="TN-SOR",
                year="2025", financial_year="2025-26", effective_from="2025-07-22", currency="INR", source="Official government document",
                source_ref="Government of Tamil Nadu, Schedule of Rates 2025-2026 Vol I, w.e.f. 22.07.2025 — copy hosted at "
                           "http://tnebes.org/archive/2025/Jul/SCHEDULE%20OF%20RATES%202025-2026%20-%20VOL%20I.pdf (verify against the "
                           "department copy).",
                notes="Basic rates of labour, materials and work items as printed (Unique Codes). Rates are exclusive of GST as stated. "
                      "Area-specific extras (e.g. night work in Corporations +25% on labour) are listed in the notes of the SOR and "
                      "are not applied automatically.")
    write("tamilnadu_sor_2025_26_vol1", rows, skipped, meta, pdf)


def karnataka_2023_24():
    pdf = os.path.join(SRC, "karnataka", "ka_vol2_buildings_2023_24.pdf")
    doc = pymupdf.open(pdf)
    rows, skipped = extract_grid(pdf, range(len(doc)), code_rx=r"^\d{1,2}(\.\d{1,3}){1,3}[a-z]?$",
                                 overrides=dict(code=0, desc=1, unit=2, rate=3), fixed=4, hier=True, strip_margin=True)
    meta = dict(name="Karnataka PWD Schedule of Rates 2023-24 — Volume 2 (Buildings)", authority="Karnataka PWD",
                department="Public Works, Ports & Inland Water Transport Department, Government of Karnataka",
                country="India", region="Karnataka", authority_level="state", schedule_type="SR", code_system="KA-SR",
                year="2023", financial_year="2023-24", currency="INR", source="Official government document",
                source_ref="KPWD Common Schedule of Rates 2023-24, Volume 2 Buildings (Grand Finale, 15-11-2023) — "
                           "https://kpwd.karnataka.gov.in/storage/pdf-files/PWDSR-Vol-IIBuildings-GrandFinale-15-11-2023.pdf",
                notes="Latest full Buildings volume published by KPWD. KPWD revises material prices through quarterly Issue Rates "
                      "(2026-27 Q1 w.e.f. 04.04.2026 and Q2 w.e.f. 04.07.2026 are published on kpwd.karnataka.gov.in); those "
                      "files are scanned images and are NOT applied here, so item rates are as printed in the 2023-24 volume.")
    # Volume 1 (Common SR: earthwork, concrete, RCC, reinforcement ...) - codes prefixed V1- (both volumes number from 1)
    pdf1 = os.path.join(SRC, "karnataka", "ka_vol1_common_2023_24.pdf")
    d1 = pymupdf.open(pdf1)
    r1, s1 = extract_grid(pdf1, range(len(d1)), code_rx=r"^(\d{1,2}(\.\d{1,3}){1,3}[a-z]?(\.[a-z]{1,2})?|[a-z]{1,2}\.?|\(?[ivx]{1,4}\)?)$",
                          overrides=dict(code=0, desc=1, unit=2, rate=3), fixed=4, hier=True, letter_sub=True, strip_margin=True)
    for r in r1:
        r["code"] = "V1-" + r["code"].replace("..", ".").rstrip(".")
    rows = r1 + rows
    meta["name"] = "Karnataka PWD Schedule of Rates 2023-24 — Vol 1 (Common) + Vol 2 (Buildings)"
    meta["source_ref"] += " ; Vol 1 Common SR: https://kpwd.karnataka.gov.in/storage/pdf-files/Vol-1CommonSR-2023-24(GrandFinale)-15-11-2023.pdf"
    meta["notes"] += " Vol 1 item codes are prefixed 'V1-'."
    write("karnataka_sr_2023_24_vol2_buildings", rows, skipped + s1, meta, pdf)


def maharashtra_2022_23():
    pdf = os.path.join(SRC, "maharashtra", "mh_ssr_2022_23.pdf")
    doc = pymupdf.open(pdf)
    rows, skipped = extract_grid(pdf, range(len(doc)), code_rx=r"^(\d{1,3}\.\d{1,3}[A-Za-z]?|\d{1,3}\.\d{1,3}\.[a-z]{1,2}|[ivx]{1,4})$",
                                 overrides=dict(sl=0, code=2, desc=4, unit=6, rate=7), fixed=9, letter_sub=True)
    meta = dict(name="Maharashtra PWD State Schedule of Rates 2022-23", authority="Maharashtra PWD",
                department="Public Works Department, Government of Maharashtra", country="India", region="Maharashtra",
                authority_level="state", schedule_type="SSR", code_system="MH-SSR", year="2022", financial_year="2022-23",
                currency="INR", source="Official government document",
                source_ref="PWD Maharashtra, State Schedule of Rates 2022-2023 (latest edition on the PWD publications page, "
                           "re-published 2025) — https://cdnbbsr.s3waas.gov.in/s3ea80421fc06a2ed5c7adc1018e0026df/uploads/2025/07/202507031303590066.pdf",
                notes="Completed rates for 2022-23 EXCLUDING GST, as printed. The SSR also prints the labour component per item "
                      "(not stored here). No newer State SSR has been published by Maharashtra PWD as of this import.")
    write("maharashtra_ssr_2022_23", rows, skipped, meta, pdf)


SPECS.update(maharashtra_2022_23=maharashtra_2022_23, andhra_2025_26=andhra_2025_26, tamilnadu_2025_26=tamilnadu_2025_26, karnataka_2023_24=karnataka_2023_24)




def odisha_2022():
    """Odisha SOR 2022: Chapter 1 basic material rates are printed per DISTRICT (5 district columns per table);
    single-rate tables apply statewide. Chapter 25 item rates are statewide. One schedule per district."""
    pdf = os.path.join(SRC, "odisha_2022", "odisha_sor_2022.pdf")
    doc = pymupdf.open(pdf)
    dist_rates, state_rates, names = {}, {}, {}
    sec = 0
    last_sl = None
    for pno in range(7, 168):
        for t in doc[pno].find_tables().tables:
            rows = t.extract()
            if not rows:
                continue
            hdr = [re.sub(r"\s+", " ", c or "").strip() for c in rows[0]]
            if not hdr[0].lower().startswith("sl"):
                continue
            dcols = [(i, h) for i, h in enumerate(hdr[3:], 3) if h and not re.search(r"rate", h, re.I)]
            single = any(re.search(r"rate", h, re.I) for h in hdr[3:])
            parent = None
            for r in rows[1:]:
                r = [re.sub(r"\s+", " ", c or "").strip() for c in r]
                sl, name, unit = r[0], r[1], r[2] if len(r) > 2 else ""
                if re.fullmatch(r"\d{1,4}", sl):
                    parent = (sl, name)
                    key = sl
                elif re.fullmatch(r"[a-z]{1,2}|\(?[ivx]{1,4}\)?", sl) and parent:
                    key = parent[0] + sl.strip("()")
                    name = f"{parent[1]} — {name}"
                else:
                    continue
                if not unit or not name:
                    continue
                if single and not dcols:
                    if last_sl is not None and key.isdigit() and int(key) < 3 and int(last_sl or 0) > 10:
                        sec += 1  # numbering restarted: new sub-section of single-rate materials
                    code = f"OD-M{sec}-{key}"
                    v = r[3] if len(r) > 3 else ""
                    if RATE.match(v.replace(" ", "")):
                        state_rates[code] = (name, unit, v)
                    last_sl = key if key.isdigit() else last_sl
                else:
                    code = f"OD-MD-{key}"
                    for i, dname in dcols:
                        v = r[i] if i < len(r) else ""
                        if RATE.match(v.replace(" ", "")):
                            dist_rates.setdefault(dname, {})[code] = (name, unit, v)
    misc, mskip = extract_grid(pdf, range(224, len(doc)), code_rx=r".*", overrides=None)
    for m in misc:
        m["code"] = "OD-25-" + m["code"].lstrip("S")
    out = []
    for dname, items in sorted(dist_rates.items()):
        rows = []
        for code, (nm, unit, v) in {**{k: v for k, v in state_rates.items()}, **items}.items():
            u = unit_norm(unit)
            if not re.search(r"[A-Za-z]", u):
                continue
            rows.append(dict(code=code, description=nm, unit=u, rate=float(v.replace(",", "").replace(" ", "")), category=category(nm)))
        rows += [{k: m[k] for k in ("code", "description", "unit", "rate", "category")} for m in misc]
        slug_d = re.sub(r"[^a-z0-9]+", "_", dname.lower()).strip("_")
        meta = dict(name=f"Odisha Schedule of Rates 2022 — {dname} district", authority="Odisha Works Department",
                    department="Works Department, Government of Odisha", country="India", region="Odisha", district=dname,
                    authority_level="state", schedule_type="SOR", code_system="OD-SOR", year="2022", financial_year="2022-23",
                    effective_from="2023-04-20", currency="INR", source="Official government document",
                    source_ref="Government of Odisha, Works Department, Schedule of Rates 2022 (Office Memorandum dt 20.04.2023) — "
                               "https://works.odisha.gov.in/sites/default/files/2024-07/Schedule%20of%20Rates-%202022.pdf",
                    notes=f"Chapter 1 basic material rates for {dname} district (district column as printed) plus statewide "
                          "single-rate materials and Chapter 25 item rates. Most work-item rates in this SOR are to be derived "
                          "with the Odisha Analysis of Rates 2006 and are not printed, so they are not included.")
        write(f"odisha_sor_2022_{slug_d}", rows, [], meta, pdf)
        out.append(dname)
    print("districts:", len(out), out)


SPECS["odisha_2022"] = odisha_2022

def puducherry_2024_25():
    for reg, fn in (("Puducherry", "psr-2024-25-puducherry-region"), ("Karaikal", "psr-2024-25-karaikal-region"), ("Mahe", "psr-2024-25-mahe-region")):
        pdf = os.path.join(SRC, "puducherry_2024_25", fn + ".pdf")
        doc = pymupdf.open(pdf)
        rows, skipped = extract_grid(pdf, range(len(doc)), code_rx=r"^\d{3,5}[A-Za-z]?$",
                                     overrides=dict(sl=0, code=1, desc=2, unit=3, rate=4), fixed=5)
        meta = dict(name=f"Puducherry Schedule of Rates (PSR) 2024-25 — {reg} region", authority="Puducherry PWD",
                    department="Public Works Department, Government of Puducherry", country="India", region="Puducherry",
                    district=reg, authority_level="state", schedule_type="PSR", code_system="PY-PSR", year="2024",
                    financial_year="2024-25", effective_from="2024-08-14", currency="INR", source="Official government document",
                    source_ref=f"PWD Puducherry, PSR 2024-25 ({reg} region), w.e.f. 14 August 2024 — https://pwd.py.gov.in/sites/default/files/{fn}.pdf",
                    notes="Rates as printed in the regional PSR. Correction slips 1-3 published on pwd.py.gov.in are NOT yet applied.")
        write(f"puducherry_psr_2024_25_{reg.lower()}", rows, skipped, meta, pdf)


SPECS["puducherry_2024_25"] = puducherry_2024_25






def telangana_basic_2026_27():
    """Part-1 'Rates of Materials' and the common 'Labour Rates 2026-27' (three official zones:
    I municipal corporations, II municipalities, III rural & other areas)."""
    pdf = os.path.join(SRC, "telangana_2026_27", "ts_csr_2026_27.pdf")
    doc = pymupdf.open(pdf)
    rows, skipped, parent = [], [], None
    for pno in range(32, 37):
        if "Rates of Materials (Part-1)" not in doc[pno].get_text()[:200]:
            continue
        for t in doc[pno].find_tables().tables:
            for r in t.extract():
                r = [re.sub(r"\s+", " ", c or "").strip() for c in r]
                sl, desc = r[0], r[1] if len(r) > 1 else ""
                unit = r[2] if len(r) > 2 else ""
                nums = [c for c in r[3:] if RATE.match(c.replace(",", ""))]
                m = re.fullmatch(r"(\d{1,3})\s*(?:\(([a-z])\))?", sl)
                if m:
                    code = "P1-" + m.group(1) + (m.group(2) or "")
                    parent = (m.group(1), desc)
                elif re.fullmatch(r"\(([a-z])\)", sl) and parent:
                    code = "P1-" + parent[0] + sl.strip("()")
                    desc = f"{parent[1]} — {desc}"
                else:
                    continue
                if not unit or not nums:
                    continue
                rows.append(dict(code=code, description=desc, unit=unit_norm(unit), rate=float(nums[0].replace(",", "")),
                                 category=category(desc), page=pno + 1))
    sec = None
    for pno in range(44, 58):
        for t in doc[pno].find_tables().tables:
            for r in t.extract():
                r = [re.sub(r"\s+", " ", c or "").strip() for c in r]
                if re.fullmatch(r"(I|II|III|IV)\.", r[0]):
                    sec = r[0].rstrip(".")
                    continue
                if not (sec and re.fullmatch(r"\d{1,3}", r[0]) and len(r) >= 8):
                    continue
                zones = r[5:8]
                if not all(RATE.match(z.replace(",", "")) for z in zones):
                    continue
                for zi, z in enumerate(zones, 1):
                    rows.append(dict(code=f"LAB-{sec}-{r[0]}-Z{zi}", description=f"{r[2]} ({r[1]}) — {r[4]} — Zone-{'I' * zi if zi < 4 else zi}: "
                                     + ["Municipal corporations", "Municipalities", "Rural & other areas"][zi - 1],
                                     unit="day", rate=float(z.replace(",", "")), category="Labour", page=pno + 1))
    import csv as _csv
    base = os.path.join(OUT, "telangana_csr_2026_27_buildings.csv")
    old = list(_csv.DictReader(open(base, encoding="utf-8")))
    keep = [o for o in old if not o["code"].startswith(("P1-", "LAB-"))]
    meta = json.load(open(base.replace(".csv", ".meta.json"), encoding="utf-8"))
    meta["notes"] = meta["notes"].split(" Includes Part-1")[0] + (" Includes Part-1 basic material rates (codes P1-) and the common labour "
                    "rates 2026-27 per GO MS No.6 LAB-I dt 30.05.2026 in three zones (codes LAB-<category>-<sl>-Z1/Z2/Z3).")
    allrows = [dict(o, rate=float(o["rate"])) for o in keep] + rows
    write("telangana_csr_2026_27_buildings", allrows, meta.get("skipped_rows", []) + skipped, {k: v for k, v in meta.items() if k not in ("items", "skipped", "skipped_rows", "source_file", "source_sha256", "verification")}, pdf)
    print("basic rows", len(rows))


SPECS["telangana_basic_2026_27"] = telangana_basic_2026_27





def andhra_basic_2024_25():
    """AP Panchayat Raj Engg. 'Labour Rates and Conveyance 2024-25' (rates as per CSSR 2024-25 from 01.07.2024):
    official labour / material rates with their CFMS codes (LAB-xxxxx, MAT-xxxxx). Appended to the AP schedule."""
    pdf = os.path.join(SRC, "andhra_2025_26", "ap_pred_labour_conveyance_2024_25.pdf")
    doc = pymupdf.open(pdf)
    unit_of = lambda code, name: ("day" if code.startswith("LAB") else "1000 each" if "1000" in name else "cum" if re.search(r"(?i)sand|metal|gravel|rubbish|chips|earth", name)
                                  else "litre" if re.search(r"(?i)paint|primer|compound \(lr|oil|polish", name) else "kg" if re.search(r"(?i)wire|cement|kg", name) else "sqm" if re.search(r"(?i)tiles|jali|sheet|partition|board|pad", name) else "")
    rows = []
    for pno in (3, 4):
        t = doc[pno].get_text().replace("\n", " | ")
        for m in re.finditer(r"\|\s*([A-Za-z0-9][^|]{2,60}?)\s*\|\s*(?:\(\s*[^|]*\)\s*\|\s*)?((?:LAB|MAT)-\d{5})\s*(?:\|\s*&\s*\d+\s*)?\|\s*([\d,]+\.\d\d)", t):
            name, code, rate = m.group(1).strip(), m.group(2), float(m.group(3).replace(",", ""))
            u = unit_of(code, name)
            if not u or re.search(r"(?i)grills", name) or re.fullmatch(r"\d+", name):
                continue
            rows.append(dict(code=code, description=name + " (AP CSSR 2024-25 basic rate)", unit=u, rate=rate, category="Labour" if code.startswith("LAB") else category(name), page=pno + 1))
    seen, out = set(), []
    for r in rows:
        if r["code"] not in seen:
            seen.add(r["code"]); out.append(r)
    import csv as _csv
    base = os.path.join(OUT, "andhra_buildings_sor_2025_26.csv")
    old = [o for o in _csv.DictReader(open(base, encoding="utf-8")) if o["code"] not in seen]
    meta = json.load(open(base.replace(".csv", ".meta.json"), encoding="utf-8"))
    meta["notes"] = meta["notes"].split(" Basic labour/material")[0] + (
        " Basic labour/material rates (CFMS codes LAB-/MAT-) added from AP Panchayat Raj Engineering 'Labour Rates and Conveyance "
        "2024-25' (CSSR 2024-25, from 01.07.2024), https://pred.ap.gov.in/PRED/SSR.aspx — one year older than the Buildings SoR. "
        "Cement and reinforcement steel are NOT printed by AP (monthly rate fixed by the Sub-Committee): enter them on the estimate.")
    write("andhra_buildings_sor_2025_26", [dict(o, rate=float(o["rate"])) for o in old] + out, meta.get("skipped_rows", []),
          {k: v for k, v in meta.items() if k not in ("items", "skipped", "skipped_rows", "source_file", "source_sha256", "verification")}, pdf)
    for r in out:
        print(r["code"], r["unit"], r["rate"], r["description"][:50])


SPECS["andhra_basic_2024_25"] = andhra_basic_2024_25


if __name__ == "__main__":
    for n in sys.argv[1:] or SPECS:
        SPECS[n]()
