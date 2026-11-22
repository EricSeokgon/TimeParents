# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, SPECPATH)
sys.path.insert(0, str(Path(SPECPATH) / 'tools'))
from app_version import VERSION
from build_family import build as build_family


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.ico', 'assets'), ('assets/icon.png', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

file_info = None
if sys.platform == 'win32':
    from PyInstaller.utils.win32 import versioninfo as vi
    numeric_version = tuple(map(int, VERSION.split('.'))) + (0,)
    strings = vi.StringTable('041204B0', [
        vi.StringStruct('ProductName', 'TimeParents'),
        vi.StringStruct('FileDescription', 'TimeParents'),
        vi.StringStruct('FileVersion', VERSION),
        vi.StringStruct('ProductVersion', VERSION),
        vi.StringStruct('OriginalFilename', 'TimeParents.exe'),
    ])
    file_info = vi.VSVersionInfo(
        ffi=vi.FixedFileInfo(filevers=numeric_version, prodvers=numeric_version),
        kids=[vi.StringFileInfo([strings]), vi.VarFileInfo([vi.VarStruct('Translation', [1042, 1200])])],
    )

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TimeParents',
    version=file_info,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

if sys.platform == 'win32':
    build_family(Path(DISTPATH) / 'family', VERSION)
