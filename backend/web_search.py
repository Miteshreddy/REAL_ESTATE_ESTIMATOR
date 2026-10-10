"""Web search + page reading for live price checks.

Providers (first configured one wins; keys come from the environment, never from code):
    PWD_SEARCH_API_KEY            Brave Search API
    TAVILY_API_KEY                Tavily search API
    GOOGLE_CSE_KEY + GOOGLE_CSE_CX  Google Programmable Search
    SEARXNG_URL                   self-hosted SearXNG metasearch (free, no key; JSON output must be enabled)
Search engines' HTML pages are not scraped (bot checks, terms of use). Result pages themselves are fetched — robots.txt
is honoured, size and time are capped, only http(s) public hosts are contacted.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import urllib.robotparser
from html import unescape
from urllib.parse import urlparse

import requests

TIMEOUT = 15
UA = "PWD-Estimator-price-check/1.0"
MAX_BYTES = 1_500_000


def provider() -> str | None:
    if os.environ.get("PWD_SEARCH_API_KEY"):
        return "brave"
    if os.environ.get("TAVILY_API_KEY"):
        return "tavily"
    if os.environ.get("GOOGLE_CSE_KEY") and os.environ.get("GOOGLE_CSE_CX"):
        return "google"
    if os.environ.get("SEARXNG_URL"):
        return "searxng"
    return None


def search(q: str, n: int = 10) -> list[dict]:
    """[{url, title, text}] from the configured provider; [] when none is configured."""
    p = provider()
    if p == "brave":
        r = requests.get("https://api.search.brave.com/res/v1/web/search", params=dict(q=q, count=n, country="IN"), timeout=TIMEOUT,
                         headers={"Accept": "application/json", "X-Subscription-Token": os.environ["PWD_SEARCH_API_KEY"]})
        r.raise_for_status()
        res = (r.json().get("web") or {}).get("results") or []
        return [dict(url=x.get("url"), title=x.get("title") or "",
                     text=" ".join([x.get("description") or ""] + list(x.get("extra_snippets") or []))) for x in res]
    if p == "tavily":
        r = requests.post("https://api.tavily.com/search", timeout=TIMEOUT * 2,
                          json=dict(api_key=os.environ["TAVILY_API_KEY"], query=q, max_results=n, include_raw_content=False))
        r.raise_for_status()
        return [dict(url=x.get("url"), title=x.get("title") or "", text=x.get("content") or "") for x in r.json().get("results") or []]
    if p == "google":
        r = requests.get("https://www.googleapis.com/customsearch/v1", timeout=TIMEOUT,
                         params=dict(key=os.environ["GOOGLE_CSE_KEY"], cx=os.environ["GOOGLE_CSE_CX"], q=q, num=min(n, 10), gl="in"))
        r.raise_for_status()
        return [dict(url=x.get("link"), title=x.get("title") or "", text=x.get("snippet") or "") for x in r.json().get("items") or []]
    if p == "searxng":
        r = requests.get(os.environ["SEARXNG_URL"].rstrip("/") + "/search", timeout=TIMEOUT * 2,
                         params=dict(q=q, format="json", language="en-IN", safesearch=0), headers={"User-Agent": UA})
        r.raise_for_status()
        return [dict(url=x.get("url"), title=x.get("title") or "", text=x.get("content") or "") for x in (r.json().get("results") or [])[:n]]
    return []


def _public(host: str) -> bool:
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (socket.gaierror, ValueError):
        return False


def _robots_ok(url: str) -> bool:
    u = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = requests.get(f"{u.scheme}://{u.netloc}/robots.txt", timeout=8, headers={"User-Agent": UA})
        if r.status_code >= 400:
            return True
        rp.parse(r.text.splitlines())
        return rp.can_fetch(UA, url)
    except requests.RequestException:
        return True


def page_text(url: str) -> str:
    """Visible text of a public result page ('' when not allowed or not reachable)."""
    u = urlparse(url or "")
    if u.scheme not in ("http", "https") or not u.hostname or not _public(u.hostname) or not _robots_ok(url):
        return ""
    try:
        with requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, stream=True, allow_redirects=True) as r:
            if r.status_code >= 400 or "html" not in (r.headers.get("content-type") or ""):
                return ""
            raw = r.raw.read(MAX_BYTES, decode_content=True)
    except requests.RequestException:
        return ""
    t = raw.decode("utf-8", "ignore")
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", t)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", t)))
