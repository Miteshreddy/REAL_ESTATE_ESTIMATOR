"""NLP utilities: drawing-annotation parsing, room-label understanding and SOR semantic matching."""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, make_pipeline

# ------------------------------------------------------------------ dimension / scale parsing
FT_IN = re.compile(r"(\d{1,3})\s*['’]\s*-?\s*(\d{1,2}(?:\.\d+)?)?\s*(?:\"|”|'')?")
MET = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|m)?\b", re.I)
PAIR = re.compile(r"(\d[\d.'’\"”\s-]*?)\s*[xX×\*]\s*(\d[\d.'’\"”\s-]*)")
SCALE = re.compile(r"(?:scale|sc\.?)\s*[:=-]?\s*1\s*[:/]\s*(\d{2,4})|\b1\s*:\s*(20|25|50|75|100|125|150|200|250|500|1000)\b", re.I)
NTS = re.compile(r"\bN\.?T\.?S\.?\b|NOT\s+TO\s+SCALE", re.I)
FLOORS = re.compile(r"\bG\s*\+\s*(\d)\b", re.I)
FLOOR_HT = re.compile(r"(?:floor|storey|clear)\s*(?:ht|height)\.?\s*[:=-]?\s*(\d+(?:\.\d+)?)\s*(m|mm)?", re.I)


def parse_length(tok: str, hint_unit: str = "m") -> float | None:
    """'12'6"' -> 3.81 ; '3600' -> 3.6 ; '3.60' -> 3.6 ; '360cm' -> 3.6"""
    tok = tok.strip()
    m = FT_IN.fullmatch(tok) or (FT_IN.match(tok) if "'" in tok or "’" in tok else None)
    if m:
        ft = float(m.group(1))
        inch = float(m.group(2) or 0)
        return round(ft * 0.3048 + inch * 0.0254, 4)
    m = MET.fullmatch(tok)
    if not m:
        return None
    v = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit == "mm" or (not unit and v >= 100):
        return v / 1000.0
    if unit == "cm":
        return v / 100.0
    return v


FTIN = re.compile(r"(?<![\d.])(\d{1,2})\s*['](?:\s*(\d{1,2})\s*[\"]?)?\s*[xX×]\s*(\d{1,2})\s*['](?:\s*(\d{1,2})\s*[\"]?)?"
                  r"|(?<![\d.])(\d{1,2})\s*['\"]?\s+(\d{1,2})\s*[\"]\s*[xX×]\s*(\d{1,2})\s*['\"]?\s*(\d{1,2})\s*[\"]")


def ftin_pair(text: str):
    """Feet-inch room dimensions as OCR reads them: 11'0" x 12'2" → 11′0° x 12 2* (primes become ′ ° *, marks get lost)."""
    t = re.sub(r"[′’`´]", "'", text)
    t = re.sub(r"[″”°*]", '"', t)
    t = re.sub(r"'\s*'", '"', t)
    m = FTIN.search(t)
    if not m:
        return None
    g = [x for x in m.groups()]
    fa, ia, fb, ib = (g[0], g[1], g[2], g[3]) if g[0] is not None else (g[4], g[5], g[6], g[7])
    ia, ib = int(ia or 0), int(ib or 0)
    if ia > 11 or ib > 11:
        return None
    a, b = (int(fa) + ia / 12) * 0.3048, (int(fb) + ib / 12) * 0.3048
    return (round(a, 4), round(b, 4)) if 0.5 < a < 40 and 0.5 < b < 40 else None


def parse_pair(text: str):
    m = PAIR.search(text)
    if not m:
        return ftin_pair(text)
    a, b = parse_length(m.group(1)), parse_length(m.group(2))
    if a and b and 0.5 < a < 40 and 0.5 < b < 40:
        return a, b
    return None


def parse_project_notes(texts: list[str]) -> dict:
    out = {}
    blob = " | ".join(texts)
    m = SCALE.search(blob)
    if m:
        out["scale_den"] = int(m.group(1) or m.group(2))
    if NTS.search(blob):
        out["nts"] = True  # NOT TO SCALE: the scale must come from written dimensions or calibration
    m = FLOORS.search(blob)
    if m:
        out["floors"] = int(m.group(1)) + 1
    m = FLOOR_HT.search(blob)
    if m:
        v = float(m.group(1))
        out["floor_height"] = v / 1000 if (m.group(2) or "").lower() == "mm" or v > 50 else v
    if re.search(r"dimensions?\s+in\s+(mm|millimet)", blob, re.I):
        out["dim_unit"] = "mm"
    elif re.search(r"dimensions?\s+in\s+(feet|ft)", blob, re.I):
        out["dim_unit"] = "ft"
    return out


# ------------------------------------------------------------------ room label classifier
ROOM_TYPES = ["living", "bedroom", "kitchen", "toilet", "dining", "utility", "store", "pooja", "balcony", "stair", "corridor", "study", "garage"]

