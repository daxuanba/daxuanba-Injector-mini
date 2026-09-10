# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\大轩巴入库器网页版\\dxb_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('D:\\大轩巴入库器网页版\\templates', 'templates'), ('D:\\大轩巴入库器网页版\\static', 'static'), ('D:\\大轩巴入库器网页版\\assets', 'assets'), ('D:\\大轩巴入库器网页版\\app.py', '.'), ('C:\\Users\\HW\\.workbuddy\\binaries\\python\\envs\\default\\Lib\\site-packages\\PySide6\\plugins', 'PySide6/plugins')],
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
    name='大轩巴入库器mini',
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
    icon=['D:\\大轩巴入库器网页版\\assets\\icon.ico'],
)
