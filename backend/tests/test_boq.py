"""Tasks 12-14: reference BOQ validation, provenance, comparison rules and cost metrics."""
from __future__ import annotations

import hashlib
import os

from conftest import new_project


def _post(c, pid, csv_text, **meta):
    return c.post(f"/api/projects/{pid}/reference-boq", files={"file": ("boq.csv", csv_text.encode(), "text/csv")}, data=meta)


def test_approved_requires_authority_date_reference(env):
    _, c = env
    p = new_project(c, {})
    r = _post(c, p["id"], "description,unit,quantity,rate,amount\nX,cum,1,10,10\n", approval_status="approved", currency="INR")
    assert r.status_code == 422 and "approval_authority" in r.text


def test_arithmetic_currency_and_status_validation(env):
    _, c = env
    p = new_project(c, {})
    r = _post(c, p["id"], "description,unit,quantity,rate,amount\nX,cum,2,10,99\n", approval_status="provisional", currency="INR")
    assert r.status_code == 422 and "≠ amount" in r.text
    r = _post(c, p["id"], "description,unit,quantity,rate,amount\nX,cum,2,10,20\n", approval_status="provisional")
    assert r.status_code == 422 and "currency" in r.text
    r = _post(c, p["id"], "description,unit,quantity,rate,amount\nX,cum,2,10,20\n", approval_status="final-ish", currency="INR")
    assert r.status_code == 422 and "approval_status" in r.text


def test_original_preserved_and_approved_grade(env):
    A, c = env
    p = new_project(c, {})
    txt = "item_code,description,unit,quantity,rate,amount\nW-0003,Clearing scrub jungle,sqm,100,6.36,636\n"
    r = _post(c, p["id"], txt, approval_status="approved", currency="INR", approval_authority="EE PWD Bldgs (TEST)",
              approval_date="2026-01-01", source_reference="TEST FIXTURE — not a real sanction", drawing_revision="R0")
    assert r.status_code == 200, r.text
    sha = hashlib.sha256(txt.encode()).hexdigest()
    assert r.json()["reference"]["sha256"] == sha
    assert os.path.exists(os.path.join(A.DATA, "reference_boqs", p["id"], sha + ".csv"))
    m = r.json()["metrics"]
    assert m["validation_grade"].startswith("VALIDATED") and m["matched"] == 1
    assert r.json()["comparison"]["pairs"][0]["method"] == "exact item code"


def test_comparison_never_matches_incompatible_units_and_handles_zero():
    import boq
    est = [dict(key="rcc_slab", description="Reinforced cement concrete slab", qty=10.0, unit="cum", amount=1000.0, rate=100.0, category="RCC Works"),
           dict(key="plaster_int", description="Cement plaster internal walls", qty=50.0, unit="sqm", amount=500.0, rate=10.0, category="Plastering")]
    rows = [dict(code="", description="RCC slab concrete", unit="sqm", qty=10.0, amount=1000.0),
            dict(code="", description="cement plaster internal", unit="sqm", qty=0.0, amount=0.0)]
    cmp = boq.compare(rows, est)
    assert len(cmp["pairs"]) == 1 and cmp["pairs"][0]["key"] == "plaster_int" and cmp["pairs"][0]["rel_qty_diff"] is None
    assert "incompatible unit" in cmp["unmatched_reference"][0]["reason"]
    m = boq.metrics(cmp, dict(total=1500.0, subtotal=1500.0), rows, dict(approval_status="provisional"))
    assert m["quantity"]["zero_reference_lines"] == 1 and m["validation_grade"].startswith("PROVISIONAL")
    assert m["completeness"]["matched_reference_amount_pct"] == 0.0


def test_ambiguous_description_not_matched():
    import boq
    est = [dict(key="rcc_beam", description="Reinforced cement concrete work", qty=1.0, unit="cum", amount=1.0, rate=1.0, category="RCC Works"),
           dict(key="rcc_column", description="Reinforced cement concrete work", qty=1.0, unit="cum", amount=1.0, rate=1.0, category="RCC Works")]
    cmp = boq.compare([dict(code="", description="reinforced cement concrete", unit="cum", qty=1.0, amount=1.0)], est)
    assert not cmp["pairs"] and "ambiguous" in cmp["unmatched_reference"][0]["reason"]
