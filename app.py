
import asyncio
import os
import webbrowser
import sys
import threading
import time
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path
import json as standard_json
import winreg
import shutil
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from flask_socketio import SocketIO, emit

import tkinter as tk
from tkinter import ttk



if sys.platform == 'win32':
    import ctypes
    
    class ConsoleManager:
        def __init__(self):
            self.kernel32 = ctypes.WinDLL('kernel32')
            self.is_visible = self.kernel32.GetConsoleWindow() != 0
        def toggle_console(self):
            if self.is_visible: self._hide_console()
            else: self._show_console()
            return not self.is_visible
        def _show_console(self):
            if not self.is_visible:
                if self.kernel32.AllocConsole():
                    sys.stdout = open('CONOUT$', 'w')
                    sys.stderr = open('CONOUT$', 'w')
                    print("--- 控制台已附加 ---")
                    print("大轩巴入库器mini 的日志将在这里显示。")
                    self.is_visible = True
                else: print("错误: 无法分配新的控制台。")
        def _hide_console(self):
            if self.is_visible:
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
                if self.kernel32.FreeConsole(): self.is_visible = False
                else: print("错误: 无法释放控制台。")
    console_manager = ConsoleManager()
else:
    class ConsoleManager:
        def toggle_console(self): return False
        def _show_console(self): pass
    console_manager = ConsoleManager()

project_root = Path.cwd()
sys.path.insert(0, str(project_root))

try:
    from backend import (DxbBackend, DEFAULT_CONFIG, GREENLUMA_OFFICIAL_URL,
                         KernelHub, KERNEL_SPECS, net_selftest, kernel_update_state)
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dxb-injector-secret-key-v2'
app.config['USER_DATA_FOLDER'] = project_root / 'userdata'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

def get_port_from_gui():
    result = {'port': 5000}
    root = tk.Tk()
    root.title("设置端口")
    window_width, window_height = 300, 150
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    root.attributes('-topmost', True)
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill="both", expand=True)
    ttk.Label(main_frame, text="请输入端口号 (默认: 5000):").pack(pady=5)
    port_var = tk.StringVar(value="5000")
    entry = ttk.Entry(main_frame, textvariable=port_var, width=10)
    entry.pack(pady=5)
    entry.focus()
    def on_ok():
        try:
            port_val = int(port_var.get().strip())
            if 1024 <= port_val <= 65535: result['port'] = port_val
        except (ValueError, TypeError): pass
        root.destroy()
    ttk.Button(main_frame, text="启动", command=on_ok).pack(pady=10)
    root.bind('<Return>', lambda event: on_ok())
    root.mainloop()
    return result['port']


def should_show_console_on_startup():
    config_path = project_root / 'config.json'
    if not config_path.exists(): return False
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = standard_json.load(f)
        return config.get("show_console_on_startup", False)
    except Exception as e:
        print(f"启动时读取配置失败: {e}")
        return False

TASK_STATE = {"status": "idle", "progress": [], "result": None}

def patch_log_for_socketio(logger):
    if hasattr(logger, '_is_patched_by_web'): return
    def create_handler(original_func, log_type):
        def handler(msg, *args, **kwargs):
            try: full_msg = msg % args if args else msg
            except TypeError: full_msg = str(msg)
            if len(TASK_STATE["progress"]) > 200: TASK_STATE["progress"].pop(0)
            TASK_STATE["progress"].append({"type": log_type, "message": full_msg})
            socketio.emit('task_progress', {"type": log_type, "message": full_msg})
            return original_func(full_msg)
        return handler
    original_info, original_warning, original_error, original_debug = logger.info, logger.warning, logger.error, logger.debug
    logger.info, logger.warning, logger.error, logger.debug = create_handler(original_info, "info"), create_handler(original_warning, "warning"), create_handler(original_error, "error"), create_handler(original_debug, "debug")
    setattr(logger, '_is_patched_by_web', True)


def _quick_backend():
    """轻量后端：只读配置 + 日志，不做完整 initialize（给不需要异步初始化的接口用）。"""
    b = DxbBackend()
    b.log = logging.getLogger(' 大轩巴入库器mini')
    try:
        b.config = b._load_config_sync() or {}
    except Exception:
        b.config = {}
    return b


STEAM_LOGIN = {
    "available": False,
    "status": "idle",
    "message": "",
    "account": None,
}
_steam_login_launcher = None
_external_link_opener = None
_in_app_opener = None
_devtools_opener = None


def register_external_link_opener(fn):
    """由桌面壳注入：把外链交给系统浏览器打开。

    WebView2 里 window.open / target=_blank 会直接导航主窗口，
    主窗口被替换成 Steam 商店页后，路由和标签栏全丢，表现为「卡死、F12 不灵、关不掉」。
    """
    global _external_link_opener
    _external_link_opener = fn if callable(fn) else None


def register_in_app_opener(fn):
    """由桌面壳注入：在**应用内**新开一个内嵌窗口显示外部网页。

    有这个（优先用），点外链就是「在应用里开浏览器」；
    没有就退回系统浏览器。绝不允许外链把主窗口顶掉。
    """
    global _in_app_opener
    _in_app_opener = fn if callable(fn) else None


def register_devtools_opener(fn):
    """由桌面壳注入：F12 / Ctrl+Shift+I 打开 WebView2 DevTools。"""
    global _devtools_opener
    _devtools_opener = fn if callable(fn) else None


def register_steam_login_launcher(fn):
    """由桌面壳在启动时注入。fn() 负责打开内置浏览器登录窗口（非阻塞）。"""
    global _steam_login_launcher
    _steam_login_launcher = fn if callable(fn) else None
    STEAM_LOGIN["available"] = _steam_login_launcher is not None


def steam_login_failed(message: str):
    STEAM_LOGIN["status"] = "error"
    STEAM_LOGIN["message"] = message or "登录失败。"


def steam_login_succeeded(cookie: str):
    """桌面壳抓到 steamLoginSecure 后回调：落盘 Cookie 并读取账号信息。"""
    cookie = (cookie or '').strip()
    if not cookie or 'steamLoginSecure' not in cookie:
        steam_login_failed('未能从内置浏览器读到登录态，请重新登录。')
        return {"success": False, "message": STEAM_LOGIN["message"]}
    account = _quick_backend().free_account_info(cookie)
    if not account.get('success'):
        steam_login_failed(account.get('message') or 'Cookie 无效或已过期。')
        return {"success": False, "message": STEAM_LOGIN["message"]}
    try:
        b = _quick_backend()
        cfg = b._load_config_sync() or {}
        cfg['steam_cookie'] = cookie
        b._save_config_sync(cfg)
    except Exception:
        pass
    STEAM_LOGIN["account"] = account
    STEAM_LOGIN["status"] = "success"
    STEAM_LOGIN["message"] = "已登录：" + (account.get('name') or 'Steam 账号')
    return {"success": True, "account": account}


_elevated_restart = None


def register_elevated_restart(fn):
    """由桌面壳注入：fn() 负责以管理员身份重新拉起本程序（非阻塞，随后自杀）。"""
    global _elevated_restart
    _elevated_restart = fn if callable(fn) else None


_normal_restart = None


def register_app_restart(fn):
    """由桌面壳注入：fn() 负责正常重新拉起本程序（非阻塞，随后自杀）。"""
    global _normal_restart
    _normal_restart = fn if callable(fn) else None


_window_closer = None


def register_window_closer(fn):
    """由桌面壳注入：fn() 立刻关掉主窗口。

    提权/普通重启时，新实例会开一个新窗口；旧实例必须马上把自己的窗口收掉，
    否则用户会看到「一个主窗口 + 后面还压着一个旧窗口」。
    """
    global _window_closer
    _window_closer = fn if callable(fn) else None


def _is_steam_logged_in() -> bool:
    """入库前的登录态判定。

    以前只看「内置浏览器 cookie」，用户在 **Steam 客户端**里登录的一律判成未登录，
    于是入库被拦住、还一直弹登录窗口。现在先认本机 Steam 客户端的登录态
    （读 config\\loginusers.vdf），那才是真正决定「往哪个账号的库里写」的东西。
    """
    if STEAM_LOGIN.get("status") == "success" and STEAM_LOGIN.get("account"):
        return True
    try:
        b = _quick_backend()
        b.config = b._load_config_sync() or {}
        if b.steam_account().get("logged_in"):
            return True
    except Exception:
        pass
    try:
        cfg = _quick_backend()._load_config_sync() or {}
        return bool(str(cfg.get('steam_cookie') or '').strip())
    except Exception:
        return False


def _steam_login_required():
    """统一的“请先登录”响应体。"""
    return jsonify({"success": False, "need_login": True, "injected": 0, "skipped": 0,
                    "available": STEAM_LOGIN.get("available", False),
                    "message": "请先登录 Steam 账号，登录后才能入库。"})

@app.route('/')
def index(): return render_template('index.html')

@app.route('/settings')
def settings_page(): return render_template('settings.html')

@app.route('/about')
def about_page(): return render_template('about.html')

@app.route('/manager')
def manager_page():
    return render_template('manager.html')

@app.route('/recommend')
def recommend_page():
    return render_template('recommend.html')

@app.route('/craft')
def craft_page():
    return render_template('craft.html')

@app.route('/free')
def free_page():
    return render_template('free.html')

@app.route('/tools')
def tools_page():
    """工具箱：Steam 错误诊断修复 + 下载管理。"""
    return render_template('tools.html')


@app.route('/downloader')
def downloader_page():
    """下载管理：三个内核的真实版本检测 + 自动下载 + 自动装到 Steam 主目录。"""
    return render_template('downloader.html')


@app.route('/inject')
def inject_page():
    """离线注入：启动 Steam（普通 / GreenLuma 隐身 / 注入版）+ 真实模块枚举检测。"""
    return render_template('inject.html')


