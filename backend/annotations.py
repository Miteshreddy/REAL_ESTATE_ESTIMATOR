"""Human annotation workflow for Tamil Nadu drawings (label schema v1).

States:  UNANNOTATED → PSEUDO-LABEL (model output, never ground truth) → IN_REVIEW (human draft) → VERIFIED | REJECTED
VERIFIED requires approval by TWO different reviewers (neither the annotator); a reviewer rejection or a disagreement keeps the
record out of the verified set. Only VERIFIED records on training-eligible pages may be exported for training.

Record (data/tn_dataset/annotations/records/<page_id>.json):
  annotation_id, page_id, project_id, sheet_sha256, schema_version, status, annotator, created, updated,
  reviews: [{reviewer, decision: approve|reject, at, note}], corrections: [{by, at, note}], notes,
  objects: [{id, class, bbox?: [x0,y0,x1,y1] px, polygon?: [[x,y]…] px, value?, unit?, attrs?: {}}]
"""
from __future__ import annotations

import json
import os
import uuid
from collections import Counter, defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "data", "tn_dataset")
REC = os.path.join(DS, "annotations", "records")
SCHEMA_VERSION = "tn-annot-1"
STATES = ("UNANNOTATED", "PSEUDO-LABEL", "IN_REVIEW", "VERIFIED", "REJECTED")
ARCH = ["room", "wall", "wall_centerline", "door", "window", "door_swing", "stair", "lift", "column", "dimension", "scale", "floor_label",
        "unit_boundary", "open_area", "courtyard", "common_space", "room_label"]
STRUCT = ["beam", "slab", "footing", "foundation", "rebar_schedule", "bar_mark", "structural_dimension", "drawing_reference"]
CLASSES = ARCH + STRUCT
NEEDS_UNIT = {"dimension", "structural_dimension", "scale"}
REQUIRED_REVIEWS = 2


class AnnotationError(ValueError):
    pass


def now():
    return datetime.now().isoformat(timespec="seconds")


def _meta(name, default):
    p = os.path.join(DS, "metadata", name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def path(page_id):
    return os.path.join(REC, os.path.basename(page_id) + ".json")


def load(page_id):
    p = path(page_id)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def state(page_id) -> str:
    r = load(page_id)
    if r:
        return r["status"]
    return "PSEUDO-LABEL" if os.path.exists(os.path.join(DS, "pseudo_labels", page_id + ".json")) else "UNANNOTATED"


def validate(rec: dict, pages: dict | None = None) -> list[str]:
    pages = pages if pages is not None else _meta("pages.json", {})
    errs = []
    pg = pages.get(rec.get("page_id"))
    if not pg:
        return [f"unknown page {rec.get('page_id')}"]
    if rec.get("project_id") and pg.get("project_id") and rec["project_id"] != pg["project_id"]:
        errs.append(f"project_id {rec['project_id']} does not match the page's project {pg['project_id']}")
    if rec.get("sheet_sha256") and rec["sheet_sha256"] != pg["sha256"]:
        errs.append("annotation is attached to a different drawing revision (sheet hash mismatch)")
    W, H = pg["width"], pg["height"]
    seen = set()
    dims = defaultdict(list)
    for o in rec.get("objects", []):
        oid = o.get("id")
        if not oid:
            errs.append("object without id")
        elif oid in seen:
            errs.append(f"duplicated annotation id {oid}")
        seen.add(oid)
        if o.get("class") not in CLASSES:
            errs.append(f"{oid}: unknown class {o.get('class')}")
        if "bbox" in o:
            b = o["bbox"]
            if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)):
                errs.append(f"{oid}: malformed bbox")
            elif not (b[0] < b[2] and b[1] < b[3]):
                errs.append(f"{oid}: invalid bbox (x0<x1, y0<y1 required)")
            elif b[0] < 0 or b[1] < 0 or b[2] > W or b[3] > H:
                errs.append(f"{oid}: bbox outside the {W}x{H} page image")
        if "polygon" in o:
            pts = o["polygon"]
            if not (isinstance(pts, list) and len(pts) >= 3 and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in pts)):
                errs.append(f"{oid}: malformed polygon (≥3 [x,y] points)")
            elif any(not (0 <= x <= W and 0 <= y <= H) for x, y in pts):
                errs.append(f"{oid}: polygon outside the page image")
            else:
                a = 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))))
                if a <= 0:
                    errs.append(f"{oid}: degenerate polygon (zero area)")
        if "bbox" not in o and "polygon" not in o and "value" not in o:
            errs.append(f"{oid}: needs bbox, polygon or value")
        if o.get("class") in NEEDS_UNIT:
            if o.get("value") is None:
                errs.append(f"{oid}: {o.get('class')} needs a value")
            if not o.get("unit"):
                errs.append(f"{oid}: {o.get('class')} needs a unit")
            if o.get("attrs", {}).get("ref"):
                dims[o["attrs"]["ref"]].append((o.get("value"), o.get("unit")))
    for ref, vals in dims.items():
        if len({(float(v), u) for v, u in vals if v is not None}) > 1:
            errs.append(f"conflicting dimensions for {ref}: {vals}")
    return errs


