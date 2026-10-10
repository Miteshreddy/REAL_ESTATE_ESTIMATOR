"""Idempotent TN drawing-corpus builder:  python tn_corpus/scripts/build_corpus.py [--report-dir DIR]

Inputs (never modified): supplied PDFs (copied byte-identical into supplied/), quarantined candidates (raw_candidates/),
optional local seed folder. Outputs: registry/*.csv|json, pages/ (150 dpi renders), thumbs/, pseudo_labels/, reports.
Nothing is ever marked APPROVED_*: only a human with rights evidence can set that (registry/approvals.csv, see README).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import cv2
import numpy as np
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(REPO, "backend"))
from tn_data_ingestion import dedup  # noqa: E402  (shared dHash / text-signature logic)

DL = os.path.join(os.path.expanduser("~"), "Downloads")
SUPPLIED = [  # (file in Downloads, role, source_class, note)
    ("Buildings.pdf", "original_handbook", "user_supplied_official_copy",
     "TNRD Buildings handbook (also listed on the TNRD catalogue as buildings_design/Buildings.pdf)"),
    ("TN_Type_Design_Drawings_Extract.pdf", "derived_extract", "user_supplied_derived",
     "21-page extract of handbook pages 313-333 (derived; duplicates of handbook pages)"),
    ("_TNRERA.pdf", "registry_listing", "user_supplied_official_copy",
     "TN RERA project-registration listing printout (text table; no drawings expected)"),
]
SEED_DIR = r"G:\velo\real-estate\drawings\tamilnadu"
DPI = 150
STOPWORDS = {"the", "of", "and", "to", "in", "is", "for", "be", "with", "by", "shall", "that", "are", "this", "will", "on", "as", "which",
             "from", "or", "an", "have", "has", "been", "was", "were", "their", "its", "any", "all", "should", "may", "not"}
PRIVACY_RESTRICTED = {  # sha256[:16] → reason (assistant visual spot-check, 2026-10-09; to be confirmed by a person)
    "a760646f0097e6c6": "Kauvery hospital EC compliance report: contains patient lab / radiology reports with names, invoices and "
                        "insurance policies — personal / sensitive data",
}
# Project identity established from the drawings' own title blocks (sheet titles read on the page; assistant visual
# spot-check 2026-10-09). Page ranges split a multi-building document into one project per building.
SUBPROJECTS = {  # file sha256[:16] -> [(first_page, last_page, project_key)]
    "4e0b49ba427feeca": [(32, 33, "sipcot:women_hostel_irungattukottai"), (34, 38, "sipcot:men_hostel_sriperumbudur"),
                         (39, 43, "sipcot:women_hostel_sriperumbudur"), (44, 46, "sipcot:women_hostel_tiruppur"),
                         (47, 49, "sipcot:men_hostel_tiruppur")],
}
_RP = "independent_real_project"
PROJECT_META = {  # project_key -> verified facts (title block / document text); anything absent stays UNKNOWN
    "sipcot:women_hostel_irungattukottai": dict(category="hostel", district="Kancheepuram (Irungattukottai)", nature=_RP,
                                                title="SIPCOT Package 1 - Women Hostel, Irungattukottai (RFP Annexure X)"),
    "sipcot:men_hostel_sriperumbudur": dict(category="hostel", district="Kancheepuram (Sriperumbudur)", nature=_RP,
                                            title="SIPCOT Package 2 - Men Hostel, Sriperumbudur"),
    "sipcot:women_hostel_sriperumbudur": dict(category="hostel", district="Kancheepuram (Sriperumbudur)", nature=_RP,
                                              title="SIPCOT Package 3 - Women Hostel, Sriperumbudur"),
    "sipcot:women_hostel_tiruppur": dict(category="hostel", district="Tiruppur", nature=_RP, title="SIPCOT Package 4 - Women Hostel, Tiruppur"),
    "sipcot:men_hostel_tiruppur": dict(category="hostel", district="Tiruppur", nature=_RP, title="SIPCOT Package 5 - Men Hostel, Tiruppur"),
    "file:SIPCOT-RFP-for-hostels-operation-and-maintanence.pdf": dict(category="hostel", nature="tender/RFP text (drawings split into 5 projects)",
                                                                    title="SIPCOT hostels O&M RFP - text pages"),
    "file:ApprovedPlan.pdf": dict(category="commercial", district="Chennai (CMDA area; Rajiv Gandhi Salai per title block)", nature=_RP,
                                  title="CMDA approved plan PP-NHRB-S-0167-2025 - Stilt + 3 floors commercial office building, 17.97 m"),
    "file:12144929.pdf": dict(category="hospital", district="Chennai (Egmore)", nature="report containing plans of a real project",
                              title="JICA preparatory survey - Institute of Child Health, new OPD building"),
    "file:12248522.pdf": dict(category="hospital;medical_college", district="Tamil Nadu (multi-site survey)", nature="survey report (few drawings)",
                              title="JICA data collection survey on urban health care in Tamil Nadu (2 files)"),
    "file:1000045200_01.pdf": dict(category="hospital;medical_college", district="Madurai", nature="survey report with campus master plans",
                                   title="JICA preparatory survey - AIIMS Madurai"),
    "file:KRR_final_draft_CCR_2024_final_11zon__2___2_.pdf": dict(category="hospital", district="Chengalpattu (Tambaram taluk)",
                                                                  nature="compliance report - personal data, not extracted",
                                                                  title="Kauvery Hospital EC compliance report"),
    "file:EOI_for-appointment-of-a-public-sector-undertaking-Government-organization-as-Project-Management-Consultant_13112025.pdf":
        dict(category="university;hostel", district="Tiruvarur", nature="context document (no working drawings)", title="CUTN PMC EOI"),
    "file:Minutes-22nd-Building-Committee-of-CUTN_10052024.pdf": dict(category="university;hostel", district="Tiruvarur",
                                                                      nature="context document (no working drawings)",
                                                                      title="CUTN building committee minutes"),
    "file:hostels-pre-bid-queries.pdf": dict(category="hostel", nature="pre-bid clarifications (no drawings)", title="SIPCOT hostels pre-bid queries"),
    "file:Tamil-Nadu-Combined-Development-and-Building-Rules-2019_Gazette_43_Ex_III_1a_04.02.2019.pdf":
        dict(category="reference_only", nature="building rules (illustrative diagrams only)", title="TN Combined Development & Building Rules 2019"),
    "file:Completion-Report.pdf": dict(category="hospital", nature="programme report", title="TNHSP completion report"),
    "file:Tendeedoc.pdf": dict(category="hostel", nature="corrupt download (721 bytes)", title="IIT Madras hostel tender document"),
    "file:_TNRERA.pdf": dict(category="registry_listing", nature="registry listing (no drawings)", title="TN RERA registration listing"),
}
PII_RX = re.compile(r"patient\s*(name|id)|age\s*/\s*(sex|gender)|\buhid\b|referring\s+doctor|\bdate\s+of\s+birth\b|"
                    r"\baadhaa?r\b", re.I)  # bare 12-digit numbers are not used: dimension runs on drawings collide


def pii_suspected(text: str) -> bool:
    """Patient-record / identity-number patterns. A flagged page gets no pseudo-labels and no annotation-queue entry."""
    return bool(PII_RX.search(text or ""))


SKIP_DEDUP = ("blank_unknown", "unrelated_text", "boq_specification")
DRAW_TYPES = ["architectural_floor_plan", "site_plan", "elevation", "section", "structural_ga", "foundation", "column_schedule",
              "beam_schedule", "slab_plan", "reinforcement_bbs", "services_mep", "boq_specification", "unrelated_text", "blank_unknown"]
RULES = [  # (type, regex) — evaluated on page text (lower case); first strongest wins
    ("reinforcement_bbs", r"bar bending|\bbbs\b|reinforcement detail|cutting length"),
    ("column_schedule", r"column schedule|column details|schedule of columns"),
    ("beam_schedule", r"beam schedule|schedule of beams|beam l\.?s|longitudinal section of beam|\bbeam\b.*\bdetails?\b"),
    ("foundation", r"foundation|footing|\bpcc\b.*\bbed\b|grade beam|plinth beam"),
    ("slab_plan", r"roof slab|slab plan|roof plan|roof beam|\bslab\b"),
    ("services_mep", r"water supply|sanitary|plumbing|electrical|drainage|\bdrain\b|septic|leach pit|soak pit"),
    ("site_plan", r"site plan|key plan|layout plan|location plan|site layout"),
    ("elevation", r"elevation"),
    ("section", r"\bsection\b|sectional"),
    ("architectural_floor_plan", r"ground floor|first floor|second floor|floor plan|\bplan\b"),
    ("boq_specification", r"specification|abstract estimate|bill of quantit|detailed estimate|\bqty\b|rate per|\bcum\b|\bsqm\b"),
]
PSEUDO_DIM = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,3})?\s*[x×X]\s*\d{1,2}(?:\.\d{1,3})?|\d{3,5}\s*(mm)?|\d{1,2}\.\d{2}\s*m?|\d{1,2}'\s*-?\s*\d{0,2}\"?)\s*$")
FLOOR_LBL = re.compile(r"(ground|first|second|third|terrace|basement|stilt)\s+floor|roof\s+plan|\bG\.?F\b|\bF\.?F\b", re.I)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def wcsv(path, rows, cols=None):
    cols = cols or (list(rows[0].keys()) if rows else ["empty"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


_OCR = None


def ocr_text(png: str, key: str) -> str:
    """RapidOCR on the render, cached in ocr_cache/<page_id>.txt (outlined / scanned sheets carry no PDF text)."""
    global _OCR
    cp = os.path.join(ROOT, "ocr_cache", key + ".txt")
    if os.path.exists(cp):
        return open(cp, encoding="utf-8").read()
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    res, _ = _OCR(png)
    t = "\n".join(r[1] for r in (res or []))
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    open(cp, "w", encoding="utf-8").write(t)
    return t


def classify(text: str, n_vec: int, ink: float, img_cover: float) -> tuple[str, float, list[str]]:
    t = (text or "").lower()
    hits = [(k, len(re.findall(rx, t))) for k, rx in RULES]
    hits = [(k, n) for k, n in hits if n]
    prose = sum(1 for w in re.findall(r"[a-z]+", t) if w in STOPWORDS)
    nums = len(re.findall(r"\d+", t))
    if prose >= 15 and nums < 1.5 * prose and n_vec <= 150:  # a vector drawing with general notes is still a drawing  # running sentences (reports, contracts); drawing sheets with general notes still carry
        # many dimensions (TNRD sheets: 1.5-4 numbers per function word; report pages: < 1). Tuned on 37 spot-checked pages.
        return ("boq_specification", 0.5, [k for k, _ in hits]) if any(k == "boq_specification" for k, _ in hits) else ("unrelated_text", 0.6, [k for k, _ in hits])
    drawingish = n_vec > 150 or img_cover > 0.5 or (ink > 0.03 and len(t.split()) < 120)
    words = len(t.split())
    if ink < 0.003 and words < 5:
        return "blank_unknown", 0.9, []
    if not drawingish and words > 250:
        if any(k == "boq_specification" for k, _ in hits) and words > 0:
            return "boq_specification", 0.55, [k for k, _ in hits]
        return "unrelated_text", 0.7, [k for k, _ in hits]
    if not hits:
        return ("blank_unknown", 0.3, []) if not drawingish else ("architectural_floor_plan", 0.25, [])
    order = {k: i for i, (k, _) in enumerate(RULES)}
    # structure-specific labels outrank the generic word 'plan' when present
    best = sorted(hits, key=lambda kn: (order[kn[0]] if kn[0] != "architectural_floor_plan" or len(hits) == 1 else 99, -kn[1]))[0][0]
    conf = min(0.9, 0.4 + 0.1 * dict(hits)[best] + (0.15 if drawingish else 0))
    return best, round(conf, 2), [k for k, _ in hits]


def page_pseudo(page) -> list[dict]:
    """Text-span pseudo-labels with exact PDF-point boxes (dimension strings, floor labels). PSEUDO only."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                s = sp["text"].strip()
                if not s:
                    continue
                cls = "dimension_text" if PSEUDO_DIM.match(s) else "floor_label" if FLOOR_LBL.search(s) else None
                if cls:
                    out.append(dict(cls=cls, text=s, bbox_pt=[round(v, 1) for v in sp["bbox"]]))
    return out


