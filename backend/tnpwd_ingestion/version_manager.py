"""Editions, amendments, comparison and activation. History is never overwritten:
each document's extraction stays in tn_rate_items keyed by its SHA-256; a production schedule = base SOR (+ amendments)
materialised into rate_schedules / rate_items under its own id, and older schedules are set 'inactive', not deleted."""
from __future__ import annotations

import difflib
import json

from .store import log, now

TN_SCHEDULE_PREFIX = "tn-pwd-sor-"


def diff(old: list[dict], new: list[dict]) -> dict:
    o, n = {i["code"]: i for i in old}, {i["code"]: i for i in new}
    added = sorted(set(n) - set(o))
    removed = sorted(set(o) - set(n))
    changed, renamed = [], []
    for c in sorted(set(o) & set(n)):
        if abs(float(o[c]["rate"]) - float(n[c]["rate"])) > 0.005:
            changed.append(dict(code=c, old=o[c]["rate"], new=n[c]["rate"], pct=round((n[c]["rate"] / o[c]["rate"] - 1) * 100, 2) if o[c]["rate"] else None))
        if difflib.SequenceMatcher(None, o[c]["description"].lower(), n[c]["description"].lower()).ratio() < 0.8:
            renamed.append(dict(code=c, old=o[c]["description"][:80], new=n[c]["description"][:80]))
    return dict(added=added, removed=removed, rate_changed=changed, renamed=renamed,
                summary=dict(added=len(added), removed=len(removed), rate_changed=len(changed), renamed=len(renamed)))


def apply_amendment(base: list[dict], rows: list[dict]) -> tuple[list[dict], list[dict]]:
    by = {i["code"]: dict(i) for i in base}
    applied = []
    for r in rows:
        if r["code"] in by:
            it = by[r["code"]]
            applied.append(dict(code=r["code"], old=it["rate"], new=r["rate"], page=r.get("page")))
            it["rate"] = r["rate"]
            it["amended"] = True
    return list(by.values()), applied


def schedule_id(edition_fy: str, amendment_date: str | None) -> str:
    return TN_SCHEDULE_PREFIX + edition_fy + (("-amd-" + amendment_date) if amendment_date else "")


def activate(con, sid: str, meta: dict, items: list[dict], provenance: dict):
    """Materialise a TN schedule for production and make it the only active TN schedule (older ones → inactive)."""
    import rates  # app module (same process)
    exists = con.execute("SELECT 1 FROM rate_schedules WHERE id=?", (sid,)).fetchone()
    if not exists:
        rates._insert_schedule(con, dict(meta, id=sid, status="draft"), imported_by="tnpwd refresh")
    con.execute("DELETE FROM rate_items WHERE schedule_id=?", (sid,))
    t = now()
    con.executemany("INSERT INTO rate_items(schedule_id, code, description, unit, rate, category, source, updated, analysis) VALUES(?,?,?,?,?,?,?,?,?)",
                    [(sid, i["code"], i["description"], i["unit"], float(i["rate"]), i.get("category"),
                      json.dumps(dict(provenance, page=i.get("page"), amended=bool(i.get("amended"))), ensure_ascii=False), t, None) for i in items])
    con.execute("UPDATE rate_schedules SET status='inactive' WHERE region='Tamil Nadu' AND id<>? AND status='active'", (sid,))
    con.execute("UPDATE rate_schedules SET status='active', imported_on=? WHERE id=?", (t, sid))
    con.execute("""INSERT INTO tn_versions(schedule_id, base_sha256, amendment_sha256, standard_data_sha256, edition, effective_from, effective_to,
                   status, activated_at, diff_summary) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(schedule_id) DO UPDATE SET status='active', activated_at=excluded.activated_at, diff_summary=excluded.diff_summary""",
                (sid, provenance.get("base_sha256"), provenance.get("amendment_sha256"), provenance.get("standard_data_sha256"),
                 meta.get("financial_year"), meta.get("effective_from"), meta.get("effective_to"), "active", t,
                 json.dumps(provenance.get("diff_summary") or {})))
    con.execute("UPDATE tn_versions SET status='superseded' WHERE schedule_id<>? AND status='active'", (sid,))
    con.commit()
    log(con, "activate", provenance.get("base_sha256"), schedule_id=sid, items=len(items))
