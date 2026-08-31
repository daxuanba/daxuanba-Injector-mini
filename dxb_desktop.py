# -*- coding: utf-8 -*-
"""大轩巴入库器网页版 · QT6 桌面壳
=================================
把内嵌 Flask 本地服务器装进一个 QT6 窗口，直接加载网页。
- 优先 PySide6，其次 PyQt6（都需 WebEngine 组件）
- 若两者都没装，自动回退到系统默认浏览器打开网页
- 不影响原版：原版 `python app.py` 仍可独立运行并自动开浏览器

启动：python dxb_desktop.py
"""
import os
import sys
import threading
import socket
import webbrowser
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def find_free_port(start=7860, end=7920):
    """在 127.0.0.1 上找一个空闲端口"""
    for p in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return start


def load_flask_module():
    """从 app.py 加载 Flask 应用（不触发 __main__ 的自动开浏览器）"""
    import importlib.util
    spec = importlib.util.spec_from_file_location('dxb_flask_app', BASE / 'app.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def start_flask_server(port):
    """在子线程里跑本地服务器"""
    os.chdir(BASE)
    try:
        mod = load_flask_module()
        print(f'[大轩巴] 本地服务器已启动：http://127.0.0.1:{port}')
        mod.socketio.run(
            mod.app,
            host='127.0.0.1',
            port=port,
            debug=False,
            allow_unsafe_werkzeug=True,
        )
    except Exception as e:
        print('[大轩巴] 服务器启动失败：', e)
        print('[大轩巴] 请确认已安装 flask / flask-socketio / requests / httpx')


def shutdown_server(url):
    """通知网页点击“关闭应用”后真正退出服务器进程"""
    try:
        urllib.request.urlopen(url + '/api/shutdown', timeout=2)
    except Exception:
        pass


# ---------- QT6 绑定（优先 PySide6，其次 PyQt6） ----------
HAVE_QT = None
QtWidgets = QtCore = QtWeb = None
try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QLabel, QAction
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAVE_QT = 'PySide6'
except ImportError:
    try:
        from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QLabel, QAction
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        HAVE_QT = 'PyQt6'
    except ImportError:
        HAVE_QT = None


# 无 QT 环境时给占位，保证模块仍能 import（此时走浏览器回退分支，不会实例化窗口）
if HAVE_QT is None:
    QMainWindow = QWebEngineView = QToolBar = QLabel = QAction = QUrl = object


class DxbWindow(QMainWindow):
    def __init__(self, url):
        super().__init__()
        self.base_url = url
        self.setWindowTitle('大轩巴入库器网页版')
        self.resize(1240, 820)
        self.setStyleSheet(
            'QMainWindow{background:#0b0b0b;}'
            'QToolBar{background:#0b0b0b;border:none;spacing:6px;}'
            'QLabel{color:#f1c40f;font-weight:700;font-size:15px;}'
            'QToolButton{color:#f3f3f3;background:#1a1a1a;border:none;'
            'padding:6px 12px;border-radius:8px;}'
            'QToolButton:hover{background:#262626;}'
        )

        self.browser = QWebEngineView()
        self.setCentralWidget(self.browser)

        tb = QToolBar('导航')
        tb.setMovable(False)
        self.addToolBar(tb)

        brand = QLabel('大轩巴')
        tb.addWidget(brand)

        self._add_action(tb, '返回', lambda: self.browser.back())
        self._add_action(tb, '刷新', lambda: self.browser.reload())
        self._add_action(tb, '首页', lambda: self.browser.setUrl(QUrl(self.base_url)))

        self.browser.setUrl(QUrl(url))

    def _add_action(self, tb, text, slot):
        a = QAction(text, self)
        a.triggered.connect(slot)
        tb.addAction(a)

    def closeEvent(self, event):
        shutdown_server(self.base_url)
        event.accept()


def main():
    port = find_free_port()
    url = f'http://127.0.0.1:{port}'

    server_thread = threading.Thread(target=start_flask_server, args=(port,), daemon=True)
    server_thread.start()

    if HAVE_QT is None:
        print('[大轩巴] 未检测到 PySide6 / PyQt6，改用系统默认浏览器打开网页。')
        print(f'[大轩巴] 本地服务地址：{url}')
        webbrowser.open_new(url)
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            shutdown_server(url)
        return

    print(f'[大轩巴] 使用 {HAVE_QT} 桌面窗口打开网页。')
    app = QApplication(sys.argv)
    win = DxbWindow(url)
    win.show()
    app.exec()
    shutdown_server(url)
    os._exit(0)


if __name__ == '__main__':
    main()
