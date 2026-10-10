"""TNRD type-design discovery crawler.

  python tn_corpus/scripts/tnrd_discover.py --catalog-only        # resolve the live catalogue → catalog/tnrd_type_design_catalog.csv
  python tn_corpus/scripts/tnrd_discover.py --download-candidates # + quarantine PDFs in raw_candidates/ with SHA-256 sidecars

Downloads are RAW_CANDIDATE / REVIEW_REQUIRED, never training-eligible. Idempotent: an existing sidecar with the same
Last-Modified/ETag is not re-downloaded (use --refresh to re-check).
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_fetch as sf  # noqa: E402

ROOT = sf.ROOT
CATALOG_URL = "https://tnrd.tn.gov.in/buildings_design.html"
POLICY_URL = "https://tnrd.tn.gov.in/rdweb_newsite/project/reports/Public/WebsitePolicies.php"
CAT = os.path.join(ROOT, "catalog", "tnrd_type_design_catalog.csv")
Q = os.path.join(ROOT, "raw_candidates")
COLS = ["entry_no", "column", "catalogue_title", "title_basis", "url", "file_name", "category_hint", "set_hint"]


def parse_catalog(page: str) -> list[dict]:
    out = []
    for row in re.findall(r"<tr.*?</tr>", page, re.S | re.I):
        cells = re.findall(r"<td.*?</td>", row, re.S | re.I)
        for ci, cell in enumerate(cells):
            for href, text in re.findall(r'href="(buildings_design/[^"]+)"[^>]*>(.*?)</a>', cell, re.S | re.I):
                t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()
                if not t:
                    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()
                out.append(dict(column=ci, catalogue_title=t, url=urljoin(CATALOG_URL, href), file_name=href.split("/")[-1]))
    seen, res = set(), []
    for i, r in enumerate(out):
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        r["entry_no"] = len(res) + 1
        r["title_basis"] = "link text on catalogue page (extracted)"
        r["category_hint"] = category(r["catalogue_title"] + " " + r["file_name"])
        r["set_hint"] = set_hint(r["file_name"])
        res.append(r)
    return res


def category(t: str) -> str:
    t = t.lower()
    for k, v in (("school", "school"), ("esb", "school"), ("anganwadi", "anganwadi"), ("kitchen", "school"), ("toilet", "sanitation"),
                 ("stg", "sanitation"), ("stb", "sanitation"), ("ihhl", "sanitation"), ("sanitary", "sanitation"), ("septic", "sanitation"),
                 ("imsc", "sanitation"), ("library", "library"), ("lb-", "library"), ("community hall", "community_hall"), ("ch-", "community_hall"),
                 ("panchayat", "panchayat_office"), ("po-", "panchayat_office"), ("vao", "office"), ("aee", "office"), ("iay", "house"),
                 ("green house", "house"), ("pvt", "house"), ("godown", "warehouse"), ("pds", "shop"), ("shg", "community"),
                 ("pstr", "shelter"), ("passenger", "shelter"), ("cremation", "shed"), ("cs-", "shed"), ("thrash", "open_structure"),
                 ("tf-", "open_structure"), ("milk", "cooperative"), ("mc-", "cooperative"), ("handbook", "handbook"),
                 ("buildings.pdf", "handbook"), ("roads", "roads_bridges_handbook_out_of_scope")):
        if k in t:
            return v
    return "UNKNOWN"


DPO_SHEETS = re.compile(r"^(Beam L\.S|Cross Section|Drain|FF|GF|Plinth beam|Portico|SF-ARC|Sanitary|Stair case|Tranining Hall|Water Supply)", re.I)


def set_hint(fn: str) -> str:
    """Sheets listed without a building title in the second catalogue column look like one multi-sheet building package
    (GF/FF/SF architecture, roofs, beams, portico, stair, services). INFERRED — confirm with TNRD."""
    return "INFERRED: multi-sheet office package (District Panchayat Office GF/FF listed separately)" if DPO_SHEETS.match(fn) else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog-only", action="store_true")
    ap.add_argument("--download-candidates", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(CAT), exist_ok=True)
    try:
        r = sf.get(CATALOG_URL)
    except sf.Blocked as e:
        print("catalogue fetch blocked:", e)
        return 2
    page = r["body"].decode("utf-8", "replace")
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    open(os.path.join(ROOT, "logs", "tnrd_catalogue_page.html"), "w", encoding="utf-8").write(page)  # public page, kept for provenance
    rows = parse_catalog(page)
    pol = dict(url=POLICY_URL, robots_allowed=sf.robots_allowed(POLICY_URL))
    for x in rows:
        x["robots_allowed"] = sf.robots_allowed(x["url"])
    with open(CAT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS + ["robots_allowed"])
        w.writeheader()
        w.writerows(rows)
    print(f"catalogue: {len(rows)} PDF links on {CATALOG_URL}; policy page robots_allowed={pol['robots_allowed']}")
    if not a.download_candidates:
        return 0
    os.makedirs(Q, exist_ok=True)
    got = skipped = blocked = 0
    for x in rows:
        side = os.path.join(Q, re.sub(r"[^A-Za-z0-9._-]+", "_", x["file_name"]) + ".json")
        if os.path.exists(side) and not a.refresh:
            skipped += 1
            continue
        try:
            d = sf.get(x["url"], expect="pdf")
        except sf.Blocked as e:
            blocked += 1
            json.dump(dict(x, acquisition_state="BLOCKED_BY_SOURCE_RULES" if "robots" in str(e) else "FAILED", reason=str(e), at=sf.now()),
                      open(side, "w", encoding="utf-8"), indent=1)
            continue
        path = os.path.join(Q, d["sha256"] + ".pdf")
        if not os.path.exists(path):
            open(path, "wb").write(d["body"])
        json.dump(dict(x, final_url=d["final_url"], http_status=d["status"], content_type=d["content_type"], bytes=len(d["body"]),
                       sha256=d["sha256"], file_path=os.path.relpath(path, ROOT), acquired_at=sf.now(), last_modified=d["last_modified"],
                       etag=d["etag"], source_organisation="Rural Development & Panchayat Raj Dept, Govt of Tamil Nadu (TNRD)",
                       licence_policy_url=POLICY_URL, permission_evidence="TNRD website policy: reproduction with attribution allowed; "
                       "ML-training use not addressed", acquisition_state="RAW_CANDIDATE", usage_state="REVIEW_REQUIRED",
                       training_eligible=False, evaluation_eligible=False, attribution=f"Source: TNRD, {x['url']}"),
                  open(side, "w", encoding="utf-8"), indent=1)
        got += 1
        print("ok", x["file_name"], len(d["body"]))
    print(f"downloaded {got}, already present {skipped}, blocked/failed {blocked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
