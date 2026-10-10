"""Make sure the Gemma 3 4B model is available: join the two repo parts (Git LFS) or, if the host cloned only LFS
pointers, download the file once from Hugging Face (bartowski/google_gemma-3-4b-it-GGUF) into the data disk; SHA-256 verified."""
import hashlib
import os
import sys
import urllib.request

NAME = "google_gemma-3-4b-it-Q4_K_M.gguf"
SHA256 = "4996030242583a40aa151ff93f49ed787ac8c25e4120c3ae4588b2e2a7d1ae94"
URL = f"https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/{NAME}"
sys.path.insert(0, "/app/backend")
import model_file  # noqa: E402

model_file.ensure_joined(verbose=True)
repo_copy = os.path.join("/app", "data", "models", "llm", NAME)
if os.path.exists(repo_copy) and os.path.getsize(repo_copy) > 2_000_000_000:
    sys.exit(0)
dst = os.path.join(os.environ.get("EST_DATA_DIR", "/var/data"), "llm", NAME)
if os.path.exists(dst) and os.path.getsize(dst) > 2_000_000_000:
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
