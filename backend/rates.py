"""Jurisdiction-aware rate schedules.

    Project location ──► jurisdiction ──► applicable rate schedule ──► rate items

* A rate schedule (CPWD DSR 2023, a State PWD SOR, a municipal schedule …) is its own entity with its
  authority, scope (country / region / district / city — empty = the whole parent level), financial year,
  revision, effective dates, source and status.
* Rate items belong to exactly one schedule (primary key schedule_id + code).
* resolve() decides which schedule applies to a location. It never falls back to an unrelated schedule:
  if nothing matches the result is "unavailable"; if several match equally the user must choose.
* Location never touches quantities — it only selects where rates come from.
No rate in this module is invented: schedules and items only enter the database by import / explicit entry.
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import date, datetime

import nlp

AUTHORITY_LEVELS = [
    ("central", "Central government (e.g. CPWD)"),
    ("state", "State government (State PWD / SOR)"),
    ("local", "Local body / municipal"),
    ("department", "Other department / agency"),
]
STATUSES = ("draft", "active", "inactive")
META_FIELDS = ("name", "authority", "department", "country", "region", "district", "city", "authority_level", "schedule_type", "adopts",
               "code_system", "year", "financial_year", "revision", "effective_from", "effective_to", "currency", "source",
               "source_ref", "notes")
SCOPE = ("region", "district", "city")

CPWD_ID = "in-cpwd-dsr-2023-civil"
CPWD_META = dict(
    id=CPWD_ID, name="CPWD Delhi Schedule of Rates 2023 (Civil)", authority="CPWD",
    department="Central Public Works Department, Ministry of Housing and Urban Affairs, Government of India",
    country="India", region=None, district=None, city=None, authority_level="central", schedule_type="DSR",
    code_system="CPWD-DSR", year="2023", financial_year=None, revision=None, effective_from=None, effective_to=None,
    currency="INR", source="Official government document",
    source_ref="CPWD DSR 2023 Vol. I & II (Civil, English) — dsr_2023_english_nsrcivil.pdf, parsed by ml/training/import_dsr.py "
               "into data/sor/cpwd_dsr_2023_civil.csv",
    notes="Rates are CPWD base rates for Delhi. CPWD publishes separate cost indices for other places; none is applied "
          "automatically. The effective date is not recorded in the imported data.",
    status="active")


def now():
    return datetime.now().isoformat(timespec="seconds")


def _n(v):
    v = (v if v is not None else "")
    v = str(v).strip()
    return v or None


def _eq(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


# ------------------------------------------------------------------------------------------- schema / migration
def ensure_schema(con, dsr_csv: str, seed_fallback=None):
    """Create the schedule tables and migrate a pre-schedule database without losing anything."""
    con.execute("""CREATE TABLE IF NOT EXISTS rate_schedules(id TEXT PRIMARY KEY, name TEXT NOT NULL, authority TEXT,
        department TEXT, country TEXT, region TEXT, district TEXT, city TEXT, authority_level TEXT, schedule_type TEXT,
        code_system TEXT, year TEXT, financial_year TEXT, revision TEXT, effective_from TEXT, effective_to TEXT,
        currency TEXT, source TEXT, source_ref TEXT, notes TEXT, status TEXT DEFAULT 'draft', created TEXT,
        imported_on TEXT, imported_by TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS rate_items(schedule_id TEXT NOT NULL, code TEXT NOT NULL, description TEXT,
        unit TEXT, rate REAL, category TEXT, source TEXT, updated TEXT, analysis TEXT, PRIMARY KEY(schedule_id, code))""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_sched_scope ON rate_schedules(country, region, status)")
    pcols = {r[1] for r in con.execute("PRAGMA table_info(projects)")}
    for c in ("loc", "rate_schedule_id", "rate_selection"):
        if c not in pcols:
            con.execute(f"ALTER TABLE projects ADD COLUMN {c} TEXT")
    # adoption: an authority that officially adopts another schedule (e.g. a State PWD adopting CPWD DSR) is a
    # schedule of its own (jurisdiction, authority, source) whose items are read from the adopted schedule
    scols = {r[1] for r in con.execute("PRAGMA table_info(rate_schedules)")}
    if "adopts" not in scols:
        con.execute("ALTER TABLE rate_schedules ADD COLUMN adopts TEXT")

    has_cpwd = con.execute("SELECT 1 FROM rate_schedules WHERE id=?", (CPWD_ID,)).fetchone()
    if not has_cpwd:
        _insert_schedule(con, CPWD_META, imported_by="system migration")
    if not con.execute("SELECT 1 FROM rate_items WHERE schedule_id=? LIMIT 1", (CPWD_ID,)).fetchone():
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "sor" in tables and con.execute("SELECT COUNT(*) FROM sor").fetchone()[0]:
            # legacy single library = CPWD DSR 2023 (+ the user's edits / rate analyses): move it, keep the old table
            con.execute("""INSERT INTO rate_items(schedule_id, code, description, unit, rate, category, source, updated, analysis)
                           SELECT ?, code, description, unit, rate, category, source, updated, analysis FROM sor""", (CPWD_ID,))
            con.execute("ALTER TABLE sor RENAME TO sor_legacy_backup")
        else:
            seed_cpwd(con, dsr_csv, seed_fallback)
    # legacy projects: keep the schedule they were priced with (the only library that existed = CPWD DSR 2023)
    for pid, ov in con.execute("SELECT id, overrides FROM projects WHERE rate_schedule_id IS NULL OR rate_schedule_id=''").fetchall():
        sel = dict(mode="legacy", status="selected", at=now(),
                   reason="Created before jurisdiction support; priced with the single library that existed (CPWD DSR 2023). Preserved unchanged.",
                   history=[])
        try:
            ovd = json.loads(ov or "{}")
        except ValueError:
            ovd = {}
        for o in ovd.values():
            if (o.get("sor_code") or o.get("rate") is not None) and not o.get("schedule_id"):
                o["schedule_id"] = CPWD_ID
        con.execute("UPDATE projects SET rate_schedule_id=?, rate_selection=?, loc=COALESCE(loc, '{}'), overrides=? WHERE id=?",
                    (CPWD_ID, json.dumps(sel), json.dumps(ovd), pid))


def seed_cpwd(con, dsr_csv, seed_fallback=None):
    con.execute("DELETE FROM rate_items WHERE schedule_id=?", (CPWD_ID,))
    t = now()
    rows = []
    if os.path.exists(dsr_csv):
        with open(dsr_csv, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append((CPWD_ID, r["code"], r["description"], r["unit"], float(r["rate"]), r["category"], "DSR 2023", t, None))
    elif seed_fallback:
        rows = [(CPWD_ID, *r, t, a) for r, a in seed_fallback()]
    con.executemany("INSERT INTO rate_items VALUES(?,?,?,?,?,?,?,?,?)", rows)


def _insert_schedule(con, m, imported_by=None):
    vals = {k: _n(m.get(k)) for k in META_FIELDS}
    con.execute(f"""INSERT INTO rate_schedules(id, {', '.join(META_FIELDS)}, status, created, imported_on, imported_by)
                    VALUES(?, {', '.join('?' * len(META_FIELDS))}, ?, ?, ?, ?)""",
                (m["id"], *[vals[k] for k in META_FIELDS], m.get("status", "draft"), now(), now() if m.get("status") == "active" else None, imported_by))


# ------------------------------------------------------------------------------------------- queries
def item_source(con, sid):
    """Schedule whose rate items are used: the schedule itself, or the one it officially adopts."""
    r = con.execute("SELECT adopts FROM rate_schedules WHERE id=?", (sid,)).fetchone()
    return (r[0] if r and r[0] else sid)


def get_schedule(con, sid):
    if not sid:
        return None
    r = con.execute("SELECT * FROM rate_schedules WHERE id=?", (sid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["item_count"] = con.execute("SELECT COUNT(*) FROM rate_items WHERE schedule_id=?", (item_source(con, sid),)).fetchone()[0]
    return d


def list_schedules(con, **f):
    q, args = "SELECT * FROM rate_schedules WHERE 1=1", []
    for k in ("country", "region", "authority", "authority_level", "status", "schedule_type"):
        if f.get(k):
            q += f" AND lower(COALESCE({k},''))=lower(?)"
            args.append(f[k])
    if f.get("year"):
        q += " AND (year=? OR financial_year=?)"
        args += [f["year"], f["year"]]
    out = [dict(r) for r in con.execute(q + " ORDER BY country, region, authority, year DESC", args)]
    counts = dict(con.execute("SELECT schedule_id, COUNT(*) FROM rate_items GROUP BY schedule_id").fetchall())
    for d in out:
        d["item_count"] = counts.get(d.get("adopts") or d["id"], 0)
    return out


def items_of(con, sid):
    out = [dict(r) for r in con.execute("SELECT * FROM rate_items WHERE schedule_id=?", (item_source(con, sid),))]
    for r in out:
        r["analysis"] = json.loads(r["analysis"]) if r.get("analysis") else None
    return out


def label(s):
    """One-line human name: 'CPWD · CPWD Delhi Schedule of Rates 2023 (Civil)'."""
    if not s:
        return "No rate schedule"
    bits = [s["name"]]
    if s.get("financial_year") and s["financial_year"] not in s["name"]:
        bits.append(f"FY {s['financial_year']}")
    if s.get("revision"):
        bits.append(f"rev. {s['revision']}")
    return " · ".join(bits)


def scope_text(s):
    parts = [s.get(k) for k in ("city", "district", "region", "country") if s.get(k)]
    return ", ".join(parts) + (" (whole country)" if not any(s.get(k) for k in SCOPE) else "")


def public(s):
    if not s:
        return None
    d = {k: s.get(k) for k in ("id", "name", "authority", "department", "country", "region", "district", "city", "authority_level",
                               "schedule_type", "code_system", "year", "financial_year", "revision", "effective_from",
                               "effective_to", "currency", "source", "source_ref", "notes", "status", "imported_on",
                               "imported_by", "item_count", "adopts")}
    d["label"] = label(s)
    d["scope"] = scope_text(s)
    return d


# ------------------------------------------------------------------------------------------- resolution
def loc_text(loc):
    if not loc or not any(loc.get(k) for k in ("country", "region", "district", "city")):
        return "Not specified"
    return ", ".join(loc[k] for k in ("city", "district", "region", "country") if loc.get(k))


def resolve(con, loc: dict | None, on: str | None = None) -> dict:
    """Applicable schedule for a project location.

    Returns {status: selected | ambiguous | unavailable, schedule, candidates[], reason}.
    Rules (in order):
      1. only ACTIVE schedules of the same country whose scope contains the location (an empty scope level
         covers the whole parent level) and whose effective window contains the project date;
      2. if the project names its executing authority level (central / state / local / department), only
         schedules of that level;
      3. of several revisions of the same schedule (authority + type + scope) the latest one is kept;
      4. the most specific scope wins (city > district > region > country) — but a country-wide schedule
         is only auto-selected when the authority level was given (CPWD DSR applies to central works,
         not automatically to state works);
      5. anything still tied is returned as 'ambiguous' for the user to choose.
    """
    loc = loc or {}
    country = _n(loc.get("country"))
    if not country:
        return dict(status="unavailable", schedule=None, candidates=[],
                    reason="Project location (country) is not specified, so no rate schedule can be determined.")
    on = on or date.today().isoformat()
    rows = [dict(r) for r in con.execute("SELECT * FROM rate_schedules WHERE status='active' AND lower(country)=lower(?)", (country,))]
    cands = []
    for s in rows:
        ok = True
        for k in SCOPE:
            if s.get(k) and not _eq(s[k], loc.get(k)):
                ok = False
        if s.get("effective_from") and s["effective_from"] > on:
            ok = False
        if s.get("effective_to") and s["effective_to"] < on:
            ok = False
        if ok:
            cands.append(s)
    lvl = _n(loc.get("authority_level"))
    if lvl:
        cands = [s for s in cands if _eq(s.get("authority_level"), lvl)]
    # latest revision per schedule family
    fam = {}
    for s in cands:
        key = (s.get("authority") or "", s.get("schedule_type") or "", (s.get("region") or "").lower(),
               (s.get("district") or "").lower(), (s.get("city") or "").lower(), s.get("authority_level") or "")
        rank = (s.get("effective_from") or "", s.get("financial_year") or "", s.get("year") or "", s.get("revision") or "")
        if key not in fam or rank > fam[key][0]:
            fam[key] = (rank, s)
    cands = [v[1] for v in fam.values()]
    spec = lambda s: sum(1 for k in SCOPE if s.get(k))
    cands.sort(key=lambda s: (-spec(s), s.get("authority") or ""))
    where = loc_text(loc)
    lvl_txt = dict(AUTHORITY_LEVELS).get(lvl, "") if lvl else ""
    if not cands:
        others = [public(s) for s in rows if s.get("status") == "active"]
        return dict(status="unavailable", schedule=None, candidates=[],
                    other_active=[o for o in others if o],
                    reason=f"No official rate schedule is configured for this jurisdiction ({where}"
                           + (f", {lvl_txt}" if lvl_txt else "") + "). An administrator can import the applicable schedule.")
    top = [s for s in cands if spec(s) == spec(cands[0])]
    if len(top) == 1 and (lvl or spec(top[0]) > 0):
        s = top[0]
        why = (f"{s['authority']} schedule for {scope_text(s)}" + (f", {lvl_txt}" if lvl_txt else "")
               + (" — most specific jurisdiction match" if len(cands) > 1 else ""))
        return dict(status="selected", schedule=public(_with_count(con, s)), candidates=[public(_with_count(con, c)) for c in cands], reason=why)
    return dict(status="ambiguous", schedule=None, candidates=[public(_with_count(con, c)) for c in cands],
                reason=("Several schedules could apply to " + where + ". Choose the one that governs this work"
                        if len(top) > 1 else
                        f"Only a country-wide schedule ({label(top[0])}, {top[0].get('authority_level')} works) matches {where}. "
                        "It is not applied automatically — select it explicitly if the work is executed under it, "
                        "or set the executing authority."))


def _with_count(con, s):
    s = dict(s)
    s["item_count"] = con.execute("SELECT COUNT(*) FROM rate_items WHERE schedule_id=?", (item_source(con, s["id"]),)).fetchone()[0]
    return s


# ------------------------------------------------------------------------------------------- admin: create / activate / import
def slug(m):
    parts = [m.get("country"), m.get("region"), m.get("district"), m.get("city"), m.get("authority"), m.get("schedule_type"),
             m.get("financial_year") or m.get("year"), ("r" + m["revision"]) if m.get("revision") else None]
    return re.sub(r"[^a-z0-9]+", "-", "-".join(p for p in parts if p).lower()).strip("-")[:80] or "schedule"


def validate_meta(con, m, sid=None):
    errs = []
    for k in ("name", "authority", "country", "authority_level", "schedule_type", "currency", "source"):
        if not _n(m.get(k)):
            errs.append(f"'{k}' is required")
    if _n(m.get("authority_level")) and m["authority_level"] not in dict(AUTHORITY_LEVELS):
        errs.append(f"authority_level must be one of {', '.join(dict(AUTHORITY_LEVELS))}")
    if _n(m.get("adopts")):
        t = con.execute("SELECT adopts FROM rate_schedules WHERE id=?", (m["adopts"],)).fetchone()
        if not t:
            errs.append(f"adopted schedule '{m['adopts']}' does not exist")
        elif t[0]:
            errs.append("an adopted schedule cannot itself be an adoption")
        elif m["adopts"] == sid:
            errs.append("a schedule cannot adopt itself")
    for k in ("effective_from", "effective_to"):
        if _n(m.get(k)) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m[k]):
            errs.append(f"'{k}' must be a date YYYY-MM-DD")
    if _n(m.get("effective_from")) and _n(m.get("effective_to")) and m["effective_to"] < m["effective_from"]:
        errs.append("effective_to is before effective_from")
    if _n(m.get("district")) and not _n(m.get("region")) or _n(m.get("city")) and not _n(m.get("region")):
        errs.append("a district / city scope needs its state / region")
    # duplicate schedule = same authority, type, scope, year and revision
    q = """SELECT id FROM rate_schedules WHERE lower(COALESCE(authority,''))=lower(?) AND lower(COALESCE(schedule_type,''))=lower(?)
           AND lower(COALESCE(country,''))=lower(?) AND lower(COALESCE(region,''))=lower(?) AND lower(COALESCE(district,''))=lower(?)
           AND lower(COALESCE(city,''))=lower(?) AND COALESCE(year,'')=? AND COALESCE(financial_year,'')=? AND COALESCE(revision,'')=?"""
    dup = con.execute(q, tuple((_n(m.get(k)) or "") for k in ("authority", "schedule_type", "country", "region", "district", "city",
                                                                  "year", "financial_year", "revision"))).fetchall()
    dup = [d[0] for d in dup if d[0] != sid]
    if dup:
        errs.append(f"a schedule with the same authority, type, jurisdiction, year and revision already exists ({dup[0]})")
    return errs


def create_schedule(con, m, by=None):
    errs = validate_meta(con, m)
    if errs:
        return None, errs
    sid = m.get("id") or slug(m)
    base, i = sid, 2
    while con.execute("SELECT 1 FROM rate_schedules WHERE id=?", (sid,)).fetchone():
        sid, i = f"{base}-{i}", i + 1
    _insert_schedule(con, dict(m, id=sid, status="draft"), imported_by=by)
    return sid, []


def activation_errors(con, sid):
    s = get_schedule(con, sid)
    if not s:
        return ["schedule not found"]
    errs = validate_meta(con, s, sid)
    if s["item_count"] == 0:
        errs.append("the schedule has no rate items — import them before activating")
    # another ACTIVE schedule of the same family whose effective window overlaps = accidental duplicate activation
    for o in con.execute("""SELECT * FROM rate_schedules WHERE status='active' AND id<>? AND lower(COALESCE(authority,''))=lower(?)
                            AND lower(COALESCE(schedule_type,''))=lower(?) AND lower(COALESCE(country,''))=lower(?)
                            AND lower(COALESCE(region,''))=lower(?) AND lower(COALESCE(district,''))=lower(?)
                            AND lower(COALESCE(city,''))=lower(?)""",
                         (sid, s.get("authority") or "", s.get("schedule_type") or "", s.get("country") or "", s.get("region") or "",
                          s.get("district") or "", s.get("city") or "")).fetchall():
        o = dict(o)
        a0, a1 = s.get("effective_from") or "0000", s.get("effective_to") or "9999"
        b0, b1 = o.get("effective_from") or "0000", o.get("effective_to") or "9999"
        if a0 <= b1 and b0 <= a1:
            errs.append(f"'{label(o)}' ({o['id']}) is already active for the same authority and jurisdiction over an overlapping "
                        "period — set its effective_to date or deactivate it first")
    return errs


UNITS_OK = re.compile(r"^.{1,80}$")  # official units can be long ("per bag of 50kg cement used")


def parse_rows(rows):
    """Normalise imported rows and validate them. Returns (items, errors). Nothing is written here."""
    items, errs, seen = [], [], {}
    for n, row in enumerate(rows, start=2):
        r = {str(k).strip().lower(): ("" if v is None else str(v)).strip() for k, v in row.items() if k}
        if not any(r.values()):
            continue
        code = r.get("code") or r.get("item no") or r.get("item no.") or r.get("item code") or r.get("sl no")
        desc = r.get("description") or r.get("desc") or r.get("item description")
        unit = r.get("unit")
        rate = r.get("rate") or r.get("rate (rs)") or r.get("rate in rs") or r.get("rate (inr)")
        cat = r.get("category") or r.get("chapter") or r.get("sub head") or "Miscellaneous"
        bad = []
        if not code:
            bad.append("missing code")
        if not desc:
            bad.append("missing description")
        if not unit:
            bad.append("missing unit")
        elif not UNITS_OK.match(unit):
            bad.append(f"invalid unit '{unit}'")
        val = None
        if not rate:
            bad.append("missing rate")
        else:
            try:
                val = float(rate.replace(",", ""))
                if not (val > 0) or val != val or val > 1e9:
                    bad.append(f"invalid rate '{rate}' (must be a positive number)")
            except ValueError:
                bad.append(f"invalid rate '{rate}' (not a number)")
        if code and code in seen:
            bad.append(f"duplicate code {code} (also on row {seen[code]})")
        if code:
            seen.setdefault(code, n)
        an = r.get("analysis")
        if an:
            try:
                an = json.dumps(json.loads(an))
            except ValueError:
                bad.append("analysis is not valid JSON")
        if bad:
            errs.append(f"row {n}: " + "; ".join(bad))
        else:
            items.append((code, desc, unit, val, cat, an or None))
    if not items and not errs:
        errs.append("the file contains no rate items (expected columns: code, description, unit, rate, category)")
    return items, errs


def import_items(con, sid, rows, by=None, replace=False):
    s = get_schedule(con, sid)
    if not s:
        return dict(ok=False, errors=["schedule not found"])
    if s.get("adopts"):
        return dict(ok=False, errors=[f"this schedule adopts {s['adopts']}; its items come from that schedule"])
    if s["status"] == "active" and not replace:
        return dict(ok=False, errors=["this schedule is active; import into a new draft schedule (new revision) instead, "
                                      "or pass replace=true to replace its items deliberately"])
    items, errs = parse_rows(rows)
    if errs:
        return dict(ok=False, errors=errs[:200], error_count=len(errs), valid_rows=len(items))
    t = now()
    con.execute("DELETE FROM rate_items WHERE schedule_id=?", (sid,))
    con.executemany("INSERT INTO rate_items VALUES(?,?,?,?,?,?,?,?,?)",
                    [(sid, c, d, u, r, k, "import", t, a) for c, d, u, r, k, a in items])
    con.execute("UPDATE rate_schedules SET imported_on=?, imported_by=? WHERE id=?", (t, by or "administrator", sid))
    return dict(ok=True, imported=len(items))


# ------------------------------------------------------------------------------------------- per-schedule matcher cache
class Library:
    """Rate items + TF-IDF matcher of ONE schedule, built on demand and cached by schedule id."""

    def __init__(self):
        self._cache = {}

    def get(self, con, sid):
        if not sid:
            return {}, None
        if sid not in self._cache:
            rows = items_of(con, sid)
            self._cache[sid] = ({r["code"]: r for r in rows}, nlp.SORMatcher(rows) if rows else None)
        return self._cache[sid]

    def invalidate(self, sid=None):
        if sid is None:
            self._cache.clear()
        else:
            self._cache.pop(sid, None)


def load_regions(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
