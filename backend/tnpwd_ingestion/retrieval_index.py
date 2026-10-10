"""Search over validated TN documents (SOR items, Standard Data items, page text) — SQLite FTS5 with BM25 ranking.

Retrieval only HELPS mapping and review (suggestions with their source page). It never prices anything by itself:
only validated, structured rows in rate_items / tn_sd_items reach the estimate.
"""
from __future__ import annotations

import json
import re


def rebuild(con, sha: str, kind: str, rows: list[tuple[int, str, str]]):
    """rows: (page, ref, text)"""
    try:
        con.execute("DELETE FROM tn_fts WHERE sha256=? AND kind=?", (sha, kind))
        con.executemany("INSERT INTO tn_fts(sha256, page, kind, ref, text) VALUES(?,?,?,?,?)", [(sha, p, kind, r, t) for p, r, t in rows])
        con.commit()
    except Exception:  # noqa: BLE001 — no FTS5: search() falls back to LIKE on tn_doc_pages
        pass


def _q(text):
    words = [w for w in re.findall(r"[A-Za-z0-9]+(?::[0-9]+)*", text) if len(w) > 1]
    return " OR ".join(f'"{w}"' for w in words[:20])


def search(con, text: str, kind: str | None = None, limit: int = 10) -> list[dict]:
    q = _q(text)
    if not q:
        return []
    try:
        sql = ("SELECT f.sha256, f.page, f.kind, f.ref, snippet(tn_fts, 4, '[', ']', '…', 18) AS snip, bm25(tn_fts) AS score, "
               "d.title, d.edition, d.verification_status FROM tn_fts f LEFT JOIN tn_documents d ON d.sha256=f.sha256 "
               "WHERE tn_fts MATCH ?" + (" AND f.kind=?" if kind else "") + " ORDER BY score LIMIT ?")
        rows = con.execute(sql, (q, kind, limit) if kind else (q, limit)).fetchall()
    except Exception:  # noqa: BLE001
        like = "%" + text.split()[0] + "%"
        rows = con.execute("SELECT p.sha256, p.page, 'page' AS kind, '' AS ref, substr(p.text,1,200) AS snip, 0 AS score, d.title, d.edition, "
                           "d.verification_status FROM tn_doc_pages p LEFT JOIN tn_documents d ON d.sha256=p.sha256 WHERE p.text LIKE ? LIMIT ?",
                           (like, limit)).fetchall()
    return [dict(r) for r in rows]