def load_catalogue():
    p = os.path.join(ROOT, "catalog", "tnrd_type_design_catalog.csv")
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def collect_files():
    files = []
    os.makedirs(os.path.join(ROOT, "supplied"), exist_ok=True)
    for fn, role, cls, note in SUPPLIED:
        src = os.path.join(DL, fn)
        dst = os.path.join(ROOT, "supplied", fn)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)  # byte-identical copy; original untouched
        if os.path.exists(dst):
            files.append(dict(file_name=fn, path=dst, role=role, source_class=cls, note=note, url="", source_organisation=
                              "TN RERA" if "RERA" in fn else "TNRD (copy supplied by user)", acquisition_state="USER_SUPPLIED"))
    for sc in sorted(os.listdir(os.path.join(ROOT, "raw_candidates"))) if os.path.isdir(os.path.join(ROOT, "raw_candidates")) else []:
        if not sc.endswith(".json"):
            continue
        m = json.load(open(os.path.join(ROOT, "raw_candidates", sc), encoding="utf-8"))
        rec = dict(m, sidecar=sc, role="tnrd_catalogue_candidate" if "entry_no" in m else "external_lead",
                   source_class=m.get("source_class", "official_portal"))
        rec["path"] = os.path.join(ROOT, m["file_path"]) if m.get("file_path") else None
        files.append(rec)
    if os.path.isdir(SEED_DIR):
        for fn in sorted(os.listdir(SEED_DIR)):
            if fn.lower().endswith(".pdf"):
                files.append(dict(file_name=fn, path=os.path.join(SEED_DIR, fn), role="local_seed", source_class="previously_collected",
                                  url="", note="earlier-session copy of TNRD catalogue files", acquisition_state="LOCAL_SEED",
                                  source_organisation="TNRD (earlier collection)"))
    return files


