"""Scale guard: makes an ASSUMED raster scale consistent with what the user said and with how buildings are built.

Runs after analysis, for every plan, never for a sheet whose scale is already MEASURED (CAD units, printed scale,
written dimensions, plinth-area note, user calibration). In order of trust:

  1. user-entered built-up area (scope config 'built_up_area_m2', total over the floors drawn) → per-floor target
  2. typical room sizes: labelled rooms (bedroom, kitchen, toilet, living, dining) whose measured areas are implausible
     for their type (a 5 m² bedroom) reveal a wrong scale; the median ratio to typical sizes corrects it

Both return a LINEAR factor k (real / measured length) and a reason; app.py re-runs the sheet's analysis with it, exactly
like a user calibration. A prior-based correction stays NEEDS REVIEW (it is an estimate, not a measurement).
"""
from __future__ import annotations

import math
import statistics

# typical clear room areas in Indian residential / institutional plans (m²) and the plausible band around them
TYPICAL = {"bedroom": (11.0, 7.0, 20.0), "kitchen": (7.5, 4.5, 14.0), "toilet": (3.5, 2.0, 7.0), "living": (15.0, 9.0, 32.0),
           "dining": (10.0, 6.0, 20.0), "office_zone": (12.0, 6.0, 40.0)}
TYPE_WORDS = {"bedroom": ("BED", "BEDROOM", "B.R", "BR"), "kitchen": ("KITCHEN", "KIT"), "toilet": ("TOILET", "BATH", "WC", "W.C"),
              "living": ("LIVING", "HALL", "DRAWING"), "dining": ("DINING",)}


def room_kind(r: dict) -> str | None:
    t = (r.get("room_type") or r.get("type") or "").lower()
    if t in TYPICAL:
        return t
    n = str(r.get("name") or "").upper()
    for k, words in TYPE_WORDS.items():
        if any(w in n for w in words):
            return k
    return None


def prior_factor(sheet: dict) -> tuple[float, str] | None:
    """Linear correction from typical room sizes, or None when the measured rooms are plausible / too few."""
    ratios, out_of_band = [], 0
    for r in sheet.get("rooms") or []:
        k = room_kind(r)
        a = r.get("area") or 0
        if not k or a <= 0.3:
            continue
        typ, lo, hi = TYPICAL[k]
        ratios.append(typ / a)
        out_of_band += a < lo  # only too-SMALL rooms reveal a wrong scale; big halls / classrooms are normal in public buildings
    if len(ratios) < 3 or out_of_band < max(2, math.ceil(0.6 * len(ratios))):
        return None
    k_area = statistics.median(ratios)
    if k_area <= 1.7:  # normal variation, or rooms larger than typical (halls, classrooms): leave the scale alone
        return None
    k = math.sqrt(k_area)
    return k, f"auto: typical room sizes ({len(ratios)} labelled rooms, {out_of_band} implausible) — area ×{k_area:.2f}"


def user_area_factor(sheet: dict, user_total_m2: float | None, n_plans: int) -> tuple[float, str] | None:
    plinth = (sheet.get("metrics") or {}).get("plinth_area") or 0
    if not user_total_m2 or plinth <= 0 or n_plans <= 0:
        return None
    target = user_total_m2 / n_plans
    k_area = target / plinth
    if 0.85 <= k_area <= 1.18:
        return None
    return math.sqrt(k_area), f"user-entered built-up area {user_total_m2:.0f} m² over {n_plans} floor plan(s)"


def needs_guard(sheet: dict) -> bool:
    cal = (sheet.get("areas") or {}).get("calibration") or {}
    return sheet.get("kind") == "floor_plan" and sheet.get("source") in ("image", "pdf") and cal.get("status") not in ("MEASURED", "USER-CONFIRMED") \
        and "scale_guard" not in sheet and not sheet.get("derived_floor") and not sheet.get("area_only")


def cost_range(total: float, sheets: list[dict]) -> dict | None:
    """Total ± the area uncertainty of the least certain floor plan (quantities scale with area)."""
    unc = [((s.get("areas") or {}).get("calibration") or {}).get("relative_uncertainty") for s in sheets if s.get("kind") == "floor_plan"]
    unc = [u for u in unc if u]
    if not total or not unc:
        return None
    u = max(unc)
    if u <= 0.06:
        return None
    return dict(low=round(total * (1 - u)), high=round(total * (1 + u)), relative=u,
                note="range from the drawing's scale uncertainty — calibrate one known dimension to narrow it")
