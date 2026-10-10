"""Tamil Nadu PWD pricing of take-off items.

    take-off item ──(reviewed map data/tnpwd/maps/takeoff_tn.json)──► TN SOR finished-work rate
                                                                   └─► TN Standard Data item × TN SOR basic rates
                                                                   └─► suggestion (not priced until the engineer confirms)
                                                                   └─► NEEDS RATE / NEEDS RATE ANALYSIS (listed, never ₹0)
Only validated, activated data is used: the active TN schedule's rate_items and the Standard Data stored by the
ingestion (tn_sd_items). Every priced line carries the document, edition, page and SHA-256 it came from.
"""
from __future__ import annotations

import json
import os

from tnpwd_ingestion.rate_analysis import Resolver, price_variant

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(ROOT, "data", "tnpwd", "maps", "takeoff_tn.json")
_cache = {}


def item_map():
    m = json.load(open(MAP_PATH, encoding="utf-8"))
    return {k: v for k, v in m.items() if not k.startswith("_")}


def standard_data(con):
    """Latest stored Standard Data Book (by effective date) → (sha, doc row, {data_no: item})."""
    try:
        d = con.execute("SELECT * FROM tn_documents WHERE doc_type='standard_data' AND extracted_at IS NOT NULL "
                        "ORDER BY effective_from DESC LIMIT 1").fetchone()
    except Exception:  # noqa: BLE001 — ingestion tables absent (fresh test database)
        return None, None, {}
    if not d:
        return None, None, {}
    sha = d["sha256"]
    if _cache.get("sd_sha") != sha:
        items = {}
        for r in con.execute("SELECT data_no, page, description, components FROM tn_sd_items WHERE sha256=? ORDER BY page", (sha,)):
            items.setdefault(r["data_no"], dict(data_no=r["data_no"], page=r["page"], description=r["description"],
                                                variants=json.loads(r["components"])))
        _cache.update(sd_sha=sha, sd_items=items, sd_doc=dict(d))
    return sha, _cache["sd_doc"], _cache["sd_items"]


def unit_key(u):
    u = (u or "").lower().strip()
    return {"m": "metre", "rm": "metre", "nos": "each", "no": "each", "number": "each"}.get(u, u)


