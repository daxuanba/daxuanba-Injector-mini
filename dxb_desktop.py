# -*- coding: utf-8 -*-
"""大轩巴入库器mini · 桌面壳（主窗口内嵌 WebView2）
==================================================
把内嵌 Flask 本地服务器装进**本程序自己的窗口**里显示，不跳外部浏览器。

窗口引擎：pywebview + 系统 Microsoft Edge WebView2
- 浏览器内核不打包进 exe（不再依赖 Qt WebEngine，体积从 250MB 降到 ~35MB）
- 依赖 Windows 系统自带的 WebView2 Runtime；检测不到就弹原生提示并引导去微软官方安装
- 免hosts加速：用 WebView2 官方支持的环境变量 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
  向内核注入 --host-resolver-rules（不改系统 hosts、不需管理员）
- Steam 登录：开第二个内嵌窗口，从 WebView2 原生 CookieManager 读 steamLoginSecure
  （该 Cookie 是 HttpOnly，只有原生接口能拿到）

打包后（PyInstaller）行为：
- RESOURCE_DIR（代码 / 模板 / 静态资源）取自 sys._MEIPASS
- USER_DIR（config.json / userdata / temp / logs）固定落在 exe 同目录，
  保证用户配置持久化；若 exe 所在目录不可写，回退到 %LOCALAPPDATA%
- 日志统一写入 USER_DIR/dxb_run.log，便于排错

启动：python dxb_desktop.py
"""
import os
import sys
import json
import re
import time
import threading
import socket
import subprocess
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
    """从 app.pyd / app.py 加载 Flask 应用（不触发 __main__ 的自动开浏览器）

    加密版优先：app.pyd 是 Cython 编译出的真实扩展模块（源码不可见），
    扩展模块的初始化函数必须与模块名匹配（PyInit_app），故这里模块名固定为 'app'。
    没有 .pyd 时回退到明文 app.py，保持开发/未加密构建可用。
    """
    import importlib.util
    app_pyd = RESOURCE_DIR / 'app.pyd'
    if app_pyd.exists():
        load_path, mod_name = app_pyd, 'app'
    else:
        load_path, mod_name = RESOURCE_DIR / 'app.py', 'dxb_flask_app'
    spec = importlib.util.spec_from_file_location(mod_name, load_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
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


def start_flask_server(port, mod=None):
    """在子线程里跑本地服务器（mod 由主线程加载后传入，避免重复加载）"""
    try:
        os.chdir(USER_DIR)
        if mod is None:
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


def load_accel_rules():
    """从 config.json 读免hosts加速映射，生成 Chromium --host-resolver-rules 字符串。
    仅重定向已启用分类的域名→IP，结尾 MAP * * 让其余域名走系统默认解析。"""
    try:
        cfg_path = USER_DIR / 'config.json'
        if not cfg_path.exists():
            return ''
        cfg = json.load(open(cfg_path, encoding='utf-8'))
        hf = cfg.get('accel_hostsfree', {}) or {}
        rules = []
        for cat, pairs in hf.items():
            for d, ip in (pairs or {}).items():
                rules.append(f'MAP {d} {ip}')
        if not rules:
            return ''
        rules.append('MAP * *')
        return ','.join(rules)
    except Exception:
        return ''


def _register_restart_launchers(mod, url):
    """注册提权重启 + 普通重启 launcher（与窗口引擎无关）。"""
    if hasattr(mod, 'register_elevated_restart'):
        def _relaunch_elevated():
            import ctypes
            if IS_FROZEN:
                exe = sys.executable
                params = ' '.join(f'"{a}"' for a in sys.argv[1:])
            else:
                exe = sys.executable
                files = [os.path.abspath(sys.argv[0])] + list(sys.argv[1:])
                params = ' '.join(f'"{p}"' for p in files)
            try:
                rc = ctypes.windll.shell32.ShellExecuteW(
                    None, 'runas', exe, params, str(Path(exe).resolve().parent), 1)
            except Exception as e:
                print('[大轩巴] 提权失败:', e)
                return False
            if int(rc) <= 32:
                print('[大轩巴] 提权被拒绝（ShellExecuteW 返回 %s）' % rc)
                return False
            # 1.5s 后再关旧实例：给 Flask 把「提权成功」的响应吐回页面留足时间
            threading.Timer(1.5, lambda: shutdown_server(url)).start()
            return True
        mod.register_elevated_restart(_relaunch_elevated)

    if hasattr(mod, 'register_app_restart'):
        def _relaunch_normal():
            try:
                subprocess.Popen([sys.executable] + list(sys.argv[1:]))
            except Exception as e:
                print('[大轩巴] 重启失败:', e)
                return False
            threading.Timer(0.5, lambda: shutdown_server(url)).start()
            return True
        mod.register_app_restart(_relaunch_normal)


def _make_in_app_opener(webview_mod):
    """构造「在应用内新开窗口」的回调，交给 app.py 的 /api/open-external 用。"""
    def _open(url):
        if webview_mod is None:
            return False
        try:
            w = webview_mod.create_window(
                '大轩巴 · 浏览', url, width=1180, height=820, min_size=(900, 600))
            return w is not None
        except Exception as e:
            print('[大轩巴] 应用内新窗口打开失败：', e)
            return False
    return _open


# ------------------------------------------------------------------ WebView2 运行时
# WebView2 Runtime 的 EdgeUpdate 客户端 GUID（微软固定值，Evergreen 版）
WEBVIEW2_CLIENT_GUID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
# 微软官方 Evergreen Bootstrapper 直链（约 2MB，装完系统所有 WebView2 程序共用）
WEBVIEW2_DOWNLOAD_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'


def webview2_runtime_version():
    """返回系统已安装的 WebView2 Runtime 版本号；未安装返回 ''。

    WebView2 Runtime 是 Windows 的系统组件（随 Edge 分发/更新），
    正常 Win10 1803+ / Win11 都自带；精简版系统或老旧系统可能没有。
    """
    # 1) 注册表（覆盖 64/32 位与“仅当前用户”安装三种情况）
    try:
        import winreg
        paths = [
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\\' + WEBVIEW2_CLIENT_GUID),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\EdgeUpdate\Clients\\' + WEBVIEW2_CLIENT_GUID),
            (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\EdgeUpdate\Clients\\' + WEBVIEW2_CLIENT_GUID),
        ]
        for hive, sub in paths:
            try:
                with winreg.OpenKey(hive, sub) as k:
                    pv, _ = winreg.QueryValueEx(k, 'pv')
                    pv = str(pv or '').strip()
                    if pv and pv != '0.0.0.0':
                        return pv
            except Exception:
                continue
    except Exception:
        pass
    # 2) 目录兜底（注册表被清理但文件还在的情况）
    for base in (os.environ.get('PROGRAMFILES(X86)'), os.environ.get('PROGRAMFILES'),
                 os.environ.get('LOCALAPPDATA')):
        if not base:
            continue
        app_dir = Path(base) / 'Microsoft' / 'EdgeWebView' / 'Application'
        try:
            vers = [p.name for p in app_dir.iterdir()
                    if p.is_dir() and p.name[:1].isdigit()]
        except Exception:
            continue
        if vers:
            return sorted(vers)[-1]
    return ''


def _message_box(text, title, flags):
    """原生提示框（windowed 打包后没有控制台，只能靠系统弹窗告知用户）"""
    try:
        import ctypes
        return int(ctypes.windll.user32.MessageBoxW(None, text, title, flags))
    except Exception:
        print('[大轩巴]', title, text)
        return 0


def prompt_install_webview2():
    """提示用户安装 WebView2 Runtime（系统组件，不随本程序打包）。"""
    text = (
        '本程序需要「Microsoft Edge WebView2 运行时」才能在自己的窗口里显示界面。\n'
        '当前系统未检测到该组件。\n\n'
        '它是 Windows 的系统级组件（约 2MB，装一次本机所有同类软件共用），\n'
        '所以不随本程序打包；装完重新打开本程序即可。\n\n'
        '点「是」打开微软官方下载页，点「否」退出。'
    )
    ret = _message_box(text, '大轩巴入库器mini · 缺少 WebView2 运行组件', 0x04 | 0x30)  # MB_YESNO|MB_WARNING
    if ret == 6:  # IDYES
        try:
            os.startfile(WEBVIEW2_DOWNLOAD_URL)
        except Exception:
            try:
                webbrowser.open_new(WEBVIEW2_DOWNLOAD_URL)
            except Exception:
                pass


# 加速内核混合端口（mihomo mixed-port）：开着时内嵌浏览器直连它
ACCEL_HTTP_PORT = 7890


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def apply_accel_to_webview2(rules, core_running=False):
    """免hosts加速 + 网络策略注入 WebView2 内核。

    v2.27 新增：以前只注入 --host-resolver-rules，WebView2 会**继承系统代理**。
    一旦加速把系统代理打开（或残留开着），页面里的 Google Fonts / socket.io CDN
    请求会被丢进代理里挂着不返回 —— 渲染停在白/灰屏，看上去就是「应用卡死」。
    所以这里显式决定内嵌浏览器的上网方式：
      - 加速在跑 → 直连加速端口，并把 127.0.0.1 排除（本地 API 必须直连）
      - 没加速   → --no-proxy-system（彻底忽略系统代理）
    """
    args = []
    args.append('--proxy-bypass-list=127.0.0.1;localhost')
    if core_running:
        args.append(f'--proxy-server=http://127.0.0.1:{ACCEL_HTTP_PORT}')
    else:
        args.append('--no-proxy-server')
    if rules:
        args.append(f'--host-resolver-rules={rules}')
    if not args:
        return False
    try:
        prev = os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '').strip()
        os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = (prev + ' ' + ' '.join(args)).strip()
        n = len([a for a in args if a.startswith('--host-resolver-rules=')])
        print(f'[大轩巴] WebView2 网络策略：{"加速端口直连" if core_running else "忽略系统代理"}'
              f'（{n} 条域名映射）')
        return True
    except Exception as e:
        print('[大轩巴] 注入加速参数失败：', e)
        return False


