# -*- coding: utf-8 -*-
"""大轩巴入库器mini · QT6 桌面壳
=================================
把内嵌 Flask 本地服务器装进一个 QT6 窗口，直接加载网页。
- 优先 PySide6，其次 PyQt6（都需 WebEngine 组件）
- 若两者都没装，自动回退到系统默认浏览器打开网页
- 不影响原版：原版 `python app.py` 仍可独立运行并自动开浏览器

打包后（PyInstaller）行为：
- RESOURCE_DIR（代码 / 模板 / 静态资源）取自 sys._MEIPASS
- USER_DIR（config.json / userdata / temp / logs）固定落在 exe 同目录，
  保证用户配置持久化；若 exe 所在目录不可写，回退到 %LOCALAPPDATA%
- 日志统一写入 USER_DIR/dxb_run.log，便于排错

启动：python dxb_desktop.py
"""
import os
import sys
import time
import threading
import socket
import webbrowser
import urllib.request
import urllib.error
from pathlib import Path

# ------------------------------------------------------------------ 路径分离
IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    RESOURCE_DIR = Path(sys._MEIPASS)                       # 打包后的资源解压区
    EXE_DIR = Path(sys.executable).resolve().parent         # exe 所在目录
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    EXE_DIR = RESOURCE_DIR


def pick_user_dir():
    """用户数据目录：源码运行=项目目录；打包运行=exe 同目录（不可写则回退 %LOCALAPPDATA%）"""
    if not IS_FROZEN:
        return RESOURCE_DIR
    try:
        probe = EXE_DIR / '.dxb_write_test'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        return EXE_DIR
    except Exception:
        fallback = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'DaXuanBaInjector'
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


USER_DIR = pick_user_dir()

# app.py / backend.py 大量使用 Path.cwd() 作为数据落点，
# 必须把工作目录切到 USER_DIR，否则配置会写进临时解压区而丢失。
try:
    os.chdir(USER_DIR)
except Exception:
    pass
sys.path.insert(0, str(RESOURCE_DIR))
sys.path.insert(0, str(USER_DIR))


def setup_logging():
    """打包为 windowed 时控制台不可见，把 stdout/stderr 落盘"""
    if not IS_FROZEN:
        return
    try:
        fh = open(USER_DIR / 'dxb_run.log', 'w', encoding='utf-8', buffering=1)
        sys.stdout = fh
        sys.stderr = fh
    except Exception:
        pass


def _stub_tkinter():
    """app.py 顶层会 import tkinter（只在其 __main__ 选端口时用）。
    打包时注入空壳，避免把整套 tcl/tk 运行时打进 exe。"""
    if 'tkinter' in sys.modules:
        return
    import types

    class _Stub:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return _Stub()

        def __call__(self, *a, **k):
            return _Stub()

    tk = types.ModuleType('tkinter')
    ttk = types.ModuleType('tkinter.ttk')
    for attr in ('Tk', 'Toplevel', 'Frame', 'Label', 'Button', 'Entry',
                 'StringVar', 'IntVar', 'BooleanVar', 'DoubleVar',
                 'Checkbutton', 'Radiobutton', 'Listbox', 'Text', 'Canvas',
                 'messagebox', 'filedialog', 'simpledialog'):
        setattr(tk, attr, _Stub)
    for attr in ('Frame', 'Label', 'Button', 'Entry', 'Combobox', 'Style',
                 'LabelFrame', 'Progressbar', 'Notebook', 'Scrollbar'):
        setattr(ttk, attr, _Stub)
    tk.ttk = ttk
    sys.modules['tkinter'] = tk
    sys.modules['tkinter.ttk'] = ttk


def _ensure_tkinter():
    """有真实 tkinter 就用真的；没有（打包环境常精简掉）就注入空壳，
    保证 app.py 顶层 `import tkinter` 不炸。"""
    if 'tkinter' in sys.modules:
        return
    try:
        import tkinter  # noqa: F401
        return
    except Exception:
        _stub_tkinter()


_ensure_tkinter()

# 让 PyInstaller 收集 backend（app.py 是动态加载的，静态分析扫不到）
try:
    import backend  # noqa: F401
except Exception:
    pass


def find_free_port(start=7860, end=7920):
    """在 127.0.0.1 上找一个空闲端口"""
    for p in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex(('127.0.0.1', p)) != 0:
                return p
    return start


