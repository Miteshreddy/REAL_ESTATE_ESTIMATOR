"""HTTP fetching with robots.txt, timeouts, retries, caching, content-type / PDF validation and SHA-256."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import re
from urllib.parse import unquote, urljoin, urlparse

import requests

from .store import CACHE_DIR, DOC_DIR

UA = "TN-PWD-Estimator/1.0 (public document ingestion; contact: project administrator)"
TIMEOUT = 60
RETRIES = 3
_robots = {}


class FetchError(Exception):
    pass


def _robots_rules(base):
    """(allow, disallow) path patterns for our user agent from robots.txt; '*' and '$' wildcards supported
    (Python's urllib.robotparser ignores them, which would let '/*.pdf$' through)."""
    try:
        r = requests.get(urljoin(base, "/robots.txt"), timeout=20, headers={"User-Agent": UA})
    except requests.RequestException:
        return None  # unreachable robots.txt → do not crawl
    if r.status_code != 200 or "html" in r.headers.get("content-type", "").lower():
        return [], []
    cur = None
    allow, dis = [], []
    agents = ["*"]  # rules before any User-agent line are treated as applying to everyone (conservative)
    for line in r.text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        k = k.lower()
        if k == "user-agent":
            if cur == "rules":
                agents = []
            agents.append(v.lower())
            cur = "agents"
        elif k in ("allow", "disallow"):
            cur = "rules"
            if any(a == "*" or a in UA.lower() for a in agents) and v:
                (allow if k == "allow" else dis).append(v)
    return allow, dis


def _match(pattern, path):
    rx = "^" + re.escape(pattern).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    return re.match(rx, path) is not None


def allowed(url: str) -> bool:
    """robots.txt check (longest match wins, Allow beats Disallow on ties). Missing robots.txt = no restriction;
    an unreachable one blocks the fetch."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        _robots[base] = _robots_rules(base)
    rules = _robots[base]
    if rules is None:
        return False
    path = unquote(p.path or "/") + (("?" + p.query) if p.query else "")
    best = (-1, True)
    for pat in rules[1]:
        if _match(pat, path) and len(pat) > best[0]:
            best = (len(pat), False)
    for pat in rules[0]:
        if _match(pat, path) and len(pat) >= best[0]:
            best = (len(pat), True)
    return best[1]


def _get(url, **kw):
    last = None
    for i in range(RETRIES):
        try:
            return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, **kw)
        except requests.exceptions.SSLError as e:
            last = e
            break  # some government / association hosts reject Python's TLS stack → curl fallback below
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise FetchError(str(last))


def get_text(url: str) -> str:
    if not allowed(url):
        raise FetchError(f"robots.txt disallows {url}")
    r = _get(url)
    if r.status_code != 200:
        raise FetchError(f"HTTP {r.status_code} for {url}")
    return r.text


def head(url: str) -> dict:
    try:
        r = requests.head(url, timeout=30, headers={"User-Agent": UA}, allow_redirects=True)
        return dict(status=r.status_code, content_type=r.headers.get("content-type"), last_modified=r.headers.get("last-modified"),
                    length=int(r.headers.get("content-length") or 0) or None)
    except requests.RequestException as e:
        return dict(status=None, error=str(e))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def download_pdf(url: str) -> dict:
    """Download to the cache, validate it is a real PDF, store it under its SHA-256. Returns {sha256, path, bytes}."""
    if not allowed(url):
        raise FetchError(f"robots.txt disallows {url}")
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(DOC_DIR, exist_ok=True)
    tmp = os.path.join(CACHE_DIR, hashlib.md5(url.encode()).hexdigest() + ".part")
    try:
        r = _get(url, stream=True)
        if r.status_code != 200:
            raise FetchError(f"HTTP {r.status_code}")
        ct = r.headers.get("content-type", "")
        if "html" in ct:
            raise FetchError(f"not a document (content-type {ct}) — possibly a login or error page")
        with open(tmp, "wb") as f:
            for b in r.iter_content(1 << 16):
                f.write(b)
    except FetchError as e:
        if "SSL" not in str(e) and "HTTP" in str(e):
            raise
        if not shutil.which("curl"):
            raise
        subprocess.run(["curl", "-s", "-f", "-L", "-m", "300", "-A", UA, "-o", tmp, url], check=True)
    with open(tmp, "rb") as f:
        if f.read(5) != b"%PDF-":
            os.remove(tmp)
            raise FetchError("downloaded file is not a PDF")
    sha = sha256_file(tmp)
    dst = os.path.join(DOC_DIR, sha + ".pdf")
    if os.path.exists(dst):
        os.remove(tmp)  # duplicate of a file we already hold
    else:
        os.replace(tmp, dst)
    return dict(sha256=sha, path=dst, bytes=os.path.getsize(dst))
