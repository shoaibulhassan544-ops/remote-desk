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
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
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
    upx=True,
    console=False,  # windowed GUI app
    icon=None,
)
