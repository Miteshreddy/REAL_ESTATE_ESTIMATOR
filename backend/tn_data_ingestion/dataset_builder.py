"""Build the TN construction-drawing dataset: ingest files → pages → projects → purposes → project-level splits.

data/tn_dataset/
  raw/            content-addressed originals (<sha256>.<ext>)
  processed/      page images (<page_id>.png, ≤1600 px)
  projects/       one JSON per project (all fields of §14)
  annotations/    verified/<page_id>.json   (human-verified only)
  pseudo_labels/  <page_id>.json            (model output — NEVER ground truth)
  hard_cases/     pages selected by the active-learning loop
  train/ validation/ unseen_test/   split manifests (page ids, by PROJECT)
  metadata/       pages.json, projects.json, duplicates.json, splits.json, queue.json, dashboard.json
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import cv2

from . import VERSION, dedup, downloader, license_check
from .parsers import classify_text, pages, project_key

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DS = os.path.join(ROOT, "data", "tn_dataset")
SUB = ("raw", "processed", "projects", "annotations/verified", "pseudo_labels", "hard_cases", "train", "validation", "unseen_test", "metadata")
EVAL_PROJECT_HINTS = ("block-a-refuge",)  # projects reserved for evaluation (added to by data/evaluation/tn/manifest.json)


def now():
    return datetime.now().isoformat(timespec="seconds")


def _load(name, default):
    p = os.path.join(DS, "metadata", name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def _save(name, obj):
    json.dump(obj, open(os.path.join(DS, "metadata", name), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)


def ensure_dirs():
    for s in SUB:
        os.makedirs(os.path.join(DS, s), exist_ok=True)


def ingest(paths: list[str], source: str, url: str | None = None, district: str | None = None, city: str | None = None,
           project_keys: list[str] | None = None) -> dict:
    ensure_dirs()
    pages_db = _load("pages.json", {})
    rejected = _load("rejected.json", [])
    added = 0
    for n_, path in enumerate(paths):
        try:
            f = downloader.store_local(path, os.path.join(DS, "raw"))
        except (ValueError, OSError) as e:
            rejected.append(dict(file=os.path.basename(path), reason=f"invalid / unsupported file: {e}"))
            continue
        lic = license_check.status(source, url)
        try:
            page_list = list(pages(f["path"], f["kind"]))
        except Exception as e:  # noqa: BLE001 — corrupt document
            rejected.append(dict(file=os.path.basename(path), sha256=f["sha256"], reason=f"corrupt document: {str(e)[:120]}"))
            continue
        if page_list and min(page_list[0][1].shape[:2]) < 200:
            rejected.append(dict(file=os.path.basename(path), sha256=f["sha256"], reason=f"image too small to be a drawing {page_list[0][1].shape[1]}x{page_list[0][1].shape[0]}"))
            continue
        for no, img, text, method in page_list:
            pid = f"{f['sha256'][:16]}-p{no}"
            if pid in pages_db:
                continue
            meta = classify_text(os.path.basename(path), text)
            cv2.imwrite(os.path.join(DS, "processed", pid + ".png"), img)
            pages_db[pid] = dict(page_id=pid, sha256=f["sha256"], page=no, file=os.path.basename(path), file_type=f["kind"],
                                 source=source, source_url=url, license_status=lic["status"], license_reason=lic["reason"],
                                 collection_date=now(), text_method=method, dhash=dedup.dhash(img),
                                 text_sig=sorted(dedup.text_sig(text)), project_key=project_keys[n_] if project_keys else project_key(path, text),
                                 district=district or meta["district"], city=city, building_type=meta["building_type"],
                                 drawing_type=meta["drawing_type"], discipline=meta["discipline"], scale=meta["scale"],
                                 width=int(img.shape[1]), height=int(img.shape[0]), version=VERSION,
                                 training_eligible=license_check.usable_for(lic["status"], "01_DRAWING_TRAINING"),
                                 evaluation_eligible=license_check.usable_for(lic["status"], "07_UNSEEN_TEST"),
                                 licence_evidence=lic["reason"], attribution=url or source, transformations=["rasterised ≤1600 px (gray)"])
            added += 1
    _save("pages.json", pages_db)
    _save("rejected.json", rejected)
    return dict(added_pages=added, total_pages=len(pages_db), rejected=len(rejected))


def group_projects() -> dict:
    """Project = file-name project key, merged with any other project that shares a (near-)duplicate page."""
    pages_db = _load("pages.json", {})
    parent = {p["project_key"]: p["project_key"] for p in pages_db.values()}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    dups = []
    items = list(pages_db.values())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = dict(items[i], text_sig=set(items[i]["text_sig"])), dict(items[j], text_sig=set(items[j]["text_sig"]))
            why = dedup.near_duplicate(a, b)
            if why:
                dups.append(dict(a=a["page_id"], b=b["page_id"], why=why))
                parent[find(a["project_key"])] = find(b["project_key"])
    projects = {}
    for p in pages_db.values():
        root = find(p["project_key"])
        pr = projects.setdefault(root, dict(project_id="tn-" + hashlib.sha1(root.encode()).hexdigest()[:10], project_name=root, pages=[],
                                            sources=set(), files=set()))
        pr["pages"].append(p["page_id"])
        pr["sources"].add(p["source"])
        pr["files"].add(p["file"])
        p["project_id"] = pr["project_id"]
    out = {}
    for root, pr in projects.items():
        pg = [pages_db[x] for x in pr["pages"]]
        maj = lambda k: max((x[k] for x in pg if x.get(k)), key=lambda v: sum(1 for x in pg if x.get(k) == v), default=None)
        out[pr["project_id"]] = dict(project_id=pr["project_id"], project_name=pr["project_name"], source=sorted(pr["sources"]),
                                     source_url=next((x["source_url"] for x in pg if x.get("source_url")), None), building_type=maj("building_type"),
                                     district=maj("district"), city=maj("city"), drawing_types=sorted({x["drawing_type"] for x in pg}),
                                     disciplines=sorted({x["discipline"] for x in pg}), file_types=sorted({x["file_type"] for x in pg}),
                                     files=sorted(pr["files"]), page_count=len(pg), pages=sorted(pr["pages"]),
                                     scale=maj("scale"), collection_date=min(x["collection_date"] for x in pg),
                                     source_status=maj("license_status"), license_status=maj("license_status"))
        json.dump(out[pr["project_id"]], open(os.path.join(DS, "projects", pr["project_id"] + ".json"), "w"), indent=1)
    _save("pages.json", pages_db)
    _save("projects.json", out)
    _save("duplicates.json", dups)
    return dict(projects=len(out), duplicate_pairs=len(dups))


SPLITS = ("tn_train", "tn_validation", "final_holdout", "development_benchmark", "smoke_test", "reference", "excluded")
SPLIT_POLICY = """Split policy v2 (seed recorded):
- development_benchmark: TN projects already used by evaluation scripts during development (tn_eval sheets). They have been
  looked at while building the system, so they are NOT a credible final holdout and are never trained on.