ZIP_V2 = os.path.join(ROOT, "sources", "zip_v2", "TN_High_Impact_Architecture_Corpus")


def zip_derivatives(page_rows) -> list[dict]:
    """v2 ZIP sheets/PNGs are crops of handbook pages. Link each asset to the handbook page it declares, and confirm the
    link from the asset's own PDF text (printed page number) — they are derivatives, not new drawings or projects."""
    inv = os.path.join(ZIP_V2, "04_SOURCE_CATALOGS", "included_page_inventory.csv")
    if not os.path.exists(inv):
        return []
    hb = {p["page_no"]: p for p in page_rows if p["file_role"] == "original_handbook"}
    out = []
    for r in csv.DictReader(open(inv, encoding="utf-8-sig")):
        pg = int(r["source_printed_page"])
        src = hb.get(pg)
        for kind in ("asset_pdf", "asset_png"):
            p = os.path.join(ZIP_V2, r[kind])
            if not os.path.exists(p):
                out.append(dict(asset_id=r["asset_id"], asset_type=kind, path=r[kind], status="MISSING_IN_ZIP"))
                continue
            check = "not checkable (raster)"
            if kind == "asset_pdf":
                t = pymupdf.open(p)[0].get_text()
                check = "printed page number found in asset text" if str(pg) in t.split() else "printed page number NOT found — verify"
            out.append(dict(asset_id=r["asset_id"], asset_type="single_sheet_pdf" if kind == "asset_pdf" else "rendered_png_200dpi",
                            path=os.path.relpath(p, ROOT), bytes=os.path.getsize(p), sha256=sha_file(p), declared_source_page=pg,
                            handbook_page_id=src["page_id"] if src else "", sheet_title=r["sheet_title"], provenance_check=check,
                            role="derivative of handbook page — not an independent drawing or project", status="LINKED"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-dir", default=os.path.join(DL, "report"))
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    reg = os.path.join(ROOT, "registry")
    for d in ("registry", "pages", "thumbs", "pseudo_labels", "templates"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    cat = load_catalogue()
    files = collect_files()
    file_rows, page_rows, by_sha = [], [], {}
    corrupt = []
    for f in files:
        if not f.get("path") or not os.path.exists(f["path"]):
            file_rows.append(dict(f, sha256=f.get("sha256", ""), extraction_status=f.get("acquisition_state", "NOT_ACQUIRED"),
                                  exclusion_reason=f.get("reason", "not acquired")))
            continue
        sha = sha_file(f["path"])
        f["sha256"], f["bytes"] = sha, os.path.getsize(f["path"])
        f["duplicate_of_file"] = by_sha.get(sha, {}).get("file_name", "")
        file_rows.append(f)
        if sha in by_sha:
            f["extraction_status"] = "DUPLICATE_FILE (identical SHA-256; pages not re-extracted)"
            continue
        by_sha[sha] = f
        try:
            doc = pymupdf.open(f["path"])
        except Exception as e:  # noqa: BLE001
            f["extraction_status"] = "CORRUPT"
            corrupt.append(dict(file=f["file_name"], error=str(e)[:200]))
            continue
        f["pages"] = len(doc)
        f["extraction_status"] = "EXTRACTED"
        if sha[:16] in PRIVACY_RESTRICTED:  # personal data: no renders / OCR / labels are produced or kept
            f["extraction_status"] = "NOT EXTRACTED — " + PRIVACY_RESTRICTED[sha[:16]]
            f["usage_state"] = "RESTRICTED_PERSONAL_DATA"
            for d in ("pages", "thumbs", "ocr_cache", "pseudo_labels"):
                for fn in os.listdir(os.path.join(ROOT, d)) if os.path.isdir(os.path.join(ROOT, d)) else []:
                    if fn.startswith(sha[:16]):
                        os.remove(os.path.join(ROOT, d, fn))
            continue
        for i, pg in enumerate(doc):
            pid = f"{sha[:16]}-p{i + 1}"
            text = pg.get_text()
            n_vec = len(pg.get_drawings()) if len(text) < 20000 else 0
            img_cover = min(1.0, sum(abs((b[2] - b[0]) * (b[3] - b[1])) for b in (x["bbox"] for x in pg.get_image_info())) / max(1, pg.rect.width * pg.rect.height))
            png = os.path.join(ROOT, "pages", pid + ".png")
            if not os.path.exists(png) and not a.no_render:
                pix = pg.get_pixmap(dpi=DPI, alpha=False)
                pix.save(png)
            img = cv2.imread(png, cv2.IMREAD_GRAYSCALE) if os.path.exists(png) else None
            ink = float((img < 200).mean()) if img is not None else 0.0
            th = os.path.join(ROOT, "thumbs", pid + ".jpg")
            if img is not None and not os.path.exists(th):
                s = 400 / max(img.shape)
                cv2.imwrite(th, cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA))
            text_method = "pdf_text"
            if img is not None and ink > 0.01 and len(text.split()) < 40:
                text = text + "\n" + ocr_text(png, pid)
                text_method = "pdf_text+ocr"
            dtype, conf, alts = classify(text, n_vec, ink, img_cover)
            title = next((ln.strip() for ln in text.splitlines() if re.search(r"plan|elevation|section|detail|schedule|type design", ln, re.I)), "")[:120]
            pii = pii_suspected(text)
            pseudo = page_pseudo(pg) if dtype not in ("unrelated_text", "blank_unknown") and not pii else []
            if pseudo:
                json.dump(dict(page_id=pid, label_state="PSEUDO_LABEL", generator="text-span rules v1 (dimension/floor-label)",
                               coord_frame=dict(unit="pdf_point", render_dpi=DPI, px_per_pt=DPI / 72), labels=pseudo, created=now()),
                          open(os.path.join(ROOT, "pseudo_labels", pid + ".json"), "w", encoding="utf-8"), indent=1)
            page_rows.append(dict(page_id=pid, file_sha256=sha, file_name=f["file_name"], file_role=f["role"], page_no=i + 1,
                                  page_w_pt=round(pg.rect.width, 1), page_h_pt=round(pg.rect.height, 1), render_dpi=DPI,
                                  px_per_pt=round(DPI / 72, 4), content="vector" if n_vec > 150 else "raster" if img_cover > 0.5 else
                                  "text" if text.strip() else "empty", vector_paths=n_vec, image_cover=round(img_cover, 3),
                                  text_chars=len(text), text_method=text_method, ink_ratio=round(ink, 4), drawing_type=dtype, classification_confidence=conf,
                                  classification_method="keyword rules + vector/raster density (heuristic, not validated)",
                                  other_type_signals=alts, sheet_title_extracted="" if pii else title, pseudo_labels=len(pseudo), pii_suspected=pii,
                                  render_path=os.path.relpath(png, ROOT) if os.path.exists(png) else "",
                                  thumb_path=os.path.relpath(th, ROOT) if os.path.exists(th) else "",
                                  dhash=dedup.dhash(img) if img is not None else 0,
                                  dhash_rot=[dedup.dhash(np.rot90(img, k)) for k in (1, 2, 3)] if img is not None else [], text_sig=sorted(dedup.text_sig(text))))
    # ------------------------------------------------ duplicates (pages)
    dups = []
    sigs = [dict(p, text_sig=set(p["text_sig"]), sha256=p["file_sha256"], page=p["page_no"]) for p in page_rows]
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            a_, b_ = sigs[i], sigs[j]
            if a_["drawing_type"] in SKIP_DEDUP or b_["drawing_type"] in SKIP_DEDUP:
                continue  # text / blank pages are not drawings; their duplicates do not affect drawing counts or splits
            if min(a_["ink_ratio"], b_["ink_ratio"]) < 0.02 and a_["sha256"] != b_["sha256"]:
                continue  # near-empty pages (title / divider pages) collide in dHash — no reliable visual evidence
            why = dedup.near_duplicate(a_, b_)
            if not why:  # rotation-invariant: a landscape re-save of the same sheet is still the same sheet
                for hr in a_["dhash_rot"]:
                    why = dedup.near_duplicate(dict(a_, dhash=hr), b_)
                    if why:
                        why += " (rotated)"
                        break
            if why:
                dups.append(dict(page_a=a_["page_id"], file_a=a_["file_name"], page_b=b_["page_id"], file_b=b_["file_name"], reason=why))
    # declared derivation: extract page i = handbook page 312+i (confirmed only when the printed page number matches)
    hb = {p["page_no"]: p for p in page_rows if p["file_role"] == "original_handbook"}
    have = {(d["page_a"], d["page_b"]) for d in dups}
    for p in page_rows:
        if p["file_role"] == "derived_extract":
            src = hb.get(312 + p["page_no"])
            if src and (src["page_id"], p["page_id"]) not in have and str(312 + p["page_no"]) in p["text_sig"]:
                dups.append(dict(page_a=src["page_id"], file_a=src["file_name"], page_b=p["page_id"], file_b=p["file_name"],
                                 reason=f"declared derivation: extract p{p['page_no']} = handbook p{312 + p['page_no']} (printed page number matches)"))
            p["duplicate_of_page"] = src["page_id"] if src else ""
    # ------------------------------------------------ project grouping
    catmap = {c["file_name"]: c for c in cat}
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def key_of(f):
        if f["role"] in ("original_handbook", "derived_extract") or f["file_name"] == "Buildings.pdf":
            return "tnrd:buildings_handbook"
        c = catmap.get(f["file_name"])
        if c and c.get("set_hint"):
            return "tnrd:multisheet_office_package"
        if c:
            return "tnrd:" + re.sub(r"[^a-z0-9]+", "_", c["catalogue_title"].lower()).strip("_")
        if f["role"] in ("original_handbook", "derived_extract"):
            return "tnrd:buildings_handbook"
        return "file:" + f["file_name"]
    sha_key = {}
    for f in file_rows:
        if f.get("sha256"):
            k = key_of(f)
            find(k)
            if f["sha256"] in sha_key:
                parent[find(k)] = find(sha_key[f["sha256"]])
            sha_key.setdefault(f["sha256"], k)
    page_key = {p["page_id"]: sha_key[p["file_sha256"]] for p in page_rows}
    for p in page_rows:  # one project per building inside multi-building documents
        for a0, a1, sub in SUBPROJECTS.get(p["file_sha256"][:16], []):
            if a0 <= p["page_no"] <= a1:
                page_key[p["page_id"]] = sub
                find(sub)
    design_dups = []
    pages_per_key = Counter(page_key.values())
    pair_count = Counter()
    for d in dups:
        ka, kb = page_key[d["page_a"]], page_key[d["page_b"]]
        if ka != kb:
            pair_count[tuple(sorted((ka, kb)))] += 1
    for d in dups:
        ka, kb = find(page_key[d["page_a"]]), find(page_key[d["page_b"]])
        if ka != kb:
            k0 = tuple(sorted((page_key[d["page_a"]], page_key[d["page_b"]])))
            need = min(3, pages_per_key[k0[0]], pages_per_key[k0[1]])
            merged = pair_count[k0] >= need and "handbook" not in ka + kb
            design_dups.append(dict(d, project_a=ka, project_b=kb, matching_pairs=pair_count[k0],
                                    grouping="MERGED (same design / document family)" if merged else
                                    "NOT MERGED (handbook reprint)" if "handbook" in ka + kb else f"NOT MERGED ({pair_count[k0]} < {need} matching pages)"))
            if merged:  # one isolated page match never merges two documents into one project
                parent[ka] = kb
    projects = defaultdict(lambda: dict(files=set(), pages=[], types=Counter(), cats=set(), titles=set(), urls=set(), roles=set()))
    for f in file_rows:
        if not f.get("sha256"):
            continue
        k = find(key_of(f))
        P = projects[k]
        P["files"].add(f["file_name"])
        P["roles"].add(f["role"])
        c = catmap.get(f["file_name"])
        if c:
            P["cats"].add(c["category_hint"])
            P["titles"].add(c["catalogue_title"])
            P["urls"].add(c["url"])
        elif f.get("building_type"):
            P["cats"].add(f["building_type"])
    for p in page_rows:
        k = find(page_key[p["page_id"]])
        p["project_id"] = "tnc-" + hashlib.sha1(k.encode()).hexdigest()[:10]
        projects[k]["files"].add(p["file_name"])
        projects[k]["pages"].append(p["page_id"])
        projects[k]["types"][p["drawing_type"]] += 1
    approvals = {}
    ap_path = os.path.join(reg, "approvals.csv")
    if os.path.exists(ap_path):  # human decisions only: project_id,usage_state,approved_by,evidence_ref,date
        for r in csv.DictReader(open(ap_path, encoding="utf-8")):
            if r.get("approved_by") and r.get("evidence_ref"):
                approvals[r["project_id"]] = r
    proj_rows = []
    for k, P in sorted(projects.items()):
        pid = "tnc-" + hashlib.sha1(k.encode()).hexdigest()[:10]
        is_ref = "registry_listing" in P["roles"] or "external_lead" in P["roles"] and not P["types"].get("architectural_floor_plan")
        drawing_pages = sum(v for t, v in P["types"].items() if t not in ("unrelated_text", "blank_unknown", "boq_specification"))
        apv = approvals.get(pid)
        restricted = any(f.get("usage_state") == "RESTRICTED_PERSONAL_DATA" for f in file_rows if f.get("file_name") in P["files"])
        state = apv["usage_state"] if apv else "RESTRICTED_PERSONAL_DATA" if restricted else ("REVIEW_REQUIRED" if drawing_pages else "REJECTED")
        meta = PROJECT_META.get(k, {})
        if not meta and k.startswith("tnrd:"):
            meta = dict(nature="handbook (reference document)" if "handbook" in k else "out-of-scope handbook (roads & bridges)"
                        if "roads" in k else "standard type design (generic, no site)", district="NOT APPLICABLE (type design - no site)")
        proj_rows.append(dict(project_id=pid, project_key=k, title=meta.get("title", ";".join(sorted(P["titles"])) or k),
                              project_nature=meta.get("nature", "UNKNOWN"), state_region="Tamil Nadu", district=meta.get("district", "UNKNOWN"),
                              building_category=meta.get("category") or ";".join(sorted(P["cats"] - {"UNKNOWN"})) or ("handbook" if "handbook" in k else "UNKNOWN"),
                              catalogue_titles=sorted(P["titles"]), source_urls=sorted(P["urls"]), files=sorted(P["files"]),
                              file_roles=sorted(P["roles"]), pages=len(P["pages"]), drawing_pages=drawing_pages,
                              drawing_type_counts=dict(P["types"]), revision="UNKNOWN", date="UNKNOWN",
                              grouping_basis="catalogue entry / inferred multi-sheet set / identical or near-duplicate sheets merged",
                              usage_state=state, training_eligible=state == "APPROVED_FOR_TRAINING",
                              evaluation_eligible=state in ("APPROVED_FOR_EVALUATION", "APPROVED_FOR_TRAINING"),
                              permission_evidence=apv["evidence_ref"] if apv else ("TNRD policy permits attributed reproduction; ML training "
                              "rights not addressed → human review") if k.startswith("tnrd:") else "none - public URL only; rights holder not contacted", annotation_state="NOT_STARTED", split="UNASSIGNED",
                              exclusion_reason="" if drawing_pages else "no drawing pages (text/listing only)", reference_only=is_ref))
    proj_by_id = {p["project_id"]: p for p in proj_rows}
    # ------------------------------------------------ splits: only for approved projects
    approved = [p for p in proj_rows if p["usage_state"] in ("APPROVED_FOR_TRAINING", "APPROVED_FOR_EVALUATION")]
    for p in approved:
        u = int(hashlib.sha256(("tnc-v1" + p["project_id"]).encode()).hexdigest(), 16) % 100
        p["split"] = "final_holdout" if p["usage_state"] == "APPROVED_FOR_EVALUATION" else ("tn_train" if u < 80 else "tn_validation")
    leak = []
    for d in dups:
        sa = proj_by_id[next(p["project_id"] for p in page_rows if p["page_id"] == d["page_a"])]["split"]
        sb = proj_by_id[next(p["project_id"] for p in page_rows if p["page_id"] == d["page_b"])]["split"]
        if sa != sb and "UNASSIGNED" not in (sa, sb):
            leak.append(dict(d, split_a=sa, split_b=sb))
    split_audit = dict(created=now(), policy="Splits are assigned only to human-approved projects; related sheets/variants share a "
                       "project id; near-duplicate pages across different splits fail the audit; existing development projects "
                       "stay in development_benchmark (see data/tn_dataset).", approved_projects=len(approved),
                       split_counts=dict(Counter(p["split"] for p in proj_rows)), cross_split_duplicate_pairs=len(leak), leaks=leak,
                       ok=not leak, final_holdout_sealed=True,
                       note="0 projects approved → no train/validation/holdout split created (correct by policy)." if not approved else "")
    # ------------------------------------------------ registries
    for p in page_rows:
        p["project_id"] = p.get("project_id", "")
    wcsv(os.path.join(reg, "page_inventory.csv"), [{k: v for k, v in p.items() if k not in ("text_sig", "dhash_rot")} for p in page_rows])
    fcols = ["file_name", "role", "source_class", "source_organisation", "catalogue_title", "url", "final_url", "http_status", "content_type",
             "bytes", "sha256", "file_path", "path", "pages", "acquired_at", "acquisition_state", "usage_state", "licence_policy_url",
             "permission_evidence", "training_eligible", "evaluation_eligible", "attribution", "extraction_status", "duplicate_of_file",
             "exclusion_reason", "note"]
    for f in file_rows:
        f.setdefault("usage_state", "REVIEW_REQUIRED")
        f.setdefault("training_eligible", False)
        f.setdefault("evaluation_eligible", False)
    wcsv(os.path.join(reg, "file_inventory.csv"), file_rows, fcols)
    wcsv(os.path.join(reg, "project_manifest.csv"), proj_rows)
    wcsv(os.path.join(reg, "duplicates.csv"), dups, ["page_a", "file_a", "page_b", "file_b", "reason"])
    wcsv(os.path.join(reg, "design_reuse.csv"), design_dups, ["project_a", "project_b", "matching_pairs", "grouping", "page_a", "file_a", "page_b", "file_b", "reason"])
    deriv = zip_derivatives(page_rows)
    wcsv(os.path.join(reg, "zip_v2_derivatives.csv"), deriv)
    src_rows = source_registry(cat, file_rows)
    wcsv(os.path.join(reg, "source_registry.csv"), src_rows)
    lrq = [dict(project_id=p["project_id"], project_key=p["project_key"], files=p["files"], pages=p["pages"], drawing_pages=p["drawing_pages"],
                current_state=p["usage_state"], source_urls=p["source_urls"], policy_url="https://tnrd.tn.gov.in/rdweb_newsite/project/reports/"
                "Public/WebsitePolicies.php", question="Confirm in writing that these drawings may be used for (a) ML training and/or "
                "(b) evaluation; confirm no third-party copyright", decision="", decided_by="", evidence_ref="", decided_on="")
           for p in proj_rows if p["usage_state"] == "REVIEW_REQUIRED"]
    wcsv(os.path.join(reg, "license_review_queue.csv"), lrq)
    if not os.path.exists(ap_path):
        wcsv(ap_path, [], ["project_id", "usage_state", "approved_by", "evidence_ref", "date"])
    classes = ["wall", "room", "door", "window", "dimension", "floor_label", "column", "beam", "slab", "foundation", "bbs_field"]
    aq = [dict(page_id=p["page_id"], project_id=p["project_id"], drawing_type=p["drawing_type"], render_path=p["render_path"],
               px_per_pt=p["px_per_pt"], classes=classes, pseudo_label_file=f"pseudo_labels/{p['page_id']}.json" if p["pseudo_labels"] else "",
               state="NOT_STARTED", reviews_required=2, reviewer_1="", reviewer_2="",
               priority=1 if p["drawing_type"] in ("architectural_floor_plan", "reinforcement_bbs", "column_schedule", "beam_schedule",
                                                   "foundation") else 2)
          for p in page_rows if p["drawing_type"] not in ("unrelated_text", "blank_unknown", "boq_specification")
          and p["file_role"] != "derived_extract" and not p["pii_suspected"]]  # extract = handbook duplicate; PII pages excluded
    wcsv(os.path.join(reg, "annotation_queue.csv"), sorted(aq, key=lambda r: (r["priority"], r["page_id"])))
    json.dump(split_audit, open(os.path.join(reg, "split_audit.json"), "w"), indent=1)
    write_templates()
    summary = summarise(cat, file_rows, page_rows, proj_rows, dups, design_dups, corrupt, aq, split_audit, src_rows)
    json.dump(summary, open(os.path.join(reg, "dataset_build_summary.json"), "w"), indent=1, default=str)
    md = report_md(summary)
    open(os.path.join(ROOT, "DATASET_BUILD_REPORT.md"), "w", encoding="utf-8").write(md)
    os.makedirs(a.report_dir, exist_ok=True)
    for fn in ("source_registry.csv", "project_manifest.csv", "page_inventory.csv", "license_review_queue.csv", "file_inventory.csv",
               "duplicates.csv", "design_reuse.csv", "annotation_queue.csv", "split_audit.json", "dataset_build_summary.json"):
        shutil.copy2(os.path.join(reg, fn), os.path.join(a.report_dir, fn))
    shutil.copy2(os.path.join(ROOT, "DATASET_BUILD_REPORT.md"), os.path.join(a.report_dir, "DATASET_BUILD_REPORT.md"))
    shutil.copy2(os.path.join(ROOT, "catalog", "tnrd_type_design_catalog.csv"), os.path.join(a.report_dir, "tnrd_type_design_catalog.csv"))
    lg = os.path.join(ROOT, "logs", "fetch_decisions.jsonl")
    if os.path.exists(lg):
        shutil.copy2(lg, os.path.join(a.report_dir, "crawl_decision_log.jsonl"))
    print(json.dumps(summary["headline"], indent=1))


def source_registry(cat, file_rows):
    got = Counter(f.get("url") for f in file_rows if f.get("sha256"))
    rows = [
        dict(source_id="tnrd_catalogue", name="TNRD Type Design Drawings for Buildings", url="https://tnrd.tn.gov.in/buildings_design.html",
             source_class="official_portal", robots="allowed (only /rdweb_newsite/ disallowed)", access="public, no login",
             licence_state="REVIEW_REQUIRED", licence_evidence="TNRD website policy (summary supplied by user; page itself is under "
             "robots-disallowed /rdweb_newsite/ so it was not fetched)", items_discovered=len(cat),
             items_acquired=sum(1 for c in cat if got.get(c["url"])), status="CRAWLED"),
        dict(source_id="tnrd_policy", name="TNRD website policies", url="https://tnrd.tn.gov.in/rdweb_newsite/project/reports/Public/WebsitePolicies.php",
             source_class="official_portal", robots="DISALLOWED (/rdweb_newsite/)", access="not fetched", licence_state="n/a",
             licence_evidence="", items_discovered=1, items_acquired=0, status="BLOCKED_BY_SOURCE_RULES — read manually by a person"),
        dict(source_id="tntenders", name="Tamil Nadu eProcurement", url="https://tntenders.gov.in/", source_class="official_portal",
             robots="robots.txt 404", access="tender documents behind per-download CAPTCHA", licence_state="REVIEW_REQUIRED",
             licence_evidence="", items_discovered=1, items_acquired=0,
             status="BLOCKED_BY_SOURCE_RULES — CAPTCHA not bypassed; manual acquisition queue (tender id, BOQ stage) required"),
        dict(source_id="tntenders_example", name="Example tender with arch/structural/MEP drawings + BOQ",
             url="https://tntenders.gov.in/nicgep/app?component=%24DirectLink&page=FrontEndViewTender&service=direct&sp=SJLXy4LUHUWwElXBIxZzbHw%3D%3D",
             source_class="official_portal", robots="n/a", access="session-bound link + CAPTCHA", licence_state="REVIEW_REQUIRED",
             licence_evidence="", items_discovered=1, items_acquired=0, status="MANUAL_ACQUISITION — BOQ would be TENDERED stage, not final"),
        dict(source_id="tnhsp", name="Tamil Nadu Health System Project", url="https://tnhsp.org/pages/view/Projects_TNUHP",
             source_class="official_portal", robots="no robots.txt (error page)", access="public", licence_state="REVIEW_REQUIRED",
             licence_evidence="no terms found", items_discovered=1, items_acquired=sum(1 for f in file_rows if "tnhsp" in str(f.get("url"))),
             status="LEAD — only a completion report is linked; no drawing packages found"),
        dict(source_id="jica_ich", name="JICA report — ICH & Hospital for Children, Chennai", url="https://openjicareport.jica.go.jp/pdf/12144929.pdf",
             source_class="third_party_public_report", robots="allowed", access="public", licence_state="REVIEW_REQUIRED",
             licence_evidence="JICA terms not reviewed", items_discovered=1,
             items_acquired=sum(1 for f in file_rows if "jica" in str(f.get("url"))), status="QUARANTINED"),
        dict(source_id="tnpwdea", name="TN PWD Engineers Association downloads", url="https://tnpwdea.org/downloads.php?category_id=4",
             source_class="secondary_host", robots="robots.txt 404", access="public", licence_state="REVIEW_REQUIRED",
             licence_evidence="secondary host — verify official origin", items_discovered=1, items_acquired=0,
             status="LEAD ONLY — rate documents (handled by backend/tnpwd_ingestion), not drawings"),
        dict(source_id="tnrera", name="TN RERA", url="https://rera.tn.gov.in/", source_class="official_portal",
             robots="DISALLOWS /uploads/ and *.pdf", access="not crawled", licence_state="BLOCKED_BY_SOURCE_RULES",
             licence_evidence="builder drawings are third-party copyright", items_discovered=1, items_acquired=0,
             status="BLOCKED_BY_SOURCE_RULES — only the user-supplied listing printout is inventoried"),
        dict(source_id="tn_pwd_policy_notes", name="TN PWD Buildings policy notes / citizen charters (cms.tn.gov.in)",
             url="https://cms.tn.gov.in/cms_migrated/document/docfiles/pwd_buildings_e_1.pdf", source_class="official_portal",
             robots="not checked (host not on allowlist)", access="public", licence_state="REVIEW_REQUIRED", licence_evidence="",
             items_discovered=6, items_acquired=0, status="LEAD — text reports (confirm PWD type designs exist for PHC/HSC/schools/"
             "hostels; drawings via Chief Architect, PWD Chepauk — permission request needed)"),
        dict(source_id="tn_gazette_mspb", name="TN Gazette — Multistoried & Public Building Rules notices",
             url="https://stationeryprinting.tn.gov.in/", source_class="official_portal", robots="not checked", access="public",
             licence_state="n/a", licence_evidence="", items_discovered=7, items_acquired=0, status="LEAD — rules text, no drawings"),
        dict(source_id="permissioned_partners", name="Architects / builders / structural consultants / QS / contractors in TN",
             url="", source_class="permissioned_private", robots="n/a", access="requires written permission", licence_state="NOT_REQUESTED",
             licence_evidence="", items_discovered=0, items_acquired=0, status="EXTERNAL — outreach + data-sharing agreement required"),
    ]
    v2 = os.path.join(ROOT, "registry", "catalog_v2_acquisition.csv")
    if os.path.exists(v2):  # one row per v2-catalogue direct-PDF lead, with the real acquisition outcome
        for r in csv.DictReader(open(v2, encoding="utf-8")):
            rows.append(dict(source_id="v2:" + r["source_id"], name=r["title"], url=r["url"], source_class="v2_catalogue_lead",
                             robots="checked at fetch", access="public direct PDF claim", licence_state="REVIEW_REQUIRED",
                             licence_evidence="none — public URL only", items_discovered=1,
                             items_acquired=1 if r["acquisition_state"] == "RAW_CANDIDATE" else 0,
                             status=r["acquisition_state"] + (f" — {r['reason']}" if r.get("reason") else "")))
    return rows


def write_templates():
    t = os.path.join(ROOT, "templates")
    schema = dict(title="Approved BOQ reference (Tamil Nadu)", type="object", required=["project_id", "boq_stage", "approving_authority",
                  "approval_reference", "approval_date", "drawing_revision", "currency", "sor_year", "lines"],
                  properties=dict(project_id=dict(type="string"), boq_stage=dict(enum=["TENDERED", "PROVISIONAL", "AWARDED", "REVISED",
                                  "FINAL_APPROVED", "PAID_AS_BUILT"], description="A tender file is TENDERED, never FINAL_APPROVED"),
                                  approving_authority=dict(type="string"), approval_reference=dict(type="string"),
                                  approval_date=dict(type="string", format="date"), drawing_revision=dict(type="string"),
                                  currency=dict(const="INR"), sor_year=dict(type="string"), source_document_sha256=dict(type="string"),
                                  selling_price=dict(type="null", description="Never used: selling/market price is not construction cost"),
                                  lines=dict(type="array", items=dict(type="object", required=["item_no", "description", "unit", "quantity"],
                                             properties=dict(item_no={}, sor_code={}, description={}, unit={}, quantity=dict(type="number"),
                                                             rate=dict(type=["number", "null"]), amount=dict(type=["number", "null"]),
                                                             quantity_kind=dict(enum=["tendered", "awarded", "revised", "final", "paid"]))))))
    json.dump(schema, open(os.path.join(t, "approved_boq.schema.json"), "w"), indent=1)
    wcsv(os.path.join(t, "approved_boq_template.csv"), [], ["project_id", "boq_stage", "approving_authority", "approval_reference",
         "approval_date", "drawing_revision", "sor_year", "item_no", "sor_code", "description", "unit", "tendered_qty", "awarded_qty",
         "revised_qty", "final_qty", "paid_qty", "rate", "amount"])
    wcsv(os.path.join(t, "annotation_template.csv"), [], ["page_id", "project_id", "class", "geometry_type", "points_px", "px_per_pt",
         "attributes", "annotator", "reviewer_1", "reviewer_1_decision", "reviewer_2", "reviewer_2_decision", "state"])


def summarise(cat, files, pages, projects, dups, design_dups, corrupt, aq, split_audit, src):
    acquired = [f for f in files if f.get("sha256")]
    uniq = {f["sha256"]: f for f in acquired}
    dl = [f for f in acquired if f["role"] in ("tnrd_catalogue_candidate", "external_lead")]
    dl_uniq = {f["sha256"] for f in dl}
    blocked = [f for f in files if not f.get("sha256")]
    cats = Counter()
    for p in projects:
        for c in (p["building_category"] or "UNKNOWN").split(";"):
            cats[c] += 1
    head = dict(
        sources_in_registry=len(src), tnrd_catalogue_links=len(cat), tnrd_catalogue_unique_urls=len({c["url"] for c in cat}),
        documents_downloaded_this_build=len(dl), unique_downloaded_files=len(dl_uniq), bytes_downloaded=sum(f["bytes"] for f in dl),
        supplied_files=sum(1 for f in acquired if f["role"] in ("original_handbook", "derived_extract", "registry_listing")),
        local_seed_files=sum(1 for f in acquired if f["role"] == "local_seed"),
        unique_files_total=len(uniq), bytes_unique_total=sum(f["bytes"] for f in uniq.values()),
        identical_file_duplicates=len(acquired) - len(uniq), pages_extracted=len(pages),
        drawing_pages=sum(1 for p in pages if p["drawing_type"] not in ("unrelated_text", "blank_unknown", "boq_specification")),
        near_duplicate_page_pairs=len(dups), cross_project_design_reuse_pairs=len(design_dups), projects=len(projects),
        projects_with_drawings=sum(1 for p in projects if p["drawing_pages"]), corrupted_files=len(corrupt), blocked_or_failed=len(blocked),
        pii_suspected_pages=sum(1 for p in pages if p.get("pii_suspected")),
        pseudo_labelled_pages=sum(1 for p in pages if p["pseudo_labels"]), pseudo_labels=sum(p["pseudo_labels"] for p in pages),
        annotation_queue_pages=len(aq), verified_annotations=0, approved_for_training=sum(p["usage_state"] == "APPROVED_FOR_TRAINING" for p in projects),
        approved_for_evaluation=sum(p["usage_state"] == "APPROVED_FOR_EVALUATION" for p in projects),
        review_required=sum(p["usage_state"] == "REVIEW_REQUIRED" for p in projects), rejected=sum(p["usage_state"] == "REJECTED" for p in projects),
        approved_boq_projects=0)
    return dict(created=now(), headline=head, drawing_types=dict(Counter(p["drawing_type"] for p in pages)),
                drawing_types_by_role={r: dict(Counter(p["drawing_type"] for p in pages if p["file_role"] == r)) for r in {p["file_role"] for p in pages}},
                content=dict(Counter(p["content"] for p in pages)), building_categories=dict(cats), usage_states=dict(Counter(p["usage_state"] for p in projects)),
                annotation_states=dict(NOT_STARTED=len(aq), PSEUDO_LABEL_pages=head["pseudo_labelled_pages"], VERIFIED=0, IN_REVIEW=0),
                split_audit=split_audit, corrupt=corrupt, blocked=[dict(file=f.get("file_name"), url=f.get("url"), reason=f.get("reason")) for f in blocked],
                projects=[dict(project_id=p["project_id"], key=p["project_key"], category=p["building_category"], files=len(p["files"]),
                               pages=p["pages"], drawing_pages=p["drawing_pages"], state=p["usage_state"]) for p in projects],
                sources=src)


def report_md(s):
    h = s["headline"]
    L = [f"# TN Drawing Corpus — Dataset Build Report", "", f"Generated {s['created']} by `tn_corpus/scripts/build_corpus.py` (idempotent).", "",
         "**Status: candidate corpus, NOT a validated training dataset.** 0 projects are approved for training or evaluation, "
         "0 annotations are verified and 0 approved BOQs exist. Everything below is REVIEW_REQUIRED until a person with rights "
         "evidence approves it in `tn_corpus/registry/approvals.csv`.", "", "## Exact counts", "", "| Measure | Count |", "|---|---|"]
    lab = dict(sources_in_registry="Sources in registry", tnrd_catalogue_links="TNRD catalogue PDF links (live page)",
               documents_downloaded_this_build="Documents downloaded into quarantine", unique_downloaded_files="…of which unique (SHA-256)",
               bytes_downloaded="Bytes downloaded", supplied_files="User-supplied files", local_seed_files="Earlier local seed files",
               unique_files_total="Unique files overall", bytes_unique_total="Bytes (unique files)", identical_file_duplicates="Identical-file duplicates",
               pages_extracted="Pages extracted (150 dpi + thumbnails)", drawing_pages="Pages classified as drawings",
               near_duplicate_page_pairs="Near-duplicate page pairs (dHash/text)", cross_project_design_reuse_pairs="Design reuse pairs across catalogue entries/handbook",
               projects="Projects after grouping", projects_with_drawings="Projects with ≥1 drawing page", corrupted_files="Corrupted files",
               blocked_or_failed="Blocked / failed acquisitions", pseudo_labelled_pages="Pages with pseudo-labels", pseudo_labels="Pseudo-labels (text spans)",
               annotation_queue_pages="Pages in annotation queue", verified_annotations="Verified annotations",
               approved_for_training="Projects APPROVED_FOR_TRAINING", approved_for_evaluation="Projects APPROVED_FOR_EVALUATION",
               review_required="Projects REVIEW_REQUIRED", rejected="Projects REJECTED (no drawings)", approved_boq_projects="Approved BOQ projects")
    for k, v in h.items():
        L.append(f"| {lab.get(k, k)} | {v:,} |" if isinstance(v, int) else f"| {lab.get(k, k)} | {v} |")
    L += ["", "The request mentioned 70 catalogue entries. The live TNRD page lists **"
          f"{h['tnrd_catalogue_links']} PDF links** (26 table rows); the 70-entry CSV from the starter ZIP was not on disk, so the "
          "catalogue was rebuilt from the live page.", "", "## Page classification (heuristic, not validated)", "", "| Type | Pages |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in sorted(s["drawing_types"].items(), key=lambda kv: -kv[1])]
    L += ["", "By file role:", ""] + [f"- **{r}**: {d}" for r, d in s["drawing_types_by_role"].items()]
    L += ["", "## Building categories (projects)", ""] + [f"- {k}: {v}" for k, v in sorted(s["building_categories"].items(), key=lambda kv: -kv[1])]
    L += ["", "Missing categories (no lawful source found yet): multi-storey apartments, hospitals with drawings, medical colleges, "
          "universities, commercial buildings, hostels with drawings. All TNRD material is rural single/two-storey public buildings.",
          "", "## Sources", "", "| Source | Class | Robots | Status | Discovered | Acquired |", "|---|---|---|---|---|---|"]
    L += [f"| {r['name']} | {r['source_class']} | {r['robots']} | {r['status']} | {r['items_discovered']} | {r['items_acquired']} |" for r in s["sources"]]
    L += ["", "## Usage / permission states", ""] + [f"- {k}: {v}" for k, v in s["usage_states"].items()]
    L += ["", "## Annotation states", ""] + [f"- {k}: {v}" for k, v in s["annotation_states"].items()]
    sa = s["split_audit"]
    L += ["", "## Split / leakage audit", "", f"- Approved projects: {sa['approved_projects']}", f"- Split counts: {sa['split_counts']}",
          f"- Cross-split duplicate pairs: {sa['cross_split_duplicate_pairs']} → {'OK' if sa['ok'] else 'FAIL'}", f"- {sa['note']}",
          "", "## Blocked / failed", ""] + ([f"- {b['file']}: {b['reason']}" for b in s["blocked"]] or ["- none"])
    L += ["", "## Pipeline safeguards", "", "Host allowlist; SSRF guard (public IPs, http/s only, redirects re-checked); robots.txt with "
          "wildcards; 3 s per-host delay; 45 s timeout; 80 MB cap; PDF magic-byte check; SHA-256 content addressing; sidecar "
          "metadata; idempotent re-runs; kill switch `tn_corpus/STOP_CRAWL`; allow/deny log `logs/fetch_decisions.jsonl`. "
          "Crawling is offline from the estimator: nothing here changes rates or model weights.", "",
          "## External permissions / inputs still needed", "",
          "1. Written TNRD confirmation that type-design drawings may be used for ML training (queue: `license_review_queue.csv`).",
          "2. Manual eProcurement downloads (CAPTCHA) of building tenders, recorded as TENDERED-stage BOQs.",
          "3. Permission from PWD Chief Architect (Chepauk) for PHC / school / hostel type designs.",
          "4. Data-sharing agreements with TN architects/builders/consultants for apartments, hospitals, commercial buildings.",
          "5. Annotators + two independent reviewers per high-impact label.",
          "6. Approved (FINAL_APPROVED / PAID) BOQs with authority, reference, date and drawing revision.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
