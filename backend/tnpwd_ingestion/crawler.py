"""Discover TN PWD documents on the registered discovery pages (public pages only)."""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin

from . import downloader
from .document_classifier import classify_title
from .source_registry import DISCOVERY_PAGES, host_kind
from .store import log, now


def parse_table_page(page_url: str, text: str) -> list[dict]:
    out = []
    for row in re.findall(r"<tr.*?</tr>", text, re.S | re.I):
        links = re.findall(r'href="([^"]+\.pdf)"', row, re.I)
        if not links:
            continue
        cells = [html.unescape(re.sub(r"<[^>]+>|\s+", " ", c)).strip() for c in re.findall(r"<td.*?</td>", row, re.S | re.I)]
        cells = [c for c in cells if c and c.lower() != "download" and not c.isdigit()]
        title = cells[0] if cells else ""
        desc = cells[1] if len(cells) > 1 else title
        for l in links:
            out.append(dict(url=urljoin(page_url, l), title=title, description=desc, discovery_page=page_url))
    return out


def discover(con) -> list[dict]:
    found = []
    for p in DISCOVERY_PAGES:
        try:
            docs = parse_table_page(p["url"], downloader.get_text(p["url"]))
        except downloader.FetchError as e:
            log(con, "discover_failed", page=p["url"], error=str(e))
            continue
        for d in docs:
            c = classify_title(d["title"] + " " + d["description"])
            h = downloader.head(d["url"])
            d.update(c, host_kind=host_kind(d["url"]), http=h)
            con.execute("""INSERT INTO tn_sources(url, title, description, discovery_page, host, host_kind, discovered_at, last_checked,
                           http_last_modified, content_length, status) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(url) DO UPDATE SET title=excluded.title, description=excluded.description, last_checked=excluded.last_checked,
                           http_last_modified=excluded.http_last_modified, content_length=excluded.content_length""",
                        (d["url"], d["title"], d["description"], d["discovery_page"], d["url"].split("/")[2], d["host_kind"], now(), now(),
                         h.get("last_modified"), h.get("length"), "discovered"))
            found.append(d)
    con.commit()
    log(con, "discover", count=len(found))
    return found
