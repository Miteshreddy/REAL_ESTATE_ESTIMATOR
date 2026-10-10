"""Web price lookup for items without a PWD rate (suggestions only — the user decides).

Uses a web-search API (Brave Search: set env PWD_SEARCH_API_KEY). Result snippets are parsed for rupee amounts
with a unit ("₹ 300 per sq ft", "Rs. 650/point"); per-sq-ft prices are converted to per-sqm. The median plausible
value is returned with every source URL. Nothing is written to the rate database: the UI shows the suggestion and
the user applies it as an editable item rate. Without a key the endpoint reports that lookup is not configured.
"""
from __future__ import annotations

import os
import re
import statistics

import requests

API = "https://api.search.brave.com/res/v1/web/search"
TIMEOUT = 15
SQFT_PER_SQM = 10.7639
UNIT_WORDS = {
    "sqm": r"(?:sq\.?\s*m|sqm|m2|m²|square\s*met(?:er|re))", "sqft": r"(?:sq\.?\s*ft|sqft|square\s*f(?:ee|oo)t|sft)",
    "metre": r"(?:running\s*met(?:er|re)|rmt|metre|meter|\bm\b|rft)", "cum": r"(?:cum|cu\.?\s*m|m3|cubic\s*met(?:er|re))",
    "kg": r"(?:kg|kilogram)", "point": r"(?:point|pt)", "each": r"(?:each|no\.?|nos|unit|piece|pc)", "litre": r"(?:litre|liter|ltr|l\b)",
}
AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:/|per|a)?\s*([a-z.² ]{0,22})", re.I)


def configured() -> bool:
    import web_search
    return bool(web_search.provider())


def _unit_of(tail: str) -> str | None:
    t = tail.lower().strip()
    for u, rx in UNIT_WORDS.items():
        if re.match(rx, t):
            return u
    return None


def parse_prices(text: str, unit: str) -> list[float]:
    """Rupee amounts in `text` expressed in (or convertible to) `unit`."""
    want = {"m": "metre", "rm": "metre", "nos": "each", "no": "each"}.get(unit, unit)
    out = []
    for amt, tail in AMOUNT.findall(text or ""):
        try:
            v = float(amt.replace(",", ""))
        except ValueError:
            continue
        u = _unit_of(tail)
        if u == want:
            out.append(v)
        elif u == "sqft" and want == "sqm":
            out.append(round(v * SQFT_PER_SQM, 2))
    return [v for v in out if 1 <= v <= 5_000_000]


def lookup(description: str, unit: str, place: str = "Chennai") -> dict:
    if not configured():
        return dict(enabled=False, message="Web price lookup needs a search key: PWD_SEARCH_API_KEY (Brave), TAVILY_API_KEY, or GOOGLE_CSE_KEY + GOOGLE_CSE_CX.")
    q = f"{description[:90]} rate per {unit} {place} 2025"
    import web_search
    try:
        results = web_search.search(q, 10)
    except (requests.RequestException, ValueError) as e:
        return dict(enabled=True, ok=False, query=q, message=f"search failed: {str(e)[:120]}")
    found = []
    for i, res in enumerate(results):
        text = f"{res['title']} {res['text']}"
        if i < 3 and res.get("url"):  # read the top pages too, not only the snippets
            text += " " + web_search.page_text(res["url"])[:200_000]
        for v in parse_prices(text, unit):
            found.append(dict(value=v, url=res.get("url"), title=(res.get("title") or "")[:120]))
    vals = sorted(f["value"] for f in found)
    if len(vals) >= 3:  # drop outliers outside 0.5×–2× the median
        med = statistics.median(vals)
        found = [f for f in found if med / 2 <= f["value"] <= med * 2]
        vals = sorted(f["value"] for f in found)
    return dict(enabled=True, ok=bool(vals), query=q, unit=unit, suggestion=round(statistics.median(vals), 2) if vals else None,
                low=vals[0] if vals else None, high=vals[-1] if vals else None, sources=found[:8],
                note="Indicative web prices — review before applying; applied values are editable estimates.")
