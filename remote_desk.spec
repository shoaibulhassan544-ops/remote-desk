# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one-file windowed build of RemoteDesk."""
import os
block_cipher = None

a = Analysis(
    # DO NOT use app/main.py here: it uses relative imports and fails
    # in a built EXE with "attempted relative import with no known
    # parent package". run.py uses absolute imports instead.
    ['run.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[('assets/icon.png', 'assets')],  # window/taskbar icon at runtime
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # v1.0.10: excludes stays EMPTY on purpose — excluding any VC++
    # runtime DLLs would break the bundle on PCs without that runtime
    # ("Failed to load Python DLL"). One-file build is kept.
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name='RemoteDesk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # v1.0.10: UPX DISABLED on purpose. UPX-compressed onefile bundles
    # are a known cause of antivirus interference + extraction / DLL
    # load failures ("Failed to load Python DLL ... python311.dll").
    # A slightly bigger EXE that always starts beats a smaller one
    # that sometimes fails to load.
    upx=False,
    console=False,  # windowed GUI app
    icon='assets/icon.ico',  # EXE + taskbar icon
)
