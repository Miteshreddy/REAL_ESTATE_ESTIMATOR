"""One-time local setup for PWD Estimator (Windows, macOS, Linux). Run by start.bat / start.sh inside .venv.

  1. Python libraries (requirements.txt) + the llama.cpp engine for the in-app Meta Llama model
  2. Large model files: a GitHub "Download ZIP" contains only Git LFS pointers for them — each is downloaded from the
     repository's LFS storage and checked against the SHA-256 in its pointer
  3. SearXNG (open-source metasearch, pinned version) in its own environment for web price discovery
  4. .env with the local settings (never overwritten)
Every step is safe to repeat; a failed optional step (llama engine, SearXNG) is reported and the app still runs.
"""
from __future__ import annotations

import hashlib
import io
import os
import platform
import secrets
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "Miteshreddy/REAL_ESTATE_ESTIMATOR"
LFS_URL = f"https://media.githubusercontent.com/media/{REPO}/main/"
SEARXNG_COMMIT = "f4822b3fc46726bb259d14c6332b702c76b98f82"
TOOLS = os.path.join(ROOT, "tools")
WIN, MAC = os.name == "nt", sys.platform == "darwin"
PY = sys.executable


def step(msg):
    print(f"\n==> {msg}", flush=True)


def pip(*args, quiet=True) -> bool:
    cmd = [PY, "-m", "pip", "install", "--disable-pip-version-check"] + (["-q"] if quiet else []) + list(args)
    return subprocess.call(cmd) == 0


def install_libraries():
    step("Installing Python libraries (first run: a few minutes)")
    subprocess.call([PY, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade", "pip"])
    if not pip("-r", os.path.join(ROOT, "requirements.txt")):
        sys.exit("[setup] library installation failed — check the internet connection and run the start script again")
    step("Installing the llama.cpp engine (runs the Gemma model inside the app)")
    if MAC and platform.machine() == "arm64":
        index = "https://abetlen.github.io/llama-cpp-python/whl/metal"
    else:
        index = "https://abetlen.github.io/llama-cpp-python/whl/cpu"
    if not pip("llama-cpp-python==0.3.36", "--prefer-binary", "--extra-index-url", index):
        print("[setup] llama.cpp engine could not be installed — written summaries are off, everything else works")


def _pointer(path):
    try:
        if os.path.getsize(path) > 1024:
            return None
        txt = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return None
    if not txt.startswith("version https://git-lfs"):
        return None
    oid = next((l.split("sha256:")[1].strip() for l in txt.splitlines() if l.startswith("oid sha256:")), None)
    size = next((int(l.split()[1]) for l in txt.splitlines() if l.startswith("size ")), None)
    return (oid, size) if oid else None


def fetch_large_files():
    step("Checking large model files (Git LFS)")
    found = 0
    for base in ("data",):
        for d, _, files in os.walk(os.path.join(ROOT, base)):
            for f in files:
                path = os.path.join(d, f)
                ptr = _pointer(path)
                if not ptr:
                    continue
                found += 1
                rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                oid, size = ptr
                print(f"  downloading {rel} ({size / 1e9:.2f} GB)…", flush=True)
                h, tmp = hashlib.sha256(), path + ".part"
                try:
                    with urllib.request.urlopen(LFS_URL + urllib.request.quote(rel), timeout=60) as r, open(tmp, "wb") as out:
                        while True:
                            b = r.read(1 << 20)
                            if not b:
                                break
                            h.update(b)
                            out.write(b)
                except OSError as e:
                    print(f"  [setup] could not download {rel}: {e} — the app uses its fallback")
                    continue
                if h.hexdigest() != oid:
                    os.remove(tmp)
                    print(f"  [setup] checksum mismatch for {rel} — discarded")
                    continue
                os.replace(tmp, path)
                print(f"  ok  {rel}")
    if not found:
        print("  all model files present")
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    import model_file
    print("  Gemma 3 4B:", "ready" if model_file.ensure_joined(verbose=True) else "not available (written summaries off)")


def install_searxng():
    step("Installing SearXNG (open-source web search for price discovery)")
    src, env = os.path.join(TOOLS, "searxng"), os.path.join(TOOLS, "searxng_env")
    if not os.path.exists(os.path.join(src, "searx", "webapp.py")):
        try:
            url = f"https://github.com/searxng/searxng/archive/{SEARXNG_COMMIT}.zip"
            data = urllib.request.urlopen(url, timeout=120).read()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                prefix = z.namelist()[0].split("/")[0] + "/"
                for n in z.namelist():
                    rel = n[len(prefix):]
                    if not rel or n.endswith("/") or ":" in rel:  # Linux server templates with ':' are not needed
                        continue
                    dst = os.path.join(src, *rel.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with z.open(n) as fi, open(dst, "wb") as fo:
                        shutil.copyfileobj(fi, fo)
        except Exception as e:
            print(f"  [setup] SearXNG download failed ({e}) — web search is off; curated price pages still work")
            return False
    epy = os.path.join(env, "Scripts" if WIN else "bin", "python.exe" if WIN else "python")
    if not os.path.exists(epy) and subprocess.call([PY, "-m", "venv", env]) != 0:
        print("  [setup] could not create the SearXNG environment — web search is off")
        return False
    if subprocess.call([epy, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", os.path.join(src, "requirements.txt")]) != 0:
        print("  [setup] SearXNG libraries failed to install — web search is off")
        return False
    if WIN:  # SearXNG imports the Unix-only 'pwd' module; a tiny stand-in makes it start on Windows
        site = os.path.join(env, "Lib", "site-packages")
        shutil.copy(os.path.join(ROOT, "deploy", "searxng", "pwd_windows_shim.py"), os.path.join(site, "pwd.py"))
    cfg = os.path.join(TOOLS, "searxng_settings.yml")
    if not os.path.exists(cfg):
        txt = open(os.path.join(ROOT, "deploy", "searxng", "settings.yml"), encoding="utf-8").read()
        open(cfg, "w", encoding="utf-8").write(txt.replace("__SEARXNG_SECRET__", secrets.token_hex(32)))
    print("  ok  SearXNG ready")
    return True


def write_env(searx_ok: bool):
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        return
    open(p, "w", encoding="utf-8").write("# Local settings for PWD Estimator (git-ignored)\n"
                                          + ("SEARXNG_URL=http://127.0.0.1:8888\n" if searx_ok else "")
                                          + "LLM_BACKEND=llamacpp\n")


def main():
    install_libraries()
    fetch_large_files()
    ok = install_searxng() if os.environ.get("PWD_SKIP_SEARXNG") != "1" else False
    write_env(ok)
    open(os.path.join(ROOT, ".setup_done"), "w").write("1\n")
    step("Setup complete")


if __name__ == "__main__":
    main()
