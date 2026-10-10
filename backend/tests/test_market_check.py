"""Live market check: price parsing, verdict, no-key behaviour, endpoint wiring (search mocked — no network in tests)."""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("EST_DATA_DIR", tempfile.mkdtemp(prefix="mkt_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import market_check  # noqa: E402
import web_search  # noqa: E402


def test_parse_rates_ranges_units_and_bounds():
    t = "Hospital cost ₹2,500 - ₹3,500 per sq ft; basic ₹1,800/sq.ft; Rs. 25000 per sqm; paint ₹ 40 per sq ft"
    assert market_check.parse_rates(t) == [3000.0, 1800.0, 2322.6]


def test_verdict_levels():
    bm = dict(ok=True, median=2500)
    assert market_check.verdict(2600, bm)["level"] == "ok"
    assert market_check.verdict(5000, bm)["level"] == "high"
    assert market_check.verdict(1000, bm)["level"] == "low"
    assert market_check.verdict(None, bm)["level"] == "none"


def test_without_search_provider_curated_pages_still_work(monkeypatch):
    for k in ("PWD_SEARCH_API_KEY", "TAVILY_API_KEY", "GOOGLE_CSE_KEY", "GOOGLE_CSE_CX", "SEARXNG_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(web_search, "page_text", lambda url: "House construction cost in Trichy is ₹2,300 per sq ft. "
                                                             "Standard house construction ₹2,100 - ₹2,500 per sq ft.")
    r = market_check.benchmark("Residential house", "Tiruchirappalli Tamil Nadu", use_cache=False)
    assert r["enabled"] and r["ok"] and r["median"] == 2300 and "not configured" in r["search_note"]


def test_benchmark_with_mocked_search(monkeypatch):
    monkeypatch.setattr(web_search, "provider", lambda: "brave")
    monkeypatch.setattr(web_search, "page_text", lambda url: "")
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(market_check, "ROOT_DATA", os.environ["EST_DATA_DIR"])  # no curated pages in this test
    monkeypatch.setattr(web_search, "search", lambda q, n=10: [
        dict(url="https://a.example/1", title="Hospital cost", text="Hospital construction cost ₹2,400 per sq ft"),
        dict(url="https://a.example/2", title="Build cost", text="Building construction cost ₹2,800 per sq ft"),
        dict(url="https://a.example/3", title="Outlier", text="Construction cost ₹19,000 per sq ft"),
    ])
    r = market_check.benchmark("Hospital", "Chennai Tamil Nadu", use_cache=False)
    assert r["ok"] and r["median"] == 2600 and r["n"] == 2 and "Hospital" in r["query"]
    assert r["rejected"] and "outlier" in r["rejected"][0]["rejected"]
    assert all(x["url"] and x["retrieved"] and x["quote"] for x in r["sources"])


def test_endpoint_wiring(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    monkeypatch.setattr(market_check, "benchmark", lambda bt, place, use_cache=True: dict(enabled=True, ok=True, median=2500, building_type=bt, place=place))
    with TestClient(app.app) as c:
        p = c.post("/api/projects", data={"name": "mkt", "building_type": "Hospital / health centre", "loc": '{"district":"Chennai"}'}).json()
        r = c.get(f"/api/projects/{p['id']}/market-check").json()
    assert r["benchmark"]["building_type"] == "Hospital / health centre"
    assert "Chennai" in r["benchmark"]["place"]


def test_page_text_refuses_private_hosts():
    assert web_search.page_text("http://127.0.0.1/secret") == ""
    assert web_search.page_text("file:///etc/passwd") == ""
