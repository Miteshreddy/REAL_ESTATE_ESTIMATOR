"""Dataset leakage check — exits non-zero on any leak.

Fails if: the same project is in two splits; the same drawing file (SHA-256) is in two splits; a near-identical page
(perceptual hash / text similarity) is in two splits; the same source file name appears in two splits.

Usage: python ml/dataset/check_leakage.py [data/tn_dataset]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from tn_data_ingestion import dedup  # noqa: E402


def check(ds):
    projects = json.load(open(os.path.join(ds, "metadata", "projects.json"), encoding="utf-8"))
    pages = json.load(open(os.path.join(ds, "metadata", "pages.json"), encoding="utf-8"))
    split_of_page = {}
    problems = []
    proj_split = {}
    for sp in ("tn_train", "tn_validation", "final_holdout", "development_benchmark", "smoke_test", "reference", "excluded",
               "train", "validation", "unseen_test"):
        man = os.path.join(ds, sp, "manifest.json")
        if not os.path.exists(man):
            continue
        m = json.load(open(man))
        for pid in m["projects"]:
            if pid in proj_split and proj_split[pid] != sp:
                problems.append(f"project {pid} in {proj_split[pid]} and {sp}")
            proj_split[pid] = sp
        for pg in m["pages"]:
            if pg in split_of_page and split_of_page[pg] != sp:
                problems.append(f"page {pg} in {split_of_page[pg]} and {sp}")
            split_of_page[pg] = sp
    by_sha, by_file = {}, {}
    for pg, sp in split_of_page.items():
        p = pages[pg]
        for key, store, what in ((p["sha256"], by_sha, "file hash"), (p["file"].lower(), by_file, "source file")):
            if key in store and store[key] != sp:
                problems.append(f"same {what} {key[:20]} in {store[key]} and {sp}")
            store.setdefault(key, sp)
    items = [dict(pages[pg], text_sig=set(pages[pg]["text_sig"]), split=sp) for pg, sp in split_of_page.items()]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a["split"] != b["split"]:
                why = dedup.near_duplicate(a, b)
                if why:
                    problems.append(f"near-duplicate {a['page_id']} ({a['split']}) ~ {b['page_id']} ({b['split']}): {why}")
    return dict(ok=not problems, problems=problems, projects=len(proj_split), pages=len(split_of_page),
                splits={s: sum(1 for v in proj_split.values() if v == s) for s in sorted(set(proj_split.values()))})


if __name__ == "__main__":
    r = check(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "tn_dataset"))
    print(json.dumps(r, indent=1)[:4000])
    sys.exit(0 if r["ok"] else 1)
