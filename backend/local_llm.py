"""Local open-weights LLM (Google Gemma 3 4B) running on this machine — no cloud API, no key, no data leaves the server.

Engine: llama.cpp in-process (llama-cpp-python). Model file LLM_MODEL_PATH, default
data/models/llm/google_gemma-3-4b-it-Q4_K_M.gguf (Gemma 3 4B instruction-tuned, 4-bit, 2.49 GB; stored as two Git LFS
parts and joined at setup, see model_file.py). LLM_BACKEND=none switches the assistant off. LLM_GPU_LAYERS offloads
layers to a GPU when llama-cpp-python was built with GPU support.

Two jobs, both grounded so the model cannot invent numbers:
  extract_rates(text)  construction ₹/sq ft figures from a web page; each figure must come with a quote whose
                       numbers really appear in the page, otherwise it is dropped
  summarise(facts)     a plain-language explanation of an estimate written ONLY from the facts given; every number in
                       the reply must appear in the facts (else the summary is rejected and the caller shows none)
Callers fall back to rule-based code whenever no model is available.
Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms (data/models/llm/).
"""
from __future__ import annotations

import json
import os
import re
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GGUF = os.path.join(ROOT, "data", "models", "llm", "google_gemma-3-4b-it-Q4_K_M.gguf")
_LLM, _LOCK = None, threading.Lock()


def _gguf() -> str:
    import model_file
    model_file.ensure_joined()  # the repo ships the model in two parts; join once (checksum verified)
    return _gguf_path()


def _gguf_path() -> str:
    """LLM_MODEL_PATH > the repo copy (Git LFS, joined by model_file.py) > a copy in the data folder (EST_DATA_DIR/llm)."""
    if os.environ.get("LLM_MODEL_PATH"):
        return os.environ["LLM_MODEL_PATH"]
    alt = os.path.join(os.environ.get("EST_DATA_DIR") or os.path.join(ROOT, "data"), "llm", os.path.basename(DEFAULT_GGUF))
    for p in (DEFAULT_GGUF, alt):
        if os.path.exists(p) and os.path.getsize(p) > 50_000_000:
            return p
    return DEFAULT_GGUF


def backend() -> str:
    return "none" if os.environ.get("LLM_BACKEND") == "none" else "llamacpp"


def _gguf_ok() -> bool:
    try:  # a Git LFS pointer (not fetched) is a tiny text file, not a model
        return os.path.getsize(_gguf()) > 50_000_000
    except OSError:
        return False


def model() -> str:
    return os.path.basename(_gguf_path()).replace(".gguf", "")


GEMMA_LAYERS, GEMMA_VRAM_MB = 34, 3600  # Gemma 3 4B Q4 + 8k context on the GPU


def gpu_layers() -> int:
    """LLM_GPU_LAYERS (number, -1 = all, 0 = CPU only) or 'auto' (default): all layers when the GPU has room, a
    proportional share when it is tight (the rest runs on the CPU), 0 without GPU support in the installed engine."""
    v = os.environ.get("LLM_GPU_LAYERS", "auto")
    if v != "auto":
        return int(v)
    try:
        import llama_cpp
        if not llama_cpp.llama_supports_gpu_offload():
            return 0
    except Exception:
        return 0
    free = _free_vram_mb()
    if free is None:  # GPU present but memory unknown (AMD / Intel / Apple): try all, the loader falls back to CPU
        return -1
    if free >= GEMMA_VRAM_MB:
        return -1
    return max(0, int(GEMMA_LAYERS * (free - 600) / GEMMA_VRAM_MB))


def _free_vram_mb() -> int | None:
    import shutil
    import subprocess
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout.split()
        return max(int(x) for x in out) if out else None
    except Exception:
        return None


def _llamacpp():
    """Load once. GPU + CPU split per gpu_layers(); if the GPU load fails, CPU only (the app never depends on a GPU)."""
    global _LLM, LOADED_ON
    if _LLM is None:
        from llama_cpp import Llama
        kw = dict(model_path=_gguf(), n_ctx=8192, n_threads=max(1, (os.cpu_count() or 2) - 1), verbose=False)
        n = gpu_layers()
        if n:
            try:  # one GPU (LLM_MAIN_GPU, default 0 = first device); not split across a discrete + integrated GPU
                _LLM = Llama(n_gpu_layers=n, split_mode=0, main_gpu=int(os.environ.get("LLM_MAIN_GPU", "0")), **kw)
                LOADED_ON = f"GPU ({'all' if n < 0 else n} of {GEMMA_LAYERS} layers) + CPU"
            except Exception:
                _LLM = None
        if _LLM is None:
            _LLM = Llama(n_gpu_layers=0, **kw)
            LOADED_ON = "CPU"
    return _LLM


LOADED_ON = None


def can_extract() -> bool:
    """Reading web price pages needs a capable model. Measured on three real price pages (CPU): Llama 3.2 1B / 3B missed
    or misread most figures, Gemma 3 4B read all three. LLM_EXTRACT=0 switches page reading off (summaries stay)."""
    return os.environ.get("LLM_EXTRACT", "1") == "1" and available()


