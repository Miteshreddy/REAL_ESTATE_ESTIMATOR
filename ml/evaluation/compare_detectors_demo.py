"""YOLOv8s vs YOLOv8m through the APP's real inference path on the 5 synthetic demo images (no training).

    python ml/evaluation/compare_detectors_demo.py [out.json]

Reference ("marker truth"): the demo generator draws doors as RED bars and windows as BLUE bars on the walls. They are
counted by colour inside the building's wall frame (the legend swatches below the plan are excluded). This is the
generator's own definition for these SYNTHETIC images — not real-drawing or Tamil Nadu accuracy.
A detection is a true positive if its centre falls within a not-yet-matched marker of the same class (marker box
expanded by 0.3 m); one-to-one.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
DEMO = os.path.join(ROOT, "data", "demo_tn5")
MODELS = ["opening_det.onnx", "opening_det_v8m.onnx"]


def markers(img):
    b, g, r = [img[:, :, i].astype(int) for i in range(3)]
    dark = ((b < 70) & (g < 70) & (r < 70)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    walls = [k for k in range(1, n) if max(st[k, 2], st[k, 3]) >= 150]  # long wall segments (markers split the frame)
    x0 = min(st[k, 0] for k in walls); y0 = min(st[k, 1] for k in walls)
    x1 = max(st[k, 0] + st[k, 2] for k in walls); y1 = max(st[k, 1] + st[k, 3] for k in walls)
    w, h = x1 - x0, y1 - y0
    out = {}
    for kind, m in (("door", (r > 180) & (g < 90) & (b < 90)), ("window", (b > 180) & (r < 90) & (g < 160))):
        n, lab, st2, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        boxes = []
        for k in range(1, n):
            bx, by, bw, bh, a = st2[k]
            cx, cy = bx + bw / 2, by + bh / 2
            if a >= 40 and x0 - 15 <= cx <= x0 + w + 15 and y0 - 15 <= cy <= y0 + h + 15:  # inside the plan, not the legend
                boxes.append((bx, by, bx + bw, by + bh))
        out[kind] = boxes
    return out, (x0, y0, x0 + w, y0 + h)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "reports_v2", "door_window_audit", "demo5_detector_comparison.json")
    import parsers
    import detector
    from ml import Models
    models = Models(os.path.join(ROOT, "data", "models"))
    res = dict(note="SYNTHETIC demo images; reference = generator's red (door) / blue (window) markers inside the plan", images={}, models={})
    imgs = sorted(glob.glob(os.path.join(DEMO, "*.png")))
    for mf in MODELS:
        os.environ["EST_DETECTOR_MODEL"] = mf
        tot = {k: dict(tp=0, fp=0, fn=0, ref=0, geometry=0, combined=0) for k in ("door", "window")}
        times = []
        for ip in imgs:
            img = cv2.imread(ip)
            ref, frame = markers(img)
            t0 = time.perf_counter()
            sheets = parsers.parse_any(ip, models)
            dt = time.perf_counter() - t0
            times.append(dt)
            plan = next((s for s in sheets if s.get("kind") == "floor_plan"), sheets[0])
            ppm = plan["scale"]["px_per_m"] / plan["scale"].get("analysis_downscale", 1.0) if plan.get("scale", {}).get("px_per_m") else None
            dets = detector.detect(img, plan["scale"]["px_per_m"]) if plan.get("scale", {}).get("px_per_m") else []
            row = dict(model_used=plan.get("detector_model"), seconds=round(dt, 2), rooms=len(plan.get("rooms") or []))
            for k in ("door", "window"):
                R = ref[k]
                D = [d for d in dets if d["kind"] == k]
                pad = 0.3 * (ppm or 40)
                used, tp = set(), 0
                for d in sorted(D, key=lambda d: -d["score"]):
                    j = next((j for j, (a, b, c, e) in enumerate(R) if j not in used and a - pad <= d["x_px"] <= c + pad and b - pad <= d["y_px"] <= e + pad), None)
                    if j is not None:
                        used.add(j)
                        tp += 1
                geo = sum(1 for o in plan.get("openings") or [] if o["kind"] == k and o.get("source") != "detector")
                comb = sum(1 for o in plan.get("openings") or [] if o["kind"] == k)
                row[k] = dict(reference=len(R), detector=len(D), detector_tp=tp, detector_fp=len(D) - tp, detector_fn=len(R) - tp,
                              geometry=geo, combined_in_app=comb, app_detector_count=(plan.get("detector_counts") or {}).get(k))
                for f, v in (("tp", tp), ("fp", len(D) - tp), ("fn", len(R) - tp), ("ref", len(R)), ("geometry", geo), ("combined", comb)):
                    tot[k][f] += v
            res["images"].setdefault(os.path.basename(ip), {})[mf] = row
            print(mf, os.path.basename(ip), {k: row[k] for k in ("door", "window")}, row["seconds"], "s", flush=True)
        summ = {}
        for k, v in tot.items():
            p = v["tp"] / max(1, v["tp"] + v["fp"])
            r = v["tp"] / max(1, v["ref"])
            summ[k] = dict(v, precision=round(p, 3), recall=round(r, 3), f1=round(2 * p * r / max(1e-9, p + r), 3))
        res["models"][mf] = dict(totals=summ, mean_seconds_per_image=round(float(np.mean(times)), 2),
                                 file_mb=round(os.path.getsize(os.path.join(ROOT, "data", "models", mf)) / 1e6, 1))
    os.environ.pop("EST_DETECTOR_MODEL", None)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(res, open(out_path, "w"), indent=1)
    print(json.dumps(res["models"], indent=1))


if __name__ == "__main__":
    main()