def background_install_unlocker():
    """后台线程：自动下载安装解锁工具，不阻塞页面初始化。"""
    async def _run():
        async with DxbBackend() as backend:
            patch_log_for_socketio(backend.log)
            backend.config = await backend.load_config()
            if not backend.config:
                return
            backend.steam_path = backend.get_steam_path()
            if not backend.steam_path or not backend.steam_path.exists():
                backend.log.error("后台安装解锁工具失败：无法确定 Steam 路径。")
                return
            installed = await backend.ensure_unlocker_installed()
            if installed:
                backend.log.info(f"后台自动安装解锁工具完成: {installed}")
            else:
                backend.log.warning("后台自动安装解锁工具失败，请前往设置页手动安装。")
    try:
        asyncio.run(_run())
    except Exception as e:
        print(f"后台安装解锁工具异常: {e}")


@app.route('/api/initialize', methods=['POST'])
def initialize_app():
    try:
        async def _init():
            async with DxbBackend() as backend:
                patch_log_for_socketio(backend.log)
                unlocker_type = await backend.initialize()
                if backend.config is None:
                    return {"success": False, "message": "加载配置失败，请检查日志。"}
                pending = getattr(backend, '_pending_unlocker_install', False)
                return {
                    "success": True,
                    "unlocker_type": unlocker_type,
                    "detected": dict(getattr(backend, 'detected_kernels',
                                             {'steamtools': False, 'greenluma': False,
                                              'opensteamtool': False})),
                    "pending_unlocker_install": pending,
                    "steam_path": str(backend.steam_path) if backend.steam_path else "Not Found",
                    "has_token": bool(backend.config.get("Github_Personal_Token", "").strip())
                }

        result = asyncio.run(_init())
        if result.get("pending_unlocker_install"):
            threading.Thread(target=background_install_unlocker, daemon=True).start()
        return jsonify(result)

    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"后端初始化失败: {str(e)}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message})

@app.route('/api/check_updates', methods=['POST'])
def check_updates():
    try:
        async def _check():
            async with DxbBackend() as backend:
                patch_log_for_socketio(backend.log)
                await backend.initialize()
                has_update, update_info = await backend.check_for_updates()
                return {
                    "success": True,
                    "has_update": has_update,
                    "update_info": update_info
                }
        
        result = asyncio.run(_check())
        return jsonify(result)
        
    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"检查更新失败: {str(e)}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message})

@app.route('/api/steam_status', methods=['GET'])
def steam_status():
    try:
        async def _st():
            async with DxbBackend() as backend:
                await backend.initialize()
                return backend.get_steam_status()
        return jsonify({"success": True, **asyncio.run(_st())})
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/dependency/status', methods=['GET'])
def dependency_status():
    try:
        async def _st():
            async with DxbBackend() as backend:
                await backend.initialize()
                return (backend.get_opensteamtool_status(), backend.get_steamtools_status(),
                        backend.get_greenluma_status(), backend.get_steam_status())
        otool, stools, gluma, steam = asyncio.run(_st())
        return jsonify({"success": True, "opensteamtool": otool, "steamtools": stools,
                        "greenluma": gluma, "steam": steam})
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


def _background_install_dependency(kind: str, force: bool):
    """后台线程：从 GitHub 下载/更新依赖内核，不阻塞页面。"""
    async def _run():
        async with DxbBackend() as backend:
            patch_log_for_socketio(backend.log)
            await backend.initialize()
            if kind == "opensteamtool":
                res = await backend.ensure_opensteamtool_installed(force=force)
            elif kind == "steamtools":
                res = await backend.ensure_steamtools_installed(force=force)
            elif kind == "greenluma":
                res = await backend.ensure_greenluma_installed(force=force)
            else:
                backend.log.error(f"未知依赖类型: {kind}")
                return
            if res:
                backend.log.info(f"依赖 {kind} 安装/更新完成。")
            else:
                backend.log.warning(f"依赖 {kind} 安装/更新失败，请查看日志或手动安装。")
    try:
        asyncio.run(_run())
    except Exception as e:
        print(f"后台安装依赖 {kind} 异常: {e}")


@app.route('/api/dependency/install', methods=['POST'])
def dependency_install():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "")
    force = bool(data.get("force", False))
    if kind not in ("opensteamtool", "steamtools", "greenluma"):
        return jsonify({"success": False, "message": "未知的依赖类型。"}), 400

    if kind in ("greenluma", "steamtools"):
        threading.Thread(target=_background_kernel_install, args=(kind, force), daemon=True).start()
        if kind == "greenluma":
            msg = "已在后台开始下载 GreenLuma 隐身版（官方 stealth DLL，无窗口、无管理员）。"
        else:
            admin = False
            try:
                admin = bool(DxbBackend.is_admin())
            except Exception:
                admin = False
            msg = ("已在后台下载 SteamTools 官方安装包，管理员模式将 /S 静默安装（无窗口）。"
                   if admin else
                   "已在后台下载 SteamTools 官方安装包；当前不是管理员，稍后会弹出官方安装向导，"
                   "请按提示点完（想要无窗口静默装就用管理员身份重启本程序）。")
        return jsonify({"success": True, "kind": kind, "message": msg})

    threading.Thread(target=_background_install_dependency, args=(kind, force), daemon=True).start()
    label = {"opensteamtool": "OpenSteamTool 内核", "steamtools": "SteamTools",
             "greenluma": "GreenLuma"}.get(kind, kind)
    return jsonify({"success": True, "message": f"已在后台开始下载/更新 {label}。"})


KERNEL_PROGRESS: Dict[str, Dict[str, Any]] = {}


def _kernel_prog(kind: str):
    def prog(pct, msg):
        KERNEL_PROGRESS[kind] = {"percent": int(pct or 0), "message": str(msg or ''),
                                 "running": True, "ts": time.time()}
        try:
            socketio.emit('kernel_progress', {"kind": kind, "percent": int(pct or 0), "message": msg})
        except Exception:
            pass
    return prog


def _kernel_finish(kind: str, res: Dict[str, Any], backend):
    try:
        state = KernelHub(backend).local_status(kind)
    except Exception:
        state = {}
    KERNEL_PROGRESS[kind] = {
        "percent": 100 if res.get("success") else 0,
        "message": str(res.get("message") or ''),
        "running": False, "ts": time.time(),
    }
    try:
        socketio.emit('kernel_done', {"kind": kind, "result": res, "state": state})
    except Exception:
        pass


def _background_kernel_install(kind: str, force: bool, mode: str = ""):
    async def _run():
        async with DxbBackend() as backend:
            patch_log_for_socketio(backend.log)
            await backend.initialize()
            hub = KernelHub(backend)
            try:
                res = await hub.install(kind, on_progress=_kernel_prog(kind), force=force, mode=mode)
            except Exception as e:
                res = {"success": False, "message": f"安装异常：{e}"}
            _kernel_finish(kind, res, backend)
    try:
        asyncio.run(_run())
    except Exception as e:
        KERNEL_PROGRESS[kind] = {"percent": 0, "message": str(e), "running": False, "ts": time.time()}


@app.route('/api/kernel/progress', methods=['GET'])
def kernel_progress():
    """前端轮询安装进度（不依赖 socket.io）。"""
    return jsonify({"success": True, "progress": KERNEL_PROGRESS})


@app.route('/api/kernel/status', methods=['GET'])
def kernel_status():
    """三个内核：本地状态 + 远端最新版 + 是否需要更新（真实检测，不弹浏览器）。"""
    try:
        async def _inner():
            async with DxbBackend() as backend:
                await backend.initialize()
                hub = KernelHub(backend)
                local = hub.all_local()
                want_remote = request.args.get('remote', '1') != '0'
                remote = {}
                if want_remote:
                    got = await asyncio.gather(
                        *[hub.remote_latest(k) for k in KERNEL_SPECS],
                        return_exceptions=True)
                    for k, r in zip(KERNEL_SPECS.keys(), got):
                        remote[k] = {"ok": False, "note": str(r)[:120]} if isinstance(r, Exception) else r
                for k, st in local.items():
                    if not want_remote:
                        st['remote_version'] = ''
                        st['remote_ok'] = False
                        st['remote_note'] = '未查询（remote=0）'
                        st['update_state'] = 'unknown'
                        continue
                    r = remote.get(k) or {}
                    st['remote_version'] = r.get('version') or ''
                    st['remote_ok'] = bool(r.get('ok'))
                    st['remote_note'] = r.get('note') or ''
                    if k == 'greenluma':
                        st['remote_stealth'] = r.get('stealth_version') or ''
                        st['remote_inject'] = r.get('inject_version') or ''
                        cur = (st.get('mode') or 'stealth')
                        st['remote_version'] = (st['remote_stealth'] if cur == 'stealth'
                                                else (st['remote_inject'] or st['remote_version']))
                    st['update_state'] = kernel_update_state(
                        st.get('version') or '', st.get('remote_version') or '',
                        bool(st.get('installed')))
                sp = backend.get_steam_path()
                try:
                    is_admin = bool(DxbBackend.is_admin())
                except Exception:
                    is_admin = False
                return {"success": True, "kernels": local,
                        "order": list(KERNEL_SPECS.keys()),
                        "steam_path": str(sp) if sp else '',
                        "admin": is_admin,
                        "probed": want_remote,
                        "account": backend.steam_account(),
                        "conflict": hub.conflict_check(),
                        "injection": hub.injection_status()}
        return jsonify(asyncio.run(_inner()))
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/updates/check', methods=['GET'])
def updates_check():
    """真实检查更新：应用自身 + 每个内核的远端最新版，全部并发，只查不下载。"""
    try:
        async def _inner():
            async with DxbBackend() as backend:
                patch_log_for_socketio(backend.log)
                await backend.initialize()
                return await backend.check_all_updates()
        r = asyncio.run(_inner())
        r['success'] = True
        return jsonify(r)
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/kernel/repair/scan', methods=['GET'])
def kernel_repair_scan():
    try:
        b = DxbBackend()
        b.config = b._load_config_sync() or {}
        return jsonify({'success': True, **(KernelHub(b).repair_scan())})
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/kernel/repair', methods=['POST'])
def kernel_repair():
    data = request.get_json(silent=True) or {}
    try:
        b = DxbBackend()
        b.config = b._load_config_sync() or {}
        r = KernelHub(b).repair(
            close_steam=bool(data.get('close_steam', True)),
            clear_cache=bool(data.get('clear_cache', True)))
        return jsonify(r)
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/kernel/repair/restore', methods=['POST'])
def kernel_repair_restore():
    data = request.get_json(silent=True) or {}
    try:
        b = DxbBackend()
        b.config = b._load_config_sync() or {}
        return jsonify(KernelHub(b).restore_repair(str(data.get('batch') or '')))
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/steam/account', methods=['GET'])
def steam_account_api():
    """本机 Steam 客户端的登录账号（读 loginusers.vdf，不需要联网也不需要 cookie）"""
    try:
        b = DxbBackend()
        b.config = b._load_config_sync() or {}
        return jsonify({"success": True, "account": b.steam_account()})
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/steam/avatar')
def steam_avatar():
    """本机 Steam 缓存的头像（config\\avatarcache\\<steamid64>.png），只回本机那个文件"""
    try:
        b = DxbBackend()
        b.config = b._load_config_sync() or {}
        acc = b.steam_account()
        p = acc.get('avatar_path') or ''
        if not p or not os.path.exists(p):
            return Response(b'', status=404, mimetype='image/png')
        with open(p, 'rb') as f:
            data = f.read()
        return Response(data, mimetype='image/png',
                        headers={'Cache-Control': 'no-store'})
    except Exception as e:
        return Response(b'', status=404, mimetype='image/png')


