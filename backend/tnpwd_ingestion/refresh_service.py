"""TN PWD rate refresh — command line and API entry points.

    python -m tnpwd_ingestion.refresh_service check        # discover documents, report new / changed ones (no download)
    python -m tnpwd_ingestion.refresh_service download     # download + hash + classify + verify (history kept by SHA-256)
    python -m tnpwd_ingestion.refresh_service extract      # SOR rates, amendments, Standard Data, page text → DB + index
    python -m tnpwd_ingestion.refresh_service build        # latest SOR + its amendments → validated candidate + diff vs active
    python -m tnpwd_ingestion.refresh_service activate     # make the validated candidate the production TN schedule
    python -m tnpwd_ingestion.refresh_service refresh      # all of the above (activation only if validation passes)
    python -m tnpwd_ingestion.refresh_service status | compare <schedule_a> <schedule_b> | search <text>
"""
from __future__ import annotations

import json
import os
import sys

import pymupdf

from . import PARSER_VERSION, crawler, downloader, retrieval_index, validator, version_manager
from .amendment_parser import parse_amendment
from .document_classifier import classify_document
from .pdf_text import page_texts
from .rate_parser import parse_sor
from .source_registry import AUTHORITY, DEPARTMENT, KNOWN_COPIES, host_kind
from .standard_data_parser import parse as parse_sd
from .store import connect, log, now

RELEVANT = ("sor", "sor_amendment", "standard_data")


def check(con):
    found = crawler.discover(con)
    have = {r["url"]: dict(r) for r in con.execute("SELECT u.url, d.sha256, d.title FROM tn_doc_urls u JOIN tn_documents d ON d.sha256=u.sha256")}
    out = []
    for d in found:
        st = "already held" if d["url"] in have else ("NEW" if d["doc_type"] in RELEVANT else "not relevant")
        out.append(dict(title=d["title"], type=d["doc_type"], financial_year=d["financial_year"], effective_from=d["effective_from"],
                        url=d["url"], host_kind=d["host_kind"], last_modified=(d.get("http") or {}).get("last_modified"), status=st))
    log(con, "check", new=sum(1 for o in out if o["status"] == "NEW"), total=len(out))
    return out


def _verify(con, sha, url):
    if host_kind(url) == "official":
        return "official source", f"downloaded from a Government domain ({url.split('/')[2]})"
    hosts = {u.split("/")[2] for (u,) in con.execute("SELECT url FROM tn_doc_urls WHERE sha256=?", (sha,))}
    hosts |= {k["url"].split("/")[2] for k in KNOWN_COPIES if k["sha256"] == sha}
    if len(hosts) >= 2:
        return "cross-verified", f"identical file (SHA-256) published on {len(hosts)} independent public hosts: {', '.join(sorted(hosts))}; not a Government domain"
    return "unverified secondary source", f"single non-government host ({url.split('/')[2]}); verify against the department copy"


def download(con, only_relevant=True):
    rows = [dict(r) for r in con.execute("SELECT * FROM tn_sources")]
    res = []
    for s in rows:
        from .document_classifier import classify_title
        c = classify_title((s["title"] or "") + " " + (s["description"] or ""))
        if only_relevant and c["doc_type"] not in RELEVANT:
            continue
        try:
            d = downloader.download_pdf(s["url"])
        except Exception as e:  # noqa: BLE001
            log(con, "download_failed", url=s["url"], error=str(e))
            res.append(dict(url=s["url"], error=str(e)))
            continue
        doc = pymupdf.open(d["path"])
        first = " ".join(doc[i].get_text() for i in range(min(4, len(doc))))
        cl = classify_document((s["title"] or "") + " " + (s["description"] or ""), first)
        text_pages = sum(1 for p in doc if len(p.get_text().strip()) > 40)
        con.execute("INSERT OR IGNORE INTO tn_doc_urls VALUES(?,?,?)", (d["sha256"], s["url"], now()))
        status, note = _verify(con, d["sha256"], s["url"])
        con.execute("""INSERT INTO tn_documents(sha256, url, title, doc_type, authority, department, document_name, edition, year, financial_year,
                       effective_from, pages, text_pages, needs_ocr, local_path, downloaded_at, parser_version, verification_status, verification_note)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(sha256) DO UPDATE SET verification_status=excluded.verification_status,
                       verification_note=excluded.verification_note""",
                    (d["sha256"], s["url"], s["title"], cl["doc_type"], AUTHORITY, DEPARTMENT, s["description"], cl["edition"], cl["year"],
                     cl["financial_year"], cl["effective_from"], len(doc), text_pages, int(text_pages < len(doc) * 0.5), d["path"], now(),
                     PARSER_VERSION, status, note))
        con.commit()
        log(con, "download", d["sha256"], url=s["url"], bytes=d["bytes"], type=cl["doc_type"], verification=status)
        res.append(dict(url=s["url"], sha256=d["sha256"], type=cl["doc_type"], financial_year=cl["financial_year"], verification=status))
    return res


def _docs(con, kind):
    return [dict(r) for r in con.execute("SELECT * FROM tn_documents WHERE doc_type=? ORDER BY financial_year DESC, effective_from DESC", (kind,))]


