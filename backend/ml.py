"""Machine-learning models.

1. PrimitiveClassifier  - RandomForest that classifies vector PDF drawing primitives into
                          wall / door / window / column / furniture / dimension / other.
                          Trained on hundreds of procedurally generated, randomly styled plans
                          rendered through the *same* PDF extraction path used at inference.
2. RoomGeomClassifier   - GradientBoosting classifier predicting room type from geometry when
                          a drawing has no readable label (raster scans).
3. RoomLabelModel       - (nlp.py) TF-IDF char+word n-gram logistic regression for room labels.
"""
from __future__ import annotations

import os
import random
import time

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import train_test_split

import nlp
import samples

MODEL_VERSION = 5


def _type_of(name: str) -> str:
    n = name.upper()
    for k, t in [("TOILET", "toilet"), ("BED", "bedroom"), ("KITCHEN", "kitchen"), ("LIVING", "living"),
                 ("DINING", "dining"), ("STUDY", "study"), ("STORE", "store"), ("POOJA", "pooja"), ("UTILITY", "utility")]:
        if k in n:
            return t
    return "bedroom"


# ------------------------------------------------------------------------------------------
class PrimitiveClassifier:
    def __init__(self):
        self.model = None
        self.report = {}

    def train(self, n_plans=70, seed=7):
        import pymupdf as fitz
        from parsers import _page_med_short, pdf_primitive_features
        rng = random.Random(seed)
        X, y = [], []
        for i in range(n_plans):
            plan = samples.generate_plan(seed=1000 + i)
            style = dict(wall_fill=rng.choice([(0.22, 0.22, 0.24), (0, 0, 0), (0.5, 0.5, 0.5), (0.35, 0.3, 0.3), (0.75, 0.75, 0.75)]),
                         wall_lw=rng.choice([0.2, 0.4, 0.8]), door_lw=rng.choice([0.3, 0.6, 1.0]),
                         scale_den=rng.choice([50, 75, 100, 100, 100]), furniture=rng.random() < 0.7, seed=i)
            ann = []
            doc = samples.render_pdf(plan, None, style, ann)
            page = doc[0]
            dr = page.get_drawings()
            med = _page_med_short(dr)
            for d in dr:
                r = d["rect"]
                best, lbl = 0.0, "other"
                for a_lbl, ar in ann:
                    inter = (r & ar)
                    if inter.is_empty and not (r.is_empty or ar.is_empty):
                        # zero-area lines: compare by containment
                        if ar.contains(r) or (abs(r.x0 - ar.x0) + abs(r.y0 - ar.y0) + abs(r.x1 - ar.x1) + abs(r.y1 - ar.y1) < 1.0):
                            iou = 0.9
                        else:
                            continue
                    else:
                        ra, aa = r.get_area(), ar.get_area()
                        if ra > 0 and aa <= 4.5 * ra:
                            iou = inter.get_area() / ra
                        else:
                            ua = ra + aa - inter.get_area()
                            iou = inter.get_area() / ua if ua > 0 else (0.9 if ar.contains(r) else 0)
                    if iou > best:
                        best, lbl = iou, a_lbl
                if best < 0.5:
                    lbl = "other"
                X.append(pdf_primitive_features(d, med))
                y.append(lbl)
            doc.close()
        X, y = np.array(X), np.array(y)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0, stratify=y)
        self.model = RandomForestClassifier(n_estimators=160, min_samples_leaf=1, n_jobs=-1, random_state=0, class_weight="balanced")
        self.model.fit(Xtr, ytr)
        acc = float((self.model.predict(Xte) == yte).mean())
        self.model.fit(X, y)
        self.report = dict(samples=int(len(y)), holdout_accuracy=round(acc, 4),
                           classes={c: int((y == c).sum()) for c in np.unique(y)})

    def predict(self, X):
        if len(X) == 0:
            return np.array([]), np.array([])
        p = self.model.predict_proba(X)
        return self.model.classes_[p.argmax(1)], p.max(1)


# ------------------------------------------------------------------------------------------
class RoomGeomClassifier:
    def __init__(self):
        self.model = None
        self.report = {}

    @staticmethod
    def feats(f, plinth):
        return [f["area"], f["aspect"], f["min_side"], 1.0 if f["touches_ext"] else 0.0, f["area"] / max(plinth, 1)]

    def train(self, n_plans=900):
        X, y = [], []
        for i in range(n_plans):
            p = samples.generate_plan(seed=50000 + i)
            plinth = p["W"] * p["H"]
            for r in p["rooms"]:
                w, h = r["dims"]
                x0, y0 = r["poly"][0]
                ext = x0 < 1e-6 or y0 < 1e-6 or abs(x0 + w - p["W"]) < 1e-6 or abs(y0 + h - p["H"]) < 1e-6
                X.append(self.feats(dict(area=w * h, aspect=max(w, h) / min(w, h), min_side=min(w, h), touches_ext=ext), plinth))
                y.append(_type_of(r["name"]))
        X, y = np.array(X), np.array(y)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
        self.model = GradientBoostingClassifier(n_estimators=120, max_depth=3, random_state=0).fit(Xtr, ytr)
        self.report = dict(samples=int(len(y)), holdout_accuracy=round(float((self.model.predict(Xte) == yte).mean()), 4))

    def predict(self, f, plinth):
        p = self.model.predict_proba([self.feats(f, plinth)])[0]
        i = int(p.argmax())
        return self.model.classes_[i], float(p[i])


# ------------------------------------------------------------------------------------------
class Models:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"models_v{MODEL_VERSION}.joblib")
        self.room_label = nlp.RoomLabelModel()
        if os.path.exists(path):
            d = joblib.load(path)
            self.primitive, self.room_geom, self.train_time = d["primitive"], d["room_geom"], d["t"]
        else:
            t0 = time.time()
            print("[ml] training models on synthetic drawings (first run only)...", flush=True)
            self.primitive = PrimitiveClassifier()
            self.primitive.train()
            print("[ml] primitive classifier:", self.primitive.report, flush=True)
            self.room_geom = RoomGeomClassifier()
            self.room_geom.train()
            print("[ml] room geometry classifier:", self.room_geom.report, flush=True)
            self.train_time = round(time.time() - t0, 1)
            joblib.dump(dict(primitive=self.primitive, room_geom=self.room_geom, t=self.train_time), path)

    def info(self):
        return {
            "primitive_classifier": dict(algo="RandomForest (160 trees, 15 geometric/style features)", **self.primitive.report),
            "room_geometry_classifier": dict(algo="Gradient Boosting (5 features)", **self.room_geom.report),
            "room_label_nlp": dict(algo="TF-IDF char(2-4)+word n-grams -> Logistic Regression", classes=len(nlp.ROOM_TYPES)),
            "sor_matcher": dict(algo="TF-IDF word(1-2)+char(3-5) cosine + unit/category priors"),
            "train_seconds": self.train_time,
        }