# ------------------------------------------------------------------ 内置登录窗口
class SteamLoginHelper:
    """用第二个内嵌 WebView2 窗口登录 Steam，轮询原生 CookieManager 抓 steamLoginSecure。

    - 登录态持久：与主窗口共用同一个 WebView2 用户数据目录（storage_path），
      下次启动仍处于登录状态（store.steampowered.com 的 Cookie 直接可用）。
    - 为什么轮询：pywebview 没暴露 cookie 变更事件，且 steamLoginSecure 是 HttpOnly，
      页面里 document.cookie 读不到，只能走原生 CookieManager（pywebview 内部已做
      主线程 marshal，可从后台线程安全调用）。
    """

    def __init__(self, webview_mod, flask_mod):
        self.webview = webview_mod
        self.flask_mod = flask_mod
        self.win = None
        self._done = False
        self._lock = threading.Lock()
        self._polling = False

    # ---- 供 Flask 线程调用（backend 请求登录时）----
    def open(self):
        """打开（或重新唤起）登录窗口。返回 False 让前端走「手动粘贴 Cookie」兜底。"""
        with self._lock:
            self._done = False
            if self.win is not None:
                try:
                    self.win.show()
                    self.win.restore()
                    self._start_poll()
                    return True
                except Exception:
                    self.win = None
            try:
                self.win = self.webview.create_window(
                    '大轩巴 · 登录 Steam',
                    'https://store.steampowered.com/login/',
                    width=1040, height=720, min_size=(760, 560),
                )
                self.win.events.closed += self._on_closed
            except Exception as e:
                print('[大轩巴] 登录窗口创建失败：', e)
                self.win = None
                return False
        self._start_poll()
        return True

    def _on_closed(self):
        self.win = None
        self._done = False

    def _start_poll(self):
        if self._polling:
            return
        self._polling = True
        threading.Thread(target=self._poll, daemon=True).start()

    def _cookie_jar(self):
        """读取当前窗口的全部 Cookie（含 HttpOnly）"""
        w = self.win
        if w is None:
            return {}
        try:
            raw = w.get_cookies() or []
        except Exception:
            return {}
        jar = {}
        for c in raw:
            try:
                name = getattr(c, 'name', None)
                if name is None and isinstance(c, dict):
                    name = c.get('name')
                value = getattr(c, 'value', None)
                if value is None and isinstance(c, dict):
                    value = c.get('value')
                if name:
                    jar[str(name)] = '' if value is None else str(value)
            except Exception:
                continue
        return jar

    def _poll(self):
        deadline = time.time() + 1800          # 最多等 30 分钟，超时自动停止轮询
        try:
            while time.time() < deadline:
                time.sleep(1.5)
                if self.win is None or self._done:
                    return
                jar = self._cookie_jar()
                if 'steamLoginSecure' not in jar:
                    continue
                self._done = True
                time.sleep(0.8)                # 等同批次的 sessionid 等到齐
                jar.update(self._cookie_jar())
                header = '; '.join(f'{k}={v}' for k, v in jar.items() if k)
                ok = False
                try:
                    res = self.flask_mod.steam_login_succeeded(header)
                    ok = bool(res and res.get('success'))
                except Exception as e:
                    print('[大轩巴] 登录态回传失败：', e)
                    try:
                        self.flask_mod.steam_login_failed(str(e))
                    except Exception:
                        pass
                if ok:
                    print('[大轩巴] Steam 登录成功，Cookie 已回传主程序。')
                    self._close()
                else:
                    print('[大轩巴] 读取到的登录态无效，保持窗口等待重试。')
                    self._done = False
                return
            print('[大轩巴] 登录窗口等待超时（30 分钟），停止轮询。')
        finally:
            self._polling = False

    def _close(self):
        w = self.win
        self.win = None
        try:
            if w is not None:
                w.destroy()
        except Exception:
            pass