- smoke_test: third-party copyrighted drawings (e.g. the five-layout complex set) — run blind, no ground truth, never trained on.
- reference: non-Tamil Nadu drawings (Aparna Hyderabad, Uttarakhand, Nalanda) — reference results only.
- excluded: licence review pending / rejected / disallowed — not used at all.
- new training-eligible TN projects: deterministic hash split by PROJECT → tn_train 70 / tn_validation 15 / final_holdout 15.
- final_holdout membership is FROZEN (metadata/final_holdout.frozen.json): members never move, and the holdout is excluded
  from training, threshold tuning and model selection."""


def split(seed="tn-v2", ratios=(0.70, 0.15, 0.15), reserved_eval: list[str] | None = None) -> dict:
    projects = _load("projects.json", {})
    pages = _load("pages.json", {})
    frozen = _load("final_holdout.frozen.json", {"projects": []})
    eval_dir = os.path.join(ROOT, "ml", "test_drawings", "tamilnadu")
    eval_files = {f.lower() for f in os.listdir(eval_dir)} if os.path.isdir(eval_dir) else set()
    splits = {k: [] for k in SPLITS}
    for pid, pr in sorted(projects.items()):
        pg = [pages[x] for x in pr["pages"]]
        lic = {x["license_status"] for x in pg}
        srcs = set(pr["source"])
        if pid in frozen["projects"] and not all(x.get("evaluation_eligible") for x in pg):
            sp, why = "excluded", "frozen holdout member whose licence no longer allows evaluation (removed from holdout, logged)"
            frozen.setdefault("removed", []).append(dict(project=pid, at=now(), reason="licence"))
            frozen["projects"] = [x for x in frozen["projects"] if x != pid]
        elif pid in frozen["projects"]:
            sp, why = "final_holdout", "frozen holdout member"
        elif srcs & {"non_tn_reference"}:
            sp, why = "reference", "not a Tamil Nadu project"
        elif srcs & {"scribd_arch"}:
            sp, why = "smoke_test", "third-party copyrighted drawing — smoke test only"
        elif any(f.lower() in eval_files for f in pr["files"]) or (reserved_eval and pid in reserved_eval):
            sp, why = "development_benchmark", "used by evaluation scripts during development (exposed)"
        elif not all(x.get("training_eligible") for x in pg):
            sp, why = "excluded", f"licence not cleared for training ({', '.join(sorted(lic))})"
        else:
            u = int(hashlib.sha256((seed + pid).encode()).hexdigest(), 16) % 10_000 / 10_000
            sp = "tn_train" if u < ratios[0] else "tn_validation" if u < ratios[0] + ratios[1] else "final_holdout"
            why = f"deterministic project hash split (seed {seed})"
        pr["split"], pr["split_reason"] = sp, why
        splits[sp].append(pid)
    frozen["projects"] = sorted(set(frozen["projects"]) | set(splits["final_holdout"]))
    frozen["sha256"] = hashlib.sha256(json.dumps(frozen["projects"]).encode()).hexdigest()
    _save("final_holdout.frozen.json", frozen)
    for sp, ids in splits.items():
        os.makedirs(os.path.join(DS, sp), exist_ok=True)
        json.dump(dict(projects=ids, pages=[pg for i in ids for pg in projects[i]["pages"]]), open(os.path.join(DS, sp, "manifest.json"), "w"), indent=1)
    _save("projects.json", projects)
    manifest = [dict(project_id=pid, split=pr["split"], reason=pr["split_reason"], sheets=pr["pages"],
                     hashes=sorted({pages[x]["sha256"] for x in pr["pages"]}), license=pr.get("license_status")) for pid, pr in projects.items()]
    _save("split_manifest.json", dict(seed=seed, ratios=ratios, policy=SPLIT_POLICY, created=now(), projects=manifest,
                                      sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()))
    _save("splits.json", dict(seed=seed, ratios=ratios, created=now(), counts={k: len(v) for k, v in splits.items()}))
    return {k: len(v) for k, v in splits.items()}
