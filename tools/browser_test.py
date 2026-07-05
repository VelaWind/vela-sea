"""Automated real-browser test suite for the Vela Sea web build.

Drives headless Chromium (Playwright) against the built site: boot + splash,
feature-by-feature checks (motion, fps cap, select/follow easing, Esc, time
compression, zoom, hover, event feed, long-run stability), then a GitHub
Pages preflight that serves docs/ under a /vela-sea/ SUBPATH exactly as
Pages will.

Signals it reads:
- [WEBTEST] beacons: main.py logs one line per ~5 s to the JS console (NOT
  stdout — pygbag routes stdout to its on-page terminal, which Playwright
  cannot read) carrying cumulative profiler counters, sim speed, event count,
  selection, and a clickable vessel's framebuffer coordinates.
- The HTTP request log of our own in-process server (404 audit, wheel 200).
- Screenshots, pixel-sampled with pygame (no display needed) for motion /
  zoom / hover / menu checks.  A human (or Claude, per CLAUDE.md) must still
  LOOK at the saved PNGs before trusting a green table.

Usage:
    python tools/browser_test.py                # default run (~10-12 min)
    python tools/browser_test.py --skip-build   # reuse existing build/web
    python tools/browser_test.py --longrun 60   # shorten the stability soak

Extended validation (each flag runs ONLY its phase, skipping the default
suite, so runs stay composable and the default stays fast):
    --engines chromium,firefox,webkit   # cross-engine boot + core (webkit~Safari)
    --mobile                            # iPhone 13 descriptor: boot, LOOK, tap
    --lifecycle                         # tab frozen 2 min + resume, resizes
    --network                           # ~4 Mbps cold load: time-to-sea, bytes
    --endurance 1800                    # N-second ambient soak: fps/heap/errors

Artifacts land in tools/browser_test_out/ (gitignored): screenshots,
console.log, summary.md.  Exit code 0 only if every non-skipped test passes.
"""

import argparse
import functools
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame  # noqa: E402  (pixel sampling of screenshots only)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "build", "VelaSea", "build", "web")
DOCS_DIR = os.path.join(ROOT, "docs")
OUT_DIR = os.path.join(ROOT, "tools", "browser_test_out")
# NOT an 8xxx port: pygbag's runtime (aio/pep0723.py) rewrites the wheel CDN
# to a HARDCODED http://localhost:8000/cdn/ whenever the page URL starts with
# "http://localhost:8" — on any other 8xxx port the wheel fetch hits :8000,
# gets connection-refused, and the game never boots (found by this suite's
# first run on 8123).  Off the 8xxx pattern the rewrite never fires and the
# wheel resolves from the REMOTE CDN — exactly what real GitHub Pages does,
# so the test environment is also more faithful.
PORT = 9123
VIEWPORT = {"width": 1600, "height": 900}
WHEEL_PATH = "/cdn/cp312/pygame_ce-2.5.7-cp312-cp312-wasm32_bi_emscripten.whl"
# Central chart region (CSS px at the 1600x900 viewport): clear of the status
# bar, fleet panel, fps overlay, minimap and info card, so frame-to-frame
# diffs there mean "the world moved", not "the clock ticked".
CHART_RECT = (430, 120, 700, 540)


# ---------------------------------------------------------------------------
# HTTP server with a request log (the 404 audit reads this)
# ---------------------------------------------------------------------------

class _QuietHandler(SimpleHTTPRequestHandler):
    records: list = []          # class-level; reset by serve()

    def log_request(self, code="-", size="-"):
        try:
            _QuietHandler.records.append((self.path, int(code)))
        except (TypeError, ValueError):
            _QuietHandler.records.append((self.path, -1))

    def log_message(self, *a):   # silence stderr chatter
        pass


