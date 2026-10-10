"""Rate analysis from a state's official BASIC rates (materials + labour).

Several State SORs (Telangana, Andhra Pradesh, Tamil Nadu, Puducherry, Odisha …) publish the basic rates of
materials and labour, while the rate of a finished item (brickwork, RCC, plaster …) is built by the engineer
from standard data. This module does exactly that, transparently:

    item rate = Σ (consumption per unit × that state's official basic rate) × (1 + overheads & profit)

* Basic rates come ONLY from the project's own schedule, through the resource codes listed per schedule below
  (looked up and checked against the source PDF). If any resource of a recipe is missing from that schedule the
  item is left unpriced — nothing is borrowed from another state.
* Consumption figures are standard engineering values for these specifications (cement / sand / aggregate per
  m³ of concrete or mortar, bricks per m³, labour days per unit), in line with CPWD analysis-of-rates practice.
  They are an ESTIMATING standard, not part of the state SOR, and every derived rate says so and shows its
  full breakdown so the engineer can check or replace it with the state's own Standard Data.
"""
from __future__ import annotations

# resource keys -> unit used in the recipes
RES_UNIT = dict(cement="tonne", sand="cum", psand="cum", agg20="cum", agg40="cum", brick="1000 nos", steel="tonne",
                wire="kg", tile="sqm", emulsion="litre", primer="litre", putty="kg", extpaint="litre", ply="sqm",
                mason="day", mazdoor="day", carpenter="day", barbender="day", painter="day", flush="sqm", dframe="metre")

# per unit of the take-off item (units as in takeoff.py)
_CONC = lambda c, s, a, agg="agg20", mason=0.17, maz=1.8: {"cement": c, "sand": s, agg: a, "mason": mason, "mazdoor": maz}
RECIPES = {
    "site_clearance": ("sqm", {"mazdoor": 0.02}, "Clearing site, manual"),
    "excavation": ("cum", {"mazdoor": 0.60}, "Excavation in ordinary soil up to 1.5 m, manual"),
    "backfill": ("cum", {"mazdoor": 0.25}, "Back filling with excavated earth, ramming"),
    "sand_fill": ("cum", {"sand": 1.20, "mazdoor": 0.25}, "Sand filling under floors, consolidated"),
    "pcc_found": ("cum", _CONC(0.17, 0.47, 0.94, "agg40", 0.10, 1.60), "PCC 1:4:8 (40 mm aggregate)"),
    "pcc_floor": ("cum", _CONC(0.32, 0.44, 0.88), "PCC 1:2:4 (20 mm aggregate)"),
    "rcc_footing": ("cum", _CONC(0.40, 0.42, 0.84, mason=0.25, maz=2.5), "RCC 1:1.5:3 (M20) footings, excl. steel & formwork"),
    "rcc_column": ("cum", _CONC(0.40, 0.42, 0.84, mason=0.35, maz=3.0), "RCC 1:1.5:3 (M20) columns, excl. steel & formwork"),
    "rcc_beam": ("cum", _CONC(0.40, 0.42, 0.84, mason=0.35, maz=3.0), "RCC 1:1.5:3 (M20) beams, excl. steel & formwork"),
    "rcc_slab": ("cum", _CONC(0.40, 0.42, 0.84, mason=0.30, maz=2.8), "RCC 1:1.5:3 (M20) slabs, excl. steel & formwork"),
    "rcc_lintel": ("cum", _CONC(0.40, 0.42, 0.84, mason=0.35, maz=3.0), "RCC 1:1.5:3 (M20) lintels, excl. steel & formwork"),
    "fw_found": ("sqm", {"ply": 0.10, "carpenter": 0.12, "mazdoor": 0.15}, "Formwork to foundations (plywood, ~10 uses)"),
    "fw_col": ("sqm", {"ply": 0.12, "carpenter": 0.18, "mazdoor": 0.20}, "Formwork to columns (plywood, ~10 uses)"),
    "fw_beam": ("sqm", {"ply": 0.12, "carpenter": 0.18, "mazdoor": 0.22}, "Formwork to beams (plywood, ~10 uses)"),
    "fw_slab": ("sqm", {"ply": 0.12, "carpenter": 0.15, "mazdoor": 0.20}, "Formwork to slabs incl. propping (plywood, ~10 uses)"),
    "mas_plinth": ("cum", {"brick": 0.50, "cement": 0.060, "sand": 0.28, "mason": 0.80, "mazdoor": 1.60}, "Brick masonry in CM 1:6, foundation & plinth"),
    "mas_230": ("cum", {"brick": 0.50, "cement": 0.060, "sand": 0.28, "mason": 0.90, "mazdoor": 1.70}, "Brick masonry 230 mm in CM 1:6, superstructure"),
    "mas_115": ("sqm", {"brick": 0.057, "cement": 0.0085, "sand": 0.025, "mason": 0.13, "mazdoor": 0.18}, "Half-brick masonry 115 mm in CM 1:4"),
    "plaster_int": ("sqm", {"cement": 0.0035, "psand": 0.017, "mason": 0.07, "mazdoor": 0.07}, "12 mm cement plaster 1:6"),
    "plaster_ext": ("sqm", {"cement": 0.0063, "psand": 0.020, "mason": 0.08, "mazdoor": 0.08}, "15 mm cement plaster 1:4"),
    "plaster_ceil": ("sqm", {"cement": 0.0035, "psand": 0.0085, "mason": 0.08, "mazdoor": 0.08}, "6 mm cement plaster 1:3 to ceiling"),
    "steel_footing": ("kg", {"steel": 0.00105, "wire": 0.010, "barbender": 0.010, "mazdoor": 0.010}, "Reinforcement incl. cutting, bending, binding"),
    "steel_column": ("kg", {"steel": 0.00105, "wire": 0.010, "barbender": 0.012, "mazdoor": 0.012}, "Reinforcement incl. cutting, bending, binding"),
    "steel_beam": ("kg", {"steel": 0.00105, "wire": 0.010, "barbender": 0.012, "mazdoor": 0.012}, "Reinforcement incl. cutting, bending, binding"),
    "steel_slab": ("kg", {"steel": 0.00105, "wire": 0.010, "barbender": 0.010, "mazdoor": 0.010}, "Reinforcement incl. cutting, bending, binding"),
    "floor_vit": ("sqm", {"tile": 1.05, "cement": 0.012, "sand": 0.024, "mason": 0.20, "mazdoor": 0.20}, "Vitrified tile flooring on 20 mm CM 1:4 bed"),
    "floor_antiskid": ("sqm", {"tile": 1.05, "cement": 0.012, "sand": 0.024, "mason": 0.22, "mazdoor": 0.22}, "Anti-skid tile flooring on 20 mm CM 1:4 bed"),
    "dado": ("sqm", {"tile": 1.05, "cement": 0.008, "sand": 0.015, "mason": 0.25, "mazdoor": 0.25}, "Tile dado on 12 mm CM 1:3"),
    "skirting": ("sqm", {"tile": 1.05, "cement": 0.008, "sand": 0.015, "mason": 0.25, "mazdoor": 0.25}, "Tile skirting on 12 mm CM 1:3"),
    "putty": ("sqm", {"putty": 0.75, "painter": 0.05, "mazdoor": 0.01}, "Wall putty, 2 coats"),
    "paint_int": ("sqm", {"primer": 0.09, "emulsion": 0.17, "painter": 0.07}, "Primer + 2 coats acrylic emulsion, interior"),
    "door_shutter": ("sqm", {"flush": 1.0, "carpenter": 0.20, "mazdoor": 0.10},
                     "Flush door shutter 35 mm, teak ply both faces (official supply rate) + fixing labour; hinges & fittings NOT included"),
    "door_frame": ("metre", {"dframe": 1.0, "mason": 0.03, "mazdoor": 0.05},
                   "Factory door frame per metre (official rate: TS MS pressed, AP GI powder-coated, TN RCC 100×65) + fixing — "
                   "SPECIFICATION DIFFERS from the timber 100×60 frame of the take-off; engineer to confirm"),
    "paint_ext": ("sqm", {"primer": 0.09, "extpaint": 0.20, "painter": 0.07}, "Primer + 2 coats exterior acrylic paint"),
}

