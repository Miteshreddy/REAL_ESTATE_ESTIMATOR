"""Tamil Nadu-only product scope.

* Every project is located in India / Tamil Nadu (district, city / municipality and executing authority are recorded).
* Pricing always resolves to the active, currently effective Tamil Nadu PWD schedule. Other schedules (CPWD, other
  states) stay in the database for audit of legacy projects but are INACTIVE and cannot be selected.
* A fresh database is bootstrapped from data/tnpwd/snapshot (the validated TN edition with full provenance).
"""
from __future__ import annotations

import csv
import json
import os
from datetime import date

import rates

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "data", "tnpwd", "snapshot")
STATE = "Tamil Nadu"
DISTRICTS = ["Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul", "Erode", "Kallakurichi",
             "Kancheepuram", "Kanniyakumari", "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai", "Nagapattinam", "Namakkal",
             "Nilgiris", "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi", "Thanjavur",
             "Theni", "Thoothukudi", "Tiruchirappalli", "Tirunelveli", "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai",
             "Tiruvarur", "Vellore", "Viluppuram", "Virudhunagar"]
EXEC_AUTHORITIES = ["Tamil Nadu PWD (Buildings)", "Tamil Nadu PWD (Water Resources)", "Highways Department", "Local body / municipality",
                    "Other TN Government department"]


class OutOfScope(ValueError):
    pass


def tn_loc(loc: dict | None) -> dict:
    loc = dict(loc or {})
    if loc.get("country") and loc["country"].strip().lower() != "india":
        raise OutOfScope("This estimator covers Tamil Nadu PWD works only (country must be India).")
    if loc.get("region") and loc["region"].strip().lower() != "tamil nadu":
        raise OutOfScope(f"This estimator covers Tamil Nadu PWD works only — '{loc['region']}' is not supported.")
    loc["country"], loc["region"] = "India", STATE
    loc["authority_level"] = "state"
    return loc


def deactivate_others(con):
    con.execute("UPDATE rate_schedules SET status='inactive' WHERE status='active' AND (region IS NULL OR region<>?)", (STATE,))


def active_tn(con, on: str | None = None):
    on = on or date.today().isoformat()
    rows = [dict(r) for r in con.execute("SELECT * FROM rate_schedules WHERE status='active' AND region=? AND code_system='TN-SOR'", (STATE,))]
    rows = [r for r in rows if (not r.get("effective_from") or r["effective_from"] <= on) and (not r.get("effective_to") or r["effective_to"] >= on)]
    rows.sort(key=lambda r: (r.get("effective_from") or "", r.get("financial_year") or ""), reverse=True)
    return rows[0] if rows else None


def resolve(con, loc=None, on=None):
    s = active_tn(con, on)
    if not s:
        return dict(status="unavailable", schedule=None, candidates=[],
                    reason="No validated Tamil Nadu PWD schedule is active — run the TN PWD refresh (Admin › Tamil Nadu PWD data).")
    pub = rates.public(rates._with_count(con, s))
    return dict(status="selected", schedule=pub, candidates=[pub],
                reason=f"Tamil Nadu PWD — latest validated applicable edition ({s.get('financial_year')}, effective {s.get('effective_from')})")


def bootstrap(con):
    """Fresh database: load the validated TN edition + Standard Data from the committed snapshot."""
    deactivate_others(con)
    if active_tn(con) or not os.path.exists(os.path.join(SNAP, "schedule.json")):
        return False
    from tnpwd_ingestion.store import ensure
    ensure(con)
    s = json.load(open(os.path.join(SNAP, "schedule.json"), encoding="utf-8"))
    if not con.execute("SELECT 1 FROM rate_schedules WHERE id=?", (s["id"],)).fetchone():
        rates._insert_schedule(con, dict(s, status="active"), imported_by="TN snapshot bootstrap")
    con.execute("UPDATE rate_schedules SET status='active' WHERE id=?", (s["id"],))
    con.execute("DELETE FROM rate_items WHERE schedule_id=?", (s["id"],))
    with open(os.path.join(SNAP, "rate_items.csv"), encoding="utf-8") as f:
        con.executemany("INSERT INTO rate_items(schedule_id, code, description, unit, rate, category, source, updated) VALUES(?,?,?,?,?,?,?,?)",
                        [(s["id"], r["code"], r["description"], r["unit"], float(r["rate"]), r["category"], r["source"], rates.now())
                         for r in csv.DictReader(f)])
    for d in json.load(open(os.path.join(SNAP, "documents.json"), encoding="utf-8")):
        con.execute(f"INSERT OR IGNORE INTO tn_documents({', '.join(d)}) VALUES({', '.join('?' * len(d))})", list(d.values()))
        if d.get("url"):
            con.execute("INSERT OR IGNORE INTO tn_doc_urls VALUES(?,?,?)", (d["sha256"], d["url"], d.get("downloaded_at")))
    for v in json.load(open(os.path.join(SNAP, "versions.json"), encoding="utf-8")):
        con.execute(f"INSERT OR IGNORE INTO tn_versions({', '.join(v)}) VALUES({', '.join('?' * len(v))})", list(v.values()))
    for it in json.load(open(os.path.join(SNAP, "standard_data_items.json"), encoding="utf-8")):
        con.execute(f"INSERT OR IGNORE INTO tn_sd_items({', '.join(it)}) VALUES({', '.join('?' * len(it))})", list(it.values()))
    return True


def locations():
    return dict(countries=[dict(name="India", region_label="State", district_label="District", city_label="City / municipality",
                                regions=[dict(name=STATE, type="State")], districts=DISTRICTS, cities=[])],
                authority_levels=[dict(value="state", label="Tamil Nadu PWD")], executing_authorities=EXEC_AUTHORITIES,
                scope="Tamil Nadu PWD only")
