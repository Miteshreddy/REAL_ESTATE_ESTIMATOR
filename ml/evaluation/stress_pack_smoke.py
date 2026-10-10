"""Workflow / parser smoke test of the TN stress pack's folder 03 reference drawings through the real app.

    python ml/evaluation/stress_pack_smoke.py <pack_root> <out_dir>

Reference drawings are NOT matched to any tender case: results are parser / workflow checks, never cost accuracy.
Throw-away data directory; the user's database is never touched. The 334-page handbook is skipped (prose + duplicates
of the type-design extract; see report).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
import time

PACK, OUT = sys.argv[1], sys.argv[2]
os.environ["EST_DATA_DIR"] = tempfile.mkdtemp(prefix="stress_smoke_")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

LEGEND_WORDS = ("legend", "title", "scale", "drawn", "checked", "approved", "note", "section", "elevation", "detail")


def main():
    os.makedirs(OUT, exist_ok=True)
    man = os.path.join(PACK, "03_REFERENCE_DRAWINGS_NOT_MATCHED_TO_TENDER_VALUES", "reference_drawing_manifest.csv")
    rows = list(csv.DictReader(open(man, encoding="utf-8-sig")))
    res = []
    with TestClient(app.app) as c:
        for m in rows:
            path = os.path.join(PACK, m["path"])
            fn = os.path.basename(path)
            r = dict(file=fn, manifest_sha256=m["sha256"])
            if not os.path.exists(path):
                res.append({**r, "result": "MISSING"}); continue
            data = open(path, "rb").read()
            r["sha256"] = hashlib.sha256(data).hexdigest(); r["hash_ok"] = r["sha256"] == m["sha256"]; r["bytes"] = len(data)
            if "Handbook" in fn:
                res.append({**r, "result": "SKIPPED", "reason": "334-page prose handbook; drawing pages covered by the type-design extract"}); continue
            t = time.time()
            try:
                p = c.post("/api/projects", data={"name": f"smoke {fn}", "loc": '{"district":"Chennai"}'}).json()
                resp = c.post(f"/api/projects/{p['id']}/files", files={"files": (fn, data)})
                q = resp.json()
                sh = q.get("sheets", [])
                rooms = [x for s in sh for x in (s.get("rooms") or [])]
                susp = [x.get("name") for x in rooms if any(w in str(x.get("name", "")).lower() for w in LEGEND_WORDS)]
                r.update(result="OK" if resp.status_code == 200 else f"HTTP {resp.status_code}", secs=round(time.time() - t, 1),
                         sheets=len(sh), kinds=sorted({s.get("kind") for s in sh}),
                         floors=[(s.get("floor") or {}).get("label") for s in sh if s.get("floor")],
                         scale=sorted({str(((s.get("areas") or {}).get("calibration") or {}).get("status")) for s in sh}),
                         rooms=len(rooms), suspicious_room_names=susp,
                         doors=sum(1 for s in sh for o in (s.get("openings") or []) if o.get("kind") == "door"),
                         windows=sum(1 for s in sh for o in (s.get("openings") or []) if o.get("kind") == "window"),
                         detector_models=sorted({str(s.get("detector_model")) for s in sh}),
                         warnings=sorted({f"{k['level']}: {k['code']}" for k in q.get("checks", [])}),
                         status=((q.get("stats") or {}).get("status_summary") or {}).get("status"),
                         total=(q.get("estimate") or {}).get("total"))
                json.dump(q, open(os.path.join(OUT, fn + ".json"), "w"), default=str)
            except Exception as e:
                r.update(result="EXCEPTION", error=repr(e)[:300], secs=round(time.time() - t, 1))
            res.append(r); print(json.dumps(r)[:400], flush=True)
    json.dump(res, open(os.path.join(OUT, "smoke_results.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
