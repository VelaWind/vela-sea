# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build spec for Vela Sea (tracked, reproducible — see DISTRIBUTION.md).
#
#   Build:   pyinstaller vela_sea.spec
#   Output:  dist/VelaSea/  (run VelaSea.exe — no Python needed)
#
# Folder build (one EXE + a COLLECT dir), NOT one-file: it launches faster and
# trips fewer antivirus heuristics than a single self-extracting .exe.
#
# datas=[('assets', 'assets')] bundles the 7 pre-generated sound wavs into the
# app under assets/sounds, matching config.SOUND_DIR = resource_path('assets/
# sounds'). Bundling them (rather than generating at runtime) means the sound
# layer never has to WRITE into the read-only bundle dir — see DISTRIBUTION.md.

import sys


# Windows "Details" tab metadata (right-click VelaSea.exe -> Properties).
# Without this block the exe carries no version resource at all.  Every field
# is the project's public name only: no personal name, email or location may
# appear here, because this text ships inside every downloaded build.
# The version is read from config.GAME_VERSION so the exe can never disagree
# with the title screen.  config.py is pure Python (no Pygame), so importing
# it here is safe.
sys.path.insert(0, SPECPATH)
from config import GAME_VERSION  # noqa: E402

# The version resource only exists on Windows builds, and its helper module
# (pefile) is only installed there, so other platforms skip it.
VERSION_INFO = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
        VarStruct, VSVersionInfo)

    _ver = tuple(int(x) for x in GAME_VERSION.split(".")) + (0,)
    VERSION_INFO = VSVersionInfo(
        ffi=FixedFileInfo(filevers=_ver, prodvers=_ver),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "VelaWind"),
                StringStruct("FileDescription", "Vela Sea"),
                StringStruct("FileVersion", GAME_VERSION),
                StringStruct("InternalName", "VelaSea"),
                StringStruct("LegalCopyright", "Copyright (c) 2026 VelaWind"),
                StringStruct("OriginalFilename", "VelaSea.exe"),
                StringStruct("ProductName", "Vela Sea"),
                StringStruct("ProductVersion", GAME_VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 0x04B0])]),
        ],
    )

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
    name='VelaSea',
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
    version=VERSION_INFO,     # public project metadata only (see top of file)
    # icon='assets/icon.ico',  # no icon yet — drop a .ico here and uncomment later
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VelaSea',
)
