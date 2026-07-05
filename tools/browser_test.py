"""Automated real-browser test suite for the Meridian Sea web build.

Drives headless Chromium (Playwright) against the built site: boot + splash,
feature-by-feature checks (motion, fps cap, select/follow easing, Esc, time
compression, zoom, hover, event feed, long-run stability), then a GitHub
Pages preflight that serves docs/ under a /gps-simulator/ SUBPATH exactly as
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
    python tools/browser_test.py                # full run (~10-12 min)
    python tools/browser_test.py --skip-build   # reuse existing build/web
    python tools/browser_test.py --longrun 60   # shorten the stability soak

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
WEB_DIR = os.path.join(ROOT, "build", "MeridianSea", "build", "web")
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


def boot_phase(page, suite, url, tag, shots_prefix):
    """Navigate + splash + boot-to-beacons + 404/traceback audit."""
    page.goto(url, wait_until="domcontentloaded")
    splash_seen = False
    try:
        page.wait_for_selector("#meridian-brand-splash", timeout=8000)
        splash_seen = True
    except Exception:
        pass
    shot(page, f"{shots_prefix}_splash.png")
    suite.add(f"{tag}: branded splash", splash_seen,
              "MERIDIAN SEA splash div present" if splash_seen
              else "splash div never appeared")

    booted = wait_beacon_count(page, suite, 2, timeout_s=240)
    n_webprof = sum(1 for ln in suite.console if "[WEBPROF]" in ln)
    suite.add(f"{tag}: boot (sim loop alive)", booted,
              f"{len(suite.beacons())} [WEBTEST] beacons, "
              f"{n_webprof} [WEBPROF] console lines")
    if not booted:
        return False

    bad = [(p, c) for p, c in _QuietHandler.records
           if c == 404 and p != "/favicon.ico"]
    suite.add(f"{tag}: no asset 404s", not bad,
              "requests clean" if not bad else f"404s: {bad[:5]}")
    tb = suite.tracebacks()
    suite.add(f"{tag}: zero Python tracebacks", not tb,
              "console clean" if not tb else tb[0][:160])
    r = canvas_rect(page)
    fills = (abs(r["w"] - VIEWPORT["width"]) <= 12
             and abs(r["h"] - VIEWPORT["height"]) <= 12)
    suite.add(f"{tag}: canvas fills viewport (no letterbox)", fills,
              f"canvas {r['w']:.0f}x{r['h']:.0f} at ({r['x']:.0f},{r['y']:.0f})"
              f" in {VIEWPORT['width']}x{VIEWPORT['height']}")
    page.wait_for_timeout(3000)
    shot(page, f"{shots_prefix}_sea.png")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--longrun", type=int, default=180)
    args = ap.parse_args()

    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)

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
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        page.on("console", lambda m: suite.console.append(m.text))
        page.on("pageerror", lambda e: suite.errors.append(str(e)))

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
            shutil.copytree(DOCS_DIR, os.path.join(tmp, "gps-simulator"))
            # localhost-only shim: dev mode requests /cdn/ at the origin ROOT
            # (host==localhost); real Pages (host!=localhost) resolves the
            # wheel from the remote CDN instead — documented in build_web.py.
            shutil.copytree(os.path.join(DOCS_DIR, "cdn"),
                            os.path.join(tmp, "cdn"))
            srv, thread = serve(tmp)
            ctx2 = browser.new_context(viewport=VIEWPORT)
            page2 = ctx2.new_page()
            page2.on("console", lambda m: suite.console.append(m.text))
            page2.on("pageerror", lambda e: suite.errors.append(str(e)))
            n0 = len(suite.beacons())
            page2.goto(f"http://localhost:{PORT}/gps-simulator/",
                       wait_until="domcontentloaded")
            try:
                page2.wait_for_selector("#meridian-brand-splash", timeout=8000)
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
            suite.add("Pages subpath: boot under /gps-simulator/",
                      splash2 and booted2 and not bad2,
                      f"splash={splash2} beacons={len(suite.beacons()) - n0} "
                      f"404s={bad2[:4] if bad2 else 'none'}")
            ctx2.close()
        else:
            suite.skip("Pages subpath preflight",
                       "docs/ missing — deploy step never landed")

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
