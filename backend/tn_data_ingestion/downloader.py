"""Downloads with robots.txt, timeouts, retries, cache, magic-byte validation and SHA-256 (shared with tnpwd_ingestion)."""
from __future__ import annotations

import os
import shutil

from tnpwd_ingestion import downloader as _d

MAGIC = {b"%PDF-": "pdf", b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"AC10": "dwg", b"II*\x00": "tif", b"MM\x00*": "tif"}
MAX_BYTES = 200 * 1024 * 1024


def sniff(path: str) -> str | None:
    with open(path, "rb") as f:
        head = f.read(8)
    for k, v in MAGIC.items():
        if head.startswith(k):
            return v
    if path.lower().endswith(".dxf"):
        with open(path, "rb") as f:
            if b"SECTION" in f.read(4096):
                return "dxf"
    return None


def store_local(path: str, raw_dir: str) -> dict:
    """Validate a local file and store it content-addressed (raw/<sha>.<ext>)."""
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("file too large")
    kind = sniff(path)
    if not kind:
        raise ValueError("unsupported / invalid file (magic bytes)")
    sha = _d.sha256_file(path)
    os.makedirs(raw_dir, exist_ok=True)
    dst = os.path.join(raw_dir, f"{sha}.{kind}")
    if not os.path.exists(dst):
        shutil.copy(path, dst)
    return dict(sha256=sha, path=dst, kind=kind, bytes=os.path.getsize(dst))


allowed = _d.allowed
get_text = _d.get_text
FetchError = _d.FetchError
