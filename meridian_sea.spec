# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build spec for Meridian Sea (tracked, reproducible — see DISTRIBUTION.md).
#
#   Build:   pyinstaller meridian_sea.spec
#   Output:  dist/MeridianSea/  (run MeridianSea.exe — no Python needed)
#
# Folder build (one EXE + a COLLECT dir), NOT one-file: it launches faster and
# trips fewer antivirus heuristics than a single self-extracting .exe.
#
# datas=[('assets', 'assets')] bundles the 7 pre-generated sound wavs into the
# app under assets/sounds, matching config.SOUND_DIR = resource_path('assets/
# sounds'). Bundling them (rather than generating at runtime) means the sound
# layer never has to WRITE into the read-only bundle dir — see DISTRIBUTION.md.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MeridianSea',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,            # GUI app — no terminal window opens behind the game
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/icon.ico',  # no icon yet — drop a .ico here and uncomment later
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MeridianSea',
)
