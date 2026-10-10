"""SOR amendments (often scanned): OCR the table, read  code | name | unit | old rate | revised rate.

Self-check: the 'old rate' column printed in the amendment must equal the rate of the same code in the base SOR.
Rows that fail the check (or whose numbers OCR could not read cleanly) are rejected, never guessed.
"""
from __future__ import annotations

import re

import pymupdf

from .pdf_text import ocr_page

CODE = re.compile(r"^[A-Z]{1,2}\s*-\s*[\dOo]{3,5}$")  # OCR may read 0 as O
NUM = re.compile(r"^\d{1,6}(\.\d{1,2})?$")


def _merge_split_codes(words):
    """OCR sometimes splits 'M-0209' into 'M-0' + '0209' (overlapping boxes): join a bare prefix with the 3-5 digit
    token that starts inside / right after it on the same line."""
    out, skip = [], set()
    for i, w in enumerate(words):
        if i in skip:
            continue
        if re.fullmatch(r"[A-Z]{1,2}\s*-\s*[\dO]?", w[4]):
            nxt = next((j for j, v in enumerate(words) if j != i and abs((v[1] + v[3]) / 2 - (w[1] + w[3]) / 2) < 5
                        and w[2] - 6 <= v[0] <= w[2] + 6 and re.fullmatch(r"[\dO]{3,5}", v[4])), None)
            if nxt is not None:
                v = words[nxt]
                skip.add(nxt)
                out.append((w[0], min(w[1], v[1]), v[2], max(w[3], v[3]), w[4].split("-")[0].strip() + "-" + v[4], min(w[5], v[5])))
                continue
        out.append(w)
    return out


def parse_amendment(path: str, base_rates: dict[str, float]) -> dict:
    doc = pymupdf.open(path)
    text_all, rows, rejected = [], [], []
    effective = None
    for p in doc:
        words = [(x0, y0, x1, y1, t.strip(), c) for x0, y0, x1, y1, t, c in (ocr_page(p, 300) if len(p.get_text().strip()) < 40 else
                 [(w[0], w[1], w[2], w[3], w[4], 1.0) for w in p.get_text("words")])]
        words = _merge_split_codes(words)
        text_all.append(" ".join(w[4] for w in words))
        m = re.search(r"with\s*effect\s*from\s*(\d{2})\.(\d{2})\.(\d{4})", text_all[-1], re.I)
        codes = [w for w in words if CODE.match(w[4])]
        for cw in codes:
            yc = (cw[1] + cw[3]) / 2
            same = sorted([w for w in words if abs((w[1] + w[3]) / 2 - yc) < 9 and w[0] > cw[2]], key=lambda w: w[0])
            nums = [float(w[4]) for w in same if NUM.match(w[4].replace(",", ""))]
            unit = next((w[4] for w in same if re.match(r"^(each|sqm\.?|sq\.m\.?|cum|kg|nos?\.?|metre|m)$", w[4], re.I)), None)
            pre, _, num = re.sub(r"\s", "", cw[4]).partition("-")
            code = pre + "-" + num.replace("O", "0").replace("o", "0")
            name = " ".join(w[4] for w in same if not NUM.match(w[4].replace(",", "")) and w[4] != unit)[:150]
            if len(nums) < 2:
                rejected.append(dict(code=code, page=p.number + 1, why="old / revised rate not both readable"))
                continue
            old, new = nums[-2], nums[-1]
            base = base_rates.get(code)
            if base is None:
                rejected.append(dict(code=code, page=p.number + 1, why="code not in the base SOR"))
            elif abs(base - old) > 0.005:
                rejected.append(dict(code=code, page=p.number + 1, old_ocr=old, base=base, why="printed old rate ≠ base SOR rate (OCR or edition mismatch)"))
            else:
                rows.append(dict(code=code, name=name, unit=unit, old_rate=old, rate=new, page=p.number + 1, check="old rate matches base SOR"))
    full = " ".join(text_all)
    m = re.findall(r"with\s*effect\s*from\s*(\d{2})\.(\d{2})\.(\d{4})", full, re.I)
    dates = sorted({f"{y}-{mo}-{d}" for d, mo, y in m})
    proc = re.search(r"Proceeding\s*No\.?\s*([A-Z0-9/ .-]+?),?\s*dated[:\s]*(\d{2}\.\d{2}\.\d{4})", full, re.I)
    # 'immediate effect' → the proceeding date; otherwise the latest w.e.f. date printed
    effective = (f"{proc.group(2)[6:]}-{proc.group(2)[3:5]}-{proc.group(2)[:2]}" if proc and re.search(r"immediate\s*effect", full, re.I)
                 else dates[-1] if dates else None)
    return dict(rows=rows, rejected=rejected, effective_from=effective,
                reference=(f"Proceeding No. {proc.group(1).strip()} dated {proc.group(2)}" if proc else None))
