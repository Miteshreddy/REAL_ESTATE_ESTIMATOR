"""TN dataset build / refresh — command line.

    python -m tn_data_ingestion.refresh build        # ingest local seeds + uploaded client drawings, group, dedup, split, queue
    python -m tn_data_ingestion.refresh discover     # public-page discovery (robots.txt / licence checked; nothing auto-trusted)
    python -m tn_data_ingestion.refresh pseudo [n]   # pseudo-label up to n pages (NOT ground truth)
    python -m tn_data_ingestion.refresh export       # verified annotations → YOLO (project split)
    python -m tn_data_ingestion.refresh dashboard    # dataset quality dashboard (data/tn_dataset/metadata/dashboard.json)
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter

from . import annotation_queue, crawler, dataset_builder
from .dataset_builder import DS, _load, _save
from .source_registry import LOCAL_SEEDS

ROOT = dataset_builder.ROOT


def build():
    out = {}
    for s in LOCAL_SEEDS:
        files = sorted(glob.glob(os.path.join(s["path"], "*.pdf")) + glob.glob(os.path.join(s["path"], "*.png")))
        out[s["path"]] = dataset_builder.ingest(files, s["source"], district=s.get("district"))
    # client / user drawings (Tamil Nadu projects created in the app) — evaluation reserved by default
    # Aparna (Hyderabad) is NOT Tamil Nadu: reference only
    ap = [u for u in glob.glob(os.path.join(ROOT, "data", "uploads", "*", "*")) if "refuge" in u.lower()]
    if ap:
        out["reference"] = dataset_builder.ingest(ap, "non_tn_reference")
    smoke = sorted(glob.glob(os.path.join(ROOT, "data", "evaluation", "tn", "complex_smoke", "case*.png")))
    if smoke:
        out["smoke"] = dataset_builder.ingest(smoke, "scribd_arch", project_keys=["complex-" + os.path.splitext(os.path.basename(x))[0] for x in smoke])
    out["projects"] = dataset_builder.group_projects()
    out["splits"] = dataset_builder.split()
    out["queue"] = len(annotation_queue.build_queue())
    out["dashboard"] = dashboard()
    return out


def dashboard():
    pages = _load("pages.json", {})
    projects = _load("projects.json", {})
    ver = [json.load(open(f)) for f in glob.glob(os.path.join(DS, "annotations", "verified", "*.json"))]
    pse = [json.load(open(f)) for f in glob.glob(os.path.join(DS, "pseudo_labels", "*.json"))]
    obj = lambda anns: Counter(o["class"] for a in anns for o in a.get("objects", []))
    disc = _load("discovery.json", [])
    states = Counter()
    for pid in pages:
        st = "UNANNOTATED"
        vp = os.path.join(DS, "annotations", "verified", pid + ".json")
        if os.path.exists(vp):
            st = json.load(open(vp)).get("verification_status", "IN_REVIEW").upper()
        elif os.path.exists(os.path.join(DS, "pseudo_labels", pid + ".json")):
            st = "PSEUDO-LABEL"
        states[st] += 1
    d = dict(total_projects=len(projects), total_sheets=len(pages),
             discovered_candidates=len(disc), discovered_disallowed=sum(1 for x in disc if "disallowed" in x.get("status", "")),
             downloaded_documents=len({p["sha256"] for p in pages.values()}),
             training_eligible_projects=sum(1 for p in projects.values() if p.get("split") in ("tn_train", "tn_validation")),
             evaluation_eligible_projects=sum(1 for p in projects.values() if p.get("split") in ("final_holdout", "development_benchmark")),
             permission_pending_projects=sum(1 for p in projects.values() if p.get("split") == "excluded"),
             rejected_or_corrupt=_load("rejected.json", []), annotation_states=states,
             splits=Counter(p.get("split") for p in projects.values()),
             verified_pages=len(ver), verified_objects=obj(ver), pseudo_pages=len(pse), pseudo_objects=obj(pse),
             structural_sheets=sum(1 for p in pages.values() if p["discipline"] == "structural"),
             commercial_sheets=sum(1 for p in pages.values() if p["building_type"] in ("commercial", "office", "hospital", "educational")),
             scans=sum(1 for p in pages.values() if "raster" in p["text_method"]),
             vector_files=sum(1 for p in pages.values() if p["text_method"] == "vector text"),
             cad_files=sum(1 for p in pages.values() if p["file_type"] in ("dxf", "dwg")),
             district_distribution=Counter(p.get("district") or "not stated" for p in projects.values()),
             building_type_distribution=Counter(p.get("building_type") for p in projects.values()),
             drawing_type_distribution=Counter(p["drawing_type"] for p in pages.values()),
             license_status=Counter(p["license_status"] for p in pages.values()),
             duplicates=len(_load("duplicates.json", [])),
             annotation_queue=len(_load("queue.json", [])))
    d = json.loads(json.dumps(d))
    _save("dashboard.json", d)
    return d


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    if cmd == "build":
        r = build()
    elif cmd == "discover":
        r = crawler.discover()
        _save("discovery.json", r)
    elif cmd == "pseudo":
        r = dict(pseudo_labelled=annotation_queue.pseudo_label(limit=int(sys.argv[2]) if len(sys.argv) > 2 else 200), queue=len(annotation_queue.build_queue()))
    elif cmd == "export":
        r = annotation_queue.export_yolo()
    else:
        r = dashboard()
    print(json.dumps(r, indent=1, default=str)[:6000])