# official resource codes per schedule numbering system: resource -> [(code, factor to recipe unit)]
# factor converts the schedule's unit to the recipe unit (e.g. quintal -> tonne = 10)
RESOURCES = {
    "TN-SOR": dict(cement=[("M-0001", 1)], sand=[("M-0125", 1)], psand=[("M-0126", 1)], agg20=[("M-0088", 1)],
                   agg40=[("M-0086", 1)], brick=[("M-0006", 1)], steel=[("M-0002", 1)], wire=[("M-0188", 1)],
                   tile=[("M-0218", 1)], emulsion=[("M-0420", 1)], primer=[("M-0419", 1)], putty=[("M-0428", 1)],
                   extpaint=[("M-0426", 1)], ply=[("M-0628", 1)], flush=[("M-0387", 1)], dframe=[("M-0398", 1)], mason=[("L-0029", 1)], mazdoor=[("L-0073", 1)],
                   carpenter=[("L-0016", 1)], barbender=[("L-0019", 1)], painter=[("L-0036", 1)]),
    "PY-PSR": dict(cement=[("0367", 1)], sand=[("0100B", 1)], psand=[("0100B", 1)], agg20=[("0295", 1), ("0109", 1)],
                   agg40=[("0293", 1), ("0110", 1)], brick=[("0121", 1), ("0120", 1)], steel=[("0103A", 1)], wire=[("7335", 1)],
                   tile=[("2752", 1)], emulsion=[("0803", 1)], primer=[("0808", 1)], putty=[("0824", 1)], extpaint=[("8505", 1)],
                   ply=[("8724", 1)], flush=[("0713", 1)], mason=[("0007", 1)], mazdoor=[("0191", 1)], carpenter=[("0111", 1)],
                   barbender=[("0102", 1)], painter=[("0131", 1)]),
}
# Telangana: labour rates are official per zone (I municipal corporations, II municipalities, III rural) -> {Z}
RESOURCES["TS-CSR"] = dict(cement=[("P1-5a", 1)], sand=[("P1-27a", 1)], psand=[("P1-28", 1)], agg20=[("P1-8", 1)],
                           agg40=[("P1-9", 1)], brick=[("TBSC-A.I-01", 1000)], steel=[("P1-62a", 1)], wire=[("P1-3", 1)],
                           tile=[("TBSC-C.II-01", 1)], emulsion=[("TBSC-G.III-01", 1)], primer=[("TBSC-G.I-01", 1)],
                           putty=[("TBSC-G.I-03", 1)], extpaint=[("TBSC-G.III-02", 1)], ply=[("TBSC-J.II-05", 1)], flush=[("TBSC-L.II-03", 1)], dframe=[("TBSC-L.I-01", 1)],
                           mason=[("LAB-I-11-{Z}", 1)], mazdoor=[("LAB-III-1-{Z}", 1)], carpenter=[("LAB-I-4-{Z}", 1)],
                           barbender=[("LAB-I-1-{Z}", 1)], painter=[("LAB-I-35-{Z}", 1)])
