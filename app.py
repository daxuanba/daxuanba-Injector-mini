# --- START OF FILE app.py (MODIFIED WITH AUTO-UPDATE AND CUSTOM REPOS) ---

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

# --- Project Setup ---
project_root = Path.cwd()
sys.path.insert(0, str(project_root))

try:
    from backend import DxbBackend, DEFAULT_CONFIG
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dxb-injector-secret-key-v2'
app.config['USER_DATA_FOLDER'] = project_root / 'userdata'
# 仅保留一次初始化，并显式指定 threading 模式：
# 后台线程（安装依赖/跑任务）会通过 patch_log_for_socketio 调用 socketio.emit，
# 必须运行在 threading 模式下，否则跨线程 emit 会失败。
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- GUI Port Prompt ---
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


# --- Pre-startup Config Check ---
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

# --- Global Task State & Logging ---
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


# ---------------- 沉默浏览器登录 Steam ----------------
# 桌面壳（dxb_desktop.py）启动时注入 launcher；无 GUI 环境则降级为手动粘贴 Cookie。
STEAM_LOGIN = {
    "available": False,   # 桌面壳是否注入内置浏览器登录
    "status": "idle",     # idle | waiting | success | error
    "message": "",
    "account": None,
}
_steam_login_launcher = None


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


def _is_steam_logged_in() -> bool:
    """入库前的登录态判定：内置浏览器登录成功，或配置里已存过 Cookie。"""
    if STEAM_LOGIN.get("status") == "success" and STEAM_LOGIN.get("account"):
        return True
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

# --- HTML Page Routes ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/settings')
def settings_page(): return render_template('settings.html')

@app.route('/about')
def about_page(): return render_template('about.html')

# NEW: Route for the file manager page
@app.route('/manager')
def manager_page():
    return render_template('manager.html')

# NEW: 手搓独立页面
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


# --- Core API Routes ---
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
def initialize_app():  # 改为同步函数
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
                    "pending_unlocker_install": pending,
                    "steam_path": str(backend.steam_path) if backend.steam_path else "Not Found",
                    "has_token": bool(backend.config.get("Github_Personal_Token", "").strip())
                }

        result = asyncio.run(_init())
        # 如果标记了后台安装，启动后台线程，不阻塞初始化响应
        if result.get("pending_unlocker_install"):
            threading.Thread(target=background_install_unlocker, daemon=True).start()
        return jsonify(result)

    except Exception as e:
        dummy_backend = DxbBackend()
        message = f"后端初始化失败: {str(e)}"
        dummy_backend.log.error(dummy_backend.stack_error(e))
        return jsonify({"success": False, "message": message})

# NEW: Auto-update check endpoint
@app.route('/api/check_updates', methods=['POST'])
def check_updates():  # 改为同步函数
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

# NEW: Steam 状态（首页状态条：位置 + 内核检测）
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

# NEW: 依赖模块状态（OpenSteamTool 内核 / SteamTools）
@app.route('/api/dependency/status', methods=['GET'])
def dependency_status():
    try:
        async def _st():
            async with DxbBackend() as backend:
                await backend.initialize()
                return backend.get_opensteamtool_status(), backend.get_steamtools_status(), backend.get_steam_status()
        otool, stools, steam = asyncio.run(_st())
        return jsonify({"success": True, "opensteamtool": otool, "steamtools": stools, "steam": steam})
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
    if kind not in ("opensteamtool", "steamtools"):
        return jsonify({"success": False, "message": "未知的依赖类型。"}), 400
    threading.Thread(target=_background_install_dependency, args=(kind, force), daemon=True).start()
    label = "OpenSteamTool 内核" if kind == "opensteamtool" else "SteamTools"
    return jsonify({"success": True, "message": f"已在后台开始下载/更新 {label}。"})


# NEW: 应用自更新：下载最新安装包并自动打开安装
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
                # 优先下载 .exe 资产（本应用为单文件 exe）
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
            # 退出当前进程，让新安装包接管
            def kill_process():
                time.sleep(1.0)
                os._exit(0)
            threading.Thread(target=kill_process, daemon=True).start()
        return jsonify(result)
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": str(e)})


