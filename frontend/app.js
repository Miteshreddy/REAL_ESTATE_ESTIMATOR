/* Drawing-based cost estimation — frontend (vanilla JS, no build step) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
// client-facing branding (mirrors backend/brand.py): the engine is state-specific, the UI just says "PWD"
const brand = (s) => String(s ?? "").replace(/,?\s*Government of Tamil Nadu/gi, "").replace(/,\s*Tamil Nadu\b/gi, "").replace(/\bTamil Nadu,\s*/gi, "").replace(/\s*·\s*Tamil Nadu\b/gi, "")
  .replace(/\bTamil Nadu\s+/gi, "").replace(/\s*\(?\bTamil Nadu\b\)?/gi, "").replace(/\bTN[ -](?=PWD|SOR|SD\b|Standard)/g, "");
const esc = (s) => brand(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const view = $("#view");
const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const inr = (v) => (v == null ? "—" : INR.format(v));
const lakh = (v) => (v >= 1e7 ? `₹${(v / 1e7).toFixed(2)} Cr` : `₹${(v / 1e5).toFixed(2)} L`);
const num = (v, d = 2) => (v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d }));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

const TYPE_COLORS = { living: "#5b8def", bedroom: "#8b7cf6", kitchen: "#f2a541", toilet: "#3fb68b", dining: "#e46fa8", utility: "#4cb8c4",
  store: "#9aa1b2", pooja: "#e0b43a", balcony: "#64a8e8", stair: "#a98be0", corridor: "#8d9bbd", study: "#e8805f", garage: "#8a929c", unknown: "#9aa1b2" };
const ROOM_TYPES = Object.keys(TYPE_COLORS);
const KIND = { floor_plan: "Floor plan", section: "Section", elevation: "Elevation", structural: "Structural", schedule: "Schedule", other: "Reference" };
const FLOORS = [["Basement", -1], ["Ground floor", 0], ["First floor", 1], ["Second floor", 2], ["Third floor", 3], ["Fourth floor", 4], ["Typical floor", 1]];
const PARAMS = [["floors", "Floors", 1], ["floor_height", "Floor height (m)", 0.05], ["plinth_height", "Plinth height (m)", 0.05], ["foundation_depth", "Foundation depth (m)", 0.1],
  ["slab_thickness", "Slab thickness (m)", 0.005], ["parapet_height", "Parapet height (m)", 0.05], ["sill_height", "Sill height (m)", 0.05], ["lintel_height", "Lintel height (m)", 0.05]];

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(path, o);
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}
function toast(msg, err = false) {
  const t = document.createElement("div"); t.className = "toast" + (err ? " err" : ""); t.textContent = msg;
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), 3200);
}
function modal(html, wide = false) { $("#modalCard").innerHTML = html; $("#modalCard").style.width = wide ? "min(900px,96vw)" : ""; $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("mousedown", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => e.key === "Escape" && closeModal());
async function safe(fn) { try { return await fn(); } catch (e) { toast(e.message, true); } }

function loading(title) {
  const stages = ["Reading drawings", "Identifying sheet types, floors and schedules", "Finding walls, rooms, doors and windows", "Reading levels and structural schedules", "Calculating quantities", "Applying PWD rates"];
  const d = document.createElement("div"); d.className = "loading";
  d.innerHTML = `<div><div class="spinner"></div><b>${esc(title)}</b><div class="stage-txt" id="stg">${stages[0]}…</div></div>`;
  document.body.appendChild(d);
  let i = 0; const iv = setInterval(() => { i = Math.min(i + 1, stages.length - 1); $("#stg", d).textContent = stages[i] + "…"; }, 1100);
  return () => { clearInterval(iv); d.remove(); };
}

// ------------------------------------------------------------------ router
const routes = [[/^#?\/?$/, renderHome], [/^#\/estimates$/, renderEstimates], [/^#\/rates$/, renderRates], [/^#\/annotate(?:\/([\w-]+))?$/, (m) => renderAnnotate(m[1])], [/^#\/p\/(\w+)(?:\/(\w+))?$/, (m) => renderProject(m[1], m[2])]];
function router() {
  const h = location.hash || "#/";
  $$(".nav nav a").forEach((a) => a.classList.toggle("on", h.startsWith(a.getAttribute("href"))));
  for (const [re, fn] of routes) { const m = h.match(re); if (m) return fn(m); }
  renderHome();
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); router(); });
document.addEventListener("click", (e) => { if (e.target.closest("#navnew")) { e.preventDefault(); newProjectDialog(); } });

// ------------------------------------------------------------------ project location → applicable rate schedule
// Every option and every decision comes from the backend (/api/locations, /api/rate-schedules/applicable).
let LOCS = null;
const getLocs = async () => (LOCS ||= await api("/api/locations"));
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v)).toString();
function rsKV(s) {
  if (!s) return "";
  const rows = [["Authority", s.authority + (s.department ? ` — ${s.department}` : "")], ["Schedule", s.name], ["Applies to", s.scope],
    ["Year / FY", [s.year, s.financial_year].filter(Boolean).join(" / ") || "not recorded"], ["Revision", s.revision || "—"],
    ["Effective", (s.effective_from || "not recorded") + (s.effective_to ? ` to ${s.effective_to}` : "")], ["Items", num(s.item_count, 0)],
    ["Source", (s.source || "") + (s.source_ref ? `: ${s.source_ref}` : "")]];
  return `<div class="kv">${rows.map(([k, v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join("")}</div>`;
}
function resolutionHTML(r, name = "rsch") {
  if (r.status === "selected") return `<div class="rsrc"><div class="t">Applicable rate schedule</div><b>✓ ${esc(r.schedule.label)}</b><div class="muted" style="font-size:12.5px">${esc(r.reason)}</div>${rsKV(r.schedule)}</div>`;
  if (r.status === "ambiguous") return `<div class="rsrc"><div class="t">Choose the applicable rate schedule</div><div class="muted" style="font-size:12.5px">${esc(r.reason)}</div>
    ${r.candidates.map((c) => `<label class="choice"><input type="radio" name="${name}" value="${esc(c.id)}"><div><b>${esc(c.label)}</b><div class="muted" style="font-size:12.5px">${esc(c.authority)} · applies to ${esc(c.scope)} · ${esc(c.authority_level || "")} works · ${num(c.item_count, 0)} items</div></div></label>`).join("")}
    <label class="choice"><input type="radio" name="${name}" value="" checked><div class="muted">Decide later — quantities are calculated, items stay unpriced until a schedule is selected</div></label></div>`;
  return `<div class="rsrc none"><div class="t">PWD rates</div><b>No validated PWD schedule is active.</b><div style="font-size:12.5px;margin-top:4px">${esc(r.reason)}</div>
    <div style="font-size:12.5px;margin-top:4px">Quantities will still be taken off. An administrator can refresh it under <a class="btn-link" href="#/rates">PWD data</a>.</div></div>`;
}
async function locationForm(el, init = {}, moreEl = null) {
  const L = await getLocs();
  const c = L.countries[0];
  const district = `<div><label class="lbl">District</label><select class="input" data-l="district"><option value="">Not specified</option>${(c.districts || []).map((d) => `<option ${d === init.district ? "selected" : ""}>${esc(d)}</option>`).join("")}</select></div>`;
  const rest = `<div><label class="lbl">City / municipality</label><input class="input" data-l="city" placeholder="Optional" value="${esc(init.city || "")}"></div>
      <div><label class="lbl">Executing authority</label><select class="input" data-l="executing_authority"><option value="">Not specified</option>${(L.executing_authorities || []).map((a) => `<option ${a === init.executing_authority ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></div>`;
  if (moreEl) { el.innerHTML = `${district}<div data-rs></div>`; moreEl.innerHTML = `<div class="locgrid" style="grid-template-columns:1fr 1fr">${rest}</div>`; }
  else el.innerHTML = `<div class="locgrid" style="grid-template-columns:1fr 1fr 1fr">${district}${rest}</div><div data-rs></div>`;
  const fields = () => [...$$("[data-l]", el), ...(moreEl ? $$("[data-l]", moreEl) : [])];
  const value = () => { const v = { country: "India", region: "Tamil Nadu", ...(init.municipality ? { municipality: init.municipality } : {}) }; fields().forEach((i) => { if (i.value.trim()) v[i.dataset.l] = i.value.trim(); }); return v; };
  let res = null;
  const refresh = async () => {
    res = await api("/api/rate-schedules/applicable?" + qs(value()));
    $("[data-rs]", el).innerHTML = moreEl && res.status === "selected"
      ? `<div class="muted" style="font-size:12.5px;margin-top:6px">Rates: <b style="color:var(--text)">✓ ${esc(res.schedule.label)}</b></div>` : resolutionHTML(res);
  };
  fields().forEach((i) => (i.onchange = refresh));
  await refresh();
  return { value, resolution: () => res, choice: () => (res?.status === "selected" ? res.schedule.id : "") };
}
function rateSourcePanel(P) {
  const rs = P.rate_source || {}, s = rs.schedule, sel = rs.selection || {};
  const MODE = { auto: "selected automatically for the project's jurisdiction", manual: "selected by the user", legacy: "kept from before jurisdiction support", none: "" };
  return `<div class="card pad no-lock" style="margin-bottom:14px"><div class="row" style="flex-wrap:wrap"><div class="grow"><b>Rate source</b>
      <div class="muted" style="font-size:13px;margin-top:2px">Project location: <b style="color:var(--text)">${esc(rs.location_text || "Not specified")}</b></div></div>
      ${locked() ? "" : `<button class="btn btn-sm" id="chloc">Change location</button><button class="btn btn-sm" id="chsch">Change rate schedule</button>`}</div>
    ${s ? `<div class="rsrc"><div class="t">Rates are taken only from</div><b>${esc(s.label)}</b> <span class="badge ${s.status === "active" ? "ok" : "warn"}">${esc(s.status)}</span>
        <div class="muted" style="font-size:12.5px">${esc(MODE[sel.mode] || sel.mode || "")}${sel.reason ? " — " + esc(sel.reason) : ""}</div>${rsKV(s)}</div>`
      : `<div class="rsrc none"><b>No official rate schedule is applied.</b><div style="font-size:12.5px;margin-top:4px">${esc(rs.message || "")}</div><div style="font-size:12.5px;margin-top:4px">Quantities are complete; every item is unpriced until a schedule is selected.</div></div>`}</div>`;
}
function bindRateSource() {
  $("#chloc") && ($("#chloc").onclick = async () => {
    modal(`<h2>Project location</h2><p class="muted" style="margin:6px 0 4px">Changing the jurisdiction may change the applicable PWD/SOR rates and therefore the estimated cost. Quantities are not affected.</p><div id="lf"></div>
      <div class="row" style="justify-content:flex-end;margin-top:18px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Save location</button></div>`, true);
    const lf = await locationForm($("#lf"), WS.P.loc || {});
    $("#cx").onclick = closeModal;
    $("#sv").onclick = () => safe(async () => {
      const r = await api(`/api/projects/${WS.P.id}/location`, { method: "PATCH", json: { loc: lf.value() } });
      const pick = lf.choice();
      let P = r;
      if (pick && r.rate_source?.schedule?.id !== pick) P = await api(`/api/projects/${WS.P.id}/rate-schedule`, { method: "PATCH", json: { schedule_id: pick } });
      closeModal(); setP(P); if (r.notice) toast(r.notice);
    });
  });
  $("#chsch") && ($("#chsch").onclick = async () => {
    const [res, all] = await Promise.all([api("/api/rate-schedules/applicable?" + qs(WS.P.loc || {})), api("/api/rate-schedules?status=active")]);
    const ids = new Set(res.candidates.map((c) => c.id));
    const others = all.filter((s) => !ids.has(s.id));
    modal(`<h2>Rate schedule</h2><p class="muted" style="margin:6px 0 10px">Location: ${esc(WS.P.rate_source?.location_text || "Not specified")}. ${esc(res.reason)}</p>
      ${res.candidates.map((c) => `<label class="choice"><input type="radio" name="sc" value="${esc(c.id)}" ${WS.P.rate_source?.schedule?.id === c.id ? "checked" : ""}><div><b>${esc(c.label)}</b><div class="muted" style="font-size:12.5px">${esc(c.authority)} · applies to ${esc(c.scope)} · ${num(c.item_count, 0)} items</div></div></label>`).join("") || `<div class="rsrc none">No configured schedule covers this jurisdiction.</div>`}
      ${others.length ? `<details style="margin-top:12px"><summary class="muted" style="cursor:pointer">Other active schedules (not configured for this jurisdiction)</summary>
        ${others.map((c) => `<label class="choice"><input type="radio" name="sc" value="${esc(c.id)}" data-out="1"><div><b>${esc(c.label)}</b><div class="muted" style="font-size:12.5px">${esc(c.authority)} · applies to ${esc(c.scope)}</div></div></label>`).join("")}
        <label class="lbl" style="margin-top:10px">Reason for using a schedule outside the project's jurisdiction (required, recorded)</label><input class="input" id="why"></details>` : ""}
      <div class="row" style="justify-content:flex-end;margin-top:18px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Apply schedule</button></div>`, true);
    $("#cx").onclick = closeModal;
    $("#sv").onclick = () => safe(async () => {
      const r = $("input[name=sc]:checked"); if (!r) return toast("Select a schedule", true);
      if (r.dataset.out && !$("#why").value.trim()) return toast("Give the reason for using this schedule", true);
      const P = await api(`/api/projects/${WS.P.id}/rate-schedule`, { method: "PATCH", json: { schedule_id: r.value, reason: $("#why")?.value || "" } });
      closeModal(); setP(P); toast("Rate schedule applied — rates and cost recalculated, quantities unchanged");
    });
  });
}
const schedQ = () => (WS.P?.rate_source?.schedule?.id ? `&schedule_id=${encodeURIComponent(WS.P.rate_source.schedule.id)}` : "");