def available() -> bool:
    if backend() == "none":
        return False
    try:
        import llama_cpp  # noqa: F401
    except ImportError:
        return False
    return _gguf_ok()


def _chat(system: str, user: str, as_json: bool = False, num_predict: int = 900) -> str | None:
    """One completion, or None (model missing / failed) — the caller then uses rule-based code. JSON is requested in
    the prompt: llama.cpp's strict JSON mode made Gemma return '{}'."""
    if not available():
        return None
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        with _LOCK:  # one generation at a time (the model is shared by all requests)
            out = _llamacpp().create_chat_completion(messages=msgs, temperature=0, top_p=0.9, max_tokens=num_predict)
        return out["choices"][0]["message"]["content"]
    except Exception:  # never break the app because of the assistant
        return None


def _json_part(text: str) -> str:
    """The JSON object inside a reply that may be wrapped in ``` fences or prose."""
    a, b = text.find("{"), text.rfind("}")
    return text[a:b + 1] if a >= 0 and b > a else "{}"


def _windows(text: str, size: int = 150, limit: int = 4500) -> str:
    parts = [text[max(0, m.start() - size): m.end() + size] for m in re.finditer(r"₹|rs\.?\s*\d|inr", text, re.I)]
    out, n = [], 0
    for p in parts:
        if n + len(p) > limit:
            break
        out.append(p)
        n += len(p)
    return " … ".join(out)


EXTRACT_SYS = ("You extract data. Reply with JSON only. You never guess: if the text does not state a figure, you do not list it.")
EXTRACT_USER = """List every BUILDING CONSTRUCTION cost per square foot stated in the text (excluding land).
JSON format: {"figures":[{"rate_per_sqft":number,"quality":"basic|standard|premium|luxury|unknown","city":string|null,"quote":"exact words from the text containing the number"}]}
Rules: per m² → divide by 10.764; a range → its midpoint; ignore land price, rent, interiors, single items and material prices.

TEXT:
"""


def extract_rates(text: str) -> list[dict] | None:
    """Figures with quality tier, or None when the model is unavailable (caller uses the regex parser)."""
    if not can_extract():
        return None
    body = _windows(text or "")
    if not body:
        return []
    out = _chat(EXTRACT_SYS, EXTRACT_USER + body, True)
    if out is None:
        return None
    try:
        figs = json.loads(_json_part(out)).get("figures") or []
    except (ValueError, AttributeError):
        return None
    page_digits = re.sub(r"[,\s]", "", text)
    res = []
    for f in figs if isinstance(figs, list) else []:
        try:
            v = float(f.get("rate_per_sqft"))
        except (TypeError, ValueError, AttributeError):
            continue
        nums = [x.replace(",", "") for x in re.findall(r"\d[\d,]{2,}", str(f.get("quote") or ""))]
        if not nums or not all(n in page_digits for n in nums):  # the quoted number must be on the page
            continue
        res.append(dict(value=round(v, 1), quality=str(f.get("quality") or "unknown").lower(), city=f.get("city"), quote=str(f.get("quote"))[:160]))
    return res


SUMMARY_SYS = ("You are a quantity surveyor writing for a client. Use ONLY the facts provided. Do not add numbers, rates, "
               "or claims that are not in the facts. Plain English, short sentences, no markdown headings.")
SUMMARY_USER = """Write a summary of this construction estimate in 5 short bullet points (each starting with "- "):
1) what is estimated and its total; 2) what drives the cost (top categories); 3) how reliable it is and why (status, scale,
assumptions); 4) how it compares with the market check, if given; 5) the single most useful next step for the user.

FACTS (JSON):
"""


def _numbers(s: str) -> set[str]:
    return {re.sub(r"[,\s]", "", x).rstrip(".") for x in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


def summarise(facts: dict) -> dict | None:
    """{'text', 'model'} or None. Rejected when the reply contains a number that is not in the facts."""
    blob = json.dumps(facts, ensure_ascii=False, default=str)
    out = _chat(SUMMARY_SYS, SUMMARY_USER + blob, False, num_predict=500)
    if not out:
        return None
    allowed = _numbers(blob) | {str(i) for i in range(0, 11)}
    # numbers may be written as lakh/crore conversions of the facts: allow those derived forms too
    for v in list(allowed):
        try:
            f = float(v)
        except ValueError:
            continue
        for d in (1e5, 1e7):
            allowed |= {f"{f / d:.1f}", f"{f / d:.2f}", f"{f / d:.0f}"}
    bad = [n for n in _numbers(out) if n not in allowed and n.lstrip("0") not in allowed]
    if bad:
        return dict(text=None, rejected=True, reason=f"model wrote numbers not in the estimate ({', '.join(bad[:5])})", model=model())
    return dict(text=out.strip(), model=model(), rejected=False)
