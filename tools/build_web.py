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
    python tools/build_web.py --deploy   # build + sync the finished page into docs/
                                         # (the GitHub Pages artifact — tracked!)

GitHub Pages deployment notes
-----------------------------
Pages serves project sites at https://<user>.github.io/<repo>/ — a SUBPATH.
The page is subpath-safe because every reference is either RELATIVE
(favicon.png, and platform.fopen("meridiansea.tar.gz"/".apk") resolve against
the page URL) or ABSOLUTE-REMOTE (the runtime JS/wasm from
https://pygame-web.github.io/cdn/).  On any non-localhost host the runtime's
dev mode never triggers, so the pygame-ce wheel also resolves from the REMOTE
cdn via pep0723 — the local cdn/ copy in the bundle is used only by localhost
dev serving (dev mode requests http://localhost:<port>/cdn/... at the origin
ROOT, so it is expected to 404 when docs/ is served under a subpath on
localhost; that quirk cannot occur on real Pages, where the host differs).
GitHub Pages cannot send COOP/COEP headers; pygbag 0.9.3's default
non-threaded runtime tolerates their absence — verified earlier on plain
http.server, which sends none either.

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


def _sea_color_hex() -> str:
    """The game's deep-water color as a CSS hex string, read from config.py so
    the page background can never drift from the chart's sea color."""
    sys.path.insert(0, ROOT)
    try:
        from config import COLOR_WATER
        return "#%02x%02x%02x" % tuple(COLOR_WATER[:3])
    except Exception:
        return "#0a1c34"   # last-known DEEP_WATER; only used if config breaks
    finally:
        sys.path.remove(ROOT)


PAGE_MARKER = "meridian-brand"

# Inline SVG favicon: cyan vessel triangle on a deep-navy rounded square.
_FAVICON = ("data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 "
            "viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 "
            "rx=%2212%22 fill=%22%230a1c34%22/><path d=%22M32 10 L45 48 L32 "
            "41 L19 48 Z%22 fill=%22%234fd1e0%22/></svg>")


def _head_block(sea: str) -> str:
    """Page chrome: sea background, title, favicon, splash styling."""
    return f"""<style id="{PAGE_MARKER}-style">
  html, body {{ background: {sea} !important; margin: 0; padding: 0; overflow: hidden; }}
  #{PAGE_MARKER}-splash {{
    position: fixed; inset: 0; z-index: 9999; background: {sea};
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; transition: opacity .7s ease;
    font-family: 'Segoe UI', system-ui, sans-serif; }}
  .ms-word {{ color: #dee9f4; font-size: 44px; letter-spacing: .35em;
              font-weight: 200; padding-left: .35em; }}
  .ms-word span {{ color: #4fd1e0; font-weight: 400; }}
  .ms-sub  {{ color: #6c8096; font-size: 13px; letter-spacing: .22em;
              margin-top: 10px; text-transform: lowercase; }}
  .ms-bar  {{ width: 220px; height: 2px; margin-top: 26px; overflow: hidden;
              border-radius: 2px; background: rgba(140,170,200,.14); }}
  .ms-bar div {{ width: 40%; height: 100%; background: #4fd1e0;
                 border-radius: 2px; animation: msld 1.4s ease-in-out infinite; }}
  @keyframes msld {{ 0% {{ transform: translateX(-110%); }}
                     100% {{ transform: translateX(330%); }} }}
</style>
<link id="{PAGE_MARKER}-icon" rel="icon" href='{_FAVICON}'>
<meta name="theme-color" content="{sea}">
</head>"""


def _body_block() -> str:
    """Branded splash overlay + self-removing fade script.

    Fades out once pygbag reveals a real canvas (the runtime grows the 1px
    placeholder and flips visibility when the app takes over); a 45s failsafe
    guarantees the splash can never trap the page on a stalled load.
    """
    return f"""<div id="{PAGE_MARKER}-splash">
  <div class="ms-word">MERIDIAN<span>&nbsp;SEA</span></div>
  <div class="ms-sub">ambient maritime simulator</div>
  <div class="ms-bar"><div></div></div>
</div>
<script id="{PAGE_MARKER}-script">
(function () {{
  var s = document.getElementById('{PAGE_MARKER}-splash');
  if (!s) return;
  var t0 = Date.now();
  var iv = setInterval(function () {{
    var up = false;
    var cs = document.getElementsByTagName('canvas');
    for (var i = 0; i < cs.length; i++) {{
      if (cs[i].width > 100 && cs[i].style.visibility !== 'hidden') {{ up = true; break; }}
    }}
    if (up || Date.now() - t0 > 45000) {{
      clearInterval(iv);
      setTimeout(function () {{
        s.style.opacity = '0';
        setTimeout(function () {{ if (s.parentNode) s.parentNode.removeChild(s); }}, 750);
      }}, up ? 450 : 0);
    }}
  }}, 250);
}})();
</script>
</body>"""


def patch_web_page() -> None:
    """Brand the page: sea background, favicon, and a full-page loading splash
    ("MERIDIAN SEA / ambient maritime simulator" + shimmer bar) that fades out
    when the canvas takes over — replacing pygbag's default gray loader look.

    Inline CSS/SVG only; no new asset files.  Idempotent (keyed on
    PAGE_MARKER).  Patched into BOTH the generated index.html and the cached
    *.tmpl templates (build/web-cache/): pygbag's test server regenerates
    index.html from the cached template on each serve, so patching only
    index.html would not survive `--serve`.
    """
    sea = _sea_color_hex()
    targets = [os.path.join(WEB_DIR, "index.html")]
    cache_dir = os.path.join(STAGE, "build", "web-cache")
    if os.path.isdir(cache_dir):
        targets += [os.path.join(cache_dir, f) for f in os.listdir(cache_dir)
                    if f.endswith(".tmpl")]
    for path in targets:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        if PAGE_MARKER in html or "</head>" not in html:
            continue                      # already patched / no head to patch
        html = html.replace("</head>", _head_block(sea), 1)
        if "</body>" in html:
            html = html.replace("</body>", _body_block(), 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"patched page brand (splash + favicon + sea bg) -> {path}")


DOCS_DIR = os.path.join(ROOT, "docs")

# Everything the page needs at runtime, nothing else.  The non-itch unpack
# branch fetches meridiansea.tar.gz (the .apk is the itch.zone branch — ship
# both, they're ~380 KB each); favicon.png is the <link rel=icon> fallback;
# cdn/ holds the pre-fetched pygame-ce wheel for localhost dev serving.
DEPLOY_FILES = ["index.html", "favicon.png",
                "meridiansea.apk", "meridiansea.tar.gz"]
DEPLOY_DIRS = ["cdn"]

DOCS_README = """# docs/ — deployed web build (generated)

Generated by `python tools/build_web.py --deploy` for GitHub Pages — do NOT
edit anything here; edit the game source and re-deploy instead.
"""


def deploy_to_docs() -> None:
    """Sync the finished web page into docs/ (the tracked GitHub Pages root),
    replacing previous contents.  Prints every file copied, with sizes."""
    if os.path.exists(DOCS_DIR):
        shutil.rmtree(DOCS_DIR)
    os.makedirs(DOCS_DIR)
    total = 0
    for name in DEPLOY_FILES:
        src = os.path.join(WEB_DIR, name)
        if not os.path.isfile(src):
            print(f"WARNING: expected build output missing, skipped: {name}")
            continue
        shutil.copy2(src, os.path.join(DOCS_DIR, name))
        size = os.path.getsize(src)
        total += size
        print(f"deployed {name}  ({size:,} bytes)")
    for name in DEPLOY_DIRS:
        src = os.path.join(WEB_DIR, name)
        if not os.path.isdir(src):
            print(f"WARNING: expected build dir missing, skipped: {name}/")
            continue
        shutil.copytree(src, os.path.join(DOCS_DIR, name))
        size = sum(os.path.getsize(os.path.join(r, f))
                   for r, _, fs in os.walk(src) for f in fs)
        total += size
        print(f"deployed {name}/  ({size:,} bytes)")
    with open(os.path.join(DOCS_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(DOCS_README)
    print(f"deploy complete -> {DOCS_DIR}  (total {total / 1e6:.2f} MB)")


def run_pygbag(extra: list) -> int:
    # --ume_block 0: don't gate the sim behind a click-to-start splash.  This is
    # an ambient spectator simulator — it should boot the living sea immediately
    # on page load.  (Browser audio policy still needs a user gesture before any
    # sound plays, so it's silent ambient until the first click — that's fine.)
    cmd = [sys.executable, "-m", "pygbag", "--disable-sound-format-error",
           "--ume_block", "0", "--title", "Meridian Sea"] + extra + [STAGE]
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
    # Patch AFTER build, BEFORE serve: --serve regenerates index.html from the
    # cached template, which patch_web_page() also patches, so the sea-color
    # page framing survives the re-pack.
    patch_web_page()
    if "--deploy" in sys.argv:
        deploy_to_docs()
    if "--serve" in sys.argv:
        # pygbag re-packs the apk on serve start; the cdn/ folder survives.
        return run_pygbag([])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