def latest_sor(con):
    """Newest edition = highest financial year, then latest effective date — read from the documents, not from the site's wording."""
    docs = [d for d in _docs(con, "sor") if d["financial_year"]]
    docs.sort(key=lambda d: (d["financial_year"], d["effective_from"] or ""), reverse=True)
    return docs[0] if docs else None


def extract(con, sha=None):
    out = {}
    base = latest_sor(con)
    targets = [sha] if sha else [d["sha256"] for d in (([base] if base else []) + _docs(con, "sor_amendment") + _docs(con, "standard_data"))]
    for s in targets:
        d = dict(con.execute("SELECT * FROM tn_documents WHERE sha256=?", (s,)).fetchone())
        if d["doc_type"] == "sor":
            items, skipped = parse_sor(d["local_path"])
            con.execute("DELETE FROM tn_rate_items WHERE sha256=?", (s,))
            con.executemany("INSERT INTO tn_rate_items VALUES(?,?,?,?,?,?,?)",
                            [(s, i["code"], i["description"], i["unit"], i["rate"], i["category"], i["page"]) for i in items])
            retrieval_index.rebuild(con, s, "sor_item", [(i["page"], i["code"], f'{i["code"]} {i["description"]} per {i["unit"]} ₹{i["rate"]}') for i in items])
            summ = dict(items=len(items), skipped=len(skipped))
        elif d["doc_type"] == "sor_amendment":
            if not base:
                continue
            br = {r["code"]: r["rate"] for r in con.execute("SELECT code, rate FROM tn_rate_items WHERE sha256=?", (base["sha256"],))}
            a = parse_amendment(d["local_path"], br)
            con.execute("UPDATE tn_documents SET effective_from=COALESCE(?, effective_from), revision=? WHERE sha256=?",
                        (a["effective_from"], a["reference"], s))
            summ = dict(rows=a["rows"], rejected=a["rejected"], effective_from=a["effective_from"], reference=a["reference"], base_sha256=base["sha256"])
        elif d["doc_type"] == "standard_data":
            items = parse_sd(d["local_path"])
            con.execute("DELETE FROM tn_sd_items WHERE sha256=?", (s,))
            con.executemany("INSERT OR REPLACE INTO tn_sd_items VALUES(?,?,?,?,?,?,?,?,?)",
                            [(s, i["data_no"], i["page"], None, i["description"], None, None, json.dumps(i["variants"], ensure_ascii=False), None) for i in items])
            retrieval_index.rebuild(con, s, "standard_data", [(i["page"], "SD " + i["data_no"], i["description"]) for i in items])
            summ = dict(items=len(items), variants=sum(len(i["variants"]) for i in items))
        else:
            continue
        pages = list(page_texts(d["local_path"], ocr_missing=True, max_ocr_pages=10))
        con.execute("DELETE FROM tn_doc_pages WHERE sha256=?", (s,))
        con.executemany("INSERT INTO tn_doc_pages VALUES(?,?,?,?)", [(s, p, t, m) for p, t, m in pages])
        retrieval_index.rebuild(con, s, "page", [(p, f"p{p}", t[:4000]) for p, t, m in pages if t])
        con.execute("UPDATE tn_documents SET extracted_at=?, extract_summary=?, parser_version=? WHERE sha256=?",
                    (now(), json.dumps(summ, ensure_ascii=False, default=str), PARSER_VERSION, s))
        con.commit()
        log(con, "extract", s, **{k: v for k, v in summ.items() if not isinstance(v, list)})
        out[s] = summ
    return out


def build(con):
    base = latest_sor(con)
    if not base:
        return dict(ok=False, error="no TN SOR document held — run check/download first")
    items = [dict(r) for r in con.execute("SELECT code, description, unit, rate, category, page FROM tn_rate_items WHERE sha256=?", (base["sha256"],))]
    amds = [d for d in _docs(con, "sor_amendment") if d["financial_year"] == base["financial_year"] and d.get("extract_summary")]
    applied, amd_sha, amd_date = [], None, None
    for a in sorted(amds, key=lambda d: d["effective_from"] or ""):
        summ = json.loads(a["extract_summary"])
        if summ.get("base_sha256") != base["sha256"]:
            continue
        items, ap = version_manager.apply_amendment(items, summ["rows"])
        applied += [dict(x, amendment=a["revision"]) for x in ap]
        amd_sha, amd_date = a["sha256"], a["effective_from"]
    active = con.execute("SELECT id FROM rate_schedules WHERE region='Tamil Nadu' AND status='active'").fetchone()
    prev = [dict(r) for r in con.execute("SELECT code, description, unit, rate FROM rate_items WHERE schedule_id=?", (active[0],))] if active else []
    v = validator.validate_rates(items, prev or None)
    dif = version_manager.diff(prev, items) if prev else None
    sd = _docs(con, "standard_data")
    cand = dict(ok=v["ok"], validation=v, schedule_id=version_manager.schedule_id(base["financial_year"], amd_date),
                base=dict(sha256=base["sha256"], title=base["title"], financial_year=base["financial_year"], effective_from=base["effective_from"],
                          verification=base["verification_status"]),
                amendments_applied=applied, amendment_sha256=amd_sha, standard_data_sha256=sd[0]["sha256"] if sd else None,
                diff_vs_active=(dict(active=active[0], **dif["summary"]) if dif else None), items=len(items))
    con.execute("INSERT OR REPLACE INTO tn_events VALUES(?,?,?,?)", (now(), "build", base["sha256"], json.dumps(cand, default=str)))
    con.commit()
    return dict(cand, _items=items)