@app.route('/api/kernel/install', methods=['POST'])
def kernel_install():
    data = request.get_json(silent=True) or {}
    kind = str(data.get('kind') or '').strip()
    if kind not in KERNEL_SPECS:
        return jsonify({"success": False, "message": "未知内核。"}), 400
    force = bool(data.get('force', True))
    mode = str(data.get('mode') or '').strip().lower()
    threading.Thread(target=_background_kernel_install, args=(kind, force, mode), daemon=True).start()
    if kind == "greenluma":
        label = "GreenLuma 隐身版" if (mode or "stealth") != "inject" else "GreenLuma 注入版"
    else:
        label = KERNEL_SPECS[kind]['name']
    if KERNEL_SPECS[kind].get('installer'):
        extra = "（安装包型：下完会自动运行官方安装包）"
    else:
        extra = ""
    return jsonify({"success": True, "kind": kind, "mode": mode,
                    "message": f"已开始下载/安装 {label}{extra}。"})


@app.route('/api/kernel/uninstall', methods=['POST'])
def kernel_uninstall():
    """卸载内核。目前只有 GreenLuma 隐身版需要（要把 Steam 目录里的 user32.dll 拿掉）。"""
    data = request.get_json(silent=True) or {}
    kind = str(data.get('kind') or '').strip()
    mode = str(data.get('mode') or 'stealth').strip().lower()
    if kind != 'greenluma' or mode != 'stealth':
        return jsonify({"success": False, "message": "只有 GreenLuma 隐身版支持在这里移除。"}), 400
    try:
        res = KernelHub(_quick_backend()).uninstall_greenluma_stealth()
        return jsonify(res)
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/kernel/install_local', methods=['POST'])
def kernel_install_local():
    """本地文件通道：上传 .exe 安装包就直接跑它，上传 zip/7z 就解压释放。"""
    kind = str(request.form.get('kind') or '').strip()
    f = request.files.get('file')
    if kind not in KERNEL_SPECS:
        return jsonify({"success": False, "message": "未知内核。"}), 400
    if not f:
        return jsonify({"success": False, "message": "没收到文件。"}), 400
    data = f.read()
    if not data:
        return jsonify({"success": False, "message": "文件为空。"}), 400
    fname = f.filename or 'pkg.zip'

    def _run():
        async def _inner():
            async with DxbBackend() as backend:
                await backend.initialize()
                hub = KernelHub(backend)
                try:
                    res = await hub.install_from_local(kind, fname, data, on_progress=_kernel_prog(kind))
                except Exception as e:
                    res = {"success": False, "message": f"安装异常：{e}"}
                _kernel_finish(kind, res, backend)
        asyncio.run(_inner())
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "kind": kind,
                    "message": f"已开始从本地包安装 {KERNEL_SPECS[kind]['name']}。"})


