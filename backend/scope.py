"""Estimation scope — what part of the property / work the estimate covers.

One estimation engine; the scope is metadata that (1) sets which cost categories count in the total, (2) decides
whether storeys are multiplied, and (3) is shown on every report. Nothing is invented: out-of-scope lines are still
quantified and listed (excluded from the total), and storey repetition only comes from drawings or user input.

    type       default categories in the total                  storeys
    room       finishes & internal work (no substructure/frame) 1 (never asks for a floor count)
    section    finishes & internal work (structure optional)    config.repeat (user, default 1)
    floors     all                                              per-plan floor labels / repeats (existing logic)
    property   all                                              per-plan floor labels / repeats (existing logic)
    custom     user-selected categories                         per-plan floor labels / repeats
"""
from __future__ import annotations

from sor import CATEGORY_ORDER

TYPES = {
    "room": "Room or small area",
    "section": "Selected section",
    "floors": "Floor or multiple floors",
    "property": "Entire property",
    "custom": "Custom scope (selected work)",
}
FINISHES = ["Masonry", "Plastering", "Flooring", "Painting", "Doors & Windows", "Waterproofing", "Electrical",
            "Plumbing & Sanitary", "Miscellaneous"]
STRUCTURE = ["Earthwork", "Concrete Works", "RCC Works", "Formwork", "Reinforcement"]
PRESETS = {"room": FINISHES, "section": FINISHES, "floors": CATEGORY_ORDER, "property": CATEGORY_ORDER, "custom": CATEGORY_ORDER}
# building-configuration fields shown per project type (all optional context; never used as measured dimensions)
CONFIG_FIELDS = {
    "apartment": ["blocks", "floors", "units", "parking", "lifts", "staircases", "typical_floors"],
    "house": ["storeys", "houses", "built_up_area_m2", "roof_type"],
    "institutional": ["blocks", "floors", "beds_or_rooms", "occupancy", "special_services"],
    "other": ["blocks", "floors", "notes"],
}
LABELS = ["Bedroom", "Bathroom / toilet", "Kitchen", "Living / dining", "Office room", "Ground floor", "First floor",
          "Second floor", "Typical floor", "Terrace", "Basement / stilt", "Foundation", "Structural drawing",
          "Electrical layout", "Plumbing layout", "Site plan", "Elevation / section", "Custom section"]


def default() -> dict:
    """Projects created before scopes existed: whole property, all categories (unchanged behaviour)."""
    return dict(type="property", label="", categories=list(CATEGORY_ORDER), config={}, user_set=False)


def normalize(sc: dict | None) -> dict:
    out = default()
    if not sc:
        return out
    t = sc.get("type") if sc.get("type") in TYPES else "property"
    out.update(type=t, label=str(sc.get("label") or "").strip()[:120], user_set=True)
    cats = sc.get("categories")
    out["categories"] = [c for c in CATEGORY_ORDER if c in cats] if isinstance(cats, list) and cats else list(PRESETS[t])
    cfg = sc.get("config") if isinstance(sc.get("config"), dict) else {}
    out["config"] = {k: v for k, v in cfg.items() if v not in (None, "")}
    return out


def effective_params(params: dict, sc: dict) -> dict:
    """Storeys for the take-off. Room scope never multiplies by a floor count; a section repeats only if the user said so."""
    p = dict(params or {})
    if sc["type"] == "room":
        p["floors"] = 1
    elif sc["type"] == "section":
        try:
            p["floors"] = max(1, int(sc["config"].get("repeat") or 1))
        except (TypeError, ValueError):
            p["floors"] = 1
    return p


# new-foundation / ground-floor substructure work — not part of an upper-floor extension unless the user includes it
SUBSTRUCTURE_KEYS = {"site_clearance", "excavation", "backfill", "sand_fill", "anti_termite", "pcc_found", "pcc_floor",
                     "rcc_footing", "fw_found", "steel_footing", "mas_plinth"}
STRUCTURE_CATS = {"Concrete Works", "RCC Works", "Formwork", "Reinforcement"}


def plan_floors(s: dict) -> set:
    """Floor numbers a plan stands for — user-set floor first, else what the drawing text states; empty if unknown."""
    fl = s.get("floor") or {}
    occ = fl.get("occurrences") or (s.get("floor_info") or {}).get("floor_occurrences")
    if occ:
        return set(int(x) for x in occ)
    if fl.get("level") is not None:
        return set(range(int(fl["level"]), int(fl["level"]) + max(1, int(fl.get("repeat", 1)))))
    return set()


# work that follows from the plinth area alone (open platforms / sheds whose sheet gives only the plinth area)
AREA_ONLY_KEYS = {"site_clearance", "sand_fill", "anti_termite", "pcc_floor"}


def context(sheets: list[dict]) -> dict:
    """Evidence the exclusion rules depend on (recomputed from the current drawings every time)."""
    plans = [s for s in sheets if s.get("enabled", True) and s.get("kind") == "floor_plan"]
    per = [plan_floors(s) for s in plans]
    known = [f for f in per if f]
    floors_all = sorted(set().union(*known)) if known else []
    return dict(floors=floors_all, area_only=bool(plans) and all(s.get("area_only") for s in plans),
                upper_only=bool(plans) and len(known) == len(plans) and min(floors_all) >= 1,  # every plan is floor ≥ 1
                has_structural=any(s.get("enabled", True) and (s.get("kind") == "structural" or s.get("structural")) for s in sheets))


def exclusion(item: dict, sc: dict, ctx: dict):
    """None if the line counts in the total; else (kind, reason) with kind 'scope' (outside what the user asked to
    estimate) or 'unresolved' (in scope, but its quantity cannot be supported by the evidence under the chosen policy)."""
    if item.get("custom"):
        return None  # items the user added by hand are always part of the estimate
    if item.get("category") not in sc["categories"]:
        return ("scope", "work category not in the selected scope")
    if item.get("key") in SUBSTRUCTURE_KEYS and ctx.get("upper_only") and not sc["config"].get("include_foundation"):
        return ("scope", f"upper-floor work only (floors {', '.join(map(str, ctx['floors']))}) — no new foundation / ground-floor "
                         "substructure; include foundation in the scope if this work needs it")
    if ctx.get("area_only") and item.get("key") not in AREA_ONLY_KEYS:
        return ("unresolved", "open / area-only structure: only the plinth area is known from the drawing — walls, roof, frame "
                              "and finishes are not measured; add them as items if this structure has them")
    basis = str(item.get("basis") or "")
    if sc["config"].get("assumption_policy") == "strict" and item.get("category") in STRUCTURE_CATS and "assumed" in basis \
            and not ctx.get("has_structural"):
        return ("unresolved", "structural quantity would be ASSUMED (no structural drawing / schedule) — left unresolved under "
                              "the strict assumption policy; upload the structural drawings or allow provisional assumptions")
    return None


def in_scope(item: dict, sc: dict, ctx: dict | None = None) -> bool:
    return exclusion(item, sc, ctx or {}) is None


def describe(sc: dict) -> str:
    t = TYPES[sc["type"]] + (f" — {sc['label']}" if sc.get("label") else "")
    if set(sc["categories"]) != set(CATEGORY_ORDER):
        t += " · work included: " + ", ".join(sc["categories"])
    return t
