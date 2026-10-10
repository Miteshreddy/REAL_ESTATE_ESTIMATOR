"""PWD item-mapping review (Task 11).

Automatic suggestions (reviewed item map, analysis, candidates) are kept SEPARATE from engineer-approved mappings.
An approval records: take-off key + unit, selected TN code (SOR code or 'SD:<data no>'), reviewer, timestamp, schedule revision,
rate-analysis status. Unit compatibility is mandatory: a mapping whose unit differs from the take-off unit cannot be approved
unless the reviewer gives an explicit conversion justification (e.g. per 100 cft → per cum).
Accuracy of the automatic suggestions = agreement with APPROVED reviews (top-1 / top-3); with no reviews: NOT VALIDATED.
"""
from __future__ import annotations

import json
from datetime import datetime

from tnpwd_ingestion.rate_analysis import unit_of


def ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS mapping_reviews(key TEXT, unit TEXT, selected_code TEXT, decision TEXT, reviewer TEXT,
                   at TEXT, schedule_id TEXT, rate_analysis_status TEXT, unit_justification TEXT, candidates TEXT, note TEXT,
                   PRIMARY KEY(key, unit, reviewer, schedule_id))""")


def units_compatible(a, b) -> bool:
    ua, ub = unit_of(a), unit_of(b)
    if ua is None or ub is None:
        return (a or "").strip().lower() == (b or "").strip().lower()
    return ua[0] == ub[0]


def suggestions(items: list[dict]) -> list[dict]:
    """One row per take-off line: the automatic suggestion + candidates + unit check."""
    out = []
    for it in items:
        cands = [dict(code=c["code"], unit=c.get("unit"), description=c.get("description", "")[:120]) for c in (it.get("candidates") or [])]
        if it.get("derived"):
            src = (it["derived"].get("source") or {})
            cands = [dict(code=f"SD:{src.get('data_no')}", unit=it["unit"], description=it["derived"].get("description", "")[:120])] + cands
        top = it.get("sor_code") or (cands[0]["code"] if cands else None)
        mism = [c["code"] for c in cands if c.get("unit") and not units_compatible(c["unit"], it["unit"])]
        out.append(dict(key=it["key"], description=it["description"][:120], unit=it["unit"], category=it["category"], suggested=top,
                        candidates=cands[:5], unit_mismatch_candidates=mism, method=it.get("map_method"),
                        rate_analysis=("required" if it.get("rate_gap") == "NEEDS RATE ANALYSIS" else "analysed" if it.get("derived") else "direct item"
                                       if it.get("sor_code") else "none"),
                        needs_review=bool(not top or mism or it.get("status") in ("review", "unmapped") or it.get("rate_gap"))))
    return out


def approve(con, key, unit, code, reviewer, decision, schedule_id, code_unit=None, unit_justification="", note="", candidates=None):
    ensure(con)
    if not reviewer:
        raise ValueError("a named reviewer is required")
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be approve or reject")
    if decision == "approve" and code_unit and not units_compatible(code_unit, unit) and not unit_justification.strip():
        raise ValueError(f"unit mismatch: take-off unit {unit} vs item unit {code_unit} — give an explicit conversion justification")
    con.execute("INSERT OR REPLACE INTO mapping_reviews VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (key, unit, code, decision, reviewer, datetime.now().isoformat(timespec="seconds"), schedule_id,
                 "analysis" if str(code).startswith("SD:") else "direct", unit_justification, json.dumps(candidates or []), note))


def approved(con, schedule_id) -> dict:
    ensure(con)
    out = {}
    for r in con.execute("SELECT * FROM mapping_reviews WHERE decision='approve' AND schedule_id=? ORDER BY at", (schedule_id,)):
        out[(r["key"], r["unit"])] = dict(r)
    return out


def evaluate(con, schedule_id, sugg: list[dict]) -> dict:
    ref = approved(con, schedule_id)
    rows = [s for s in sugg if (s["key"], s["unit"]) in ref]
    if not rows:
        return dict(status="NOT VALIDATED", reviewed_items=0, reason="no engineer-approved mappings for this schedule yet")
    t1 = sum(1 for s in rows if s["suggested"] == ref[(s["key"], s["unit"])]["selected_code"])
    t3 = sum(1 for s in rows if ref[(s["key"], s["unit"])]["selected_code"] in [s["suggested"]] + [c["code"] for c in s["candidates"][:3]])
    by_cat = {}
    for s in rows:
        c = by_cat.setdefault(s["category"], [0, 0])
        c[0] += s["suggested"] == ref[(s["key"], s["unit"])]["selected_code"]
        c[1] += 1
    return dict(status="MEASURED" if len(rows) >= 30 else "INSUFFICIENT DATA", reviewed_items=len(rows),
                top1_pct=round(100 * t1 / len(rows), 1), top3_pct=round(100 * t3 / len(rows), 1),
                precision_by_category={k: round(100 * a / b, 1) for k, (a, b) in by_cat.items()},
                coverage_pct=round(100 * sum(1 for s in sugg if s["suggested"]) / max(1, len(sugg)), 1),
                unit_mismatch_flagged=sum(1 for s in sugg if s["unit_mismatch_candidates"]))