def activate(con, cand=None):
    cand = cand or build(con)
    if not cand.get("ok"):
        return dict(ok=False, error="validation failed — not activated", validation=cand.get("validation"))
    base = dict(con.execute("SELECT * FROM tn_documents WHERE sha256=?", (cand["base"]["sha256"],)).fetchone())
    eff = (cand["amendments_applied"] and con.execute("SELECT effective_from FROM tn_documents WHERE sha256=?", (cand["amendment_sha256"],)).fetchone()[0]) \
        or base["effective_from"]
    meta = dict(name=f"Tamil Nadu PWD Schedule of Rates {base['financial_year']} — Vol I" + (" (incl. amendment)" if cand["amendments_applied"] else ""),
                authority="Tamil Nadu PWD", department=DEPARTMENT, country="India", region="Tamil Nadu", authority_level="state",
                schedule_type="SOR", code_system="TN-SOR", year=base["year"], financial_year=base["financial_year"],
                revision=("Amendment " + "; ".join(sorted({a["amendment"] or "" for a in cand["amendments_applied"]}))) if cand["amendments_applied"] else None,
                effective_from=eff, currency="INR", source=f"TN PWD document ({base['verification_status']})",
                source_ref=f"{base['title']} — {base['url']} — SHA-256 {base['sha256']}",
                notes="Rates exclusive of GST as printed. Finished-item rates are analysed with the TN PWD Standard Data Book "
                      "(see rate analysis on each item).")
    prov = dict(source_url=base["url"], source_title=base["title"], authority=AUTHORITY, department=DEPARTMENT, document_name=base["document_name"],
                edition=base["edition"], financial_year=base["financial_year"], effective_from=eff, base_sha256=base["sha256"],
                amendment_sha256=cand["amendment_sha256"], standard_data_sha256=cand["standard_data_sha256"], downloaded_at=base["downloaded_at"],
                parser_version=PARSER_VERSION, verification_status=base["verification_status"], diff_summary=cand.get("diff_vs_active"))
    version_manager.activate(con, cand["schedule_id"], meta, cand["_items"], prov)
    return dict(ok=True, schedule_id=cand["schedule_id"], items=len(cand["_items"]), amendments_applied=len(cand["amendments_applied"]))


def status(con):
    return dict(
        documents=[{k: d[k] for k in ("sha256", "title", "doc_type", "financial_year", "effective_from", "revision", "pages", "verification_status",
                                      "verification_note", "downloaded_at", "extracted_at", "url")} for d in map(dict, con.execute(
            "SELECT * FROM tn_documents ORDER BY doc_type, financial_year DESC"))],
        versions=[dict(r) for r in con.execute("SELECT * FROM tn_versions ORDER BY activated_at DESC")],
        sources=[dict(r) for r in con.execute("SELECT url, title, host_kind, last_checked, http_last_modified FROM tn_sources")],
        last_check=(con.execute("SELECT at FROM tn_events WHERE kind='check' ORDER BY at DESC LIMIT 1").fetchone() or [None])[0],
        events=[dict(r) for r in con.execute("SELECT at, kind, sha256, substr(detail,1,300) AS detail FROM tn_events ORDER BY at DESC LIMIT 30")])


def compare(con, a, b):
    ia = [dict(r) for r in con.execute("SELECT code, description, unit, rate FROM rate_items WHERE schedule_id=?", (a,))]
    ib = [dict(r) for r in con.execute("SELECT code, description, unit, rate FROM rate_items WHERE schedule_id=?", (b,))]
    return version_manager.diff(ia, ib)


def refresh(con):
    out = dict(check=check(con), download=download(con), extract={k: {kk: vv for kk, vv in v.items() if not isinstance(vv, list)}
                                                                    for k, v in extract(con).items()})
    cand = build(con)
    out["build"] = {k: v for k, v in cand.items() if k != "_items"}
    out["activate"] = activate(con, cand) if cand.get("ok") else dict(ok=False, error="validation failed — previous schedule kept")
    return out


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    con = connect()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "build":
        r = {k: v for k, v in build(con).items() if k != "_items"}
    elif cmd == "compare":
        r = compare(con, sys.argv[2], sys.argv[3])
    elif cmd == "search":
        r = retrieval_index.search(con, " ".join(sys.argv[2:]))
    else:
        r = dict(check=check, download=download, extract=extract, activate=activate, refresh=refresh, status=status)[cmd](con)
    print(json.dumps(r, indent=1, ensure_ascii=False, default=str)[:20000])
