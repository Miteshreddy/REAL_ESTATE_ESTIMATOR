# Model package

- `../data/models/floorplan_unet.onnx` — the model the app runs (CPU, ONNX Runtime).
- `weights/floorplan_unet_r34.pt` — the same model's PyTorch weights (U-Net, ResNet-34 encoder, 5 classes), for fine-tuning.
- `training/` — data preparation, training, evaluation and export scripts (CubiCasa5K). The dataset paths in them point to the dataset folder; change `--data` / the constants at the top if the dataset moves.
- `metrics/` — measured results on the train subset, validation and test splits, plus the training history.
- `ground_truth/` — the hand-labelled Tamil Nadu sheet ground truth used by `backend/tn_eval.py`.

Re-export after fine-tuning: `python training/export_onnx.py weights/floorplan_unet_r34.pt`
