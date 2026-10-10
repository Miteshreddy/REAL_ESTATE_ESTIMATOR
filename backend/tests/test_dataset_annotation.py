"""Tasks 1-3: ingestion governance, annotation workflow, leakage-safe splits (temporary dataset; nothing touches real data)."""
from __future__ import annotations

import json
import os

import cv2
import numpy as np
import pytest


@pytest.fixture()
def ds(tmp_path, monkeypatch):
    import annotations as A
    from tn_data_ingestion import dataset_builder as D
    root = tmp_path / "tn_dataset"
    monkeypatch.setattr(D, "DS", str(root))
    monkeypatch.setattr(A, "DS", str(root))
    monkeypatch.setattr(A, "REC", str(root / "annotations" / "records"))
    D.ensure_dirs()
    return D, A, tmp_path


def _png(path, seed=0, size=(900, 700)):
    rng = np.random.default_rng(seed)
    img = np.full((size[1], size[0]), 255, np.uint8)
    for _ in range(10 if min(size) > 300 else 0):
        x, y = int(rng.integers(20, size[0] - 220)), int(rng.integers(20, size[1] - 220))
        cv2.rectangle(img, (x, y), (x + int(rng.integers(60, 200)), y + int(rng.integers(60, 200))), 0, 4)
    cv2.imwrite(str(path), img)
    return str(path)


# ------------------------------------------------------------------ Task 1
def test_ingest_rejects_corrupt_and_tiny_and_is_idempotent(ds):
    D, A, tmp = ds
    bad = tmp / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 truncated garbage")
    tiny = _png(tmp / "tiny.png", size=(16, 14))
    good = _png(tmp / "good.png")
    r1 = D.ingest([str(bad), tiny, good], "user")
    assert r1["added_pages"] == 1 and r1["rejected"] == 2
    r2 = D.ingest([good], "user")
    assert r2["added_pages"] == 0  # repeat runs do not reprocess


def test_restricted_sources_never_training_eligible(ds):
    D, A, tmp = ds
    D.ingest([_png(tmp / "a.png", 1)], "scribd_arch", project_keys=["complex-a"])
    D.ingest([_png(tmp / "b.png", 2)], "non_tn_reference", project_keys=["aparna"])
    D.ingest([_png(tmp / "c.png", 3)], "tnrd", project_keys=["tnrd-x"])
    pages = json.load(open(os.path.join(D.DS, "metadata", "pages.json")))
    assert not any(p["training_eligible"] for p in pages.values())  # third-party, non-TN and pending-licence govt
    D.group_projects()
    sp = D.split()
    assert sp["smoke_test"] == 1 and sp["reference"] == 1 and sp["excluded"] == 1 and sp["tn_train"] == 0


# ------------------------------------------------------------------ Task 3
def test_split_routes_and_freezes_holdout(ds):
    D, A, tmp = ds
    for i in range(12):
        D.ingest([_png(tmp / f"p{i}.png", 10 + i)], "user", project_keys=[f"client-proj-{i}"])
    D.group_projects()
    s1 = D.split()
    assert s1["tn_train"] + s1["tn_validation"] + s1["final_holdout"] == 12
    frozen = json.load(open(os.path.join(D.DS, "metadata", "final_holdout.frozen.json")))["projects"]
    s2 = D.split(seed="another-seed")  # even with a different seed, frozen holdout members do not move
    projects = json.load(open(os.path.join(D.DS, "metadata", "projects.json")))
    assert all(projects[p]["split"] == "final_holdout" for p in frozen)
    man = json.load(open(os.path.join(D.DS, "metadata", "split_manifest.json")))
    assert man["sha256"] and all("reason" in m for m in man["projects"])


# ------------------------------------------------------------------ Task 2
def _page(D, tmp):
    D.ingest([_png(tmp / "plan.png", 99)], "user", project_keys=["client-plan"])
    D.group_projects()
    D.split()
    return next(iter(json.load(open(os.path.join(D.DS, "metadata", "pages.json")))))