def serve(root: str):
    """Start a threaded static server on PORT; returns (server, thread)."""
    _QuietHandler.records = []
    handler = functools.partial(_QuietHandler, directory=root)
    srv = ThreadingHTTPServer(("localhost", PORT), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, t


def stop(srv, t):
    try:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Screenshot pixel sampling (pygame; no display required for load/get_at)
# ---------------------------------------------------------------------------

def region_diff(png_a: str, png_b: str, rect=CHART_RECT, step: int = 6) -> float:
    """Fraction of sampled pixels that differ between two screenshots."""
    sa = pygame.image.load(png_a)
    sb = pygame.image.load(png_b)
    x0, y0, w, h = rect
    differ = total = 0
    for y in range(y0, min(y0 + h, sa.get_height(), sb.get_height()), step):
        for x in range(x0, min(x0 + w, sa.get_width(), sb.get_width()), step):
            total += 1
            if sa.get_at((x, y)) != sb.get_at((x, y)):
                differ += 1
    return differ / max(1, total)


# ---------------------------------------------------------------------------
# Test harness state
# ---------------------------------------------------------------------------

class _SpecialDone(Exception):
    """Internal control flow: unwinds main()'s try to the artifact-writing
    finally block once the flag-gated special phases have all run."""


class Suite:
    def __init__(self):
        self.rows = []            # (name, verdict, evidence)
        self.console = []         # all console lines (both phases)
        self.errors = []          # pageerror exceptions

    def add(self, name, ok, evidence):
        self.rows.append((name, "PASS" if ok else "FAIL", evidence))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} — {evidence}")

    def skip(self, name, why):
        self.rows.append((name, "SKIP", why))
        print(f"[SKIP] {name} — {why}")

    # ---- console helpers ----------------------------------------------
    def beacons(self):
        out = []
        for ln in self.console:
            i = ln.find("[WEBTEST] t=")
            if i < 0:
                continue
            d = {}
            for tok in ln[i + len("[WEBTEST] "):].split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    d[k] = v
            out.append(d)
        return out

    def tracebacks(self):
        return [ln for ln in self.console
                if "Traceback (most recent call" in ln] + self.errors


def fps_between(b1, b2) -> float:
    dt = float(b2["t"]) - float(b1["t"])
    return (int(b2["n"]) - int(b1["n"])) / dt if dt > 0 else 0.0


def work_ms_between(b1, b2) -> float:
    dn = int(b2["n"]) - int(b1["n"])
    if dn <= 0:
        return 0.0
    work = sum(float(b2[k]) - float(b1[k])
               for k in ("sim", "chart", "panels", "flip"))
    return work / dn * 1e3


def canvas_rect(page):
    """The game canvas's ACTUAL CSS box.  Never assume full-bleed: pygbag's
    sizing has been seen leaving the canvas letterboxed, and mapping clicks
    against the viewport then misses everything (run-4 lesson)."""
    return page.evaluate(
        "() => { const r = document.getElementById('canvas')"
        ".getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height}; }")


def css_from_fb(page, b, vx, vy):
    """Map beacon framebuffer coords to CSS px through the real canvas box."""
    r = canvas_rect(page)
    return (r["x"] + vx * r["w"] / int(b["fbw"]),
            r["y"] + vy * r["h"] / int(b["fbh"]))


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def attach(page, suite):
    """Wire console + pageerror capture.  Lines carry the console type prefix
    ("[error] ...") so phases can count JS errors; beacon/traceback scanning
    uses substring search, so the prefix is transparent to them."""
    page.on("console", lambda m: suite.console.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: suite.errors.append(str(e)))


def js_error_count(suite) -> int:
    return (sum(1 for ln in suite.console if ln.startswith("[error]"))
            + len(suite.errors))


