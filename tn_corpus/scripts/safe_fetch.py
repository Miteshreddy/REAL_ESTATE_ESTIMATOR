"""Governed HTTP fetching for the TN drawing corpus.

Host allowlist, SSRF guard (public IPs only, http/https only), robots.txt (wildcards, rules before any User-agent apply
to everyone), modest delay per host, timeouts, response-size cap, MIME + magic-byte validation, retry-safe, kill switch
(file `tn_corpus/STOP_CRAWL`), and an append-only allow/deny decision log. Never handles credentials, CAPTCHA or logins.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin, urlparse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "logs", "fetch_decisions.jsonl")
KILL = os.path.join(ROOT, "STOP_CRAWL")
UA = "TN-Drawing-Corpus-Builder/1.0 (research dataset; respects robots.txt; low rate)"
ALLOW_HOSTS = {"tnrd.tn.gov.in", "www.tnrd.tn.gov.in", "tnhsp.org", "www.tnhsp.org", "openjicareport.jica.go.jp",
               "tntenders.gov.in", "tnpwdea.org", "www.tnpwdea.org", "rera.tn.gov.in", "www.rera.tn.gov.in"}
DELAY_S = 3.0
TIMEOUT = 45
MAX_BYTES = 80 * 1024 * 1024
MAGIC = {"pdf": b"%PDF-", "png": b"\x89PNG", "jpg": b"\xff\xd8\xff"}
_last, _robots = {}, {}


class Blocked(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(decision, url, reason, **kw):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(at=now(), decision=decision, url=url, reason=reason, **kw), ensure_ascii=False) + "\n")


def ssrf_ok(url: str) -> tuple[bool, str]:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False, f"scheme {p.scheme!r} not allowed"
    host = (p.hostname or "").lower()
    if host not in ALLOW_HOSTS:
        return False, f"host {host!r} not on allowlist"
    try:
        ips = {ai[4][0] for ai in socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80))}
    except socket.gaierror as e:
        return False, f"DNS failure: {e}"
    for ip in ips:
        a = ipaddress.ip_address(ip)
        if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast:
            return False, f"host resolves to non-public address {ip}"
    return True, "ok"


def _rules(base):
    try:
        r = requests.get(urljoin(base, "/robots.txt"), timeout=20, headers={"User-Agent": UA})
    except requests.RequestException:
        return None
    if r.status_code >= 400 or "html" in r.headers.get("content-type", "").lower():
        return [], []
    allow, dis, agents, cur = [], [], ["*"], None
    for line in r.text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if cur == "rules":
                agents = []
            agents.append(v.lower())
            cur = "agents"
        elif k in ("allow", "disallow"):
            cur = "rules"
            if v and any(a == "*" or a in UA.lower() for a in agents):
                (allow if k == "allow" else dis).append(v)
    return allow, dis


def _m(pat, path):
    rx = "^" + re.escape(pat).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    return re.match(rx, path) is not None


def robots_allowed(url: str) -> bool:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        _robots[base] = _rules(base)
    rules = _robots[base]
    if rules is None:
        return False
    path = unquote(p.path or "/") + (("?" + p.query) if p.query else "")
    best = (-1, True)
    for pat in rules[1]:
        if _m(pat, path) and len(pat) > best[0]:
            best = (len(pat), False)
    for pat in rules[0]:
        if _m(pat, path) and len(pat) >= best[0]:
            best = (len(pat), True)
    return best[1]


def check(url: str) -> None:
    if os.path.exists(KILL):
        log("deny", url, "kill switch STOP_CRAWL present")
        raise Blocked("kill switch")
    ok, why = ssrf_ok(url)
    if not ok:
        log("deny", url, why)
        raise Blocked(why)
    if not robots_allowed(url):
        log("deny", url, "robots.txt disallows")
        raise Blocked("robots.txt disallows")


def get(url: str, expect: str | None = None, retries=3) -> dict:
    """GET with all guards. expect='pdf' validates MIME/magic. Returns dict(status, final_url, content_type, body, sha256)."""
    check(url)
    host = urlparse(url).hostname
    last = None
    for i in range(retries):
        wait = DELAY_S - (time.time() - _last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()
        try:
            r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, stream=True, allow_redirects=True)
            final = r.url
            if final != url:
                ok, why = ssrf_ok(final)
                if not ok:
                    log("deny", url, f"redirect to {final}: {why}")
                    raise Blocked(why)
            buf = bytearray()
            for chunk in r.iter_content(65536):
                buf += chunk
                if len(buf) > MAX_BYTES:
                    log("deny", url, f"response exceeds {MAX_BYTES} bytes")
                    raise Blocked("too large")
            body = bytes(buf)
            ct = r.headers.get("content-type", "")
            if r.status_code in (401, 403, 429) or "captcha" in body[:20000].decode("latin1").lower():
                log("deny", url, f"access restricted (HTTP {r.status_code} / challenge) — not bypassed", status=r.status_code)
                raise Blocked(f"HTTP {r.status_code}")
            if r.status_code >= 500:
                raise requests.RequestException(f"HTTP {r.status_code}")
            if expect and r.status_code == 200 and not body.startswith(MAGIC[expect]):
                log("deny", url, f"magic bytes are not {expect} (content-type {ct})", status=r.status_code)
                raise Blocked("bad magic")
            log("allow", url, "fetched", status=r.status_code, bytes=len(body), final_url=final, content_type=ct)
            return dict(status=r.status_code, final_url=final, content_type=ct, body=body, sha256=hashlib.sha256(body).hexdigest(),
                        last_modified=r.headers.get("last-modified"), etag=r.headers.get("etag"))
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    log("error", url, f"failed after {retries} tries: {last}")
    raise Blocked(f"network: {last}")
