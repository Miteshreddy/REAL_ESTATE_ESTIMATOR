"""Reference BOQs (Tasks 12-14): upload + validation + provenance, quantity comparison, item / total cost accuracy.

UPLOAD   CSV / XLSX with the columns of data/templates/reference_boq_template.csv, plus document metadata (form fields):
         approval_status ∈ approved | provisional | user-entered | derived | incomplete | rejected,
         approval_authority, approval_date, source_reference, drawing_revision, boq_revision, currency (INR), scope,
         inclusions, exclusions, taxes_included (yes/no). The original file is stored unchanged with its SHA-256.
         'approved' REQUIRES approval_authority + approval_date + source_reference — otherwise the upload is refused
         (never silently downgraded). Selling / listing prices are not BOQs.
COMPARE  match rules (in order, each line matched at most once): (1) exact item code = estimate TN code;
         (2) engineer-approved mapping of the estimate line = BOQ code; (3) same unit family AND description similarity ≥ 0.35.
         Unit-incompatible pairs are never matched. Every unmatched / excluded line is listed with its reason.
METRICS  item quantity: absolute & relative error (relative undefined when the reference is 0 — reported as None);
         cost: MAE, median AE, % within ±5 / ±10 %, WAPE = Σ|est−ref| / Σ|ref| over matched lines, signed bias,
         total-cost error, completeness = matched reference amount / total reference amount, and the reference amount the
         estimate leaves unpriced. Only APPROVED BOQs count as validation; others are reported as PROVISIONAL.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import statistics as st
from datetime import datetime

from tnpwd_ingestion.rate_analysis import unit_of

STATUSES = ("approved", "provisional", "user-entered", "derived", "incomplete", "rejected")
COLUMNS = ["item_no", "item_code", "description", "category", "quantity", "unit", "rate", "amount", "tax", "source_reference", "notes"]
FAMILY = {"Earthwork": "civil", "Waterproofing": "civil", "Concrete Works": "concrete", "RCC Works": "concrete", "Formwork": "formwork",
          "Reinforcement": "reinforcement", "Masonry": "masonry", "Flooring": "flooring", "Plastering": "plastering", "Painting": "painting",
          "Doors & Windows": "doors_windows", "Electrical": "services", "Plumbing & Sanitary": "services"}


def ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS boq_uploads(id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, uploaded_at TEXT, filename TEXT,
                   sha256 TEXT, stored_path TEXT, approval_status TEXT, meta TEXT, rows TEXT, validation TEXT)""")


def _num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip())
    except ValueError:
        return "invalid"


def validate(rows: list[dict], meta: dict) -> dict:
    errors, warnings, clean = [], [], []
    st_ = (meta.get("approval_status") or "").strip().lower()
    if st_ not in STATUSES:
        errors.append(f"approval_status must be one of {', '.join(STATUSES)}")
    if st_ == "approved":
        for k in ("approval_authority", "approval_date", "source_reference"):
            if not (meta.get(k) or "").strip():
                errors.append(f"an APPROVED BOQ needs '{k}' (who approved it, when, and the document reference)")
    if (meta.get("currency") or "").strip().upper() not in ("INR", "₹", "RS"):
        errors.append("currency is required and must be INR")
    if not (meta.get("drawing_revision") or "").strip():
        warnings.append("drawing_revision not given — the BOQ cannot be tied to a drawing revision")
    seen = set()
    for i, r in enumerate(rows, 1):
        k = {str(a).strip().lower().replace(" ", "_"): b for a, b in r.items() if a}
        desc = str(k.get("description") or "").strip()
        q, rate, amt, tax = _num(k.get("quantity") or k.get("qty")), _num(k.get("rate")), _num(k.get("amount")), _num(k.get("tax"))
        unit = str(k.get("unit") or "").strip()
        if not desc and q is None and amt is None:
            continue  # blank line
        line = f"line {i}"
        if not desc:
            errors.append(f"{line}: description missing")
        if q is None:
            errors.append(f"{line}: quantity missing")
        if "invalid" in (q, rate, amt, tax):
            errors.append(f"{line}: malformed number")
            continue
        if q is not None and q < 0:
            errors.append(f"{line}: negative quantity")
        if not unit:
            errors.append(f"{line}: unit missing")
        elif unit_of(unit) is None and unit.lower() not in ("point", "set", "ls", "job"):
            warnings.append(f"{line}: unit '{unit}' not recognised — the line can only be matched by exact item code")
        if q is not None and rate is not None and amt is not None and abs(q * rate - amt) > max(1.0, 0.01 * abs(amt)):
            errors.append(f"{line}: quantity × rate ({q * rate:,.2f}) ≠ amount ({amt:,.2f})")
        key = (str(k.get("item_code") or "").strip(), desc.lower(), unit.lower(), str(k.get("item_no") or ""))
        if key in seen:
            errors.append(f"{line}: duplicate item {key}")
        seen.add(key)
        clean.append(dict(item_no=k.get("item_no"), code=str(k.get("item_code") or "").strip(), description=desc[:300],
                          category=str(k.get("category") or "").strip(), qty=q, unit=unit, rate=rate,
                          amount=amt if amt is not None else (q * rate if q is not None and rate is not None else None), tax=tax,
                          source_reference=k.get("source_reference")))
    if not clean:
        errors.append("no BOQ lines found")
    return dict(ok=not errors, errors=errors, warnings=warnings, lines=len(clean), rows=clean)


