# -*- coding: utf-8 -*-
"""大轩巴入库器网页版 · 打包脚本
================================
用 PyInstaller 把 dxb_desktop.py（内嵌 Flask 服务器 + QT6 WebEngine 窗口）
打包成单个 exe。

关键点：
1. app.py 是用 importlib 动态加载的，PyInstaller 静态分析扫不到，
   必须作为 data 打进去，并手动声明它 import 的第三方库。
2. templates / static / assets 作为 data 打包，运行时落在 sys._MEIPASS。
3. backend 用 hidden-import 收集，其传递依赖会被自动分析。
4. 排除 tkinter：运行时由 dxb_desktop.py 注入空壳，避免打包 tcl/tk 整套。

用法：python build_exe.py
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
NAME = '大轩巴入库器网页版'

sep = os.pathsep

# ---- 数据文件（源码路径;包内相对路径）----
datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('assets', 'assets'),
    ('app.py', '.'),          # 动态加载的 Flask 入口，必须作为数据打包
]

# ---- 需要显式声明的隐藏依赖 ----
# app.py 是 data，PyInstaller 分析不到它的 import，故需手工列出。
# backend 走 hidden-import，其依赖会被自动递归收集。
hidden = [
    'backend',
    'flask',
    'flask_socketio',
    'flask_cors',
    'engineio',
    'engineio.async_drivers.threading',
    'socketio',
    'simple_websocket',
    'httpx',
    'aiofiles',
    'colorlog',
    'ujson',
    'vdf',
    'requests',
    # backend 用标准库 winreg（Windows 自带），无需 pywin32
]

excludes = [
    'tkinter',      # 运行时空壳替代
    'matplotlib',
    'numpy',
    'pytest',
    'PIL',
]


def main():
    # 把 PySide6 的 plugins 目录（含 platforms/qwindows.dll 窗口平台插件）打进包，
    # 否则冻结后创建 QApplication 会因找不到 qwindows 平台插件而崩溃。
    try:
        import PySide6  # noqa
        _ps_dir = os.path.dirname(PySide6.__file__)
        _plug = os.path.join(_ps_dir, 'plugins')
        if os.path.isdir(_plug):
            datas.append((_plug, 'PySide6/plugins'))
    except Exception:
        pass

    import PyInstaller.__main__

    args = [
        '--noconfirm',
        # 注意：不用 --clean，它会批量删除 build 目录（在受限环境会被安全策略拦截）
        '--onefile',
        '--windowed',
        f'--name={NAME}',
        f'--distpath={BASE / "dist"}',
        f'--workpath={BASE / "build"}',
        f'--specpath={BASE}',
    ]

    for src, dst in datas:
        p = BASE / src
        if p.exists():
            args.append(f'--add-data={p}{sep}{dst}')
        else:
            print(f'[警告] 缺少数据路径，已跳过：{p}')

    for h in hidden:
        args.append(f'--hidden-import={h}')

    for e in excludes:
        args.append(f'--exclude-module={e}')

    # 控制台保留日志能力：windowed 下 dxb_desktop 会把日志写入 dxb_run.log
    args.append(str(BASE / 'dxb_desktop.py'))

    print('[大轩巴] 打包参数：')
    for a in args:
        print('   ', a)

    PyInstaller.__main__.run(args)


if __name__ == '__main__':
    main()