# ------------------------------------------------------------------ 主窗口引用
# 重启/提权时，新实例会开一个新窗口，旧实例必须立刻把窗口收掉，
# 否则用户看到「一个主窗口 + 后面还压着一个旧窗口」。
_MAIN_WINDOW = None


def _close_main_window():
    """立刻销毁主窗口（从 Flask 线程调用，pywebview 会派发到 GUI 线程）。"""
    w = _MAIN_WINDOW
    if w is None:
        return
    try:
        w.destroy()
        print('[大轩巴] 旧窗口已关闭。')
    except Exception as e:
        print('[大轩巴] 关闭主窗口失败：', e)


# ------------------------------------------------------------------ 外链与 F12
# 问题：pywebview 的 edgechromium 里 window.open(url,'_blank') 会在**当前窗口**导航过去，
# 主窗口被替成 Steam 商店页 → 顶部标签栏和路由全丢，看起来像「卡死点不动」，
# 而且此时 F12/关闭按钮都失灵（用户实际遇到的正是这个）。
# 修法：拦截离开本地源的导航，一律丢给系统浏览器；主窗口永远只显示本地页面。

# 应用内新窗口的注册入口：页面点外链时优先用它开第二个内嵌窗口，
# 这样「在应用里打开浏览器」成立，又不会顶掉主窗口。
_IN_APP_OPENER = {'fn': None}


