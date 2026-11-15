# -*- mode: python ; coding: utf-8 -*-

# NSCP desktop build.
#
# The splash is drawn procedurally (no GIF), so no animation asset is bundled.
# Only the app icon and the packaged resources ship with the binary.

a = Analysis(
    ['src\\npsc_gui\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/npsc_resources', 'npsc_resources'),
        ('assets/icons/nscp.ico', 'assets/icons'),
        ('assets/icons/neuro-prompt-semantic-compiler.svg', 'assets/icons'),
    ],
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
    name='NSCP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icons\\nscp.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NSCP',
)
