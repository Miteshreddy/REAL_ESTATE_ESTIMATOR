"""Classify a TN PWD document and read its edition / effective date from its title and first pages."""
from __future__ import annotations

import re

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _date(text):
    t = text.lower()
    m = re.search(r"w\.?\s*e\.?\s*f\.?\s*:?\s*(\d{1,2})[\s./-]*([a-z]{3})[a-z]*[\s./-]*(\d{4})", t)
    if m and m.group(2) in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"w\.?\s*e\.?\s*f\.?\s*:?\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})", t)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def classify_title(text: str) -> dict:
    t = text.lower()
    if re.search(r"standard\s*data", t):
        kind = "standard_data"
    elif re.search(r"amend|ammend|revis|corrigend|addend", t) and re.search(r"sor|schedule\s*of\s*rates|rate", t):
        kind = "sor_amendment"
    elif re.search(r"\bsor\b|schedule\s*of\s*rates", t):
        kind = "sor"
    else:
        kind = "other"
    fy = re.search(r"(20\d\d)\s*[-–/]\s*(20)?(\d\d)\b", text)
    financial_year = f"{fy.group(1)}-{fy.group(3)}" if fy else None
    vol = re.search(r"vol(?:ume)?\.?\s*[-–:]?\s*([ivx]+|\d+)\b", t)
    return dict(doc_type=kind, financial_year=financial_year, year=fy.group(1) if fy else None,
                edition=(f"SOR {financial_year}" if kind in ("sor", "sor_amendment") and financial_year else None)
                if kind != "standard_data" else "Standard Data Book",
                volume=vol.group(1).upper() if vol else None, effective_from=_date(text),
                approved="approved" in t)


def classify_document(title: str, first_pages_text: str) -> dict:
    c = classify_title(title)
    body = classify_title(first_pages_text[:6000])
    for k in ("financial_year", "year", "effective_from", "volume"):
        c[k] = c.get(k) or body.get(k)
    if c["doc_type"] == "other":
        c["doc_type"] = body["doc_type"]
    return c
