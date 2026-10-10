"""The estimator gets better with use — from engineers' confirmed decisions and reference BOQs, never from unverified web text.

1. Learned mappings: when an estimate is CONFIRMED, every take-off line whose TN PWD item or rate the engineer chose /
   confirmed is recorded. On later projects
     * a learned TN SOR code is applied automatically (rate still read from the CURRENT TN edition), labelled
       "learned from N confirmed estimates";
     * a learned manual rate is only SUGGESTED (rates go stale) — the line stays unpriced until confirmed.
2. Reference BOQs: an approved / sanctioned BOQ uploaded for a project is compared line by line with the system's
   quantities and costs; every comparison is stored in evaluation_runs, which is the real-accuracy record.
"""
from __future__ import annotations

import json
import re
from datetime import datetime


def ensure(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS learned_mappings(key TEXT, unit TEXT, kind TEXT, value TEXT, schedule_id TEXT, n INTEGER,
        first_at TEXT, last_at TEXT, last_project TEXT, PRIMARY KEY(key, unit, kind, value));
    CREATE TABLE IF NOT EXISTS learned_votes(key TEXT, unit TEXT, kind TEXT, value TEXT, project TEXT, PRIMARY KEY(key, unit, kind, value, project));
    CREATE TABLE IF NOT EXISTS reference_boqs(project_id TEXT PRIMARY KEY, uploaded_at TEXT, source TEXT, rows TEXT);
    CREATE TABLE IF NOT EXISTS evaluation_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, project_id TEXT, kind TEXT, metrics TEXT);
    """)


def now():
    return datetime.now().isoformat(timespec="seconds")


def record_confirmation(con, p, est):
    """Called when an estimate is confirmed."""
    ensure(con)
    ov = p.get("overrides") or {}
    for it in est["items"]:
        o = ov.get(it["key"]) or {}
        if it.get("custom"):
            continue
        rows = []
        if o.get("sor_code"):
            rows.append(("sor_code", o["sor_code"]))
        elif it.get("sor_code") and it.get("status") in ("confirmed", "edited") and it.get("map_method") in ("table", "learned", "nlp"):
            rows.append(("sor_code", it["sor_code"]))
        if o.get("rate") is not None:
            rows.append(("rate", str(float(o["rate"]))))
        for kind, val in rows:
            new = con.execute("INSERT OR IGNORE INTO learned_votes VALUES(?,?,?,?,?)", (it["key"], it["unit"], kind, val, p["id"])).rowcount
            if not new:
                continue  # the same project re-confirmed after reopening counts once
            con.execute("""INSERT INTO learned_mappings VALUES(?,?,?,?,?,1,?,?,?)
                           ON CONFLICT(key, unit, kind, value) DO UPDATE SET n=n+1, last_at=excluded.last_at, last_project=excluded.last_project""",
                        (it["key"], it["unit"], kind, val, p.get("rate_schedule_id"), now(), now(), p["id"]))


def learned(con, key, unit):
    ensure(con)
    return [dict(r) for r in con.execute("SELECT * FROM learned_mappings WHERE key=? AND unit=? ORDER BY n DESC, last_at DESC", (key, unit))]


def apply_learned(con, items, by_code):
    """Unpriced lines: use what engineers confirmed before."""
    for it in items:
        if it.get("derived") or it.get("sor_code") or it.get("custom"):
            continue
        L = learned(con, it["key"], it["unit"])
        from tn_pricing import unit_key
        code = next((x for x in L if x["kind"] == "sor_code" and x["value"] in by_code
                     and unit_key(by_code[x["value"]]["unit"]) == unit_key(it["unit"])), None)
        if code:
            r = by_code[code["value"]]
            it.update(sor_code=r["code"], map_method="learned", status="auto", map_score=min(1.0, 0.6 + 0.1 * code["n"]), rate_gap=None,
                      candidates=[dict(code=r["code"], description=r["description"][:160], unit=r["unit"], rate=r["rate"], score=1.0)],
                      map_check=f"learned: TN item {r['code']} chosen by engineers in {code['n']} confirmed estimate(s) "
                                f"(last {code['last_at'][:10]}); rate from the current TN edition")
            continue
        rate = next((x for x in L if x["kind"] == "rate"), None)
        if rate:
            it["learned_rate"] = dict(rate=float(rate["value"]), n=rate["n"], last_at=rate["last_at"])
            it["map_check"] = (it.get("map_check") or "") + f" · engineers entered ₹{float(rate['value']):,.2f} in {rate['n']} confirmed estimate(s) — confirm to use"


# --------------------------------------------------------------------------- reference BOQ
def _num(v):
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None


def save_reference(con, pid, rows, source):
    ensure(con)
    clean = []
    for r in rows:
        k = {str(a).strip().lower(): b for a, b in r.items() if a}
        q, a = _num(k.get("qty") or k.get("quantity")), _num(k.get("amount") or k.get("cost"))
        if q is None and a is None:
            continue
        clean.append(dict(code=str(k.get("code") or k.get("item code") or k.get("sor code") or "").strip(),
                          description=str(k.get("description") or k.get("item") or "")[:300], unit=str(k.get("unit") or "").strip(),
                          qty=q, rate=_num(k.get("rate")), amount=a))
    con.execute("INSERT OR REPLACE INTO reference_boqs VALUES(?,?,?,?)", (pid, now(), source, json.dumps(clean)))
    return clean


def _words(s):
    s = re.sub(r"\bm\s*-\s*(\d\d)", r"m\1", (s or "").lower())
    return set(re.findall(r"[a-z]{3,}|\d+:\d+(?::\d+)?|m\d\d", s)) | ({"rcc"} if re.search(r"reinforced cement concrete|\brcc\b", s) else set())


def _item_text(i):
    return " ".join(str(x) for x in (i["description"], i.get("sor_desc"), (i.get("derived") or {}).get("description"), i["key"].replace("_", " ")) if x)


def compare(con, pid, est):
    """Match reference lines to estimate lines (same TN code, else best description overlap with the same unit)."""
    ensure(con)
    r = con.execute("SELECT * FROM reference_boqs WHERE project_id=?", (pid,)).fetchone()
    if not r:
        return None
    ref = json.loads(r["rows"])
    items = est["items"]
    pairs, unmatched = [], []
    for x in ref:
        it = next((i for i in items if x["code"] and i.get("sor_code") == x["code"]), None)
        if not it:
            from tnpwd_ingestion.rate_analysis import unit_of
            ux = unit_of(x["unit"])
            cands = [(len(_words(x["description"]) & _words(_item_text(i))) / max(1, len(_words(x["description"]))), i) for i in items
                     if not x["unit"] or ux is None or (unit_of(i["unit"]) or (None,))[0] == ux[0]]
            cands.sort(key=lambda t: -t[0])
            it = cands[0][1] if cands and cands[0][0] >= 0.35 else None
        if it:
            pairs.append(dict(reference=x, key=it["key"], system_qty=it["qty"], system_amount=it["amount"],
                              qty_err=(it["qty"] - x["qty"]) / x["qty"] if x.get("qty") else None,
                              amount_err=(it["amount"] - x["amount"]) / x["amount"] if x.get("amount") else None))
        else:
            unmatched.append(x)
    qe = [abs(p["qty_err"]) for p in pairs if p["qty_err"] is not None]
    ae = [abs(p["amount_err"]) for p in pairs if p["amount_err"] is not None]
    ref_total = sum(x["amount"] or 0 for x in ref)
    import statistics as st
    m = dict(reference_lines=len(ref), matched=len(pairs), unmatched=len(unmatched),
             qty_median_ape=round(st.median(qe) * 100, 2) if qe else None, qty_within10=round(sum(e <= .1 for e in qe) / len(qe) * 100, 1) if qe else None,
             amount_median_ape=round(st.median(ae) * 100, 2) if ae else None,
             total_reference=round(ref_total, 2), total_system=est["total"],
             total_err_pct=round((est["total"] / ref_total - 1) * 100, 2) if ref_total else None)
    con.execute("INSERT INTO evaluation_runs(at, project_id, kind, metrics) VALUES(?,?,?,?)", (now(), pid, "reference_boq", json.dumps(m)))
    return dict(metrics=m, pairs=pairs, unmatched=unmatched, source=r["source"], uploaded_at=r["uploaded_at"])


def accuracy_history(con):
    ensure(con)
    return [dict(r, metrics=json.loads(r["metrics"])) for r in con.execute("SELECT * FROM evaluation_runs ORDER BY at DESC LIMIT 200")]
