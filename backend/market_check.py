"""Live market reality check: current ₹/sq ft construction cost for a building type, read from the web.

Searches (web_search provider), reads result snippets and the result pages, extracts '₹ 2,200 per sq ft' and
'₹2,000 – ₹2,800 per sq ft' figures, drops implausible values and outliers, and compares the median with the project's
estimated cost per sq ft. Advisory only: it never changes quantities or PWD rates — the user decides. Results are
cached for 7 days per (building type, place).
"""
from __future__ import annotations

import json
import os
import re
import statistics
import time

import web_search

PER_SQFT = r"(?:/|per|a)?\s*(?:sq\.?\s*ft|sqft|square\s*f(?:ee|oo)t|sft)"
PER_SQM = r"(?:/|per|a)?\s*(?:sq\.?\s*m\b|sqm|m2|m²|square\s*met(?:er|re))"
RS = r"(?:₹|rs\.?|inr)\s*"
NUM = r"([\d,]+(?:\.\d+)?)"
RANGE = re.compile(rf"{RS}{NUM}\s*(?:-|–|to)\s*(?:{RS})?{NUM}\s*({PER_SQFT}|{PER_SQM})", re.I)
SINGLE = re.compile(rf"{RS}{NUM}\s*({PER_SQFT}|{PER_SQM})", re.I)
LO, HI = 600.0, 25000.0          # plausible ₹ / sq ft for building construction
CACHE_DAYS = 7


def _per_sqm(unit: str) -> bool:
    return not re.search(r"ft|feet|foot", unit, re.I)