def register_in_app_opener(fn):
    _IN_APP_OPENER['fn'] = fn if callable(fn) else None


def _open_in_app(url):
    """在应用内开新窗口显示外部网页；内核起不来时回退系统浏览器。"""
    u = str(url or '').strip()
    if not u:
        return False
    opener = _IN_APP_OPENER.get('fn')
    if opener is not None:
        try:
            if opener(u):
                return True
        except Exception as e:
            print('[大轩巴] 应用内新窗口打开失败：', e)
    return _open_in_system(u)


def _open_in_system(url):
    u = str(url or '').strip()
    if not u:
        return False
    try:
        if hasattr(os, 'startfile'):
            os.startfile(u)
        else:
            webbrowser.open(u)
        print('[大轩巴] 外链已交给系统浏览器：', u[:120])
        return True
    except Exception as e:
        print('[大轩巴] 打开外链失败：', e)
        return False


def _is_absolute_http(url):
    return bool(re.match(r'^(https?:)?//', str(url or '').strip(), re.I))


def _install_external_link_guard(win, local_prefixes):
    """导航守卫（v2.27 重写）。

    原则：**站内一律放行**，只处理真正的外部目标。
    - 绝对 http(s) 外链 → 在应用内新开一个 WebView2 窗口（主窗口不动）
    - 非 http(s) 协议（steam://、mailto:）→ 交给系统默认程序
    - 站内 / 相对路径 / # 锚点 → 完全不拦，交给 WebView2 正常渲染
    """
    if win is None:
        return

    def _is_local(url):
        u = str(url or '').strip().lower()
        if not u:
            return True
        if u.startswith(('about:', 'data:', 'blob:', 'javascript:', 'file:', 'view-source:')):
            return True
        for p in local_prefixes:
            if u.startswith(p):
                return True
        return False

    try:
        native = getattr(win, 'native', None)
        chrome = getattr(native, 'browser', None)
        ctl = getattr(chrome, 'webview', None)
        core = ctl.CoreWebView2
    except Exception as e:
        print('[大轩巴] 外链拦截初始化失败（不影响使用）：', e)
        return

    def on_new_window(sender, args):
        try:
            uri = str(args.Uri)
        except Exception:
            return
        try:
            args.set_Cancel(True)
        except Exception:
            try:
                args.Cancel = True
            except Exception:
                pass
        # 站内交给 WebView2 自己开（多标签），外链开新窗口，非 http 协议交系统程序
        if _is_local(uri):
            return
        if _is_absolute_http(uri):
            _open_in_app(uri)
        else:
            _open_in_system(uri)

    def on_navigation_starting(sender, args):
        try:
            uri = str(args.Uri)
        except Exception:
            return
        if _is_local(uri):
            return
        try:
            args.set_Cancel(True)
        except Exception:
            try:
                args.Cancel = True
            except Exception:
                return
        # 外链：应用内新窗口；非 http 协议：系统程序
        if _is_absolute_http(uri):
            _open_in_app(uri)
        else:
            _open_in_system(uri)

    try:
        core.NewWindowRequested += on_new_window
    except Exception as e:
        print('[大轩巴] NewWindowRequested 拦截失败：', e)
    try:
        core.NavigationStarting += on_navigation_starting
    except Exception as e:
        print('[大轩巴] NavigationStarting 拦截失败：', e)

    # 页面注入：与 external-link.js 同一套判据（只拦绝对 http(s)）
    try:
        js = """
        (function () {
          if (window.__dxgInstalled) { return; }
          window.__dxgInstalled = true;
          const absHttp = (u) => /^(https?:)?\\/\\//i.test(String(u || '').trim());
          const origOpen = window.open;
          window.open = function (url, target, features) {
            try {
              if (url && absHttp(String(url).indexOf('://') > -1 ? String(url) : url)) {
                const inApp = (target !== '_self' && target !== '_top');
                fetch('/api/open-external', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ url: String(url), in_app: inApp })
                });
                return null;
              }
            } catch (e) {}
            return origOpen.apply(window, arguments);
          };
          document.documentElement.setAttribute('data-dxb-linkguard', '1');
          document.addEventListener('click', function (ev) {
            const a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
            if (!a) { return; }
            const href = (a.getAttribute('href') || '').trim();
            if (!href || href.charAt(0) === '#') { return; }
            if (href.indexOf('javascript:') === 0 || href.indexOf('mailto:') === 0) { return; }
            if (!absHttp(href)) { return; }
            ev.preventDefault();
            const d = a.dataset || {};
            fetch('/api/open-external', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url: href, in_app: (d.external !== 'browser') })
            });
          }, true);
        })();
        """
        win.load_js(js)
        print('[大轩巴] 外链守卫已启用（站内放行 / 外链应用内新窗口）。')
    except Exception as e:
        print('[大轩巴] 注入外链拦截脚本失败：', e)


