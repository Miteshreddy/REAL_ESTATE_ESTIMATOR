"""Price a TN Standard Data item with TN SOR basic rates of the same edition.

    rate per unit = Σ (component qty × unit factor × SOR basic rate)  ÷  'Total for N' quantity  ×  Π(1 + additions %)

Component → resource resolution, in order:
  1. sub-data of the same book (mortars, concretes …) by name, priced recursively;
  2. SOR basic items (L- labour, M- material, W- work, H- hire) by normalised name;
     numbers in the name (20mm, 1:6, M-20, class I/II, 230x110x75) must all appear in the candidate,
     and the units must be convertible (kg↔tonne, Nos↔day/each, cu.m, sq.m, litre, 1000 each).
Anything not resolved unambiguously stays UNRESOLVED: the item is then 'needs rate analysis' and is never priced
from a partial sum. Lump-sum sundries (LS, no amount printed in the book) are listed as excluded.
"""
from __future__ import annotations

import re
from functools import lru_cache

UNIT = {  # canonical unit, factor to it
    "cu.m": ("cum", 1), "cum": ("cum", 1), "cu.m.": ("cum", 1), "m3": ("cum", 1),
    "sq.m": ("sqm", 1), "sq.m.": ("sqm", 1), "sqm": ("sqm", 1), "sqm.": ("sqm", 1), "m2": ("sqm", 1),
    "kg": ("kg", 1), "kg.": ("kg", 1), "kgs": ("kg", 1), "mt": ("kg", 1000), "mt.": ("kg", 1000), "tonne": ("kg", 1000), "t": ("kg", 1000),
    "quintal": ("kg", 100), "qtl": ("kg", 100),
    "nos": ("nos", 1), "nos.": ("nos", 1), "no": ("nos", 1), "no.": ("nos", 1), "each": ("nos", 1), "day": ("nos", 1), "number": ("nos", 1),
    "1000 each": ("nos", 1000), "1000 nos": ("nos", 1000), "100 each": ("nos", 100), "10 each": ("nos", 10),
    "litre": ("litre", 1), "lit": ("litre", 1), "lit.": ("litre", 1), "ltr": ("litre", 1), "litres": ("litre", 1), "kl": ("litre", 1000),
    "m": ("m", 1), "metre": ("m", 1), "rm": ("m", 1), "rmt": ("m", 1), "r.m": ("m", 1), "km": ("m", 1000),
}


def unit_of(u):
    u = (u or "").strip().lower().rstrip(",")
    u = re.sub(r"\s+", " ", u)
    return UNIT.get(u) or UNIT.get(u.rstrip("."))


# TN terminology: the Standard Data Book and the SOR name the same resource differently (documented, reviewable)
SYNONYMS = [(r"machine\s*crushed\s*(stone|granite)?\s*(jelly|metal)", "hbgs jelly"), (r"hard\s*broken\s*granite\s*stone", "hbgs"),
            (r"\(?commercially\s*called\s*m\s*-?\s*sand\)?", " msand "), (r"\(\s*m\s*-?\s*sand\s*\)", " msand "),
            (r"\(\s*p\s*-?\s*sand\s*\)", " psand "), (r"plastering\s*sand", "psand"),
            (r"plasticizer", "plasticiser"), (r"\bmasons\b", "mason"), (r"\bmazdoors\b", "mazdoor"),
            (r"\b\d+\s*-\s*(\d+)\s*mm", r"\1mm")]  # '10-12mm jelly' is priced as the 12mm size