async function loadMarketCheck(pid, refresh = false) {
  const el = $("#mkt"); if (!el) return;
  let r;
  try { r = await api(`/api/projects/${pid}/market-check${refresh ? "?refresh=1" : ""}`); } catch (e) { r = { benchmark: { enabled: true, ok: false, message: String(e) } }; }
  if (!$("#mkt") || WS.P?.id !== pid) return;
  const b = r.benchmark || {}, v = r.verdict || {};
  const head = `<div class="row"><b class="grow">Market check</b>${b.enabled ? `<button class="btn btn-sm" id="mktr">Refresh</button>` : ""}</div>`;
  if (!b.enabled) { el.innerHTML = `${head}<div class="muted" style="font-size:12.5px;margin-top:6px">${esc(b.message || "")}</div>`; return; }
  if (!b.ok) el.innerHTML = `${head}<div class="muted" style="font-size:12.5px;margin-top:6px">${esc(b.message || `Not enough web prices found for "${b.building_type || "this building"}".`)}</div>`;
  else el.innerHTML = `${head}<div class="benchmark ${v.level === "ok" ? "" : "warn"}"><b>₹${num(b.low, 0)} – ₹${num(b.high, 0)} per sq ft</b> on the web (median ₹${num(b.median, 0)}, ${b.n} prices, ${esc(b.place)})
      <div style="margin-top:6px">${esc(v.text || "")}</div>
      ${r.market_total ? `<div style="margin-top:6px"><span class="badge warn">Preliminary budget range</span> ${num(r.market_total.built_up_sqft, 0)} sq ft × market rate: <b>${inr(r.market_total.median)}</b> <span class="muted">(${inr(r.market_total.low)} – ${inr(r.market_total.high)})</span>
        <div class="muted" style="font-size:12px">Area: ${esc(r.market_total.area_basis)}. Not a drawing-based BOQ.</div></div>` : ""}</div>
    ${b.official ? `<div class="muted" style="font-size:12.5px"><b>Historical context only</b> — official TNRD unit costs for ${esc(b.official.year)} (${esc(b.official.group)} buildings): ₹${num(b.official.low, 0)} – ₹${num(b.official.high, 0)} per sq ft. These are ${esc(b.official.year)} prices, not current costs.</div>` : ""}
    <details class="more"><summary>Sources (${b.sources.length}) · read by ${esc((b.read_by || []).join(", ") || "—")} · checked ${esc(b.checked || "")}${r.benchmark.cached ? " · cached" : ""}</summary>
      ${b.search_note ? `<div class="muted" style="font-size:12px;margin-top:4px">${esc(b.search_note)}</div>` : ""}
      ${b.sources.map((s) => `<div style="font-size:12px;margin-top:4px">₹${num(s.value, 0)}/sq ft — <a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.url)}</a></div>`).join("")}
      <div class="muted" style="font-size:12px;margin-top:6px">${esc(b.note || "")}</div></details>`;
  $("#mktr") && ($("#mktr").onclick = () => { el.querySelector(".benchmark, .muted") && (el.innerHTML = `${head}<div class="muted" style="font-size:12.5px;margin-top:6px">Searching…</div>`); loadMarketCheck(pid, true); });
}

// ------------------------------------------------------------------ HOME (projects)
const BUILDING_TYPES = ["Residential house", "Apartment / multi-storey residential", "Hospital / health centre", "School", "College / university",
  "Hostel", "Commercial building", "Government office", "Community / public building", "Other"];
