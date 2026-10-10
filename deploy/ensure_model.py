"""Make sure the Meta Llama 3.2 3B model file is the real model, not an unfetched Git LFS pointer.
Downloads it once (Hugging Face, bartowski/Llama-3.2-3B-Instruct-GGUF) into the data disk and verifies SHA-256."""
import hashlib
import os
import sys
import urllib.request

NAME = "Llama-3.2-3B-Instruct-Q4_K_S.gguf"
SHA256 = "bfb5db97e77e3927e18d971806e36d1886271d6c62e160d5bc78bcdbefb7197c"
URL = f"https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/{NAME}"
repo_copy = os.path.join("/app", "data", "models", "llm", NAME)
if os.path.exists(repo_copy) and os.path.getsize(repo_copy) > 1_000_000_000:
    sys.exit(0)
dst = os.path.join(os.environ.get("EST_DATA_DIR", "/var/data"), "llm", NAME)
if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000_000:
    os.environ["LLM_MODEL_PATH"] = dst
    sys.exit(0)
os.makedirs(os.path.dirname(dst), exist_ok=True)
print("[ensure_model] downloading", URL, flush=True)
h = hashlib.sha256()
with urllib.request.urlopen(URL, timeout=60) as r, open(dst + ".part", "wb") as f:
    while True:
        b = r.read(1 << 20)
        if not b:
            break
        h.update(b)
        f.write(b)
if h.hexdigest() != SHA256:
    os.remove(dst + ".part")
    sys.exit("[ensure_model] checksum mismatch - model discarded")
os.replace(dst + ".part", dst)
print("[ensure_model] model ready", dst, flush=True)
