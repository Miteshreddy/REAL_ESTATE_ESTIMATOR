"""Client-facing branding: the product is shown as "PWD Estimator".

The engine stays Tamil Nadu-only (tn_scope.py); only text shown to clients (UI strings, HTML / PDF / XLSX reports) drops
the state name and internal source labels. frontend/app.js mirrors these rules in `brand()`.
"""
from __future__ import annotations

import re

PRODUCT = "PWD Estimator"
RULES = [
    (re.compile(r",?\s*Government of Tamil Nadu", re.I), ""),
    (re.compile(r",\s*Tamil Nadu\b", re.I), ""),
    (re.compile(r"\bTamil Nadu,\s*", re.I), ""),
    (re.compile(r"\s*·\s*Tamil Nadu\b", re.I), ""),
    (re.compile(r"\bTamil Nadu\s+", re.I), ""),
    (re.compile(r"\s*\(?\bTamil Nadu\b\)?", re.I), ""),
    (re.compile(r"\bTN[ -](?=PWD|SOR|SD\b|Standard)"), ""),
]


def text(s: str) -> str:
    for rx, rep in RULES:
        s = rx.sub(rep, s)
    return s


def debrand(obj):
    """Deep copy of a project / estimate with client-facing strings de-branded."""
    if isinstance(obj, str):
        return text(obj)
    if isinstance(obj, dict):
        return {k: debrand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [debrand(v) for v in obj]
    return obj