def norm(s):
    s = (s or "").lower()
    for a, b in SYNONYMS:
        s = re.sub(a, b, s)
    s = s.replace("–", "-").replace("×", "x")
    s = re.sub(r"\b1st\b|\bist\b|\bi st\b|\bfirst\b", " i ", s)
    s = re.sub(r"\b2nd\b|\biind\b|\bii nd\b|\bsecond\b", " ii ", s)
    s = re.sub(r"category\s*-\s*", "category ", s)
    s = re.sub(r"class\s*-\s*", "class ", s)
    s = re.sub(r"-\s*(i{1,3})\s+class", r" \1 class", s)
    s = re.sub(r"(\d)\s*mm", r"\1mm", s)
    s = re.sub(r"m\s*-\s*(\d\d)\b", r"m\1", s)
    s = re.sub(r"[^a-z0-9:.x ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


STOP = set("of the and in for with to by a an etc complete as per including incl using all any on at or from is be cost supply supplying providing".split())


def toks(s):
    return [t for t in norm(s).split() if t not in STOP]


def keys(s):
    """tokens that must match exactly: sizes, ratios, grades, class numerals."""
    n = norm(s)
    k = set(re.findall(r"\b\d+(?:\.\d+)?mm\b|\b\d+:\d+(?::\d+)?\b|\bm\d\d\b|\b\d+x\d+(?:x\d+)?\b", n))
    m = re.search(r"\b(i{1,3})\s+class\b|\bclass\s+(i{1,3})\b|\bcategory\s+(i{1,3})\b", n)
    if m:
        k.add("cls:" + next(g for g in m.groups() if g))
    return k


# Where the Standard Data names a generic resource that the SOR splits into several priced grades, the grade used is an
# explicit, documented estimating choice (shown on every analysed rate as 'default choice — review'), never silent.
RESOURCE_DEFAULTS = {
    "sand": ("M-0126", "SOR 2025-26 prints no river sand; plastering sand (P-Sand) used for 'Sand' in mortars"),
    "grinding mortar": ("W-0163", "ordinary grinding lime assumed (special grinding lime only where specified)"),
}


class Resolver:
    def __init__(self, sor_items: list[dict], sd_items: list[dict]):
        self.sor = sor_items
        self.by_code = {r["code"]: r for r in sor_items}
        self.sd = sd_items
        self._tok = [(set(toks(r["description"])), keys(r["description"]), r) for r in sor_items]
        self._sdtok = [(set(toks(it["description"])), keys(it["description"]), it) for it in sd_items]

    def _best(self, name, per, pool, kind, context=""):
        tn, kn = set(toks(name)), keys(name)
        ctx = set(toks(context)) - tn
        if not tn:
            return None, []
        pu = unit_of(per)
        scored = []
        for t, k, r in pool:
            if kn - k:  # every size / ratio / class in the component must be in the candidate
                continue
            ov = len(tn & t)
            if not ov:
                continue
            score = ov / len(tn | t) + 0.5 * ov / len(tn) + 0.03 * len(ctx & t)  # item context breaks ties (brick vs stone mason)
            if kind == "sor":
                ru = unit_of(r["unit"])
                if pu and ru and pu[0] != ru[0]:
                    continue
                if pu is None and ru is None:
                    continue
            scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        if not scored or scored[0][0] < 0.55:
            return None, scored[:3]
        return scored[0][1], scored[:3]

    def resolve(self, comp, context=""):
        name, per = comp["name"], comp.get("per")
        if re.search(r"vibrat", name, re.I):  # SOR W-0101 (RCC) / W-0100 (PCC): 'where vibrators are specified … per cu.m over and above'
            code = "W-0101" if re.search(r"reinforc|\brcc\b|r\.c\.c", context, re.I) else "W-0100"
            if code in self.by_code:
                return dict(kind="sor", code=code, item=self.by_code[code], default="vibration charge per SOR " + code)
        d = RESOURCE_DEFAULTS.get(norm(name))
        if d and d[0] in self.by_code:
            return dict(kind="sor", code=d[0], item=self.by_code[d[0]], default=d[1])
        # sub-data first (mortars / concretes defined in the same book)
        if re.search(r"mortar|mortor|concrete \d|\bcc\b|\b1:\d", norm(name)):
            it, _ = self._best(name, per, self._sdtok, "sd")
            if it is not None:
                return dict(kind="sub_data", ref=it["data_no"], item=it)
        r, cands = self._best(name, per, self._tok, "sor", context)
        if r is None:
            return dict(kind="unresolved", candidates=[(round(s, 2), c["code"], c["description"][:60]) for s, c in cands])
        # ambiguity: two near-equal candidates with different rates
        alt = [c for s, c in cands[1:] if s >= cands[0][0] - 0.02 and abs(float(c["rate"]) - float(r["rate"])) > 0.005]
        if alt:
            return dict(kind="ambiguous", candidates=[(round(s, 2), c["code"], c["description"][:60], c["rate"]) for s, c in cands])
        return dict(kind="sor", code=r["code"], item=r)


def _bound(name, bind):
    n = norm(name)
    for k, ref in (bind or {}).items():
        if n.startswith(norm(k)) or norm(k) in n:
            return ref
    return None


def price_variant(var, res: Resolver, depth=0, seen=(), context="", bind=None, ignore=None, sd_by_no=None):
    """bind: {component name (prefix): 'SOR:<code>' | 'SD:<data_no>:<variant>'} — explicit, reviewed wiring for components the
    book names generically or defines in a sub-data block of the same item. ignore: component / addition names to leave out
    (e.g. extras for upper floors), each reported in 'excluded'."""
    parts, total, unresolved, excluded = [], 0.0, [], []
    for c in var["components"]:
        if c.get("lump_sum"):
            excluded.append(dict(name=c["name"], why="lump-sum sundries — no amount printed in the Standard Data"))
            continue
        if any(norm(i) in norm(c["name"]) for i in (ignore or [])):
            excluded.append(dict(name=c["name"], why="left out by the reviewed item map (see note)"))
            continue
        ref = _bound(c["name"], bind)
        if ref and ref.startswith("SD:") and sd_by_no is not None:
            _, no, vi = ref.split(":")
            sub_it = sd_by_no.get(no)
            if sub_it is None or int(vi) >= len(sub_it["variants"]):
                unresolved.append(dict(name=c["name"], why=f"bound sub-data {ref} not found"))
                continue
            sv = sub_it["variants"][int(vi)]
            sp = price_variant(sv, res, depth + 1, seen + (no,), context, bind, ignore, sd_by_no)
            if not sp["complete"]:
                unresolved.append(dict(name=c["name"], why=f"bound sub-data {ref} incomplete"))
                continue
            r = dict(kind="sub_data_bound", ref=no)
            rate, ref_txt = sp["rate"], f"SD {no} v{vi}"
            ru, cu = unit_of(sv.get("per_unit")) or unit_of(c.get("per")), unit_of(c["unit"])
            if not cu or not ru or cu[0] != ru[0]:
                unresolved.append(dict(name=c["name"], why=f"unit {c['unit']} vs sub-data {sv.get('per_unit')}"))
                continue
            q = c["qty"] * cu[1] / ru[1]
            total += q * rate
            parts.append(dict(name=c["name"], qty=c["qty"], unit=c["unit"], ref=ref_txt, rate=round(rate, 2), qty_in_rate_unit=round(q, 5),
                              amount=round(q * rate, 2), default="bound by item map"))
            continue
        if ref and ref.startswith("SOR:") and ref[4:] in res.by_code:
            r = dict(kind="sor", code=ref[4:], item=res.by_code[ref[4:]], default="bound by item map")
        else:
            r = res.resolve(c, context)
        cu = unit_of(c["unit"])
        if r["kind"] == "sub_data" and depth < 3 and r["ref"] not in seen:
            sub = r["item"]["variants"][0]
            sp = price_variant(sub, res, depth + 1, seen + (r["ref"],))
            if not sp["complete"]:
                unresolved.append(dict(name=c["name"], why=f"sub-data {r['ref']} incomplete"))
                continue
            rate, rate_unit, ref = sp["rate"], sub.get("per_unit") or c.get("per"), f"SD {r['ref']}"
            ru = unit_of(rate_unit) or unit_of(c.get("per"))
        elif r["kind"] == "sor":
            rate, ru, ref = float(r["item"]["rate"]), unit_of(r["item"]["unit"]), r["code"]
        else:
            unresolved.append(dict(name=c["name"], why=r["kind"], candidates=r.get("candidates")))
            continue
        if not cu or not ru or cu[0] != ru[0]:
            unresolved.append(dict(name=c["name"], why=f"unit {c['unit']} not convertible to {rate_unit if r['kind']=='sub_data' else r['item']['unit']}"))
            continue
        q = c["qty"] * cu[1] / ru[1]
        amt = q * rate
        total += amt
        parts.append(dict(name=c["name"], qty=c["qty"], unit=c["unit"], ref=ref, rate=round(rate, 2), qty_in_rate_unit=round(q, 5), amount=round(amt, 2),
                          default=r.get("default")))
    per = var.get("per_qty") or 1.0
    m = re.search(r"(?:main\s*data|data)\s*for\s*([\d.]+)\s*(?:sq\.?\s*m|m2|cu\.?\s*m)", var.get("label") or "", re.I)
    if per == 1.0 and m:  # 'Main Data for 128.66 Sq.m' — the quantities above are for that area
        per = float(m.group(1))
    sub = total / per
    rate = sub
    adds = []
    for a in var.get("additions", []):
        if any(norm(i) in norm(a["text"]) for i in (ignore or [])):
            excluded.append(dict(name=a["text"][:80], why="left out by the reviewed item map (see note)"))
            continue
        if re.search(r"wastage", a["text"], re.I):  # applies to one component, not to the whole rate → cannot be applied blindly
            unresolved.append(dict(name=a["text"][:80], why="component-level wastage addition — needs review"))
            continue
        pct = a.get("pct")
        if pct is None:
            m = re.search(r"([\d.]+)\s*%", a["text"])
            pct = float(m.group(1)) if m and not re.search(r"extra\s+of\s+above|cost\s+of", a["text"], re.I) else None
        if pct is not None:
            a = dict(a, pct=pct)
        if a.get("pct") is not None:
            inc = rate * a["pct"] / 100
            adds.append(dict(text=a["text"][:80], pct=a["pct"], amount=round(inc, 2)))
            rate += inc
        else:
            # an 'Add for …' line that refers to a SOR work item (e.g. vibration charges for RCC) — priced per unit if it resolves
            nm = re.sub(r"^add\s+(for\s+)?", "", a["text"], flags=re.I)
            nm = re.split(r"\s(?:cu\.?\s?m|sq\.?\s?m|sub[\s-]*total)", nm, flags=re.I)[0]
            r = res.resolve(dict(name=nm, per=var.get("per_unit")), context)
            if r["kind"] == "sor" and unit_of(r["item"]["unit"]) and unit_of(var.get("per_unit")) and unit_of(r["item"]["unit"])[0] == unit_of(var.get("per_unit"))[0]:
                inc = float(r["item"]["rate"])
                adds.append(dict(text=a["text"][:80], ref=r["code"], amount=round(inc, 2)))
                rate += inc
            else:
                unresolved.append(dict(name=a["text"][:80], why="addition without a printed percentage (amount from another data item)"))
    # a 'Main Data … Cost of MS sheets, props …' block whose material lines were not parsed would price labour only
    if re.search(r"cost\s+of", var.get("label") or "", re.I) and parts and all(str(x["ref"]).startswith("L-") for x in parts):
        unresolved.append(dict(name=(var.get("label") or "")[:80], why="material cost lines named in the heading were not parsed — labour-only rate rejected"))
    return dict(complete=not unresolved, rate=round(rate, 2), per_unit=var.get("per_unit"), per_qty=per, subtotal=round(sub, 2),
                components=parts, additions=adds, unresolved=unresolved, excluded=excluded)
