"""Start PWD Estimator locally: SearXNG in the background (if installed), then the app; opens the browser.
Ctrl+C stops both. Used by start.bat / start.sh."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
WIN = os.name == "nt"
PORT = int(os.environ.get("PORT", "8000"))


def start_searxng():
    env_py = os.path.join(TOOLS, "searxng_env", "Scripts" if WIN else "bin", "python.exe" if WIN else "python")
    cfg = os.path.join(TOOLS, "searxng_settings.yml")
    if not (os.path.exists(env_py) and os.path.exists(cfg)):
        return None
    log = open(os.path.join(TOOLS, "searxng.log"), "w")
    return subprocess.Popen([env_py, "-m", "searx.webapp"], cwd=os.path.join(TOOLS, "searxng"), stdout=log, stderr=log,
                            env=dict(os.environ, SEARXNG_SETTINGS_PATH=cfg))


def open_browser():
    for _ in range(240):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=2)
            webbrowser.open(f"http://127.0.0.1:{PORT}")
            return
        except OSError:
            time.sleep(1)


def port_free(port: int) -> bool:
    import socket
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main():
    if not port_free(PORT):
        print(f"\n  Port {PORT} is already in use - PWD Estimator may already be running: open http://127.0.0.1:{PORT}")
        print("  (or close the other window, or set PORT=8001 and start again)\n")
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        return
    sx = start_searxng()
    print("  Web search (SearXNG):", "running" if sx else "not installed (curated price pages only)")
    print(f"\n  Open http://127.0.0.1:{PORT}  (opens automatically)   Ctrl+C to stop\n", flush=True)
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        subprocess.call([sys.executable, "-m", "uvicorn", "app:app", "--app-dir", os.path.join(ROOT, "backend"),
                         "--host", "127.0.0.1", "--port", str(PORT)])
    except KeyboardInterrupt:
        pass
    finally:
        if sx:
            sx.terminate()


if __name__ == "__main__":
    main()