# NEW: Lua 手搓（Steam API 抓信息 -> 生成 OpenSteamTool 风格 lua）
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


# NEW: 手搓结果一键入库（写入 Steam config\lua）
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


# NEW: Get available sources (including custom repos)
@app.route('/api/sources', methods=['GET'])
def get_sources():  # 改为同步函数
    try:
        async def _get_sources():
            async with DxbBackend() as backend:
                await backend.initialize()
                
                # Built-in sources
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
                
                # Custom sources
                custom_github_repos = backend.get_custom_github_repos()
                custom_zip_repos = backend.get_custom_zip_repos()
                
                # Add custom GitHub repos
                for repo in custom_github_repos:
                    builtin_sources[f"{repo['name']} (自定义GitHub)"] = repo['repo']
                
                # Add custom ZIP repos  
                for repo in custom_zip_repos:
                    builtin_sources[f"{repo['name']} (自定义ZIP)"] = f"custom_zip_{repo['name']}"

                # 探测所有内置源可用性，剔除不可用，自动选最优
                availability, recommended = await backend.test_sources()
                filtered_sources = {
                    name: value for name, value in builtin_sources.items()
                    if availability.get(value, True)
                }
                # 自定义源默认视为可用（用户已配置）
                if recommended is None or recommended not in filtered_sources.values():
                    # 若推荐项被过滤（不可用），回退到过滤后第一个「内置」可用源；
                    # 仅从 availability 中筛选内置源，避免把自定义源误当推荐默认。
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
        # 需要查 GitHub API 的源（仓库类 + 自动搜索）才校验速率；
        # steamautocracks_v2 走 steamui 接口，不消耗 GitHub API 额度，排除。
        needs_github_api = (tool_type == "search") or ("/" in tool_type and tool_type != "steamautocracks_v2")
        if needs_github_api and not await backend.check_github_api_rate_limit():
            raise Exception("GitHub API 请求次数已用尽，无法继续。")
                
        app_id_extracted = backend.extract_app_id(app_id)
        if not app_id_extracted:
            raise Exception(f"无法从 '{app_id}' 中提取有效AppID。请输入有效的AppID或链接。")
            
        if tool_type == "search":
            backend.log.info(f"正在所有 GitHub 仓库中搜索 AppID: {app_id_extracted}...")
            # MODIFIED: Use all repos including custom ones
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
        
        # 修改这里：添加steamautocracks_v2到zip_sources列表
        zip_sources = ["printedwaste", "cysaw", "furcate", "walftech", "steamdatabase", "steamautocracks_v2", "sudama"]
        
        # Check for custom zip sources
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

# Workshop task runner
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
    patch_depot_key = data.get('patch_depot_key', False)  # NEW: 获取depotkey修补参数
    
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

# Workshop task endpoint
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

# --- NEW: File Manager API ---
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

# --- 免费游戏页 API ---
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
    # 桌面壳投递失败（槽未匹配 / 桥已销毁）时必须如实上报，
    # 否则前端会显示“已打开登录窗口”然后白等 5 分钟 —— 就是用户报的“点了打不开”。
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
    # 前端用 encodeURIComponent 传参，Flask 已解码一次，这里不要再 unquote
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
    """批量永久入库免费游戏（写入解锁器 lua 目录）。"""
    data = request.get_json(silent=True) or {}
    appids = data.get('appids') or []
    names = data.get('names') or {}
    if not appids:
        return jsonify({"success": False, "message": "没有需要入库的游戏。"}), 400
    # 未登录不允许入库：先让用户用内置浏览器登录 Steam
    if not _is_steam_logged_in():
        return _steam_login_required()
    try:
        async def _inject():
            async with DxbBackend() as backend:
                await backend.initialize()
                return backend.inject_free_games(appids, names)
        return jsonify(asyncio.run(_inject()))
    except Exception as e:
        dummy = DxbBackend()
        dummy.log.error(dummy.stack_error(e))
        return jsonify({"success": False, "message": f"入库失败: {e}", "injected": 0, "skipped": 0})

