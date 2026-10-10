"""Quarantine-download individual non-TNRD leads that robots.txt permits (python tn_corpus/scripts/fetch_leads.py).
Each lead is REVIEW_REQUIRED; rights are never inferred from a public URL. Leads whose access path is a CAPTCHA,
login or robots disallow are listed in catalog/public_source_registry.csv instead and are NOT fetched."""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_fetch as sf  # noqa: E402

LEADS = [
    dict(lead_id="jica_ich_chennai", url="https://openjicareport.jica.go.jp/pdf/12144929.pdf",
         title="JICA report — Institute of Child Health and Hospital for Children, Chennai (as named in the request)",
         source_organisation="JICA Open Report library", source_class="third_party_public_report", building_type="hospital",
         licence_policy_url="https://openjicareport.jica.go.jp/", permission_evidence="none recorded — JICA report terms not reviewed"),
    dict(lead_id="tnhsp_completion_report", url="https://tnhsp.org/uploads/Completion-Report.pdf",
         title="TNHSP Completion Report (linked from Projects_TNUHP page)", source_organisation="Tamil Nadu Health System Project",
         source_class="official_portal", building_type="hospital", licence_policy_url="https://tnhsp.org/",
         permission_evidence="none recorded — site terms not found"),
]


def main():
    q = os.path.join(sf.ROOT, "raw_candidates")
    os.makedirs(q, exist_ok=True)
    for L in LEADS:
        side = os.path.join(q, "lead_" + L["lead_id"] + ".json")
        if os.path.exists(side) and "--refresh" not in sys.argv:
            print("present", L["lead_id"])
            continue
        try:
            d = sf.get(L["url"], expect="pdf")
        except sf.Blocked as e:
            json.dump(dict(L, acquisition_state="BLOCKED_BY_SOURCE_RULES" if re.search("robots|HTTP 4|captcha", str(e)) else "FAILED",
                           reason=str(e), at=sf.now()), open(side, "w", encoding="utf-8"), indent=1)
            print("blocked", L["lead_id"], e)
            continue
        path = os.path.join(q, d["sha256"] + ".pdf")
        if not os.path.exists(path):
            open(path, "wb").write(d["body"])
        json.dump(dict(L, file_name=L["url"].rsplit("/", 1)[-1], final_url=d["final_url"], http_status=d["status"],
                       content_type=d["content_type"], bytes=len(d["body"]), sha256=d["sha256"], file_path=os.path.relpath(path, sf.ROOT),
                       acquired_at=sf.now(), acquisition_state="RAW_CANDIDATE", usage_state="REVIEW_REQUIRED", training_eligible=False,
                       evaluation_eligible=False, attribution=f"Source: {L['source_organisation']}, {L['url']}"),
                  open(side, "w", encoding="utf-8"), indent=1)
        print("ok", L["lead_id"], len(d["body"]))


if __name__ == "__main__":
    main()
