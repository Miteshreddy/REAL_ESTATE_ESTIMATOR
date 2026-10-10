"""Test fixtures. Every test session runs against a throw-away data directory (database, uploads), never the
real one. The two 'state' schedules created here are TEST FIXTURES ONLY: their items are copies of CPWD DSR rows
with deliberately different numbers so that rate differences are visible. They are not real schedules and
exist only inside the temporary test database."""
from __future__ import annotations

import csv
import importlib
import io
import os
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

SAMPLE = "compact_home.dxf"  # small generated drawing: fast, deterministic


def make_app(tmp):
    os.environ["EST_DATA_DIR"] = tmp
    import app as A
    A = importlib.reload(A)
    from fastapi.testclient import TestClient
    return A, TestClient(A.app)


@pytest.fixture(scope="session")
def env():
    tmp = tempfile.mkdtemp(prefix="est_test_")
    A, client = make_app(tmp)
    with client as c:
        yield A, c


def new_project(c, loc=None, schedule_id="", name="Test"):
    data = {"name": name, "sample": SAMPLE, "loc": __import__("json").dumps(loc or {})}
    if schedule_id:
        data["rate_schedule_id"] = schedule_id
    r = c.post("/api/projects", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def fixture_csv(c, factor):
    """CSV of the CPWD rows with every rate multiplied by `factor` (TEST DATA ONLY)."""
    rows = list(csv.DictReader(io.StringIO(c.get("/api/sor/export.csv").text)))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["code", "description", "unit", "rate", "category"])
    w.writeheader()
    for r in rows:
        w.writerow(dict(r, rate=round(float(r["rate"]) * factor, 2)))
    return buf.getvalue().encode()


def make_state_schedule(c, region, factor, **extra):
    meta = dict(name=f"TEST FIXTURE {region} SOR", authority=f"TEST {region} PWD", country="India", region=region,
                authority_level="state", schedule_type="SOR", code_system="CPWD-DSR", financial_year="2025-26",
                currency="INR", source="test fixture (not an official schedule)")
    meta.update(extra)
    r = c.post("/api/rate-schedules", json=meta)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    r = c.post(f"/api/rate-schedules/{sid}/import", files={"file": ("s.csv", fixture_csv(c, factor), "text/csv")}, data={"by": "pytest"})
    assert r.status_code == 200, r.text
    r = c.patch(f"/api/rate-schedules/{sid}", json={"status": "active"})
    assert r.status_code == 200, r.text
    return sid
