"""The estimator improves from confirmed estimates; reference BOQs are scored and recorded."""
from __future__ import annotations

from conftest import new_project


def test_confirmed_choice_is_reused_on_next_project(env):
    _, c = env
    p = new_project(c, {})
    it = next(i for i in p["estimate"]["items"] if i["key"] == "door_shutter")
    assert it["map_method"] == "estimated"  # first time: no PWD rate → editable estimated average
    assert c.patch(f"/api/projects/{p['id']}/items/door_shutter", json=dict(sor_code="M-0387")).status_code == 200
    assert c.post(f"/api/projects/{p['id']}/confirm", json=dict(by="engineer")).status_code == 200
    q = new_project(c, {})
    d = next(i for i in q["estimate"]["items"] if i["key"] == "door_shutter")
    assert d["rate"] is not None and d["sor_code"] == "M-0387" and "learned" in d["map_check"]
    L = c.get("/api/learning").json()
    assert any(x["key"] == "door_shutter" and x["value"] == "M-0387" for x in L["learned"])


def test_reference_boq_comparison_recorded(env):
    _, c = env
    p = new_project(c, {})
    slab = next(i for i in p["estimate"]["items"] if i["key"] == "rcc_slab")
    csv_ = (f"description,unit,quantity,rate,amount\nRCC M20 slab concrete,cum,{slab['qty'] * 1.1:.2f},{slab['rate']:.2f},"
            f"{slab['qty'] * 1.1 * slab['rate']:.2f}\n").encode()
    r = c.post(f"/api/projects/{p['id']}/reference-boq", files={"file": ("boq.csv", csv_, "text/csv")},
               data={"approval_status": "provisional", "currency": "INR"})
    assert r.status_code == 200, r.text
    m = r.json()["metrics"]
    assert m["matched"] == 1 and abs(m["quantity"]["median_ape_pct"] - 9.09) < 0.2
    assert m["validation_grade"].startswith("PROVISIONAL")
    assert c.get("/api/learning").json()["evaluation_runs"]