def wait_server_ready(url, timeout=60):
    """轮询等待 Flask 服务器真正起来，避免窗口先开却刷不出页面"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except urllib.error.HTTPError:
            return True          # 4xx 也说明服务器已经在工作
        except Exception:
            time.sleep(0.3)
    return False


def load_flask_module():
    """从 app.py 加载 Flask 应用（不触发 __main__ 的自动开浏览器）"""
    import importlib.util
    app_py = RESOURCE_DIR / 'app.py'
    spec = importlib.util.spec_from_file_location('dxb_flask_app', app_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 冻结环境下，app.py 是动态 importlib 加载的模块，Flask 的 get_root_path
    # 拿不到它的 __file__，会回退到当前工作目录，导致 templates/ 与 static/
    # 找不到（TemplateNotFound）。这里显式把模板/静态目录指向资源目录的绝对路径，
    # 并重建 jinja 环境，确保冻结后页面与静态资源都能正确加载。
    mod.app.template_folder = str(RESOURCE_DIR / 'templates')
    mod.app.static_folder = str(RESOURCE_DIR / 'static')
    try:
        mod.app.jinja_env = mod.app.create_jinja_environment()
    except Exception:
        pass
    return mod


def start_flask_server(port):
    """在子线程里跑本地服务器"""
    try:
        os.chdir(USER_DIR)
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
        import traceback
        traceback.print_exc()
        print('[大轩巴] 请确认已安装 flask / flask-socketio / requests / httpx')


def shutdown_server(url):
    """通知网页点击“关闭应用”后真正退出服务器进程"""
    try:
        urllib.request.urlopen(url + '/api/shutdown', timeout=2)
    except Exception:
        pass


# ---------- QT6 绑定（优先 PySide6，其次 PyQt6） ----------
HAVE_QT = None
try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QLabel
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage
    HAVE_QT = 'PySide6'
except ImportError as e:
    import traceback
    print('[大轩巴] PySide6 加载失败（将尝试 PyQt6）：', type(e).__name__, e)
    traceback.print_exc()
    try:
        from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QLabel
        from PyQt6.QtGui import QAction, QIcon
        from PyQt6.QtCore import QUrl, Qt
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEnginePage
        HAVE_QT = 'PyQt6'
    except ImportError:
        HAVE_QT = None


# 无 QT 环境时给占位，保证模块仍能 import（此时走浏览器回退分支，不会实例化窗口）
if HAVE_QT is None:
    QMainWindow = QWebEngineView = QToolBar = QLabel = QAction = QIcon = QUrl = QWebEnginePage = object


class DxbWebPage(QWebEnginePage):
    """target=_blank / window.open 弹出独立浏览窗口（带返回按钮）。
    无法创建窗口时直接不打开。"""
    def __init__(self, parent_view, win_ref=None):
        super().__init__(parent_view)
        self._win_ref = win_ref  # 用于拿到主窗口的弹窗容器

    def createWindow(self, wintype):
        host = self._win_ref() if callable(self._win_ref) else None
        if host is None:
            return None  # 打不开就不打开
        return host.open_popup()


class DxbPopup(QMainWindow):
    """外链独立小窗口：返回 / 关闭"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('大轩巴 · 浏览')
        self.setWindowIcon(QIcon(str(RESOURCE_DIR / 'assets' / 'icon.ico')))
        self.resize(1040, 720)
        self.setStyleSheet(
            'QMainWindow{background:#0b0b0b;}'
            'QToolBar{background:#0b0b0b;border:none;spacing:6px;}'
            'QToolButton{color:#f3f3f3;background:#1a1a1a;border:none;'
            'padding:6px 12px;border-radius:8px;}'
        )
        self.view = QWebEngineView()
        self.view.setPage(DxbWebPage(self.view, lambda: self.parent()))
        self.setCentralWidget(self.view)
        tb = QToolBar('导航')
        tb.setMovable(False)
        self.addToolBar(tb)
        for text, slot in (('返回', self.view.back), ('刷新', self.view.reload), ('关闭', self.close)):
            a = QAction(text, self)
            a.triggered.connect(slot)
            tb.addAction(a)

    def load(self, qurl):
        self.view.setUrl(qurl)


class DxbWindow(QMainWindow):
    def __init__(self, url):
        super().__init__()
        self.base_url = url
        self.setWindowTitle('大轩巴入库器mini')
        self.setWindowIcon(QIcon(str(RESOURCE_DIR / 'assets' / 'icon.ico')))
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
        self.browser.setPage(DxbWebPage(self.browser, lambda: self))
        self.setCentralWidget(self.browser)
        self.popups = []

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

    def open_popup(self):
        """创建外链浏览小窗口（保持引用防 GC）"""
        popup = DxbPopup(self)
        popup.setAttribute(Qt.WA_DeleteOnClose, True)
        popup.show()
        self.popups.append(popup)
        popup.destroyed.connect(lambda: self.popups.remove(popup) if popup in self.popups else None)
        return popup.view.page()

    def closeEvent(self, event):
        shutdown_server(self.base_url)
        event.accept()


def main():
    setup_logging()
    # 冻结环境显式指向 QT 平台插件目录，避免找不到 qwindows 导致窗口创建失败
    if IS_FROZEN:
        _qt_plugins = RESOURCE_DIR / 'PySide6' / 'plugins'
        if _qt_plugins.is_dir():
            os.environ.setdefault('QT_PLUGIN_PATH', str(_qt_plugins))
            os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH', str(_qt_plugins / 'platforms'))
    port = find_free_port()
    url = f'http://127.0.0.1:{port}'

    print(f'[大轩巴] 数据目录：{USER_DIR}')
    print(f'[大轩巴] 资源目录：{RESOURCE_DIR}')

    server_thread = threading.Thread(target=start_flask_server, args=(port,), daemon=True)
    server_thread.start()

    if HAVE_QT is None:
        print('[大轩巴] 未检测到 PySide6 / PyQt6，改用系统默认浏览器打开网页。')
        print(f'[大轩巴] 本地服务地址：{url}')
        wait_server_ready(url)
        webbrowser.open_new(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            shutdown_server(url)
        return

    print(f'[大轩巴] 使用 {HAVE_QT} 桌面窗口打开网页。')
    wait_server_ready(url)

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(RESOURCE_DIR / 'assets' / 'icon.ico')))
    win = DxbWindow(url)
    win.show()
    app.exec()
    shutdown_server(url)
    os._exit(0)


if __name__ == '__main__':
    main()
