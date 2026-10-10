"""Public-page discovery of drawing / BOQ documents. Every candidate is checked against robots.txt and the licence
rules; disallowed sources are recorded (so the gap is visible) but never fetched."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from . import downloader, license_check
from .source_registry import SOURCES

DOC = re.compile(r'href="([^"]+\.(?:pdf|dwg|dxf|png|jpe?g))"', re.I)


def discover(pages: list[str] | None = None) -> list[dict]:
    found = []
    for src in SOURCES:
        if not src["url"]:
            continue
        for page in (pages or [src["url"]]):
            ok = downloader.allowed(page)
            if not ok:
                found.append(dict(source=src["id"], url=page, status="disallowed by robots.txt"))
                continue
            try:
                html = downloader.get_text(page)
            except downloader.FetchError as e:
                found.append(dict(source=src["id"], url=page, status=f"fetch failed: {e}"))
                continue
            for href in DOC.findall(html):
                u = urljoin(page, href)
                rb = downloader.allowed(u)
                found.append(dict(source=src["id"], url=u, robots_allowed=rb,
                                  licence=license_check.status(src["id"], u, rb), status="candidate" if rb else "disallowed by robots.txt"))
    return found
