"""Area definitions and measurement evidence (Task 5). The six areas are never interchangeable:

  room_usable_area   area of one room inside its finished walls
  carpet_area        Σ room usable areas of private (non-common) rooms — walls, shafts, lifts, stairs excluded
  common_area        Σ room usable areas of common spaces (corridor, lobby, refuge, stairs, lift, shaft, services)
  plinth_area        covered area of the building footprint at plinth level, INCLUDING walls (outer envelope)
  built_up_area      plinth area of one floor (covered area incl. walls) — per floor
  gross_floor_area   Σ built-up areas over all floors the plans stand for (floor occurrences / storeys)

Measurement evidence hierarchy (best first): explicit dimensions → CAD/vector geometry → calibrated pixel geometry (known
dimension / verified scale) → polygon with a known calibration basis → UNRESOLVED (no reliable calibration).
An assumed scale (e.g. wall thickness assumed 230 mm) is never presented as a measurement: those areas are 'NEEDS REVIEW'.
"""
from __future__ import annotations

COMMON = {"corridor", "lobby", "refuge", "shaft", "electrical", "staircase", "lift", "common", "service"}


def calibration(sheet: dict) -> dict:
    sc = sheet.get("scale") or {}
    m = str(sc.get("method") or "")
    src = str(sheet.get("source") or sheet.get("method") or "")
    if m.startswith("derived floor:"):
        basis, status, unc = m, "NEEDS REVIEW", 0.15
    elif m.startswith("calibrated from user-entered built-up area"):  # scale guard (checked first: the re-run says 'user calibration')
        basis, status, unc = f"scaled to the built-up area entered by the user ({m.split(' — ')[0]})", "USER-CONFIRMED", 0.10
    elif m.startswith("auto: typical room sizes"):
        basis, status, unc = f"ESTIMATED scale from typical room sizes ({m.split(' — ')[0]}) — calibrate to confirm", "NEEDS REVIEW", 0.30
    elif "dxf" in src.lower() or "cad" in m.lower() or "vector" in m.lower() or "units" in m.lower() or sheet.get("source") == "vector":
        basis, status, unc = "CAD / vector geometry (drawing units)", "MEASURED", 0.02
    elif "user calibration" in m or "calibrated by user" in m:  # app.update_sheet writes "calibrated by user — …"
        basis, status, unc = "user calibration (known dimension)", "MEASURED", 0.03
    elif "room dimension labels" in m or "overall dimensions" in m or "plinth area note" in m:
        basis, status, unc = f"calibrated from written dimensions ({m})", "MEASURED", 0.05
    elif "scale" in m.lower() and ("1:" in m or "scale_den" in sc):
        basis, status, unc = f"printed scale ({m})", "MEASURED", 0.04
    elif "fallback" in m:
        basis, status, unc = f"no reliable calibration ({m})", "UNRESOLVED", None
    elif m.startswith("auto"):
        basis, status, unc = f"ASSUMED scale ({m})", "NEEDS REVIEW", 0.25
    elif not m and src.lower() not in ("image", "raster", "photo"):
        basis, status, unc = "vector geometry (drawing units)", "MEASURED", 0.02
    elif not m:
        basis, status, unc = "raster sheet without a recorded scale method", "NEEDS REVIEW", 0.25
    else:
        basis, status, unc = m, "NEEDS REVIEW", 0.15
    if status != "MEASURED" and sheet.get("scale_confirmed"):  # the user accepted the automatic scale: still not measured
        basis, status, unc = f"USER-CONFIRMED assumed scale ({m or 'no method recorded'}) — not measured", "USER-CONFIRMED", unc or 0.25
    return dict(basis=basis, status=status, relative_uncertainty=unc, method=m or None)


def compute(sheet: dict, storeys: int | None = None) -> dict:
    rooms = sheet.get("rooms") or []
    m = sheet.get("metrics") or {}
    cal = calibration(sheet)
    occ = (sheet.get("floor_info") or {}).get("floor_occurrences") or []
    n = len(occ) or storeys
    st = cal["status"]
    room_rows = []
    for r in rooms:
        explicit = r.get("area_basis") == "explicit dimensions"
        room_rows.append(dict(id=r.get("id"), name=r.get("name"), room_type=r.get("room_type") or r.get("type"), area_m2=r.get("area"),
                              method="explicit written dimensions" if explicit else "polygon × calibration",
                              formula=(f"{r['label_dims'][0]} × {r['label_dims'][1]}" if explicit and r.get("label_dims") else "polygon area"),
                              status="MEASURED" if explicit else st, polygon_area_m2=r.get("polygon_area", r.get("area"))))
    private = [x for x in room_rows if x["room_type"] not in COMMON]
    common = [x for x in room_rows if x["room_type"] in COMMON]
    plinth = m.get("plinth_area")
    out = dict(
        calibration=cal,
        room_usable_area=room_rows,
        carpet_area=dict(value_m2=round(sum(x["area_m2"] or 0 for x in private), 2), definition="Σ usable area of private rooms (excl. walls, common areas)",
                         formula=f"Σ {len(private)} private rooms", status=st if not all(x["status"] == "MEASURED" for x in private) or st != "MEASURED" else "MEASURED",
                         uncertainty=cal["relative_uncertainty"]),
        common_area=dict(value_m2=round(sum(x["area_m2"] or 0 for x in common), 2), definition="Σ usable area of corridors, lobbies, stairs, lifts, shafts, refuge, services",
                         formula=f"Σ {len(common)} common spaces", status=st, uncertainty=cal["relative_uncertainty"]),
        plinth_area=dict(value_m2=plinth, definition="covered footprint at plinth level incl. walls (outer envelope)", formula="envelope polygon area",
                         status=st if plinth else "UNRESOLVED", uncertainty=cal["relative_uncertainty"]),
        built_up_area=dict(value_m2=plinth, definition="covered area of ONE floor incl. walls", formula="= plinth / floor envelope of this plan",
                           status=st if plinth else "UNRESOLVED", uncertainty=cal["relative_uncertainty"]),
        gross_floor_area=dict(value_m2=round(plinth * n, 2) if plinth and n else None,
                              definition="Σ built-up area over the floors this plan stands for",
                              formula=f"built-up × {n} floor(s) ({'occurrences ' + str(occ) if occ else 'storeys parameter'})" if n else "storey count required",
                              status=(st if plinth and n else "UNRESOLVED"),
                              note=None if n else "STOREY COUNT REQUIRED — the sheet does not state how many floors it applies to"),
    )
    if st == "UNRESOLVED":
        for k in ("carpet_area", "common_area", "plinth_area", "built_up_area", "gross_floor_area"):
            out[k]["reason"] = "scale could not be established reliably — calibrate with a known dimension"
    return out