@app.route('/api/kernel/launch', methods=['POST'])
def kernel_launch():
    """启动 Steam；GreenLuma 模式走 DLLInjector.exe 无窗口注入。"""
    data = request.get_json(silent=True) or {}
    mode = str(data.get('mode') or 'auto').strip()

    def _run():
        async def _inner():
            async with DxbBackend() as backend:
                await backend.initialize()
                return await KernelHub(backend).launch_steam(mode)
        return asyncio.run(_inner())
    try:
        return jsonify(_run())
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/kernel/injection', methods=['GET'])
def kernel_injection():
    """真实检测 steam.exe 当前是否加载了 GreenLuma / LumaCore 注入模块。"""
    try:
        return jsonify({"success": True, **KernelHub(_quick_backend()).injection_status()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/net/selftest', methods=['GET'])
def net_selftest_route():
    """直连 / 代理 两条路的真实连通性测试（回答“为什么非要加速”）。"""
    mode = (request.args.get('mode') or 'direct').strip()
    try:
        return jsonify({"success": True, **asyncio.run(net_selftest(mode=mode))})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/net/proxy', methods=['GET', 'POST'])
def net_proxy_route():
    """查看 / 设置后端代理（直连不通时用，支持 http:// 与 socks5://）。"""
    b = _quick_backend()
    cfg = b.config or {}
    if request.method == 'GET':
        return jsonify({"success": True, "proxy": cfg.get('network_proxy') or ''})
    data = request.get_json(silent=True) or {}
    proxy = str(data.get('proxy') or '').strip()
    cfg['network_proxy'] = proxy
    try:
        b._save_config_sync(cfg)
    except Exception as e:
        return jsonify({"success": False, "message": f"保存失败：{e}"})
    return jsonify({"success": True, "proxy": proxy,
                    "message": "已保存。重启应用后后端请求改走该代理。"})


_OPEN_URL_WHITELIST = (
    "cs.rin.ru",
    "github.com", "raw.githubusercontent.com", "api.github.com",
    "go.microsoft.com",
    "learn.microsoft.com",
    "store.steampowered.com", "steamcommunity.com",
)


@app.route('/api/app/open_url', methods=['POST'])
def app_open_url():
    """用系统默认浏览器打开白名单内的外链（内置窗口不外跳，只有明确点按钮才走系统浏览器）。"""
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return jsonify({"success": False, "message": "只允许打开 http/https 链接。"}), 400
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if not any(host == h or host.endswith("." + h) for h in _OPEN_URL_WHITELIST):
        return jsonify({"success": False, "message": f"该域名不在白名单内，已拒绝打开：{host}"}), 403
    try:
        webbrowser.open(url)
        return jsonify({"success": True, "message": f"已用系统浏览器打开：{host}", "url": url})
    except Exception as e:
        return jsonify({"success": False, "message": f"打开失败：{e}"})


@app.route('/api/auto_update', methods=['POST'])
def auto_update():
    try:
        async def _up():
            async with DxbBackend() as backend:
                patch_log_for_socketio(backend.log)
                await backend.initialize()
                has_update, info = await backend.check_for_updates()
                if not has_update:
                    return {"success": True, "has_update": False}
                urls = info.get("download_urls", [])
                if not urls:
                    return {"success": False, "message": "未找到可下载的安装包。"}
                asset = next((u for u in urls if u["name"].lower().endswith(".exe")), urls[0])
                data = await backend._download_bytes(asset["url"])
                if not data:
                    return {"success": False, "message": "下载安装包失败。"}
                import tempfile
                tmp = Path(tempfile.gettempdir()) / asset["name"]
                tmp.write_bytes(data)
                backend.log.info(f"已下载更新安装包到 {tmp}，即将打开安装...")
                if sys.platform == 'win32' and os.startfile:
                    os.startfile(str(tmp))
                return {"success": True, "has_update": True, "path": str(tmp)}
        result = asyncio.run(_up())
        if result.get("has_update") and result.get("success"):
            def kill_process():
                time.sleep(1.0)
                os._exit(0)
            threading.Thread(target=kill_process, daemon=True).start()
        return jsonify(result)
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/craft_lua', methods=['POST'])
def craft_lua():
    data = request.get_json(silent=True) or {}
    appid = str(data.get("appid", "")).strip()
    include_depotkeys = bool(data.get("include_depotkeys", True))
    include_manifests = bool(data.get("include_manifests", True))
    if not appid:
        return jsonify({"success": False, "message": "请输入 AppID。"}), 400
    try:
        async def _craft():
            async with DxbBackend() as backend:
                patch_log_for_socketio(backend.log)
                await backend.initialize()
                lua, filename, info = await backend.craft_opensteamtool_lua(
                    appid, include_depotkeys=include_depotkeys, include_manifests=include_manifests)
                return lua, filename, info
        lua, filename, info = asyncio.run(_craft())
        return jsonify({"success": True, "lua": lua, "filename": filename, "info": info})
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/craft_import', methods=['POST'])
def craft_import():
    data = request.get_json(silent=True) or {}
    lua = data.get("lua", "")
    filename = str(data.get("filename", "")).strip()
    if not lua:
        return jsonify({"success": False, "message": "无 lua 内容，请先手搓。"}), 400
    if not filename or not filename.endswith(".lua") or "/" in filename or "\\" in filename:
        return jsonify({"success": False, "message": "文件名无效。"}), 400
    try:
        async def _imp():
            async with DxbBackend() as backend:
                patch_log_for_socketio(backend.log)
                await backend.initialize()
                lua_dir = backend.steam_path / 'config' / 'lua'
                lua_dir.mkdir(parents=True, exist_ok=True)
                target = lua_dir / filename
                target.write_text(lua, encoding='utf-8')
                backend.log.info(f"手搓 lua 已入库: {target}")
                return str(target)
        target = asyncio.run(_imp())
        return jsonify({"success": True, "message": f"已写入 {target}，重启 Steam 后生效。", "path": target})
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": f"入库失败: {e}"})


@app.route('/api/download_lua', methods=['POST'])
def download_lua():
    data = request.get_json(silent=True) or {}
    lua = data.get("lua", "")
    filename = data.get("filename", "crafted.lua")
    if not lua:
        return jsonify({"success": False, "message": "无 lua 内容。"}), 400
    try:
        import tempfile
        tmp = Path(tempfile.gettempdir()) / filename
        tmp.write_text(lua, encoding='utf-8')
        return send_from_directory(tmp.parent, tmp.name, as_attachment=True,
                                   mimetype='text/plain; charset=utf-8')
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/sources', methods=['GET'])
def get_sources():
    try:
        async def _get_sources():
            async with DxbBackend() as backend:
                await backend.initialize()
                
                builtin_sources = {
                    "自动搜索GitHub": "search",
                    "SWA V2": "printedwaste", 
                    "Cysaw": "cysaw",
                    "Furcate": "furcate",
                    "Walftech": "walftech",
                    "steamdatabase": "steamdatabase",
                    "SteamAutoCracks/ManifestHub(2) （仅密钥）": "steamautocracks_v2",
                    "Sudama库(仅密钥）": "sudama",
                    "清单不求人库（仅清单）": "buqiuren", 
                    "GitHub (Auiowu)": "Auiowu/ManifestAutoUpdate",
                    "GitHub (SAC)": "SteamAutoCracks/ManifestHub",
                    "GitHub (ikun0014/ManifestHub)": "ikun0014/ManifestHub",
                    "GitHub (Masaiki/ManifestAutoUpdate)": "Masaiki/ManifestAutoUpdate",
                    "GitHub (wxy1343/ManifestAutoUpdate)": "wxy1343/ManifestAutoUpdate",
                    "GitHub (Cyberbolt/ManifestAutoUpdate)": "Cyberbolt/ManifestAutoUpdate",
                    "GitHub (Fairyvmos/bruh-hub)": "Fairyvmos/bruh-hub",
                    "GitHub (Cracko298/ManifestHub)": "Cracko298/ManifestHub",
                }
                
                custom_github_repos = backend.get_custom_github_repos()
                custom_zip_repos = backend.get_custom_zip_repos()
                
                for repo in custom_github_repos:
                    builtin_sources[f"{repo['name']} (自定义GitHub)"] = repo['repo']
                
                for repo in custom_zip_repos:
                    builtin_sources[f"{repo['name']} (自定义ZIP)"] = f"custom_zip_{repo['name']}"

                if request.args.get('fast') == '1':
                    availability = {v: True for v in backend.SOURCE_PROBE}
                    recommended = next(
                        (v for v, spec in backend.SOURCE_PROBE.items()
                         if spec is not None), 'search')
                else:
                    availability, recommended = await backend.test_sources()
                filtered_sources = {
                    name: value for name, value in builtin_sources.items()
                    if availability.get(value, True)
                }
                if recommended is None or recommended not in filtered_sources.values():
                    recommended = next(
                        (v for v in filtered_sources.values()
                         if availability.get(v, False)),
                        None,
                    )

                return {
                    "success": True,
                    "sources": filtered_sources,
                    "recommended": recommended,
                    "availability": availability,
                    "probed": request.args.get('fast') != '1',
                    "custom_github_count": len(custom_github_repos),
                    "custom_zip_count": len(custom_zip_repos)
                }
        
        result = asyncio.run(_get_sources())
        return jsonify(result)
        
    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"获取清单源失败: {str(e)}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message})

async def _run_search_game_task(game_name):
    async with DxbBackend() as backend:
        patch_log_for_socketio(backend.log)
        await backend.initialize()
        results = await backend.find_appid_by_name(game_name)
        return results

@app.route('/api/search_game', methods=['POST'])
def search_game():
    data = request.get_json()
    game_name = data.get('game_name', '').strip()
    if not game_name:
        return jsonify({"success": False, "message": "请输入游戏名称。"}), 400
    try:
        results = asyncio.run(_run_search_game_task(game_name))
        return jsonify({"success": True, "games": results})
    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"搜索时发生错误: {e}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message}), 500

async def _run_unlock_task(app_id, tool_type, use_st_auto_update, add_all_dlc, patch_depot_key):
    async with DxbBackend() as backend:
        patch_log_for_socketio(backend.log)
        TASK_STATE["status"] = "running"
        TASK_STATE["progress"] = []
        TASK_STATE["result"] = None
        unlocker_type = await backend.initialize()
        if not unlocker_type:
            raise Exception("解锁工具类型未能确定，请检查配置或Steam路径。")

        await backend.checkcn()
        needs_github_api = (tool_type == "search") or ("/" in tool_type and tool_type != "steamautocracks_v2")
        if needs_github_api and not await backend.check_github_api_rate_limit():
            raise Exception("GitHub API 请求次数已用尽，无法继续。")
                
        app_id_extracted = backend.extract_app_id(app_id)
        if not app_id_extracted:
            raise Exception(f"无法从 '{app_id}' 中提取有效AppID。请输入有效的AppID或链接。")
            
        if tool_type == "search":
            backend.log.info(f"正在所有 GitHub 仓库中搜索 AppID: {app_id_extracted}...")
            results = await backend.search_all_repos_for_appid(app_id_extracted)
            if not results:
                raise Exception(f"在所有 GitHub 仓库中都未找到 AppID {app_id_extracted} 的清单。")
            TASK_STATE["result"] = {
                "success": True, "message": "搜索完成，请选择一个清单源。", "action_required": "select_source",
                "sources": results, "context": {"use_st_auto_update": use_st_auto_update, "add_all_dlc": add_all_dlc, "patch_depot_key": patch_depot_key}
            }
            backend.log.info(f"找到 {len(results)} 个源，请在界面上选择。")
            return
            
        backend.log.info(f"--- 正在使用源 '{tool_type}' 处理 AppID: {app_id_extracted} ---")
        
        zip_sources = ["printedwaste", "cysaw", "furcate", "walftech", "steamdatabase", "steamautocracks_v2", "sudama"]
        
        if tool_type.startswith("custom_zip_"):
            success = await backend.process_zip_source(app_id_extracted, tool_type, unlocker_type, use_st_auto_update, add_all_dlc, patch_depot_key)
        elif tool_type in zip_sources:
            success = await backend.process_zip_source(app_id_extracted, tool_type, unlocker_type, use_st_auto_update, add_all_dlc, patch_depot_key)
        else:
            success = await backend.process_github_manifest(app_id_extracted, tool_type, unlocker_type, use_st_auto_update, add_all_dlc, patch_depot_key)
        
        if success:
            TASK_STATE["result"] = {"success": True, "message": f"成功配置 AppID {app_id_extracted}。重启 Steam 后生效。"}
        else:
            raise Exception(f"处理 AppID {app_id_extracted} 失败，请检查日志。")

async def _run_workshop_task(workshop_input, download_resources, copy_to_depot):
    async with DxbBackend() as backend:
        patch_log_for_socketio(backend.log)
        TASK_STATE["status"] = "running"
        TASK_STATE["progress"] = []
        TASK_STATE["result"] = None

        unlocker_type = await backend.initialize()
        if not unlocker_type:
            raise Exception("后端初始化失败，请检查配置或Steam路径。")

        backend.log.info(f"--- 开始下载创意工坊资源: {workshop_input} ---")

        success = await backend.process_workshop_item(workshop_input, download_resources=download_resources, copy_to_depot=copy_to_depot)

        if success:
            TASK_STATE["result"] = {"success": True, "message": f"成功处理创意工坊资源。重启 Steam 后生效。"}
        else:
            raise Exception(f"处理创意工坊资源失败，请检查日志。")

@app.route('/api/start_task', methods=['POST'])
def start_task():
    if TASK_STATE["status"] == "running":
        return jsonify({"success": False, "message": "一个任务正在运行中。"})
    data = request.get_json()
    app_id_input = data.get('app_id', '').strip()
    tool_type = data.get('tool_type', 'search')
    use_st_auto_update = data.get('use_st_auto_update', False)
    add_all_dlc = data.get('add_all_dlc', False)
    patch_depot_key = data.get('patch_depot_key', False)
    
    if not app_id_input:
        return jsonify({"success": False, "message": "请输入 AppID 或链接。"})
    def task_wrapper():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_unlock_task(app_id_input, tool_type, use_st_auto_update, add_all_dlc, patch_depot_key))
            TASK_STATE["status"] = "completed"
        except Exception as e:
            TASK_STATE["status"] = "error"
            message = f"发生错误: {str(e)}"
            TASK_STATE["result"] = {"success": False, "message": message}
            dummy_backend = DxbBackend()
            patch_log_for_socketio(dummy_backend.log)
            dummy_backend.log.error(dummy_backend.stack_error(e))
        finally:
            if TASK_STATE["status"] == "running":
                TASK_STATE["status"] = "error"
                TASK_STATE["result"] = {"success": False, "message": "任务意外终止。"}
            loop.close()
    thread = threading.Thread(target=task_wrapper, daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "任务已开始。"})