def save_draft(page_id, objects, annotator, notes="", from_pseudo=False) -> dict:
    """Create / update a human draft (IN_REVIEW). Editing a VERIFIED record re-opens review (corrections are logged)."""
    pages = _meta("pages.json", {})
    pg = pages.get(page_id)
    if not pg:
        raise AnnotationError(f"unknown page {page_id}")
    if not annotator or annotator.lower().startswith("model") or annotator.lower().startswith("pseudo"):
        raise AnnotationError("an annotation draft needs a named human annotator")
    rec = load(page_id) or dict(annotation_id=uuid.uuid4().hex[:12], page_id=page_id, project_id=pg.get("project_id"),
                                sheet_sha256=pg["sha256"], schema_version=SCHEMA_VERSION, created=now(), reviews=[], corrections=[])
    if rec.get("status") in ("VERIFIED", "IN_REVIEW", "REJECTED") and rec.get("objects") is not None:
        rec["corrections"].append(dict(by=annotator, at=now(), note=notes or "objects edited", previous_status=rec.get("status")))
    rec.update(objects=objects, annotator=annotator, updated=now(), status="IN_REVIEW", reviews=[], notes=notes,
               initialised_from_pseudo=bool(from_pseudo or rec.get("initialised_from_pseudo")))
    errs = validate(rec, pages)
    if errs:
        raise AnnotationError("; ".join(errs[:10]))
    os.makedirs(REC, exist_ok=True)
    json.dump(rec, open(path(page_id), "w", encoding="utf-8"), indent=1)
    return rec


def start_from_pseudo(page_id, annotator) -> dict:
    """Copy model pseudo labels into a human draft — the draft still needs full human review."""
    p = os.path.join(DS, "pseudo_labels", page_id + ".json")
    if not os.path.exists(p):
        raise AnnotationError("no pseudo labels for this page")
    ps = json.load(open(p))
    objs = [dict(id=f"o{i + 1}", **{k: v for k, v in o.items() if k in ("class", "bbox", "polygon")}) for i, o in enumerate(ps["objects"])]
    return save_draft(page_id, objs, annotator, notes=f"initialised from pseudo labels ({ps.get('model')}) — every object must be checked",
                      from_pseudo=True)


