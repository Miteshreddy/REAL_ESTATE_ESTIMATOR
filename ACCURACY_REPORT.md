# Accuracy Report — Drawing-Based Cost Estimation System

All figures below are **measured**, on data the system was **not trained or tuned on**, unless stated otherwise.
Each section names its data, its ground truth and the script that reproduces it.

---

## 1. Summary

| What is measured | Data | Result |
|---|---|---|
| Floor-plan segmentation (deep learning) | CubiCasa5K official **test** split, 399 plans never seen in training | Mean IoU 0.740 · walls 0.729 · rooms 0.898 · room detection F1 0.772 |
| Total project cost — CAD (DXF) | 10 unseen generated drawing sets, exact ground truth | **0.43 %** mean error, 100 % of sets within ±5 % |
| Total project cost — vector PDF (full set incl. structural) | 10 unseen generated drawing sets | **0.85 %** mean error, 100 % within ±5 % |
| Total project cost — scanned drawing | 10 unseen generated drawing sets | **0.72 %** mean error, 100 % within ±5 % |
| BOQ items within ±5 % of true quantity | same sets | 100 % (CAD), 99.8 % (PDF), 95.5 % (scan) |
| Room areas on **real government CAD drawings** | 6 Uttarakhand PWD type designs, 242 rooms, vs architects' written dimensions | **2.0 %** median error, 62.8 % within ±5 %, 78.5 % within ±10 % |
| PWD item mapping (NLP alone, no table) | 41 take-off items vs expert-chosen CPWD DSR 2023 items, 2,396-item library | **93 %** exact (top-1), 95 % in top-3 |
| PWD item mapping (system, table + NLP) | same | 48 / 51 items mapped; 3 flagged (electrical / tank — not in DSR civil volume) |

---

## 2. Floor-plan segmentation model

**Model:** U-Net with ImageNet-pretrained ResNet-34 encoder, 5 classes (background, wall, room, door, window).
**Training data:** CubiCasa5K — 4,199 training plans; augmentation for prints, scans, photocopies and real
sheet clutter (schedule tables, notes, title blocks, dimension lines, hatching, rotated text).
**Validation:** 399 official validation plans (model selection only). **Test:** 399 official test plans, used once.

### 2.1 Pixel metrics on the test set (399 unseen plans)
| Class | IoU | Precision | Recall | F1 |
|---|---|---|---|---|
| Wall | 0.729 | 78.2 % | 91.5 % | 0.843 |
| Room | 0.898 | 93.3 % | 95.9 % | 0.946 |
| Door | 0.616 | 70.3 % | 83.4 % | 0.763 |
| Window | 0.715 | 77.3 % | 90.6 % | 0.834 |

Mean IoU (foreground classes): **0.740** · Pixel accuracy: **93.1 %**

### 2.2 Object-level metrics on the test set (what the estimate depends on)
| Object | Precision | Recall | F1 | Matching rule |
|---|---|---|---|---|
| Room | 70.0 % | 86.1 % | 0.772 | IoU ≥ 0.5 (GT 4094, predicted 5037) |
| Door | 83.6 % | 89.9 % | 0.867 | IoU ≥ 0.3 (GT 4057, predicted 4362) |
| Window | 81.3 % | 83.1 % | 0.822 | IoU ≥ 0.3 (GT 3384, predicted 3458) |

### 2.3 Training vs unseen data (over-fitting check)
| | Training split | Validation | Test (unseen) |
|---|---|---|---|
| Mean IoU (foreground) | 0.731 | 0.741 | 0.740 |

A small gap between training and test means the model generalises rather than memorises.

Reproduce: `G:\velo\real-estate\training\evaluate_seg.py --split test`

---

## 3. Cost accuracy on unseen drawing sets (end to end)

Ground truth: each benchmark drawing set is generated from known geometry (seeds disjoint from all training).
The estimate produced from the **drawing** (drawing → quantities → DSR rates → cost) is compared with the
estimate produced from the **true geometry** through the same measurement rules — this isolates the error
introduced by reading the drawing.

| Format | Sets | Mean cost error | 90th percentile | Sets within ±5 % | BOQ items within ±5 % | Rooms found |
|---|---|---|---|---|---|---|
| CAD (DXF) | 10 | 0.43 % | 0.61 % | 100 % | 100 % | 100 % |
| Vector PDF (5-sheet set: 2 plans, section, foundation plan, schedules) | 10 | 0.85 % | 0.93 % | 100 % | 99.8 % | 100 % |
| Scanned image | 10 | 0.72 % | 1.10 % | 100 % | 95.5 % | 100 % |

Reproduce: `backend\benchmark.py 10 pdf,dxf,png` (results in `data\benchmark_results.json`).

---

