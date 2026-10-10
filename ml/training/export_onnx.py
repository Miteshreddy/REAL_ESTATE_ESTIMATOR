"""Export the trained segmentation model to ONNX for the application (no PyTorch needed at runtime)."""
import os
import shutil
import sys

import torch

from train_seg import make_model

W = sys.argv[1] if len(sys.argv) > 1 else r"G:\velo\real-estate\runs\unet_r34\best.pt"
OUT = r"G:\velo\real-estate\runs\unet_r34\floorplan_unet.onnx"
APP = r"C:\Users\Mitesh Reddy\Desktop\assignment\real estate\data\models\floorplan_unet.onnx"

model = make_model()
model.load_state_dict(torch.load(W, map_location="cpu"))
model.eval()
x = torch.zeros(1, 1, 512, 512)
torch.onnx.export(model, x, OUT, input_names=["image"], output_names=["logits"], opset_version=17,
                  dynamic_axes={"image": {2: "h", 3: "w"}, "logits": {2: "h", 3: "w"}}, dynamo=False)
shutil.copy(OUT, APP)
print("exported", OUT, os.path.getsize(OUT) // 2**20, "MB -> copied to app")