def review(page_id, reviewer, decision, note="") -> dict:
    rec = load(page_id)
    if not rec:
        raise AnnotationError("nothing to review")
    if rec["status"] not in ("IN_REVIEW",):
        raise AnnotationError(f"record is {rec['status']}, not IN_REVIEW")
    if not reviewer or reviewer == rec.get("annotator"):
        raise AnnotationError("the reviewer must be a named person other than the annotator")
    if any(r["reviewer"] == reviewer for r in rec["reviews"]):
        raise AnnotationError("this reviewer has already reviewed the current version")
    if decision not in ("approve", "reject"):
        raise AnnotationError("decision must be approve or reject")
    errs = validate(rec)
    if decision == "approve" and errs:
        raise AnnotationError("cannot approve an invalid annotation: " + "; ".join(errs[:5]))
    rec["reviews"].append(dict(reviewer=reviewer, decision=decision, at=now(), note=note))
    dec = [r["decision"] for r in rec["reviews"]]
    if "reject" in dec and "approve" in dec:
        rec["disagreement"] = True  # needs resolution: annotator corrects → new draft → fresh reviews
    if dec.count("reject") >= 1 and len(dec) >= REQUIRED_REVIEWS and "approve" not in dec:
        rec["status"] = "REJECTED"
    elif dec.count("approve") >= REQUIRED_REVIEWS:
        rec["status"] = "VERIFIED"
        rec["verified_at"] = now()
    rec["updated"] = now()
    json.dump(rec, open(path(page_id), "w", encoding="utf-8"), indent=1)
    return rec


def verified_records(training_only=True) -> list[dict]:
    pages = _meta("pages.json", {})
    out = []
    if not os.path.isdir(REC):
        return out
    for f in os.listdir(REC):
        r = json.load(open(os.path.join(REC, f), encoding="utf-8"))
        pg = pages.get(r["page_id"], {})
        if r["status"] != "VERIFIED" or validate(r, pages):
            continue
        if training_only and not pg.get("training_eligible"):
            continue
        out.append(r)
    return out


def coverage() -> dict:
    pages = _meta("pages.json", {})
    projects = _meta("projects.json", {})
    by_proj, by_class = defaultdict(Counter), defaultdict(Counter)
    for pid, pg in pages.items():
        st = state(pid)
        by_proj[pg.get("project_id")][st] += 1
        r = load(pid)
        if r:
            for o in r.get("objects", []):
                by_class[o["class"]][r["status"]] += 1
    return dict(states=Counter(state(p) for p in pages), by_project={k: dict(v) for k, v in by_proj.items()},
                by_class={k: dict(v) for k, v in by_class.items()},
                verified_training_records=len(verified_records(True)), verified_records_any=len(verified_records(False)),
                projects=len(projects), schema_version=SCHEMA_VERSION)


def export_coco(records: list[dict], classes=CLASSES) -> dict:
    pages = _meta("pages.json", {})
    cats = [dict(id=i + 1, name=c) for i, c in enumerate(classes)]
    cid = {c: i + 1 for i, c in enumerate(classes)}
    images, anns = [], []
    for k, r in enumerate(records):
        pg = pages[r["page_id"]]
        images.append(dict(id=k + 1, file_name=r["page_id"] + ".png", width=pg["width"], height=pg["height"], project_id=r["project_id"]))
        for o in r["objects"]:
            if o["class"] not in cid or ("bbox" not in o and "polygon" not in o):
                continue
            if "bbox" in o:
                x0, y0, x1, y1 = o["bbox"]
            else:
                xs, ys = [p[0] for p in o["polygon"]], [p[1] for p in o["polygon"]]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            anns.append(dict(id=len(anns) + 1, image_id=k + 1, category_id=cid[o["class"]], bbox=[x0, y0, x1 - x0, y1 - y0], area=(x1 - x0) * (y1 - y0),
                             iscrowd=0, segmentation=[sum(o["polygon"], [])] if "polygon" in o else []))
    return dict(info=dict(schema=SCHEMA_VERSION, created=now(), note="VERIFIED annotations only"), images=images, annotations=anns, categories=cats)


def export_measurements(records: list[dict]) -> list[dict]:
    """Dimensions / structural values (structured JSON, not boxes)."""
    return [dict(page_id=r["page_id"], project_id=r["project_id"], **{k: o.get(k) for k in ("id", "class", "value", "unit", "attrs")})
            for r in records for o in r["objects"] if o.get("value") is not None]
