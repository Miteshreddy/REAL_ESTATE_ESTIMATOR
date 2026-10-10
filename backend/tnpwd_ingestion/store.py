"""Storage for TN PWD documents, their extracted content and the audit trail (same SQLite file as the app).

History is never overwritten: every downloaded file is kept by SHA-256, every extraction is stored per document,
and every check / import / activation is logged in tn_events.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.environ.get("EST_DATA_DIR") or os.path.join(ROOT, "data")
DOC_DIR = os.path.join(DATA, "tnpwd", "documents")
CACHE_DIR = os.path.join(DATA, "tnpwd", "cache")


def now():
    return datetime.now().isoformat(timespec="seconds")


def connect(path=None):
    con = sqlite3.connect(path or os.path.join(DATA, "estimate.db"), timeout=60)
    con.row_factory = sqlite3.Row
    ensure(con)
    return con


def ensure(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS tn_sources(url TEXT PRIMARY KEY, title TEXT, description TEXT, discovery_page TEXT, host TEXT,
        host_kind TEXT, discovered_at TEXT, last_checked TEXT, http_last_modified TEXT, content_length INTEGER, status TEXT);
    CREATE TABLE IF NOT EXISTS tn_documents(sha256 TEXT PRIMARY KEY, url TEXT, title TEXT, doc_type TEXT, authority TEXT,
        department TEXT, document_name TEXT, edition TEXT, year TEXT, financial_year TEXT, revision TEXT, effective_from TEXT,
        effective_to TEXT, pages INTEGER, text_pages INTEGER, needs_ocr INTEGER, local_path TEXT, downloaded_at TEXT,
        parser_version TEXT, verification_status TEXT, verification_note TEXT, extracted_at TEXT, extract_summary TEXT);
    CREATE TABLE IF NOT EXISTS tn_doc_urls(sha256 TEXT, url TEXT, seen_at TEXT, PRIMARY KEY(sha256, url));
    CREATE TABLE IF NOT EXISTS tn_rate_items(sha256 TEXT, code TEXT, description TEXT, unit TEXT, rate REAL, category TEXT,
        page INTEGER, PRIMARY KEY(sha256, code));
    CREATE TABLE IF NOT EXISTS tn_sd_items(sha256 TEXT, data_no TEXT, page INTEGER, section TEXT, description TEXT,
        per_qty REAL, per_unit TEXT, components TEXT, additions TEXT, PRIMARY KEY(sha256, data_no, page));
    CREATE TABLE IF NOT EXISTS tn_doc_pages(sha256 TEXT, page INTEGER, text TEXT, method TEXT, PRIMARY KEY(sha256, page));
    CREATE TABLE IF NOT EXISTS tn_events(at TEXT, kind TEXT, sha256 TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS tn_versions(schedule_id TEXT PRIMARY KEY, base_sha256 TEXT, amendment_sha256 TEXT, standard_data_sha256 TEXT,
        edition TEXT, effective_from TEXT, effective_to TEXT, status TEXT, activated_at TEXT, diff_summary TEXT);
    """)
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS tn_fts USING fts5(sha256 UNINDEXED, page UNINDEXED, kind UNINDEXED, ref UNINDEXED, text)")
    except sqlite3.OperationalError:  # FTS5 missing in this SQLite build → retrieval falls back to LIKE
        pass
    con.commit()


def log(con, kind, sha=None, **detail):
    con.execute("INSERT INTO tn_events VALUES(?,?,?,?)", (now(), kind, sha, json.dumps(detail, ensure_ascii=False, default=str)))
    con.commit()
