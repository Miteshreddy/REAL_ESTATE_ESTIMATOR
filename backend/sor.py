"""PWD Schedule of Rates (seed library).

Rates are INDICATIVE figures in the style of CPWD DSR / State PWD SOR (INR, incl. materials,
labour & contractor's profit). They are meant to be replaced/edited by the estimation team or
overwritten through CSV import of the applicable state SOR.
"""

SEED_SOR = [
    # code, description, unit, rate, category
    ("2.1.1", "Clearing jungle including uprooting of rank vegetation, grass, brush wood, trees and saplings of girth up to 30 cm", "sqm", 18.40, "Earthwork"),
    ("2.8.1", "Earth work in excavation by mechanical means (hydraulic excavator) / manual means in foundation trenches or drains, including dressing of sides and ramming of bottoms, lift up to 1.5 m, disposal of excavated earth up to 50 m", "cum", 312.55, "Earthwork"),
    ("2.25", "Filling available excavated earth in trenches, plinth, sides of foundations in layers not exceeding 20 cm, consolidating each layer by ramming and watering", "cum", 186.40, "Earthwork"),
    ("2.33", "Supplying and filling local sand / murrum under floors including watering, ramming and consolidating", "cum", 1645.00, "Earthwork"),
    ("2.34", "Anti-termite treatment: pre-constructional chemical treatment of soil with chlorpyriphos emulsifiable concentrate (plinth area measured)", "sqm", 52.10, "Earthwork"),

    ("4.1.8", "Providing and laying in position cement concrete of specified grade excluding cost of centering and shuttering - All work up to plinth level: 1:4:8 (1 cement : 4 coarse sand : 8 graded stone aggregate 40 mm nominal size) PCC", "cum", 6380.00, "Concrete Works"),
    ("4.1.3", "Providing and laying cement concrete 1:2:4 (1 cement : 2 coarse sand : 4 graded stone aggregate 20 mm) PCC for flooring base / sills", "cum", 7710.00, "Concrete Works"),

    ("5.1.3", "Providing and laying in position specified grade of reinforced cement concrete M25 in foundations, footings, bases of columns, raft, excluding cost of centering, shuttering and reinforcement", "cum", 8640.00, "RCC Works"),
    ("5.3.1", "Providing and laying RCC M25 in columns, pillars, piers, abutments, posts and struts up to floor five level, excluding centering, shuttering and reinforcement", "cum", 10120.00, "RCC Works"),
    ("5.3.2", "Providing and laying RCC M25 in beams, suspended floors, roofs having slope up to 15 degrees, landings, balconies, shelves, chajjas, lintels, girders, bressumers and cantilevers, plinth beams", "cum", 9680.00, "RCC Works"),
    ("5.3.3", "Providing and laying RCC M25 in suspended slabs, roof slabs and landings up to floor five level, excluding centering and reinforcement", "cum", 9450.00, "RCC Works"),
    ("5.9.1", "Centering and shuttering including strutting, propping and removal of form for foundations, footings, bases of columns, mass concrete and plinth beams", "sqm", 312.60, "Formwork"),
    ("5.9.3", "Centering and shuttering including strutting, propping for suspended floors, roofs, landings, balconies and access platform (slab formwork)", "sqm", 798.30, "Formwork"),
    ("5.9.5", "Centering and shuttering including strutting, propping for lintels, beams, plinth beams, girders, bressumers and cantilevers", "sqm", 712.40, "Formwork"),
    ("5.9.6", "Centering and shuttering for columns, pillars, piers, abutments, posts and struts", "sqm", 834.20, "Formwork"),
    ("5.22.6", "Steel reinforcement for RCC work including straightening, cutting, bending, placing in position and binding all complete - Thermo-Mechanically Treated bars Fe 500D (TMT)", "kg", 92.80, "Reinforcement"),

    ("6.1.1", "Brick work with common burnt clay F.P.S. (non modular) bricks of class designation 7.5 in foundation and plinth in cement mortar 1:6 (1 cement : 6 coarse sand)", "cum", 7820.00, "Masonry"),
    ("6.4.1", "Brick work with common burnt clay bricks of class designation 7.5 in superstructure above plinth level up to floor V level in cement mortar 1:6, 230 mm thick external walls", "cum", 8310.00, "Masonry"),
    ("6.13.1", "Half brick masonry with common burnt clay bricks of class designation 7.5 in superstructure above plinth level, 115 mm thick partition walls in cement mortar 1:4", "sqm", 1012.00, "Masonry"),
    ("6.40", "AAC block masonry 200 mm thick with autoclaved aerated concrete blocks in cement mortar / adhesive", "cum", 6950.00, "Masonry"),

    ("11.41.2", "Providing and laying vitrified floor tiles 600x600 mm in different sizes (thickness 8 to 10 mm) with water absorption less than 0.08% conforming to IS 15622, laid on 20 mm thick cement mortar 1:4", "sqm", 1386.00, "Flooring"),
    ("11.46.2", "Providing and laying ceramic glazed floor tiles anti-skid 300x300 mm (thickness 7 mm) of 1st quality in toilets, bathrooms and wet areas on 20 mm cement mortar 1:4", "sqm", 1048.00, "Flooring"),
    ("11.37.1", "Providing and fixing 1st quality ceramic glazed wall tiles (dado) conforming to IS 15622 of approved make in all colours, shades, 6 mm thick on 12 mm cement plaster 1:3 in toilets and kitchen", "sqm", 1135.00, "Flooring"),
    ("11.26.1", "Kota stone slab flooring 20 to 25 mm thick over 20 mm thick base of cement mortar 1:4 laid and jointed with grey cement slurry, including rubbing and polishing", "sqm", 1210.00, "Flooring"),
    ("11.27.1", "Granite stone slab 18 mm thick in kitchen counter platform / treads of steps / risers, gang saw cut, mirror polished, laid over cement mortar", "sqm", 3420.00, "Flooring"),
    ("11.41.3", "Vitrified tile skirting 100 mm high matching floor tiles fixed with cement mortar 1:4 and grey cement slurry", "sqm", 1295.00, "Flooring"),

    ("13.4.1", "12 mm cement plaster of mix 1:6 (1 cement : 6 fine sand) on rough side of single or half brick wall - internal plaster", "sqm", 314.80, "Plastering"),
    ("13.1.1", "15 mm cement plaster on the rough side of single or half brick wall of mix 1:4 (1 cement : 4 fine sand) - external plaster", "sqm", 372.30, "Plastering"),
    ("13.16.1", "6 mm cement plaster of mix 1:3 (1 cement : 3 fine sand) to ceiling / underside of RCC slab", "sqm", 268.50, "Plastering"),

    ("13.61.1", "Wall painting with acrylic emulsion paint of approved brand, having VOC content less than 50 g/litre, two or more coats on new work over plaster (interior)", "sqm", 162.40, "Painting"),
    ("13.82.1", "Wall painting with premium acrylic smooth exterior weather proof paint of required shade, two or more coats on new work (exterior)", "sqm", 196.70, "Painting"),
    ("13.80", "Applying priming coat with ready mixed primer and two coats wall putty of approved make on interior plastered surfaces", "sqm", 118.20, "Painting"),
    ("13.43.1", "Painting with synthetic enamel paint of approved brand and shade on new wood / steel work, two or more coats (doors, frames, grills)", "sqm", 148.60, "Painting"),

    ("9.21.1", "Providing and fixing factory made flush door shutters, 35 mm thick, decorative type, core of block board construction, with frame of 1st class hard wood, including ISI marked hardware fittings", "sqm", 3640.00, "Doors & Windows"),
    ("9.1.1", "Providing wood work in frames of doors, windows, clerestory windows and other frames, wrought framed and fixed in position with hold fast lugs, hard wood (sal / teak equivalent) chowkhat", "cum", 128500.00, "Doors & Windows"),
    ("9.48.1", "Providing and fixing pressed steel door frames manufactured from commercial mild steel sheet of 1.25 mm thickness, profile of size 105x60 mm", "metre", 812.00, "Doors & Windows"),
    ("21.1.1", "Providing and fixing aluminium work for doors, windows, ventilators and partitions with extruded built-up standard tubular sections, anodised, including 5 mm glass glazing and EPDM gaskets (sliding windows)", "sqm", 6250.00, "Doors & Windows"),
    ("21.4", "Providing and fixing UPVC sliding windows with 5 mm toughened glass, multi-point locking, mosquito mesh shutter", "sqm", 7480.00, "Doors & Windows"),
    ("10.25.1", "Steel work welded in built up sections / framed work including cutting, hoisting, fixing in position and applying a priming coat - MS window grills and railings", "kg", 142.30, "Doors & Windows"),

    ("22.4.1", "Providing and laying integral cement based water proofing treatment including preparation of surface for roof terrace (brick bat coba with APP membrane)", "sqm", 1268.00, "Waterproofing"),
    ("22.9", "Providing and applying two coats of polymer modified cementitious waterproofing coating in toilets, bathrooms and wet areas (floor + 300 mm up walls)", "sqm", 486.00, "Waterproofing"),

    ("1.1.1", "Wiring for light point / fan point / exhaust fan point / call bell point with 1.5 sq. mm FRLS PVC insulated copper conductor single core cable in surface / recessed PVC conduit, with modular switch, modular plate, suitable GI box and earthing", "point", 1185.00, "Electrical"),
    ("1.11.1", "Wiring for 6A / 16A power socket outlet with 4 sq. mm FRLS PVC insulated copper conductor single core cable in recessed PVC conduit with modular socket and switch", "point", 1640.00, "Electrical"),
    ("1.32", "Supplying and fixing distribution board TPN 8-way double door with MCB / RCCB, including earthing station", "each", 18400.00, "Electrical"),

    ("17.1.1", "Providing and fixing water closet squatting pan / European type W.C. pan with flushing cistern, seat cover and all fittings complete (sanitary fixture)", "each", 9850.00, "Plumbing & Sanitary"),
    ("17.7.1", "Providing and fixing wash basin with C.I. / M.S. brackets, pillar taps, waste fittings and trap complete", "each", 6120.00, "Plumbing & Sanitary"),
    ("17.11", "Providing and fixing stainless steel kitchen sink with drain board, including waste coupling, trap and fittings", "each", 7340.00, "Plumbing & Sanitary"),
    ("18.7.1", "Providing and fixing CPVC pipes, having thermal stability for hot & cold water supply including all CPVC plain & brass threaded fittings, internal work 20 mm nominal bore", "metre", 486.00, "Plumbing & Sanitary"),
    ("19.7.1", "Providing, laying and jointing UPVC SWR soil, waste and rain water pipes 110 mm diameter with all fittings complete", "metre", 742.00, "Plumbing & Sanitary"),
    ("18.39", "Providing and fixing overhead PVC / polyethylene water storage tank, ISI marked, with cover and all connections (per litre capacity)", "litre", 11.40, "Plumbing & Sanitary"),
]