_ROOM_TRAIN = {
    "living": ["living room", "living", "hall", "drawing room", "drawing", "lounge", "family room", "liv", "living/dining", "great room", "sitting", "reception", "foyer"],
    "bedroom": ["bedroom", "bed room", "master bedroom", "m.bed", "m bed", "bed rm", "br 1", "bedroom 2", "guest room", "kids room", "children bedroom", "bed", "mbr", "gbr", "bedroom-3", "guest bed"],
    "kitchen": ["kitchen", "kit", "kitchenette", "cooking", "pantry kitchen", "modular kitchen", "kit.", "kitchen/utility"],
    "toilet": ["toilet", "bath", "bathroom", "w.c.", "wc", "wash", "washroom", "attached toilet", "t&b", "toilet 2", "powder room", "lavatory", "restroom", "bath rm", "common toilet", "ensuite"],
    "dining": ["dining", "dining room", "dinning", "din", "dining area", "breakfast"],
    "utility": ["utility", "wash area", "laundry", "service area", "dry balcony", "wash yard"],
    "store": ["store", "store room", "storage", "godown", "box room", "lumber", "shoe rack", "closet"],
    "pooja": ["pooja", "puja", "pooja room", "prayer", "mandir", "worship"],
    "balcony": ["balcony", "sit out", "sitout", "verandah", "veranda", "deck", "terrace", "porch", "open terrace"],
    "stair": ["staircase", "stair", "stairs", "lift", "staircase hall", "stair well", "up", "dn"],
    "corridor": ["passage", "corridor", "lobby", "circulation", "gallery", "landing"],
    "study": ["study", "office", "home office", "library", "work room", "den"],
    "garage": ["garage", "parking", "car park", "car porch", "stilt parking"],
}


class RoomLabelModel:
    def __init__(self):
        X, y = [], []
        for k, vs in _ROOM_TRAIN.items():
            for v in vs:
                for variant in {v, v.upper(), v.title(), v.replace(" ", ""), v + " 1"}:
                    X.append(variant)
                    y.append(k)
        feats = FeatureUnion([
            ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True)),
            ("w", TfidfVectorizer(analyzer="word", lowercase=True)),
        ])
        self.pipe = make_pipeline(feats, LogisticRegression(max_iter=2000, C=8))
        self.pipe.fit(X, y)

    def predict(self, label: str) -> tuple[str, float]:
        p = self.pipe.predict_proba([label])[0]
        i = int(np.argmax(p))
        return self.pipe.classes_[i], float(p[i])


ROOM_WORDS = re.compile(r"[A-Za-z]{2,}")


STAIR_MARKS = re.compile(r"^(UP|DN|DOWN|UP\s*/\s*DN|N|S|E|W|A|B|C|D|[A-Z]-[A-Z]|WIDTH.*|TREAD.*|RISER.*)$", re.I)


def looks_like_room_label(text: str) -> bool:
    t = text.strip()
    if len(t) < 2 or len(t) > 32 or STAIR_MARKS.match(t):
        return False
    if SCALE.search(t) or re.search(r"plan|scale|dimension|floor ht|drawing no|sheet|north", t, re.I):
        return False
    return bool(ROOM_WORDS.search(t))


# ------------------------------------------------------------------ layer name understanding (DXF)
LAYER_RULES = [
    ("wall", r"wall|wal\b|a-wall|masonry|brick|partition"),
    ("door", r"door|dr\b|a-door"),
    ("window", r"window|glaz|win\b|wdw|vent"),
    ("opening", r"woodwork|joinery|carpentry|opening|shutter"),
    ("beam", r"beam|\bbm\b|lintel"),
    ("column", r"col|column|s-cols|pillar|\brcc\b|_rcc|rcc_"),
    ("room", r"room|area|space|zone"),
    ("text", r"text|anno|label|note|tag"),
    ("dim", r"dim"),
    ("furniture", r"furn|fixt|equip|sanit|plumb"),
]


def classify_layer(name: str) -> str:
    n = name.lower()
    for k, pat in LAYER_RULES:
        if re.search(pat, n):
            return k
    return "other"


# ------------------------------------------------------------------ SOR semantic matcher
SYN = {
    "rcc": "reinforced cement concrete rcc", "pcc": "plain cement concrete pcc", "tmt": "tmt steel reinforcement bars",
    "plaster": "plaster plastering", "tiles": "tiles tile flooring", "paint": "painting paint",
    "excavation": "excavation earth work earthwork", "masonry": "brick work masonry", "shuttering": "centering shuttering formwork",
}


def _norm(t: str) -> str:
    t = t.lower()
    t = re.sub(r"[^a-z0-9.:/ ]", " ", t)
    for k, v in SYN.items():
        t = re.sub(rf"\b{k}\b", v, t)
    return t


@dataclass
class Match:
    code: str
    score: float


class SORMatcher:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.vec = FeatureUnion([
            ("w", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, stop_words="english")),
            ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)),
        ])
        # the specific sub-item text (after " — ") distinguishes variants, so it is weighted twice
        docs = [_norm(f"{r['description']} {r['description'].split(' — ')[-1]} {r['category']} {r['category']}") for r in rows]
        self.M = self.vec.fit_transform(docs) if rows else None

    def search(self, query: str, unit: str | None = None, category: str | None = None, k: int = 5) -> list[dict]:
        if not self.rows:
            return []
        q = self.vec.transform([_norm(query + (" " + category if category else ""))])
        s = (self.M @ q.T).toarray().ravel() / 2.0
        if unit:
            s = s + np.array([0.12 if r["unit"] == unit else -0.08 for r in self.rows])
        if category:
            s = s + np.array([0.08 if r["category"] == category else 0 for r in self.rows])
        # "Extra for …", dismantling and repair items are add-ons, never the main item for new work
        ql = query.lower()
        for word, pen in (("extra for", 0.25), ("dismantl", 0.25), ("repair", 0.15), ("old work", 0.12), ("existing", 0.08)):
            if word not in ql:
                s = s - np.array([pen if word in r["description"].lower()[:90] else 0 for r in self.rows])
        idx = np.argsort(-s)[:k]
        return [dict(self.rows[i], score=round(float(max(0.0, min(1.0, s[i]))), 3)) for i in idx]
