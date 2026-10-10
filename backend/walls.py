"""Wall quantities (Task 7) — length, surface area, masonry volume, plaster and paint areas are separate quantities.

  wall_length            Σ centre-line length (external = envelope perimeter − corners; internal = ½ × wall-blob outline)
  wall_face_area         length × height                                   (one face)
  masonry_volume         length × height × thickness − Σ(opening w × h × thickness)   (deductions listed)
  plaster_area_internal  internal walls: 2 faces; external walls: inner face only; − openings (each face once)
  plaster_area_external  external walls, outer face − openings
  paint_area_*           = the corresponding plaster area (finish follows plaster)

Each value carries its formula, inputs and a status: MEASURED (all inputs from the drawing), ASSUMED (an input is a default
— e.g. wall height not shown on any section) or UNRESOLVED (an input is missing).
"""
from __future__ import annotations


def _status(*srcs):
    if any(s == "missing" for s in srcs):
        return "UNRESOLVED"
    if any(s in ("default", "assumed") for s in srcs):
        return "ASSUMED"
    return "MEASURED"


def compute(sheet: dict, params: dict, src: dict | None = None) -> dict:
    m = sheet.get("metrics") or {}
    src = src or {}
    H = params.get("floor_height")
    h_src = "drawing" if src.get("floor_height") not in (None, "default") else "default"
    slab = params.get("slab_thickness") or 0
    clear_h = (H - slab) if H else None
    L_ext, L_int = m.get("L_ext"), m.get("L_int")
    t_ext, t_int = m.get("t_ext"), m.get("t_int")
    len_src = "drawing" if L_ext is not None else "missing"
    t_src = "drawing" if t_ext else "missing"
    ops = sheet.get("openings") or []
    ext_ops = [o for o in ops if o.get("ext")]
    int_ops = [o for o in ops if not o.get("ext")]
    op_area = lambda L: sum(o["w"] * o.get("h", 2.1) for o in L)
    out = dict(height=dict(value=clear_h, source=f"floor height {H} m − slab {slab} m" if H else None, status=_status(h_src)))
    out["wall_length_external"] = dict(value=round(L_ext, 2) if L_ext is not None else None, unit="m", formula="envelope perimeter − 4 × t_ext",
                                       status=_status(len_src))
    out["wall_length_internal"] = dict(value=round(L_int, 2) if L_int is not None else None, unit="m", formula="½ × internal wall-blob outlines + door gaps",
                                       status=_status(len_src))
    if clear_h and L_ext is not None:
        out["wall_face_area_external"] = dict(value=round(L_ext * clear_h, 2), unit="sqm", formula=f"{L_ext:.2f} × {clear_h:.2f}", status=_status(len_src, h_src))
        out["wall_face_area_internal"] = dict(value=round((L_int or 0) * clear_h, 2), unit="sqm", formula=f"{(L_int or 0):.2f} × {clear_h:.2f}", status=_status(len_src, h_src))
    if clear_h and L_ext is not None and t_ext:
        de = round(op_area(ext_ops) * t_ext, 3)
        di = round(op_area(int_ops) * (t_int or t_ext), 3)
        out["masonry_volume_external"] = dict(value=round(L_ext * clear_h * t_ext - de, 3), unit="cum",
                                              formula=f"{L_ext:.2f} × {clear_h:.2f} × {t_ext:.3f} − {de}", deductions=dict(openings=len(ext_ops), volume=de),
                                              status=_status(len_src, h_src, t_src))
        out["masonry_volume_internal"] = dict(value=round((L_int or 0) * clear_h * (t_int or t_ext) - di, 3), unit="cum",
                                              formula=f"{(L_int or 0):.2f} × {clear_h:.2f} × {(t_int or t_ext):.3f} − {di}", deductions=dict(openings=len(int_ops), volume=di),
                                              status=_status(len_src, h_src, t_src))
    else:
        out["masonry_volume_external"] = dict(value=None, unit="cum", status="UNRESOLVED",
                                              reason="wall thickness or height not available" if not t_ext else "wall length not available")
    if clear_h and L_ext is not None:
        pi = (L_int or 0) * clear_h * 2 + L_ext * clear_h - 2 * op_area(int_ops) - op_area(ext_ops)
        pe = L_ext * clear_h - op_area(ext_ops)
        out["plaster_area_internal"] = dict(value=round(pi, 2), unit="sqm", sides="internal walls both faces + inner face of external walls",
                                            formula="2·L_int·h + L_ext·h − 2·Σ internal openings − Σ external openings", status=_status(len_src, h_src))
        out["plaster_area_external"] = dict(value=round(pe, 2), unit="sqm", sides="outer face of external walls",
                                            formula="L_ext·h − Σ external openings", status=_status(len_src, h_src))
        out["paint_area_internal"] = dict(out["plaster_area_internal"], formula="= plaster area internal")
        out["paint_area_external"] = dict(out["plaster_area_external"], formula="= plaster area external")
    return out
