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

Usage
-----
    python tools/build_web.py            # build only  -> build/web-src/build/web/
    python tools/build_web.py --serve    # build + serve at http://localhost:8000

Output lives under build/ (gitignored).  `--disable-sound-format-error` is
passed because the effects are stdlib-generated PCM WAVs; pygbag prefers OGG but
packs WAV with the flag (browser playback is handled fail-safe at runtime).
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# pygbag derives the app/apk name from this folder's name, so name it nicely:
# the bundle ships as MeridianSea.apk.  Lives under build/ (gitignored).
STAGE = os.path.join(ROOT, "build", "MeridianSea")

# The ONLY things that ship to the browser: the runtime files, nothing else.
RUNTIME_FILES = ["main.py", "config.py"]
RUNTIME_DIRS = ["engine", "render", "data", "assets"]


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


def main() -> int:
    stage_clean_tree()
    serve = "--serve" in sys.argv
    cmd = [sys.executable, "-m", "pygbag", "--disable-sound-format-error",
           "--title", "Meridian Sea"]
    if not serve:
        cmd.append("--build")
    cmd.append(STAGE)
    print(f"staged clean runtime tree -> {STAGE}")
    print("running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
