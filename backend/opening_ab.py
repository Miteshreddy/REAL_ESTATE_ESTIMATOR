"""A/B check for raster opening detection (wall-interruption merge on/off) on SYNTHETIC PNG plans with exact ground
truth. Run before adopting a change to the opening detector so a better real-drawing count never hides a regression.
Usage: python opening_ab.py [n]"""
import os
import sys
import tempfile

import numpy as np

import benchmark
import parsers
import samples
from ml import Models

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
FLAG = sys.argv[2] if len(sys.argv) > 2 else "EST_GAP_MERGE"
models = Models(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models"))
tmp = tempfile.mkdtemp()
res = {}
for mode in ("0", "1"):
    os.environ[FLAG] = mode
    d_err, w_err, d_exact, w_exact = [], [], 0, 0
    for i in range(n):
        seed = 81000 + i * 13
        rng = np.random.default_rng(seed)
        g = samples.generate_plan(seed, round(float(rng.uniform(6.5, 16)), 1), round(float(rng.uniform(6, 13)), 1))
        path = os.path.join(tmp, f"p{seed}.png")
        samples.render_png(g, path)
        sp = [s for s in parsers.parse_any(path, models) if s.get("kind") == "floor_plan"][0]
        gt = benchmark.gt_sheet(g, sp, "Ground floor", 0, columns_visible=False)
        for kind, errs in (("door", d_err), ("window", w_err)):
            a = sum(1 for o in sp["openings"] if o["kind"] == kind)
            b = sum(1 for o in gt["openings"] if o["kind"] == kind)
            errs.append(abs(a - b) / max(1, b))
    res[mode] = dict(door_count_mape=round(float(np.mean(d_err)) * 100, 2), door_exact=float(np.mean([e == 0 for e in d_err])) * 100,
                     window_count_mape=round(float(np.mean(w_err)) * 100, 2), window_exact=float(np.mean([e == 0 for e in w_err])) * 100)
    print(FLAG, mode, res[mode], flush=True)
