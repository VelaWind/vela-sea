"""Headless visual preview of the WEB rendering path — the self-check harness.

Runs the exact IS_WEB code path off-browser (VELA_FORCE_WEB=1 + SDL dummy
video driver), boots spectator mode at a real-canvas-like resolution, advances
the simulation, and saves PNG snapshots to tools/preview_out/ (gitignored):

    boot.png     first rendered frame (overview fit, panels, status bar)
    ambient.png  ~30 sim-seconds in (event log populated, vessels underway)
    follow.png   camera following a moving vessel (selection chip, info panel)
    zoom.png     zoomed-in frame (static chunk rebuilt at high zoom)

It also prints a [WEBPROF]-style bucket breakdown (sim / chart / panels /
flip).  Absolute ms are native CPython — far faster than WASM — but the
RATIOS between buckets show where frame time goes.

THE RULE (see CLAUDE.md): after every visual change to the web build, re-run
this and actually LOOK at the PNGs before moving on.

Usage:
    python tools/web_preview.py                 # 1835x980 (real-canvas match)
    python tools/web_preview.py --size 1280x720
"""

import argparse
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["VELA_FORCE_WEB"] = "1"   # config.IS_WEB -> True (web code path)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

OUT_DIR = os.path.join(ROOT, "tools", "preview_out")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size", default="1835x980",
                    help="framebuffer WxH (default 1835x980 = real canvas)")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.lower().split("x"))

    import main as game_main
    # Headless: the JS bridge is absent, so the fallback IS the framebuffer.
    game_main.WEB_FB_FALLBACK_W, game_main.WEB_FB_FALLBACK_H = w, h
    import pygame

    os.makedirs(OUT_DIR, exist_ok=True)
    g = game_main.Game()
    assert g.player_vessel is None, "web path must boot as spectator"
    prof = g._prof
    assert prof is not None, "WEB_PROFILE should be on for the web path"

    def frames(n: int) -> None:
        for _ in range(n):
            s = time.perf_counter()
            g.update_simulation(1.0 / 30.0)
            prof.sim += time.perf_counter() - s
            g.render()          # fills prof.chart / prof.panels / prof.flip
            prof.n += 1
            prof.steps += g.last_sim_steps

    def snap(name: str) -> None:
        path = os.path.join(OUT_DIR, name)
        pygame.image.save(g.display, path)
        print(f"saved {path}")

    # 1. Boot frame (static chunk builds on the first render).
    frames(2)
    snap("boot.png")

    # 2. ~30 sim-seconds of ambience (event log fills, vessels move).
    t0 = g.mission_manager.sim_elapsed_s
    while g.mission_manager.sim_elapsed_s - t0 < 30.0:
        frames(1)
    snap("ambient.png")

    # 3. Following a moving vessel (selected chip + info panel visible).
    target = next((v for v in g.world.vessels if v.status == "underway"),
                  g.world.vessels[0])
    g.selected_vessel = target
    g.camera.set_follow_target(target)
    frames(12)
    snap("follow.png")

    # 4. Zoomed in on the followed vessel (chunk rebuild at high zoom).
    g.camera.zoom = 2.5
    g.camera.clamp_zoom(0.4, 4.0)
    pygame.time.wait(350)       # open the static-chunk rebuild throttle
    frames(12)
    snap("zoom.png")

    n = max(1, prof.n)
    m = 1e3
    print("\n[PREVIEW-PROF] %d frames | sim=%.2f chart=%.2f panels=%.2f "
          "flip=%.2f ms/f | steps/f=%.2f" % (
              n, prof.sim / n * m, prof.chart / n * m,
              prof.panels / n * m, prof.flip / n * m, prof.steps / n))
    print("(native CPython — read the RATIOS, not the absolute ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
