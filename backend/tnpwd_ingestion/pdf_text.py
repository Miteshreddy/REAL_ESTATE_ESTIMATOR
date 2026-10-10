"""Page text with OCR fallback for scanned pages (RapidOCR, already used by the drawing reader)."""
from __future__ import annotations

import numpy as np
import pymupdf

_ocr = None


def ocr_page(page, dpi=200) -> list[tuple]:
    """[(x0, y0, x1, y1, text, conf)] in PDF points."""
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
    res, _ = _ocr(img)
    k = 72 / dpi
    out = []
    for box, txt, conf in res or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append((min(xs) * k, min(ys) * k, max(xs) * k, max(ys) * k, txt, float(conf)))
    return out


def page_texts(path: str, ocr_missing=True, max_ocr_pages=40):
    """Yield (page_no, text, method) for every page; scanned pages are OCR'd (capped to keep refreshes bounded)."""
    doc = pymupdf.open(path)
    n_ocr = 0
    for i, p in enumerate(doc):
        t = p.get_text()
        if len(t.strip()) > 40 or not ocr_missing:
            yield i + 1, t, "text"
        elif n_ocr < max_ocr_pages:
            n_ocr += 1
            lines = {}
            for x0, y0, x1, y1, s, c in ocr_page(p):
                lines.setdefault(round((y0 + y1) / 2 / 6), []).append((x0, s))
            yield i + 1, "\n".join(" ".join(s for _, s in sorted(v)) for _, v in sorted(lines.items())), "ocr"
        else:
            yield i + 1, "", "skipped"
