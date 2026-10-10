"""Local open-source LLM (Meta Llama) running on this machine — no cloud API, no key, no data leaves the server.

Backends (LLM_BACKEND, default 'llamacpp' when the model file exists, else 'ollama'):
    llamacpp  in-process llama.cpp (llama-cpp-python); model file LLM_MODEL_PATH, default
              data/models/llm/Llama-3.2-3B-Instruct-Q4_K_S.gguf (Meta Llama 3.2 3B Instruct, 4-bit, 1.93 GB, Git LFS)
    ollama    optional local Ollama server (OLLAMA_URL, OLLAMA_MODEL) — e.g. Llama 3.1 8B on a GPU workstation

Two jobs, both grounded so the model cannot invent numbers:
  extract_rates(text)  construction ₹/sq ft figures from a web page; each figure must come with a quote whose
                       numbers really appear in the page, otherwise it is dropped
  summarise(facts)     a plain-language explanation of an estimate written ONLY from the facts given; every number in
                       the reply must appear in the facts (else the summary is rejected and the caller shows none)
Callers fall back to rule-based code whenever no model is available.
Built with Llama — Llama 3.2 is licensed under the Llama 3.2 Community License (see data/models/llm/LICENSE).
"""
from __future__ import annotations

import json
import os
import re
import threading

import requests

TIMEOUT = 120
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GGUF = os.path.join(ROOT, "data", "models", "llm", "Llama-3.2-3B-Instruct-Q4_K_S.gguf")
_LLM, _LOCK = None, threading.Lock()


def _gguf() -> str:
    """LLM_MODEL_PATH > the repo copy (Git LFS) > a copy fetched into the data disk by deploy/ensure_model.py."""
    if os.environ.get("LLM_MODEL_PATH"):
        return os.environ["LLM_MODEL_PATH"]
    alt = os.path.join(os.environ.get("EST_DATA_DIR") or os.path.join(ROOT, "data"), "llm", os.path.basename(DEFAULT_GGUF))
    for p in (DEFAULT_GGUF, alt):
        if os.path.exists(p) and os.path.getsize(p) > 50_000_000:
            return p
    return DEFAULT_GGUF


def backend() -> str:
    b = os.environ.get("LLM_BACKEND")
    if b:
        return b
    return "llamacpp" if _gguf_ok() else "ollama"


def _gguf_ok() -> bool:
    try:  # a Git LFS pointer (not fetched) is a tiny text file, not a model
        return os.path.getsize(_gguf()) > 50_000_000
    except OSError:
        return False


def _url():
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def model() -> str:
    if backend() == "llamacpp":
        return os.path.basename(_gguf()).replace(".gguf", "")
    return os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


def _llamacpp():
    global _LLM
    if _LLM is None:
        from llama_cpp import Llama
        _LLM = Llama(model_path=_gguf(), n_ctx=8192, n_threads=max(1, (os.cpu_count() or 2) - 1),
                     n_gpu_layers=int(os.environ.get("LLM_GPU_LAYERS", "0")), verbose=False)
    return _LLM


def can_extract() -> bool:
    """Reading web price pages needs a strong model: measured on real pages, Llama 3.2 1B / 3B missed or misread most
    figures, Llama 3.1 8B read every tier correctly. Small in-app models are used only for summaries (LLM_EXTRACT=1 forces)."""
    if os.environ.get("LLM_EXTRACT") == "1":
        return available()
    return backend() == "ollama" and "8b" in model().lower() and available()


def available() -> bool:
    if backend() == "none":  # switched off (e.g. a small server plan)
        return False
    if backend() == "llamacpp":
        try:
            import llama_cpp  # noqa: F401
        except ImportError:
            return False
        return _gguf_ok()
    try:
        r = requests.get(_url() + "/api/tags", timeout=3)
        return r.ok and any(m.get("name", "").startswith(model().split(":")[0]) for m in r.json().get("models", []))
    except requests.RequestException:
        return False


def _chat(system: str, user: str, as_json: bool, num_predict: int = 900) -> str | None:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if backend() == "llamacpp":
        if not available():
            return None
        try:
            with _LOCK:  # one generation at a time (the model is shared by all requests)
                out = _llamacpp().create_chat_completion(messages=msgs, temperature=0, top_p=0.9, max_tokens=num_predict,
                                                         response_format={"type": "json_object"} if as_json else None)
            return out["choices"][0]["message"]["content"]
        except Exception:  # never break the app because of the assistant
            return None
    try:
        r = requests.post(_url() + "/api/chat", timeout=TIMEOUT, json=dict(
            model=model(), stream=False, format="json" if as_json else None, keep_alive="10m",
            options=dict(temperature=0, top_p=0.9, num_ctx=8192, num_predict=num_predict), messages=msgs))
        r.raise_for_status()
        return r.json().get("message", {}).get("content")
    except (requests.RequestException, ValueError):
        return None


def _windows(text: str, size: int = 180, limit: int = 9000) -> str:
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
        figs = json.loads(out).get("figures") or []
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