@app.route('/api/workshop/check', methods=['POST'])
def workshop_check():
    """下载前检测创意工坊物品是否存在。"""
    data = request.get_json(silent=True) or {}
    workshop_input = (data.get('workshop_input') or '').strip()
    if not workshop_input:
        return jsonify({"success": False, "message": "请输入创意工坊物品链接或ID。"}), 400
    try:
        backend = DxbBackend()
        backend.log = logging.getLogger(' 大轩巴入库器mini')
        workshop_id = backend.extract_workshop_id(workshop_input)
        if not workshop_id:
            return jsonify({"success": False, "message": "无法从输入中提取有效的创意工坊ID。"}), 400
        info = asyncio.run(_run_workshop_check(workshop_id))
        return jsonify({"success": True, **info})
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": f"检测失败: {e}"}), 500

async def _run_workshop_check(workshop_id):
    async with DxbBackend() as backend:
        patch_log_for_socketio(backend.log)
        await backend.initialize()
        return await backend.check_workshop_exists(workshop_id)

@app.route('/api/workshop/start_task', methods=['POST'])
def start_workshop_task():
    if TASK_STATE["status"] == "running":
        return jsonify({"success": False, "message": "一个任务正在运行中。"})

    data = request.get_json()
    workshop_input = data.get('workshop_input', '').strip()
    download_resources = data.get('download_resources', True)
    copy_to_depot = data.get('copy_to_depot', False)

    if not workshop_input:
        return jsonify({"success": False, "message": "请输入创意工坊物品链接或ID。"})

    if not download_resources and not copy_to_depot:
        return jsonify({"success": False, "message": "请至少选择一个操作。"})

    def task_wrapper():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_workshop_task(workshop_input, download_resources, copy_to_depot))
            TASK_STATE["status"] = "completed"
        except Exception as e:
            TASK_STATE["status"] = "error"
            message = f"发生错误: {str(e)}"
            TASK_STATE["result"] = {"success": False, "message": message}
            dummy_backend = DxbBackend()
            patch_log_for_socketio(dummy_backend.log)
            dummy_backend.log.error(dummy_backend.stack_error(e))
        finally:
            if TASK_STATE["status"] == "running":
                TASK_STATE["status"] = "error"
                TASK_STATE["result"] = {"success": False, "message": "任务意外终止。"}
            loop.close()

    thread = threading.Thread(target=task_wrapper, daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "创意工坊资源下载已开始。"})

@app.route('/api/task_status')
def get_task_status():
    """任务状态 + 完整日志缓冲（切换页面回来后据此还原日志与进度，不重跑任务）。"""
    return jsonify({"status": TASK_STATE["status"],
                    "progress": TASK_STATE["progress"][-400:],
                    "result": TASK_STATE["result"]})

@app.route('/api/manager/files', methods=['GET'])
def get_managed_files():
    try:
        async def _get_files():
            async with DxbBackend() as backend:
                await backend.initialize()
                files_data = await backend.get_managed_files()
                return {"success": True, "data": files_data}
        
        result = asyncio.run(_get_files())
        return jsonify(result)
        
    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"获取文件列表失败: {str(e)}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message})

@app.route('/api/manager/installed', methods=['GET'])
def get_installed_games():
    """真实扫描 Steam 已装应用，DLC 归入各自游戏下。"""
    try:
        backend = DxbBackend()
        backend.log = logging.getLogger(' 大轩巴入库器mini')
        backend.config = backend._load_config_sync()
        tree = backend.installed_games_tree()
        return jsonify(tree)
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": f"扫描已装应用失败: {e}",
                        "games": [], "others": [], "total": 0, "dlc_total": 0})

@app.route('/api/steam/login/start', methods=['POST'])
def steam_login_start():
    """拉起内置（沉默）浏览器登录 Steam。"""
    if _steam_login_launcher is None:
        STEAM_LOGIN["available"] = False
        return jsonify({"success": False, "available": False,
                        "message": "当前环境没有内置浏览器，请手动粘贴 Cookie 登录。"})
    STEAM_LOGIN["status"] = "waiting"
    STEAM_LOGIN["message"] = "已打开登录窗口，请在窗口里完成 Steam 登录。"
    STEAM_LOGIN["account"] = None
    try:
        ok = _steam_login_launcher()
    except Exception as e:
        steam_login_failed(f"打开登录窗口失败: {e}")
        return jsonify({"success": False, "available": True, "message": STEAM_LOGIN["message"]})
    if ok is False:
        steam_login_failed("无法唤醒内置登录窗口，请改用“手动粘贴”Cookie 登录。")
        return jsonify({"success": False, "available": True, "message": STEAM_LOGIN["message"]})
    return jsonify({"success": True, "available": True, "message": STEAM_LOGIN["message"]})


@app.route('/api/steam/login/status')
def steam_login_status():
    return jsonify({"success": True, "available": STEAM_LOGIN["available"],
                    "status": STEAM_LOGIN["status"], "message": STEAM_LOGIN["message"],
                    "account": STEAM_LOGIN["account"]})


@app.route('/api/steam/img/<appid>')
def steam_image(appid):
    """封面图本地代理：多 CDN/多路径回退 + appdetails 兜底 + 落盘缓存，
    解决 webview 直连 CDN 空白。可选 ?u=<图片URL> 直接指定地址。"""
    url = request.args.get('u', '').strip()
    try:
        data = _quick_backend().fetch_steam_image(appid, url)
    except Exception:
        data = None
    if not data:
        return Response(status=404)
    resp = Response(data, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'public, max-age=604800'
    return resp


@app.route('/api/steam/proxy')
def steam_image_proxy():
    """通用 Steam 图片代理。

    推荐页 header_image 是带 hash 目录 + 时间戳的完整地址（如
    .../store_item_assets/steam/apps/3892270/<hash>/header.jpg），拼模板必然 404，
    只能按 URL 原样代理。仅放行 Steam CDN 白名单域名，避免变成任意 URL 转发器。
    """
    url = request.args.get('u', '').strip()
    appid = request.args.get('appid', '').strip()
    data = None
    if url:
        try:
            b = _quick_backend()
            if b._is_allowed_image_url(url):
                data = b.fetch_image_by_url(url, appid)
        except Exception:
            data = None
    if not data:
        return Response(status=404)
    resp = Response(data, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'public, max-age=604800'
    return resp


@app.route('/api/recommend')
def recommend_games():
    """游戏推荐页数据：特惠 / 热销 / 新品 / 即将推出（Steam 官方 featuredcategories）。"""
    try:
        return jsonify(_quick_backend().featured_games())
    except Exception as e:
        return jsonify({"success": False, "message": f"获取推荐数据失败: {e}", "sections": []})


@app.route('/api/free/games', methods=['GET'])
def free_games():
    query = request.args.get('q', '').strip()
    try:
        backend = DxbBackend()
        backend.log = logging.getLogger(' 大轩巴入库器mini')
        result = backend.free_games_list(query)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"获取免费游戏失败: {e}", "games": [], "total": 0})

@app.route('/api/free/inject', methods=['POST'])
def free_inject():
    """批量永久入库免费游戏：走 Steam 官方 Checkout.AddFreeLicense#1，只认 API 会话 Cookie。"""
    data = request.get_json(silent=True) or {}
    appids = data.get('appids') or []
    names = data.get('names') or {}
    if not appids:
        return jsonify({"success": False, "message": "没有需要入库的游戏。"}), 400
    cookie = (data.get('cookie') or '').strip()
    if not cookie:
        try:
            cfg = DxbBackend()._load_config_sync() or {}
            cookie = (cfg.get('steam_cookie') or '').strip()
        except Exception:
            cookie = ''
    if not cookie or 'steamLoginSecure' not in cookie:
        return jsonify({"success": False, "mode": "api", "need_login": True,
                        "injected": 0, "skipped": 0, "items": [],
                        "message": "入库必须连接 Steam 官方账号：请点上方「登录 Steam」输入用户名密码完成邮箱验证。"})
    try:
        async def _inject():
            async with DxbBackend() as backend:
                await backend.initialize()
                return backend.inject_free_games(appids, names, cookie)
        return jsonify(asyncio.run(_inject()))
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "mode": "api", "message": f"入库失败: {e}",
                        "injected": 0, "skipped": 0, "items": []})

