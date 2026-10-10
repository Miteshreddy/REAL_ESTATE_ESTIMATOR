"""TN SOR rate tables → items (code, description, unit, rate, category, page). Reuses the audited grid extractor
of ml/training/import_state_sor.py (multi-line cells, wrapped codes, ambiguous / merged rate cells rejected)."""
from __future__ import annotations

import importlib.util
import os
import re

import pymupdf

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_mod = None


def _importer():
    global _mod
    if _mod is None:
        spec = importlib.util.spec_from_file_location("import_state_sor", os.path.join(_ROOT, "ml", "training", "import_state_sor.py"))
        _mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)
    return _mod


TN_CODE = r"^[A-Z]{1,3}-\d{3,5}[A-Za-z]?$"  # TN 'Unique Codes': L-0001 labour, M-0001 material, W-0001 work, …


HEADING = re.compile(r"(?<=\S)\s+(?:[A-Z]|[IVX]{1,4})\.\s+[A-Z][A-Za-z]")  # ' … Steel A. BRICKS AND TILE …', ' … Mixing N. Metal and Iron Works'


def strip_heading(desc: str) -> tuple[str, bool]:
    """A section heading printed in the row below an item ('Steel A. BRICKS AND TILE PRODUCTS Second Class …') is merged
    into that item's cell by the table extractor; cut it off at the capitalised heading."""
    m = HEADING.search(desc)
    if m and m.start() >= 4:
        return desc[:m.start()].strip(), True
    return desc, False


def parse_sor(path: str) -> tuple[list[dict], list[dict]]:
    m = _importer()
    rows, skipped = m.extract_grid(path, range(len(pymupdf.open(path))), code_rx=TN_CODE)
    out = []
    for r in rows:
        d, cut = strip_heading(r["description"])
        out.append(dict(code=r["code"], description=d, unit=r["unit"], rate=float(r["rate"]), category=r["category"], page=r.get("page"),
                        heading_removed=cut))
    return out, skipped


def unit_norm(u):
    return _importer().unit_norm(u)