def test_annotation_validation(ds):
    D, A, tmp = ds
    pid = _page(D, tmp)
    with pytest.raises(A.AnnotationError, match="invalid bbox"):
        A.save_draft(pid, [dict(id="o1", **{"class": "door"}, bbox=[50, 50, 10, 60])], "Asha")
    with pytest.raises(A.AnnotationError, match="outside"):
        A.save_draft(pid, [dict(id="o1", **{"class": "door"}, bbox=[0, 0, 5000, 60])], "Asha")
    with pytest.raises(A.AnnotationError, match="duplicated"):
        A.save_draft(pid, [dict(id="o1", **{"class": "door"}, bbox=[1, 1, 9, 9]), dict(id="o1", **{"class": "window"}, bbox=[2, 2, 9, 9])], "Asha")
    with pytest.raises(A.AnnotationError, match="needs a unit"):
        A.save_draft(pid, [dict(id="d1", **{"class": "dimension"}, value=3.6)], "Asha")
    with pytest.raises(A.AnnotationError, match="malformed polygon"):
        A.save_draft(pid, [dict(id="r1", **{"class": "room"}, polygon=[[1, 1], [2, 2]])], "Asha")
    with pytest.raises(A.AnnotationError, match="conflicting dimensions"):
        A.save_draft(pid, [dict(id="d1", **{"class": "dimension"}, value=3.6, unit="m", attrs=dict(ref="BED1-W")),
                           dict(id="d2", **{"class": "dimension"}, value=3.9, unit="m", attrs=dict(ref="BED1-W"))], "Asha")
    with pytest.raises(A.AnnotationError, match="human annotator"):
        A.save_draft(pid, [dict(id="o1", **{"class": "door"}, bbox=[1, 1, 9, 9])], "model-unet")


def test_annotation_double_review_and_export(ds):
    D, A, tmp = ds
    pid = _page(D, tmp)
    A.save_draft(pid, [dict(id="o1", **{"class": "door"}, bbox=[10, 10, 40, 30])], "Asha")
    assert A.state(pid) == "IN_REVIEW"
    with pytest.raises(A.AnnotationError, match="other than the annotator"):
        A.review(pid, "Asha", "approve")
    A.review(pid, "Ravi", "approve")
    assert A.state(pid) == "IN_REVIEW"  # one approval is not enough
    with pytest.raises(A.AnnotationError, match="already reviewed"):
        A.review(pid, "Ravi", "approve")
    A.review(pid, "Meena", "approve")
    assert A.state(pid) == "VERIFIED"
    coco = A.export_coco(A.verified_records(training_only=True))
    assert len(coco["images"]) == 1 and coco["annotations"][0]["bbox"] == [10, 10, 30, 20]
    A.save_draft(pid, [dict(id="o1", **{"class": "door"}, bbox=[10, 10, 41, 30])], "Asha", notes="moved edge")
    assert A.state(pid) == "IN_REVIEW" and A.load(pid)["corrections"]  # an edit re-opens review, history kept


def test_rejection_and_disagreement(ds):
    D, A, tmp = ds
    pid = _page(D, tmp)
    A.save_draft(pid, [dict(id="o1", **{"class": "window"}, bbox=[10, 10, 40, 30])], "Asha")
    A.review(pid, "Ravi", "approve")
    A.review(pid, "Meena", "reject", "this is a wardrobe")
    r = A.load(pid)
    assert r["status"] != "VERIFIED" and r.get("disagreement")
    assert not A.verified_records(training_only=False)


def test_pseudo_labels_never_verified(ds):
    D, A, tmp = ds
    pid = _page(D, tmp)
    os.makedirs(os.path.join(D.DS, "pseudo_labels"), exist_ok=True)
    json.dump(dict(model="unet", objects=[{"class": "door", "bbox": [5, 5, 20, 20]}]), open(os.path.join(D.DS, "pseudo_labels", pid + ".json"), "w"))
    assert A.state(pid) == "PSEUDO-LABEL" and not A.verified_records(False)
    r = A.start_from_pseudo(pid, "Asha")
    assert r["status"] == "IN_REVIEW" and r["initialised_from_pseudo"]
