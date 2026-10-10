"""Excel and printable HTML estimation reports with drawing → quantity → rate → cost traceability."""
from __future__ import annotations

import brand
import html
import io
import re
from datetime import datetime


def inr(x):
    if x is None:
        return "—"
    x = float(x)
    neg = x < 0
    x = abs(x)
    s = f"{x:,.2f}"
    whole, dec = s.split(".")
    whole = whole.replace(",", "")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + whole + "." + dec


def rate_source_lines(full: dict) -> list[tuple[str, str]]:
    """Where every rate comes from: location -> authority -> schedule -> year / revision -> source."""
    rs = full.get("rate_source") or {}
    s = rs.get("schedule") or {}
    sel = rs.get("selection") or {}
    scope_line = ("Estimation scope", full.get("scope_text") or "Entire property")
    if not s:
        return [scope_line, ("Project location", rs.get("location_text") or full.get("location") or "Not specified"),
                ("Rate schedule", "NONE — " + (rs.get("message") or "No official rate schedule is configured for this jurisdiction."))]
    out = [scope_line, ("Project location", rs.get("location_text") or full.get("location") or "Not specified"),
           ("Rate authority", s.get("authority") + (f" — {s['department']}" if s.get("department") else "")),
           ("Rate schedule", s.get("name")),
           ("Jurisdiction of the schedule", s.get("scope") or ""),
           ("Year / financial year", " / ".join(x for x in (s.get("year"), s.get("financial_year")) if x) or "not recorded"),
           ("Revision", s.get("revision") or "—"),
           ("Effective", (s.get("effective_from") or "not recorded") + (f" to {s['effective_to']}" if s.get("effective_to") else "")),
           ("Source", (s.get("source") or "") + (f": {s['source_ref']}" if s.get("source_ref") else "")),
           ("How it was selected", f"{sel.get('mode', '')} — {sel.get('reason', '')}")]
    p = full.get("params") or {}
    adj = []
    if float(p.get("cost_index", 1) or 1) != 1:
        adj.append(f"cost index ×{p['cost_index']} (set by the user)")
    if p.get("finish", "standard") != "standard":
        adj.append(f"finish '{p['finish']}' adjustment on flooring, painting, doors & windows (set by the user)")
    out.append(("Adjustments to schedule rates", "; ".join(adj) if adj else "none — schedule rates applied as published"))
    return out