def wait_beacon_count(page, suite, count, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if len(suite.beacons()) >= count:
            return True
        page.wait_for_timeout(1000)   # pumps console events (sync API)
    return len(suite.beacons()) >= count


def shot(page, name):
    path = os.path.join(OUT_DIR, name)
    page.screenshot(path=path)
    return path


def boot_phase(page, suite, url, tag, shots_prefix, viewport=None,
               boot_timeout=240):
    """Navigate + splash + boot-to-beacons + 404/traceback audit.

    Counts beacons and requests from THIS navigation only, so it can run
    repeatedly (per engine / per phase) inside one process.
    """
    viewport = viewport or VIEWPORT
    rec0 = len(_QuietHandler.records)
    n0 = len(suite.beacons())
    page.goto(url, wait_until="domcontentloaded")
    splash_seen = False
    try:
        page.wait_for_selector("#vela-brand-splash", timeout=8000)
        splash_seen = True
    except Exception:
        pass
    shot(page, f"{shots_prefix}_splash.png")
    suite.add(f"{tag}: branded splash", splash_seen,
              "VELA SEA splash div present" if splash_seen
              else "splash div never appeared")

    booted = wait_beacon_count(page, suite, n0 + 2, timeout_s=boot_timeout)
    n_webprof = sum(1 for ln in suite.console if "[WEBPROF]" in ln)
    suite.add(f"{tag}: boot (sim loop alive)", booted,
              f"{len(suite.beacons()) - n0} [WEBTEST] beacons, "
              f"{n_webprof} [WEBPROF] console lines")
    if not booted:
        return False

    bad = [(p, c) for p, c in _QuietHandler.records[rec0:]
           if c == 404 and p != "/favicon.ico"]
    suite.add(f"{tag}: no asset 404s", not bad,
              "requests clean" if not bad else f"404s: {bad[:5]}")
    tb = suite.tracebacks()
    suite.add(f"{tag}: zero Python tracebacks", not tb,
              "console clean" if not tb else tb[0][:160])
    r = canvas_rect(page)
    fills = (abs(r["w"] - viewport["width"]) <= 12
             and abs(r["h"] - viewport["height"]) <= 12)
    suite.add(f"{tag}: canvas fills viewport (no letterbox)", fills,
              f"canvas {r['w']:.0f}x{r['h']:.0f} at ({r['x']:.0f},{r['y']:.0f})"
              f" in {viewport['width']}x{viewport['height']}")
    page.wait_for_timeout(3000)
    shot(page, f"{shots_prefix}_sea.png")
    return True


# ---------------------------------------------------------------------------
# Extended validation phases (flag-gated; each runs standalone)
# ---------------------------------------------------------------------------

def engine_core(pw, suite, engine):
    """Boot + core checks on one engine.  A non-Chromium engine that cannot
    boot the WASM runtime is a KNOWN LIMITATION (skip), not a failure — we
    report the console evidence and move on, per the validation spec."""
    url = f"http://localhost:{PORT}/"
    browser = None
    try:
        browser = getattr(pw, engine).launch(headless=True)
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        attach(page, suite)
        n0 = len(suite.beacons())
        page.goto(url, wait_until="domcontentloaded")
        booted = wait_beacon_count(page, suite, n0 + 2, timeout_s=240)
        if not booted:
            ev = (suite.console[-1][:140] if suite.console
                  else "no console output at all")
            if engine == "chromium":
                suite.add(f"{engine}: boot", False, ev)
            else:
                suite.skip(f"{engine}: boot",
                           f"known limitation — WASM runtime never came up "
                           f"(last console: {ev})")
            return
        tb = suite.tracebacks()
        suite.add(f"{engine}: boot", not tb,
                  "sim loop alive, console clean" if not tb else tb[0][:120])
        a = shot(page, f"30_{engine}_a.png")
        page.wait_for_timeout(6000)
        b = shot(page, f"30_{engine}_b.png")
        frac = region_diff(a, b)
        suite.add(f"{engine}: ships move", frac > 0.002,
                  f"chart diff {frac:.4f} over 6 s")
        bs = suite.beacons()
        fps = fps_between(bs[-2], bs[-1]) if len(bs) - n0 >= 2 else 0.0
        floor = 24.0 if engine == "chromium" else 15.0
        suite.add(f"{engine}: fps", floor <= fps <= 34.0,
                  f"{fps:.1f} fps (floor {floor:.0f} for this engine)")
    finally:
        if browser is not None:
            browser.close()


def mobile_suite(pw, suite):
    """iPhone 13 descriptor: boot, LOOK, tap-select.  WebKit (= iOS Safari
    engine) preferred; falls back to Chromium (= Android reality) if WebKit
    cannot boot, and says which engine produced the verdict."""
    url = f"http://localhost:{PORT}/"
    dev = pw.devices["iPhone 13"]
    used = None
    for engine in ("webkit", "chromium"):
        browser = None
        try:
            browser = getattr(pw, engine).launch(headless=True)
            ctx = browser.new_context(**dev)
            page = ctx.new_page()
            attach(page, suite)
            n0 = len(suite.beacons())
            page.goto(url, wait_until="domcontentloaded")
            if not wait_beacon_count(page, suite, n0 + 2, timeout_s=240):
                suite.skip(f"mobile boot ({engine})",
                           "WASM runtime never came up on this engine")
                browser.close()
                continue
            used = engine
            vp = dev["viewport"]
            suite.add(f"mobile boot ({engine})", True,
                      f"booted at {vp['width']}x{vp['height']} dpr="
                      f"{dev.get('device_scale_factor', 1)}")
            page.wait_for_timeout(3000)
            shot(page, "40_mobile_sea.png")
            # tap a vessel off a fresh beacon (touch -> selection echo)
            nb = len(suite.beacons())
            wait_beacon_count(page, suite, nb + 1, timeout_s=12)
            bs = [d for d in suite.beacons() if "vessel" in d]
            if bs:
                bv = bs[-1]
                tx, ty = css_from_fb(page, bv, float(bv["vx"]), float(bv["vy"]))
                ne = len([l for l in suite.console
                          if "[WEBTEST] selected=" in l])
                page.tap(f"#canvas", position={
                    "x": tx - canvas_rect(page)["x"],
                    "y": ty - canvas_rect(page)["y"]})
                page.wait_for_timeout(1500)
                sel = [l for l in suite.console
                       if "[WEBTEST] selected=" in l][ne:]
                ok = bool(sel) and not sel[-1].endswith("=None")
                suite.add("mobile tap-select", ok,
                          sel[-1][-50:] if sel else "no selection echo on tap")
                shot(page, "41_mobile_tap.png")
            else:
                suite.skip("mobile tap-select", "no beacon vessel coords")
            suite.skip("mobile pinch-zoom",
                       "untested — Playwright has no native pinch gesture")
            browser.close()
            return
        except Exception as e:
            suite.skip(f"mobile boot ({engine})", f"engine error: {e}")
            if browser is not None:
                browser.close()
    if used is None:
        suite.add("mobile verdict", False,
                  "no engine could boot the mobile viewport")


def lifecycle_suite(pw, suite):
    """Frozen-tab resume (dt clamp) + resize robustness.  Chromium (CDP).

    Playwright's default Chromium args DISABLE background throttling, so
    Page.setWebLifecycleState can be a no-op (first run: beacons flowed
    straight through the "frozen" window).  We drop those args, then DETECT
    whether the freeze actually took (a >60 s beacon-time gap) and only
    assert the burst bound when it did — a non-freezing engine proves
    nothing about the clamp either way.
    """
    url = f"http://localhost:{PORT}/"
    browser = pw.chromium.launch(headless=True, ignore_default_args=[
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding"])
    try:
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        attach(page, suite)
        n0 = len(suite.beacons())
        page.goto(url, wait_until="domcontentloaded")
        if not wait_beacon_count(page, suite, n0 + 2, timeout_s=240):
            suite.add("lifecycle: boot", False, "never booted")
            return
        cdp = ctx.new_cdp_session(page)
        b0 = suite.beacons()[-1]
        cdp.send("Page.setWebLifecycleState", {"state": "frozen"})
        time.sleep(120)                      # page JS is frozen; plain sleep
        cdp.send("Page.setWebLifecycleState", {"state": "active"})
        nb = len(suite.beacons())
        wait_beacon_count(page, suite, nb + 2, timeout_s=30)
        bs = [b for b in suite.beacons() if float(b["t"]) >= float(b0["t"])]
        gaps = [float(bs[i + 1]["t"]) - float(bs[i]["t"])
                for i in range(len(bs) - 1)]
        froze = bool(gaps) and max(gaps) > 60.0
        b1 = suite.beacons()[-1]
        steps = int(b1["steps"]) - int(b0["steps"])
        wall = float(b1["t"]) - float(b0["t"])
        if froze:
            # Unclamped, 120 s hidden at TIME_COMPRESSION 80 would demand
            # ~9600 catch-up steps; the 0.5 s dt clamp + step cap keep the
            # resume burst to (clamp + ~15 s normal running) ~= 1300.
            suite.add("lifecycle: no catch-up burst after 2 min frozen",
                      steps < 3000,
                      f"froze (max beacon gap {max(gaps):.0f}s); steps "
                      f"across window: {steps} (unclamped ~9600+)")
        else:
            # Engine refused to freeze: verify no anomaly while backgrounded
            # (steps track wall time linearly — no burst, no stall).
            rate = steps / wall if wall > 0 else 0.0
            suite.add("lifecycle: backgrounded 2 min, no anomaly",
                      60.0 <= rate <= 110.0,
                      f"engine would not freeze (max gap {max(gaps):.1f}s); "
                      f"steps/s {rate:.1f} stayed linear; dt-clamp itself is "
                      f"covered by the headless frame-cap test")
        fps = fps_between(suite.beacons()[-2], suite.beacons()[-1])
        suite.add("lifecycle: smooth resume", 24.0 <= fps <= 34.0,
                  f"post-resume fps {fps:.1f}")
        for i, (w, h) in enumerate([(1835, 980), (1200, 700), (1600, 900)]):
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(4000)      # heal watchdog runs ~1/s
            r = canvas_rect(page)
            ok = abs(r["w"] - w) <= 12 and abs(r["h"] - h) <= 12
            suite.add(f"lifecycle: resize {w}x{h}", ok
                      and not suite.tracebacks(),
                      f"canvas {r['w']:.0f}x{r['h']:.0f}, tracebacks "
                      f"{len(suite.tracebacks())}")
            shot(page, f"50_resize_{w}x{h}.png")
    finally:
        browser.close()


def network_suite(pw, suite):
    """Cold load at ~4 Mbps (hotel wifi): time-to-splash, time-to-sea, bytes."""
    url = f"http://localhost:{PORT}/"
    browser = pw.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        attach(page, suite)
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions", {
            "offline": False, "latency": 40,
            "downloadThroughput": 500_000,   # 4 Mbps
            "uploadThroughput": 125_000,
        })
        # Count bytes via CDP events: performance-API transferSize reads 0 for
        # cross-origin resources without Timing-Allow-Origin, which hides the
        # entire pygame-web CDN download (the bulk of a cold load).
        total = {"bytes": 0.0}
        cdp.on("Network.loadingFinished",
               lambda p: total.__setitem__(
                   "bytes", total["bytes"] + p.get("encodedDataLength", 0)))
        n0 = len(suite.beacons())
        t0 = time.monotonic()
        page.goto(url, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#vela-brand-splash", timeout=20000)
            t_splash = time.monotonic() - t0
        except Exception:
            t_splash = -1.0
        booted = wait_beacon_count(page, suite, n0 + 1, timeout_s=360)
        t_sea = time.monotonic() - t0 if booted else -1.0
        mb = total["bytes"] / 1e6
        shot(page, "60_slow_network_sea.png")
        suite.add("slow-network: splash shown", 0 <= t_splash < 15,
                  f"time-to-splash {t_splash:.1f}s")
        suite.add("slow-network: sea boots", booted,
                  f"time-to-sea {t_sea:.1f}s, ~{mb:.1f} MB transferred "
                  f"at 4 Mbps")
    finally:
        browser.close()


def endurance_suite(pw, suite, secs):
    """The ambient use-case: an N-second tab, sampled every minute."""
    url = f"http://localhost:{PORT}/"
    browser = pw.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        attach(page, suite)
        n0 = len(suite.beacons())
        page.goto(url, wait_until="domcontentloaded")
        if not wait_beacon_count(page, suite, n0 + 2, timeout_s=240):
            suite.add("endurance: boot", False, "never booted")
            return
        shot(page, "70_endurance_start.png")
        samples = []                 # (minute, fps, heap_mb, err_count)
        t_end = time.monotonic() + secs
        minute = 0
        while time.monotonic() < t_end:
            waited = 0
            while waited < 60 and time.monotonic() < t_end:
                page.wait_for_timeout(10_000)
                waited += 10
            minute += 1
            bs = suite.beacons()
            fps = fps_between(bs[-2], bs[-1]) if len(bs) >= 2 else 0.0
            heap = page.evaluate(
                "() => performance.memory ? "
                "performance.memory.usedJSHeapSize / 1e6 : -1")
            samples.append((minute, fps, heap, js_error_count(suite)))
            print(f"  [endurance] min {minute}: fps={fps:.1f} "
                  f"heap={heap:.0f}MB errors={samples[-1][3]}")
        shot(page, "71_endurance_end.png")
        fps_list = [s[1] for s in samples]
        heaps = [s[2] for s in samples if s[2] >= 0]
        low = [f for f in fps_list if f < 25.0]
        tb = suite.tracebacks()
        suite.add(f"endurance {secs}s: fps >=25 throughout", not low,
                  f"fps first={fps_list[0]:.1f} last={fps_list[-1]:.1f} "
                  f"min={min(fps_list):.1f} over {len(samples)} samples")
        suite.add(f"endurance {secs}s: zero tracebacks", not tb,
                  "clean" if not tb else tb[0][:120])
        if len(heaps) >= 4:
            early = sum(heaps[:3]) / 3
            late = sum(heaps[-3:]) / 3
            suite.add(f"endurance {secs}s: heap bounded",
                      late < early * 2.0 + 50,
                      f"heap first={heaps[0]:.0f}MB last={heaps[-1]:.0f}MB "
                      f"(early avg {early:.0f} -> late avg {late:.0f})")
        else:
            suite.skip("endurance: heap trend", "performance.memory absent")
    finally:
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--longrun", type=int, default=180)
    ap.add_argument("--engines", default=None,
                    help="comma list: chromium,firefox,webkit — run per-engine"
                         " core checks only")
    ap.add_argument("--mobile", action="store_true")
    ap.add_argument("--lifecycle", action="store_true")
    ap.add_argument("--network", action="store_true")
    ap.add_argument("--endurance", type=int, default=0,
                    help="ambient soak length in seconds (e.g. 1800)")
    args = ap.parse_args()

    special = bool(args.engines or args.mobile or args.lifecycle
                   or args.network or args.endurance)
    if os.path.exists(OUT_DIR) and not special:
        shutil.rmtree(OUT_DIR)          # special runs accumulate artifacts
    os.makedirs(OUT_DIR, exist_ok=True)

    if not args.skip_build:
        print("building web bundle...")
        rc = subprocess.call([sys.executable,
                              os.path.join(ROOT, "tools", "build_web.py")])
        if rc != 0:
            print("build failed")
            return 1

    from playwright.sync_api import sync_playwright

    suite = Suite()
    srv = thread = None
    pw = browser = None
    tmp = None
    try:
        srv, thread = serve(WEB_DIR)
        pw = sync_playwright().start()

        if special:
            # Extended phases only — the default 18-test suite is skipped so
            # each validation dimension can run (and be re-run) on its own.
            if args.engines:
                for engine in args.engines.split(","):
                    engine_core(pw, suite, engine.strip())
            if args.mobile:
                mobile_suite(pw, suite)
            if args.lifecycle:
                lifecycle_suite(pw, suite)
            if args.network:
                network_suite(pw, suite)
            if args.endurance:
                endurance_suite(pw, suite, args.endurance)
            raise _SpecialDone()

        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        attach(page, suite)

        # ---------------- STEP 1: boot (dev build, served at root) --------
        if not boot_phase(page, suite, f"http://localhost:{PORT}/",
                          "boot", "01"):
            raise RuntimeError("boot failed — aborting feature tests")
        # Off the localhost:8xxx pattern the wheel resolves from the REMOTE
        # CDN (as on real Pages) — assert the runtime fetched it and that no
        # local wheel request failed.
        wheel_fetches = [ln for ln in suite.console
                         if "cross_file.fetch" in ln and "pygame_ce" in ln]
        local_wheel_404 = any(p == WHEEL_PATH and c == 404
                              for p, c in _QuietHandler.records)
        suite.add("boot: pygame wheel resolved", bool(wheel_fetches)
                  and not local_wheel_404,
                  wheel_fetches[0][-100:] if wheel_fetches
                  else "no wheel fetch seen in console")

        # ---------------- STEP 2: features --------------------------------
        # 1. ships move: two shots 8 s apart differ in the chart region
        a = shot(page, "03_move_a.png")
        page.wait_for_timeout(8000)
        b = shot(page, "03_move_b.png")
        frac = region_diff(a, b)
        suite.add("ships move", frac > 0.002,
                  f"chart-region diff {frac:.4f} over 8 s")

        # 2. fps cap ~30, idle-dominant
        wait_beacon_count(page, suite, 4, timeout_s=30)
        bs = suite.beacons()
        fps = fps_between(bs[-2], bs[-1])
        wms = work_ms_between(bs[-2], bs[-1])
        idle = max(0.0, 1000.0 / fps - wms) if fps > 0 else 0.0
        cap_ok = 24.0 <= fps <= 33.5 and idle > wms
        suite.add("fps cap 30 / idle-dominant", cap_ok,
                  f"fps={fps:.1f} work={wms:.1f}ms idle={idle:.1f}ms")

        # 3. click-to-select + camera easing.  Click off a FRESH beacon: at
        # TIME_COMPRESSION a 5 s-stale position has drifted ~10 wu — right at
        # the select radius, i.e. a coin-flip click.
        n_now = len(suite.beacons())
        wait_beacon_count(page, suite, n_now + 1, timeout_s=12)
        bs = [d for d in suite.beacons() if "vessel" in d]
        if not bs:
            suite.add("click-select vessel", False, "no beacon vessel coords")
        else:
            bv = bs[-1]
            cx, cy = css_from_fb(page, bv, float(bv["vx"]), float(bv["vy"]))
            n_before = len([l for l in suite.console
                            if "[WEBTEST] selected=" in l])
            page.mouse.click(cx, cy)
            page.wait_for_timeout(1500)
            sel_lines = [l for l in suite.console
                         if "[WEBTEST] selected=" in l][n_before:]
            selected = bool(sel_lines) and not sel_lines[-1].endswith("=None")
            suite.add("click-select vessel", selected,
                      sel_lines[-1][-60:] if sel_lines
                      else f"no selection echo after click at ({cx:.0f},{cy:.0f})")
            # easing: three shots 0.35 s apart must all differ (camera gliding)
            e1 = shot(page, "08_ease_1.png")
            page.wait_for_timeout(350)
            e2 = shot(page, "08_ease_2.png")
            page.wait_for_timeout(350)
            e3 = shot(page, "08_ease_3.png")
            d12 = region_diff(e1, e2)
            d23 = region_diff(e2, e3)
            suite.add("follow easing (no snap)",
                      d12 > 0.003 and d23 > 0.0015,
                      f"diffs {d12:.4f} then {d23:.4f} (still gliding)")
            shot(page, "07_selected.png")

        # 4. Esc: deselect, no pause menu
        pre = shot(page, "09_esc_pre.png")
        n_before = len([l for l in suite.console
                        if "[WEBTEST] selected=" in l])
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
        post = shot(page, "09_esc_post.png")
        sel_lines = [l for l in suite.console
                     if "[WEBTEST] selected=" in l][n_before:]
        deselected = bool(sel_lines) and sel_lines[-1].endswith("=None")
        menu_frac = region_diff(pre, post)
        suite.add("Esc deselects, no menu", deselected and menu_frac < 0.35,
                  f"selected=None echoed={deselected}, "
                  f"screen diff {menu_frac:.3f} (menu overlay would be >0.5)")

        # 5. time compression: 3 (2x) then 4 (3x); steps/frame scales
        base = suite.beacons()[-1]
        page.keyboard.press("3")
        page.wait_for_timeout(6000)
        page.keyboard.press("4")
        wait_beacon_count(page, suite, len(suite.beacons()) + 2, timeout_s=15)
        bs = suite.beacons()
        sp = [d["speed"] for d in bs[-3:]]
        b1, b2 = bs[-2], bs[-1]
        steps_pf = ((int(b2["steps"]) - int(b1["steps"]))
                    / max(1, int(b2["n"]) - int(b1["n"])))
        base_pf = float(int(base["steps"])) / max(1, int(base["n"]))
        # 3x must be honest: steps/frame ~3x the 1x baseline (the old web step
        # cap of 4 pinned this at ~1.5x — the bug this assertion exists for).
        suite.add("time compression 3x", "3" in sp and steps_pf > 2.2 * base_pf,
                  f"beacon speeds {sp}, steps/f {base_pf:.2f} -> {steps_pf:.2f}")
        shot(page, "10_speed.png")

        # 8 (early, while at 3x — events flow faster): event log ticks
        ev0 = int(suite.beacons()[-1]["events"])
        got_event = False
        for _ in range(15):
            page.wait_for_timeout(5000)
            if int(suite.beacons()[-1]["events"]) > ev0:
                got_event = True
                break
        suite.add("event log ticks", got_event,
                  f"events {ev0} -> {suite.beacons()[-1]['events']} "
                  f"(sim at 3x)")
        page.keyboard.press("2")   # back to 1x for the soak
        page.wait_for_timeout(500)

        # 6. zoom: wheel in -> big change, wheel out
        z0 = shot(page, "04_zoom_pre.png")
        page.mouse.move(800, 450)
        page.mouse.wheel(0, -600)
        page.wait_for_timeout(1200)
        z1 = shot(page, "04_zoom_in.png")
        zfrac = region_diff(z0, z1)
        suite.add("zoom eases at cursor", zfrac > 0.10,
                  f"chart diff {zfrac:.3f} after wheel-in")
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(1200)

        # 7. hover: vessel ring + fleet row highlight
        n_now = len(suite.beacons())
        wait_beacon_count(page, suite, n_now + 1, timeout_s=12)
        bs = [d for d in suite.beacons() if "vessel" in d]
        if bs:
            bv = bs[-1]
            hx, hy = css_from_fb(page, bv, float(bv["vx"]), float(bv["vy"]))
            page.mouse.move(60, 850)          # park far away
            page.wait_for_timeout(400)
            h0 = shot(page, "05_hover_pre.png")
            page.mouse.move(hx, hy)
            page.wait_for_timeout(700)
            h1 = shot(page, "05_hover_vessel.png")
            r = (max(0, int(hx) - 90), max(0, int(hy) - 90), 180, 180)
            hfrac = region_diff(h0, h1, rect=r, step=3)
            suite.add("vessel hover ring", hfrac > 0.01,
                      f"local diff {hfrac:.3f} around vessel")
        else:
            suite.skip("vessel hover ring", "no beacon vessel coords")
        page.mouse.move(60, 850)
        page.wait_for_timeout(400)
        r0 = shot(page, "06_row_pre.png")
        # First fleet rows sit near fb (170, 205); map through the canvas box.
        _cr = canvas_rect(page)
        _bs = suite.beacons()[-1]
        page.mouse.move(_cr["x"] + 170 * _cr["w"] / int(_bs["fbw"]),
                        _cr["y"] + 205 * _cr["h"] / int(_bs["fbh"]))
        page.wait_for_timeout(500)
        r1 = shot(page, "06_hover_row.png")
        rfrac = region_diff(r0, r1, rect=(30, 220, 440, 90), step=3)
        suite.add("fleet row hover", rfrac > 0.004,
                  f"panel-strip diff {rfrac:.3f}")

        # 9. long-run stability
        t_end = time.monotonic() + args.longrun
        while time.monotonic() < t_end:
            page.wait_for_timeout(10000)
        bs = suite.beacons()
        window = [b for b in bs if float(b["t"]) >= float(bs[-1]["t"]) - args.longrun]
        fps_list = [fps_between(window[i], window[i + 1])
                    for i in range(len(window) - 1)]
        low = [f for f in fps_list if f < 25.0]
        tb = suite.tracebacks()
        suite.add(f"long-run {args.longrun}s stable",
                  not low and not tb,
                  f"{len(fps_list)} windows, min fps "
                  f"{min(fps_list):.1f}, tracebacks {len(tb)}"
                  if fps_list else "no beacon windows")
        shot(page, "11_longrun_end.png")

        ctx.close()
        stop(srv, thread)
        srv = thread = None

        # ---------------- STEP 3: Pages subpath preflight ------------------
        if os.path.isdir(DOCS_DIR):
            tmp = tempfile.mkdtemp(prefix="pages_preflight_")
            shutil.copytree(DOCS_DIR, os.path.join(tmp, "vela-sea"))
            # localhost-only shim: dev mode requests /cdn/ at the origin ROOT
            # (host==localhost); real Pages (host!=localhost) resolves the
            # wheel from the remote CDN instead — documented in build_web.py.
            shutil.copytree(os.path.join(DOCS_DIR, "cdn"),
                            os.path.join(tmp, "cdn"))
            srv, thread = serve(tmp)
            ctx2 = browser.new_context(viewport=VIEWPORT)
            page2 = ctx2.new_page()
            attach(page2, suite)
            n0 = len(suite.beacons())
            page2.goto(f"http://localhost:{PORT}/vela-sea/",
                       wait_until="domcontentloaded")
            try:
                page2.wait_for_selector("#vela-brand-splash", timeout=8000)
                splash2 = True
            except Exception:
                splash2 = False
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline and len(suite.beacons()) < n0 + 2:
                page2.wait_for_timeout(1000)
            booted2 = len(suite.beacons()) >= n0 + 2
            bad2 = [(p, c) for p, c in _QuietHandler.records
                    if c == 404 and p != "/favicon.ico"]
            page2.wait_for_timeout(3000)
            shot(page2, "12_subpath_sea.png")
            suite.add("Pages subpath: boot under /vela-sea/",
                      splash2 and booted2 and not bad2,
                      f"splash={splash2} beacons={len(suite.beacons()) - n0} "
                      f"404s={bad2[:4] if bad2 else 'none'}")
            ctx2.close()
        else:
            suite.skip("Pages subpath preflight",
                       "docs/ missing — deploy step never landed")

    except _SpecialDone:
        pass
    finally:
        try:
            if browser is not None:
                browser.close()
            if pw is not None:
                pw.stop()
        except Exception:
            pass
        if srv is not None:
            stop(srv, thread)
        if tmp and os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        # Artifacts: full console log + summary table
        with open(os.path.join(OUT_DIR, "console.log"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(suite.console))
            if suite.errors:
                f.write("\n\n=== pageerrors ===\n" + "\n".join(suite.errors))
        with open(os.path.join(OUT_DIR, "summary.md"), "w",
                  encoding="utf-8") as f:
            f.write("# Browser test summary\n\n")
            f.write("| test | verdict | evidence |\n|---|---|---|\n")
            for name, verdict, ev in suite.rows:
                f.write(f"| {name} | {verdict} | {ev} |\n")

    failed = [r for r in suite.rows if r[1] == "FAIL"]
    print(f"\n{len(suite.rows) - len(failed)}/{len(suite.rows)} passed"
          + (f" — FAILURES: {[r[0] for r in failed]}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