def read_table(data: bytes, filename: str) -> list[dict]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(it)]
        return [dict(zip(head, row)) for row in it]
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))


def upload(con, project_id, data: bytes, filename: str, meta: dict, store_dir: str) -> dict:
    ensure(con)
    rows = read_table(data, filename)
    v = validate(rows, meta)
    sha = hashlib.sha256(data).hexdigest()
    if not v["ok"]:
        return dict(stored=False, validation={k: v[k] for k in ("ok", "errors", "warnings", "lines")})
    os.makedirs(store_dir, exist_ok=True)
    dst = os.path.join(store_dir, f"{sha}{os.path.splitext(filename)[1].lower()}")
    if not os.path.exists(dst):
        open(dst, "wb").write(data)  # original kept unchanged
    con.execute("INSERT INTO boq_uploads(project_id, uploaded_at, filename, sha256, stored_path, approval_status, meta, rows, validation) VALUES(?,?,?,?,?,?,?,?,?)",
                (project_id, datetime.now().isoformat(timespec="seconds"), filename, sha, dst, meta["approval_status"].lower(), json.dumps(meta),
                 json.dumps(v["rows"]), json.dumps({k: v[k] for k in ("ok", "errors", "warnings", "lines")})))
    return dict(stored=True, sha256=sha, approval_status=meta["approval_status"].lower(), validation={k: v[k] for k in ("ok", "errors", "warnings", "lines")})


