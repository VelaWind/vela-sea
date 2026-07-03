"""Build the WebAssembly (pygbag) bundle from a CLEAN staged tree.

Why this exists
---------------
`python -m pygbag --build .` packages the WHOLE project directory, and on
Windows pygbag's ignore config does NOT reliably exclude `.venv`: its filter
matches folders by their last path component, so `.venv/Lib/site-packages/...`
slips straight through.  The result is a ~45 MB bundle stuffed with pip /
site-packages — and pygbag's import scanner, seeing those packages, even tries
to resolve bogus PyPI deps like `mysql_python` that the game never uses.

The robust, cross-platform fix (pygbag's own recommendation) is a dedicated
build folder: copy ONLY the runtime files into a clean staging dir and run
pygbag there, so nothing but the game ships.

The pygame-ce wheel pre-fetch
-----------------------------
When the page is served from localhost, pygbag's runtime enters dev mode
(cpythonrc.py keys on "//localhost:" in the URL) and resolves packages
SAME-ORIGIN under /cdn/ — so the browser requests
    GET /cdn/cp312/pygame_ce-<ver>-...-wasm32_bi_emscripten.whl
from OUR server, not from the remote CDN.  pygbag's test server is supposed to
proxy+cache that from https://pygame-web.github.io, but the proxy is fragile
(a bare `except:` turns any fetch/cache hiccup into an instant 404 → gray
screen; `--cdn` can't help because it only changes which remote is proxied,
not the loader's same-origin lookup).  We were on the latest pygbag (0.9.3)
— no newer release fixes this.

Fix: after building, download the wheel ONCE into the served tree at the exact
path the loader asks for (build/web/cdn/cp312/...).  The test server then
serves it as a plain static file — no proxy, no network at page-load, no race.
This also makes the plain-http.server fallback below work.

Usage
-----
    python tools/build_web.py            # build only  -> build/MeridianSea/build/web/
    python tools/build_web.py --serve    # build + serve at http://localhost:8000

Fallback serve (if pygbag's test server misbehaves): the build output is fully
static, so this is known-good once the wheel has been pre-fetched:
    cd build/MeridianSea/build/web && python -m http.server 8000
(The runtime JS/wasm then loads straight from the remote CDN — needs internet —
and the wheel serves from the local cdn/ folder.  Note plain http.server sends
no COOP/COEP headers; pygbag's default non-threaded runtime loads without them.)

Output lives under build/ (gitignored).  `--disable-sound-format-error` is
passed because the effects are stdlib-generated PCM WAVs; pygbag prefers OGG but
packs WAV with the flag (browser playback is handled fail-safe at runtime).
"""

import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# pygbag derives the app/apk name from this folder's name, so name it nicely:
# the bundle ships as MeridianSea.apk.  Lives under build/ (gitignored).
STAGE = os.path.join(ROOT, "build", "MeridianSea")
WEB_DIR = os.path.join(STAGE, "build", "web")

# The ONLY things that ship to the browser: the runtime files, nothing else.
RUNTIME_FILES = ["main.py", "config.py"]
RUNTIME_DIRS = ["engine", "render", "data", "assets"]

# The wheel pygbag 0.9.3's cp312 runtime requests (the exact URL the browser
# 404'd on).  Pinned to the file hosted on the pygame-web CDN; bump alongside
# pygbag when its runtime moves to a newer pygame-ce / Python tag.
CDN_BASE = "https://pygame-web.github.io/cdn/"
PYGAME_WHEEL = "cp312/pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl"


def stage_clean_tree() -> None:
    """Copy runtime files into an empty STAGE dir (drops caches/compiled files)."""
    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)
    for f in RUNTIME_FILES:
        shutil.copy2(os.path.join(ROOT, f), os.path.join(STAGE, f))
    for d in RUNTIME_DIRS:
        shutil.copytree(
            os.path.join(ROOT, d), os.path.join(STAGE, d),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))


def prefetch_pygame_wheel() -> None:
    """Place the pygame-ce wheel into build/web/cdn/... as a static file.

    Non-fatal on failure: the test server's proxy remains as a (flaky) fallback,
    so a download hiccup here should not kill the build.
    """
    dest = os.path.join(WEB_DIR, "cdn", *PYGAME_WHEEL.split("/"))
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        print(f"pygame-ce wheel already present -> {dest}")
        return
    url = CDN_BASE + PYGAME_WHEEL
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        print(f"pre-fetched pygame-ce wheel ({os.path.getsize(dest)} bytes) -> {dest}")
    except Exception as e:  # noqa: BLE001 — any failure just means proxy fallback
        print(f"WARNING: wheel pre-fetch failed ({e}); "
              "the dev server will fall back to its CDN proxy")
        if os.path.exists(dest):
            os.remove(dest)          # never leave a truncated wheel behind


def run_pygbag(extra: list) -> int:
    cmd = [sys.executable, "-m", "pygbag", "--disable-sound-format-error",
           "--title", "Meridian Sea"] + extra + [STAGE]
    print("running:", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    stage_clean_tree()
    print(f"staged clean runtime tree -> {STAGE}")
    # Always build first so build/web exists, then drop the wheel into it.
    rc = run_pygbag(["--build"])
    if rc != 0:
        return rc
    prefetch_pygame_wheel()
    if "--serve" in sys.argv:
        # pygbag re-packs the apk on serve start; the cdn/ folder survives.
        return run_pygbag([])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
