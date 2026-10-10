"""Run after training: evaluate (test / val / train subset), export ONNX + metadata to the app,
and fill the model placeholders in ACCURACY_REPORT.md."""
import glob
import json
import os
import random
import shutil
import subprocess
import sys

RUN = r"G:\velo\real-estate\runs\unet_r34_v2"
APP = r"C:\Users\Mitesh Reddy\Desktop\assignment\real estate"
PY = sys.executable


def ev(split):
    out = subprocess.run([PY, "evaluate_seg.py", "--weights", os.path.join(RUN, "best.pt"), "--split", split],
                         capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
    if out.returncode:
        print(out.stderr[-2000:])
        raise SystemExit(1)
    return json.load(open(os.path.join(RUN, f"metrics_{split}.json")))


# a 400-plan training subset for the over-fitting check
sub = os.path.join(r"G:\velo\real-estate\prepared", "trainsub")
if not os.path.exists(sub):
    random.seed(0)
    files = random.sample(sorted(glob.glob(r"G:\velo\real-estate\prepared\train\img\*.png")), 400)
    for d in ("img", "mask"):
        os.makedirs(os.path.join(sub, d), exist_ok=True)
    for f in files:
        shutil.copy(f, os.path.join(sub, "img", os.path.basename(f)))
        shutil.copy(f.replace("\\img\\", "\\mask\\"), os.path.join(sub, "mask", os.path.basename(f)))

test, val, train = ev("test"), ev("val"), ev("trainsub")
subprocess.run([PY, "export_onnx.py", os.path.join(RUN, "best.pt")], check=True, cwd=os.path.dirname(os.path.abspath(__file__)))

meta = dict(model="U-Net / ResNet-34 (ImageNet), 5 classes", trained_on="CubiCasa5K 4,199 plans + sheet-clutter augmentation",
            test=dict(miou_fg=test["miou_fg"], iou=test["iou"], objects=test["objects"]),
            val_miou_fg=val["miou_fg"], train_subset_miou_fg=train["miou_fg"],
            history=json.load(open(os.path.join(RUN, "history.json"))))
json.dump(meta, open(os.path.join(APP, "data", "models", "floorplan_unet.json"), "w"), indent=1)

pct = lambda v: f"{v * 100:.1f} %"
cls = ["wall", "room", "door", "window"]
pix = "\n".join(f"| {c.title()} | {test['iou'][c]:.3f} | {pct(test['precision'][c])} | {pct(test['recall'][c])} | {test['f1'][c]:.3f} |" for c in cls)
rule = {"room": "IoU ≥ 0.5", "door": "IoU ≥ 0.3", "window": "IoU ≥ 0.3"}
obj = "\n".join(f"| {k.title()} | {pct(v['precision'])} | {pct(v['recall'])} | {v['f1']:.3f} | {rule[k]} (GT {v['gt']}, predicted {v['pred']}) |" for k, v in test["objects"].items())
summ = (f"Mean IoU {test['miou_fg']:.3f} · walls {test['iou']['wall']:.3f} · rooms {test['iou']['room']:.3f} · "
        f"room detection F1 {test['objects']['room']['f1']:.3f}")
rp = os.path.join(APP, "ACCURACY_REPORT.md")
r = open(rp, encoding="utf-8").read()
for k, v in {"{{SEG_SUMMARY}}": summ, "{{SEG_PIXEL_TABLE}}": pix, "{{SEG_OBJ_TABLE}}": obj, "{{SEG_MIOU}}": f"{test['miou_fg']:.3f}",
             "{{SEG_PIXACC}}": pct(test["pixel_acc"]), "{{SEG_TRAIN_MIOU}}": f"{train['miou_fg']:.3f}", "{{SEG_VAL_MIOU}}": f"{val['miou_fg']:.3f}"}.items():
    r = r.replace(k, v)
open(rp, "w", encoding="utf-8").write(r)
print(json.dumps(dict(test=test["miou_fg"], val=val["miou_fg"], train=train["miou_fg"], objects=test["objects"]), indent=1))
