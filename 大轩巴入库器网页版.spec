# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['dxb_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('static', 'static'), ('assets', 'assets'), ('app.py', '.'), ('C:/Users/HW/.workbuddy/binaries/python/envs/default/Lib/site-packages/PySide6/plugins', 'PySide6/plugins')],
    hiddenimports=['backend', 'flask', 'flask_socketio', 'flask_cors', 'engineio', 'engineio.async_drivers.threading', 'socketio', 'simple_websocket', 'httpx', 'aiofiles', 'colorlog', 'ujson', 'vdf', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pytest', 'PIL'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='大轩巴入库器网页版',
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
)
