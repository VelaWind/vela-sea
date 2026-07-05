# Distribution — packaging Vela Sea as a standalone Windows build

Vela Sea ships as a **folder-based PyInstaller build**: a `VelaSea.exe`
plus an `_internal/` folder of dependencies. Testers unzip and double-click the
exe — **no Python install required**.

## Prerequisites (developer machine)

```
python -m venv .venv                 # if you don't have one
.\.venv\Scripts\activate
pip install -r requirements-dev.txt  # runtime deps + PyInstaller (players don't need this)
```

`requirements.txt` stays clean (just `pygame`) so players never see PyInstaller.

## Build

```
pyinstaller vela_sea.spec
```

- Output: **`dist/VelaSea/`** containing `VelaSea.exe` and `_internal/`.
- The build recipe is the tracked **`vela_sea.spec`** (not ad-hoc CLI flags),
  so builds are reproducible. `build/` and `dist/` are git-ignored.
- Add `--clean` to force a fresh build: `pyinstaller vela_sea.spec --clean`.

What the spec does:
- `console=False` — GUI app; no terminal window opens behind the game.
- `datas=[('assets', 'assets')]` — bundles the 7 pre-generated sound wavs.
- `name='VelaSea'` — output exe/folder name.
- No icon yet — there's a commented `icon=` line in the spec; drop a `.ico` into
  `assets/` and uncomment it to brand the exe and window.

## Make a release zip

```
python -c "import zipfile,os; src='dist/VelaSea'; \
z=zipfile.ZipFile('VelaSea_v0.6.0.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9); \
[z.write(os.path.join(r,f),'VelaSea/'+os.path.relpath(os.path.join(r,f),src).replace(os.sep,'/')) \
for r,_,fs in os.walk(src) for f in fs]; z.close()"
```

> Use Python's `zipfile` (forward-slash entries), **not** PowerShell
> `Compress-Archive` — on PowerShell 5.1 it writes backslash separators, a
> non-standard ZIP that some extractors mishandle.

- One-file builds (`--onefile`) are intentionally **avoided**: they launch
  slower (self-extract every run) and trip more antivirus heuristics.

## Version naming

`VelaSea_v<MAJOR>.<MINOR>.<PATCH>.zip`, matching `GAME_VERSION` in
`config.py` (e.g. `VelaSea_v0.6.0.zip`). Bump `GAME_VERSION` first, rebuild,
then zip — the version shows on the title screen and is stamped into saves.

## For testers

1. Download `VelaSea_v0.6.0.zip`.
2. Unzip anywhere (Desktop, Downloads — anywhere writable).
3. Open the `VelaSea` folder and run **`VelaSea.exe`**.

No Python, no install. Keep the `_internal/` folder next to the exe.

### Antivirus note (expected, harmless)

The exe is **unsigned**, so Windows SmartScreen may show *"Windows protected your
PC"* on first launch. Testers click **More info → Run anyway**. Windows Defender
occasionally quarantines unsigned PyInstaller exes as a false positive. This is
normal for indie PyInstaller builds; the real fix is an Authenticode code-signing
certificate (paid) for a public release.

## Where the game keeps its save & settings

- **Frozen (.exe):** `%APPDATA%\VelaSea\` — both `save.json` (career) and
  `settings.json` (audio/display/keybinds/gameplay) live here
  (e.g. `C:\Users\<you>\AppData\Roaming\VelaSea\`) — always writable, even if
  the app is unzipped under `Program Files`.
- **From source:** `save.json` / `settings.json` in the working directory
  (dev/test behaviour unchanged).

This split is handled by `config.user_data_dir()` (keyed on `sys.frozen`), so the
bundle directory itself is never written to. A missing `settings.json` just means
defaults (identical to prior behaviour). Sounds are likewise **read** from
the bundle (`config.resource_path('assets/sounds')` → `sys._MEIPASS`); the wavs
are pre-generated and bundled, so the sound layer never needs to write into the
read-only bundle at runtime.
