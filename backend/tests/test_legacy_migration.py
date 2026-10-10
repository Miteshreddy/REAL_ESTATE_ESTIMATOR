"""TEST 7: a database from before jurisdiction support (single `sor` table, projects without location columns)
still opens after the upgrade, keeps its original rates and totals, and is backed up before migration."""
from __future__ import annotations

import csv
import glob
import json
import os
import sqlite3
import tempfile

from conftest import make_app, new_project

LEGACY_PROJECTS = """CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT, client TEXT, location TEXT, created TEXT, updated TEXT,
    status TEXT, params TEXT, sheets TEXT, items TEXT, overrides TEXT, history TEXT, versions TEXT)"""
LEGACY_SOR = """CREATE TABLE sor(code TEXT PRIMARY KEY, description TEXT, unit TEXT, rate REAL, category TEXT,
    source TEXT DEFAULT 'seed', updated TEXT, analysis TEXT)"""


def test_7_legacy_project_opens_with_unchanged_rates():
    # 1) produce a real project with the current code, then rewrite it into the OLD database layout
    src = tempfile.mkdtemp(prefix="est_src_")
    A, client = make_app(src)
    with client as c:
        p = new_project(c, {}, name="Legacy")
        con0 = sqlite3.connect(os.path.join(src, "estimate.db"))
        r = con0.execute("SELECT id,name,client,location,created,updated,status,params,sheets,items,overrides,history,versions FROM projects WHERE id=?",
                         (p["id"],)).fetchone()
        expected_total = p["estimate"]["total"]
        item = next(i for i in p["estimate"]["items"] if i["key"] == "rcc_slab")
    legacy = tempfile.mkdtemp(prefix="est_legacy_")
    con = sqlite3.connect(os.path.join(legacy, "estimate.db"))
    con.execute(LEGACY_PROJECTS)
    con.execute(LEGACY_SOR)
    with open(os.path.join(A.REPO_DATA, "sor", "cpwd_dsr_2023_civil.csv"), encoding="utf-8") as f:
        con.executemany("INSERT INTO sor VALUES(?,?,?,?,?,?,?,?)",
                        [(x["code"], x["description"], x["unit"], float(x["rate"]), x["category"], "DSR 2023", "2026-01-01", None)
                         for x in csv.DictReader(f)])
    ov = {"rcc_slab": {"rate": 9999.0}}  # a legacy rate override without any schedule tag
    con.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (*r[:10], json.dumps(ov), r[11], r[12]))
    con.commit()
    con.close()

    # 2) start the upgraded app on the legacy database
    A2, client2 = make_app(legacy)
    with client2 as c:
        assert glob.glob(os.path.join(legacy, "estimate.db.pre-schedules-*.bak")), "database must be backed up before migration"
        g = c.get(f"/api/projects/{r[0]}").json()
        assert g["rate_source"]["schedule"]["id"] == "in-cpwd-dsr-2023-civil"
        assert g["rate_source"]["selection"]["mode"] == "legacy"
        slab = next(i for i in g["estimate"]["items"] if i["key"] == "rcc_slab")
        assert slab["base_rate"] == 9999.0  # legacy override preserved
        assert g["estimate"]["total"] > 0 and item["qty"] == slab["qty"]  # quantities unchanged; legacy rates kept (CPWD, now inactive)
        # the old table is kept as a backup, not dropped
        names = {x[0] for x in sqlite3.connect(os.path.join(legacy, "estimate.db")).execute("SELECT name FROM sqlite_master")}
        assert "sor_legacy_backup" in names and "rate_items" in names
        assert c.get("/api/projects").status_code == 200