CATEGORY_ORDER = [
    "Earthwork", "Concrete Works", "RCC Works", "Formwork", "Reinforcement", "Masonry",
    "Plastering", "Flooring", "Painting", "Doors & Windows", "Waterproofing",
    "Electrical", "Plumbing & Sanitary", "Miscellaneous",
]


# Sample rate analyses (per CPWD analysis format: materials + labour + machinery, + water 1%, + contractor's
# profit & overheads 15%). Quantities are typical coefficients; material/labour rates are indicative.
SEED_ANALYSIS = {
    "6.4.1": dict(per=1, unit="cum", water_pct=1, overhead_pct=15, components=[
        dict(type="material", desc="Common burnt clay bricks (class 7.5)", unit="nos", qty=500, rate=8.5),
        dict(type="material", desc="Cement mortar 1:6 (cement)", unit="bag", qty=1.25, rate=380),
        dict(type="material", desc="Coarse sand", unit="cum", qty=0.25, rate=1900),
        dict(type="labour", desc="Mason (2nd class)", unit="day", qty=0.75, rate=950),
        dict(type="labour", desc="Beldar / mazdoor", unit="day", qty=1.8, rate=720),
        dict(type="labour", desc="Bhisti (curing)", unit="day", qty=0.3, rate=720),
        dict(type="machinery", desc="Scaffolding, sundries", unit="LS", qty=1, rate=240)]),
    "5.3.3": dict(per=1, unit="cum", water_pct=1, overhead_pct=15, components=[
        dict(type="material", desc="Cement OPC 43 grade (M25 design mix)", unit="bag", qty=8.0, rate=380),
        dict(type="material", desc="Coarse sand", unit="cum", qty=0.44, rate=1900),
        dict(type="material", desc="Stone aggregate 20 mm", unit="cum", qty=0.88, rate=1650),
        dict(type="material", desc="Admixture", unit="kg", qty=1.6, rate=95),
        dict(type="labour", desc="Mason", unit="day", qty=0.17, rate=950),
        dict(type="labour", desc="Beldar / mazdoor", unit="day", qty=1.9, rate=720),
        dict(type="machinery", desc="Concrete mixer & vibrator hire incl. fuel", unit="cum", qty=1, rate=420)]),
    "13.4.1": dict(per=10, unit="sqm", water_pct=1, overhead_pct=15, components=[
        dict(type="material", desc="Cement", unit="bag", qty=0.6, rate=380),
        dict(type="material", desc="Fine sand", unit="cum", qty=0.155, rate=1800),
        dict(type="labour", desc="Mason (2nd class)", unit="day", qty=1.0, rate=950),
        dict(type="labour", desc="Beldar / mazdoor", unit="day", qty=1.2, rate=720),
        dict(type="machinery", desc="Scaffolding, sundries", unit="LS", qty=1, rate=120)]),
}


def analysis_rate(a: dict) -> float:
    base = sum(float(c["qty"]) * float(c["rate"]) for c in a.get("components", []))
    return round(base * (1 + float(a.get("water_pct", 1)) / 100) * (1 + float(a.get("overhead_pct", 15)) / 100) / max(1e-9, float(a.get("per", 1))), 2)
