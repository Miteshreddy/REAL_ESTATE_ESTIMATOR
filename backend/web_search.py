"""Web search + page reading for live price checks.

Search: self-hosted SearXNG (open-source metasearch, free, no key) at SEARXNG_URL, installed by the start scripts.
Search engines' own HTML pages are never scraped (bot checks, terms of use). Result pages themselves are fetched —
robots.txt is honoured, size and time are capped, only public http(s) hosts are contacted.
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
    return "searxng" if os.environ.get("SEARXNG_URL") else None


def search(q: str, n: int = 10) -> list[dict]:
    """[{url, title, text}] from SearXNG; [] when it is not configured. Raises on network errors (callers report them)."""
    if not provider():
        return []
    r = requests.get(os.environ["SEARXNG_URL"].rstrip("/") + "/search", timeout=TIMEOUT * 2,
                     params=dict(q=q, format="json", language="en-IN", safesearch=0), headers={"User-Agent": UA})
    r.raise_for_status()
    return [dict(url=x.get("url"), title=x.get("title") or "", text=x.get("content") or "") for x in (r.json().get("results") or [])[:n]]


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
