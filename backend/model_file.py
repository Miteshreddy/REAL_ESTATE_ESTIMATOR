"""The Gemma 3 4B model file is 2.49 GB — over GitHub's 2 GB per-file limit for Git LFS — so the repository stores it
as two parts (<name>.part1 / .part2). ensure_joined() rebuilds the original file once and verifies its SHA-256; a
mismatch discards the result (the app then runs without the language model)."""
from __future__ import annotations

import hashlib
import os
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "data", "models", "llm")
NAME = "google_gemma-3-4b-it-Q4_K_M.gguf"
SIZE = 2489758112
SHA256 = "4996030242583a40aa151ff93f49ed787ac8c25e4120c3ae4588b2e2a7d1ae94"
_LOCK = threading.Lock()


def _parts() -> list[str]:
    return [os.path.join(DIR, f"{NAME}.part{i}") for i in (1, 2)]


def _real(path: str, min_size: int) -> bool:
    try:
        return os.path.getsize(path) >= min_size
    except OSError:
        return False


def ensure_joined(verbose: bool = False) -> bool:
    target = os.path.join(DIR, NAME)
    if _real(target, SIZE):
        return True
    parts = _parts()
    if not all(_real(p, 1_000_000) for p in parts):  # missing, or Git LFS pointers not fetched yet
        return False
    with _LOCK:
        if _real(target, SIZE):
            return True
        h, tmp = hashlib.sha256(), target + ".joining"
        with open(tmp, "wb") as out:
            for p in parts:
                with open(p, "rb") as f:
                    while True:
                        b = f.read(1 << 22)
                        if not b:
                            break
                        h.update(b)
                        out.write(b)
        if h.hexdigest() != SHA256:
            os.remove(tmp)
            if verbose:
                print("[model] joined file failed the checksum — discarded")
            return False
        os.replace(tmp, target)
        for p in parts:  # the joined file replaces the parts on disk (the repo still has them)
            try:
                os.remove(p)
            except OSError:
                pass
        if verbose:
            print("[model] Gemma 3 4B ready")
    return True