def latest(con, project_id):
    ensure(con)
    r = con.execute("SELECT * FROM boq_uploads WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    return dict(r, meta=json.loads(r["meta"]), rows=json.loads(r["rows"])) if r else None


def _words(s):
    s = re.sub(r"\bm\s*-\s*(\d\d)", r"m\1", (s or "").lower())
    return set(re.findall(r"[a-z]{3,}|\d+:\d+(?::\d+)?|m\d\d", s)) | ({"rcc"} if re.search(r"reinforced cement concrete|\brcc\b", s) else set())


def _compat(a, b):
    ua, ub = unit_of(a), unit_of(b)
    return ua is not None and ub is not None and ua[0] == ub[0] and ua[1] == ub[1]


def compare(boq_rows: list[dict], est_items: list[dict], approved_codes: dict | None = None) -> dict:
    approved_codes = approved_codes or {}
    used, pairs, unmatched_ref = set(), [], []
    for x in boq_rows:
        hit, how = None, None
        if x["code"]:
            hit = next((i for i in est_items if i["key"] not in used and i.get("sor_code") == x["code"]), None)
            how = "exact item code" if hit else None
            if not hit:
                hit = next((i for i in est_items if i["key"] not in used and approved_codes.get(i["key"]) == x["code"]), None)
                how = "engineer-approved mapping" if hit else None
        if not hit:
            cands = []
            for i in est_items:
                if i["key"] in used:
                    continue
                txt = " ".join(str(t) for t in (i["description"], i.get("sor_desc"), (i.get("derived") or {}).get("description"),
                                                 i["key"].replace("_", " ")) if t)  # the key names the element (rcc_slab → 'slab')
                sim = len(_words(x["description"]) & _words(txt)) / max(1, len(_words(x["description"])))
                if sim >= 0.35:
                    cands.append((sim, i))
            cands.sort(key=lambda t: -t[0])
            ok = [(s, i) for s, i in cands if _compat(x["unit"], i["unit"])]
            if len(ok) > 1 and abs(ok[0][0] - ok[1][0]) < 1e-9:
                unmatched_ref.append(dict(x, reason=f"ambiguous: '{ok[0][1]['key']}' and '{ok[1][1]['key']}' match equally — give an item code"))
                continue
            if ok:
                hit, how = ok[0][1], f"description ({ok[0][0]:.2f}) + same unit"
            elif cands:
                unmatched_ref.append(dict(x, reason=f"best description match '{cands[0][1]['key']}' has an incompatible unit "
                                                    f"({x['unit']} vs {cands[0][1]['unit']}) — not matched"))
                continue
        if not hit:
            unmatched_ref.append(dict(x, reason="no estimate line with the same code / approved mapping / description + unit"))
            continue
        used.add(hit["key"])
        qerr = None if x["qty"] is None else hit["qty"] - x["qty"]
        rel = None if not x["qty"] else qerr / x["qty"]
        est_amt = hit["amount"] if hit.get("rate") is not None else None
        pairs.append(dict(boq=x, key=hit["key"], family=FAMILY.get(hit["category"], "other"), method=how, unit_compatible=True,
                          reference_qty=x["qty"], estimated_qty=hit["qty"], abs_qty_diff=None if qerr is None else round(abs(qerr), 3),
                          rel_qty_diff=None if rel is None else round(rel, 4), reference_amount=x["amount"], estimated_amount=est_amt,
                          estimate_priced=est_amt is not None, mapping_status=hit.get("map_method")))
    unmatched_est = [dict(key=i["key"], description=i["description"][:100], qty=i["qty"], unit=i["unit"], amount=i["amount"])
                     for i in est_items if i["key"] not in used]
    return dict(pairs=pairs, unmatched_reference=unmatched_ref, unmatched_estimate=unmatched_est)


def metrics(cmp: dict, est: dict, boq_rows: list[dict], meta: dict) -> dict:
    pairs = cmp["pairs"]
    q = [abs(p["rel_qty_diff"]) for p in pairs if p["rel_qty_diff"] is not None]
    cost = [(p["estimated_amount"], p["reference_amount"]) for p in pairs if p["estimated_amount"] is not None and p["reference_amount"]]
    ae = [abs(a - b) for a, b in cost]
    ref_total = sum((x["amount"] or 0) for x in boq_rows)
    matched_ref = sum((p["reference_amount"] or 0) for p in pairs)
    priced_ref = sum((p["reference_amount"] or 0) for p in pairs if p["estimated_amount"] is not None)
    fam = {}
    for p in pairs:
        f = fam.setdefault(p["family"], dict(lines=0, qty_rel_err=[], est=0.0, ref=0.0))
        f["lines"] += 1
        if p["rel_qty_diff"] is not None:
            f["qty_rel_err"].append(abs(p["rel_qty_diff"]))
        if p["estimated_amount"] is not None and p["reference_amount"]:
            f["est"] += p["estimated_amount"]
            f["ref"] += p["reference_amount"]
    fam = {k: dict(lines=v["lines"], qty_median_ape_pct=round(st.median(v["qty_rel_err"]) * 100, 2) if v["qty_rel_err"] else None,
                   cost_error_pct=round((v["est"] / v["ref"] - 1) * 100, 2) if v["ref"] else None) for k, v in fam.items()}
    taxes = str(meta.get("taxes_included", "")).lower() in ("yes", "true", "1")
    est_cmp_total = est["total"] if taxes else est["subtotal"]
    return dict(
        validation_grade="VALIDATED (approved BOQ)" if meta.get("approval_status") == "approved" else f"PROVISIONAL ({meta.get('approval_status')}) — not validation",
        reference_lines=len(boq_rows), matched=len(pairs), unmatched_reference=len(cmp["unmatched_reference"]), unmatched_estimate=len(cmp["unmatched_estimate"]),
        quantity=dict(n=len(q), median_ape_pct=round(st.median(q) * 100, 2) if q else None, within5_pct=round(100 * sum(e <= .05 for e in q) / len(q), 1) if q else None,
                      within10_pct=round(100 * sum(e <= .10 for e in q) / len(q), 1) if q else None,
                      zero_reference_lines=sum(1 for p in pairs if not p["reference_qty"])),
        item_cost=dict(n=len(cost), mae=round(st.mean(ae), 2) if ae else None, median_ae=round(st.median(ae), 2) if ae else None,
                       wape_pct=round(100 * sum(ae) / sum(abs(b) for _, b in cost), 2) if cost else None,
                       signed_bias_pct=round(100 * (sum(a for a, _ in cost) / sum(b for _, b in cost) - 1), 2) if cost else None,
                       within10_pct=round(100 * sum(abs(a - b) <= 0.1 * abs(b) for a, b in cost) / len(cost), 1) if cost else None),
        total=dict(reference_total=round(ref_total, 2), estimate_total_compared=round(est_cmp_total, 2),
                   basis="estimate total incl. contingency, cess, GST" if taxes else "estimate works subtotal (reference excludes taxes)",
                   total_error_pct=round((est_cmp_total / ref_total - 1) * 100, 2) if ref_total else None),
        completeness=dict(matched_reference_amount_pct=round(100 * matched_ref / ref_total, 1) if ref_total else None,
                          priced_reference_amount_pct=round(100 * priced_ref / ref_total, 1) if ref_total else None,
                          unpriced_matched_amount=round(matched_ref - priced_ref, 2),
                          unmatched_reference_amount=round(sum((x.get("amount") or 0) for x in cmp["unmatched_reference"]), 2)),
        by_family=fam,
        scope=dict(inclusions=meta.get("inclusions"), exclusions=meta.get("exclusions"), taxes_included=taxes, drawing_revision=meta.get("drawing_revision"),
                   note="differences in scope / exclusions / provisional sums are NOT model error — investigate before interpreting the total"))