# Andhra Pradesh: Buildings SoR 2025-26 + PRED 'Labour Rates and Conveyance 2024-25' basic table. AP does not print cement
# or reinforcement steel (monthly rate fixed by the Sub-Committee) -> taken from the rate the engineer enters.
RESOURCES["AP-BSOR"] = dict(sand=[("MAT-00027", 1)], psand=[("MAT-00029", 1)], agg20=[("MAT-00218", 1)], agg40=[("MAT-00220", 1)],
                            brick=[("MAT-00721", 1)], wire=[("MAT-00003", 1)], tile=[("MAT-00791", 1)], emulsion=[("MAT-01097", 1)],
                            primer=[("MAT-01073", 1)], putty=[("BMT-J.31", 1 / 20)], extpaint=[("MAT-01094", 1)], flush=[("BMT-N.14", 1)], dframe=[("BMT-N.100", 1)],
                            mason=[("LAB-00011", 1)], mazdoor=[("LAB-00120", 1)], carpenter=[("LAB-00004", 1)],
                            barbender=[("LAB-00001", 1)], painter=[("LAB-00035", 1)])
USER_RESOURCES = {"cement": "cement_rate", "steel": "steel_rate"}  # resource -> project parameter (₹ per tonne)
OVERHEAD = {"TN-SOR": 15.0, "PY-PSR": 15.0, "TS-CSR": 13.615, "AP-BSOR": 15.0}  # TS SOR states 13.615% contractor's profit & overheads  # contractor's overheads & profit applied on the analysed cost
BASIC_RATE_SYSTEMS = {"TS-CSR", "AP-BSOR", "TN-SOR", "PY-PSR", "OD-SOR"}


def derive(key: str, code_system: str, by_code: dict, zone: str = "Z1", user: dict | None = None) -> dict | None:
    """Analysed rate for one take-off item, or None when the recipe or any official basic rate is missing."""
    rec = RECIPES.get(key)
    res = RESOURCES.get(code_system)
    if not rec or not res:
        return None
    unit, cons, desc = rec
    parts, base, missing = [], 0.0, []
    for r, q in cons.items():
        hit = next(((c.replace("{Z}", zone), f) for c, f in res.get(r, []) if c.replace("{Z}", zone) in by_code), None)
        if not hit:
            uv = float((user or {}).get(USER_RESOURCES.get(r, "-")) or 0)
            if uv > 0:  # rate the engineer entered because this schedule does not print it
                amt = q * uv
                base += amt
                parts.append(dict(resource=r, code="USER", description=f"{r} — rate entered on the estimate (not printed in this SOR)",
                                  sor_unit=RES_UNIT[r], qty=q, unit=RES_UNIT[r], rate=uv, amount=round(amt, 2)))
                continue
            missing.append(r)
            continue
        c, f = hit
        item = by_code[c]
        rate = float(item["rate"]) * f
        amt = q * rate
        base += amt
        parts.append(dict(resource=r, code=c, description=item["description"][:90], sor_unit=item["unit"], qty=q,
                          unit=RES_UNIT[r], rate=round(rate, 2), amount=round(amt, 2)))
    if missing:
        return dict(ok=False, missing=missing, unit=unit, description=desc)
    oh = OVERHEAD.get(code_system, 15.0)
    return dict(ok=True, unit=unit, description=desc, components=parts, base=round(base, 2), overhead_pct=oh,
                rate=round(base * (1 + oh / 100), 2),
                basis=f"Rate analysis: standard consumption × official basic rates of this schedule + {oh:g}% overheads & profit")