@app.route('/api/free/login/start', methods=['POST'])
def free_login_start():
    """第 1 步：用户名 + 密码，返回是否需要邮箱验证码。"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({"success": False, "need_email": False, "message": "请输入用户名和密码。"}), 400
    backend = DxbBackend()
    backend.log = logging.getLogger(' 大轩巴入库器mini')
    try:
        result = backend.steam_web_login(username, password)
    except Exception as e:
        backend.log.error(backend.stack_error(e))
        return jsonify({"success": False, "need_email": False, "message": f"登录失败: {e}"})
    if result.get('success'):
        result['message'] = '用户名密码通过。'
    return jsonify(result)

@app.route('/api/free/login/finish', methods=['POST'])
def free_login_finish():
    """第 2 步：邮箱验证码 + challenge，拿到 steamLoginSecure 并保存。"""
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    challenge = (data.get('challenge') or '').strip()
    if not challenge:
        return jsonify({"success": False, "message": "登录上下文丢失，请重新输入用户名密码。"}), 400
    backend = DxbBackend()
    backend.log = logging.getLogger(' 大轩巴入库器mini')
    try:
        result = backend.steam_web_login('', '', email_code=code, challenge=challenge)
    except Exception as e:
        backend.log.error(backend.stack_error(e))
        return jsonify({"success": False, "message": f"登录失败: {e}"})
    if result.get('success') and result.get('secure'):
        secure = result['secure']
        try:
            cfg = backend._load_config_sync() or {}
            cfg['steam_cookie'] = secure
            backend._save_config_sync(cfg)
        except Exception as e:
            backend.log.warning(f"保存会话失败: {e}")
        info = backend.session_info(secure)
        result['session'] = info
        result['message'] = '登录成功，已保存 Steam 官方会话。'
    return jsonify(result)

@app.route('/api/free/logout', methods=['POST'])
def free_logout():
    """断开：清掉本地保存的会话（不影响 Steam 账号本身）。"""
    try:
        backend = DxbBackend()
        cfg = backend._load_config_sync() or {}
        cfg.pop('steam_cookie', None)
        backend._save_config_sync(cfg)
    except Exception:
        pass
    return jsonify({"success": True, "message": "已断开本地会话。"})

@app.route('/api/free/session', methods=['POST'])
def free_session():
    """校验 Steam 官方账号会话（读 steamLoginSecure Cookie），返回账号信息。"""
    data = request.get_json(silent=True) or {}
    cookie = (data.get('cookie') or '').strip()
    try:
        backend = DxbBackend()
        backend.log = logging.getLogger(' 大轩巴入库器mini')
        result = backend.session_info(cookie)
        if result.get('success') and cookie:
            try:
                cfg = backend._load_config_sync() or {}
                cfg['steam_cookie'] = cookie
                backend._save_config_sync(cfg)
            except Exception:
                pass
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "session_ok": False,
                        "message": f"读取账号信息失败: {e}"})

@app.route('/api/free/account', methods=['POST'])
def free_account():
    data = request.get_json(silent=True) or {}
    cookie = (data.get('cookie') or '').strip()
    try:
        backend = DxbBackend()
        backend.log = logging.getLogger(' 大轩巴入库器mini')
        result = backend.free_account_info(cookie)
        if result.get('success') and cookie:
            cfg = backend._load_config_sync()
            cfg['steam_cookie'] = cookie
            backend._save_config_sync(cfg)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"读取账号信息失败: {e}"})

@app.route('/api/manager/delete', methods=['POST'])
def delete_managed_files():
    data = request.get_json()
    file_type = data.get('type')
    items = data.get('items')

    if not file_type or not items:
        return jsonify({"success": False, "message": "请求参数无效。"}), 400

    try:
        async def _delete():
            async with DxbBackend() as backend:
                await backend.initialize()
                return backend.delete_managed_files(file_type, items)
        
        result = asyncio.run(_delete())
        return jsonify(result)

    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"删除文件时发生错误: {str(e)}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message}), 500

@app.route('/api/manager/open_folder', methods=['POST'])
def open_manager_folder():
    if sys.platform != 'win32':
        return jsonify({"success": False, "message": "此功能仅在Windows上可用。"}), 400
    
    data = request.get_json()
    folder_type = data.get('type')
    
    try:
        backend = DxbBackend()
        asyncio.run(backend.initialize())
        path_to_open = None
        if folder_type == 'st' and backend.steam_path:
            path_to_open = backend.steam_path / 'config' / 'stplug-in'
        elif folder_type == 'gl' and backend.steam_path:
            path_to_open = backend.steam_path / 'AppList'
        
        if path_to_open and path_to_open.exists():
            os.startfile(path_to_open)
            return jsonify({"success": True, "message": f"正在打开目录: {path_to_open}"})
        else:
            return jsonify({"success": False, "message": "目录不存在。"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": f"打开目录失败: {e}"}), 500



@app.route('/api/config/detailed')
def get_detailed_config():
    config_path = project_root / 'config.json'
    try:
        config = standard_json.load(open(config_path, 'r', encoding='utf-8')) if config_path.exists() else DEFAULT_CONFIG.copy()
        steam_path_str = config.get("Custom_Steam_Path", "")
        steam_path_is_auto = False
        if not steam_path_str:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
                    steam_path_str, _ = winreg.QueryValueEx(key, 'SteamPath')
                steam_path_is_auto = True
            except Exception: steam_path_str = ""
        return jsonify({"success": True, "config": {
            "github_token": config.get("Github_Personal_Token", ""),
            "steam_path": str(steam_path_str),
            "debug_mode": config.get("debug_mode", False),
            "logging_files": config.get("logging_files", True),
            "steam_path_is_auto": steam_path_is_auto,
            "background_image_path": config.get("background_image_path", ""),
            "background_blur": config.get("background_blur", 0),
            "background_saturation": config.get("background_saturation", 100),
            "background_brightness": config.get("background_brightness", 100),
            "show_console_on_startup": config.get("show_console_on_startup", False),
            "force_unlocker_type": config.get("force_unlocker_type", "auto"),
            "auto_install_unlocker": config.get("auto_install_unlocker", True),
            "unlocker_preference": config.get("unlocker_preference", "greenluma"),
            "greenluma_repo": config.get("greenluma_repo", "WinterSamza/GreenLuma_2025"),
            "steamtools_repo": config.get("steamtools_repo", ""),
            "custom_repos": config.get("Custom_Repos", {"github": [], "zip": []}),
        }})
    except Exception as e:
        return jsonify({"success": False, "message": f"加载详细配置失败: {e}"})

@app.route('/api/config/update', methods=['POST'])
def update_config():
    config_path = project_root / 'config.json'
    try:
        data = request.get_json()
        
        if not config_path.exists():
            config_path.parent.mkdir(exist_ok=True, parents=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                standard_json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            current_config = standard_json.load(f)
        
        updatable_keys = [
            "github_token", "steam_path", "debug_mode", "logging_files", "disable_logging",
            "background_image_path", "background_blur", "background_saturation",
            "background_brightness", "show_console_on_startup", "force_unlocker_type",
            "auto_install_unlocker", "unlocker_preference", "greenluma_repo", "steamtools_repo"
        ]
        key_map = {
            "github_token": "Github_Personal_Token",
            "steam_path": "Custom_Steam_Path"
        }
        
        for key in updatable_keys:
            if key in data:
                config_key = key_map.get(key, key)
                current_config[config_key] = data[key]

        if "auto_install_unlocker" in data:
            current_config["auto_install_unlocker_ack"] = True

        if "custom_repos" in data:
            current_config["Custom_Repos"] = data["custom_repos"]

        with open(config_path, 'w', encoding='utf-8') as f:
            standard_json.dump(current_config, f, indent=2, ensure_ascii=False)
        
        print(f"配置已保存到: {config_path}")
        return jsonify({"success": True, "message": "配置已保存。"})
        
    except Exception as e:
        print(f"保存配置失败: {e}")
        return jsonify({"success": False, "message": f"保存配置失败: {e}"})

@app.route('/api/config/reset', methods=['POST'])
def reset_config():
    config_path = project_root / 'config.json'
    try:
        existing_bg_settings = {}
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = standard_json.load(f)
            bg_keys = ["background_image_path", "background_blur", "background_saturation", "background_brightness"]
            for key in bg_keys:
                if key in current_config:
                    existing_bg_settings[key] = current_config[key]
        
        new_config = DEFAULT_CONFIG.copy()
        new_config.update(existing_bg_settings)
        
        config_path.parent.mkdir(exist_ok=True, parents=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            standard_json.dump(new_config, f, indent=2, ensure_ascii=False)
        
        print(f"配置已重置并保存到: {config_path}")
        return jsonify({"success": True, "message": "配置已重置为默认值 (背景设置已保留)。"})
        
    except Exception as e:
        print(f"重置配置失败: {e}")
        return jsonify({"success": False, "message": f"重置配置失败: {e}"})


@app.route('/api/upload_background', methods=['POST'])
def upload_background():
    if 'backgroundFile' not in request.files: return jsonify({"success": False, "message": "未找到文件"}), 400
    file = request.files['backgroundFile']
    if file.filename == '': return jsonify({"success": False, "message": "未选择文件"}), 400
    if file:
        userdata_folder = app.config['USER_DATA_FOLDER']
        userdata_folder.mkdir(exist_ok=True)
        save_path = userdata_folder / f"custom_background{Path(file.filename).suffix}"
        try:
            file.save(save_path)
            return jsonify({"success": True, "path": str(save_path.relative_to(project_root)).replace('\\', '/')})
        except Exception as e:
            return jsonify({"success": False, "message": f"保存文件失败: {e}"}), 500

@app.route('/userdata/<path:filename>')
def serve_userdata(filename): return send_from_directory(app.config['USER_DATA_FOLDER'], filename)

@app.route('/api/open-external', methods=['POST'])
def open_external():
    """把外部链接交给系统默认浏览器。

    只放行 http/https，防止页面用 file:// 之类协议做本地探测。
    """
    data = request.get_json(silent=True) or {}
    url = str(data.get('url') or '').strip()
    if not url.lower().startswith(('http://', 'https://')):
        return jsonify({"success": False, "message": "只允许打开 http/https 链接。"}), 400
    mode = 'system'
    if data.get('in_app') and _in_app_opener is not None:
        try:
            if _in_app_opener(url):
                mode = 'in_app'
            else:
                mode = 'system'
        except Exception as e:
            logging.getLogger('大轩巴入库器mini').warning('应用内窗口打开失败：%s', e)
            mode = 'system'
    else:
        mode = 'system'
    try:
        if mode == 'in_app':
            ok = True
        elif _external_link_opener is not None:
            ok = bool(_external_link_opener(url))
        else:
            ok = bool(os.startfile(url)) if hasattr(os, 'startfile') else bool(webbrowser.open(url))
        return jsonify({"success": ok, "url": url, "mode": mode})
    except Exception as e:
        return jsonify({"success": False, "message": f"打开链接失败: {e}"}), 500

@app.route('/api/devtools', methods=['POST', 'GET'])
def open_devtools():
    """F12 / Ctrl+Shift+I：打开内嵌 WebView2 的开发者工具。"""
    if _devtools_opener is None:
        return jsonify({"success": False, "message": "当前运行模式不支持 DevTools。"}), 501
    try:
        _devtools_opener()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": f"打开 DevTools 失败: {e}"}), 500

@app.route('/api/steam/launch', methods=['POST'])
def steam_launch():
    """让系统协议处理器打开 steam:// 链接（安装 / 启动游戏）。

    webview 里 window.open('steam://...') 不可靠（会被当普通外链拦截），
    统一改由本地服务调用系统默认处理程序，最稳。
    """
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or '').strip().lower()
    appid = str(data.get('appid') or '').strip()
    fixed = {
        'open_downloads': 'steam://open/downloads',
        'open_settings': 'steam://open/settings',
        'open_store': 'steam://store',
        'open_library': 'steam://open/games',
    }
    if action in fixed:
        url = fixed[action]
    elif action in ('install', 'run'):
        if not appid.isdigit():
            return jsonify({"success": False, "message": "无效的 AppID。"})
        url = f'steam://{action}/{appid}'
    else:
        return jsonify({"success": False, "message": "无效的操作。"})
    try:
        if hasattr(os, 'startfile'):
            os.startfile(url)
        else:
            webbrowser.open(url)
        msg = {
            'install': "已请求 Steam 安装，请在 Steam 客户端确认。",
            'run': "已请求 Steam 启动。",
        }.get(action, "已打开 Steam。")
        return jsonify({"success": True, "url": url, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "message": f"调用 Steam 失败: {e}", "url": url})


@app.route('/api/steam/downloads', methods=['GET'])
def steam_downloads():
    """下载管理：列出各 Steam 库里正在下载/更新与已安装的条目。"""
    try:
        return jsonify(_quick_backend().steam_downloads())
    except Exception as e:
        return jsonify({"success": False, "message": f"读取下载列表失败: {e}",
                        "active": [], "done": [], "total": 0, "active_total": 0})


@app.route('/api/steam/downloads/discard', methods=['POST'])
def steam_discard_download():
    """移除某个下载任务（半成品缓存 + 清单，清单会先备份）。"""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(_quick_backend().steam_discard_download(data.get('appid')))
    except Exception as e:
        return jsonify({"success": False, "message": f"移除下载任务失败: {e}"})


@app.route('/api/steam/diagnose', methods=['GET'])
def steam_diagnose():
    """Steam 环境体检：路径/进程/权限/空间/hosts/缓存/残留/网络。"""
    try:
        return jsonify(_quick_backend().steam_diagnose())
    except Exception as e:
        return jsonify({"success": False, "message": f"诊断失败: {e}", "checks": [], "fixes": []})


@app.route('/api/steam/repair', methods=['POST'])
def steam_repair():
    """执行诊断给出的修复动作（可多选）。"""
    data = request.get_json(silent=True) or {}
    actions = data.get('actions') or []
    if not isinstance(actions, list):
        return jsonify({"success": False, "message": "无效的修复项。", "results": []})
    try:
        return jsonify(_quick_backend().steam_repair(actions))
    except Exception as e:
        return jsonify({"success": False, "message": f"修复失败: {e}", "results": []})


@app.route('/api/steam/accel/status', methods=['GET'])
def steam_accel_status():
    """加速状态：hosts 里是否已有加速块、是否管理员、hosts 是否可写。"""
    try:
        return jsonify(_quick_backend().steam_accel_status())
    except Exception as e:
        return jsonify({"success": False, "enabled": False, "applied": {}, "count": 0,
                        "admin": False, "writable": False, "message": f"读取加速状态失败: {e}"})


@app.route('/api/steam/accel/scan', methods=['POST'])
def steam_accel_scan():
    """并发 DoH 解析 + 真实测速，给出每个域名的最优 IP。"""
    data = request.get_json(silent=True) or {}
    domains = data.get('domains')
    if domains is not None and not isinstance(domains, list):
        domains = None
    try:
        return jsonify(_quick_backend().steam_accel_scan(domains or None))
    except Exception as e:
        return jsonify({"success": False, "message": f"测速失败: {e}", "domains": []})


@app.route('/api/steam/accel/apply', methods=['POST'])
def steam_accel_apply():
    """把选中的优选 IP 写入 hosts（先备份，可一键还原）。"""
    data = request.get_json(silent=True) or {}
    entries = data.get('entries') or []
    if not isinstance(entries, list):
        return jsonify({"success": False, "message": "无效的加速条目。"})
    try:
        return jsonify(_quick_backend().steam_accel_apply(entries))
    except Exception as e:
        return jsonify({"success": False, "message": f"写入加速失败: {e}"})


@app.route('/api/steam/accel/restore', methods=['POST'])
def steam_accel_restore():
    """移除 hosts 里的加速块。"""
    try:
        return jsonify(_quick_backend().steam_accel_restore())
    except Exception as e:
        return jsonify({"success": False, "message": f"还原失败: {e}"})


@app.route('/api/accel/categories', methods=['GET'])
def accel_categories():
    """返回所有加速分类及其域名，供前端渲染标签页。"""
    try:
        from backend import ACCEL_CATEGORIES
        out = {k: {'label': v['label'],
                   'domains': [{'domain': d, 'group': g, 'desc': desc}
                               for d, g, desc in v['domains']]}
               for k, v in ACCEL_CATEGORIES.items()}
        return jsonify({"success": True, "categories": out})
    except Exception as e:
        return jsonify({"success": False, "message": f"读取加速分类失败: {e}"})


@app.route('/api/accel/<category>/status', methods=['GET'])
def accel_status_route(category):
    try:
        return jsonify(_quick_backend().accel_status(category))
    except Exception as e:
        return jsonify({"success": False, "enabled": False, "applied": {}, "count": 0,
                        "admin": False, "writable": False, "message": f"读取加速状态失败: {e}"})


@app.route('/api/accel/<category>/scan', methods=['POST'])
def accel_scan_route(category):
    data = request.get_json(silent=True) or {}
    domains = data.get('domains')
    if domains is not None and not isinstance(domains, list):
        domains = None
    try:
        return jsonify(_quick_backend().accel_scan(category, domains or None))
    except Exception as e:
        return jsonify({"success": False, "message": f"测速失败: {e}", "domains": []})


@app.route('/api/accel/<category>/apply', methods=['POST'])
def accel_apply_route(category):
    data = request.get_json(silent=True) or {}
    entries = data.get('entries') or []
    if not isinstance(entries, list):
        return jsonify({"success": False, "message": "无效的加速条目。"})
    try:
        return jsonify(_quick_backend().accel_apply(category, entries))
    except Exception as e:
        return jsonify({"success": False, "message": f"写入加速失败: {e}"})


@app.route('/api/accel/<category>/restore', methods=['POST'])
def accel_restore_route(category):
    try:
        return jsonify(_quick_backend().accel_restore(category))
    except Exception as e:
        return jsonify({"success": False, "message": f"还原失败: {e}"})


@app.route('/api/accel/<category>/hostsfree/apply', methods=['POST'])
def accel_hostsfree_apply_route(category):
    try:
        data = request.get_json(silent=True) or {}
        entries = data.get('entries', [])
        return jsonify(_quick_backend().accel_hostsfree_apply(category, entries))
    except Exception as e:
        return jsonify({"success": False, "message": f"保存失败: {e}"})


@app.route('/api/accel/<category>/hostsfree/restore', methods=['POST'])
def accel_hostsfree_restore_route(category):
    try:
        return jsonify(_quick_backend().accel_hostsfree_restore(category))
    except Exception as e:
        return jsonify({"success": False, "message": f"还原失败: {e}"})


@app.route('/api/accel/hostsfree/status', methods=['GET'])
def accel_hostsfree_status_route():
    try:
        return jsonify(_quick_backend().accel_hostsfree_status())
    except Exception as e:
        return jsonify({"success": False, "message": f"读取失败: {e}"})


@app.route('/api/app/restart', methods=['POST'])
def app_restart():
    """普通重启本程序（免hosts加速等需重启生效的功能用）。"""
    if _normal_restart is None:
        return jsonify({"success": False, "available": False,
                        "message": "当前环境不支持自动重启，请手动重启应用。"})
    def _go():
        time.sleep(0.6)
        try:
            _normal_restart()
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()
    return jsonify({"success": True, "message": "正在重启应用…"})


_privilege_state = {"last_elevate": None, "last_elevate_at": 0}


@app.route('/api/app/privilege', methods=['GET'])
def app_privilege():
    """真实检测当前权限状态（不猜）：是否管理员、能否提权、能否普通重启。"""
    try:
        is_admin = bool(DxbBackend.is_admin())
    except Exception:
        is_admin = False
    return jsonify({
        "success": True,
        "admin": is_admin,
        "level": "admin" if is_admin else "user",
        "pid": os.getpid(),
        "exe": sys.executable,
        "frozen": bool(getattr(sys, 'frozen', False)),
        "elevate_available": _elevated_restart is not None,
        "restart_available": _normal_restart is not None,
        "last_elevate": _privilege_state.get("last_elevate"),
        "last_elevate_at": _privilege_state.get("last_elevate_at"),
    })


@app.route('/api/app/restart_elevated', methods=['POST'])
def app_restart_elevated():
    """以管理员身份重启本程序：真实检测 + 真实回传 UAC 结果（仅桌面壳可用）。"""
    _privilege_state["last_elevate_at"] = time.time()

    try:
        already = bool(DxbBackend.is_admin())
    except Exception:
        already = False
    if already:
        _privilege_state["last_elevate"] = "already_admin"
        return jsonify({"success": True, "already": True, "level": "admin",
                        "message": f"检测结果：当前进程已是管理员权限（PID {os.getpid()}），无需重启。"})

    if _elevated_restart is None:
        _privilege_state["last_elevate"] = "unavailable"
        return jsonify({"success": False, "available": False, "level": "user",
                        "message": "检测结果：当前不是管理员，且本环境拿不到提权通道。\n"
                                   "请关闭程序，右键 exe →「以管理员身份运行」。"})

    try:
        ok = bool(_elevated_restart())
    except Exception as e:
        _privilege_state["last_elevate"] = f"error: {e}"
        return jsonify({"success": False, "level": "user",
                        "message": f"提权失败：{e}"})
    if not ok:
        _privilege_state["last_elevate"] = "denied"
        return jsonify({"success": False, "level": "user", "denied": True,
                        "message": "检测结果：提权被拒绝（UAC 弹窗点了「否」，或被系统策略拦截）。\n"
                                   "Steam 加速写 hosts 仍需要管理员权限，请右键 exe →「以管理员身份运行」。"})

    _privilege_state["last_elevate"] = "granted"
    return jsonify({"success": True, "level": "elevating", "restarting": True,
                    "message": "已通过 UAC 授权，正在以管理员身份重启。\n"
                               "当前窗口会在 1~2 秒内关闭，新的管理员窗口会自动打开（可能需几秒）。"})


@app.route('/api/steam/restart', methods=['POST'])
def restart_steam():
    try:
        async def _restart():
            async with DxbBackend() as backend:
                await backend.initialize()
                patch_log_for_socketio(backend.log)
                success = backend.restart_steam()
                if success:
                    return {"success": True, "message": "已发送重启 Steam 的指令。这可能需要一些时间。"}
                else:
                    return {"success": False, "message": "重启 Steam 失败，请检查路径配置或日志。"}
        
        result = asyncio.run(_restart())
        return jsonify(result)
        
    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"请求重启Steam时发生后端错误: {str(e)}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message}), 500
@app.route('/api/console/toggle', methods=['POST'])
def toggle_console():
    if sys.platform != 'win32': return jsonify({"success": False, "message": "此功能仅在Windows上可用。"}), 400
    was_visible = console_manager.is_visible
    console_manager.toggle_console()
    message = "控制台已隐藏。" if was_visible else "控制台已显示。日志将输出到新窗口。"
    return jsonify({"success": True, "message": message, "isVisible": not was_visible})

@socketio.on('connect')
def handle_connect(): emit('response', {"message": "已连接到大轩巴入库器mini服务器"})

# --------------------------------------------------------------- 加速核心

_ACCEL = {'mgr': None}


def _accel_mgr():
    """懒加载加速管理器：只在实际用到加速时才 import，不影响启动速度。"""
    if _ACCEL['mgr'] is None:
        try:
            import accel_core
            base = app.config.get('USER_DATA_FOLDER') or str(project_root)
            _ACCEL['mgr'] = accel_core.MihomoManager(
                os.path.join(base, 'accel'))
        except Exception as e:
            logging.getLogger('大轩巴入库器mini').warning('加速模块加载失败：%s', e)
            _ACCEL['mgr'] = None
    return _ACCEL['mgr']


def _accel_guard():
    m = _accel_mgr()
    if m is None:
        return None, jsonify({'success': False, 'message': '加速模块不可用'}), 500
    return m, None, None


@app.route('/api/accel/status', methods=['GET'])
def accel_status():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    st = m.status()
    try:
        import accel_core
        st['system_proxy'] = accel_core.system_proxy_state()
    except Exception:
        st['system_proxy'] = {'enabled': False, 'server': ''}
    return jsonify({'success': True, **st})


@app.route('/api/accel/ensure', methods=['POST'])
def accel_ensure():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    return jsonify(m.ensure_core())


@app.route('/api/accel/start', methods=['POST'])
def accel_start():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    return jsonify(m.start())


@app.route('/api/accel/stop', methods=['POST'])
def accel_stop():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    return jsonify(m.stop())


@app.route('/api/accel/sub', methods=['POST'])
def accel_sub():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(m.apply_subscription(str(data.get('url') or '')))


@app.route('/api/accel/nodes', methods=['GET'])
def accel_nodes():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    return jsonify(m.nodes())


@app.route('/api/accel/select', methods=['POST'])
def accel_select():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(m.select(str(data.get('name') or '')))


@app.route('/api/accel/delay', methods=['POST'])
def accel_delay():
    m, err, code = _accel_guard()
    if m is None:
        return err, code
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(m.delay_test(str(data.get('name') or '')))


@app.route('/api/accel/sysproxy', methods=['POST', 'GET'])
def accel_sysproxy():
    try:
        import accel_core
    except Exception as e:
        return jsonify({'success': False, 'message': '加速模块不可用：%s' % e}), 500
    if request.method == 'GET':
        return jsonify({'success': True, **accel_core.system_proxy_state()})
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(accel_core.set_system_proxy(bool(data.get('enable'))))


# --------------------------------------------------------------- 完整安装包

@app.route('/accel')
def accel_page():
    return render_template('accel.html')


def _version_text() -> str:
    try:
        import backend as _b
        return str(_b.CURRENT_VERSION)
    except Exception:
        try:
            import backend
            return str(backend.CURRENT_VERSION)
        except Exception:
            return '2.25'


def _installer_source_exe():
    """主程序 exe：打包产物优先，开发态退回当前解释器。"""
    for p in (os.path.join(project_root, 'dist_enc', '大轩巴入库器mini.exe'),
              os.path.join(project_root, 'dist', '大轩巴入库器mini.exe')):
        if os.path.isfile(p):
            return p
    return sys.executable


@app.route('/api/installer', methods=['GET'])
def download_installer():
    """登录后可取：主应用 + 加速内核 + 说明 打成一个 zip。

    内核 60MB 不进主 exe（否则启动和体积都难看），这里按需拉回来一起打包。
    """
    import zipfile

    try:
        import accel_core
    except Exception as e:
        return jsonify({'success': False, 'message': '打包组件缺失：%s' % e}), 500

    base = app.config.get('USER_DATA_FOLDER') or str(project_root)
    out_dir = os.path.join(base, 'installer')
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        out_dir = os.path.join(project_root, 'installer')
        os.makedirs(out_dir, exist_ok=True)

    exe = _installer_source_exe()
    if not os.path.isfile(exe):
        return jsonify({'success': False, 'message': '找不到主程序文件'}), 404

    mgr = accel_core.MihomoManager(os.path.join(base, 'accel'))
    if not mgr.core_exists():
        r = mgr.ensure_core()
        if not r.get('ok'):
            return jsonify({'success': False, 'message': r.get('message', '内核下载失败')}), 500

    out = os.path.join(out_dir, '大轩巴入库器mini-完整包.zip')
    tmp = out + '.tmp'
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(exe, arcname='大轩巴入库器mini.exe')
            z.write(mgr.core, arcname='core/大轩巴入库器mini.exe')
            z.writestr('使用说明.txt', _INSTALLER_README.format(version=_version_text()))
    except Exception as e:
        return jsonify({'success': False, 'message': '打包失败：%s' % e}), 500
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

    resp = send_from_directory(out_dir, os.path.basename(out), as_attachment=True)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


_INSTALLER_README = """大轩巴入库器mini 完整包 v{version}
========================================

