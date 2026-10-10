"""Estimated average rates, client-facing branding, web price parsing."""
from __future__ import annotations

from conftest import new_project


def test_missing_pwd_rates_get_editable_estimates(env):
    _, c = env
    p = new_project(c, {})
    items = p["estimate"]["items"]
    est = [i for i in items if i.get("map_method") == "estimated"]
    assert est and all(i["rate"] and i["rate"] > 0 for i in est)
    assert all(i["derived"]["basis"] for i in est)
    assert all(i["confidence_label"] != "HIGH CONFIDENCE" for i in est)
    k = est[0]["key"]  # user override wins over the estimate
    r = c.patch(f"/api/projects/{p['id']}/items/{k}", json={"rate": 1234.5})
    assert r.status_code == 200
    it = next(i for i in c.get(f"/api/projects/{p['id']}").json()["estimate"]["items"] if i["key"] == k)
    assert it["base_rate"] == 1234.5


def test_branding_hides_state_name():
    import brand
    assert brand.text("Tamil Nadu PWD Schedule of Rates 2025-26") == "PWD Schedule of Rates 2025-26"
    assert brand.text("Public Works Department, Government of Tamil Nadu") == "Public Works Department"
    assert brand.text("TN SOR W-0003") == "SOR W-0003"
    assert brand.text("Chennai, Tamil Nadu") == "Chennai"
    assert brand.debrand({"a": ["India · Tamil Nadu"]}) == {"a": ["India"]}


def test_report_and_ui_do_not_show_state_name(env):
    import os
    _, c = env
    p = new_project(c, {})
    html = c.get(f"/api/projects/{p['id']}/report").text
    assert "Tamil Nadu" not in html
    ui = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "index.html")
    assert "Tamil Nadu" not in open(ui, encoding="utf-8").read()


def test_web_price_parsing_and_unconfigured(monkeypatch):
    import rate_lookup
    assert rate_lookup.parse_prices("Sliding window ₹300 per sq ft, Rs. 280/sqft", "sqm") == [round(300 * 10.7639, 2), round(280 * 10.7639, 2)]
    assert rate_lookup.parse_prices("Light point Rs 650 per point; fan ₹700/point", "point") == [650.0, 700.0]
    assert rate_lookup.parse_prices("₹500 per kg", "sqm") == []
    monkeypatch.delenv("PWD_SEARCH_API_KEY", raising=False)
    assert rate_lookup.lookup("CPVC pipe", "metre")["enabled"] is False