def _enable_f12_devtools(win):
    """默认 debug=False 会让 pywebview 把 AreDevToolsEnabled 设成 False，
    F12 / Ctrl+Shift+I 就完全没反应。这里单独把 DevTools 打开。
    """
    if win is None:
        return

    def _open():
        try:
            native = getattr(win, 'native', None)
            core = native.browser.webview.CoreWebView2
            core.OpenDevToolsWindow()
            print('[大轩巴] DevTools 已打开。')
        except Exception as e:
            print('[大轩巴] 打开 DevTools 失败：', e)

    # 1) 放开内核层的 DevTools 开关
    def _enable():
        try:
            native = getattr(win, 'native', None)
            core = native.browser.webview.CoreWebView2
            s = core.Settings
            s.AreDevToolsEnabled = True
            s.AreBrowserAcceleratorKeysEnabled = True
            s.IsStatusBarEnabled = True
        except Exception as e:
            print('[大轩巴] 启用 DevTools 开关失败：', e)

    # 2) 页面注入 F12 键监听（内核在窗口创建时就把 accelerator 关了，
    #    纯靠键盘快捷键不可靠，必须在 JS 层自己接）
    js = """
    document.addEventListener('keydown', function (e) {
      if (e.key === 'F12' || ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'I' || e.key === 'i'))) {
        e.preventDefault();
        try { fetch('/api/devtools'); } catch (err) {}
      }
    }, true);
    """
    for attempt in range(40):
        try:
            if getattr(win, 'native', None) is not None:
                _enable()
                win.load_js(js)
                print('[大轩巴] F12 调试已启用。')
                return
        except Exception:
            pass
        time.sleep(0.15)
    print('[大轩巴] F12 调试启用超时（不影响正常使用）。')