【包含】
  大轩巴入库器mini.exe           主程序（已加密，双击即用）
  core/大轩巴入库器mini.exe        加速内核（加速进程显示名同主程序，任务管理器里
                                  只会看到应用自己，不出现第三方加速程序名）

【安装 / 使用】
  1. 把整个文件夹放到任意位置，不要只单独拖主程序出来（加速内核在 core/ 里）。
  2. 双击 大轩巴入库器mini.exe 启动。
  3. 首次用加速：应用内「加速」页 -> 填订阅链接 -> 启动加速。
  4. 点「一键加速 Steam」后内核会走 127.0.0.1:{port}，
     Steam 读系统代理设置即可生效；不用了点「关闭系统代理」。

【注意】
  - 加速需要订阅链接；没有订阅只能启动内核，规则全走 DIRECT。
  - 关闭应用时不会替你关掉系统代理，需手动点「关闭系统代理」。
  - 内核文件是官方原版，不含任何改动。
""".replace('{port}', '7890')


@app.route('/api/shutdown', methods=['POST', 'GET'])
def shutdown():
    """关闭应用。桌面壳（dxb_desktop）重启/提权后用 GET 打这个口，
    以前只允许 POST → 405 → 旧实例不退出 → 出现「一个主窗口一个后台窗口」。"""
    print("接收到 HTTP 关闭请求，正在准备关闭服务器...")

    def stop_accel_quietly():
        """退出前把加速收拾干净，不留「自己偷偷在跑」的加速进程和系统代理。"""
        try:
            m = _accel_mgr()
            if m is not None and m.status().get('running'):
                m.stop()
                print('关闭应用：加速内核已停止。')
        except Exception as e:
            print('关闭应用：清理加速失败：', e)

    threading.Thread(target=stop_accel_quietly, daemon=True).start()

    def kill_process():
        try:
            if _window_closer:
                t = threading.Thread(target=_window_closer, daemon=True)
                t.start()
                t.join(1.0)
        except Exception:
            pass
        time.sleep(0.2)
        os._exit(0)

    threading.Thread(target=kill_process, daemon=True).start()
    return jsonify({"success": True, "message": "服务器正在关闭..."})

if __name__ == '__main__':
    if sys.platform == 'win32':
        try:
            os.system('title ' + '大轩巴入库器mini')
        except:
            pass 
    
    if sys.platform == 'win32' and should_show_console_on_startup():
        console_manager._show_console()
    
    port = get_port_from_gui()
    
    print(f"将使用端口: {port}")
    url = f"http://127.0.0.1:{port}"
    def open_browser():
        print("服务器已启动，正在尝试自动打开浏览器...")
        webbrowser.open_new(url)
    print("正在启动大轩巴入库器mini...")
    print(f"服务器将在 {url} 上运行")
    threading.Timer(1.5, open_browser).start()
    socketio.run(app, host='127.0.0.1', port=port, debug=False, allow_unsafe_werkzeug=True)