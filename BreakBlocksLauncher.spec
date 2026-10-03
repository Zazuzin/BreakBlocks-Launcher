# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files


datas = collect_data_files("customtkinter")
datas += [("assets", "assets")]
datas += [
    ("LICENSE", "."),
    ("PRIVACY.md", "."),
    ("TERMS.md", "."),
    ("THIRD-PARTY-NOTICES.md", "."),
]

analysis = Analysis(
    ["breakblocks_launcher_boot.pyw"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="BreakBlocks Launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon="assets/branding/breakblocks_launcher.ico",
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="BreakBlocks Launcher",
)