# ------------------------------------------------------------------ 入口
def _import_webview():
    try:
        import webview
        return webview
    except Exception as e:
        print('[大轩巴] pywebview 导入失败：', e)
        return None


def main():
    setup_logging()
    port = find_free_port()
    url = f'http://127.0.0.1:{port}'

    print(f'[大轩巴] 数据目录：{USER_DIR}')
    print(f'[大轩巴] 资源目录：{RESOURCE_DIR}')

    # 窗口内核依赖系统 WebView2 Runtime：先检查，缺了直接提示去装（不白启动服务器）
    wv2 = webview2_runtime_version()
    if not wv2:
        print('[大轩巴] 未检测到 Microsoft Edge WebView2 Runtime，提示用户安装。')
        prompt_install_webview2()
        return
    print(f'[大轩巴] WebView2 Runtime：{wv2}')

    webview = _import_webview()
    if webview is None:
        _message_box(
            '缺少 pywebview 组件，无法创建内嵌窗口。\n'
            '请重新安装本程序，或联系作者。',
            '大轩巴入库器mini · 组件缺失', 0x10 | 0x00)
        return

    # 主线程先加载 Flask 模块，便于注入内置浏览器登录 launcher 与共享给后台线程
    try:
        mod = load_flask_module()
    except Exception as e:
        print('[大轩巴] Flask 模块加载失败，无法启动：', e)
        import traceback
        traceback.print_exc()
        _message_box(f'内部服务加载失败：\n{e}', '大轩巴入库器mini · 启动失败', 0x10)
        return

    # 免hosts加速 + 网络策略：必须在 WebView2 内核初始化前设置环境变量
    apply_accel_to_webview2(load_accel_rules(),
                            core_running=port_open('127.0.0.1', ACCEL_HTTP_PORT))

    server_thread = threading.Thread(target=start_flask_server, args=(port, mod), daemon=True)
    server_thread.start()

    _register_restart_launchers(mod, url)

    # 应用内新窗口：点外链时在本程序里开第二个 WebView2 窗口（不跳系统浏览器）
    try:
        if hasattr(mod, 'register_in_app_opener'):
            mod.register_in_app_opener(_make_in_app_opener(webview))
            print('[大轩巴] 应用内新窗口已注册（外链在本程序内打开）。')
    except Exception as e:
        print('[大轩巴] 注册应用内窗口失败：', e)

    print(f'[大轩巴] 本地服务地址：{url}')
    wait_server_ready(url)

    # 窗口行为：允许下载（配合下载管理）、外链不外跳系统浏览器、隐藏默认菜单
    try:
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
        webview.settings['SHOW_DEFAULT_MENUS'] = False
    except Exception as e:
        print('[大轩巴] 设置窗口选项失败：', e)

    win = webview.create_window(
        '大轩巴 入库器mini', url,
        width=1320, height=900, min_size=(1024, 700),
        text_select=True,
    )
    if win is None:
        _message_box('主窗口创建失败。', '大轩巴入库器mini · 启动失败', 0x10)
        return

    # 登录 launcher：Flask 线程请求登录时开第二个内嵌窗口（仍在本程序内，不外跳）
    helper = SteamLoginHelper(webview, mod)
    if hasattr(mod, 'register_steam_login_launcher'):
        mod.register_steam_login_launcher(helper.open)

    # 关窗 launcher：重启/提权时 /api/shutdown 会先收掉这个窗口再退进程
    global _MAIN_WINDOW
    _MAIN_WINDOW = win
    if hasattr(mod, 'register_window_closer'):
        mod.register_window_closer(_close_main_window)

    # private_mode=False + storage_path：Cookie 持久化到用户目录，
    # Steam 登录态跨启动保留（与登录窗口共用同一份用户数据目录）
    profile_dir = USER_DIR / 'steambrowser_profile'
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    def _open_external_url(url):
        u = str(url or '').strip()
        if not u:
            return False
        try:
            if hasattr(os, 'startfile'):
                os.startfile(u)
            else:
                webbrowser.open(u)
            return True
        except Exception as e:
            print('[大轩巴] 打开外链失败：', e)
            return False

    def _open_devtools(w):
        try:
            core = w.native.browser.webview.CoreWebView2
            core.OpenDevToolsWindow()
        except Exception as e:
            print('[大轩巴] 打开 DevTools 失败：', e)

    # 外链一律走系统浏览器：window.open / target=_blank 不许劫持主窗口，
    # 否则主窗口会被导航成 Steam 商店页，看起来就是「卡死点不动、关不掉」。
    try:
        if hasattr(mod, 'register_external_link_opener'):
            mod.register_external_link_opener(_open_external_url)
    except Exception as e:
        print('[大轩巴] 注册外链处理器失败：', e)

    # F12 / Ctrl+Shift+I 打开 DevTools，并放开内核的 accelerator keys
    try:
        if hasattr(mod, 'register_devtools_opener'):
            mod.register_devtools_opener(
                lambda: threading.Thread(target=_open_devtools, args=(win,),
                                         daemon=True).start())
    except Exception as e:
        print('[大轩巴] 注册 DevTools 处理器失败：', e)

    def _after_load():
        _install_external_link_guard(win, [url.lower() + '/', url.lower()])
        _enable_f12_devtools(win)

    loaded_flag = {'ok': False}

    def _on_loaded():
        loaded_flag['ok'] = True
        threading.Thread(target=_after_load, daemon=True).start()

    try:
        win.events.loaded += _on_loaded
    except Exception as e:
        print('[大轩巴] 绑定窗口加载事件失败：', e)

    def _warn_if_stuck():
        """窗口一直没渲染出来时给个可见提示（windowed 打包没控制台，光靠日志用户看不到）。"""
        for _ in range(90):
            if loaded_flag['ok']:
                return
            time.sleep(1)
        try:
            _message_box(
                '界面 90 秒还没加载出来。\n\n'
                '常见原因：\n'
                '1) 杀毒/防火墙拦了本程序的本地服务；\n'
                '2) 系统代理开着且有代理规则拦了 127.0.0.1（关闭系统代理再试）；\n'
                '3) 安装目录不可写。\n\n'
                '请到 设置 → 关于 点「打开日志」看 dxb_run.log 末几行。',
                '大轩巴入库器mini · 界面未响应', 0x10)
        except Exception:
            pass

    threading.Thread(target=_warn_if_stuck, daemon=True).start()

    print('[大轩巴] 使用内嵌 WebView2 窗口打开界面。')
    webview.start(
        gui='edgechromium',
        private_mode=False,
        storage_path=str(profile_dir),
    )
    print('[大轩巴] 窗口已关闭，进程退出。')
    shutdown_server(url)


if __name__ == '__main__':
    main()