function detailsMain(P = {}) {
  const d = P.details || {};
  return `<div class="details" style="grid-template-columns:3fr 2fr"><div><label class="lbl">Project name *</label><input class="input" id="pn" value="${esc(P.name || "")}" placeholder="e.g. Women's hostel, Block A"></div>
      <div><label class="lbl">Building type</label><select class="input" id="pt"><option value="">Select</option>${BUILDING_TYPES.map((t) => `<option ${t === d.building_type ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div></div>`;
}
function detailsExtra(P = {}) {
  const d = P.details || {};
  return `<div class="details" style="grid-template-columns:1fr 1fr"><div><label class="lbl">Client / department</label><input class="input" id="pc" value="${esc(d.client || "")}" placeholder="Optional"></div>
      <div><label class="lbl">Site address</label><input class="input" id="pa" value="${esc(d.site_address || "")}" placeholder="Street, area, town"></div></div>
    <div style="margin-top:10px"><label class="lbl">Notes</label><textarea class="input" id="pd" rows="2" placeholder="Optional">${esc(d.description || "")}</textarea></div>`;
}
const detailsFields = (P = {}) => detailsMain(P) + `<div style="margin-top:12px">${detailsExtra(P)}</div>`;
let SCOPE_OPTS = null;
const getScopeOpts = async () => (SCOPE_OPTS ||= await api("/api/scope-options"));
const SCOPE_SHORT = { room: "Room", section: "Section / wing", floors: "Floors", property: "Whole building", custom: "Selected work" };
const SCOPE_HELP = {
  room: "One bedroom, bathroom, kitchen or office room. Upload just that room's drawing — no floor count needed.",
  section: "Several rooms, a wing, block, terrace or parking area.",
  floors: "One floor, selected floors, or as many floors as you need. Different layouts per floor are fine.",
  property: "A whole villa, apartment complex, hospital, hostel, office or commercial building.",
  custom: "Only selected work — e.g. painting, flooring, masonry or plastering.",
};
const CONFIG_GROUP = (bt) => /apartment/i.test(bt || "") ? "apartment" : /house|villa/i.test(bt || "") ? "house"
  : /hospital|hostel|school|college|office|commercial|public/i.test(bt || "") ? "institutional" : "other";
const CONFIG_LABEL = { blocks: "Number of blocks", floors: "Number of floors", units: "Flats / units", parking: "Basement / stilt parking",
  lifts: "Lifts", staircases: "Staircases", typical_floors: "Floors with the same (typical) layout", storeys: "Storeys", houses: "Number of houses / villas",
  built_up_area_m2: "Built-up area (m², if known)", roof_type: "Roof type", beds_or_rooms: "Beds / rooms / wards", occupancy: "Occupancy",
  special_services: "Special structural / service needs", notes: "Notes", repeat: "This section repeats on how many floors?" };
async function scopeFields(sc = {}, bt = "") {
  const O = await getScopeOpts(), t = sc.type || "property", cats = sc.categories || O.presets[t], cfg = sc.config || {};
  const cfgKeys = (t === "room" ? [] : t === "section" ? ["repeat"] : O.config_fields[CONFIG_GROUP(bt)]).filter((k) => k !== "built_up_area_m2");
  const floorsBox = `<div><label class="lbl">Which floors? (optional)</label><input class="input" data-cfg="floors_list" value="${esc(cfg.floors_list ?? "")}" placeholder="e.g. 4,5,6 or G,1,2"></div>`;
  return `<div class="pills">${Object.keys(O.types).map((k) => `<label class="pill"><input type="radio" name="sct" value="${k}" ${k === t ? "checked" : ""}><span>${esc(SCOPE_SHORT[k] || O.types[k])}</span></label>`).join("")}</div>
    <div class="muted" style="font-size:12.5px;margin-top:6px">${esc(SCOPE_HELP[t] || "")}</div>
    ${["floors", "section"].includes(t) ? `<div style="margin-top:10px">${floorsBox}</div>` : ""}
    ${t !== "custom" ? `<div class="details" style="grid-template-columns:2fr 1fr;margin-top:10px"><div><label class="lbl">Total built-up area, if known (optional — makes the estimate much more accurate)</label>
      <input class="input" type="number" min="0" step="any" data-area value="${cfg.built_up_area_m2 ? Math.round(+cfg.built_up_area_m2 * 10.7639) : ""}" placeholder="e.g. 2000"></div>
      <div><label class="lbl">Unit</label><select class="input" data-area-unit><option value="sqft" selected>sq ft</option><option value="m2">m²</option></select></div></div>` : ""}
    <details class="more" style="margin-top:10px" ${t === "custom" ? "open" : ""}><summary>Scope options</summary>
    <div style="margin-top:10px"><label class="lbl">Scope name</label><input class="input" id="scl" value="${esc(sc.label || "")}" placeholder="e.g. Master bedroom, Block B"></div>
    <div class="lbl" style="margin-top:10px">Work included (${cats.length} of ${O.categories.length})</div>
      <div class="catgrid">${O.categories.map((c) => `<label><input type="checkbox" data-cat="${esc(c)}" ${cats.includes(c) ? "checked" : ""}> ${esc(c)}</label>`).join("")}</div>
      <div class="muted" style="font-size:12px">Unticked work is still measured and listed, but not added to the total.</div>
    <div class="details" style="grid-template-columns:1fr 1fr;margin-top:10px">
      ${t === "property" ? floorsBox : ""}
      <div><label class="lbl">Assumed structure (no structural drawing)</label><select class="input" data-cfg="assumption_policy">
        <option value="provisional" ${cfg.assumption_policy !== "strict" ? "selected" : ""}>Include as provisional</option>
        <option value="strict" ${cfg.assumption_policy === "strict" ? "selected" : ""}>Leave out of total</option></select></div></div>
    ${t !== "room" && t !== "custom" ? `<label style="display:block;margin-top:8px;font-size:13px"><input type="checkbox" data-cfgb="include_foundation" ${cfg.include_foundation ? "checked" : ""}> Include new foundation even if only upper floors are drawn</label>` : ""}
    ${cfgKeys.length ? `<div class="lbl" style="margin-top:12px">Building information (context only)</div>
      <div class="details" style="grid-template-columns:1fr 1fr;margin-top:6px">${cfgKeys.map((k) => `<div><label class="lbl">${esc(CONFIG_LABEL[k] || k)}</label><input class="input" data-cfg="${k}" value="${esc(cfg[k] ?? "")}"></div>`).join("")}</div>` : ""}
    </details>`;
}
async function bindScopeFields(el, bt) {  // re-render presets when the scope type changes
  el.querySelectorAll("input[name=sct]").forEach((r) => (r.onchange = async () => {
    const O = await getScopeOpts(), cur = readScope(el);
    el.innerHTML = await scopeFields({ type: r.value, label: cur.label, categories: O.presets[r.value], config: cur.config }, bt);
    bindScopeFields(el, bt);
  }));
}
function readScope(el) {
  const t = (el.querySelector("input[name=sct]:checked") || {}).value || "property";
  const cfg = {}; el.querySelectorAll("[data-cfg]").forEach((i) => { if (i.value.trim()) cfg[i.dataset.cfg] = i.value.trim(); });
  el.querySelectorAll("[data-cfgb]").forEach((i) => { cfg[i.dataset.cfgb] = i.checked; });
  const ar = el.querySelector("[data-area]");
  if (ar && +ar.value > 0) cfg.built_up_area_m2 = String(Math.round((el.querySelector("[data-area-unit]")?.value === "m2" ? +ar.value : +ar.value / 10.7639) * 10) / 10);
  return { type: t, label: (el.querySelector("#scl") || {}).value || "", categories: [...el.querySelectorAll("[data-cat]:checked")].map((c) => c.dataset.cat), config: cfg };
}
const readDetails = () => ({ client: $("#pc").value.trim(), building_type: $("#pt").value, site_address: $("#pa").value.trim(), description: $("#pd").value.trim() });
async function newProjectDialog() {
  modal(`<h2>New project</h2><p class="muted" style="margin:6px 0 14px">Name it, choose what to estimate, then upload drawings.</p>
    ${detailsMain()}<div style="margin-top:14px"><label class="lbl">What to estimate</label><div id="scf"></div></div>
    <div style="margin-top:12px" id="locf"></div>
    <details class="more" style="margin-top:12px"><summary>More details (optional)</summary><div style="margin-top:10px">${detailsExtra()}</div><div id="locmore" style="margin-top:10px"></div></details>
    <div class="row" style="justify-content:flex-end;margin-top:18px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Create project</button></div>`, true);
  const lf = await locationForm($("#locf"), {}, $("#locmore"));
  const scf = $("#scf"); scf.innerHTML = await scopeFields({}, ""); bindScopeFields(scf, "");
  $("#pt").onchange = async () => { const cur = readScope(scf); scf.innerHTML = await scopeFields(cur, $("#pt").value); bindScopeFields(scf, $("#pt").value); };
  $("#cx").onclick = closeModal;
  $("#sv").onclick = () => safe(async () => {
    const name = $("#pn").value.trim();
    if (!name) return toast("Enter a project name", true);
    const sc = readScope(scf);
    if (!sc.categories.length) return toast("Select at least one type of work to estimate", true);
    const fd = new FormData(), d = readDetails();
    fd.append("scope", JSON.stringify(sc));
    fd.append("name", name); Object.entries(d).forEach(([k, v]) => fd.append(k, v));
    fd.append("loc", JSON.stringify(lf.value())); if (lf.choice()) fd.append("rate_schedule_id", lf.choice());
    const p = await api("/api/projects", { method: "POST", body: fd });
    closeModal(); toast("Project created — now upload its drawings"); location.hash = `#/p/${p.id}/drawings`;
  });
}
async function renderHome() {
  const [samples, list] = await Promise.all([api("/api/samples").catch(() => []), api("/api/projects").catch(() => [])]);
  view.innerHTML = `<div class="wrap">
    <div class="home-hero"><h1>Create a project.<br>Upload its drawings. Get the estimate.</h1>
      <p>Each project keeps its own drawings, quantities, rates, reviews and reports.</p>
      <button class="btn btn-dark" id="np" style="height:44px;padding:0 22px;margin-top:6px">+ New project</button></div>
    <div class="steps">${[["01", "Create project", "Name, client, building type and location"], ["02", "Upload drawings", "Plans, sections, elevations and structural sheets"],
      ["03", "Review quantities & rates", "Area, length, volume, counts; PWD item per line"], ["04", "Get the estimate", "Item-wise and category-wise cost report"]]
      .map(([n, b, t]) => `<div><span class="n">${n}</span><b>${b}</b><span>${t}</span></div>`).join("")}</div>
    <div class="section-title"><h2>Projects</h2>${list.length > 4 ? `<a class="btn-link" href="#/estimates">View all</a>` : ""}</div>
    ${list.length ? `<div class="card">${estimatesTable(list.slice(0, 8))}</div>` : `<div class="card empty">No projects yet — create one to get started.</div>`}
    <div class="section-title"><h2>No drawings at hand? Try a sample</h2><span class="muted">Creates a project with a generated drawing set</span></div>
    <div class="samples">${samples.map((x) => `<div class="card sample"><img src="/api/samples/${x.thumb}" alt="${esc(x.label)}" data-s="${x.files[0]}" data-l="${esc(x.label)}">
      <div class="bd"><b>${esc(x.label)}</b><div class="muted" style="font-size:13px;min-height:38px">${esc(x.desc)}</div>
      <div class="fmts">${x.files.map((f) => `<button class="btn btn-sm" data-s="${f}" data-l="${esc(x.label)}">${f.split(".").pop().toUpperCase()}</button>`).join("")}
      <a class="btn btn-sm" href="/api/samples/${x.files[0]}" target="_blank" title="Open the drawing">View drawing</a></div></div></div>`).join("")}</div>
  </div>`;
  bindEstimatesTable();
  $("#np").onclick = newProjectDialog;
  $$("[data-s]").forEach((b) => (b.onclick = () => {
    const fd = new FormData(); fd.append("name", `${b.dataset.l} (sample)`); fd.append("sample", b.dataset.s); fd.append("loc", "{}");
    create(fd, b.dataset.l);
  }));
}
async function create(fd, title) {
  const done = loading(`Analysing ${title}`);
  try { const p = await api("/api/projects", { method: "POST", body: fd }); done(); location.hash = `#/p/${p.id}/drawings`; }
  catch (e) { done(); toast("Could not analyse: " + e.message, true); }
}

// ------------------------------------------------------------------ ESTIMATES list
const STATUS = { draft: ["Draft", ""], in_review: ["In review", "warn"], confirmed: ["Confirmed · locked", "ok"] };
function estimatesTable(list) {
  return `<table class="table"><thead><tr><th>Project</th><th>Drawings</th><th class="num">Plinth area</th><th>Status</th><th class="num">Estimated cost</th><th></th></tr></thead><tbody>
    ${list.map((p) => `<tr class="click" data-open="${p.id}"><td><b>${esc(p.name)}</b><div class="sub">${[p.details?.building_type, p.details?.client, p.location].filter(Boolean).map(esc).join(" · ")}${p.details?.building_type || p.details?.client || p.location ? " · " : ""}Updated ${esc(p.updated.replace("T", " ").slice(0, 16))}</div></td>
      <td class="muted">${p.files} file(s) · ${p.sheets} sheet(s)</td><td class="num">${num(p.plinth, 1)} m²</td><td><span class="badge ${STATUS[p.status]?.[1] || ""}">${STATUS[p.status]?.[0] || esc(p.status)}</span></td>
      <td class="num"><b>${inr(p.total)}</b></td><td class="num"><button class="btn-link" data-del="${p.id}" style="color:var(--dim)">Delete</button></td></tr>`).join("")}</tbody></table>`;
}
function bindEstimatesTable(after) {
  $$("[data-open]").forEach((r) => (r.onclick = (e) => { if (!e.target.closest("[data-del]")) location.hash = `#/p/${r.dataset.open}/drawings`; }));
  $$("[data-del]").forEach((b) => (b.onclick = async () => { if (!confirm("Delete this estimate?")) return; await api(`/api/projects/${b.dataset.del}`, { method: "DELETE" }); (after || router)(); }));
}
async function renderEstimates() {
  const list = await api("/api/projects");
  view.innerHTML = `<div class="wrap"><div class="row" style="margin-bottom:20px"><h1 class="grow" style="font-size:24px">Projects</h1><button class="btn btn-dark" id="np2">+ New project</button></div>
    <div class="card">${list.length ? estimatesTable(list) : `<div class="empty">No projects yet.</div>`}</div></div>`;
  bindEstimatesTable(renderEstimates);
  $("#np2").onclick = newProjectDialog;
}

// ------------------------------------------------------------------ TAMIL NADU PWD DATA (admin)
function tnDataPanel(T) {
  if (!T) return "";
  const a = T.active;
  const docs = T.documents || [];
  return `<div class="card pad" style="margin-bottom:16px">
    <div class="kv"><span>Current edition</span><span>${a ? esc(a.label) + " · effective " + esc(a.effective_from || "—") + " · " + num(a.item_count, 0) + " items" : "none active"}</span>
      <span>Previous editions</span><span>${esc((T.previous || []).map((x) => x.label).join("; ") || "—")}</span>
      <span>Last checked</span><span>${esc((T.last_check || "never").replace("T", " "))}</span>
      <span>Source</span><span>${esc(a?.source_ref || "—")}</span></div>
    <table class="table" style="margin-top:10px"><thead><tr><th>Document</th><th>Type</th><th>FY / effective</th><th>Verification</th><th>SHA-256</th></tr></thead><tbody>
      ${docs.map((d) => `<tr><td>${esc(d.title)}${d.revision ? `<div class="sub">${esc(d.revision)}</div>` : ""}</td><td>${esc(d.doc_type)}</td><td>${esc((d.financial_year || "") + " " + (d.effective_from || ""))}</td>
        <td><span class="badge ${d.verification_status === "cross-verified" || d.verification_status === "official source" ? "ok" : "warn"}" title="${esc(d.verification_note || "")}">${esc(d.verification_status)}</span></td><td class="mono sub">${esc((d.sha256 || "").slice(0, 12))}…</td></tr>`).join("")}</tbody></table>
    <div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap">
      ${[["check", "Check for updates"], ["download", "Download"], ["extract", "Extract"], ["build", "Validate & compare"], ["activate", "Activate"]].map(([k, l]) => `<button class="btn btn-sm" data-tn="${k}">${l}</button>`).join("")}</div></div>`;
}

// ------------------------------------------------------------------ PWD RATE LIBRARY + RATE ANALYSIS
const RF = { country: "", region: "", authority_level: "", status: "", sid: "" };
async function renderRates() {
  const L = await getLocs();
  let list = (await api("/api/rate-schedules?" + qs({ status: RF.status }))).filter((s) => s.region === "Tamil Nadu");
  const T = await api("/api/tnpwd/status").catch(() => null);
  if (!list.find((s) => s.id === RF.sid)) RF.sid = (list.find((s) => s.status === "active") || list[0])?.id || "";
  const S = list.find((s) => s.id === RF.sid);
  const ctry = L.countries.find((c) => c.name === RF.country);
  view.innerHTML = `<div class="wrap"><div class="row" style="margin-bottom:6px;flex-wrap:wrap"><h1 class="grow" style="font-size:24px">PWD data</h1></div>
    <p class="muted" style="margin:0 0 16px">Schedule of Rates, amendments and Standard Data Book of the Public Works Department, ingested from public documents with SHA-256, page and verification status. Only a validated, activated edition prices estimates; earlier editions stay for audit.</p>
    ${tnDataPanel(T)}
    <div class="toolbar" style="flex-wrap:wrap">
      <select class="input" data-f="status" style="max-width:150px"><option value="">Any status</option>${["active", "draft", "inactive"].map((s) => `<option ${s === RF.status ? "selected" : ""}>${s}</option>`).join("")}</select></div>
    <div class="card" style="margin-bottom:16px"><table class="table"><thead><tr><th>Schedule</th><th>Authority</th><th>Applies to</th><th>Year / FY</th><th>Revision</th><th class="num">Items</th><th>Status</th></tr></thead><tbody>
      ${list.map((s) => `<tr class="click ${s.id === RF.sid ? "sel" : ""}" data-sid="${esc(s.id)}" style="${s.id === RF.sid ? "background:var(--accent-soft)" : ""}"><td><b>${esc(s.name)}</b><div class="sub mono">${esc(s.id)}</div></td><td>${esc(s.authority)}</td><td>${esc(s.scope)}</td>
        <td>${esc([s.year, s.financial_year].filter(Boolean).join(" / ") || "—")}</td><td>${esc(s.revision || "—")}</td><td class="num">${num(s.item_count, 0)}</td>
        <td><span class="badge ${s.status === "active" ? "ok" : s.status === "draft" ? "warn" : ""}">${esc(s.status)}</span></td></tr>`).join("") || `<tr><td colspan="7" class="empty">No rate schedule matches these filters.</td></tr>`}</tbody></table></div>
    ${S ? `<div class="card pad" style="margin-bottom:16px"><div class="row" style="flex-wrap:wrap"><div class="grow"><b>${esc(S.label)}</b> <span class="badge ${S.status === "active" ? "ok" : "warn"}">${esc(S.status)}</span></div>
        <button class="btn btn-sm" id="imp">Import items (Excel / CSV)</button><a class="btn btn-sm" href="/api/sor/export.csv?schedule_id=${encodeURIComponent(S.id)}">Export CSV</a>
        ${S.status === "active" ? `<button class="btn btn-sm" id="deact">Deactivate</button>` : `<button class="btn btn-sm btn-dark" id="act">Activate</button>`}
        <button class="btn btn-sm" id="add">Add item</button></div>${rsKV(S)}
        ${S.notes ? `<div class="muted" style="font-size:12.5px;margin-top:8px">${esc(S.notes)}</div>` : ""}
        <div class="muted" style="font-size:12.5px;margin-top:6px">Imported ${esc((S.imported_on || "—").replace("T", " "))}${S.imported_by ? " by " + esc(S.imported_by) : ""}</div></div>
      <input type="file" id="csv" accept=".csv,.xlsx,.xlsm" hidden>
      <div class="toolbar"><input class="input" id="q" placeholder="Search by description or code" style="max-width:340px"><select class="input" id="cat" style="max-width:220px"><option value="">All categories</option></select><span class="dim" id="cnt"></span><span class="grow"></span>
        ${S.id === "in-cpwd-dsr-2023-civil" ? `<button class="btn-link" id="rst" style="color:var(--muted)">Restore CPWD DSR 2023 from its source file</button>` : ""}</div>
      <div class="card"><table class="table"><thead><tr><th style="width:90px">Code</th><th>Description</th><th style="width:140px">Category</th><th style="width:60px">Unit</th><th class="num" style="width:130px">Rate (₹)</th><th style="width:120px">Rate analysis</th><th style="width:40px"></th></tr></thead><tbody id="tb"></tbody></table></div>` : ""}</div>`;
  $$("[data-f]").forEach((el) => (el.onchange = () => { RF[el.dataset.f] = el.value; if (el.dataset.f === "country") RF.region = ""; renderRates(); }));
  $$("[data-sid]").forEach((r) => (r.onclick = () => { RF.sid = r.dataset.sid; renderRates(); }));
  $$("[data-tn]").forEach((b) => (b.onclick = async () => {
    b.disabled = true; b.textContent = "Working…";
    try { const r = await api("/api/tnpwd/" + b.dataset.tn, { method: "POST", body: JSON.stringify({}) }); alert(JSON.stringify(r, null, 1).slice(0, 3000)); }
    catch (e) { alert(e.message); }
    renderRates();
  }));
  if (!S) return;
  const sq = `schedule_id=${encodeURIComponent(S.id)}`;
  let rows = await api(`/api/sor?${sq}`);
  const cats = [...new Set(rows.map((r) => r.category))];
  $("#cat").innerHTML = `<option value="">All categories</option>${cats.map((c) => `<option>${esc(c)}</option>`).join("")}`;
  const reload = async () => { rows = await api(`/api/sor?${sq}`); paint(); };
  const paint = () => {
    const q = $("#q").value.toLowerCase(), c = $("#cat").value;
    const f = rows.filter((r) => (!c || r.category === c) && (!q || (r.description + r.code).toLowerCase().includes(q)));
    $("#cnt").textContent = `${f.length} items`;
    $("#tb").innerHTML = f.slice(0, 600).map((r) => `<tr><td class="code">${esc(r.code)}</td><td style="color:var(--muted)">${esc(r.description)}</td><td>${esc(r.category)}</td><td>${esc(r.unit)}</td>
      <td class="num"><input class="cell" data-code="${esc(r.code)}" value="${r.rate}"></td>
      <td><button class="btn-link" data-ra="${esc(r.code)}">${r.analysis ? "View analysis" : "Build analysis"}</button></td>
      <td class="num"><button class="btn-link" data-dr="${esc(r.code)}" style="color:var(--dim)">✕</button></td></tr>`).join("") + (f.length > 600 ? `<tr><td colspan="7" class="dim">Showing 600 of ${f.length} — refine the search</td></tr>` : "");
    $$("[data-code]").forEach((i) => (i.onchange = async () => { await safe(() => api(`/api/sor/${encodeURIComponent(i.dataset.code)}?${sq}`, { method: "PUT", json: { rate: +i.value } })); toast(`Rate ${i.dataset.code} updated`); reload(); }));
    $$("[data-dr]").forEach((b) => (b.onclick = async () => { if (!confirm(`Delete item ${b.dataset.dr} from ${S.name}?`)) return; await api(`/api/sor/${encodeURIComponent(b.dataset.dr)}?${sq}`, { method: "DELETE" }); reload(); }));
    $$("[data-ra]").forEach((b) => (b.onclick = () => rateAnalysis(rows.find((r) => r.code === b.dataset.ra), reload)));
  };
  paint(); $("#q").oninput = paint; $("#cat").onchange = paint;
  $("#imp").onclick = () => $("#csv").click();
  $("#csv").onchange = async () => {
    const file = $("#csv").files[0]; $("#csv").value = "";
    let replace = false;
    if (S.status === "active") { if (!confirm(`${S.name} is active. Replace ALL its items with this file? (Usually a new revision should be created as a new schedule instead.)`)) return; replace = true; }
    const fd = new FormData(); fd.append("file", file); fd.append("replace", replace ? "true" : "false"); fd.append("by", prompt("Imported by (name, recorded):", "") || "");
    const r = await fetch(`/api/rate-schedules/${encodeURIComponent(S.id)}/import`, { method: "POST", body: fd }); const j = await r.json();
    if (!r.ok) { const d = j.detail || {}; return modal(`<h2>Import rejected</h2><p class="muted" style="margin:6px 0">${esc(d.message || "Nothing was changed.")} ${d.error_count ? `${d.error_count} problem(s) found; ${d.valid_rows || 0} rows were valid.` : ""}</p><ul class="errlist">${(d.errors || []).map((e) => `<li>${esc(e)}</li>`).join("")}</ul><div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn" onclick="document.getElementById('modal').classList.add('hidden')">Close</button></div>`, true); }
    toast(`Imported ${j.imported} items`); renderRates();
  };
  const setStatus = (status) => safe(async () => {
    const r = await fetch(`/api/rate-schedules/${encodeURIComponent(S.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); const j = await r.json();
    if (!r.ok) { const d = j.detail || {}; return modal(`<h2>Not changed</h2><p class="muted">${esc(d.message || d)}</p><ul class="errlist">${(d.errors || []).map((e) => `<li>${esc(e)}</li>`).join("")}</ul><div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn" onclick="document.getElementById('modal').classList.add('hidden')">Close</button></div>`); }
    LOCS = null; toast(`Schedule ${status}`); renderRates();
  });
  $("#act") && ($("#act").onclick = () => setStatus("active"));
  $("#deact") && ($("#deact").onclick = () => { if (confirm("Deactivate this schedule? Projects already using it keep their rates; it will no longer be offered for new projects.")) setStatus("inactive"); });
  $("#rst") && ($("#rst").onclick = async () => { if (!confirm("Restore CPWD DSR 2023 from its source file (edits to this schedule are replaced)?")) return; await api("/api/sor/reset", { method: "POST" }); reload(); });
  $("#add").onclick = () => sorItemDialog(cats, reload, { schedule_id: S.id });
}
function scheduleDialog(L) {
  const f = (k, l, ph = "", t = "text") => `<div><label class="lbl">${l}</label><input class="input" data-m="${k}" type="${t}" placeholder="${esc(ph)}"></div>`;
  modal(`<h2>New rate schedule</h2><p class="muted" style="margin:6px 0 14px">Enter the metadata exactly as on the official document. The schedule is created as a <b>draft</b>; import its items, then activate it.</p>
    <div class="params" style="grid-template-columns:1fr 1fr 1fr">
      ${f("name", "Schedule name *", "e.g. Schedule of Rates 2025-26 (Buildings)")}${f("authority", "Authority *", "e.g. Telangana R&B Department")}${f("department", "Department", "")}
      <div><label class="lbl">Country *</label><select class="input" data-m="country">${L.countries.map((c) => `<option>${esc(c.name)}</option>`).join("")}</select></div>
      <div><label class="lbl">State / region (empty = whole country)</label><select class="input" data-m="region"><option value="">— whole country —</option>${(L.countries[0]?.regions || []).map((r) => `<option>${esc(r.name)}</option>`).join("")}</select></div>
      <div><label class="lbl">Authority level *</label><select class="input" data-m="authority_level">${L.authority_levels.map((a) => `<option value="${esc(a.value)}">${esc(a.label)}</option>`).join("")}</select></div>
      ${f("district", "District (only if the schedule is district-specific)")}${f("city", "City (only if the schedule is city-specific)")}${f("schedule_type", "Schedule type *", "SOR / DSR / …")}
      ${f("year", "Year", "e.g. 2025")}${f("financial_year", "Financial year", "e.g. 2025-26")}${f("revision", "Revision / corrigendum", "")}
      ${f("effective_from", "Effective from", "", "date")}${f("effective_to", "Effective to", "", "date")}${f("currency", "Currency *", "INR")}
      ${f("code_system", "Item numbering", "e.g. CPWD-DSR if it uses DSR item numbers")}${f("source", "Source *", "Official government document")}${f("source_ref", "Source reference", "Document title / G.O. no. / URL")}
      <div style="grid-column:1/-1"><label class="lbl">Notes</label><input class="input" data-m="notes"></div></div>
    <div class="row" style="justify-content:flex-end;margin-top:18px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Create draft schedule</button></div>`, true);
  $("[data-m=currency]").value = L.countries[0]?.currency || "INR"; $("[data-m=source]").value = "Official government document";
  $("[data-m=country]").onchange = () => { const c = L.countries.find((x) => x.name === $("[data-m=country]").value); $("[data-m=region]").innerHTML = `<option value="">— whole country —</option>` + (c?.regions || []).map((r) => `<option>${esc(r.name)}</option>`).join(""); $("[data-m=currency]").value = c?.currency || ""; };
  $("#cx").onclick = closeModal;
  $("#sv").onclick = async () => {
    const body = {}; $$("[data-m]").forEach((i) => { if (i.value.trim()) body[i.dataset.m] = i.value.trim(); });
    const r = await fetch("/api/rate-schedules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const j = await r.json();
    if (!r.ok) return toast((j.detail?.errors || [j.detail?.message || j.detail]).join(" · "), true);
    closeModal(); LOCS = null; RF.sid = j.id; RF.status = ""; toast("Draft schedule created — now import its items"); renderRates();
  };
}
function sorItemDialog(cats, after, preset = {}) {
  modal(`<h2>Add PWD item</h2><div class="params" style="margin-top:16px"><div><label class="lbl">Code</label><input class="input" id="nc" value="${esc(preset.code || "")}"></div><div><label class="lbl">Unit</label><input class="input" id="nu" value="${esc(preset.unit || "sqm")}"></div>
    <div style="grid-column:1/-1"><label class="lbl">Description</label><textarea class="input" id="nd" rows="3">${esc(preset.description || "")}</textarea></div><div><label class="lbl">Rate (₹)</label><input class="input" id="nr" type="number"></div>
    <div><label class="lbl">Category</label><select class="input" id="nk">${[...new Set([...(cats || []), "Miscellaneous"])].map((c) => `<option ${c === preset.category ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div></div>
    <div class="row" style="justify-content:flex-end;margin-top:20px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Save</button></div>`);
  $("#cx").onclick = closeModal;
  $("#sv").onclick = async () => { if (!$("#nc").value) return; await api(`/api/sor/${encodeURIComponent($("#nc").value)}${preset.schedule_id ? `?schedule_id=${encodeURIComponent(preset.schedule_id)}` : ""}`, { method: "PUT", json: { description: $("#nd").value, unit: $("#nu").value, rate: +$("#nr").value, category: $("#nk").value } }); closeModal(); toast("Item added"); after && after($("#nc").value); };
}
function rateAnalysis(item, after) {
  const a = JSON.parse(JSON.stringify(item.analysis || { per: 1, unit: item.unit, water_pct: 1, overhead_pct: 15, components: [
    { type: "material", desc: "", unit: "", qty: 0, rate: 0 }, { type: "labour", desc: "Mason", unit: "day", qty: 0, rate: 950 }, { type: "labour", desc: "Beldar / mazdoor", unit: "day", qty: 0, rate: 720 }] }));
  const calc = () => { const base = a.components.reduce((s, c) => s + (+c.qty || 0) * (+c.rate || 0), 0); const w = base * (+a.water_pct || 0) / 100, o = (base + w) * (+a.overhead_pct || 0) / 100; return { base, w, o, rate: (base + w + o) / Math.max(1e-9, +a.per || 1) }; };
  const paint = () => {
    const r = calc();
    modal(`<h2>Rate analysis · <span class="code" style="font-size:15px">${esc(item.code)}</span></h2><p class="muted" style="margin:4px 0 14px">${esc(item.description)}</p>
      <div class="row" style="margin-bottom:10px"><span>Analysis for</span><input class="input" style="width:90px" type="number" data-a="per" value="${a.per}"><span>${esc(item.unit)}</span></div>
      <table class="table"><thead><tr><th style="width:110px">Type</th><th>Description</th><th style="width:70px">Unit</th><th class="num" style="width:100px">Quantity</th><th class="num" style="width:110px">Rate (₹)</th><th class="num" style="width:110px">Amount</th><th></th></tr></thead><tbody>
      ${a.components.map((c, i) => `<tr><td><select class="input" data-c="${i}" data-f="type" style="height:32px">${["material", "labour", "machinery"].map((t) => `<option ${t === c.type ? "selected" : ""}>${t}</option>`).join("")}</select></td>
        <td><input class="input" style="height:32px" data-c="${i}" data-f="desc" value="${esc(c.desc)}"></td><td><input class="input" style="height:32px" data-c="${i}" data-f="unit" value="${esc(c.unit)}"></td>
        <td class="num"><input class="cell" data-c="${i}" data-f="qty" value="${c.qty}"></td><td class="num"><input class="cell" data-c="${i}" data-f="rate" value="${c.rate}"></td>
        <td class="num">${inr((+c.qty || 0) * (+c.rate || 0))}</td><td><button class="btn-link" data-rm="${i}" style="color:var(--dim)">✕</button></td></tr>`).join("")}
      </tbody></table><button class="btn-link" id="addc" style="margin-top:8px">+ Add row</button>
      <div style="margin-top:14px;max-width:360px;margin-left:auto">
        <div class="sum-row"><span>Materials + labour + machinery</span><span class="num">${inr(r.base)}</span></div>
        <div class="sum-row"><span>Water charges <input class="cell" style="width:56px" data-a="water_pct" value="${a.water_pct}">%</span><span class="num">${inr(r.w)}</span></div>
        <div class="sum-row"><span>Overheads & profit <input class="cell" style="width:56px" data-a="overhead_pct" value="${a.overhead_pct}">%</span><span class="num">${inr(r.o)}</span></div>
        <div class="sum-row total"><span>Rate per ${esc(item.unit)}</span><span class="num">${inr(r.rate)}</span></div></div>
      <div class="row" style="justify-content:flex-end;margin-top:18px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Save rate ${inr(r.rate)}</button></div>`, true);
    $$("[data-c]").forEach((el) => (el.onchange = () => { a.components[+el.dataset.c][el.dataset.f] = el.dataset.f === "qty" || el.dataset.f === "rate" ? +el.value : el.value; paint(); }));
    $$("[data-a]").forEach((el) => (el.onchange = () => { a[el.dataset.a] = +el.value; paint(); }));
    $$("[data-rm]").forEach((b) => (b.onclick = () => { a.components.splice(+b.dataset.rm, 1); paint(); }));
    $("#addc").onclick = () => { a.components.push({ type: "material", desc: "", unit: "", qty: 0, rate: 0 }); paint(); };
    $("#cx").onclick = closeModal;
    $("#sv").onclick = async () => { await api(`/api/sor/${encodeURIComponent(item.code)}${item.schedule_id ? `?schedule_id=${encodeURIComponent(item.schedule_id)}` : schedQ() ? "?" + schedQ().slice(1) : ""}`, { method: "PUT", json: { analysis: a } }); closeModal(); toast(`Rate ${item.code} set from analysis`); after && after(item.code); };
  };
  paint();
}

// ------------------------------------------------------------------ PROJECT WORKSPACE
const WS = { pid: null, P: null, step: "drawings", sheet: 0, layers: { rooms: true, walls: true, openings: true }, hl: new Set(), zoom: null, qf: "" };
const STEPS = [["drawings", "Drawings"], ["quantities", "Quantities"], ["rates", "PWD rates"], ["estimate", "Estimate"]];
const locked = () => WS.P?.status === "confirmed";

async function renderProject(pid, step) {
  if (WS.pid !== pid || !WS.P) {
    WS.pid = pid; WS.hl = new Set(); WS.zoom = null;
    try { WS.P = await api(`/api/projects/${pid}`); } catch (e) { view.innerHTML = `<div class="wrap"><div class="card empty">${esc(e.message)}</div></div>`; return; }
    const fp = WS.P.sheets.findIndex((s) => s.kind === "floor_plan"); WS.sheet = fp >= 0 ? fp : 0;
  }
  WS.step = step || "drawings";
  await getScopeOpts().catch(() => null);
  view.innerHTML = `<div class="wrap" style="padding-top:28px"><div class="ws-head" id="head"></div><div id="lockbar"></div><div class="stepper" id="stepper"></div><div id="body"></div></div>`;
  paintHead(); paintStep();
}
function setP(P) { if (!P) return; WS.P = P; paintHead(); paintStep(); }
const patchP = (path, body, method = "PATCH") => safe(async () => setP(await api(`/api/projects/${WS.P.id}${path}`, { method, json: body })));
function paintHead() {
  const P = WS.P, st = STATUS[P.status] || ["Draft", ""], sm = P.summary;
  const dt = P.details || {};
  $("#head").innerHTML = `<div class="grow"><div class="row"><h1>${esc(P.name)}</h1><span class="badge ${st[1]}">${st[0]}</span><button class="btn-link" id="edp" style="font-size:13px">Edit details</button></div>
      ${dt.client || dt.building_type || dt.site_address ? `<div class="muted" style="margin-top:2px;font-size:13px">${[dt.building_type, dt.client, dt.site_address].filter(Boolean).map(esc).join(" · ")}</div>` : ""}
      <div style="margin-top:4px;font-size:13px"><span class="badge ${P.scope?.type === "property" && (P.scope?.categories || []).length >= 14 ? "" : "blue"}">Scope</span> ${esc(P.scope_text || "Entire property")}
        ${(P.estimate.out_of_scope || []).length ? `<span class="muted">· partial estimate (${P.estimate.out_of_scope.length} line(s) excluded by scope)</span>` : ""} <button class="btn-link" id="chsc" style="font-size:13px">Change scope</button></div>
      <div class="muted" style="margin-top:4px">${sm.floor_plans} floor plan(s) · ${sm.sections} section/elevation · ${sm.structural} structural sheet(s) · ${P.params.floors} floor(s) · ${num(sm.built_up_area, 1)} m² built-up</div>
      <div class="muted" style="margin-top:2px;font-size:13px">${esc(P.rate_source?.location_text || "Location not specified")} · ${P.rate_source?.schedule ? `Rates: ${esc(P.rate_source.schedule.label)}` : `<span style="color:var(--warn)">No rate schedule applied</span>`}</div></div>
    <div class="ws-total"><div class="l">Construction cost (excl. land)</div><div class="v">${inr(P.estimate.total)}</div>
      ${P.summary?.cost_range ? `<div class="muted" style="font-size:12.5px" title="${esc(P.summary.cost_range.note)}">likely ${inr(P.summary.cost_range.low)} – ${inr(P.summary.cost_range.high)} (±${Math.round(P.summary.cost_range.relative * 100)}%)</div>` : ""}
      ${P.land?.provided ? `<div class="muted" style="font-size:12.5px">With land: <b>${inr(P.land.total_with_land)}</b></div>` : ""}</div>`;
  const v = P.versions?.[P.versions.length - 1];
  $("#lockbar").innerHTML = locked() ? `<div class="notice ok-n"><span class="grow">Revision R${v?.no} confirmed by <b>${esc(v?.by)}</b> on ${esc((v?.t || "").replace("T", " ").slice(0, 16))}. The estimate is locked.</span><button class="btn btn-sm" id="reopen">Reopen for revision</button></div>` : "";
  $("#reopen") && ($("#reopen").onclick = () => { const by = prompt("Your name (recorded in the audit trail):", v?.by || ""); if (by !== null) patchP("/reopen", { by }, "POST"); });
  const rev = P.stats.review;
  $("#stepper").innerHTML = STEPS.map(([k, l], i) => `<button data-st="${k}" class="${WS.step === k ? "on" : ""}"><span class="n">${i + 1}</span>${l}${k === "rates" && rev ? ` <span class="badge warn">${rev}</span>` : ""}</button>`).join("");
  $$("#stepper [data-st]").forEach((b) => (b.onclick = () => (location.hash = `#/p/${P.id}/${b.dataset.st}`)));
  $("#edp").onclick = editDetailsDialog;
  $("#chsc").onclick = scopeDialog;
  if (!P.sheets.length) $("#stepper").innerHTML = "";
}
function paintStep() {
  if (!WS.P.sheets.length) return stepUpload();
  ({ drawings: stepDrawings, quantities: stepQuantities, rates: stepRates, estimate: stepEstimate }[WS.step] || stepDrawings)();
  if (locked()) $$("#body input, #body select, #body textarea").forEach((el) => { if (!el.closest(".no-lock")) el.disabled = true; });
}
const nextBtn = (to, label) => `<div class="row" style="justify-content:flex-end;margin-top:18px"><a class="btn btn-dark" href="#/p/${WS.P.id}/${to}">${label} →</a></div>`;
const basisBadge = (b, cls) => {
  cls = cls || (!b || b === "drawing" ? "measured" : b.startsWith("assumed") ? "assumed" : b.includes("assumed") ? "partly assumed" : "measured");
  return cls === "assumed" ? `<span class="badge warn" title="${esc(b)}">assumed</span>` : cls === "partly assumed" ? `<span class="badge" title="${esc(b)}">partly assumed</span>`
    : cls === "user input" ? `<span class="badge blue" title="${esc(b)}">user input</span>` : (b && b !== "drawing" ? `<span class="badge blue" title="${esc(b)}">${esc(b.length > 40 ? b.slice(0, 40) + "…" : b)}</span>` : "");
};
function qualityBanner(P) {
  const c = P.stats?.completeness, ch = P.checks || [], asm = P.assumptions || [];
  const lv = { ERROR: "#c0392b", CONFLICT: "#c0392b", WARNING: "#b7791f", INFO: "#2b6cb0" };
  const ss = P.stats?.status_summary;
  let h = ss ? `<div class="notice ${ss.status === "COMPLETE" ? "info" : ""}" style="display:block"><b>${esc(ss.status)}</b> — ${esc(ss.headline.replace(/^PRELIMINARY estimate — /, ""))}
      <div style="font-size:12.5px;margin-top:6px">Quantities: ${Object.entries(ss.quantity).filter(([, v]) => v.lines).map(([k, v]) => `<span title="${esc(v.meaning)}">${esc(k)} ${v.lines}</span>`).join(" · ")}
      &nbsp;|&nbsp; Rates (lines in total): ${Object.entries(ss.rate).filter(([, v]) => v.lines).map(([k, v]) => `<span title="${esc(v.meaning)}">${esc(k)} ${v.lines}</span>`).join(" · ")}</div>
      <div class="dim" style="font-size:12px;margin-top:4px">${esc(ss.note)}</div></div>`
    : `<div class="notice" style="display:block"><b>Price completeness: ${esc(c?.text || "")}</b></div>`;
  const ec = P.stats?.estimate_confidence, stq = P.structural;
  if (ec) h += `<div class="card pad" style="margin-bottom:12px"><b>Estimate confidence: ${esc(ec.label)}</b>${ec.reasons.map((r) => `<div style="font-size:12.5px">• ${esc(r)}</div>`).join("")}<div class="muted" style="font-size:12px;margin-top:4px">${esc(ec.calibration)}</div>
    ${stq ? `<div style="font-size:12.5px;margin-top:6px"><b>Structural:</b> ${esc(stq.status)}${(stq.missing || []).map((m) => `<div>• ${esc(m)}</div>`).join("")}</div>` : ""}
    ${(P.sheets || []).filter((s) => s.areas && s.kind === "floor_plan").map((s) => { const A = s.areas; return `<div style="font-size:12.5px;margin-top:6px"><b>${esc(s.file || "")} areas</b> (scale: ${esc(A.calibration.basis)} — ${esc(A.calibration.status)}): carpet ${num(A.carpet_area.value_m2)} m² · common ${num(A.common_area.value_m2)} m² · plinth / built-up ${num(A.plinth_area.value_m2)} m² · gross floor ${A.gross_floor_area.value_m2 == null ? esc(A.gross_floor_area.note || "unresolved") : num(A.gross_floor_area.value_m2) + " m²"}</div>`; }).join("")}</div>`;
  if (ch.length) h += `<div class="card pad" style="margin-bottom:12px"><b>Checks</b>${ch.map((x) => `<div style="font-size:12.5px;margin-top:4px"><span style="color:${lv[x.level] || "inherit"};font-weight:600">${esc(x.level)} · ${esc(x.code)}</span> ${esc(x.message)}</div>`).join("")}</div>`;
  if (asm.length) h += `<details class="card pad" style="margin-bottom:12px"><summary><b>${asm.length} assumption(s) / missing inputs</b></summary>${asm.map((a) => `<div style="font-size:12.5px;margin-top:4px"><span class="mono">${esc(a.assumption_id)}</span> ${esc(a.description)} — <b>${esc(a.classification)}</b>${a.value != null ? ` (${esc(String(a.value))} ${esc(a.unit || "")})` : ""}${a.impact_on_cost ? ` · affects ₹${num(a.impact_on_cost, 0)}` : ""}</div>`).join("")}</details>`;
  return h;
}
const reviewDot = (lv) => lv ? `<span title="${lv === "green" ? "drawing-derived" : lv === "yellow" ? "derived / assumption involved" : "missing / review required"}" style="display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;background:${lv === "green" ? "#2f855a" : lv === "yellow" ? "#d69e2e" : "#c53030"}"></span>` : "";
function gapsBanner(P) {
  const ex = P.estimate.excluded || [], ot = P.other_elements || [], os_ = P.estimate.out_of_scope || [];
  let h = "";
  if (os_.length) h += `<div class="notice info" style="display:block"><b>${os_.length} line(s) are outside the selected scope and NOT in the total</b> (${esc(P.scope_text || "")}). Change the scope to include them.
    <div style="font-size:12.5px;margin-top:6px">${os_.map((x) => `${esc(x.description.slice(0, 60))} — ${num(x.qty)} ${esc(x.unit)}`).join("<br>")}</div></div>`;
  if (ex.length) h += `<div class="notice" style="display:block"><b>${ex.length} item(s) are NOT included in the construction cost</b> — they have a quantity but no usable rate in the selected schedule (or a suggested rate awaiting confirmation). The total is incomplete by these items.
    <div style="font-size:12.5px;margin-top:6px">${ex.map((x) => `${esc(x.description.slice(0, 70))} — ${num(x.qty)} ${esc(x.unit)} <span class="dim">(${esc(x.reason.slice(0, 90))})</span>`).join("<br>")}</div></div>`;
  if (ot.length) h += `<div class="notice info" style="display:block"><b>${ot.length} other construction element(s) identified in the drawings but not quantified</b> — enter them with “Add item” if they are part of the work.
    <div style="font-size:12.5px;margin-top:6px">${ot.map((o) => `${esc(o.element)} <span class="dim">(${esc((o.sheets || []).join("; ").slice(0, 80))})</span>`).join(" · ")}</div></div>`;
  return h;
}

// ---------- Step 0: project without drawings yet
function stepUpload() {
  const P = WS.P, d = P.details || {};
  $("#body").innerHTML = `<div class="card pad" style="margin-bottom:14px"><b>Project details</b>
      <div class="muted" style="font-size:13px;margin-top:6px">${[["Client / department", d.client], ["Building type", d.building_type], ["Site address", d.site_address], ["Location", P.rate_source?.location_text], ["Description", d.description]]
        .map(([k, v]) => `<div><span class="dim">${k}:</span> ${esc(v || "—")}</div>`).join("")}</div></div>
    <div class="upload"><div class="drop" id="drop"><div class="ic">↑</div><b>Upload this project's drawings</b><p>Architectural & structural sheets · PDF (multi-page), DWG, DXF, PNG, JPG or scans · you can add more later</p>
      <input type="file" id="fi" multiple hidden accept=".pdf,.dwg,.dxf,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp"></div><div class="files" id="fl"></div>
      <button class="btn btn-dark hidden" id="up" style="width:100%;margin-top:14px;height:44px">Upload and analyse</button></div>`;
  let files = [];
  const drop = $("#drop"), fi = $("#fi");
  const paint = () => {
    $("#fl").innerHTML = files.map((f, i) => `<div class="file"><span class="ext">${esc(f.name.split(".").pop().toUpperCase())}</span><span class="grow">${esc(f.name)}</span><span class="dim">${Math.ceil(f.size / 1024)} KB</span><button class="btn-link" data-rm="${i}" style="color:var(--muted)">Remove</button></div>`).join("");
    $$("[data-rm]").forEach((b) => (b.onclick = () => { files.splice(+b.dataset.rm, 1); paint(); }));
    $("#up").classList.toggle("hidden", !files.length);
  };
  drop.onclick = () => fi.click();
  fi.onchange = () => { files.push(...fi.files); fi.value = ""; paint(); };
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); files.push(...e.dataTransfer.files); paint(); };
  $("#up").onclick = async () => {
    const fd = new FormData(); files.forEach((f) => fd.append("files", f));
    const done = loading(`Analysing ${files.length} drawing(s)`);
    await safe(async () => { const Q = await api(`/api/projects/${P.id}/files`, { method: "POST", body: fd }); WS.sheet = Math.max(0, Q.sheets.findIndex((x) => x.kind === "floor_plan")); setP(Q); (Q.upload_skipped || []).forEach((k) => toast(`${k.file}: ${k.reason}`, true)); });
    done();
  };
}
async function scopeDialog() {
  const P = WS.P;
  if (locked()) return toast("Reopen the estimate to change its scope", true);
  modal(`<h2>Estimation scope</h2><p class="muted" style="margin:6px 0 12px">Changes what the total covers. Quantities are not recalculated from scratch and your edits are kept.</p>
    <div id="scf"></div><div class="row" style="justify-content:flex-end;margin-top:18px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Apply scope</button></div>`, true);
  const scf = $("#scf"), bt = P.details?.building_type || "";
  scf.innerHTML = await scopeFields(P.scope || {}, bt); bindScopeFields(scf, bt);
  $("#cx").onclick = closeModal;
  $("#sv").onclick = () => safe(async () => {
    const sc = readScope(scf);
    if (!sc.categories.length) return toast("Select at least one type of work", true);
    const Q = await api(`/api/projects/${P.id}`, { method: "PATCH", json: { scope: sc } });
    closeModal(); setP(Q); toast("Scope applied — totals recalculated");
  });
}
function editDetailsDialog() {
  const P = WS.P;
  modal(`<h2>Project details</h2>${detailsFields(P)}<div class="row" style="justify-content:flex-end;margin-top:18px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Save</button></div>`, true);
  $("#cx").onclick = closeModal;
  $("#sv").onclick = () => safe(async () => {
    const name = $("#pn").value.trim(); if (!name) return toast("Enter a project name", true);
    const Q = await api(`/api/projects/${P.id}`, { method: "PATCH", json: { name, details: readDetails() } });
    closeModal(); setP(Q); toast("Project details saved");
  });
}

// ---------- Step 1: drawings
function sheetLabel(s) { return `${esc(s.file)}${s.sheet && s.sheet !== "Image" && s.sheet !== "-" ? " · " + esc(s.sheet) : ""}`; }
function stepDrawings() {
  const P = WS.P, S = P.sheets[WS.sheet] || P.sheets[0];
  const isPlan = S.kind === "floor_plan";
  $("#body").innerHTML = `
    <div class="sheet-list">${P.sheets.map((s, i) => `<button class="sheet-chip ${i === WS.sheet ? "on" : ""} ${s.enabled === false ? "off" : ""}" data-sh="${i}"><span>${sheetLabel(s)}</span><small>${s.user_label ? esc(s.user_label) + " · " : ""}${KIND[s.kind] || s.kind}${s.floor?.label ? " · " + esc(s.floor.label) : ""}</small></button>`).join("")}
      <label class="sheet-chip add">+ Add drawings<input type="file" id="addf" multiple hidden accept=".pdf,.dwg,.dxf,.png,.jpg,.jpeg"></label></div>
    ${S.error ? `<div class="notice">This file could not be read: ${esc(S.error)}</div>` : ""}
    <div class="draw-grid">
      <div class="viewer-box">
        <div class="vtools">${isPlan ? `<button class="t ${WS.layers.rooms ? "on" : ""}" data-ly="rooms"><i style="background:#8b7cf6"></i>Rooms</button>
          <button class="t ${WS.layers.walls ? "on" : ""}" data-ly="walls"><i style="background:#c9364a"></i>Walls</button>
          <button class="t ${WS.layers.openings ? "on" : ""}" data-ly="openings"><i style="background:#f2a541"></i>Doors & windows</button>
          ${WS.hl.size ? `<button class="t on" id="clr">Clear highlight</button>` : ""}` : `<span class="muted" style="font-size:12.5px">${KIND[S.kind] || "Reference"} sheet — read for text, levels and schedules</span>`}
          <span class="grow"></span>${isPlan ? `<button class="t" id="cal">Calibrate scale</button>` : ""}
          <button class="t" id="zo" title="Zoom out">−</button><button class="t" id="zf">Fit</button><button class="t" id="zi" title="Zoom in">+</button></div>
        <div class="viewer" id="vw"><div class="stage" id="stage"></div></div>
      </div>
      <div class="side">${sidePanel(S)}</div>
    </div>${nextBtn("quantities", "Review quantities")}`;
  $$("[data-sh]").forEach((b) => (b.onclick = () => { WS.sheet = +b.dataset.sh; WS.zoom = null; stepDrawings(); }));
  $$("[data-ly]").forEach((b) => (b.onclick = () => { WS.layers[b.dataset.ly] = !WS.layers[b.dataset.ly]; stepDrawings(); }));
  $$("[data-r]").forEach((el) => (el.onclick = () => roomDialog(S, el.dataset.r)));
  $("#clr") && ($("#clr").onclick = () => { WS.hl.clear(); stepDrawings(); });
  $("#addf").onchange = async (e) => {
    if (locked()) return toast("Reopen the estimate to add drawings", true);
    const fd = new FormData(); [...e.target.files].forEach((f) => fd.append("files", f));
    const done = loading("Analysing new drawings");
    await safe(async () => { const Q = await api(`/api/projects/${P.id}/files`, { method: "POST", body: fd }); setP(Q); (Q.upload_skipped || []).forEach((k) => toast(`${k.file}: ${k.reason}`, true)); });
    done();
  };
  bindSide(S);
  if (!S.error) mountViewer(S);
}
function sidePanel(S) {
  const m = S.metrics || {}, fl = S.floor || {};
  const kindSel = `<div class="params" style="margin-top:12px"><div><label class="lbl">Sheet type</label><select class="input" id="kind">${Object.entries(KIND).map(([k, l]) => `<option value="${k}" ${S.kind === k ? "selected" : ""} ${k === "floor_plan" && !(S.rooms || []).length ? "disabled" : ""}>${l}</option>`).join("")}</select></div>
    <div><label class="lbl">Use in estimate</label><select class="input" id="en"><option value="1" ${S.enabled !== false ? "selected" : ""}>Yes</option><option value="0" ${S.enabled === false ? "selected" : ""}>No</option></select></div></div>
    <div class="params" style="margin-top:10px"><div style="grid-column:1/-1"><label class="lbl">Label (optional)</label><input class="input" id="slab" list="slabels" value="${esc(S.user_label || "")}" placeholder="e.g. Bedroom, First floor, Electrical layout — leave empty if unsure">
      <datalist id="slabels">${(SCOPE_OPTS?.labels || []).map((l) => `<option value="${esc(l)}">`).join("")}</datalist></div></div>
    <div class="row" style="margin-top:10px"><span class="grow"></span><button class="btn btn-sm" id="rmf" title="Remove this drawing file and everything read from it">Remove drawing</button></div>`;
  let html = `<div class="card pad" style="padding:16px"><div class="row"><b class="grow">${KIND[S.kind] || "Sheet"}</b>${S.confidence != null ? `<span class="badge ${S.confidence >= 0.8 ? "ok" : "warn"}">${Math.round(S.confidence * 100)}% confidence</span>` : ""}</div>
    <div class="muted" style="font-size:12.5px;margin-top:4px">${esc(S.method || "")}</div>
    ${(S.warnings || []).map((w) => `<div class="notice" style="margin:10px 0 0;font-size:12.5px">${esc(w)}</div>`).join("")}
    ${(S.scale?.confidence ?? 1) < 0.7 ? `<div class="notice" style="margin:10px 0 0;font-size:12.5px">Scale is an estimate (${esc(S.scale.method)}). Use <b>Calibrate scale</b> with one known dimension.</div>` : ""}${kindSel}`;
  if (S.kind === "floor_plan") {
    html += `<div class="params" style="margin-top:10px"><div><label class="lbl">Floor</label><select class="input" id="flr">${FLOORS.map(([l, v]) => `<option value="${l}" ${fl.label === l ? "selected" : ""}>${l}</option>`).join("")}<option value="" ${!fl.label ? "selected" : ""}>Not set</option></select></div>
      <div><label class="lbl">Repeats for (floors)</label><input class="input" id="rep" type="number" min="1" max="20" value="${fl.repeat || 1}"></div></div>
      <div class="stats" style="margin-top:12px"><div><span>Plinth area</span><b>${num(m.plinth_area)} m²</b></div><div><span>Carpet area</span><b>${num(m.carpet_area)} m²</b></div>
      <div><span>External walls</span><b>${num(m.L_ext)} m</b></div><div><span>Internal walls</span><b>${num(m.L_int)} m</b></div>
      <div><span>Doors</span><b>${m.n_doors ?? "—"}</b></div><div><span>Windows</span><b>${m.n_windows ?? "—"}</b></div></div>
      <div class="muted" style="font-size:12px;margin-top:8px">Scale: ${esc(S.scale?.method || "—")} · ${S.openings.filter((o) => o.tag).length}/${S.openings.length} openings matched to D/W marks</div>
      ${(() => { const cal = S.areas?.calibration || {}; return cal.status && cal.status !== "MEASURED" ? `<div class="notice" style="margin:10px 0 0;font-size:12.5px;display:block"><b>Scale ${esc(cal.status)}</b> — ${esc(cal.basis || "")}. Quantities from this drawing are marked UNVERIFIED SCALE.
        Use <b>Calibrate scale</b> with a known dimension${cal.status !== "USER-CONFIRMED" ? `, or <button class="btn-link" id="scok">accept this scale as an assumption</button>` : ` · <button class="btn-link" id="scno">withdraw acceptance</button>`}.</div>` : ""; })()}
      <div class="card pad" style="padding:12px;margin-top:10px"><b style="font-size:13px">Doors & windows — counts by source</b>
        <div style="font-size:12.5px;margin-top:4px">${["door", "window"].map((k) => { const geo = S.openings.filter((o) => o.kind === k && o.source !== "detector").length, det = S.detector_counts?.[k], fused = S.openings.filter((o) => o.kind === k).length;
          return `${k === "door" ? "Doors" : "Windows"}: drawing geometry ${geo}${det != null ? ` · detector ${det}` : ""} · combined ${fused}${(S.opening_confirmed || {})[k] != null ? ` · <b>confirmed ${S.opening_confirmed[k]}</b>` : ""}`; }).join("<br>")}</div>
        <div class="params" style="margin-top:8px"><div><label class="lbl">Confirmed doors</label><input class="input" id="cfd" type="number" min="0" value="${S.opening_confirmed?.door ?? ""}" placeholder="count on drawing"></div>
          <div><label class="lbl">Confirmed windows</label><input class="input" id="cfw" type="number" min="0" value="${S.opening_confirmed?.window ?? ""}" placeholder="count on drawing"></div></div>
        <div class="row" style="margin-top:6px"><span class="dim grow" style="font-size:12px">A confirmed count replaces the automatic count in every quantity; leave empty to use the drawing.</span><button class="btn btn-sm" id="cfs">Save counts</button></div></div>`;
  }
  html += `</div>`;
  const info = readInfo(S);
  if (info) html += `<div class="card pad" style="padding:16px"><b>Read from this sheet</b>${info}</div>`;
  if (S.kind === "floor_plan") {
    html += `<div class="card pad" style="padding:16px"><div class="row" style="margin-bottom:4px"><b class="grow">Rooms</b><span class="dim">${S.rooms.length}</span></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:6px">Click a room to verify its name and type.</div>
      <div class="list">${S.rooms.map((r) => `<div class="li" data-r="${r.id}"><span class="sw" style="background:${TYPE_COLORS[r.type] || "#999"}"></span>
        <div><div class="nm">${esc(r.name)}</div><div class="ty">${esc(r.type)}${r.type_conf < 0.6 ? ` · <span style="color:var(--warn)">verify</span>` : ""}</div></div><span class="ar">${num(r.area)} m²</span></div>`).join("") || `<div class="dim" style="padding:10px 0">No rooms found.</div>`}</div></div>`;
  }
  return html;
}
function readInfo(S) {
  const parts = [], L = S.levels || {}, st = S.structural || {}, sc = S.schedule || {};
  const lv = [["Floor height", L.floor_height, "m"], ["Plinth height", L.plinth_height, "m"], ["Foundation depth", L.foundation_depth, "m"], ["Slab thickness", L.slab_thickness, "m"],
    ["Sill height", L.sill_height, "m"], ["Lintel height", L.lintel_height, "m"], ["Parapet", L.parapet_height, "m"], ["Floors (from levels)", L.floors_from_levels, ""]].filter((x) => x[1] != null);
  if (lv.length) parts.push(`<div class="info-h">Levels & heights</div><div class="kv">${lv.map(([k, v, u]) => `<span>${k}</span><b>${num(v, 3)} ${u}</b>`).join("")}</div>`);
  const sk = Object.entries(sc);
  if (sk.length) parts.push(`<div class="info-h">Door & window schedule</div><table class="mini">${sk.map(([k, v]) => `<tr><td class="code">${esc(k)}</td><td>${num(v.w * 1000, 0)} × ${num(v.h * 1000, 0)}</td><td class="num">${v.count ?? "—"} nos</td></tr>`).join("")}</table>`);
  if (st.footings?.length) parts.push(`<div class="info-h">Footing schedule</div><table class="mini">${st.footings.map((f) => `<tr><td class="code">${esc(f.mark)}</td><td>${num(f.L * 1000, 0)}×${num(f.B * 1000, 0)}×${num(f.D * 1000, 0)}${f.bar ? ` · Y${f.bar[0]}@${f.bar[1]}` : ""}</td><td class="num">${f.count ?? "—"} nos</td></tr>`).join("")}</table>`);
  if (st.columns?.length) parts.push(`<div class="info-h">Column schedule</div><table class="mini">${st.columns.map((c) => `<tr><td class="code">${esc(c.mark)}</td><td>${num(c.b * 1000, 0)}×${num(c.d * 1000, 0)} · ${(c.main || []).map(([n, d]) => `${n}-Y${d}`).join(" + ")}${c.ties ? ` · ties Y${c.ties[0]}@${c.ties[1]}` : ""}</td><td class="num">${c.count ?? "—"} nos</td></tr>`).join("")}</table>`);
  if (st.beams?.length) parts.push(`<div class="info-h">Beam schedule</div><table class="mini">${st.beams.map((b) => `<tr><td class="code">${esc(b.mark)}</td><td>${num(b.b * 1000, 0)}×${num(b.d * 1000, 0)} · top ${(b.top || []).map(([n, d]) => `${n}-Y${d}`).join("")} bot ${(b.bot || []).map(([n, d]) => `${n}-Y${d}`).join("")}</td><td class="num">${b.length ? num(b.length, 1) + " m" : "—"}</td></tr>`).join("")}</table>`);
  const sl = (st.slabs || []).filter((x) => x.main);
  if (sl.length) parts.push(`<div class="info-h">Slab</div><table class="mini">${sl.map((x) => `<tr><td>${x.thk ? num(x.thk * 1000, 0) + " thick" : ""}</td><td>main Y${x.main[0]}@${x.main[1]}${x.dist ? `, dist Y${x.dist[0]}@${x.dist[1]}` : ""}</td></tr>`).join("")}</table>`);
  return parts.join("");
}
function bindSide(S) {
  const P = WS.P, idx = WS.sheet;
  $("#kind") && ($("#kind").onchange = (e) => patchP(`/sheets/${idx}`, { kind: e.target.value }));
  $("#en") && ($("#en").onchange = (e) => patchP(`/sheets/${idx}`, { enabled: e.target.value === "1" }));
  $("#slab") && ($("#slab").onchange = (e) => patchP(`/sheets/${idx}`, { label: e.target.value }));
  $("#scok") && ($("#scok").onclick = () => patchP(`/sheets/${idx}`, { scale_confirmed: true }));
  $("#scno") && ($("#scno").onclick = () => patchP(`/sheets/${idx}`, { scale_confirmed: false }));
  $("#cfs") && ($("#cfs").onclick = () => patchP(`/sheets/${idx}`, { opening_confirmed: { door: $("#cfd").value === "" ? null : +$("#cfd").value, window: $("#cfw").value === "" ? null : +$("#cfw").value } }));
  $("#rmf") && ($("#rmf").onclick = () => {
    const n = P.sheets.filter((x) => x.file === S.file).length;
    if (!confirm(`Remove "${S.file}" (${n} sheet(s)) from this project? Quantities read from it are removed and the estimate is recalculated. Your edits to items are kept.`)) return;
    safe(async () => { const Q = await api(`/api/projects/${P.id}/files/${encodeURIComponent(S.file)}`, { method: "DELETE" }); WS.sheet = 0; setP(Q); toast("Drawing removed"); });
  });
  const setFloor = () => { const l = $("#flr").value; const lv = (FLOORS.find(([x]) => x === l) || [l, 0])[1]; patchP(`/sheets/${idx}`, { floor: l ? { label: l, level: lv, repeat: Math.max(1, +$("#rep").value || 1) } : null }); };
  $("#flr") && ($("#flr").onchange = setFloor);
  $("#rep") && ($("#rep").onchange = setFloor);
}
const pts = (poly) => poly.map((p) => p.join(",")).join(" ");
function mountViewer(S) {
  const vw = $("#vw"), stage = $("#stage"), [, , bw, bh] = S.bbox || [0, 0, 10, 10];
  const iw = S.preview_size?.[0] || 1000, ih = S.preview_size?.[1] || (1000 * bh) / bw, L = WS.layers, hl = WS.hl;
  let svg = "";
  if (S.kind === "floor_plan") {
    const fs = Math.max(0.2, Math.min(0.36, bw / 48));
    svg = `<svg viewBox="0 0 ${bw} ${bh}" preserveAspectRatio="none">`;
    if (L.rooms) for (const r of S.rooms) {
      const c = hl.has(r.id) ? "#2f5bea" : TYPE_COLORS[r.type] || "#999";
      svg += `<polygon data-room="${r.id}" points="${pts(r.poly)}" fill="${c}" fill-opacity="${hl.has(r.id) ? 0.45 : 0.16}" stroke="${c}" stroke-width="0.03" style="cursor:pointer"/>`;
    }
    if (L.walls) {
      const path = (ws) => ws.map((w) => "M" + w.poly.map((p) => p.join(",")).join("L") + "Z").join("");
      const plain = S.walls.filter((w) => !hl.has(w.id)), lit = S.walls.filter((w) => hl.has(w.id));
      svg += `<path d="${path(plain.filter((w) => w.ext))}" fill="#c9364a" fill-opacity=".45" fill-rule="evenodd"/><path d="${path(plain.filter((w) => !w.ext))}" fill="#8b7cf6" fill-opacity=".45" fill-rule="evenodd"/>`;
      if (lit.length) svg += `<path d="${path(lit)}" fill="#2f5bea" fill-opacity=".9" fill-rule="evenodd"/>`;
    }
    if (L.openings) for (const o of S.openings) {
      const r = Math.max(0.16, o.w / 2), c = hl.has(o.id) ? "#2f5bea" : o.kind === "door" ? "#f2a541" : "#2fa6c9";
      svg += o.kind === "door" ? `<circle cx="${o.x}" cy="${o.y}" r="${r}" fill="${c}" fill-opacity=".15" stroke="${c}" stroke-width="0.04"><title>${esc(o.tag || "door")} · ${o.w} m · ${esc(o.type || "")} · ${esc(o.source || "")} ${o.confidence != null ? "(" + Number(o.confidence).toFixed(2) + ")" : ""}</title></circle>`
        : `<rect x="${o.x - r}" y="${o.y - 0.14}" width="${2 * r}" height="0.28" rx="0.06" fill="${c}" fill-opacity=".25" stroke="${c}" stroke-width="0.04"><title>${esc(o.tag || "window")} · ${o.w} m · ${esc(o.type || "")} · ${esc(o.source || "")} ${o.confidence != null ? "(" + Number(o.confidence).toFixed(2) + ")" : ""}</title></rect>`;
    }
    if (L.rooms) for (const r of S.rooms) svg += `<g pointer-events="none" text-anchor="middle" font-family="Inter"><text x="${r.cx}" y="${r.cy}" font-size="${fs}" font-weight="600" fill="#111318" stroke="#fff" stroke-width="${fs * 0.25}" paint-order="stroke">${esc(r.name)}</text>
      <text x="${r.cx}" y="${r.cy + fs * 1.2}" font-size="${fs * 0.8}" fill="#62677a" stroke="#fff" stroke-width="${fs * 0.22}" paint-order="stroke">${num(r.area)} m²</text></g>`;
    svg += `<g id="calg"></g></svg>`;
  }
  stage.innerHTML = `${S.preview ? `<img src="${S.preview}" draggable="false" alt="">` : ""}${svg}`;
  // fixed, fit-to-frame view. Zoom only with the buttons; scrollbars appear when zoomed in.
  const fitW = () => Math.min(vw.clientWidth - 24, ((vw.clientHeight - 24) * iw) / ih);
  const apply = () => { const w = WS.zoom ? fitW() * WS.zoom : fitW(); stage.style.width = w + "px"; stage.style.height = (w * ih) / iw + "px"; vw.classList.toggle("zoomed", (WS.zoom || 1) > 1.01); };
  apply();
  $("#zi").onclick = () => { WS.zoom = Math.min(6, (WS.zoom || 1) * 1.4); apply(); };
  $("#zo").onclick = () => { WS.zoom = Math.max(1, (WS.zoom || 1) / 1.4); apply(); };
  $("#zf").onclick = () => { WS.zoom = null; apply(); };
  if (S.kind !== "floor_plan") return;
  const svgEl = $("svg", stage);
  const world = (e) => { const p = svgEl.createSVGPoint(); p.x = e.clientX; p.y = e.clientY; const q = p.matrixTransform(svgEl.getScreenCTM().inverse()); return [q.x, q.y]; };
  let calib = null;
  svgEl.addEventListener("click", (e) => {
    if (calib) {
      calib.push(world(e));
      $("#calg").innerHTML = calib.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="0.1" fill="#2f5bea"/>`).join("") + (calib.length === 2 ? `<line x1="${calib[0][0]}" y1="${calib[0][1]}" x2="${calib[1][0]}" y2="${calib[1][1]}" stroke="#2f5bea" stroke-width="0.05"/>` : "");
      if (calib.length === 2) {
        const d = Math.hypot(calib[1][0] - calib[0][0], calib[1][1] - calib[0][1]); calib = null; vw.classList.remove("calib");
        setTimeout(async () => {
          const real = prompt(`Measured ${d.toFixed(2)} m on the drawing. Enter the actual length in metres:`, d.toFixed(2));
          if (!(+real > 0)) return ($("#calg").innerHTML = "");
          const done = loading("Recalculating with corrected scale");
          await patchP(`/sheets/${WS.sheet}`, { calib: { measured_m: d, real_m: +real } }); done(); toast("Scale corrected");
        }, 30);
      }
      return;
    }
    const rp = e.target.closest("[data-room]"); if (rp) roomDialog(S, rp.dataset.room);
  });
  svgEl.addEventListener("mousemove", (e) => {
    const rp = e.target.closest("[data-room]"); let tip = $("#tip");
    if (rp) {
      const r = S.rooms.find((x) => x.id === rp.dataset.room);
      if (!tip) { tip = document.createElement("div"); tip.id = "tip"; tip.className = "tip"; document.body.appendChild(tip); }
      tip.innerHTML = `<b>${esc(r.name)}</b><br>${esc(r.type)} · ${num(r.area)} m² · perimeter ${num(r.perimeter)} m`;
      tip.style.left = e.clientX + 14 + "px"; tip.style.top = e.clientY + 12 + "px";
    } else tip?.remove();
  });
  svgEl.addEventListener("mouseleave", () => $("#tip")?.remove());
  $("#cal").onclick = () => { if (locked()) return toast("Reopen the estimate to recalibrate", true); calib = []; vw.classList.add("calib"); toast("Click both ends of a known dimension"); };
}
function roomDialog(S, rid) {
  if (locked()) return toast("Reopen the estimate to edit rooms", true);
  const r = S.rooms.find((x) => x.id === rid);
  modal(`<h2>Verify room</h2><p class="muted" style="margin:6px 0 16px">${num(r.area)} m² · perimeter ${num(r.perimeter)} m. The room type decides flooring, wall tiling, waterproofing and fittings.</p>
    <div class="params"><div><label class="lbl">Name</label><input class="input" id="rn" value="${esc(r.name)}"></div>
    <div><label class="lbl">Type</label><select class="input" id="rt">${ROOM_TYPES.map((t) => `<option ${t === r.type ? "selected" : ""}>${t}</option>`).join("")}</select></div></div>
    <div class="row" style="justify-content:flex-end;margin-top:20px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Save</button></div>`);
  $("#cx").onclick = closeModal;
  $("#sv").onclick = async () => { closeModal(); await patchP(`/sheets/${WS.sheet}/rooms/${rid}`, { name: $("#rn").value, type: $("#rt").value }); toast("Room updated, quantities recalculated"); };
}

// ---------- Step 2: quantities
function groupRows(items, cols, rowFn) {
  let html = "", cur = null;
  for (const it of items) { if (it.category !== cur) { cur = it.category; html += `<tr class="group"><td colspan="${cols}">${esc(cur)}</td></tr>`; } html += rowFn(it); }
  return html;
}
function stepQuantities() {
  const P = WS.P, items = P.estimate.items.filter((i) => !WS.qf || (i.description + i.category).toLowerCase().includes(WS.qf.toLowerCase()));
  const validated = P.estimate.items.filter((i) => ["confirmed", "edited"].includes(i.status)).length;
  $("#body").innerHTML = `
    ${P.stats.assumed ? `<div class="notice">${P.stats.assumed} structural item(s) use assumed sizes because no structural drawings were found. Add the foundation, column and beam drawings to measure them, or check the quantities below.</div>` : ""}
    <div class="toolbar"><input class="input no-lock" id="qs" placeholder="Search items" value="${esc(WS.qf)}" style="max-width:300px"><span class="muted">${validated} of ${P.estimate.items.length} items validated</span><span class="grow"></span>
      ${locked() ? "" : `<button class="btn btn-sm" id="add">Add item</button><button class="btn btn-sm" id="okall">Validate all</button>`}</div>
    <div class="card"><table class="table"><thead><tr><th>Item</th><th>How it was measured</th><th class="num">Quantity</th><th>Unit</th><th>Validated</th></tr></thead><tbody>
    ${groupRows(items, 5, (it) => `<tr><td style="max-width:340px">${reviewDot(it.review_level)}<b style="font-weight:500">${esc(it.description)}</b>${it.confidence_label ? ` <span class="badge" title="${esc((it.confidence_reasons || []).join("; "))}">${esc(it.confidence_label)}</span>` : ""} ${basisBadge(it.basis, it.basis_class)}
        ${it.qty_status ? ` <span class="badge ${["MEASURED", "DERIVED", "USER-ENTERED"].includes(it.qty_status) ? "ok" : it.qty_status === "EXCLUDED" ? "" : "warn"}" title="${esc((it.exclusion || {}).reason || "")}">${esc(it.qty_status)}</span>` : ""}
        <div class="sub">${esc(it.trace || (it.drawing_refs || []).join("; "))}</div>${it.sources?.length && it.sources[0] !== "rooms" ? `<button class="btn-link" data-loc="${it.key}" style="font-size:12.5px">Show on drawing</button>` : ""}</td>
      <td class="muted" style="font-size:12.5px;max-width:340px">${esc(it.formula)}</td>
      <td class="num"><input class="cell ${it.qty !== it.qty_auto ? "changed" : ""}" data-q="${it.key}" value="${it.qty}">${it.qty !== it.qty_auto ? `<div class="sub">drawing ${num(it.qty_auto)} · <button class="btn-link" data-rs="${it.key}" style="font-size:12px">undo</button></div>` : ""}</td>
      <td>${esc(it.unit)}</td><td><input type="checkbox" data-ok="${it.key}" ${["confirmed", "edited"].includes(it.status) ? "checked" : ""}></td></tr>`)}
    </tbody></table></div>${nextBtn("rates", "Review PWD rates")}`;
  $("#qs").oninput = debounce((e) => { WS.qf = e.target.value; stepQuantities(); const q = $("#qs"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 250);
  bindItemEdits();
  $("#okall") && ($("#okall").onclick = async () => { await patchP("/validate-all", {}, "POST"); toast("All items validated"); });
  $("#add") && ($("#add").onclick = addItemDialog);
  $$("[data-loc]").forEach((b) => (b.onclick = () => {
    const it = P.estimate.items.find((x) => x.key === b.dataset.loc); WS.hl = new Set(it.sources || []);
    const si = P.sheets.findIndex((s) => [...(s.rooms || []), ...(s.walls || []), ...(s.openings || [])].some((e) => WS.hl.has(e.id)));
    if (si >= 0) WS.sheet = si; else toast("This item comes from schedules, not plan geometry");
    WS.zoom = null; location.hash = `#/p/${P.id}/drawings`;
  }));
}
function bindItemEdits() {
  const P = WS.P, patch = async (key, body, msg) => { await patchP(`/items/${key}`, body); if (msg) toast(msg); };
  $$("[data-q]").forEach((i) => (i.onchange = () => patch(i.dataset.q, { qty: +i.value }, "Quantity updated")));
  $$("[data-rs]").forEach((b) => (b.onclick = () => patch(b.dataset.rs, { reset: true })));
  $$("[data-ok]").forEach((c) => (c.onchange = () => patch(c.dataset.ok, { status: c.checked ? "confirmed" : null })));
  $$("[data-br]").forEach((i) => (i.onchange = () => patch(i.dataset.br, { rate: i.value === "" ? null : +i.value }, "Rate updated")));
  $$("[data-pick]").forEach((b) => (b.onclick = () => (locked() ? toast("Reopen the estimate to change rates", true) : ratePicker(P.estimate.items.find((x) => x.key === b.dataset.pick)))));
  $$("[data-web]").forEach((b) => (b.onclick = () => (locked() ? toast("Reopen the estimate to change rates", true) : webPrice(P.estimate.items.find((x) => x.key === b.dataset.web), patch))));
}
async function webPrice(it, patch) {
  modal(`<h2>Web price</h2><p class="muted">Searching current prices for “${esc(it.description.slice(0, 80))}” per ${esc(it.unit)}…</p>`);
  let r;
  try { r = await api("/api/rate-lookup?" + qs({ description: it.description, unit: it.unit })); } catch (e) { r = { enabled: true, ok: false, message: String(e) }; }
  if (!r.enabled || !r.ok) { modal(`<h2>Web price</h2><p>${esc(r.message || "No usable prices found for this item.")}</p><div class="row" style="justify-content:flex-end"><button class="btn" id="cx">Close</button></div>`); $("#cx").onclick = closeModal; return; }
  modal(`<h2>Web price</h2><p class="muted" style="margin:6px 0 12px">${esc(r.note)}</p>
    <div style="font-size:22px;font-weight:700">₹${esc(r.suggestion.toLocaleString("en-IN"))} <span class="muted" style="font-size:14px">per ${esc(r.unit)} (range ₹${esc(r.low)}–₹${esc(r.high)})</span></div>
    <ul style="font-size:12.5px;margin:12px 0">${r.sources.map((s) => `<li>₹${esc(s.value)} — <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a></li>`).join("")}</ul>
    <div class="params"><div><label class="lbl">Rate to apply (₹ per ${esc(r.unit)})</label><input class="input" id="wr" type="number" value="${r.suggestion}"></div></div>
    <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="ap">Apply rate</button></div>`);
  $("#cx").onclick = closeModal;
  $("#ap").onclick = async () => { closeModal(); await patch(it.key, { rate: +$("#wr").value }, "Rate applied"); };
}
function addItemDialog() {
  modal(`<h2>Add item</h2><p class="muted" style="margin:6px 0 16px">For work not shown on the drawings. A matching PWD item is suggested automatically.</p>
    <div class="params"><div style="grid-column:1/-1"><label class="lbl">Description</label><input class="input" id="cd" placeholder="e.g. Granite treads for staircase"></div>
    <div><label class="lbl">Quantity</label><input class="input" id="cq" type="number" value="1"></div><div><label class="lbl">Unit</label><select class="input" id="cu">${["sqm", "cum", "m", "kg", "each", "point", "litre"].map((u) => `<option>${u}</option>`).join("")}</select></div></div>
    <div class="row" style="justify-content:flex-end;margin-top:20px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Add</button></div>`);
  $("#cx").onclick = closeModal;
  $("#sv").onclick = async () => { if (!$("#cd").value) return; closeModal(); await patchP("/items", { description: $("#cd").value, qty: +$("#cq").value, unit: $("#cu").value }, "POST"); toast("Item added"); };
}

// ---------- Step 3: PWD rates
function stepRates() {
  const P = WS.P, items = P.estimate.items, flagged = items.filter((i) => ["review", "unmapped"].includes(i.status));
  $("#body").innerHTML = `${rateSourcePanel(P)}${qualityBanner(P)}${gapsBanner(P)}
    ${!P.rate_source?.schedule ? "" : flagged.length ? `<div class="notice">${flagged.length} item(s) have no confident PWD match. Select the applicable PWD item, build a rate by analysis, or enter a rate.</div>` : items.some((i) => i.map_method === "estimated") ? "" : `<div class="notice info">Every item is mapped to a PWD item. Click a PWD item to change it.</div>`}
    ${items.some((i) => i.map_method === "estimated") ? `<div class="notice">${items.filter((i) => i.map_method === "estimated").length} item(s) use an estimated average rate (marked <b>Estimated</b>). Edit the rate, select a PWD item, or use <b>Web price</b>.</div>` : ""}
    <div class="card"><table class="table"><thead><tr><th>Item</th><th>PWD item applied</th><th>Unit</th><th class="num">PWD rate (₹)</th><th>Match</th></tr></thead><tbody>
    ${groupRows(items, 5, (it) => {
      const fl = ["review", "unmapped"].includes(it.status);
      return `<tr class="${fl ? "flag" : ""}"><td style="max-width:320px">${esc(it.description)}</td>
        <td style="max-width:400px"><button class="btn-link" data-pick="${it.key}" style="text-align:left;color:inherit">${it.sor_code ? `<span class="code">${esc(it.sor_code)}</span> <span class="muted" style="font-size:13px">${esc((it.sor_desc || "").slice(0, 90))}…</span>` : `<span style="color:var(--bad)">Select PWD item</span>`}</button></td>
        <td>${esc(it.unit)}</td><td class="num"><input class="cell" data-br="${it.key}" value="${it.base_rate ?? ""}" placeholder="—"></td>
        <td>${it.map_method === "user" ? `<span class="badge blue">Selected</span>` : it.map_method === "estimated" ? `<span class="badge warn" title="${esc(it.derived?.basis || "")}">Estimated</span> <button class="btn-link" data-web="${it.key}" style="font-size:12px">Web price</button>` : fl ? `<span class="badge warn">Review</span> <button class="btn-link" data-web="${it.key}" style="font-size:12px">Web price</button>` : `<span class="badge ok">${Math.round((it.map_score || 0) * 100)}%</span>`}</td></tr>`;
    })}</tbody></table></div>${nextBtn("estimate", "View estimate")}`;
  bindItemEdits(); bindRateSource();
}
function ratePicker(it) {
  if (!WS.P.rate_source?.schedule) return toast("Select a rate schedule for this project first (Rate source → Change rate schedule)", true);
  modal(`<h2>Select PWD/SOR item</h2><div class="muted" style="font-size:12.5px">Searching only ${esc(WS.P.rate_source.schedule.label)}</div><p class="muted" style="margin:6px 0 12px">${esc(it.description)} · ${num(it.qty)} ${esc(it.unit)}</p>
    <input class="input" id="ps" placeholder="Search the rate library"><div id="pl" style="margin-top:6px"></div>
    <div class="row" style="margin-top:14px;border-top:1px solid var(--line);padding-top:14px"><span class="muted grow">Not in the SOR?</span><button class="btn btn-sm" id="build">Build rate by analysis</button></div>`);
  const paint = (c) => {
    $("#pl").innerHTML = c.map((o) => `<div class="opt" data-c="${esc(o.code)}"><div class="sc">${Math.round((o.score || 0) * 100)}%</div><div class="grow"><span class="code">${esc(o.code)}</span> · ${esc(o.unit)} · <b>₹${num(o.rate)}</b>${o.unit !== it.unit ? ` <span class="badge warn">different unit</span>` : ""}<div class="muted" style="font-size:12.5px;margin-top:2px">${esc(o.description)}</div></div></div>`).join("") || `<div class="dim" style="padding:12px 0">No matches</div>`;
    $$("[data-c]").forEach((d) => (d.onclick = async () => { closeModal(); await patchP(`/items/${it.key}`, { sor_code: d.dataset.c, rate: null, status: "confirmed" }); toast("PWD item applied"); }));
  };
  paint(it.candidates || []);
  $("#ps").oninput = debounce(async (e) => paint(await api(`/api/sor/search?q=${encodeURIComponent(e.target.value || it.description)}&unit=${encodeURIComponent(it.unit)}&k=8${schedQ()}`)), 250);
  $("#build").onclick = () => {
    const code = "RA-" + Math.random().toString(36).slice(2, 6).toUpperCase();
    const item = { code, description: it.description, unit: it.unit, category: it.category, analysis: null };
    rateAnalysis(item, async () => {
      await api(`/api/sor/${encodeURIComponent(code)}?${schedQ().slice(1)}`, { method: "PUT", json: { description: it.description, unit: it.unit, category: it.category } });
      await patchP(`/items/${it.key}`, { sor_code: code, rate: null, status: "confirmed" }); toast(`New rate ${code} created and applied`);
    });
  };
}

// ---------- land (second figure only)
const AREA_U = { sqm: 1, sqft: 0.09290304, sqyd: 0.83612736 };
function landCard(P) {
  const L = P.land || {}, p = P.params, u = WS.lu || "sqft";
  return `<div class="card pad"><b>Land (for figure 2 only)</b><div class="muted" style="font-size:12.5px;margin:4px 0 10px">Never added to the construction cost. Use the official guideline / ready-reckoner value from the state registration department, or your own estimate — no market data is fetched.</div>
    <div class="params"><div><label class="lbl">Plot area</label><input class="input" type="number" step="any" id="la" value="${L.area_sqm ? +(L.area_sqm / AREA_U[u]).toFixed(2) : ""}" placeholder="e.g. 2400"></div>
      <div><label class="lbl">Unit</label><select class="input" id="lu">${Object.keys(AREA_U).map((k) => `<option value="${k}" ${k === u ? "selected" : ""}>${{ sqm: "m²", sqft: "sq ft", sqyd: "sq yd" }[k]}</option>`).join("")}</select></div>
      <div><label class="lbl">Land rate per unit (₹)</label><input class="input" type="number" step="any" id="lr" value="${L.rate_per_sqm ? +(L.rate_per_sqm * AREA_U[u]).toFixed(2) : ""}"></div>
      <div><label class="lbl">Basis of the rate</label><select class="input" id="lb">${["Official guideline / ready-reckoner value", "Market estimate (user)", "Purchase price (actual)"].map((b) => `<option ${b === p.land_rate_basis ? "selected" : ""}>${b}</option>`).join("")}</select></div>
      <div><label class="lbl">Stamp duty + registration %</label><input class="input" type="number" step="0.1" id="ld" value="${p.stamp_duty_pct || 0}"></div>
      <div style="display:flex;align-items:flex-end"><button class="btn btn-sm" id="lsv" style="width:100%">Apply</button></div></div></div>`;
}
function bindLand() {
  $("#lu") && ($("#lu").onchange = () => { WS.lu = $("#lu").value; stepEstimate(); });
  $("#lsv") && ($("#lsv").onclick = async () => {
    const f = AREA_U[$("#lu").value];
    await patchP("", { params: { land_area: (+$("#la").value || 0) * f, land_rate: (+$("#lr").value || 0) / f, land_rate_basis: $("#lb").value, stamp_duty_pct: +$("#ld").value || 0 } });
    toast("Land figure updated — construction cost unchanged");
  });
}

// ---------- Step 4: estimate
function stepEstimate() {
  const P = WS.P, E = P.estimate, p = P.params, src = p._src || {}, max = Math.max(...E.categories.map((c) => c.amount), 1);
  let rows = "", cur = null;
  for (const it of E.items) {
    if (it.category !== cur) { cur = it.category; const a = E.categories.find((c) => c.name === cur)?.amount; rows += `<tr class="group"><td colspan="5">${esc(cur)}</td><td class="num">${inr(a)}</td></tr>`; }
    rows += `<tr class="${["review", "unmapped"].includes(it.status) ? "flag" : ""}"><td class="dim">${it.sno}</td><td>${esc(it.description)}<div class="sub">${it.sor_code ? `PWD/SOR ${esc(it.sor_code)}` : "No rate"} · ${esc(it.trace || "")}</div></td>
      <td class="num">${num(it.qty)}</td><td>${esc(it.unit)}</td><td class="num">${it.rate != null ? num(it.rate) : "—"}</td><td class="num">${inr(it.amount)}</td></tr>`;
  }
  const srcTxt = (k) => src[k] === "user" ? `<span class="src user">set by you · <button class="btn-link" data-reset="${k}">use drawing</button></span>` : src[k] && src[k] !== "default" ? `<span class="src">from ${esc(src[k])}</span>` : `<span class="src">default</span>`;
  const vers = P.versions || [];
  $("#body").innerHTML = `${rateSourcePanel(P)}${qualityBanner(P)}${gapsBanner(P)}<div class="est-grid">
    <div class="card"><table class="table"><thead><tr><th style="width:44px">#</th><th>Item description</th><th class="num">Quantity</th><th>Unit</th><th class="num">PWD rate</th><th class="num">Estimated cost</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="sticky" style="display:flex;flex-direction:column;gap:12px">
      <div class="card pad"><div class="two-fig"><div><div class="l">1 · Construction cost</div><div class="v">${inr(E.total)}</div><div class="s">Building only, from ${esc(P.rate_source?.schedule?.label || "— no rate schedule")}. Excludes land.</div></div>
        <div><div class="l">2 · Construction + land</div><div class="v">${P.land?.provided ? inr(P.land.total_with_land) : "—"}</div><div class="s">${P.land?.provided ? `Land ${num(P.land.area_sqm, 1)} m² × ${inr(P.land.rate_per_sqm)}/m² (${esc(P.land.basis || "rate entered by user")}) = ${inr(P.land.land_cost)}${P.land.stamp_duty_registration ? ` + stamp duty & registration ${inr(P.land.stamp_duty_registration)}` : ""}` : "Enter the plot area and land rate below."}</div></div></div></div>
      <div class="card pad"><b>Cost summary</b><div style="margin-top:10px">
        ${E.categories.slice().sort((a, b) => b.amount - a.amount).map((c) => `<div style="padding:5px 0"><div class="row" style="font-size:13px"><span class="grow">${esc(c.name)}</span><span class="num">${inr(c.amount)}</span></div><div class="catbar"><i style="width:${(c.amount / max) * 100}%"></i></div></div>`).join("")}
        <div class="sum-row" style="margin-top:10px;border-top:1px solid var(--line);padding-top:12px"><span>Works total</span><span class="num">${inr(E.subtotal)}</span></div>
        <div class="sum-row muted"><span>Contingency ${p.contingency}%</span><span class="num">${inr(E.contingency)}</span></div>
        <div class="sum-row muted"><span>Labour cess ${p.cess}%</span><span class="num">${inr(E.cess)}</span></div>
        <div class="sum-row muted"><span>GST ${p.gst}%</span><span class="num">${inr(E.gst)}</span></div>
        <div class="sum-row total"><span>Project cost</span><span class="num">${inr(E.total)}</span></div>
        <div class="muted" style="font-size:12.5px;text-align:right">${lakh(E.total)}${P.summary.cost_per_sqft ? ` · ₹${num(P.summary.cost_per_sqft, 0)} per sq ft built-up` : ""}</div></div></div>
      <div class="card pad" id="aisum"><div class="row"><b class="grow">Summary</b><button class="btn btn-sm" id="aisb">Explain this estimate</button></div>
        <div class="muted" style="font-size:12.5px;margin-top:4px">Written by Google Gemma 3 (open model) running on this server, only from this estimate's own numbers.</div><div id="aisout"></div></div>
      <div class="card pad" id="mkt"><b>Market check</b><div class="muted" style="font-size:12.5px;margin-top:4px">Checking current prices on the web…</div></div>
      <div class="card pad" style="display:flex;flex-direction:column;gap:8px">
        ${locked() ? `<div class="badge ok" style="height:34px;justify-content:center">Confirmed · locked (R${vers[vers.length - 1]?.no})</div>` : `<button class="btn btn-dark" id="conf">Confirm final estimate</button>`}
        <a class="btn" href="/api/projects/${P.id}/report.pdf" target="_blank">Download PDF report</a>
        <a class="btn" href="/api/projects/${P.id}/export.xlsx">Download Excel</a>
        <a class="btn-link" href="/api/projects/${P.id}/report" target="_blank" style="text-align:center;font-size:13px">Open report in browser</a></div>
      ${landCard(P)}
      <div class="card pad"><b>Building parameters</b><div class="muted" style="font-size:12.5px;margin:4px 0 10px">Read from the drawings where available. Change a value to override it.</div>
        ${PARAMS.map(([k, l, st]) => `<div class="prm"><label class="lbl">${l}</label><input class="input" type="number" step="${st}" data-p="${k}" value="${p[k]}">${srcTxt(k)}</div>`).join("")}</div>
      <div class="card pad"><b>Specification & charges</b><div class="params" style="margin-top:12px">
        <div><label class="lbl">Finish</label><select class="input" data-p="finish">${["economy", "standard", "premium"].map((f) => `<option ${p.finish === f ? "selected" : ""}>${f}</option>`).join("")}</select></div>
        <div><label class="lbl">Windows</label><select class="input" data-p="window_type">${[["aluminium", "Aluminium"], ["upvc", "UPVC"]].map(([v, l]) => `<option value="${v}" ${p.window_type === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div><label class="lbl" title="Used where the SOR publishes labour rates by zone (e.g. Telangana)">Labour zone (SOR)</label><select class="input" data-p="labour_zone">${[["Z1", "Zone I · Municipal corporation"], ["Z2", "Zone II · Municipality"], ["Z3", "Zone III · Rural"]].map(([v, l]) => `<option value="${v}" ${p.labour_zone === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div><label class="lbl" title="Only used where the SOR does not print cement (e.g. AP: monthly rate fixed by the Sub-Committee)">Cement rate ₹/tonne (if SOR has none)</label><input class="input" type="number" step="1" data-p="cement_rate" value="${p.cement_rate || 0}"></div>
        <div><label class="lbl" title="Only used where the SOR does not print reinforcement steel">Steel rate ₹/tonne (if SOR has none)</label><input class="input" type="number" step="1" data-p="steel_rate" value="${p.steel_rate || 0}"></div>
        <div><label class="lbl">Contingency %</label><input class="input" type="number" step="0.5" data-p="contingency" value="${p.contingency}"></div>
        <div><label class="lbl">GST %</label><input class="input" type="number" step="1" data-p="gst" value="${p.gst}"></div>
        <div><label class="lbl">Labour cess %</label><input class="input" type="number" step="0.5" data-p="cess" value="${p.cess}"></div>
        <div><label class="lbl" title="Multiplies every schedule rate. Leave 1 unless the authority publishes a cost index for the place of work.">Cost index (user-set, 1 = as published)</label><input class="input" type="number" step="0.01" data-p="cost_index" value="${p.cost_index}"></div></div></div>
      ${vers.length ? `<div class="card pad"><b>Revisions</b>${vers.slice().reverse().map((v) => `<div class="sum-row"><span>R${v.no} · ${esc(v.by)}<br><span class="dim" style="font-size:12px">${esc(v.t.replace("T", " ").slice(0, 16))}</span></span><span class="num">${inr(v.total)}</span></div>`).join("")}</div>` : ""}
      ${P.history?.length ? `<div class="card pad"><b>Activity</b><div class="hist">${P.history.slice(-8).reverse().map((h) => `<div><span class="dim">${esc(h.t.replace("T", " ").slice(5, 16))}</span> ${esc(h.text)}</div>`).join("")}</div></div>` : ""}
    </div></div>`;
  loadMarketCheck(P.id);
  $("#aisb").onclick = async () => {
    const out = $("#aisout"); out.innerHTML = `<div class="muted" style="font-size:12.5px;margin-top:8px">Writing…</div>`;
    let r; try { r = await api(`/api/projects/${P.id}/ai-summary`); } catch (e) { r = { available: true, text: null, reason: String(e) }; }
    out.innerHTML = r.text ? `<div style="font-size:13px;margin-top:8px;white-space:pre-wrap">${esc(r.text)}</div><div class="dim" style="font-size:11.5px;margin-top:6px">${esc(r.model || "")} · numbers checked against the estimate</div>`
      : `<div class="muted" style="font-size:12.5px;margin-top:8px">${esc(r.message || r.reason || "No summary.")}</div>`;
  };
  $$("[data-p]").forEach((el) => (el.onchange = async () => {
    const v = el.tagName === "SELECT" ? el.value : +el.value;
    await patchP("", { params: { [el.dataset.p]: v } }); toast("Estimate updated");
  }));
  $$("[data-reset]").forEach((b) => (b.onclick = () => patchP("", { params: { [b.dataset.reset]: null } })));
  bindRateSource(); bindLand();
  $("#conf") && ($("#conf").onclick = () => {
    modal(`<h2>Confirm final estimate</h2><p class="muted" style="margin:6px 0 16px">This saves revision R${vers.length + 1} (${inr(E.total)}) and locks the estimate. ${P.stats.review ? `<b style="color:var(--warn)">${P.stats.review} item(s) still need a PWD rate review.</b>` : ""}</p>
      <div class="params"><div><label class="lbl">Confirmed by</label><input class="input" id="cby" placeholder="Name / designation"></div><div><label class="lbl">Note (optional)</label><input class="input" id="cnote"></div></div>
      <div class="row" style="justify-content:flex-end;margin-top:20px"><button class="btn" id="cx">Cancel</button><button class="btn btn-dark" id="sv">Confirm & lock</button></div>`);
    $("#cx").onclick = closeModal;
    $("#sv").onclick = async () => { if (!$("#cby").value.trim()) return toast("Enter the name of the person confirming", true); closeModal(); await patchP("/confirm", { by: $("#cby").value, note: $("#cnote").value }, "POST"); toast("Estimate confirmed and locked"); };
  });
}

router();

// ------------------------------------------------------------------ ANNOTATION REVIEW (TN dataset)
async function renderAnnotate(pid) {
  if (!pid) {
    const [cov, pages] = await Promise.all([api("/api/annotations/coverage"), api("/api/annotations/pages")]);
    view.innerHTML = `<div class="wrap"><h1 style="font-size:24px">Drawing annotation review</h1>
      <p class="muted">Pseudo labels are model output and never ground truth. A page becomes VERIFIED only after two reviewers (other than the annotator) approve it. Only verified pages of training-eligible projects can be exported for training.</p>
      <div class="kv">${Object.entries(cov.states).map(([k, v]) => `<span>${esc(k)}</span><span>${v}</span>`).join("")}<span>Verified (training-eligible)</span><span>${cov.verified_training_records}</span></div>
      <div class="card" style="margin-top:12px"><table class="table"><thead><tr><th>Page</th><th>File</th><th>Type</th><th>Split</th><th>Licence</th><th>State</th></tr></thead><tbody>
      ${pages.map((p) => `<tr class="click" data-pg="${esc(p.page_id)}"><td class="mono">${esc(p.page_id)}</td><td>${esc(p.file)} p${p.page}</td><td>${esc(p.drawing_type)}</td><td>${esc(p.split || "")}</td><td>${esc(p.license_status)}</td><td><b>${esc(p.state)}</b></td></tr>`).join("")}</tbody></table></div></div>`;
    $$("[data-pg]").forEach((r) => (r.onclick = () => (location.hash = "#/annotate/" + r.dataset.pg)));
    return;
  }
  const A = await api("/api/annotations/" + pid);
  const objs = (A.record?.objects) || [];
  const W = A.page.width, H = A.page.height;
  const box = (o, c) => o.bbox ? `<rect x="${o.bbox[0]}" y="${o.bbox[1]}" width="${o.bbox[2] - o.bbox[0]}" height="${o.bbox[3] - o.bbox[1]}" fill="none" stroke="${c}" stroke-width="${Math.max(1, W / 500)}"><title>${esc(o.class)} ${esc(o.id || "")}</title></rect>` : "";
  view.innerHTML = `<div class="wrap"><a class="btn-link" href="#/annotate">← all pages</a><h1 style="font-size:20px">${esc(A.page.file)} · page ${A.page.page} — <span>${esc(A.state)}</span></h1>
    <p class="muted">Blue = pseudo labels (model, NOT ground truth) · Red = human draft / verified objects. Licence: ${esc(A.page.license_status)} · training eligible: ${A.page.training_eligible ? "yes" : "no"}</p>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-height:70vh;background:#fff;border:1px solid var(--line)"><image href="${A.image}" width="${W}" height="${H}"/>
      ${(A.pseudo?.objects || []).map((o) => box(o, "#3182ce")).join("")}${objs.map((o) => box(o, "#e53e3e")).join("")}</svg>
    <div class="row" style="gap:8px;margin:10px 0;flex-wrap:wrap"><input class="input" id="who" placeholder="Your name (annotator / reviewer)" style="max-width:260px">
      ${A.pseudo ? `<button class="btn btn-sm" id="fp">Start draft from pseudo labels</button>` : ""}<button class="btn btn-sm btn-dark" id="sv">Save draft</button>
      <button class="btn btn-sm" id="ap">Approve</button><button class="btn btn-sm" id="rj">Reject</button></div>
    <label class="lbl">Objects (JSON list of {id, class, bbox:[x0,y0,x1,y1] | polygon | value+unit}) — classes: ${esc(A.classes.join(", "))}</label>
    <textarea class="input mono" id="js" style="height:220px">${esc(JSON.stringify(objs, null, 1))}</textarea>
    <div class="muted" style="margin-top:8px">Reviews: ${esc(JSON.stringify(A.record?.reviews || []))}</div></div>`;
  const who = () => $("#who").value.trim();
  const call = async (url, body, method = "POST") => { try { await api(url, { method, body: JSON.stringify(body) }); renderAnnotate(pid); } catch (e) { alert(e.message); } };
  $("#fp") && ($("#fp").onclick = () => call(`/api/annotations/${pid}/from-pseudo`, { annotator: who() }));
  $("#sv").onclick = () => { let o; try { o = JSON.parse($("#js").value); } catch (e) { return alert("invalid JSON"); } call(`/api/annotations/${pid}`, { objects: o, annotator: who() }, "PUT"); };
  $("#ap").onclick = () => call(`/api/annotations/${pid}/review`, { reviewer: who(), decision: "approve" });
  $("#rj").onclick = () => call(`/api/annotations/${pid}/review`, { reviewer: who(), decision: "reject", note: prompt("Reason") || "" });
}
