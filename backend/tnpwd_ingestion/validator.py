"""Checks an extracted TN schedule before it may be activated. Errors block activation; warnings are shown."""
from __future__ import annotations

import re
from collections import Counter

CODE = re.compile(r"^[A-Z]{1,3}-\d{3,5}[A-Za-z]?$")


def validate_rates(items: list[dict], previous: list[dict] | None = None) -> dict:
    errors, warnings = [], []
    if len(items) < 500:
        errors.append(f"only {len(items)} items extracted — a TN SOR volume has thousands; extraction probably failed")
    dup = [c for c, n in Counter(i["code"] for i in items).items() if n > 1]
    if dup:
        errors.append(f"duplicate codes: {dup[:10]}")
    bad = [i["code"] for i in items if not CODE.match(i["code"])]
    if bad:
        errors.append(f"malformed codes: {bad[:10]}")
    nonpos = [i["code"] for i in items if not (isinstance(i.get("rate"), (int, float)) and i["rate"] > 0)]
    if nonpos:
        errors.append(f"non-positive / missing rates: {nonpos[:10]}")
    nounit = [i["code"] for i in items if not i.get("unit")]
    if nounit:
        errors.append(f"missing units: {nounit[:10]}")
    nopage = [i["code"] for i in items if not i.get("page")]
    if nopage:
        warnings.append(f"{len(nopage)} items without a source page")
    merged = [i["code"] for i in items if re.search(r"\b[A-Z]\.\s+[A-Z]{4,}", i.get("description", ""))]
    if merged:
        warnings.append(f"{len(merged)} descriptions contain a section heading (merged cell) e.g. {merged[:5]} — review")
    if previous:
        prev = {p["code"]: p for p in previous}
        jumps = [i["code"] for i in items if i["code"] in prev and prev[i["code"]]["rate"] and
                 not 0.5 <= i["rate"] / prev[i["code"]]["rate"] <= 2.0]
        if jumps:
            warnings.append(f"{len(jumps)} rates changed by more than ×2 vs the previous edition, e.g. {jumps[:8]} — check extraction")
    return dict(ok=not errors, errors=errors, warnings=warnings, items=len(items))
