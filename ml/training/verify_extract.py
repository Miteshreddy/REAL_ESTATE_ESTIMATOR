"""Audit an extracted schedule against its source PDF: every item's code and rate must be printed on its page
(or the following page, when the row continues). Usage: python verify_extract.py <name> <pdf>"""
import csv
import json
import os
import re
import sys

import pymupdf

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "sor", "states")


def fmt(v):
    v = float(v)
    s = [f"{v:.2f}", f"{v:,.2f}", f"{v:g}", f"{v:,.0f}" if v == int(v) else None, f"{int(v)}" if v == int(v) else None]
    w, d = f"{v:.2f}".split(".")
    head, tail = w[:-3], w[-3:]
    grp = []
    while len(head) > 2:
        grp.insert(0, head[-2:])
        head = head[:-2]
    if head:
        grp.insert(0, head)
    ind = (",".join(grp) + "," + tail) if grp else tail
    s += [ind + "." + d, ind]
    return {x for x in s if x}


def main(name, pdf):
    doc = pymupdf.open(pdf)
    meta = json.load(open(os.path.join(OUT, name + ".meta.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(OUT, name + ".csv"), encoding="utf-8")))
    page_of = {}
    import_rows = []
    # page numbers are not in the CSV: re-locate by code
    text = [re.sub(r"\s+", "", p.get_text()) for p in doc]
    ok, bad = 0, []
    for r in rows:
        code = r["code"].replace(" ", "")
        pages = [i for i, t in enumerate(text) if code in t]
        if not pages and re.search(r"\.[a-z]{1,2}$|\.[ivx]{1,4}$", code):  # sub-item: printed as 'a' under its parent code
            parent = code.rsplit(".", 1)[0]
            pages = [i for i, t in enumerate(text) if parent in t]
        found = False
        for i in pages:
            win = "".join(text[i:i + 3])  # long items continue over the next pages
            if any(f in win for f in fmt(r["rate"])):
                found = True
                break
        if found:
            ok += 1
        else:
            bad.append((r["code"], r["rate"], pages[:3]))
    meta["verification"] = dict(checked=len(rows), code_and_rate_found_in_pdf=ok, pct=round(ok / max(1, len(rows)) * 100, 2), not_found=bad[:100])
    json.dump(meta, open(os.path.join(OUT, name + ".meta.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(name, f"{ok}/{len(rows)} verified ({meta['verification']['pct']}%)", bad[:5])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
