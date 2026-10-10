"""pdf_parser / ocr_parser / table_parser / drawing_parser / metadata_parser / document_classifier in one module
(small, shared helpers). Each page becomes a record with its text (vector or OCR), its kind and its metadata."""
from __future__ import annotations

import os
import re

import numpy as np
import pymupdf

TN_DISTRICTS = ["Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul", "Erode", "Kallakurichi",
                "Kancheepuram", "Kanniyakumari", "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai", "Nagapattinam", "Namakkal", "Nilgiris",
                "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi", "Thanjavur", "Theni",
                "Thoothukudi", "Tiruchirappalli", "Tirunelveli", "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai", "Tiruvarur",
                "Vellore", "Viluppuram", "Virudhunagar"]
BUILDING_TYPES = [("anganwadi|nursery", "institutional"), ("school|class ?room|college|university|hostel", "educational"),
                  ("hospital|phc|health|clinic|dispensary", "hospital"), ("office|vao|aee|panchayat|block", "office"),
                  ("godown|warehouse|shed|store", "industrial"), ("ration|pds|shop|market|commercial|mall", "commercial"),
                  ("apartment|flat|bhk|tower|block-?[a-z]|refuge", "large_residential"), ("villa|house|residence|iay|pmay|dwelling", "basic_residential")]
DRAWING_TYPES = [("bbs|bar bending", "REBAR / BBS"), ("column schedule", "COLUMN SCHEDULE"), ("beam schedule", "BEAM SCHEDULE"),
                 ("door schedule|window schedule|joinery schedule", "DOOR/WINDOW SCHEDULE"), ("footing|foundation", "FOUNDATION PLAN"),
                 ("column (layout|plan)", "COLUMN PLAN"), ("beam (layout|plan)|plinth beam|beam l\\.?s", "BEAM PLAN"),
                 ("slab|roof plan|reinforcement", "SLAB PLAN"), ("elevation", "ELEVATION"), ("section", "SECTION"),
                 ("electrical|plumbing|sanitary|drain", "SERVICES"), ("detail", "DETAIL"), ("stair", "STAIRCASE"),
                 ("general notes|notes", "GENERAL NOTES"), ("floor plan|plan", "ARCHITECTURAL PLAN")]


def classify_text(name: str, text: str) -> dict:
    t = (name + " " + text).lower()
    btype = next((b for rx, b in BUILDING_TYPES if re.search(rx, t)), "unknown")
    dtype = next((d for rx, d in DRAWING_TYPES if re.search(rx, t)), "OTHER")
    disc = "structural" if dtype in ("REBAR / BBS", "COLUMN SCHEDULE", "BEAM SCHEDULE", "FOUNDATION PLAN", "COLUMN PLAN", "BEAM PLAN", "SLAB PLAN") \
        else "services" if dtype == "SERVICES" else "architectural"
    district = next((d for d in TN_DISTRICTS if re.search(r"\b" + d.lower() + r"\b", t)), None)
    scale = re.search(r"scale\s*[:=]?\s*1\s*[:/]\s*(\d{2,4})|\b1\s*:\s*(\d{2,4})\b|\b(nts|not to scale)\b", t)
    return dict(building_type=btype, drawing_type=dtype, discipline=disc, district=district,
                scale=("NTS" if scale and scale.group(3) else f"1:{scale.group(1) or scale.group(2)}") if scale else None)


def pages(path: str, kind: str, max_pages=60):
    """[(page_no, image (gray, ≤1600 px), text, method)]"""
    if kind == "pdf":
        doc = pymupdf.open(path)
        for i, p in enumerate(doc):
            if i >= max_pages:
                break
            t = p.get_text()
            pix = p.get_pixmap(dpi=min(110, int(1600 * 72 / max(p.rect.width, p.rect.height))), colorspace=pymupdf.csGRAY)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w)
            yield i + 1, img, t, "vector text" if len(t.strip()) > 40 else "raster (OCR on demand)"
    elif kind in ("png", "jpg", "tif"):
        import cv2
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return
        k = min(1.0, 1600 / max(img.shape))
        yield 1, cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img, "", "raster (OCR on demand)"


_R = None


def ocr_text(img) -> str:
    global _R
    if _R is None:
        from rapidocr_onnxruntime import RapidOCR
        _R = RapidOCR()
    res, _ = _R(np.dstack([img] * 3) if img.ndim == 2 else img)
    return " ".join(r[1] for r in res or [])


def table_rows(text: str) -> list[str]:
    """Lines that look like table rows (schedules, area statements): ≥3 numeric cells."""
    return [ln for ln in text.splitlines() if len(re.findall(r"\d+(?:\.\d+)?", ln)) >= 3]


def project_key(path: str, text: str) -> str:
    """Project identity = source file stem without sheet suffixes (GF / FF / -1 / (2) …)."""
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    stem = re.sub(r"[-_ ]*(gf|ff|sf|tf|arc|roof|model|sheet\s*\d+|\(\d\)|\d+)$", "", stem)
    stem = re.sub(r"[^a-z]+", "-", stem).strip("-")
    return stem or os.path.basename(path)