## 4. Real government drawings

### 4.1 Uttarakhand PWD residential type designs (CAD, DWG → DXF)
Ground truth: the room dimensions the architects wrote on the drawings (e.g. “BED ROOM 3850 X 3500”).

| Drawing | Floor plans found | Labelled rooms | Median error | Within ±5 % | Within ±10 % |
|---|---|---|---|---|---|
| GEN_TY_3_P_ALL | 2 | 28 | 5.5 % | 42.9 % | 67.9 % |
| P_TY_5_Plans_ALL | 6 | 50 | 3.3 % | 54.0 % | 70.0 % |
| TY_1_Plans_ALL | 3 | 48 | 1.4 % | 100.0 % | 100.0 % |
| TY_2_P_ALL | 2 | 24 | 5.0 % | 50.0 % | 70.8 % |
| TY_4_P_ALL | 2 | 40 | 2.5 % | 55.0 % | 85.0 % |
| TY_4_P_ALLdwg | 4 | 52 | 2.3 % | 59.6 % | 71.2 % |
| **All** | | **242** | **2.02 %** | **62.8 %** | **78.5 %** |

Notes:
- Many rooms outside ±5 % are geometrically correct (outline follows the drawn walls) but the written label is
  nominal (e.g. excludes a niche or wardrobe recess). These are counted as errors anyway.
- Open-plan areas without walls between them (stair hall + passage) are measured as one space.

Reproduce: `backend\real_eval.py` (results in `data\real_eval_results.json`).

### 4.2 Tamil Nadu RD type designs (plotted PDF, combined sheets)
27 real TNRD sheets (plan + elevation + section + schedule + title block on one page, text often drawn as outlines).
Ground truth: hand-marked plan-view boxes and the plinth area written on each sheet (`G:elo
eal-estate	n_gt`).

| Measure | Before Indian-sheet work | Now |
|---|---|---|
| Plan view picked correctly (or "no plan" correctly reported) | 55.6 % | **88.9 %** (24 / 27) |
| Plinth area within ±5 % of the written value | 60 % | **81.2 %** (13 / 16) |
| Plinth area median error | — | **1.0 %** |

Remaining failures, stated plainly:
- VAO office, kitchen shed, cattle shed: no plan view found (very small or open structures).
- Library: only part of the building picked (plinth −22 %).
- Community hall 2: OCR misread the written plinth "288.35" as "222.35", so the scale is wrong (−23 %).
- Storage godown: +11 %.

Caveat: where the scale comes from the written plinth area, the plinth check is partly self-consistent. Room
splitting and room areas on these sheets are not yet validated against an approved estimate.

### 4.4 Commercial / institutional buildings (hospital, university, bank) — NOT yet supported
9 public tender drawings downloaded for this test (`ml/test_drawings/commercial`): AIIMS-type hospital IPD block
(LHMC, 4 floors), district hospital site layout (Bijnor), Nalanda University faculty and hostel plans (6), a bank
building drawing set (46 pages).

| Result | Value |
|---|---|
| Rooms found per plan | 1–27 (real plans hold 20–100+ rooms) |
| Scale found reliably | no — most sheets fell back to "layout" / assumed 1:100 |
| Room area error (49 matched labels, bank set) | median 59 %, 4 % within ±5 % |

**Verdict: the current build is not accurate on large commercial drawings.** Reasons: walls are drawn as
hatched double lines (not filled), dimensions are in cm with no plinth note, sheets are A0 with 100+ rooms,
and the model was trained only on residential plans (CubiCasa5K) and small government buildings.
Needed: dimension-string scale reading in cm/m, hatched-wall detection on vector PDFs, and fine-tuning on
50–100 labelled commercial plans.

### 4.3 End-to-end example — Uttarakhand Type-I quarters (G+2, 12 flats, original DWG)
- 3 floor plans detected (Ground, Typical First & Second, Second — duplicate floor removed) → 3 storeys
- Built-up area 561 m² · Total estimate **₹1.47 crore** (₹2,432 per sq ft) on CPWD DSR 2023 rates
- 13 structural items marked *assumed* (no structural drawing uploaded), 7 items flagged for rate review

---

## 5. Limits (stated plainly)
1. No real **approved estimate** was available, so total-cost accuracy on real drawings is not yet proven against
   an engineer's estimate. Supplying 3–5 past projects with their approved estimates closes this gap.
2. Real **structural** drawings are partly readable (marks, counts, bar callouts, slab thickness); sizes drawn only
   as graphical dimensions fall back to marked assumptions.
3. Poor-quality photos and hand sketches will score lower than CAD / vector PDF; the review step remains essential.
4. Seed rates are CPWD DSR 2023 (civil); state SORs must be imported for state works; E&M items need their own SOR.
