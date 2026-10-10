"""Explainable confidence (Task 15). Signals are kept separate — a detector score is never reused as confidence in the
whole estimate:

  quantity   basis class (explicit / derived / partly assumed / assumed) + the sheet's scale-calibration status
  mapping    engineer-approved > reviewed item map / Standard Data analysis > learned > automatic suggestion > none
  rate       provenance verification (official / cross-verified > unverified secondary source) ; missing rate
  estimate   completeness (items priced), structural input, assumed share of cost

Labels: HIGH CONFIDENCE · NEEDS REVIEW · LOW CONFIDENCE · INSUFFICIENT INPUT.
Numeric calibration (reliability diagrams, ECE, Brier) needs labelled outcomes — none exist for Tamil Nadu yet, so every
probability-like score is reported as NOT CALIBRATED.
"""
from __future__ import annotations

CALIBRATION_STATUS = "NOT CALIBRATED — no labelled Tamil Nadu outcomes to calibrate against (validation-only calibration pending)"


def item(it: dict, scale_status: str | None) -> dict:
    reasons = []
    bc = it.get("basis_class")
    if it.get("rate") is None:
        return dict(label="INSUFFICIENT INPUT", reasons=[f"no usable TN rate ({it.get('rate_gap') or 'NEEDS RATE'})"])
    q_ok = bc in ("explicit", "derived", "user input")
    if bc in ("assumed",):
        reasons.append("quantity relies on assumptions")
    elif bc == "partly assumed":
        reasons.append("quantity partly assumed")
    if scale_status == "UNRESOLVED":
        reasons.append("drawing scale unresolved")
        q_ok = False
    elif scale_status == "NEEDS REVIEW":
        reasons.append("drawing scale assumed")
        q_ok = False
    mm = it.get("map_method")
    m_ok = mm in ("engineer-approved", "table", "analysis")
    if mm == "learned":
        reasons.append("mapping learned from earlier confirmed estimates (not reviewed for this project)")
    elif not m_ok:
        reasons.append(f"mapping is an automatic suggestion ({mm})")
    pv = (it.get("rate_provenance") or {}).get("verification") or ""
    r_ok = pv in ("official source", "cross-verified")
    if not r_ok:
        reasons.append(f"rate source verification: {pv or 'unknown'}")
    if q_ok and m_ok and r_ok:
        return dict(label="HIGH CONFIDENCE", reasons=["drawing-derived quantity, reviewed mapping, verified rate source"])
    if not q_ok and bc == "assumed":
        return dict(label="LOW CONFIDENCE", reasons=reasons)
    return dict(label="NEEDS REVIEW", reasons=reasons)


def estimate(est: dict, completeness: dict, structural_status: str, items_conf: list[dict]) -> dict:
    reasons = []
    if not completeness.get("complete"):
        reasons.append(f"{completeness.get('unresolved')} item(s) unpriced — total is incomplete")
    if "MISSING" in (structural_status or ""):
        reasons.append("structural input missing — structure quantities assumed")
    amt = sum(i["amount"] for i in est["items"]) or 1
    low = sum(i["amount"] for i, c in zip(est["items"], items_conf) if c["label"] in ("LOW CONFIDENCE", "NEEDS REVIEW"))
    if low / amt > 0.25:
        reasons.append(f"{100 * low / amt:.0f}% of the priced amount needs review or is low confidence")
    label = "HIGH CONFIDENCE" if not reasons else ("INSUFFICIENT INPUT" if not completeness.get("complete") and completeness.get("priced", 0) < 0.5 * completeness.get("total", 1)
                                                  else "NEEDS REVIEW")
    return dict(label=label, reasons=reasons, calibration=CALIBRATION_STATUS,
                by_label={k: sum(1 for c in items_conf if c["label"] == k) for k in ("HIGH CONFIDENCE", "NEEDS REVIEW", "LOW CONFIDENCE", "INSUFFICIENT INPUT")})
