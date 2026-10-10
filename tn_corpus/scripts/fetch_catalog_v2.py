"""Quarantine the direct-PDF leads of the v2 source catalogue (python tn_corpus/scripts/fetch_catalog_v2.py).

Reuses safe_fetch (allowlist, SSRF, robots, delay, size cap, PDF magic, kill switch, decision log). Only rows marked
include_in_auto_download=YES_IF_ROBOTS_ALLOW are attempted; TNRD buildings_design rows are skipped (already acquired by
tnrd_discover.py). The catalogue was compiled offline by the pack author, so every URL is treated as an unverified claim
until it actually returns a PDF. Results: raw_candidates/v2_<source_id>.json (+ <sha256>.pdf) and
registry/catalog_v2_acquisition.csv.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_fetch as sf  # noqa: E402

CAT = os.path.join(sf.ROOT, "sources", "zip_v2", "TN_High_Impact_Architecture_Corpus", "04_SOURCE_CATALOGS", "expanded_source_catalog.csv")
Q = os.path.join(sf.ROOT, "raw_candidates")


def rows():
    return list(csv.DictReader(open(CAT, encoding="utf-8-sig")))


def main():
    os.makedirs(Q, exist_ok=True)
    todo = [r for r in rows() if r["include_in_auto_download"] == "YES_IF_ROBOTS_ALLOW" and "/buildings_design/" not in r["url"]]
    sf.ALLOW_HOSTS |= {urlparse(r["url"]).hostname.lower() for r in todo}  # hosts named by the curated catalogue only
    out, seen = [], {}
    for r in todo:
        side = os.path.join(Q, f"v2_{r['source_id']}.json")
        base = dict(source_id=r["source_id"], title=r["title"], category=r["category"], state=r["state"], url=r["url"],
                    catalogue_training_status=r["training_status"], catalogue_evaluation_status=r["evaluation_status"])
        if os.path.exists(side) and "--refresh" not in sys.argv and r["state"] == "Tamil Nadu":
            out.append(json.load(open(side, encoding="utf-8")))
            continue
        if r["state"] != "Tamil Nadu":  # TN-only corpus: non-TN leads are never fetched
            rec = dict(base, acquisition_state="REJECTED_NON_TN", reason=f"state = {r['state']} (TN-only scope)", at=sf.now())
        elif r["url"] in seen:  # same URL listed under two source ids
            rec = dict(base, acquisition_state="DUPLICATE_URL", duplicate_of=seen[r["url"]], at=sf.now())
        else:
            try:
                d = sf.get(r["url"], expect="pdf")
                path = os.path.join(Q, d["sha256"] + ".pdf")
                if not os.path.exists(path):
                    open(path, "wb").write(d["body"])
                rec = dict(base, final_url=d["final_url"], http_status=d["status"], content_type=d["content_type"], bytes=len(d["body"]),
                           sha256=d["sha256"], file_path=os.path.relpath(path, sf.ROOT), file_name=r["url"].rsplit("/", 1)[-1],
                           acquired_at=sf.now(), acquisition_state="RAW_CANDIDATE", usage_state="REVIEW_REQUIRED",
                           source_class="official_portal" if any(k in r["url"] for k in (".gov.in", ".ac.in", "tn.gov")) else
                           "third_party_public_report" if "jica" in r["url"] else "third_party_host",
                           training_eligible=False, evaluation_eligible=False, building_type=r["category"].split(";")[0],
                           source_organisation=urlparse(r["url"]).hostname, attribution=f"Source: {r['url']}",
                           permission_evidence="none recorded — public URL only")
                seen[r["url"]] = r["source_id"]
            except sf.Blocked as e:
                rec = dict(base, acquisition_state="BLOCKED_BY_SOURCE_RULES" if any(k in str(e) for k in ("robots", "HTTP 4", "captcha"))
                           else "FAILED", reason=str(e), at=sf.now())
        json.dump(rec, open(side, "w", encoding="utf-8"), indent=1)
        out.append(rec)
        print(rec["source_id"], rec["acquisition_state"], rec.get("bytes") or rec.get("reason", ""))
    cols = ["source_id", "title", "category", "state", "url", "acquisition_state", "http_status", "bytes", "sha256", "reason", "duplicate_of"]
    with open(os.path.join(sf.ROOT, "registry", "catalog_v2_acquisition.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)


if __name__ == "__main__":
    main()
