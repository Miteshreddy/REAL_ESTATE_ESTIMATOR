"""Generate the machine-readable part of reports_v2/ (manifests, inventories, logs, facts.json) from files on disk.

    python ml/evaluation/build_reports_v2.py

Recomputes every count from the repository, tn_corpus/registry and data/tn_dataset; nothing is copied from older
reports without being re-derived. The narrative Markdown reports cite reports_v2/evidence/facts.json.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R2 = os.path.join(ROOT, "reports_v2")
REG = os.path.join(ROOT, "tn_corpus", "registry")
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".claude"}
BULK_DIRS = ("tn_corpus/pages", "tn_corpus/thumbs", "tn_corpus/ocr_cache", "tn_corpus/pseudo_labels", "data/tn_dataset/processed",
             "data/tn_dataset/raw", "data/tn_dataset/pseudo_labels", "data/tn_dataset/yolo", "data/previews", "ml/test_drawings",
             "tn_corpus/sources/zip_v2", "data/tnpwd/cache", "runs")
SELF = "ml/evaluation/build_reports_v2.py"  # contains the scanner pattern itself
SECRET_RX = re.compile(r"(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}", re.I)


def sh(*a):
    try:
        return subprocess.run(a, cwd=ROOT, capture_output=True, text=True, timeout=120).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"ERROR {e}"


def sha(p, limit=300 * 1024 * 1024):
    if os.path.getsize(p) > limit:
        return "SKIPPED_LARGE"
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def wcsv(name, rows, cols=None):
    p = os.path.join(R2, "manifests", name) if not os.path.isabs(name) else name
    cols = cols or (list(rows[0].keys()) if rows else ["empty"])
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in r.items()})


def rcsv(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []


def classify_path(rel: str) -> tuple[str, str, str]:
    """(category, lifecycle, role) for a repository path — rules, explained in 03_CODEBASE_INVENTORY.md."""
    r = rel.replace("\\", "/")
    n = os.path.basename(r)
    if r.startswith("backend/tests/"):
        return "test", "active", "pytest suite"
    if r.startswith("backend/tnpwd_ingestion/"):
        return "source", "active", "TN PWD document ingestion / rate analysis"
    if r.startswith("backend/tn_data_ingestion/"):
        return "source", "active", "TN drawing dataset builder (data/tn_dataset)"
    if r.startswith("backend/") and n.endswith(".py"):
        dev = {"accuracy_eval.py", "aparna_regression.py", "benchmark.py", "commercial_eval.py", "opening_ab.py", "real_eval.py",
               "tn_eval.py"}
        return "source", "evaluation/dev script" if n in dev else "active", "backend module"
    if r.startswith("frontend/"):
        return "source", "active", "web UI"
    if r.startswith("ml/training/"):
        return "source", "offline", "training / import script"
    if r.startswith("ml/evaluation/") or r.startswith("ml/dataset/"):
        return "source", "offline", "evaluation / audit script"
    if r.startswith("tn_corpus/scripts/"):
        return "source", "offline", "TN corpus acquisition / build"
    if r.startswith("tn_corpus/raw_candidates/") and n.endswith(".pdf"):
        return "dataset", "quarantine", "acquired candidate PDF (REVIEW_REQUIRED)"
    if r.startswith("tn_corpus/raw_candidates/"):
        return "dataset", "quarantine", "acquisition sidecar metadata"
    if r.startswith("tn_corpus/"):
        return "dataset", "active", "TN corpus registry / logs / supplied files"
    if r.startswith("data/models/"):
        if n in ("models_v3.joblib", "models_v4.joblib"):
            return "model", "historical (not loaded: ml.py MODEL_VERSION=5)", "older classifier bundle"
        if n.endswith(".pt"):
            return "model", "training checkpoint", "PyTorch weights (inference uses ONNX)"
        return "model", "active", "model artifact / registry"
    if r.startswith("ml/weights/"):
        return "model", "training checkpoint", "U-Net PyTorch weights"
    if r in ("yolov8s.pt", "weights/yolo26n.pt"):
        return "model", "pretrained base weights", "Ultralytics base checkpoint (not used at inference)"
    if r.startswith("data/tn_dataset/"):
        return "dataset", "active", "TN dataset (split v2)"
    if r.startswith("data/tnpwd/"):
        return "dataset", "active", "TN PWD documents / maps / store"
    if r.startswith("data/evaluation/") or r.startswith("ml/metrics/") or r.startswith("ml/ground_truth/"):
        return "evaluation", "active", "evaluation results / ground truth"
    if r.startswith("data/samples/"):
        return "dataset", "active", "synthetic sample drawings (generator output)"
    if r.startswith("data/previews/"):
        return "runtime", "generated", "UI preview renders"
    if r == "data/estimate.db" or ".db." in n or n.endswith(".bak"):
        return "runtime", "active database / backups", "SQLite application DB (not archived: may hold user projects)"
    if r.startswith("data/") and n.endswith(".png") and re.match(r"(dbg_|dl_|t[._]|t3_|planbox|real_|tn_)", n):
        return "scratch", "debug output", "debug render from earlier sessions"
    if r.startswith("data/") and n.endswith((".json", ".log")):
        return "evaluation", "historical", "earlier evaluation output"
    if r.startswith("reports/"):
        return "report", "historical (2026-10-09 completion run)", "previous report set"
    if r.startswith("runs/"):
        return "scratch", "experiment output", "Ultralytics validation runs"
    if r.startswith("tools/"):
        return "tool", "active", "bundled LibreDWG (DWG→DXF)"
    if n.endswith(".md"):
        return "report", "historical" if n != "README.md" else "active", "root-level document"
    if r.startswith("configs/"):
        return "config", "active", "training config"
    return "other", "unknown", ""


def repo_inventory():
    tracked = set(sh("git", "ls-files").splitlines())
    status = {}
    for line in sh("git", "status", "--porcelain", "--untracked-files=all", ".").splitlines():
        p = line[3:].strip().strip('"')
        if p.startswith("../"):
            continue
        status[p.replace("Desktop/assignment/real estate/", "")] = line[:2]
    rows, bulk = [], defaultdict(lambda: dict(files=0, bytes=0))
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        relp = os.path.relpath(dp, ROOT).replace("\\", "/")
        if relp.startswith("reports_v2"):
            continue
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            sz = os.path.getsize(p)
            b = next((d for d in BULK_DIRS if rel.startswith(d + "/")), None)
            if b:
                bulk[b]["files"] += 1
                bulk[b]["bytes"] += sz
                continue
            cat, life, role = classify_path(rel)
            git = "tracked" if rel in tracked else "untracked"
            if status.get(rel, "").strip() in ("M", "MM", "AM"):
                git = "tracked-modified"
            secret = ""
            if fn.endswith((".py", ".js", ".json", ".md", ".yaml", ".bat", ".txt", ".env")) and sz < 2_000_000 and rel != SELF:
                try:
                    secret = "POSSIBLE_SECRET" if SECRET_RX.search(open(p, encoding="utf-8", errors="ignore").read()) else ""
                except OSError:
                    pass
            rows.append(dict(path=rel, ext=os.path.splitext(fn)[1].lower(), bytes=sz, sha256=sha(p), git=git, category=cat, lifecycle=life,
                             role=role, secret_scan=secret))
    for p, st in status.items():
        if st.strip() == "D":
            rows.append(dict(path=p, ext=os.path.splitext(p)[1], bytes=0, sha256="", git="tracked-DELETED-uncommitted", category="dataset",
                             lifecycle="removed from working tree (split v1 manifest superseded by split v2)", role="", secret_scan=""))
    for d, v in sorted(bulk.items()):
        rows.append(dict(path=d + "/**", ext="(bulk)", bytes=v["bytes"], sha256="per-file hashes in tn_corpus/registry or data/tn_dataset/metadata",
                         git="mixed/ignored", category="bulk", lifecycle="derived/bulk", role=f"{v['files']} files", secret_scan=""))
    return sorted(rows, key=lambda r: r["path"])


def tests():
    jx = os.path.join(R2, "evidence", "pytest_junit.xml")
    if not os.path.exists(jx):
        return {}
    t = ET.parse(jx).getroot()
    s = t if t.tag == "testsuite" else t.find("testsuite")
    cases = [dict(file=c.get("classname"), name=c.get("name"), time=c.get("time"),
                  result="failed" if c.find("failure") is not None or c.find("error") is not None else "skipped" if c.find("skipped") is not None else "passed")
             for c in s.iter("testcase")]
    return dict(tests=int(s.get("tests")), failures=int(s.get("failures")), errors=int(s.get("errors")), skipped=int(s.get("skipped")),
                time_s=float(s.get("time")), timestamp=s.get("timestamp"), by_file=dict(Counter(c["file"] for c in cases)), cases=cases)


CATS = [("Multi-storey apartments", r"multi_storey_apartment|apartment|high_rise|housing"), ("Hospitals", r"hospital"),
        ("Medical colleges", r"medical_college"), ("Universities", r"universit"), ("Colleges", r"(?<!medical_)college"),
        ("Commercial buildings", r"commercial|shop|warehouse"), ("Hostels", r"hostel"), ("Schools", r"school|anganwadi"),
        ("Government offices", r"office|panchayat"), ("Residential houses", r"\bhouse\b|residential"),
        ("Public/institutional buildings", r"community|library|shelter|shed|cooperative|open_structure|sanitation|institutional"),
        ("Structural drawing packages", r"structural")]


def coverage(projects, pages, sources_v2, sources_v1_cat):
    rows = []
    for name, rx in CATS:
        leads = sum(1 for s in sources_v2 if re.search(rx, s["category"], re.I))
        disc = sum(1 for s in sources_v2 if re.search(rx, s["category"], re.I) and s["source_type"].startswith("DIRECT_PDF"))
        if name in ("Schools", "Government offices", "Residential houses", "Public/institutional buildings"):
            leads += sum(1 for c in sources_v1_cat if re.search(rx, c["category_hint"], re.I))
        P = [p for p in projects if re.search(rx, p["building_category"], re.I)]
        pid = {p["project_id"] for p in P}
        pg = [x for x in pages if x["project_id"] in pid]
        arch = sum(1 for x in pg if x["drawing_type"] == "architectural_floor_plan")
        struct = sum(1 for x in pg if x["drawing_type"] in ("structural_ga", "foundation", "column_schedule", "beam_schedule", "slab_plan", "reinforcement_bbs"))
        sched = sum(1 for x in pg if x["drawing_type"] in ("column_schedule", "beam_schedule", "reinforcement_bbs"))
        indep = sum(1 for p in P if p.get("project_nature") == "independent_real_project")
        rows.append(dict(category=name, source_leads=leads, direct_documents_listed=disc,
                         downloaded_unique_files=len({f for p in P for f in json.loads(p["files"])}), projects_or_documents=len(P),
                         independent_real_projects=indep, drawing_sheets=sum(int(p["drawing_pages"]) for p in P),
                         architectural_plan_pages=arch, structural_pages=struct, schedule_pages=sched, projects_with_boq=0,
                         permission_confirmed=0, training_eligible=0, final_evaluation_eligible=0, verified_annotations=0,
                         project_keys=[p["project_key"] for p in P]))
    return rows


NATURE = [  # (regex on project_key, nature) — documented in 05/07 reports
    (r"^tnrd:buildings_handbook$", "handbook (reference document containing type designs + generic details)"),
    (r"^tnrd:roads", "out-of-scope handbook (roads & bridges)"),
    (r"^tnrd:", "standard type design (generic, no site)"),
    (r"12144929|12248530|12248522|1000045200|12389417|10421923", "development-finance survey/report (may contain plans of real projects)"),
    (r"Completion-Report", "programme report"),
    (r"Tamil-Nadu-Combined|_TNRERA", "rules / registry listing (no drawings)"),
    (r"EOI_for|Minutes-22nd", "project context document (no working drawings)"),
    (r"ApprovedPlan", "independent_real_project"),
    (r"SIPCOT-RFP|hostels-pre-bid", "tender/RFP document (real project)"),
    (r"KRR_final", "hospital document (real building)"),
]


def nature(key):
    return next((n for rx, n in NATURE if re.search(rx, key)), "UNKNOWN")


def main():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for d in ("manifests", "logs", "diagrams", "evidence", "scratch_archive"):
        os.makedirs(os.path.join(R2, d), exist_ok=True)
    git = dict(branch=sh("git", "rev-parse", "--abbrev-ref", "HEAD"), commit=sh("git", "rev-parse", "HEAD"),
               uncommitted=[l for l in sh("git", "status", "--porcelain", ".").splitlines() if not l[3:].startswith("../")][:200])
    inv = repo_inventory()
    wcsv("repository_file_inventory.csv", inv)
    scratch = [r for r in inv if r["category"] in ("scratch",) or r["lifecycle"].startswith(("historical", "debug", "experiment", "training checkpoint", "pretrained"))
               or r["git"] == "tracked-DELETED-uncommitted" or r["category"] == "evaluation"]
    wcsv(os.path.join(R2, "scratch_archive", "scratch_inventory.csv"), scratch)
    # light-weight historical docs/logs copied (originals untouched)
    copied = []
    for rel in ("ACCURACY_REPORT.md", "TN_ESTIMATOR_FINAL_REPORT.md", "data/accuracy_eval.log", "ml/metrics/train.log", "ml/metrics/history.json",
                "reports/tn_completion/FINAL_COMPLETION_REPORT.md", "reports/tn_completion/task_ledger.json", "reports/tn_completion/final_eval_run.log",
                "data/models/opening_det.metrics.json", "data/models/opening_det.resolution_eval.json", "tn_corpus/DATASET_BUILD_REPORT.md"):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p) and os.path.getsize(p) < 3_000_000:
            dst = os.path.join(R2, "scratch_archive", rel.replace("/", "__"))
            shutil.copy2(p, dst)
            copied.append(dict(original=rel, copy=os.path.relpath(dst, ROOT).replace("\\", "/"), bytes=os.path.getsize(p), sha256=sha(p)))
    # corpus manifests
    proj = rcsv(os.path.join(REG, "project_manifest.csv"))
    for p in proj:  # identity comes from tn_corpus/scripts/build_corpus.py PROJECT_META (title-block evidence); fallback rules
        if not p.get("project_nature") or p["project_nature"] == "UNKNOWN":
            p["project_nature"] = nature(p["project_key"])
    pages = rcsv(os.path.join(REG, "page_inventory.csv"))
    files = rcsv(os.path.join(REG, "file_inventory.csv"))
    dups = rcsv(os.path.join(REG, "duplicates.csv"))
    v2acq = rcsv(os.path.join(REG, "catalog_v2_acquisition.csv"))
    v2cat = rcsv(os.path.join(ROOT, "tn_corpus", "sources", "zip_v2", "TN_High_Impact_Architecture_Corpus", "04_SOURCE_CATALOGS", "expanded_source_catalog.csv"))
    v1cat = rcsv(os.path.join(ROOT, "tn_corpus", "catalog", "tnrd_type_design_catalog.csv"))
    deriv = rcsv(os.path.join(REG, "zip_v2_derivatives.csv"))
    wcsv("project_manifest.csv", proj)
    wcsv("page_inventory.csv", pages)
    wcsv("dataset_file_inventory.csv", files)
    shutil.copy2(os.path.join(REG, "source_registry.csv"), os.path.join(R2, "manifests", "document_source_registry.csv"))
    shutil.copy2(os.path.join(REG, "license_review_queue.csv"), os.path.join(R2, "manifests", "licence_review_queue.csv"))
    shutil.copy2(os.path.join(REG, "annotation_queue.csv"), os.path.join(R2, "manifests", "annotation_queue.csv"))
    shutil.copy2(os.path.join(REG, "split_audit.json"), os.path.join(R2, "manifests", "split_audit.json"))
    shutil.copy2(os.path.join(REG, "dataset_build_summary.json"), os.path.join(R2, "manifests", "dataset_build_summary.json"))
    if deriv:
        wcsv("zip_v2_derivative_inventory.csv", deriv)
    # duplicates review table
    dup_rows = []
    for d in dups:
        kind = ("declared derivation" if "declared" in d["reason"] else "rotated re-save" if "rotated" in d["reason"] else
                "related standard-design variant" if "text similarity" in d["reason"] else "near-identical render")
        dup_rows.append(dict(d, relationship=kind, recommended_action="keep both; link (derived copy is not counted)" if kind != "related standard-design variant"
                             else "keep both as separate designs; same project group for split purposes", reviewer_status="NOT_REVIEWED"))
    for f in files:
        if f.get("duplicate_of_file"):
            dup_rows.append(dict(page_a="(file)", file_a=f["file_name"], page_b="(file)", file_b=f["duplicate_of_file"], reason="identical SHA-256",
                                 relationship="exact duplicate file", recommended_action="keep one copy; record both sources", reviewer_status="AUTO (identical bytes)"))
    wcsv("duplicate_inventory.csv", dup_rows, ["relationship", "file_a", "page_a", "file_b", "page_b", "reason", "recommended_action", "reviewer_status"])
    # drawing category manifest (per page)
    pk = {p["project_id"]: p for p in proj}
    wcsv("drawing_category_manifest.csv", [dict(page_id=x["page_id"], project_id=x["project_id"], building_category=pk.get(x["project_id"], {}).get("building_category"),
                                                project_nature=pk.get(x["project_id"], {}).get("project_nature"), file=x["file_name"], page=x["page_no"],
                                                drawing_type=x["drawing_type"], confidence=x["classification_confidence"], content=x["content"],
                                                text_method=x.get("text_method")) for x in pages])
    cov = coverage(proj, pages, v2cat, v1cat)
    wcsv("category_coverage.csv", cov)
    # model registry snapshot
    reg_json = json.load(open(os.path.join(ROOT, "data", "models", "registry.json"), encoding="utf-8"))
    arts = [dict(path=f"data/models/{fn}", bytes=os.path.getsize(os.path.join(ROOT, "data", "models", fn)), sha256=sha(os.path.join(ROOT, "data", "models", fn)))
            for fn in sorted(os.listdir(os.path.join(ROOT, "data", "models")))]
    for extra in ("ml/weights/floorplan_unet_r34.pt", "yolov8s.pt", "weights/yolo26n.pt"):
        if os.path.exists(os.path.join(ROOT, extra)):
            arts.append(dict(path=extra, bytes=os.path.getsize(os.path.join(ROOT, extra)), sha256=sha(os.path.join(ROOT, extra))))
    json.dump(dict(snapshot_at=now, registry=reg_json, artifacts=arts), open(os.path.join(R2, "manifests", "model_registry_snapshot.json"), "w"), indent=1)
    T = tests()
    json.dump(dict(run_at=T.get("timestamp"), command="python -m pytest backend/tests -q -rA --junitxml=reports_v2/evidence/pytest_junit.xml",
                   python=platform.python_version(), **T), open(os.path.join(R2, "manifests", "test_run_manifest.json"), "w"), indent=1)
    # artifact inventory = everything non-source
    wcsv("project_artifact_inventory.csv", [r for r in inv if r["category"] not in ("source", "test")])
    # logs
    shutil.copy2(os.path.join(ROOT, "tn_corpus", "logs", "fetch_decisions.jsonl"), os.path.join(R2, "logs", "acquisition_log.jsonl"))
    with open(os.path.join(R2, "logs", "dataset_discovery.log"), "w", encoding="utf-8") as f:
        for fn in ("download_run.txt", "build_run_v2.txt"):
            p = os.path.join(ROOT, "tn_corpus", "logs", fn)
            if os.path.exists(p):
                f.write(f"===== tn_corpus/logs/{fn}\n" + open(p, encoding="utf-8", errors="replace").read() + "\n")
        f.write("===== v2 catalogue acquisition (tn_corpus/registry/catalog_v2_acquisition.csv)\n")
        for r in v2acq:
            f.write(f"{r['source_id']}\t{r['acquisition_state']}\t{r.get('bytes') or r.get('reason') or r.get('duplicate_of')}\t{r['url']}\n")
    with open(os.path.join(R2, "logs", "validation_log.jsonl"), "w", encoding="utf-8") as f:
        for x in files:
            f.write(json.dumps(dict(file=x["file_name"], role=x["role"], sha256=x["sha256"], bytes=x["bytes"], extraction_status=x["extraction_status"],
                                    duplicate_of=x.get("duplicate_of_file"), usage_state=x.get("usage_state")), ensure_ascii=False) + "\n")
    # facts
    s = json.load(open(os.path.join(REG, "dataset_build_summary.json")))
    nat = Counter(p["project_nature"] for p in proj)
    ds_split = json.load(open(os.path.join(ROOT, "data", "tn_dataset", "metadata", "splits.json")))
    sc = json.load(open(os.path.join(ROOT, "data", "evaluation", "tn", "scorecard.json"), encoding="utf-8"))
    corpus_bytes = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(os.path.join(ROOT, "tn_corpus")) for f in fs)
    facts = dict(generated=now, git=git, python=platform.python_version(), platform=platform.platform(), corpus=s["headline"],
                 drawing_types=s["drawing_types"], usage_states=s["usage_states"], project_nature=dict(nat),
                 v2_catalogue=dict(entries=len(v2cat), auto_download_rows=sum(1 for r in v2cat if r["include_in_auto_download"] == "YES_IF_ROBOTS_ALLOW"),
                                   attempted=len(v2acq), outcomes=dict(Counter(r["acquisition_state"] for r in v2acq))),
                 zip_derivatives=dict(assets=len(deriv), checks=dict(Counter(d.get("provenance_check") for d in deriv))),
                 corpus_storage_bytes=corpus_bytes, repo_files=len([r for r in inv if r["ext"] != "(bulk)"]),
                 repo_categories=dict(Counter(r["category"] for r in inv)), scratch_items=len(scratch), scratch_copied=copied,
                 possible_secrets=[r["path"] for r in inv if r["secret_scan"]], tests={k: v for k, v in T.items() if k != "cases"},
                 tn_dataset_splits=ds_split, scorecard_final=sc.get("final") or sc.get("verdict"),
                 scorecard_gates={g["id"]: dict(name=g["name"], status=g["status"], value=g.get("value")) for g in sc.get("gates", [])},
                 coverage=cov)
    json.dump(facts, open(os.path.join(R2, "evidence", "facts.json"), "w"), indent=1, default=str)
    print(json.dumps({k: facts[k] for k in ("corpus", "project_nature", "v2_catalogue", "zip_derivatives", "repo_files", "scratch_items",
                                            "possible_secrets", "tests", "scorecard_final")}, indent=1, default=str)[:6000])


if __name__ == "__main__":
    sys.exit(main())
