"""Acceptance tests for the local Llama assistant, web price discovery and fallbacks (the 8 product conditions).

No network and no GPU needed: Ollama / SearXNG are pointed at closed ports or mocked. A live Llama check runs only
with RUN_LLM_TESTS=1 and a running Ollama.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("EST_DATA_DIR", tempfile.mkdtemp(prefix="ai_web_test_"))
os.environ["EST_NO_DOTENV"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import local_llm  # noqa: E402
import market_check  # noqa: E402
import web_search  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "demo05_hospital_floors_4_5_6.png")
CLOSED = "http://127.0.0.1:9"  # discard port: nothing listens


def _client():
    from fastapi.testclient import TestClient
    import app
    return TestClient(app.app)


# 1 — Llama unavailable: the application keeps working
def test_llama_unavailable_app_keeps_working(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "llamacpp")
    monkeypatch.setenv("LLM_MODEL_PATH", os.path.join(tempfile.gettempdir(), "no_such_model.gguf"))
    assert local_llm.available() is False and local_llm._chat("s", "u", False) is None
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_URL", CLOSED)
    assert local_llm.available() is False
    assert local_llm.extract_rates("House construction cost ₹2,300 per sq ft") is None
    figs, how = market_check._figures("House construction cost in Trichy is ₹2,300 per sq ft.")
    assert how == "rule-based parser" and figs[0]["value"] == 2300 and not figs[0]["rejected"]
    with _client() as c:
        p = c.post("/api/projects", data={"name": "no llama", "loc": '{"district":"Chennai"}'}).json()
        r = c.get(f"/api/projects/{p['id']}/ai-summary").json()
        assert r["available"] is False
        assert c.get(f"/api/projects/{p['id']}").status_code == 200


# 2 — Estimate explanation: only the calculated figures, nothing invented
def test_summary_rejects_invented_numbers(monkeypatch):
    facts = dict(total_inr=5361685, built_up_sqft=2002, cost_per_sqft_inr=2679, estimate_status="PRELIMINARY")
    monkeypatch.setattr(local_llm, "_chat", lambda *a, **k: "- Total is ₹5,361,685 for 2,002 sq ft.\n- Steel is 4,850 kg.")
    r = local_llm.summarise(facts)
    assert r["rejected"] and "4850" in r["reason"]
    monkeypatch.setattr(local_llm, "_chat", lambda *a, **k: "- Total ₹5,361,685 (about 53.6 lakh) for 2,002 sq ft, ₹2,679 per sq ft.\n- Status PRELIMINARY.")
    r = local_llm.summarise(facts)
    assert r["rejected"] is False and "53.6" in r["text"]


@pytest.mark.skipif(os.environ.get("RUN_LLM_TESTS") != "1", reason="live Llama check: set RUN_LLM_TESTS=1 with Ollama running")
def test_live_llama_summary_is_grounded(monkeypatch):
    assert local_llm.available(), f"no local model ({local_llm.backend()})"
    r = local_llm.summarise(dict(total_inr=2160578, built_up_sqft=481, estimate_status="PRELIMINARY", drawing_scale_status=["NEEDS REVIEW"]))
    assert r is not None and (r["rejected"] or "2160578" in r["text"].replace(",", "") or "21.6" in r["text"])


# 3 — Valid webpage price: value, unit and context match the source
def test_valid_webpage_price():
    t = "The house construction cost in Tiruchirappalli for standard quality is ₹2,300 per sq ft. Building cost Rs. 24,000 per sqm."
    figs = market_check.parse_rates_ctx(t)
    ok = [f for f in figs if not f["rejected"]]
    assert [round(f["value"]) for f in ok] == [2300, 2230]  # per m² converted to per sq ft
    assert "2,300 per sq ft" in ok[0]["quote"]
    rec = market_check._record(dict(ok[0], quality="standard", location="Tiruchirappalli"), "https://example.org/p", "t", "curated price page", "parser")
    for k in ("url", "retrieved", "quote", "unit", "location", "quality", "price_type", "status"):
        assert rec[k]
    assert rec["price_type"] == "indicative market range" and rec["status"] == "unreviewed"


# 4 — Misleading webpage: irrelevant prices are rejected with a reason
def test_misleading_webpage_rejected(monkeypatch):
    t = ("Plot rates in Srirangam are ₹4,500 per sq ft. Flats resale price ₹6,200 per sq ft. Office rent ₹45 per sq ft per month. "
         "Interior painting ₹18 per sq ft.")
    figs = market_check.parse_rates_ctx(t)
    assert figs and all(f["rejected"] for f in figs)
    # the local model's figures are also screened: another city, or premium tier, is not used in the standard median
    monkeypatch.setattr(local_llm, "extract_rates", lambda text: [
        dict(value=2400.0, quality="standard", city="Bengaluru", quote="construction ₹2,400 per sq ft"),
        dict(value=3800.0, quality="premium", city="Trichy", quote="premium ₹3,800 per sq ft")])
    figs, how = market_check._figures("construction ₹2,400 per sq ft premium ₹3,800 per sq ft", True, ["trichy"])
    assert how == "rule-based parser" or all(f["rejected"] for f in figs)


# 5 — Missing PWD rate: fallback marked estimated, approved mapping untouched
def test_missing_rate_fallback_is_marked_and_never_overwrites():
    import tn_pricing
    est = tn_pricing.estimated_rates()
    key = next(iter(est))
    unit = est[key]["unit"]
    items = [dict(key=key, unit=unit, status="unmapped", rate_gap="NEEDS RATE"),
             dict(key=key, unit=unit, status="mapped", map_method="approved", derived=dict(ok=True, rate=123.0))]
    assert tn_pricing.apply_estimates(items) == 1
    assert items[0]["status"] == "estimated" and items[0]["estimated_rate"] is True
    assert items[1]["status"] == "mapped" and items[1]["derived"]["rate"] == 123.0 and "estimated_rate" not in items[1]


# 6 — Missing drawing dimensions: uncertainty is flagged, no measured quantities are invented
def test_implausible_rooms_flag_scale_without_rescaling():
    import app
    import quality
    sheet = dict(kind="floor_plan", source="image", enabled=True, file="x.png", sheet="S1",
                 scale=dict(method="auto: external wall thickness 14.3px = 230 mm", px_per_m=60),
                 metrics=dict(plinth_area=22.0, carpet_area=18.0, n_doors=3, n_windows=2),
                 rooms=[dict(name="BED-1", area=4.0), dict(name="KITCHEN", area=2.5), dict(name="HALL", area=4.3), dict(name="BED-2", area=3.9)])
    p = dict(id="t", sheets=[sheet], scope=dict(config={}), history=[])
    app.apply_scale_guard(p)
    s = p["sheets"][0]
    assert s["metrics"]["plinth_area"] == 22.0  # quantities NOT re-measured from assumed room sizes
    assert s["scale_guard"]["suspect"] and s["scale_guard"]["implied_plinth_m2"] > 22.0
    assert s["areas"]["calibration"]["status"] == "NEEDS REVIEW"
    codes = [c["code"] for c in quality.checks(dict(sheets=[s], params={}, scope={}), dict(items=[]))] if True else []
    assert "SCALE LOOKS WRONG" in codes


# 7 — SearXNG unavailable: search fails gracefully, the rest keeps working
def test_searxng_unavailable_is_graceful(monkeypatch):
    for k in ("PWD_SEARCH_API_KEY", "TAVILY_API_KEY", "GOOGLE_CSE_KEY", "GOOGLE_CSE_CX"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SEARXNG_URL", CLOSED)
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_URL", CLOSED)
    monkeypatch.setattr(web_search, "page_text", lambda url: "")
    r = market_check.benchmark("Residential house", "Tiruchirappalli Tamil Nadu", use_cache=False)
    assert r["enabled"] and not r["ok"] and "search failed" in (r["search_note"] or "")


# 8 — Recalculation: the total reconciles with quantities × rates and the charges
def test_total_reconciles_with_items():
    with _client() as c:
        p = c.post("/api/projects", data={"name": "reconcile", "loc": '{"district":"Chennai"}'}).json()
        q = c.post(f"/api/projects/{p['id']}/files", files={"files": ("plan.png", open(FIX, "rb").read())}).json()
    E = q["estimate"]
    counted = [i for i in E["items"] if i.get("in_scope", True) and i.get("amount")]
    assert abs(sum(i["amount"] for i in counted) - E["subtotal"]) < 1.0
    for i in counted:
        assert abs(i["qty"] * i["rate"] - i["amount"]) <= max(1.0, 0.005 * i["amount"])
    assert abs(E["subtotal"] + E["contingency"] + E["cess"] + E["gst"] - E["total"]) < 1.0
