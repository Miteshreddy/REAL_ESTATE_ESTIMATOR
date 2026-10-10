"""Extract CPWD DSR 2023 (English) into a clean CSV: code, description, unit, rate, category."""
import csv
import re
import sys

import pymupdf

SRC = r"G:\velo\real-estate\sor\dsr_2023_english_nsrcivil.pdf"
OUT = r"G:\velo\real-estate\sor\cpwd_dsr_2023_civil.csv"

CHAPTER = {
    1: "Carriage", 2: "Earthwork", 3: "Mortars", 4: "Concrete Works", 5: "RCC Works", 6: "Masonry", 7: "Stone Work",
    8: "Marble & Granite", 9: "Doors & Windows", 10: "Steel Work", 11: "Flooring", 12: "Roofing", 13: "Finishing",
    14: "Repairs", 15: "Dismantling", 16: "Roads", 17: "Plumbing & Sanitary", 18: "Plumbing & Sanitary",
    19: "Plumbing & Sanitary", 20: "Piling", 21: "Doors & Windows", 22: "Waterproofing", 23: "Plumbing & Sanitary",
    24: "Miscellaneous", 25: "Miscellaneous", 26: "Miscellaneous",
}
CODE = re.compile(r"^\d{1,2}\.\d{1,3}(?:\.\d{1,3})?(?:\s*\([a-z]\))?$")
UNITS = {"cum", "sqm", "metre", "m", "kg", "each", "litre", "quintal", "tonne", "point", "set", "pair", "rm", "sq.m", "cu.m", "nos", "no", "job", "km", "100 kg"}


def category(code, desc):
    ch = int(code.split(".")[0])
    if ch == 5:
        sub = int(code.split(".")[1].split()[0])
        if sub == 9:
            return "Formwork"
        if sub == 22 or "reinforcement" in desc.lower() and "steel" in desc.lower():
            return "Reinforcement"
    if ch == 13:
        d = desc.lower()
        if any(w in d for w in ("paint", "emulsion", "distemper", "putty", "primer", "polish", "white wash", "colour wash")):
            return "Painting"
        return "Plastering"
    return CHAPTER.get(ch, "Miscellaneous")


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def num(s):
    s = clean(s).replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def main():
    doc = pymupdf.open(SRC)
    items, stack = {}, []  # stack of (code, desc) for the current item hierarchy
    for page in doc:
        for t in page.find_tables().tables:
            for row in t.extract():
                cells = [clean(c) if c is not None else "" for c in row]
                ci = next((i for i, c in enumerate(cells) if CODE.match(c)), None)
                if ci is None:
                    # continuation text of the last header without a rate
                    txt = max(cells, key=len) if cells else ""
                    if stack and len(txt) > 25 and stack[-1][0] not in items and txt not in stack[-1][1]:
                        stack[-1] = (stack[-1][0], (stack[-1][1] + " " + txt).strip())
                    continue
                code = cells[ci].split()[0]
                rest = [c for c in cells[ci + 1:] if c]
                rate = num(rest[-1]) if rest else None
                unit = rest[-2].lower() if len(rest) >= 2 and rate is not None else ""
                desc_parts = rest[:-2] if rate is not None and len(rest) >= 2 else rest
                desc = " ".join(desc_parts)
                # keep only ancestors of this code
                stack = [(c, d) for c, d in stack if code.startswith(c + ".")]
                stack.append((code, desc))
                if rate is not None and unit and not unit.replace(".", "").isdigit():
                    full = " — ".join(d for _, d in stack if d)
                    items[code] = dict(code=code, description=full, unit=unit, rate=rate)
    norm = {"sq.m": "sqm", "cu.m": "cum", "m": "metre", "no": "each", "nos": "each", "rm": "metre"}
    rows = []
    for it in items.values():
        u = norm.get(it["unit"], it["unit"])
        desc = it["description"][:1200]
        rows.append(dict(code=it["code"], description=desc, unit=u, rate=it["rate"], category=category(it["code"], desc)))
    rows.sort(key=lambda r: [int(x) if x.isdigit() else 0 for x in re.split(r"[.\s()]", r["code"]) if x])
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "description", "unit", "rate", "category"])
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(len(rows), "items written to", OUT)
    print(Counter(r["category"] for r in rows).most_common())
    print(Counter(r["unit"] for r in rows).most_common(12))


if __name__ == "__main__":
    main()