def _val(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse_rates(text: str) -> list[float]:
    """₹ per sq ft figures in text (per-m² converted; a range contributes its midpoint)."""
    out, spans = [], []
    for m in RANGE.finditer(text or ""):
        a, b = _val(m.group(1)), _val(m.group(2))
        if a and b:
            v = (a + b) / 2
            out.append(v / 10.7639 if _per_sqm(m.group(3)) else v)
            spans.append(m.span())
    for m in SINGLE.finditer(text or ""):
        if any(s <= m.start() < e for s, e in spans):
            continue
        v = _val(m.group(1))
        if v:
            out.append(v / 10.7639 if _per_sqm(m.group(2)) else v)
    return [round(v, 1) for v in out if LO <= v <= HI]


NOT_BUILD = re.compile(r"\b(plot|land|site value|guideline value|rent|rental|lease|resale|flat price|apartment price|property price|per month|registration)\b", re.I)
BUILD = re.compile(r"construct|build|civil work|house cost|turnkey", re.I)


def _sentence(text: str, a: int, b: int) -> str:
    """The sentence holding text[a:b] (a full stop counts only when followed by a space and not part of 'Rs.')."""
    stops = [m.end() for m in re.finditer(r"(?<!Rs)(?<!rs)[.!?;|]\s", text[max(0, a - 160):a])]
    start = max(0, a - 160) + (stops[-1] if stops else 0)
    m2 = re.search(r"[.!?;|]\s", text[b:b + 120])
    return text[start: b + (m2.start() if m2 else 120)]


def parse_rates_ctx(text: str) -> list[dict]:
    """parse_rates with provenance: each figure keeps its quote; figures in land / rent / resale context, or with no
    construction wording nearby, are returned as rejected with the reason."""
    out = []
    for rx, is_range in ((RANGE, True), (SINGLE, False)):
        for m in rx.finditer(text or ""):
            if not is_range and any(o["span"][0] <= m.start() < o["span"][1] for o in out):
                continue
            a = _val(m.group(1))
            b = _val(m.group(2)) if is_range else None
            unit = m.group(3) if is_range else m.group(2)
            if not a or (is_range and not b):
                continue
            v = (a + b) / 2 if is_range else a
            v = v / 10.7639 if _per_sqm(unit) else v
            ctx = _sentence(text, m.start(), m.end())
            why = None
            if not (LO <= v <= HI):
                why = "outside plausible building cost per sq ft"
            elif NOT_BUILD.search(ctx):
                why = f"land / rent / property-price context ('{NOT_BUILD.search(ctx).group(0)}')"
            elif not BUILD.search(text[max(0, m.start() - 400): m.end() + 200]):
                why = "no construction context near the figure"
            out.append(dict(value=round(v, 1), quote=re.sub(r"\s+", " ", text[max(0, m.start() - 60): m.end() + 10]).strip(),
                            span=m.span(), rejected=why))
    return out


def _cache_path():
    d = os.environ.get("EST_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    return os.path.join(d, "market_cache.json")


ALIASES = {"tiruchirappalli": ["trichy", "tiruchirappalli"], "thoothukudi": ["tuticorin", "thoothukudi"], "kanniyakumari": ["nagercoil"],
           "chennai": ["chennai"], "madurai": ["madurai"], "coimbatore": ["coimbatore"], "salem": ["salem"], "tirunelveli": ["tirunelveli"],
           "vellore": ["vellore"], "erode": ["erode"], "thanjavur": ["thanjavur"], "tiruppur": ["tiruppur"]}
OFFICIAL_GROUPS = {"school": ("school", "college"), "office": ("office", "government"), "community": ("community", "public", "hall", "hostel"),
                   "commercial": ("commercial", "shop", "market")}
ROOT_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _slugs(place: str) -> list[str]:
    d = re.sub(r"[^a-z ]", "", (place or "").lower().replace("tamil nadu", "")).strip().split(" ")[0]
    return ALIASES.get(d, [d]) if d else []


LLM_PAGES = 3  # the local model reads at most this many pages per check (~40 s each on an 8 GB GPU); the rest use the parser


def _figures(text: str, use_llm: bool = True, slugs: list[str] | None = None) -> tuple[list[dict], str]:
    """Standard-quality figures from a page: local Meta Llama 3.1 (quote-checked) when running, else the regex parser."""
    import local_llm
    g = local_llm.extract_rates(text) if text and use_llm else None
    if g:
        figs = []
        for f in g:
            why = None
            city = str(f.get("city") or "").lower()
            if not (LO <= f["value"] <= HI):
                why = "outside plausible building cost per sq ft"
            elif slugs and city and not any(x in city or city in x for x in slugs + ["tamil", "india"]):
                why = f"price is for another place ({f.get('city')})"
            elif NOT_BUILD.search(f["quote"]):
                why = "land / rent / property-price context"
            elif f["quality"] not in ("standard", "unknown"):
                why = f"{f['quality']} quality tier (kept for reference, not in the standard median)"
            figs.append(dict(value=f["value"], quote=f["quote"], quality=f["quality"], location=f.get("city"), rejected=why))
        if any(not x["rejected"] for x in figs):
            return figs, f"{local_llm.model()} (local, {local_llm.LOADED_ON or 'CPU'})"
    figs = parse_rates_ctx(text)
    for x in figs:
        x.pop("span", None)
        x["quality"] = "unknown"
    return figs, "rule-based parser"


def official(building_type: str) -> dict | None:
    """Official TN government unit costs for the matching building group (with their year — never escalated silently)."""
    try:
        T = json.load(open(os.path.join(ROOT_DATA, "tnpwd", "maps", "official_unit_costs.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    bt = (building_type or "").lower()
    grp = next((g for g, words in OFFICIAL_GROUPS.items() if any(w in bt for w in words)), None)
    if not grp:
        return None
    rows = [r for r in T["rows"] if r["group"] == grp]
    vals = sorted(r["rate_per_sqft"] for r in rows)
    return dict(source=T["source"], year=T["year"], group=grp, n=len(rows), median=round(statistics.median(vals)), low=vals[0], high=vals[-1],
                rows=[dict(building=r["building"], rate=r["rate_per_sqft"]) for r in rows])


def _record(f: dict, url: str | None, title: str, found_via: str, read_by: str) -> dict:
    """One web price with full provenance. Web prices are indicative market ranges, never PWD rates."""
    return dict(value=f["value"], unit="INR per sq ft (built-up, construction only)", url=url, title=title,
                retrieved=time.strftime("%Y-%m-%d"), quote=f.get("quote"), location=f.get("location"), quality=f.get("quality", "unknown"),
                price_type="indicative market range", found_via=found_via, read_by=read_by, rejected=f.get("rejected"),
                status="rejected" if f.get("rejected") else "unreviewed")


_JOBS, _JOBS_LOCK = {}, __import__("threading").Lock()


def cached(building_type: str, place: str) -> dict | None:
    """A fresh cached result, or None — never searches (cheap; safe inside a request)."""
    key = f"{(building_type or 'building').strip().lower()}|{place.lower()}"
    try:
        hit = json.load(open(_cache_path(), encoding="utf-8")).get(key)
    except (OSError, ValueError):
        hit = None
    if hit and time.time() - hit.get("at", 0) < CACHE_DAYS * 86400:
        return dict(hit["data"], cached=True)
    job = _JOBS.get(key)
    if job and job.get("done") and time.time() - job["at"] < 600:  # a recent unsuccessful check: do not repeat at once
        return job["data"]
    return None


def start(building_type: str, place: str, refresh: bool = False) -> None:
    """Run benchmark() in a background thread (reading pages with the local model can take minutes on a CPU)."""
    key = f"{(building_type or 'building').strip().lower()}|{place.lower()}"
    with _JOBS_LOCK:
        j = _JOBS.get(key)
        if j and not j.get("done"):
            return
        _JOBS[key] = dict(done=False, at=time.time())

    def run():
        try:
            data = benchmark(building_type, place, use_cache=not refresh)
        except Exception as e:  # reported to the page, never raised
            data = dict(enabled=True, ok=False, message=f"market check failed: {str(e)[:150]}")
        _JOBS[key] = dict(done=True, at=time.time(), data=data)

    __import__("threading").Thread(target=run, daemon=True).start()


def benchmark(building_type: str, place: str = "Tamil Nadu", read_pages: int = 4, use_cache: bool = True) -> dict:
    """Market ₹/sq ft from (1) the curated public price pages read directly, (2) SearXNG web search, each page read by
    Gemma 3 (quote-checked) or the rule-based parser; plus (3) the official TN unit costs as historical context."""
    bt = (building_type or "building").strip()
    key = f"{bt.lower()}|{place.lower()}"
    cp = _cache_path()
    cache = {}
    try:
        cache = json.load(open(cp, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    hit = cache.get(key)
    if use_cache and hit and time.time() - hit.get("at", 0) < CACHE_DAYS * 86400:
        return dict(hit["data"], cached=True)
    found, tried, methods = [], [], set()
    budget = [LLM_PAGES]

    def figures(text):
        vals, how = _figures(text, budget[0] > 0, slugs)
        if how != "rule-based parser":
            budget[0] -= 1
        return vals, how
    # (1) curated public pages — no API needed
    try:
        S = json.load(open(os.path.join(ROOT_DATA, "market_sources.json"), encoding="utf-8"))["sources"]
    except (OSError, ValueError, KeyError):
        S = []
    slugs = _slugs(place)
    urls = []
    for src in S:
        if "{city}" in src["url"]:
            urls += [(src["name"], src["url"].format(city=c)) for c in slugs]
        elif not src.get("city") or src["city"] in slugs:
            urls.append((src["name"], src["url"]))
    for name, u in urls:
        t = web_search.page_text(u)
        tried.append(u)
        if not t:
            continue
        vals, how = figures(t)
        methods.add(how)
        found += [_record(f, u, name, "curated price page", how) for f in vals[:10]]
    # (2) web search (SearXNG), when running
    year = time.strftime("%Y")
    q = f"{bt} construction cost per sq ft {place} {year}"
    search_note = None
    if web_search.provider():
        try:
            results = web_search.search(q, 10)
        except Exception as e:  # network / quota — reported, never hidden
            results, search_note = [], f"search failed: {str(e)[:150]}"
        for i, r in enumerate(results):
            if r.get("url") in tried:
                continue
            vals = [dict(f, quality="unknown") for f in parse_rates_ctx(f"{r['title']} {r['text']}")]
            for f in vals:
                f.pop("span", None)
            how = "rule-based parser (search snippet)"
            if i < read_pages and r.get("url"):
                pv, how = figures(web_search.page_text(r["url"]))
                methods.add(how)
                vals += pv[:8]
            found += [_record(f, r.get("url"), (r.get("title") or "")[:120], "web search result", how) for f in vals]
    else:
        search_note = "web search (SearXNG) not running — curated price pages only"
    ok_ = [f for f in found if not f["rejected"]]
    if len(ok_) >= 3:  # outliers vs the median of accepted figures are rejected, with the reason kept
        med = statistics.median(f["value"] for f in ok_)
        for f in ok_:
            if not (med / 2 <= f["value"] <= med * 2):
                f["rejected"] = f"outlier (more than 2× from the median ₹{med:,.0f})"
                f["status"] = "rejected"
    accepted = [f for f in found if not f["rejected"]]
    vals = sorted(f["value"] for f in accepted)
    residential = bool(re.search(r"house|villa|residential|apartment", bt, re.I))
    data = dict(enabled=True, ok=len(vals) >= 2, query=q, building_type=bt, place=place, n=len(vals),
                median=round(statistics.median(vals)) if vals else None, low=round(vals[0]) if vals else None,
                high=round(vals[-1]) if vals else None, sources=accepted[:15], rejected=[f for f in found if f["rejected"]][:20],
                checked=time.strftime("%Y-%m-%d"),
                read_by=sorted(methods), search_note=search_note, official=official(bt),
                note=("Private-market figures for houses, standard quality, excluding land. Indicative only; PWD rates are unchanged."
                      + ("" if residential else " The curated pages describe residential buildings — treat them as a floor for this building type.")),
                message=None if vals else "No market figures found for this place." + (f" {search_note}." if search_note else ""))
    if data["ok"]:
        cache[key] = dict(at=time.time(), data=data)
        try:
            json.dump(cache, open(cp, "w", encoding="utf-8"))
        except OSError:
            pass
    return data


def verdict(est_per_sqft: float | None, bm: dict) -> dict:
    if not bm.get("ok") or not est_per_sqft:
        return dict(level="none", text="No comparison available.")
    r = est_per_sqft / bm["median"]
    if r > 1.33:
        lvl, t = "high", f"Our estimate (₹{est_per_sqft:,.0f}/sq ft) is {r:.1f}× the market median — check assumed items (structure, finishes, services)."
    elif r < 0.75:
        lvl, t = "low", f"Our estimate (₹{est_per_sqft:,.0f}/sq ft) is only {r:.0%} of the market median (₹{bm['median']:,}/sq ft) — work may be missing (floors, services, unresolved lines)."
    else:
        lvl, t = "ok", f"Our estimate (₹{est_per_sqft:,.0f}/sq ft) is within ±33% of the market median (₹{bm['median']:,}/sq ft, ratio {r:.2f})."
    return dict(level=lvl, ratio=round(r, 2), text=t)
