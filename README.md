# PWD Estimator

Drawing-based construction cost estimator for Tamil Nadu public works. Upload floor plans (PDF, DWG/DXF, scans or
images): the app reads the drawings, measures rooms, walls, doors and windows, takes off quantities, prices them with
the Tamil Nadu PWD Schedule of Rates 2025-26, and produces an itemised estimate with PDF and Excel reports.

## What runs where

| Part | Technology |
|---|---|
| App | FastAPI (Python 3.12), SQLite, vanilla JavaScript UI |
| Drawing reading | PyMuPDF, ezdxf, OpenCV, RapidOCR |
| Vision models (ONNX Runtime) | U-Net (ResNet-34) segmentation; YOLOv8m / YOLOv8s door-window detector |
| Classical ML / NLP | scikit-learn: room geometry, room labels, PWD item matching |
| Rates | TN PWD SOR 2025-26 + Standard Data (bundled snapshot); editable estimated rates where PWD has none |
| Assistant (optional) | Google Gemma 3 4B via llama.cpp, in-process: estimate summaries and reading web price pages (numbers checked) |
| Market check | curated public price pages + self-hosted SearXNG search; indicative ranges only, never PWD rates |

The estimate itself is always computed by the deterministic engine; the language model only explains it.

## Run on your computer (one click)

Download the repository (green **Code → Download ZIP**, or `git clone`), unzip, then:

| System | Run |
|---|---|
| **Windows** | double-click **`start.bat`** |
| **macOS / Linux** | in Terminal: `chmod +x start.sh && ./start.sh` |

The first run sets everything up automatically (about 10–20 minutes, needs internet):
Python 3.12 if missing (winget / Homebrew / apt) → a private environment `.venv` → all Python libraries → the llama.cpp
engine → the large model files (Gemma 3 4B is joined from two parts and checksum verified) (a ZIP download contains only Git LFS placeholders; they are downloaded and checksum
verified) → SearXNG web search. Later runs start in seconds. The app opens at http://127.0.0.1:8000.

Needs about 6 GB of free disk space. DWG files need Windows (bundled converter); PDF, DXF and images work everywhere.
Optional settings go in `.env` (`SEARXNG_URL`, `LLM_BACKEND` = `llamacpp` / `ollama` / `none`, `LLM_MODEL_PATH`,
`OLLAMA_URL`, `OLLAMA_MODEL`).

Tests: `.venv` python `-m pip install -r requirements-dev.txt`, then `-m pytest backend/tests -q`.

## Deploy on Render

The repository contains `render.yaml` (Blueprint) and a `Dockerfile` that runs the app, the Gemma model and SearXNG in
one service. In Render: **New → Blueprint → this repository**. About 4–6 GB of memory is needed with the language model on; set
`LLM_BACKEND=none` for smaller plans. Project data lives on the attached disk (`/var/data`).

Large files are stored with **Git LFS** (the Gemma model in two parts, the YOLOv8m model). If a host clones LFS pointers
only, the app falls back to YOLOv8s and downloads the Gemma file once with checksum verification (`deploy/ensure_model.py`).

## Licences

Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms (copies in `data/models/llm/`).
LibreDWG converter (`tools/libredwg`, Windows only) is GPL-3. SearXNG is AGPL-3.0 (installed at build time, unmodified).