def build_xlsx(full: dict) -> bytes:
    full = brand.debrand(full)
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    navy = PatternFill("solid", fgColor="0F1B3D")
    soft = PatternFill("solid", fgColor="EEF2FF")
    amber = PatternFill("solid", fgColor="FFF4D6")
    white_b = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D0D5E2")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    est = full["estimate"]

    ws = wb.active
    ws.title = "Abstract"
    ws["A1"] = "ABSTRACT OF COST — " + full["name"]
    ws["A1"].font = Font(size=15, bold=True, color="0F1B3D")
    ws["A2"] = f"Client: {full.get('client') or '-'}   Generated: {datetime.now():%d %b %Y %H:%M}"
    p = full["params"]
    ws["A3"] = f"Floors: {p['floors']}  ·  Floor height: {p['floor_height']} m  ·  Finish: {p['finish']}  ·  Cost index: {p['cost_index']}"
    ws.append([])
    ws.append(["", "RATE SOURCE"])
    ws.cell(ws.max_row, 2).font = Font(bold=True)
    for k, v in rate_source_lines(full):
        ws.append(["", k, v])
    ws.append([])
    hdr_row = ws.max_row + 1
    ws.append(["#", "Category", "Amount (₹)", "Share %"])
    for c in ws[hdr_row]:
        c.fill, c.font = navy, white_b
    for i, c in enumerate(est["categories"], 1):
        ws.append([i, c["name"], round(c["amount"], 2), round(c["amount"] / max(1, est["subtotal"]) * 100, 2)])
    r0 = ws.max_row + 1
    for label, val in [("Sub-total (works)", est["subtotal"]), (f"Contingencies @ {p['contingency']}%", est["contingency"]),
                       (f"Labour welfare cess @ {p['cess']}%", est["cess"]), (f"GST @ {p['gst']}%", est["gst"]),
                       ("1. CONSTRUCTION COST (excl. land)", est["total"])] \
                      + ([("Land cost (" + (full["land"].get("basis") or "user rate") + ")", full["land"]["land_cost"]),
                          ("Stamp duty + registration", full["land"]["stamp_duty_registration"]),
                          ("2. CONSTRUCTION + LAND", full["land"]["total_with_land"])] if (full.get("land") or {}).get("provided") else []):
        ws.append(["", label, round(val, 2), ""])
    for row in ws.iter_rows(min_row=r0, max_row=ws.max_row):
        row[1].font = Font(bold=True)
    ws.cell(ws.max_row, 2).fill = amber
    ws.cell(ws.max_row, 3).fill = amber
    sm = full["summary"]
    ws.append([])
    ws.append(["", "Built-up area (m²)", sm["built_up_area"]])
    ws.append(["", "Cost per sq ft of built-up area (₹)", sm.get("cost_per_sqft")])
    for col, w in zip("ABCD", (6, 52, 22, 12)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=hdr_row + 1, max_row=ws.max_row):
        row[2].number_format = '#,##0.00'

    ws2 = wb.create_sheet("Detailed BOQ")
    hdr = ["S.No", "Category", "Item description (take-off)", "PWD SOR code", "SOR description", "Qty", "Unit",
           "Rate (₹)", "Amount (₹)", "Rate schedule", "Authority", "Year / revision", "Rate type", "Measurement basis", "Basis class", "Drawing reference", "Drawing elements", "Map confidence", "Status", "Note",
           "In total", "Quantity status", "Rate source", "Exclusion reason"]
    ws2.append(hdr)
    for c in ws2[1]:
        c.fill, c.font = navy, white_b
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for it in est["items"]:
        ws2.append([it["sno"], it["category"], it["description"], it.get("sor_code") or "—", (it.get("sor_desc") or "")[:300],
                    it["qty"], it["unit"], it.get("rate"), it["amount"], it.get("rate_schedule") or "— NEEDS RATE (not in total)", it.get("rate_authority"),
                    it.get("rate_year"), it.get("rate_kind"), (it.get("formula") or "") + " | basis: " + str(it.get("basis") or ""), it.get("basis_class"),
                    "; ".join(it.get("drawing_refs") or []),
                    trace_text(it, full["sheets"])[:600], it.get("map_score"), it.get("status"), it.get("note", ""),
                    "yes" if it.get("in_scope", True) else "NO", it.get("qty_status"), it.get("rate_status"), ((it.get("exclusion") or {}).get("reason") or "")])
        if it.get("status") in ("review", "unmapped"):
            for c in ws2[ws2.max_row]:
                c.fill = amber
    ws2.append(["", "", "SUB-TOTAL", "", "", "", "", "", est["subtotal"]])
    for c in ws2[ws2.max_row]:
        c.font = Font(bold=True)
        c.fill = soft
    widths = [6, 16, 48, 11, 48, 11, 7, 12, 15, 30, 20, 14, 16, 46, 12, 30, 30, 10, 10, 20]
    for i, w in enumerate(widths, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    for row in ws2.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = box
        row[7].number_format = row[8].number_format = '#,##0.00'
    ws2.freeze_panes = "D2"

    ws3 = wb.create_sheet("Measurements")
    ws3.append(["Drawing", "Sheet", "Room ID", "Room", "Type", "Type confidence", "Area (m²)", "Perimeter (m)", "Touches exterior"])
    for c in ws3[1]:
        c.fill, c.font = navy, white_b
    for s in full["sheets"]:
        for r in s.get("rooms", []):
            ws3.append([s["file"], s.get("sheet"), r["id"], r["name"], r["type"], r["type_conf"], r["area"], r["perimeter"], "yes" if r["touches_ext"] else "no"])
    ws3.append([])
    ws3.append(["Drawing", "Sheet", "Plinth area", "Envelope perimeter", "Ext wall L", "Int wall L", "t ext", "t int", "Doors", "Windows", "Scale method"])
    for c in ws3[ws3.max_row]:
        c.fill, c.font = navy, white_b
    for s in full["sheets"]:
        m = s.get("metrics") or {}
        if m:
            ws3.append([s["file"], s.get("sheet"), m["plinth_area"], m["envelope_perimeter"], m["L_ext"], m["L_int"], m["t_ext"], m["t_int"],
                        m["n_doors"], m["n_windows"], (s.get("scale") or {}).get("method")])
    for i, w in enumerate([22, 10, 10, 22, 14, 14, 12, 14, 14, 10, 50], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    ws4 = wb.create_sheet("Openings")
    ws4.append(["Drawing", "ID", "Kind", "Width (m)", "Height (m)", "External", "X (m)", "Y (m)"])
    for c in ws4[1]:
        c.fill, c.font = navy, white_b
    for s in full["sheets"]:
        for o in s.get("openings", []):
            ws4.append([s["file"], o["id"], o["kind"], o["w"], o.get("h"), "yes" if o.get("ext") else "no", o["x"], o["y"]])

    ex = est.get("excluded") or []
    ws5 = wb.create_sheet("Not in total")
    ws5.append(["Item", "Qty", "Unit", "Category", "Reason"])
    for c in ws5[1]:
        c.fill, c.font = navy, white_b
    for x_ in ex:
        ws5.append([x_["description"], x_["qty"], x_["unit"], x_["category"], x_["reason"]])
    for x_ in est.get("out_of_scope") or []:
        ws5.append([x_["description"], x_["qty"], x_["unit"], x_["category"], "outside the selected estimation scope: " + (full.get("scope_text") or "")])
    for x_ in full.get("other_elements") or []:
        ws5.append([x_["element"] + " (identified, not quantified)", None, None, "Other elements", "; ".join(x_["sheets"])])
    for i, w in enumerate([60, 12, 8, 18, 80], 1):
        ws5.column_dimensions[get_column_letter(i)].width = w

    for title, rows, head in (("Assumptions", full.get("assumptions") or [], ["assumption_id", "description", "value", "unit", "classification", "reason", "impact_on_cost"]),
                              ("Checks", full.get("checks") or [], ["level", "code", "message"])):
        ws_ = wb.create_sheet(title)
        ws_.append([h.replace("_", " ").title() for h in head])
        for c in ws_[1]:
            c.fill, c.font = navy, white_b
        for r_ in rows:
            ws_.append([r_.get(h) if not isinstance(r_.get(h), (list, dict)) else str(r_.get(h)) for h in head])
    comp = (full.get("stats") or {}).get("completeness") or {}
    ws.append([])
    ws.append(["Price completeness", comp.get("text"), "unresolved items are NOT in the total"])

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()




# ----------------------------------------------------------------------------- traceability
def _sheet_name(s):
    fl = (s.get("floor") or {}).get("label")
    return f"{s.get('file', '')} {s.get('sheet', '')}".strip() + (f" ({fl})" if fl else "")


def trace_text(it: dict, sheets: list) -> str:
    """Readable list of the drawing elements a BOQ line was measured from."""
    src = set(it.get("sources") or [])
    if not src:
        return "; ".join(it.get("drawing_refs") or [])
    parts = []
    for s in sheets:
        rooms = [r["name"] for r in s.get("rooms", []) if r["id"] in src]
        ops = {}
        for o in s.get("openings", []):
            if o["id"] in src:
                k = o.get("tag") or o["kind"]
                ops[k] = ops.get(k, 0) + 1
        we = sum(1 for w in s.get("walls", []) if w["id"] in src and w.get("ext"))
        wi = sum(1 for w in s.get("walls", []) if w["id"] in src and not w.get("ext"))
        cols = sum(1 for c in s.get("columns", []) if c["id"] in src)
        bits = []
        if rooms:
            bits.append("rooms " + ", ".join(rooms))
        if ops:
            bits.append("openings " + ", ".join(f"{k}×{v}" for k, v in sorted(ops.items())))
        if we or wi:
            bits.append(f"{we} external + {wi} internal wall segments" if we and wi else (f"{we} external wall segments" if we else f"{wi} internal wall segments"))
        if cols:
            bits.append(f"{cols} columns")
        if bits:
            parts.append(f"{_sheet_name(s)}: " + "; ".join(bits))
    marks = sorted(x for x in src if re.fullmatch(r"(F|C|PB|GB|RB|B|S)\d{1,2}[A-Z]?", x))
    if marks:
        parts.append("structural marks " + ", ".join(marks))
    if "envelope" in src:
        parts.append("building outline")
    return " | ".join(parts) or "; ".join(it.get("drawing_refs") or [])


# ----------------------------------------------------------------------------- HTML report
def _report_body(full: dict, for_pdf=False) -> str:
    e = html.escape
    est, p, sm = full["estimate"], full["params"], full["summary"]
    rows, cur = [], None
    for it in est["items"]:
        if not it.get("in_scope", True):
            continue  # excluded / unresolved lines are listed in their own sections, never inside the counted categories
        if it["category"] != cur:
            cur = it["category"]
            amt = next((c["amount"] for c in est["categories"] if c["name"] == cur), 0)
            rows.append(f'<tr class="cat"><td colspan="5">{e(cur)}</td><td class="num">{inr(amt)}</td></tr>')
        flag = ' class="flag"' if it.get("status") in ("review", "unmapped") else ""
        rows.append(f"""<tr{flag}><td>{it['sno']}</td><td><b>{e(it['description'])}</b>
            <div class="sub">PWD/SOR {e(it.get('sor_code') or '— NEEDS RATE (not in total)')} {e((it.get('sor_desc') or '')[:110])}{(' · ' + e(it['rate_schedule'])) if it.get('rate_schedule') else ''}{(' · ' + e(it.get('rate_authority') or '') + ' ' + e(it.get('rate_year') or '') + ' · ' + e(it.get('rate_kind') or '')) if it.get('rate_schedule') else ''}{(' · map ' + str(round((it.get('map_score') or 0) * 100)) + '%') if it.get('rate_schedule') else ''}</div>
            <div class="sub">Quantity: <b>{e(it.get('qty_status') or '')}</b> · Rate: <b>{e(it.get('rate_status') or '')}</b> · Basis: {e(it.get('basis') or 'drawing')} ({e(it.get('basis_class') or '')})</div>
            <div class="trace">Measured: {e(it.get('formula') or '')}<br>From: {e(trace_text(it, full['sheets']))}</div></td>
            <td class="num">{it['qty']:,.2f}</td><td>{e(it['unit'])}</td><td class="num">{inr(it.get('rate'))}</td><td class="num">{inr(it['amount'])}</td></tr>""")
    cats = "".join(f"<tr><td>{i}</td><td>{e(c['name'])}</td><td class='num'>{inr(c['amount'])}</td><td class='num'>{c['amount'] / max(1, est['subtotal']) * 100:.1f}%</td></tr>"
                   for i, c in enumerate(est["categories"], 1))
    sheets = "".join(f"<tr><td>{e(s['file'])}</td><td>{e(s.get('sheet', ''))}</td><td>{e(KIND.get(s.get('kind'), s.get('kind', '')))}</td>"
                     f"<td>{e((s.get('floor') or {}).get('label') or '—')}</td><td>{len(s.get('rooms', []))}</td><td>{'yes' if s.get('enabled', True) else 'no'}</td></tr>" for s in full["sheets"])
    src = p.get("_src", {})
    prm = "".join(f"<tr><td>{e(lbl)}</td><td class='num'>{p.get(k)}</td><td>{e(src.get(k, 'default'))}</td></tr>" for k, lbl in PARAMS)
    ver = full.get("versions") or []
    vtxt = "".join(f"<tr><td>R{v['no']}</td><td>{e(v['t'].replace('T', ' '))}</td><td>{e(v['by'])}</td><td class='num'>{inr(v['total'])}</td></tr>" for v in ver)
    status = full.get("status", "draft")
    rsrc = "".join(f"<tr><td style='width:200px;color:#62677a'>{e(k)}</td><td>{e(v or '')}</td></tr>" for k, v in rate_source_lines(full))
    return f"""<div class="hero"><div><div class="meta">DETAILED ESTIMATE · PWD SCHEDULE OF RATES</div><h1>{e(full['name'])}</h1>
<div class="meta">Generated {datetime.now():%d %b %Y, %H:%M} · Status: <b>{e(status.replace('_', ' ').upper())}</b>{f" · Revision R{ver[-1]['no']} confirmed by {e(ver[-1]['by'])}" if ver and status == 'confirmed' else ''}</div></div>
<div class="total"><div class="l">1 · Construction cost (excl. land)</div><div class="v">{inr(est['total'])}</div>{_land_line(full)}<div class="meta">Built-up {sm['built_up_area']} m² · ₹{sm.get('cost_per_sqft') or 0:,}/sq ft</div></div></div>
<h2>Rate source</h2><table>{rsrc}</table>
<h2>1. Drawings used</h2><table><tr><th>File</th><th>Sheet</th><th>Type</th><th>Floor</th><th>Rooms</th><th>Used</th></tr>{sheets}</table>
<h2>2. Parameters and where they came from</h2><table><tr><th>Parameter</th><th class="num">Value</th><th>Source</th></tr>{prm}</table>
<h2>3. Abstract of cost</h2><table><tr><th>#</th><th>Category</th><th class="num">Amount</th><th class="num">Share</th></tr>{cats}
<tr class="sum"><td></td><td>Sub-total (works)</td><td class="num">{inr(est['subtotal'])}</td><td></td></tr>
<tr><td></td><td>Contingencies @ {p['contingency']}%</td><td class="num">{inr(est['contingency'])}</td><td></td></tr>
<tr><td></td><td>Labour welfare cess @ {p['cess']}%</td><td class="num">{inr(est['cess'])}</td><td></td></tr>
<tr><td></td><td>GST @ {p['gst']}%</td><td class="num">{inr(est['gst'])}</td><td></td></tr>
<tr class="grand"><td></td><td>1. CONSTRUCTION COST (excl. land)</td><td class="num">{inr(est['total'])}</td><td></td></tr></table>
{_quality(full)}{_gaps(full)}
<h2>4. Detailed estimate with traceability</h2><table><tr><th>#</th><th>Item · PWD item · measurement · drawing elements</th><th class="num">Qty</th><th>Unit</th><th class="num">PWD rate</th><th class="num">Cost</th></tr>{''.join(rows)}</table>
{f'<h2>5. Revisions</h2><table><tr><th>Rev</th><th>Confirmed</th><th>By</th><th class="num">Total</th></tr>{vtxt}</table>' if ver else ''}
<p class="meta" style="margin-top:16px">Rates are taken only from the rate schedule shown under "Rate source"{f" × user-set cost index {p['cost_index']}" if float(p.get('cost_index', 1) or 1) != 1 else ""}. Quantities come from the drawings and do not depend on the location. Highlighted rows need estimator review.</p>
<table class="sign"><tr><td>Prepared by</td><td>Checked by</td><td>Approved by</td></tr></table>"""


def _m2(v):
    return "—" if v is None else f"{v:,.2f} m²"


def _inr(v):
    return "" if v is None else f"{v:,.0f}"


def _quality(full):
    e = html.escape
    st = full.get("stats") or {}
    ss = st.get("status_summary") or {}
    out = "<h2>Estimate status</h2>"
    if ss:
        out += f"<p><b>{e(ss.get('status', ''))}</b> — {e(ss.get('headline', '').replace('PRELIMINARY estimate — ', ''))}</p>"
        out += ("<table><tr><th>Quantity status</th><th class='num'>Lines</th><th class='num'>Amount (₹)</th><th>Meaning</th></tr>"
                + "".join(f"<tr><td>{e(k)}</td><td class='num'>{v['lines']}</td><td class='num'>{_inr(v['amount'])}</td><td>{e(v['meaning'])}</td></tr>"
                          for k, v in ss["quantity"].items() if v["lines"]) + "</table>")
        out += ("<table><tr><th>Rate source (lines in the total)</th><th class='num'>Lines</th><th class='num'>Amount (₹)</th><th>Meaning</th></tr>"
                + "".join(f"<tr><td>{e(k)}</td><td class='num'>{v['lines']}</td><td class='num'>{_inr(v['amount'])}</td><td>{e(v['meaning'])}</td></tr>"
                          for k, v in ss["rate"].items() if v["lines"]) + "</table>")
        out += f"<p class='meta'>{e(ss.get('note', ''))} Lines with a verified quantity: {ss.get('verified_quantity_lines')} of {ss.get('lines_counted')} counted lines (₹{_inr(ss.get('verified_quantity_amount'))}).</p>"
        if ss.get("identified_not_quantified"):
            out += "<p><b>Identified in the drawings but NOT quantified (not in the total):</b> " + e(", ".join(ss["identified_not_quantified"])) + "</p>"
        out += "<p class='meta'><b>Not covered by the automatic take-off</b> (add as items if part of the work): " + e(", ".join(ss.get("not_covered_by_takeoff", []))) + "</p>"
    fl = [f for f in st.get("floors_info") or [] if f]
    if fl:
        out += "<p><b>Floors:</b> " + "; ".join(e(f.get("label") or "") + f" (from '{e(f.get('source_text') or '')}', confidence {f.get('confidence')})" for f in fl) + "</p>"
    units = st.get("units") or []
    if units:
        out += "<p><b>Units:</b> " + "; ".join(e(f"{u['id']} {u.get('label') or ''} — {u.get('bedrooms')} bed, {u.get('measured_area_m2')} m²") for u in units) + "</p>"
    ec = st.get("estimate_confidence") or {}
    if ec:
        out += (f"<p><b>Estimate confidence: {e(ec.get('label', ''))}</b> — " + "; ".join(e(r) for r in ec.get("reasons", [])) +
                f"<br><span class='meta'>{e(ec.get('calibration', ''))}</span></p>")
    sq = full.get("structural") or {}
    if sq:
        out += f"<p><b>Structural:</b> {e(sq.get('status', ''))}" + "".join(f"<br>• {e(m)}" for m in sq.get("missing", [])) + "</p>"
    for s_ in full.get("sheets") or []:
        A_ = s_.get("areas")
        if A_ and s_.get("kind") == "floor_plan":
            out += (f"<p><b>Areas — {e(s_.get('file') or '')}</b> (scale basis: {e(A_['calibration']['basis'])}; {e(A_['calibration']['status'])})<br>"
                    + "<br>".join(f"{e(k.replace('_', ' '))}: {_m2(A_[k].get('value_m2'))} "
                                  f"<span class='meta'>({e(A_[k]['definition'])}; {e(A_[k].get('status', ''))})</span>"
                                  for k in ("carpet_area", "common_area", "plinth_area", "built_up_area", "gross_floor_area")) + "</p>")
    ch = full.get("checks") or []
    if ch:
        out += ("<table><tr><th>Level</th><th>Check</th><th>Detail</th></tr>" + "".join(
            f"<tr><td>{e(c['level'])}</td><td>{e(c['code'])}</td><td>{e(c['message'][:220])}</td></tr>" for c in ch) + "</table>")
    asm = full.get("assumptions") or []
    if asm:
        out += ("<h2>Assumptions &amp; missing inputs</h2><table><tr><th>ID</th><th>Assumption</th><th>Value</th><th>Class</th><th class='num'>Cost affected (₹)</th></tr>"
                + "".join(f"<tr><td>{e(a['assumption_id'])}</td><td>{e(a['description'])}</td><td>{e(str(a.get('value') if a.get('value') is not None else '—'))} {e(a.get('unit') or '')}</td>"
                          f"<td>{e(a['classification'])}</td><td class='num'>{_inr(a.get('impact_on_cost'))}</td></tr>" for a in asm)
                + "</table>")
    return out


def _gaps(full):
    e = html.escape
    ex = (full.get("estimate") or {}).get("excluded") or []
    ot = full.get("other_elements") or []
    out = ""
    if ex:
        out += ("<h2>Items NOT included in the construction cost</h2><p class='meta'>These lines have a quantity but no usable rate in the "
                "selected schedule (or a suggested rate awaiting confirmation). The total above is therefore INCOMPLETE by these items.</p>"
                "<table><tr><th>Item</th><th class='num'>Qty</th><th>Unit</th><th>Reason</th></tr>"
                + "".join(f"<tr><td>{e(x['description'][:90])}</td><td class='num'>{x['qty']:,.2f}</td><td>{e(x['unit'])}</td><td>{e(x['reason'][:140])}</td></tr>" for x in ex)
                + "</table>")
    os_ = (full.get("estimate") or {}).get("out_of_scope") or []
    out = (f"<p class='meta'><b>Estimation scope:</b> {e(full.get('scope_text') or 'Entire property')}"
           + (" — PARTIAL estimate: lines outside this scope are listed below and are NOT in the total." if os_ else "") + "</p>") + out
    if os_:
        out += ("<h2>Measured but outside the selected scope (NOT in the total)</h2><table><tr><th>Item</th><th class='num'>Qty</th><th>Unit</th><th>Why excluded</th></tr>"
                + "".join(f"<tr><td>{e(x['description'][:90])}</td><td class='num'>{x['qty']:,.2f}</td><td>{e(x['unit'])}</td><td>{e(x.get('reason') or x['category'])}</td></tr>" for x in os_)
                + "</table>")
    un = (full.get("estimate") or {}).get("unresolved") or []
    if un:
        out += ("<h2>Unresolved quantities (NOT in the total)</h2><table><tr><th>Item</th><th>Category</th><th>Why</th></tr>"
                + "".join(f"<tr><td>{e(x['description'][:90])}</td><td>{e(x['category'])}</td><td>{e(x['reason'][:200])}</td></tr>" for x in un) + "</table>")
    es = (full.get("estimate") or {}).get("estimated") or []
    if es:
        out += ("<h2>Items priced at estimated average rates</h2><p class='meta'>No schedule rate is available for these items; an "
                "average rate was applied and can be edited.</p><table><tr><th>Item</th><th>Unit</th><th class='num'>Rate (₹)</th><th>Basis</th></tr>"
                + "".join(f"<tr><td>{e(x['description'][:90])}</td><td>{e(x['unit'])}</td><td class='num'>{x['rate']:,.2f}</td>"
                          f"<td>{e(x.get('basis') or '')}</td></tr>" for x in es) + "</table>")
    if ot:
        out += ("<h2>Other construction elements identified (not quantified)</h2><table><tr><th>Element</th><th>Where</th><th>Status</th></tr>"
                + "".join(f"<tr><td>{e(o['element'])}</td><td>{e('; '.join(o['sheets'])[:90])}</td><td>{e(o['status'])}</td></tr>" for o in ot) + "</table>")
    return out


def _land_line(full):
    L = full.get("land") or {}
    if not L.get("provided"):
        return '<div class="meta">2 · With land: not entered</div>'
    return (f'<div class="meta">2 · Construction + land: <b>{inr(L["total_with_land"])}</b> — land {L["area_sqm"]:,.1f} m² × '
            f'{inr(L["rate_per_sqm"])}/m² ({html.escape(L.get("basis") or "user rate")}) = {inr(L["land_cost"])}'
            + (f' + stamp duty & registration {inr(L["stamp_duty_registration"])}' if L.get("stamp_duty_registration") else "") + '</div>')


KIND = {"floor_plan": "Floor plan", "section": "Section", "elevation": "Elevation", "structural": "Structural", "schedule": "Schedule", "other": "Reference"}
PARAMS = [("floors", "Floors"), ("floor_height", "Floor height (m)"), ("plinth_height", "Plinth height (m)"), ("foundation_depth", "Foundation depth (m)"),
          ("slab_thickness", "Slab thickness (m)"), ("parapet_height", "Parapet height (m)"), ("sill_height", "Sill height (m)"), ("lintel_height", "Lintel height (m)")]

CSS = """body{font-family:Helvetica,Arial,sans-serif;color:#111318;font-size:11px}
h1{font-size:22px;margin:4px 0} h2{font-size:13px;margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid #d9d9de}
.meta{color:#62677a;font-size:10px} .hero{border-bottom:2px solid #111318;padding-bottom:12px}
.total .l{font-size:9px;color:#62677a;text-transform:uppercase} .total .v{font-size:20px;font-weight:bold}
table{width:100%;border-collapse:collapse} th{background:#f4f4f6;text-align:left;padding:5px;font-size:9.5px;color:#62677a}
td{padding:5px;border-bottom:1px solid #ececef;vertical-align:top} .num{text-align:right;white-space:nowrap;font-size:9.5px;padding-left:8px}
tr.cat td{background:#f7f7f9;font-weight:bold} .sub{color:#62677a;font-size:9px;margin-top:2px}
.trace{color:#62677a;font-size:9px;margin-top:3px;border-left:2px solid #c9d3f5;padding-left:6px}
tr.flag td{background:#fff8ea} tr.sum td{font-weight:bold} tr.grand td{font-weight:bold;font-size:12px;border-top:2px solid #111318}
table.sign{margin-top:50px} table.sign td{border:0;border-top:1px solid #999;text-align:center;color:#62677a;width:33%}"""


def build_html(full: dict) -> str:
    full = brand.debrand(full)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Estimate — {html.escape(full['name'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}
body{{font-family:Inter,Helvetica,sans-serif;background:#f7f7f8;margin:0;font-size:12.5px}} .page{{max-width:1000px;margin:24px auto;background:#fff;padding:44px 52px;border:1px solid #e7e7ea;border-radius:12px}}
.hero{{display:flex;justify-content:space-between;align-items:flex-end}} .total{{text-align:right}} .total .v{{font-size:26px}} h1{{font-size:26px}}
.bar{{position:sticky;top:0;background:#fff;border-bottom:1px solid #e7e7ea;padding:10px 20px;display:flex;gap:8px;justify-content:flex-end}}
.bar a,.bar button{{font:inherit;border:1px solid #d9d9de;background:#fff;border-radius:8px;padding:7px 14px;cursor:pointer;text-decoration:none;color:#111318}}
.bar .dark{{background:#111318;color:#fff;border-color:#111318}}
@media print{{.bar{{display:none}} body{{background:#fff}} .page{{border:0;margin:0;padding:0}} tr{{page-break-inside:avoid}}}}</style></head>
<body><div class="bar"><a href="/api/projects/{full['id']}/export.xlsx">Download Excel</a><a class="dark" href="/api/projects/{full['id']}/report.pdf">Download PDF</a></div>
<div class="page">{_report_body(full)}</div></body></html>"""


def build_pdf(full: dict, previews_dir: str | None = None) -> bytes:
    full = brand.debrand(full)
    import pymupdf as fitz
    body = _report_body(full, for_pdf=True).replace("₹", "Rs ")
    story = fitz.Story(html=f"<html><body>{body}</body></html>", user_css=CSS)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    page_rect = fitz.paper_rect("a4")
    where = page_rect + (36, 40, -36, -40)
    more = True
    pno = 0
    while more:
        dev = writer.begin_page(page_rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
        pno += 1
    writer.close()
    # page numbers + header line
    doc = fitz.open("pdf", buf.getvalue())
    for i, pg in enumerate(doc):
        pg.insert_text(fitz.Point(36, 24), f"{full['name']}  -  Detailed estimate", fontsize=7, color=(0.45, 0.45, 0.5))
        pg.insert_text(fitz.Point(page_rect.width - 90, page_rect.height - 18), f"Page {i + 1} of {len(doc)}", fontsize=7, color=(0.45, 0.45, 0.5))
    return doc.tobytes(garbage=3, deflate=True)