def price_items(con, items: list[dict], by_code: dict, schedule: dict | None):
    """Set derived / sor_code / status on each item in place (TN schedule)."""
    sha, sd_doc, sd = standard_data(con)
    res = Resolver(list(by_code.values()), list(sd.values())) if by_code else None
    m = item_map()
    for it in items:
        for f in ("sor_factor", "included", "derived", "suggested"):
            it.pop(f, None)
        it.update(candidates=[], sor_code=None, map_score=0, nlp_agrees_with_rules=False)
        e = m.get(it["key"]) if not it.get("custom") else None
        if not e:
            it.update(map_method="none", status="unmapped", rate_gap="NEEDS RATE",
                      map_check="no Tamil Nadu PWD item mapped for this take-off line — select a TN SOR item or enter a rate")
            continue
        note = e.get("note", "")
        if e.get("sor"):
            r = by_code.get(e["sor"])
            if r and unit_key(r["unit"]) == unit_key(it["unit"]) and _in_band(r["rate"], e):
                it.update(candidates=[dict(code=r["code"], description=r["description"][:160], unit=r["unit"], rate=r["rate"], score=1.0)],
                          sor_code=r["code"], map_score=1.0, map_method="table", status="auto", map_check=note)
            else:
                it.update(map_method="none", status="unmapped", rate_gap="NEEDS RATE",
                          map_check=f"mapped TN SOR item {e['sor']} unavailable, unit-incompatible or outside the plausibility band — {note}")
            continue
        if e.get("sd"):
            src = sd.get(e["sd"])
            if not res or not src or e.get("variant", 0) >= len(src["variants"]):
                it.update(map_method="none", status="unmapped", rate_gap="NEEDS RATE ANALYSIS",
                          map_check=f"TN Standard Data {e['sd']} not available in the ingested book — {note}")
                continue
            v = src["variants"][e.get("variant", 0)]
            p = price_variant(v, res, context=src["description"], bind=e.get("bind"), ignore=e.get("ignore"), sd_by_no=sd)
            rate = round(p["rate"] * float(e.get("factor", 1.0)), 2)
            if not p["complete"]:
                it.update(map_method="none", status="unmapped", rate_gap="NEEDS RATE ANALYSIS",
                          map_check=f"TN Standard Data {e['sd']} could not be fully priced from TN SOR basic rates: "
                                    + "; ".join(f"{u['name'][:50]} ({u['why'][:40]})" for u in p["unresolved"][:4]) + f" — {note}")
                continue
            if not _in_band(rate, e):
                it.update(map_method="none", status="unmapped", rate_gap="NEEDS RATE ANALYSIS",
                          map_check=f"analysed rate ₹{rate:,.2f}/{it['unit']} is outside the plausibility band {e.get('band')} — rejected; {note}")
                continue
            it.update(map_method="analysis", status="auto", map_score=1.0, map_check=note,
                      derived=dict(ok=True, rate=rate, unit=it["unit"], description=f"TN Standard Data {e['sd']}: {src['description'][:200]}",
                                   basis=(f"TN PWD Standard Data Book item {e['sd']} (page {src['page']}) × TN SOR "
                                          f"{(schedule or {}).get('financial_year') or ''} basic rates"
                                          + (f" × {e['factor']:g} (unit conversion)" if e.get('factor') else "") + "; " + note),
                                   components=p["components"], additions=p["additions"], excluded=p["excluded"], per_qty=p["per_qty"],
                                   source=dict(document=(sd_doc or {}).get("title"), sha256=sha, page=src["page"], data_no=e["sd"],
                                               variant=e.get("variant", 0), url=(sd_doc or {}).get("url"),
                                               effective_from=(sd_doc or {}).get("effective_from"),
                                               verification=(sd_doc or {}).get("verification_status"))))
            continue
        # suggestion only / needs
        cands = [dict(code=c, description=by_code[c]["description"][:160], unit=by_code[c]["unit"], rate=by_code[c]["rate"], score=0.5)
                 for c in e.get("suggest", []) if c in by_code]
        it.update(candidates=cands, map_method="none", status="unmapped", rate_gap=e.get("needs", "NEEDS RATE"),
                  suggested=[c["code"] for c in cands], map_check=f"{e.get('needs', 'NEEDS RATE')} — {note}")


EST_PATH = os.path.join(ROOT, "data", "tnpwd", "maps", "estimated_rates.json")


def estimated_rates() -> dict:
    if not os.path.exists(EST_PATH):
        return {}
    return {k: v for k, v in json.load(open(EST_PATH, encoding="utf-8")).items() if not k.startswith("_")}


def basis_label(b: str) -> str:
    return ("reference schedule average" if b.startswith("CPWD") else "market average" if b.startswith("Market")
            else "engineering estimate") + " — editable"


def apply_estimates(items: list[dict]) -> int:
    """Lines with no PWD rate get the average rate from estimated_rates.json (unit must match), marked 'estimated'
    so the UI / report show it as an editable estimate. Returns how many lines were filled."""
    est, n = estimated_rates(), 0
    for it in items:
        e = est.get(it.get("key"))
        if it.get("status") != "unmapped" or not e or unit_key(e["unit"]) != unit_key(it.get("unit")):
            continue
        it.update(map_method="estimated", status="estimated", estimated_rate=True, original_gap=it.get("rate_gap"),
                  derived=dict(ok=True, rate=float(e["rate"]), unit=it["unit"], description="Estimated average rate",
                               basis=basis_label(e["basis"]), reference=e["basis"],  # reference: internal, not shown to clients
                               source=dict(document="estimated_rates.json", verification="estimated")))
        n += 1
    return n


def _in_band(rate, e):
    b = e.get("band")
    return b is None or (b[0] <= float(rate) <= b[1])