@app.route('/api/free/account', methods=['POST'])
def free_account():
    data = request.get_json(silent=True) or {}
    cookie = (data.get('cookie') or '').strip()
    try:
        backend = DxbBackend()
        backend.log = logging.getLogger(' 大轩巴入库器mini')
        result = backend.free_account_info(cookie)
        # 记住 cookie 到配置（本地工具，敏感信息自行保管）
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

# --- END of File Manager API ---


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
            # 解锁器自动安装
            "auto_install_unlocker": config.get("auto_install_unlocker", True),
            "unlocker_preference": config.get("unlocker_preference", "greenluma"),
            "greenluma_repo": config.get("greenluma_repo", "WinterSamza/GreenLuma_2025"),
            "steamtools_repo": config.get("steamtools_repo", "SteamTools/STAupdater"),
            # NEW: 添加自定义清单库配置
            "custom_repos": config.get("Custom_Repos", {"github": [], "zip": []}),
        }})
    except Exception as e:
        return jsonify({"success": False, "message": f"加载详细配置失败: {e}"})

@app.route('/api/config/update', methods=['POST'])
def update_config():  # 改为同步函数
    config_path = project_root / 'config.json'
    try:
        data = request.get_json()
        
        # 确保配置文件存在
        if not config_path.exists():
            # 创建默认配置
            config_path.parent.mkdir(exist_ok=True, parents=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                standard_json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        
        # 读取当前配置
        with open(config_path, 'r', encoding='utf-8') as f:
            current_config = standard_json.load(f)
        
        # 更新所有可能的键
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

        # 处理自定义清单库配置
        if "custom_repos" in data:
            current_config["Custom_Repos"] = data["custom_repos"]

        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            standard_json.dump(current_config, f, indent=2, ensure_ascii=False)
        
        print(f"配置已保存到: {config_path}")  # 添加调试日志
        return jsonify({"success": True, "message": "配置已保存。"})
        
    except Exception as e:
        print(f"保存配置失败: {e}")  # 添加错误日志
        return jsonify({"success": False, "message": f"保存配置失败: {e}"})

@app.route('/api/config/reset', methods=['POST'])
def reset_config():  # 改为同步函数
    config_path = project_root / 'config.json'
    try:
        existing_bg_settings = {}
        
        # 保留背景设置
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = standard_json.load(f)
            bg_keys = ["background_image_path", "background_blur", "background_saturation", "background_brightness"]
            for key in bg_keys:
                if key in current_config:
                    existing_bg_settings[key] = current_config[key]
        
        # 创建新配置
        new_config = DEFAULT_CONFIG.copy()
        new_config.update(existing_bg_settings)
        
        # 确保目录存在
        config_path.parent.mkdir(exist_ok=True, parents=True)
        
        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            standard_json.dump(new_config, f, indent=2, ensure_ascii=False)
        
        print(f"配置已重置并保存到: {config_path}")  # 添加调试日志
        return jsonify({"success": True, "message": "配置已重置为默认值 (背景设置已保留)。"})
        
    except Exception as e:
        print(f"重置配置失败: {e}")  # 添加错误日志
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

@app.route('/api/steam/launch', methods=['POST'])
def steam_launch():
    """让系统协议处理器打开 steam:// 链接（安装 / 启动游戏）。

    webview 里 window.open('steam://...') 不可靠（会被当普通外链拦截），
    统一改由本地服务调用系统默认处理程序，最稳。
    """
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or '').strip().lower()
    appid = str(data.get('appid') or '').strip()
    # 固定入口（无需 appid）：只白名单这几个，避免变成任意 steam:// 转发器
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
            os.startfile(url)          # Windows：交给系统协议处理器
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


@app.route('/api/steam/restart', methods=['POST'])
def restart_steam():  # 改为同步函数
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

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    print("接收到 HTTP 关闭请求，正在准备关闭服务器...")
    def kill_process():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=kill_process, daemon=True).start()
    return jsonify({"success": True, "message": "服务器正在关闭..."})

if __name__ == '__main__':
    if sys.platform == 'win32':
        try:
            os.system('title ' + '大轩巴入库器mini')
        except:
            pass 
    
    # 只调用一次控制台显示检查
    if sys.platform == 'win32' and should_show_console_on_startup():
        console_manager._show_console()
    
    # 只调用一次端口选择
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