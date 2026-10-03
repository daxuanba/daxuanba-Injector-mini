import sys
import os
import traceback
import time
import logging
import subprocess
import asyncio
import re
import aiofiles
import random
import string
import colorlog
import httpx
import winreg
import ujson as json
import vdf
import zipfile
import shutil
import struct
import zlib
import io
import socket
import ssl
import locale
import ctypes
import tempfile
from pathlib import Path
from typing import Tuple, Any, List, Dict, Literal
from urllib.parse import quote

CURRENT_VERSION = "2.20"
GITHUB_REPO = "daxuanba/daxuanba-Injector-mini"

LOG_FORMAT = '%(log_color)s%(message)s'
LOG_COLORS = {
    'INFO': 'cyan',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'purple',
}

DEFAULT_CONFIG = {
    "Github_Personal_Token": "",
    "Custom_Steam_Path": "",
    "debug_mode": False,
    "logging_files": True,
    "disable_logging": False,
    "background_image_path": "",
    "background_blur": 0,
    "background_saturation": 100,
    "background_brightness": 80, 
    "show_console_on_startup": False,
    "force_unlocker_type": "auto",
    "auto_install_unlocker": False,
    "unlocker_preference": "greenluma",
    "greenluma_repo": "",
    "steamtools_repo": "",
    "Custom_Repos": {
        "github": [],
        "zip": []
    },
    "QA1": "温馨提示: Github_Personal_Token(个人访问令牌)可在Github设置的最底下开发者选项中找到, 详情请看教程。",
    "QA6": "auto_install_unlocker: 未检测到解锁工具时是否自动下载并安装。**默认关闭**——"
           "自动安装会直接往 Steam 客户端目录写 DLL（GreenLuma 隐身版是改写版 user32.dll、"
           "OpenSteamTool/SteamTools 是代理 DLL），版本与当前 Steam 客户端不匹配时会让 Steam 起不来，"
           "所以改成要装就自己到「下载管理」页点一下。unlocker_preference 填 'greenluma' / 'steamtools' / 'opensteamtool'。",
    "QA7": "greenluma_repo / steamtools_repo: 自动安装所用的镜像仓库（owner/repo），留空即可。"
           "GreenLuma 官方只在 cs.rin.ru 论坛发布、SteamTools 官方只在 steamtools.net 发布安装包，"
           "程序默认走官方/镜像自动下载，不需要你填；填了只作为官方源不通时的兜底。",
    "QA2": "Force_Unlocker: 强制指定解锁工具, 填入 'steamtools' 或 'greenluma'。留空则自动检测。",
    "QA3": "Custom_Repos: 自定义清单库配置。github数组用于添加GitHub仓库，zip数组用于添加ZIP清单库。",
    "QA4": "GitHub仓库格式: {\"name\": \"显示名称\", \"repo\": \"用户名/仓库名\"}",
    "QA5": "ZIP清单库格式: {\"name\": \"显示名称\", \"url\": \"下载URL，用{app_id}作为占位符\"}"
}

GREENLUMA_OFFICIAL_URL = "https://cs.rin.ru/forum/viewtopic.php?f=10&t=103709"

class STConverter:
    def __init__(self):
        self.logger = logging.getLogger('STConverter')

    def convert_file(self, st_path: str) -> str:
        try:
            content, _ = self.parse_st_file(st_path)
            return content
        except Exception as e:
            self.logger.error(f'ST文件转换失败: {st_path} - {e}')
            raise

    def parse_st_file(self, st_file_path: str) -> Tuple[str, dict]:
        with open(st_file_path, 'rb') as stfile:
            content = stfile.read()
        if len(content) < 12: raise ValueError("文件头过短")
        header = content[:12]
        xorkey, size, xorkeyverify = struct.unpack('III', header)
        xorkey ^= 0xFFFEA4C8
        xorkey &= 0xFF
        encrypted_data = content[12:12+size]
        if len(encrypted_data) < size: raise ValueError("加密数据小于预期大小")
        data = bytearray(encrypted_data)
        for i in range(len(data)):
            data[i] ^= xorkey
        decompressed_data = zlib.decompress(data)
        lua_content = decompressed_data[512:].decode('utf-8')
        metadata = {'original_xorkey': xorkey, 'size': size, 'xorkeyverify': xorkeyverify}
        return lua_content, metadata


STEAM_ACCEL_DOMAINS = [
    ('store.steampowered.com',           '商店', 'Steam 商店主站'),
    ('checkout.steampowered.com',        '商店', '购物车 / 结算'),
    ('api.steampowered.com',             '商店', '商店 API 接口'),
    ('help.steampowered.com',            '商店', '客服 / 帮助'),
    ('login.steampowered.com',           '登录', '账号登录'),
    ('steamcommunity.com',               '社区', '社区主站'),
    ('www.steamcommunity.com',           '社区', '社区（www）'),
    ('cdn.akamai.steamstatic.com',       'CDN',  '商店图片 / 脚本'),
    ('community.akamai.steamstatic.com', 'CDN',  '社区静态资源'),
    ('shared.akamai.steamstatic.com',    'CDN',  '通用静态资源'),
    ('steamcdn-a.akamaihd.net',          'CDN',  'Steam CDN（老域名）'),
]

STEAM_ACCEL_DOH = [
    'https://dns.alidns.com/resolve',
    'https://doh.pub/dns-query',
    'https://doh.360.cn/resolve',
    'https://223.5.5.5/resolve',
]

HOSTS_ACCEL_BEGIN = '# ==== 大轩巴 Steam 加速 BEGIN ===='
HOSTS_ACCEL_END = '# ==== 大轩巴 Steam 加速 END ===='

BROWSER_ACCEL_DOMAINS = [
    ('cdn.jsdelivr.net',            'CDN',  'jsDelivr 公共库（npm/CDN）'),
    ('fastly.jsdelivr.net',         'CDN',  'jsDelivr Fastly 节点'),
    ('fonts.googleapis.com',        '字体', 'Google Fonts 样式表'),
    ('fonts.gstatic.com',           '字体', 'Google Fonts 字体文件'),
    ('ajax.googleapis.com',         'CDN',  'Google 前端库'),
    ('cdnjs.cloudflare.com',       'CDN',  'cdnjs 静态资源'),
    ('unpkg.com',                  'CDN',  'npm 前端包'),
    ('registry.npmjs.org',         'npm',  'npm 官方源'),
]

GITHUB_ACCEL_DOMAINS = [
    ('github.com',                  '主站', 'GitHub 网站'),
    ('api.github.com',             'API',  'REST / GraphQL 接口'),
    ('raw.githubusercontent.com',   'Raw',  '原始文件 / 脚本'),
    ('gist.githubusercontent.com',  'Gist', 'Gist 片段'),
    ('avatars.githubusercontent.com', '头像', '用户头像'),
    ('github.githubassets.com',     '静态', 'GitHub 静态资源 / 图片'),
    ('objects.githubusercontent.com', '对象存储', 'Release / LFS 大文件'),
    ('releases.githubusercontent.com', 'Release', '发布附件下载'),
    ('codeload.github.com',         '源码', 'zip/tar.gz 源码下载'),
    ('uploads.github.com',          '上传', '上传接口'),
]

ACCEL_CATEGORIES = {
    'steam': {
        'label': 'Steam',
        'begin': HOSTS_ACCEL_BEGIN,
        'end': HOSTS_ACCEL_END,
        'domains': STEAM_ACCEL_DOMAINS,
    },
    'browser': {
        'label': '浏览器',
        'begin': '# ==== 大轩巴 浏览器加速 BEGIN ====',
        'end': '# ==== 大轩巴 浏览器加速 END ====',
        'domains': BROWSER_ACCEL_DOMAINS,
    },
    'github': {
        'label': 'GitHub',
        'begin': '# ==== 大轩巴 GitHub 加速 BEGIN ====',
        'end': '# ==== 大轩巴 GitHub 加速 END ====',
        'domains': GITHUB_ACCEL_DOMAINS,
    },
}
ACCEL_CATEGORY_NAMES = list(ACCEL_CATEGORIES.keys())


class DxbBackend:
    def __init__(self):
        self.project_root = Path.cwd()
        self.client: httpx.AsyncClient | None = None
        self.config = {}
        self.steam_path = None
        self.unlocker_type = None
        self.detected_kernels = {'native': True, 'steamtools': False,
                                 'greenluma': False, 'opensteamtool': False}
        self.lock = asyncio.Lock()
        self.temp_path = self.project_root / 'temp'
        self.log = self._init_log()
        self.name_cache: Dict[str, str] = {}

    async def __aenter__(self):
        proxy = ''
        try:
            cfg = self._load_config_sync() or {}
            proxy = str(cfg.get('network_proxy') or '').strip()
        except Exception:
            proxy = ''
        kwargs = dict(verify=False, trust_env=True)
        if proxy:
            kwargs['proxy'] = proxy if '://' in proxy else f'http://{proxy}'
        try:
            self.client = httpx.AsyncClient(**kwargs)
        except Exception:
            self.client = httpx.AsyncClient(verify=False, trust_env=True)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def _init_log(self, level=logging.INFO) -> logging.Logger:
        logger = logging.getLogger(' 大轩巴入库器mini')
        logger.setLevel(level)
        if not logger.handlers:
            stream_handler = colorlog.StreamHandler()
            stream_handler.setLevel(level)
            fmt = colorlog.ColoredFormatter(LOG_FORMAT, log_colors=LOG_COLORS)
            stream_handler.setFormatter(fmt)
            logger.addHandler(stream_handler)
        return logger

    def _configure_logger(self):
        if not self.config:
            self.log.warning("无法应用日志配置，因为配置尚未加载。")
            return
        if self.config.get("disable_logging", False):
            level = logging.ERROR
            self.log.setLevel(level)
            for handler in self.log.handlers:
                if isinstance(handler, logging.StreamHandler):
                    handler.setLevel(level)
            self.log.debug("日志输出已按设置关闭（disable_logging）。")
            self.log.handlers = [h for h in self.log.handlers if not isinstance(h, logging.FileHandler)]
            return
        is_debug = self.config.get("debug_mode", False)
        level = logging.DEBUG if is_debug else logging.INFO
        self.log.setLevel(level)
        for handler in self.log.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(level)
        self.log.debug(f"日志等级已设置为: {'DEBUG' if is_debug else 'INFO'}")
        self.log.handlers = [h for h in self.log.handlers if not isinstance(h, logging.FileHandler)]
        if self.config.get("logging_files", True):
            logs_dir = self.project_root / 'logs'
            logs_dir.mkdir(exist_ok=True)
            log_file_path = logs_dir / f'dxb-injector-{time.strftime("%Y-%m-%d")}.log'
            file_handler = logging.FileHandler(log_file_path, 'a', encoding='utf-8')
            file_handler.setLevel(level)
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            file_handler.setFormatter(file_formatter)
            self.log.addHandler(file_handler)
            self.log.info(f"已启用文件日志，将保存到: {log_file_path}")
        else:
            self.log.info("文件日志已禁用。")

    def _compare_versions(self, v1: str, v2: str) -> int:
        """比较版本号，返回 -1, 0, 1"""
        try:
            import re
            
            def parse_version(v):
                match = re.match(r'(\d+(?:\.\d+)*)(.*)', v)
                if not match:
                    return (0, 0, 0), ''
                
                version_nums = match.group(1)
                suffix = match.group(2)
                
                parts = version_nums.split('.')
                while len(parts) < 3:
                    parts.append('0')
                
                version_tuple = tuple(int(p) for p in parts[:3])
                
                return version_tuple, suffix
            
            v1_tuple, v1_suffix = parse_version(v1)
            v2_tuple, v2_suffix = parse_version(v2)
            
            if v1_tuple < v2_tuple:
                return -1
            elif v1_tuple > v2_tuple:
                return 1
            
            if not v1_suffix and v2_suffix:
                return 1
            elif v1_suffix and not v2_suffix:
                return -1
            elif v1_suffix < v2_suffix:
                return -1
            elif v1_suffix > v2_suffix:
                return 1
            
            return 0
            
        except Exception as e:
            self.log.warning(f"版本比较失败: {e}")
            return 0
    
    async def check_for_updates(self) -> Tuple[bool, Dict]:
        """
        检查是否有新版本可用
        返回: (是否有更新, 版本信息字典)
        """
        try:
            self.log.info("正在检查更新...")
            
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            
            github_token = self.config.get("Github_Personal_Token", "").strip()
            headers = {'Authorization': f'Bearer {github_token}'} if github_token else {}
            
            headers['User-Agent'] = 'DaXuanBa-Rukuqi-Updater'
            
            response = await self.client.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 404:
                self.log.info("未找到发布版本")
                return False, {}
            
            response.raise_for_status()
            release_data = response.json()
            
            latest_version = release_data.get('tag_name', '').strip()
            if latest_version.startswith('v'):
                latest_version = latest_version[1:]
            
            release_name = release_data.get('name', '')
            release_body = release_data.get('body', '')
            release_url = release_data.get('html_url', '')
            published_at = release_data.get('published_at', '')
            
            download_urls = []
            assets = release_data.get('assets', [])
            for asset in assets:
                download_urls.append({
                    'name': asset.get('name', ''),
                    'url': asset.get('browser_download_url', ''),
                    'size': asset.get('size', 0)
                })
            
            if not download_urls and release_data.get('zipball_url'):
                download_urls.append({
                    'name': 'Source code (zip)',
                    'url': release_data.get('zipball_url', ''),
                    'size': 0
                })
            
            if self._compare_versions(CURRENT_VERSION, latest_version) < 0:
                self.log.info(f"发现新版本: {latest_version} (当前版本: {CURRENT_VERSION})")
                return True, {
                    'current_version': CURRENT_VERSION,
                    'latest_version': latest_version,
                    'release_name': release_name,
                    'release_body': release_body,
                    'release_url': release_url,
                    'published_at': published_at,
                    'download_urls': download_urls
                }
            else:
                self.log.info(f"当前已是最新版本 ({CURRENT_VERSION})")
                return False, {}
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                self.log.warning("GitHub API 请求次数已用尽，跳过更新检查")
            else:
                self.log.warning(f"检查更新时 HTTP 错误: {e}")
            return False, {}
        except httpx.TimeoutException:
            self.log.warning("检查更新超时，跳过")
            return False, {}
        except Exception as e:
            self.log.warning(f"检查更新失败: {e}")
            return False, {}

    async def check_all_updates(self) -> Dict[str, Any]:
        """一次性「真实」检查更新：应用自身 + 三个内核的远端最新版本，全部并发。

        返回 {'app': {...}, 'kernels': {kind: {...}}, 'checked_at': ts}
        每一项都带 ok / local / remote / has_update，探不到就如实说探不到，
        绝不拿本地版本冒充远端版本。
        """
        import time as _t
        kernels = KernelHub(self)
        kinds = [k for k in KERNEL_SPECS]

        async def _one(kind: str) -> Tuple[str, Dict[str, Any]]:
            try:
                loc = kernels.local_status(kind)
            except Exception as e:
                return kind, {"ok": False, "note": f"本地检测失败：{str(e)[:80]}"}
            try:
                rem = await kernels.remote_latest(kind)
            except Exception as e:
                return kind, {"ok": False, "installed": loc.get("installed", False),
                              "local": loc.get("version", ""), "note": f"远端查询失败：{str(e)[:80]}"}
            local_v = loc.get("version") or ""
            remote_v = rem.get("version") or ""
            upd = False
            if loc.get("installed") and local_v and remote_v:
                upd = self._compare_versions(local_v, remote_v) < 0
            return kind, {
                "ok": bool(rem.get("ok")),
                "installed": bool(loc.get("installed")),
                "builtin": bool(KERNEL_SPECS[kind].get("builtin")),
                "local": local_v,
                "remote": remote_v,
                "has_update": upd,
                "repo": rem.get("repo", ""),
                "url": rem.get("url", ""),
                "note": rem.get("note", ""),
            }

        async def _app() -> Dict[str, Any]:
            try:
                has, info = await self.check_for_updates()
                return {"ok": bool(info), "local": CURRENT_VERSION,
                        "remote": (info or {}).get("latest_version", ""),
                        "has_update": bool(has),
                        "url": (info or {}).get("release_url", ""),
                        "note": "" if has else "已是最新版本"}
            except Exception as e:
                return {"ok": False, "local": CURRENT_VERSION, "remote": "",
                        "has_update": False, "note": f"检查失败：{str(e)[:80]}"}

        app_task = asyncio.ensure_future(_app())
        k_tasks = [asyncio.ensure_future(_one(k)) for k in kinds]
        app_res = await app_task
        k_res = dict(await asyncio.gather(*k_tasks))
        self.log.info("更新检查完成："
                      + ("应用有新版 " + str(app_res.get("remote")) if app_res.get("has_update") else "应用已是最新")
                      + "；内核 " + "、".join(
                          f"{KERNEL_SPECS[k]['name']}{'可更新' if v.get('has_update') else ('已最新' if v.get('ok') else '未取到')}"
                          for k, v in k_res.items()))
        return {"app": app_res, "kernels": k_res, "checked_at": int(_t.time())}

    async def initialize(self) -> Literal["steamtools", "greenluma", "conflict", "none", None]:
        if not self.config: self.config = await self.load_config()
        if self.config is None: return None
        self._configure_logger()
        self._pending_unlocker_install = False

        self.steam_path = self.get_steam_path()
        if not self.steam_path or not self.steam_path.exists():
            self.log.error('无法确定有效的Steam路径。请在设置中手动指定。')
            return None
        self.log.info(f"Steam路径: {self.steam_path}")

        force_unlocker = self.config.get("force_unlocker_type", "auto")

        _plug = self.steam_path / 'config' / 'stplug-in'
        is_steamtools = ((self.steam_path / 'hid.dll').exists() or
                         (_plug.is_dir() and any(_plug.glob('*.lua'))))
        is_greenluma = any((self.steam_path / dll).exists() for dll in [
            'GreenLuma_2025_x86.dll', 'GreenLuma_2025_x64.dll',
            'user32.dll', 'DLLInjector.exe'])
        _lua_dir = self.steam_path / 'config' / 'lua'
        is_opensteamtool = ((self.steam_path / 'OpenSteamTool.dll').exists() or
                            (_lua_dir.is_dir() and any(_lua_dir.glob('*.lua'))))
        self.detected_kernels = {
            'native': True,
            'steamtools': is_steamtools,
            'greenluma': is_greenluma,
            'opensteamtool': is_opensteamtool,
        }

        if force_unlocker in ["steamtools", "greenluma", "opensteamtool", "native"]:
            self.unlocker_type = force_unlocker
            self.log.warning(f"已根据配置强制使用解锁工具: {force_unlocker}")
        else:
            if is_steamtools and is_greenluma:
                self.log.error("环境冲突：同时检测到SteamTools和GreenLuma！请在设置中强制指定一个。")
                self.unlocker_type = "conflict"
            elif is_steamtools:
                self.log.info("自动检测到解锁工具: SteamTools")
                self.unlocker_type = "steamtools"
            elif is_greenluma:
                self.log.info("自动检测到解锁工具: GreenLuma")
                self.unlocker_type = "greenluma"
            elif is_opensteamtool:
                self.log.info("自动检测到解锁工具: OpenSteamTool")
                self.unlocker_type = "opensteamtool"
            else:
                self.log.warning("未能自动检测到解锁工具。")
                if self.config.get("auto_install_unlocker", True):
                    self._pending_unlocker_install = True
                    self.log.info("将在后台自动下载并安装解锁工具...")
                self.unlocker_type = "none"

        try:
            (self.steam_path / 'config' / 'stplug-in').mkdir(parents=True, exist_ok=True)
            (self.steam_path / 'AppList').mkdir(parents=True, exist_ok=True)
            (self.steam_path / 'depotcache').mkdir(parents=True, exist_ok=True)
            (self.steam_path / 'config' / 'depotcache').mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.log.error(f"创建Steam子目录时失败: {e}")

        return self.unlocker_type

    def lua_output_dir(self) -> Path:
        """lua 解锁文件输出目录：opensteamtool -> config/lua；其余 -> config/stplug-in"""
        if getattr(self, 'unlocker_type', None) == 'opensteamtool':
            return self.steam_path / 'config' / 'lua'
        return self.steam_path / 'config' / 'stplug-in'

    async def ensure_unlocker_installed(self) -> str | None:
        """没检测到解锁工具时自动装一个（配置里 unlocker_preference 决定装哪个）。

        统一走「下载管理」那条安装通道：
        · GreenLuma 隐身版 → 直接下载官方 stealth DLL 释放进去，无窗口、无管理员；
        · SteamTools 是安装包型 → **只有管理员才自动装**（/S 静默无窗口）。
          普通权限下不在这里弹安装向导，免得每次启动都蹦一个窗，改为提示去下载管理页手动装。
        """
        pref = self.config.get("unlocker_preference", "greenluma")
        if pref not in KERNEL_SPECS:
            pref = "greenluma"
        spec = KERNEL_SPECS[pref]
        hub = KernelHub(self)
        if spec.get("installer") and not hub._is_admin():
            self.log.warning(
                f"{spec['name']} 是安装包型内核，只有管理员身份才能免窗口静默安装；"
                "普通权限下不自动弹官方安装向导。请到「下载管理」页手动点安装，"
                "或用管理员身份重启本程序。")
            return None
        self.log.info(f"未检测到解锁工具，正在自动下载并安装 {spec['name']} ...")
        try:
            res = await hub.install(pref)
        except Exception as e:
            self.log.error(f"自动安装 {pref} 失败: {self.stack_error(e)}")
            return None
        if res.get("success"):
            self.log.info(f"自动安装完成：{res.get('message')}")
            return pref
        self.log.error(f"自动安装失败：{res.get('message')}")
        return None

    async def _fetch_latest_release_asset(self, repo: str, exts: list) -> Tuple[str, str] | None:
        api = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            github_token = self.config.get("Github_Personal_Token", "").strip()
            headers = {'Authorization': f'Bearer {github_token}'} if github_token else {}
            headers['User-Agent'] = 'DaXuanBa-Injector'
            r = await self.client.get(api, headers=headers, timeout=20)
            r.raise_for_status()
            rel = r.json()
            for a in rel.get('assets', []):
                if any(str(a['name']).lower().endswith(e) for e in exts):
                    return a['browser_download_url'], a['name']
            self.log.warning(f"发布 {rel.get('tag_name')} 中无匹配资产: {exts}")
        except Exception as e:
            self.log.error(f"查询 {repo} 发布失败: {self.stack_error(e)}")
        return None

    async def _fetch_release_tag(self, repo: str) -> str:
        """获取仓库最新发布的 tag（用于写入版本标记）。"""
        api = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            github_token = self.config.get("Github_Personal_Token", "").strip()
            headers = {'Authorization': f'Bearer {github_token}'} if github_token else {}
            headers['User-Agent'] = 'DaXuanBa-Injector'
            r = await self.client.get(api, headers=headers, timeout=20)
            r.raise_for_status()
            return str(r.json().get('tag_name', '')).strip()
        except Exception:
            return ""

    async def _download_and_extract(self, download_url: str, ext_dir: Path) -> bool:
        """下载 zip 并解压到 ext_dir，返回是否成功。"""
        import zipfile
        zpath = self.temp_path / 'dep_extract.zip'
        try:
            data = await self._download_bytes(download_url)
            if not data:
                return False
            self.temp_path.mkdir(parents=True, exist_ok=True)
            zpath.write_bytes(data)
            ext_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(ext_dir)
            return True
        except Exception as e:
            self.log.error(f"下载/解压失败: {self.stack_error(e)}")
            return False
        finally:
            if zpath.exists():
                try:
                    zpath.unlink()
                except Exception:
                    pass

    async def ensure_opensteamtool_installed(self, force: bool = False) -> str | None:
        """从 GitHub 下载/更新 OpenSteamTool 内核（清单导入），并导入检测到的 Steam 主文件夹。
        安装：复制 dwmapi.dll / xinput1_4.dll / OpenSteamTool.dll 到 Steam 根目录，
        并确保 config\\lua 目录存在（lua 配置目录 = 检测到的 Steam 主文件夹下的 lua 目录）。
        """
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            self.log.error("无法确定有效的 Steam 路径，无法安装 OpenSteamTool 内核。")
            return None
        if not force:
            st = self.get_opensteamtool_status()
            if st["installed"]:
                self.log.info("OpenSteamTool 内核已安装，跳过（如需重装请使用强制更新）。")
                return "opensteamtool"
        repo = self.config.get("opensteamtool_repo", "OpenSteam001/OpenSteamTool").strip() or "OpenSteam001/OpenSteamTool"
        self.log.info(f"正在从 GitHub 获取 OpenSteamTool 最新发布（仓库 {repo}）...")
        asset = await self._fetch_latest_release_asset(repo, ['.zip'])
        if not asset:
            self.log.error("获取 OpenSteamTool 发布资产失败。")
            return None
        download_url, asset_name = asset
        ext_dir = self.temp_path / 'opensteamtool_extract'
        if not await self._download_and_extract(download_url, ext_dir):
            return None
        copied = False
        for dll in ext_dir.rglob('OpenSteamTool.dll'):
            shutil.copy2(dll, sp / dll.name)
            copied = True
        for dll in ext_dir.rglob('dwmapi.dll'):
            shutil.copy2(dll, sp / dll.name)
        for dll in ext_dir.rglob('xinput1_4.dll'):
            shutil.copy2(dll, sp / dll.name)
        lua_dir = sp / 'config' / 'lua'
        lua_dir.mkdir(parents=True, exist_ok=True)
        for lua in ext_dir.rglob('*.lua'):
            shutil.copy2(lua, lua_dir / lua.name)
        tag = await self._fetch_release_tag(repo)
        try:
            (sp / 'opensteamtool_version.txt').write_text(tag or asset_name, encoding='utf-8')
        except Exception:
            pass
        shutil.rmtree(ext_dir, ignore_errors=True)
        if copied:
            self.log.info(f"OpenSteamTool 内核已安装到 Steam 根目录（{sp}），lua 目录: {lua_dir}")
            return "opensteamtool"
        self.log.warning("OpenSteamTool 发布包中未找到核心 dll，安装可能不完整。")
        return None

    async def ensure_steamtools_installed(self, force: bool = False) -> str | None:
        """从 GitHub 下载/更新 SteamTools（稳定入库）到 Steam 的 stplug-in 目录。"""
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            self.log.error("无法确定有效的 Steam 路径，无法安装 SteamTools。")
            return None
        if not force:
            st = self.get_steamtools_status()
            if st["installed"]:
                self.log.info("SteamTools 已安装，跳过。")
                return "steamtools"
        repo = self.config.get("steamtools_repo", "SteamTools/STAupdater").strip() or "SteamTools/STAupdater"
        self.log.info(f"正在从 GitHub 获取 SteamTools 最新发布（仓库 {repo}）...")
        asset = await self._fetch_latest_release_asset(repo, ['.zip', '.7z'])
        if not asset:
            self.log.error("获取 SteamTools 发布资产失败。")
            return None
        download_url, asset_name = asset
        ext_dir = self.temp_path / 'steamtools_extract'
        ok = False
        if asset_name.lower().endswith('.zip'):
            ok = await self._download_and_extract(download_url, ext_dir)
        if not ok:
            self.log.warning("SteamTools 发布资产非 zip 或解压失败，请前往设置页使用官方安装包手动安装。")
            shutil.rmtree(ext_dir, ignore_errors=True)
            return None
        dst = sp / 'config' / 'stplug-in'
        dst.mkdir(parents=True, exist_ok=True)
        for item in ext_dir.rglob('*'):
            if item.is_file():
                shutil.copy2(item, dst / item.name)
        tag = await self._fetch_release_tag(repo)
        try:
            (sp / 'steamtools_version.txt').write_text(tag or asset_name, encoding='utf-8')
        except Exception:
            pass
        shutil.rmtree(ext_dir, ignore_errors=True)
        self.log.info(f"SteamTools 已释放到 {dst}，请按官方指引完成注册。")
        return "steamtools"

    async def _download_and_extract_any(self, download_url: str, asset_name: str, ext_dir: Path) -> bool:
        """下载发布资产并解压到 ext_dir：zip 走内置 zipfile，7z 走 py7zr（可选依赖）。"""
        import zipfile
        zpath = self.temp_path / (asset_name or 'dep_asset.zip')
        try:
            data = await self._download_bytes(download_url)
            if not data:
                return False
            self.temp_path.mkdir(parents=True, exist_ok=True)
            zpath.write_bytes(data)
            ext_dir.mkdir(parents=True, exist_ok=True)
            low = (asset_name or '').lower()
            if low.endswith('.7z'):
                try:
                    import py7zr
                except Exception:
                    self.log.warning("发布包是 7z 但缺少 py7zr，无法自动解压，请手动安装。")
                    return False
                with py7zr.SevenZipFile(zpath, 'r') as z:
                    z.extractall(ext_dir)
                return True
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(ext_dir)
            return True
        except Exception as e:
            self.log.error(f"下载/解压失败: {self.stack_error(e)}")
            return False
        finally:
            if zpath.exists():
                try:
                    zpath.unlink()
                except Exception:
                    pass

    async def ensure_greenluma_installed(self, force: bool = False) -> str | None:
        """从 GitHub 下载/更新 GreenLuma（DLL 注入入库）到 Steam 根目录。

        GreenLuma 2025 的 DLL 需与 steam.exe 同目录（Steam 根目录），
        解锁目标由同目录 AppList\\*.txt 决定；这里把包内 AppList 一并释放。
        """
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            self.log.error("无法确定有效的 Steam 路径，无法安装 GreenLuma。")
            return None
        if not force:
            st = self.get_greenluma_status()
            if st["installed"]:
                self.log.info("GreenLuma 已安装，跳过（如需重装请使用强制更新）。")
                return "greenluma"
        repo = self.greenluma_repo()
        if not repo:
            self.log.warning(
                "未配置 GreenLuma 仓库（greenluma_repo 为空）。"
                "GreenLuma 官方只在 cs.rin.ru 论坛发布，程序不会去猜下载源："
                f"请到官方页手动下载后把 DLL 放到 Steam 根目录，或填入自己的镜像仓库。官方页：{GREENLUMA_OFFICIAL_URL}")
            return None
        self.log.info(f"正在从 GitHub 获取 GreenLuma 最新发布（仓库 {repo}）...")
        asset = await self._fetch_latest_release_asset(repo, ['.zip', '.7z', '.exe'])
        if not asset:
            self.log.error(f"仓库 {repo} 没有可用的发布资产（.zip / .7z / .exe）。"
                           f"请改用 GreenLuma 官方发布页手动安装：{GREENLUMA_OFFICIAL_URL}")
            return None
        download_url, asset_name = asset

        if asset_name.lower().endswith('.exe'):
            data = await self._download_bytes(download_url)
            if not data:
                self.log.error("下载 GreenLuma.exe 失败。")
                return None
            try:
                (sp / 'GreenLuma.exe').write_bytes(data)
            except Exception as e:
                self.log.error(f"写入 GreenLuma.exe 失败: {e}")
                return None
            try:
                (sp / 'AppList').mkdir(exist_ok=True)
            except Exception:
                pass
            try:
                tag = await self._fetch_release_tag(repo)
                (sp / 'greenluma_version.txt').write_text(tag or asset_name, encoding='utf-8')
            except Exception:
                pass
            self.log.info(f"GreenLuma.exe 已安装到 {sp}（运行它即可注入解锁）。")
            return "greenluma"

        ext_dir = self.temp_path / 'greenluma_extract'
        if not await self._download_and_extract_any(download_url, asset_name, ext_dir):
            self.log.warning("GreenLuma 发布包下载/解压失败，请前往设置页手动下载安装。")
            shutil.rmtree(ext_dir, ignore_errors=True)
            return None

        copied: List[str] = []
        for dll in sorted(ext_dir.rglob('GreenLuma_2025_*.dll')):
            try:
                shutil.copy2(dll, sp / dll.name)
                copied.append(dll.name)
            except Exception as e:
                self.log.error(f"释放 {dll.name} 失败: {e}")
        if not copied:
            for dll in sorted(ext_dir.rglob('*.dll')):
                if 'greenluma' in dll.name.lower():
                    try:
                        shutil.copy2(dll, sp / dll.name)
                        copied.append(dll.name)
                    except Exception:
                        pass
        if not copied:
            self.log.error("发布包中未找到 GreenLuma DLL。")
            shutil.rmtree(ext_dir, ignore_errors=True)
            return None

        for extra in ('AppList', 'AppList_x64'):
            src_d = ext_dir / extra
            if src_d.is_dir():
                try:
                    shutil.copytree(src_d, sp / extra, dirs_exist_ok=True)
                    self.log.info(f"已释放 {extra} 目录到 Steam 根目录。")
                except Exception as e:
                    self.log.warning(f"释放 {extra} 失败: {e}")
        for pat in ('GreenLuma*.exe', 'DLLInjector*.exe', '*.ini'):
            for f in sorted(ext_dir.glob(pat)):
                try:
                    shutil.copy2(f, sp / f.name)
                except Exception:
                    pass
        try:
            (sp / 'AppList').mkdir(exist_ok=True)
        except Exception:
            pass

        tag = await self._fetch_release_tag(repo)
        try:
            (sp / 'greenluma_version.txt').write_text(tag or asset_name, encoding='utf-8')
        except Exception:
            pass
        shutil.rmtree(ext_dir, ignore_errors=True)
        self.log.info(f"GreenLuma 已安装到 {sp}：{', '.join(copied)}")
        return "greenluma"

    async def _download_bytes(self, url: str) -> bytes | None:
        try:
            r = await self.client.get(url, timeout=120, follow_redirects=True)
            r.raise_for_status()
            return r.content
        except Exception as e:
            self.log.error(f"下载失败: {self.stack_error(e)}")
            return None

    def stack_error(self, exception: Exception) -> str:
        return ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))

    async def gen_config_file(self):
        config_path = self.project_root / 'config.json'
        try:
            config_path.parent.mkdir(exist_ok=True, parents=True)
        
            with open(config_path, mode="w", encoding="utf-8") as f:
                f.write(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))
            self.log.info('未识别到config.json，可能为首次启动，已自动生成，若进行配置重启生效')
        except Exception as e:
            self.log.error(f'生成配置文件失败: {self.stack_error(e)}')
    
    @staticmethod
    def _migrate_config(config: Dict) -> Dict:
        """老配置的一次性迁移（就地改 dict 并返回）。

        v2.17：以前 auto_install_unlocker 默认是开的 —— 启动时只要没检测到内核，程序就会
        擅自往 Steam 客户端目录写 DLL（GreenLuma 隐身版是改写版 user32.dll，
        OpenSteamTool / SteamTools 是代理 DLL）。这些 DLL 一旦跟当前 Steam 客户端构建对不上，
        Steam 就会起不来（实测踩过）。所以：老配置里没有 ack 标记的一律先关掉；
        用户到设置页自己勾上并保存时，`/api/config/update` 会打上 ack，之后尊重他的选择。
        """
        if config.get('auto_install_unlocker') and not config.get('auto_install_unlocker_ack'):
            config['auto_install_unlocker'] = False
        return config

    async def load_config(self) -> Dict | None:
        config_path = self.project_root / 'config.json'
        if not config_path.exists():
            await self.gen_config_file()
            return DEFAULT_CONFIG

        try:
            async with aiofiles.open(config_path, mode="r", encoding="utf-8") as f:
                user_config = json.loads(await f.read())
                config = DEFAULT_CONFIG.copy()
                config.update(user_config)
                
                if 'Custom_Repos' not in config:
                    config['Custom_Repos'] = {"github": [], "zip": []}
                elif not isinstance(config['Custom_Repos'], dict):
                    config['Custom_Repos'] = {"github": [], "zip": []}
                else:
                    if 'github' not in config['Custom_Repos']:
                        config['Custom_Repos']['github'] = []
                    if 'zip' not in config['Custom_Repos']:
                        config['Custom_Repos']['zip'] = []

                return self._migrate_config(config)
        except Exception as e:
            self.log.error(f"加载配置文件失败: {self.stack_error(e)}。正在重置配置文件...")
            if config_path.exists(): os.remove(config_path)
            await self.gen_config_file()
            self.log.error("配置文件已损坏并被重置。请重启程序。")
            return None

    def _load_config_sync(self) -> Dict:
        """同步加载配置（供非异步路由使用）。"""
        config_path = self.project_root / 'config.json'
        if not config_path.exists():
            return DEFAULT_CONFIG.copy()
        try:
            with open(config_path, mode="r", encoding="utf-8") as f:
                user_config = json.loads(f.read())
            config = DEFAULT_CONFIG.copy()
            config.update(user_config)
            if 'Custom_Repos' not in config or not isinstance(config['Custom_Repos'], dict):
                config['Custom_Repos'] = {"github": [], "zip": []}
            else:
                config['Custom_Repos'].setdefault('github', [])
                config['Custom_Repos'].setdefault('zip', [])
            return self._migrate_config(config)
        except Exception:
            return DEFAULT_CONFIG.copy()

    def _save_config_sync(self, config: Dict) -> None:
        """同步保存配置（供非异步路由使用）。"""
        config_path = self.project_root / 'config.json'
        with open(config_path, mode="w", encoding="utf-8") as f:
            f.write(json.dumps(config, ensure_ascii=False, indent=2))

    def get_steam_path(self) -> Path | None:
        """定位 Steam 安装目录。多路探测，任一命中即可：
        自定义路径 → 注册表(HKCU/HKLM 32+64) → 常见默认位置。
        单一来源失败就整体“识别不出来”，所以必须逐个兜底。"""
        try:
            custom = str(self.config.get("Custom_Steam_Path") or "").strip()
            if custom:
                p = Path(custom)
                if p.exists():
                    return p
                self.log.warning(f"配置里的 Steam 路径不存在：{custom}，继续自动探测。")
        except Exception:
            pass
        for cand in self._steam_registry_paths():
            try:
                p = Path(cand)
                if p.exists():
                    return p
            except Exception:
                continue
        for cand in (r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam',
                     r'D:\Steam', r'E:\Steam', r'D:\Program Files (x86)\Steam'):
            try:
                p = Path(cand)
                if (p / 'steam.exe').exists():
                    return p
            except Exception:
                continue
        self.log.error('获取Steam路径失败。请检查Steam是否正确安装，或在设置页手动指定 Steam 路径。')
        return None

    def steam_account(self) -> Dict[str, Any]:
        """返回 {logged_in, steamid64, accountid, steam3, persona, avatar_path, most_recent}"""
        out = {"logged_in": False, "steamid64": "", "accountid": "", "steam3": "",
               "persona": "", "avatar_path": "", "most_recent": False}
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            out["error"] = "没有检测到 Steam 目录"
            return out
        lf = sp / 'config' / 'loginusers.vdf'
        if not lf.exists():
            out["error"] = f"没有 {lf}（Steam 从没登录过这台机器？）"
            return out
        try:
            data = vdf.loads(lf.read_text(encoding='utf-8', errors='ignore'))
        except Exception as e:
            out["error"] = f"解析 loginusers.vdf 失败：{e}"
            return out
        users = data.get('users') or {}
        best = None
        for key, u in users.items():
            if not isinstance(u, dict):
                continue
            sid64 = str(u.get('Steam64') or u.get('steamid64') or '')
            if not sid64 and str(key).isdigit():
                sid64 = str(key)
            try:
                acc = int(u.get('AccountID') or u.get('accountid') or 0)
            except Exception:
                acc = 0
            if best is None or (u.get('MostRecent') in (1, '1', True)
                                and not best.get('_recent')):
                best = dict(u); best['_recent'] = u.get('MostRecent') in (1, '1', True)
                best['_sid64'] = sid64; best['_acc'] = acc
        if not best:
            out["error"] = "loginusers.vdf 里没有账号记录"
            return out
        sid64 = best.get('_sid64', '')
        acc = best.get('_acc', 0)
        out.update({
            "logged_in": True,
            "steamid64": sid64,
            "accountid": str(acc),
            "steam3": str(acc) if acc else "",
            "persona": str(best.get('PersonaName') or ''),
            "most_recent": bool(best.get('_recent')),
        })
        if sid64:
            av = sp / 'config' / 'avatarcache' / f'{sid64}.png'
            if av.exists():
                out["avatar_path"] = str(av)
        if not out["avatar_path"] and acc:
            cands = sorted((sp / 'userdata').glob(f'{acc}*')) if (sp / 'userdata').is_dir() else []
            if cands:
                out["userdata_dir"] = str(cands[0])
        return out

    def get_steam_status(self) -> Dict:
        """检测 Steam 路径与已安装内核，供首页状态条显示。
        kernel: steamtools(稳定入库) / greenluma(DLL注入) / opensteamtool(清单导入) / none
        注意：OpenSteamTool 实际把 lua 放在 Steam 根目录的 config\\lua\\，
        内核 dll(OpenSteamTool.dll/dwmapi.dll/xinput1_4.dll) 也在 Steam 根目录。
        """
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            return {"steam_path": None, "exists": False, "kernel": "none",
                    "steamtools": False, "greenluma": False, "opensteamtool": False}
        is_steamtools = (sp / 'config' / 'stplug-in').is_dir()
        is_greenluma = any(sp.glob('GreenLuma*.dll'))
        is_opensteamtool = (sp / 'OpenSteamTool.dll').exists() or (sp / 'config' / 'lua').is_dir()
        if is_steamtools:
            kernel = "steamtools"
        elif is_greenluma:
            kernel = "greenluma"
        elif is_opensteamtool:
            kernel = "opensteamtool"
        else:
            kernel = "none"
        return {
            "steam_path": str(sp), "exists": True, "kernel": kernel,
            "steamtools": is_steamtools, "greenluma": is_greenluma, "opensteamtool": is_opensteamtool
        }

    def get_opensteamtool_status(self) -> Dict:
        """检测 OpenSteamTool 内核（清单导入）状态，供设置页依赖卡片显示。"""
        sp = self.get_steam_path()
        installed = False
        version = ""
        lua_dir = None
        if sp and sp.exists():
            lua_dir = sp / 'config' / 'lua'
            installed = (sp / 'OpenSteamTool.dll').exists() or (lua_dir.is_dir() and any(lua_dir.glob('*.lua')))
            vf = sp / 'opensteamtool_version.txt'
            if vf.exists():
                try:
                    version = vf.read_text(encoding='utf-8').strip()
                except Exception:
                    version = ""
        return {"steam_path": str(sp) if sp else None, "installed": installed, "version": version,
                "lua_dir": str(lua_dir) if lua_dir else None}

    def get_steamtools_status(self) -> Dict:
        """检测 SteamTools（稳定入库）状态，供设置页依赖卡片显示。"""
        sp = self.get_steam_path()
        installed = False
        version = ""
        if sp and sp.exists():
            st = sp / 'config' / 'stplug-in'
            installed = st.is_dir() and any(st.glob('*.lua'))
            vf = sp / 'steamtools_version.txt'
            if vf.exists():
                try:
                    version = vf.read_text(encoding='utf-8').strip()
                except Exception:
                    version = ""
        return {"steam_path": str(sp) if sp else None, "installed": installed, "version": version}

    def get_greenluma_status(self) -> Dict:
        """检测 GreenLuma（DLL 注入入库）状态，供设置页依赖卡片显示。"""
        sp = self.get_steam_path()
        installed = False
        version = ""
        dlls: List[str] = []
        applist = None
        gl_exe = None
        applist_count = 0
        if sp and sp.exists():
            for d in sorted(sp.glob('GreenLuma*.dll')):
                dlls.append(d.name)
            if (sp / 'GreenLuma.exe').exists():
                gl_exe = str(sp / 'GreenLuma.exe')
            installed = bool(dlls) or bool(gl_exe)
            ad = sp / 'AppList'
            if ad.is_dir():
                applist = str(ad)
                try:
                    applist_count = sum(1 for _ in ad.glob('*.txt'))
                except Exception:
                    applist_count = 0
            vf = sp / 'greenluma_version.txt'
            if vf.exists():
                try:
                    version = vf.read_text(encoding='utf-8').strip()
                except Exception:
                    version = ""
        repo = self.greenluma_repo()
        return {"steam_path": str(sp) if sp else None, "installed": installed,
                "version": version, "dlls": dlls, "exe": gl_exe,
                "applist_dir": applist, "applist_count": applist_count,
                "repo": repo, "manual_only": not repo,
                "official_url": GREENLUMA_OFFICIAL_URL}

    _NON_GAME_APPIDS = {
        '228980',
        '1070560', '1391110', '1628350',
    }

    def _steam_library_roots(self, sp: Path) -> List[Path]:
        """返回所有 Steam 库根目录：主目录 + libraryfolders.vdf 里登记的其他盘。
        用户经常把游戏装在 D 盘等别处，只扫主 steamapps 会“识别不出来”。"""
        roots: List[Path] = []

        def _add(p):
            if not p:
                return
            try:
                pth = Path(str(p))
            except Exception:
                return
            if pth not in roots:
                roots.append(pth)

        _add(sp)
        for lf in (sp / 'steamapps' / 'libraryfolders.vdf', sp / 'config' / 'libraryfolders.vdf'):
            if not lf.exists():
                continue
            try:
                data = vdf.loads(lf.read_text(encoding='utf-8', errors='ignore'))
            except Exception as e:
                self.log.warning(f"解析 {lf.name} 失败: {e}")
                continue
            libs = data.get('libraryfolders') or data.get('LibraryFolders') or {}
            if isinstance(libs, dict):
                for _, info in libs.items():
                    if isinstance(info, dict):
                        _add(info.get('path') or info.get('Path'))
                    elif isinstance(info, str):
                        _add(info)
            break
        return roots

    def _scan_installed_manifests(self, sp: Path) -> Dict[str, Dict]:
        """扫描所有库目录的 appmanifest_*.acf → {appid: {name, library}}"""
        found: Dict[str, Dict] = {}
        for root in self._steam_library_roots(sp):
            sa = root / 'steamapps'
            if not sa.is_dir():
                continue
            for f in sa.glob('appmanifest_*.acf'):
                try:
                    data = vdf.loads(f.read_text(encoding='utf-8', errors='ignore')).get('AppState', {})
                    appid = str(data.get('appid', '')).strip()
                    if not appid.isdigit():
                        continue
                    found.setdefault(appid, {
                        "name": (data.get('name') or '').strip() or f'App {appid}',
                        "library": str(root),
                    })
                except Exception as e:
                    self.log.warning(f"解析 {f.name} 失败: {e}")
        return found

    def installed_games_tree(self) -> Dict:
        """真实扫描 Steam 已装应用（appmanifest），把 DLC 归入各自游戏下。
        返回 {games:[{appid,name,dlcs:[{appid,name}]}], others:[...], total, dlc_total}。"""
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "未找到 Steam 路径，请在设置里指定 Steam 目录。",
                    "games": [], "others": [], "total": 0, "dlc_total": 0,
                    "libraries": self._steam_registry_paths(),
                    "hint": "自动探测没找到 Steam。请到「设置」页填写 Steam 安装目录（例如 D:\\Steam）。"}
        roots = self._steam_library_roots(sp)
        installed = self._scan_installed_manifests(sp)
        if not installed:
            return {"success": True, "games": [], "others": [], "total": 0, "dlc_total": 0,
                    "message": "未检测到已安装的应用。", "steam_path": str(sp),
                    "libraries": [str(r) for r in roots],
                    "hint": ("已扫描的库目录：" + "；".join(str(r) for r in roots) +
                             "。如果 Steam 里明明装了游戏，请检查：① 游戏是否装在别的盘"
                             "（正常情况下本程序会自动读取 libraryfolders.vdf）；"
                             "② 是否有权限读取（试试用管理员身份运行）；"
                             "③ 到「设置」页手动指定 Steam 路径。")}

        appids = list(installed.keys())
        details: Dict[str, Dict] = {}
        try:
            from concurrent.futures import ThreadPoolExecutor
            workers = min(8, max(1, len(appids)))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for aid, d in zip(appids, ex.map(self._steam_appdetails_one, appids)):
                    if d:
                        details[aid] = d
        except Exception as e:
            self.log.warning(f"查询商店详情失败: {e}")

        games = []
        dlcs = {}
        others = []
        for appid, meta in installed.items():
            d = details.get(appid, {})
            name = d.get('name') or meta['name']
            fgame = d.get('fullgame')
            gtype = (d.get('type') or '').lower()
            if fgame and str(fgame.get('appid')) != appid:
                dlcs.setdefault(str(fgame.get('appid')), []).append({"appid": appid, "name": name})
            elif gtype in ('game', 'application', 'demo'):
                games.append({"appid": appid, "name": name, "dlcs": []})
            elif not d:
                if appid in self._NON_GAME_APPIDS:
                    others.append({"appid": appid, "name": name})
                else:
                    games.append({"appid": appid, "name": name, "dlcs": []})
            else:
                others.append({"appid": appid, "name": name})

        dlc_count = 0
        for g in games:
            owned = dlcs.get(g['appid'], [])
            g['dlcs'] = owned
            dlc_count += len(owned)
        parented = {g['appid'] for g in games}
        for parent, lst in dlcs.items():
            if parent not in parented:
                others.extend(lst)

        games.sort(key=lambda x: x['name'].lower())
        others.sort(key=lambda x: x['name'].lower())
        return {"success": True, "games": games, "others": others,
                "total": len(games), "dlc_total": dlc_count,
                "steam_path": str(sp), "libraries": [str(r) for r in roots]}

    _ACF_ACTIVE_BITS = (256 | 1024 | 2048 | 32768 | 65536 | 131072 | 262144 | 524288 | 1048576)
    _ACF_STATE_TEXT = [
        (2048, '正在卸载'), (262144, '正在下载'), (524288, '正在安装'),
        (65536, '正在写入文件'), (131072, '正在预分配'), (32768, '正在校验文件'),
        (1048576, '正在提交'), (256, '正在更新'), (2, '等待更新'),
        (128, '文件损坏，需校验'), (32, '文件缺失，需校验'),
        (4, '已安装'), (1, '未安装'),
    ]

    def _read_acf(self, path: Path) -> Dict:
        try:
            data = vdf.loads(path.read_text(encoding='utf-8', errors='ignore'))
            return data.get('AppState', {}) or {}
        except Exception as e:
            self.log.warning(f"解析 {path.name} 失败: {e}")
            return {}

    def _state_text(self, flags: int) -> str:
        for bit, text in self._ACF_STATE_TEXT:
            if flags & bit:
                return text
        return '未知状态'

    @staticmethod
    def _to_int(v) -> int:
        try:
            return int(str(v or 0).strip() or 0)
        except Exception:
            return 0

    def steam_downloads(self) -> Dict:
        """下载管理：汇总所有 Steam 库的下载 / 更新 / 已安装条目。

        权威数据源是 steamapps/appmanifest_*.acf（含状态位和已下载字节数），
        再用 steamapps/downloading/<appid>/ 目录是否还在来佐证“正在下载”。
        """
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "未找到 Steam 路径，请在设置里指定。",
                    "active": [], "done": [], "total": 0, "active_total": 0}
        items: List[Dict] = []
        seen = set()
        for root in self._steam_library_roots(sp):
            sa = root / 'steamapps'
            if not sa.is_dir():
                continue
            downloading = set()
            dl_dir = sa / 'downloading'
            if dl_dir.is_dir():
                try:
                    downloading = {p.name for p in dl_dir.iterdir() if p.is_dir() and p.name.isdigit()}
                except Exception:
                    downloading = set()
            for f in sa.glob('appmanifest_*.acf'):
                data = self._read_acf(f)
                appid = str(data.get('appid') or '').strip()
                if not appid.isdigit() or appid in seen:
                    continue
                seen.add(appid)
                flags = self._to_int(data.get('StateFlags'))
                done_b = self._to_int(data.get('BytesDownloaded'))
                total_b = self._to_int(data.get('BytesToDownload'))
                staged = self._to_int(data.get('BytesStaged'))
                to_stage = self._to_int(data.get('BytesToStage'))
                size_disk = self._to_int(data.get('SizeOnDisk'))
                installed = bool(flags & 4)
                is_active = bool(flags & self._ACF_ACTIVE_BITS) \
                    or (bool(flags & 2) and not installed) \
                    or (appid in downloading)
                if flags & 524288 and to_stage > 0:
                    cur, tot = staged, to_stage
                else:
                    cur, tot = done_b, total_b
                if tot <= 0:
                    tot = size_disk
                    cur = size_disk if installed else 0
                if installed and not is_active:
                    percent = 100.0
                    cur = tot = max(tot, size_disk)
                else:
                    percent = round(cur * 100.0 / tot, 1) if tot > 0 else 0.0
                items.append({
                    "appid": appid,
                    "name": (data.get('name') or f'App {appid}').strip() or f'App {appid}',
                    "library": str(root),
                    "installdir": (data.get('installdir') or '').strip(),
                    "state_flags": flags,
                    "state_text": self._state_text(flags),
                    "active": is_active,
                    "installed": installed,
                    "bytes_done": cur,
                    "bytes_total": tot,
                    "size_on_disk": size_disk,
                    "percent": percent,
                    "in_downloading": appid in downloading,
                })
        active = sorted([i for i in items if i['active']], key=lambda x: x['name'].lower())
        done_all = [i for i in items if not i['active']]
        runtime = sorted([i for i in done_all if i['appid'] in self._NON_GAME_APPIDS],
                         key=lambda x: x['name'].lower())
        done = sorted([i for i in done_all if i['appid'] not in self._NON_GAME_APPIDS],
                      key=lambda x: (-x['size_on_disk'], x['name'].lower()))
        return {"success": True, "active": active, "done": done[:300], "runtime": runtime,
                "total": len(items), "active_total": len(active), "steam_path": str(sp)}

    def steam_discard_download(self, appid: str) -> Dict:
        """移除一个下载任务：备份 acf → 删半成品缓存 → 删 acf。

        只动「下载中的半成品」（steamapps/downloading/<appid> 与对应 manifest），
        不碰任何已安装的游戏文件；被删的 acf 会备份到 userdata/download_backup/
        以便回退。要彻底取消建议优先用 Steam 自带的取消按钮。
        """
        appid = str(appid or '').strip()
        if not appid.isdigit():
            return {"success": False, "message": "无效的 AppID。"}
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "未找到 Steam 路径。"}
        backup_dir = self.project_root / 'userdata' / 'download_backup'
        removed_files, removed_dirs = [], []
        for root in self._steam_library_roots(sp):
            sa = root / 'steamapps'
            if not sa.is_dir():
                continue
            dl = sa / 'downloading' / appid
            if dl.is_dir():
                try:
                    shutil.rmtree(dl)
                    removed_dirs.append(str(dl))
                except Exception as e:
                    self.log.warning(f"删除下载缓存失败 {dl}: {e}")
            acf = sa / f'appmanifest_{appid}.acf'
            if acf.exists():
                try:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(acf, backup_dir / f'appmanifest_{appid}.acf')
                    acf.unlink()
                    removed_files.append(str(acf))
                except Exception as e:
                    self.log.warning(f"移除 {acf.name} 失败: {e}")
        if not removed_files and not removed_dirs:
            return {"success": False, "message": "没找到该任务的下载缓存或清单，可能 Steam 已经处理过了。"}
        return {"success": True,
                "message": "已移除下载任务。回到 Steam 下载页刷新即可（清单已备份，可回退）。",
                "removed_files": removed_files, "removed_dirs": removed_dirs,
                "backup_dir": str(backup_dir)}

    def _steam_registry_paths(self) -> List[str]:
        """从注册表挖 Steam 安装路径（HKCU 主 + HKLM 32/64 位兜底）。"""
        out: List[str] = []
        probes = [
            (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath'),
        ]
        for hive, sub, name in probes:
            try:
                k = winreg.OpenKey(hive, sub)
                v, _ = winreg.QueryValueEx(k, name)
                winreg.CloseKey(k)
                if v and str(v) not in out:
                    out.append(str(v))
            except Exception:
                continue
        return out

    def _steam_running(self) -> bool:
        """Steam 客户端进程是否在跑。"""
        if sys.platform != 'win32':
            return False
        try:
            kw = {'creationflags': 0x08000000} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
            r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq steam.exe', '/NH'],
                               capture_output=True, text=True, timeout=15,
                               encoding='gbk', errors='ignore', **kw)
            return 'steam.exe' in (r.stdout or '').lower()
        except Exception:
            return False

    @staticmethod
    def fmt_size(n: int) -> str:
        try:
            n = float(n)
        except Exception:
            return '0 B'
        for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
            if n < 1024 or unit == 'TB':
                return f'{n:.1f} {unit}' if unit != 'B' else f'{int(n)} B'
            n /= 1024.0
        return f'{n:.1f} TB'

    @staticmethod
    def _dir_size(path: Path, budget: float = 1.2) -> int:
        """统计目录体积，带时间预算，避免大目录卡住接口。"""
        total = 0
        deadline = time.time() + budget
        try:
            for p in path.rglob('*'):
                if time.time() > deadline:
                    break
                try:
                    if p.is_file():
                        total += p.stat().st_size
                except Exception:
                    continue
        except Exception:
            pass
        return total

    def _hosts_steam_entries(self) -> List[str]:
        """找 hosts 里屏蔽 Steam 域名的行（加速器/管家改过就会命中）。"""
        p = Path(r'C:\Windows\System32\drivers\etc\hosts')
        hits: List[str] = []
        if not p.exists():
            return hits
        try:
            for line in p.read_text(encoding='utf-8', errors='ignore').splitlines():
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                if 'steam' in s.lower():
                    hits.append(s)
        except Exception:
            pass
        return hits

    def _net_probe(self, url: str, timeout: float = 6.0) -> bool:
        try:
            import httpx as _httpx
            with _httpx.Client(verify=False, timeout=timeout, trust_env=True) as c:
                r = c.get(url)
                return r.status_code < 500
        except Exception:
            return False


    @property
    def _hosts_file(self) -> Path:
        return Path(r'C:\Windows\System32\drivers\etc\hosts')

    @staticmethod
    def is_admin() -> bool:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    _DEAD_GREENLUMA_REPOS = {
        'wintersamza/greenluma_2025', 'wintersamza/greenluma', 'greenluma/2025',
        'greenluma_2025/greenluma_2025',
    }

    def greenluma_repo(self) -> str:
        """返回有效的 GreenLuma 镜像仓库；未配置（或配置的是已知失效默认值）返回 ''。"""
        repo = (self.config.get('greenluma_repo') or '').strip()
        if repo.lower() in self._DEAD_GREENLUMA_REPOS:
            return ''
        return repo

    def _read_hosts(self) -> str:
        """surrogateescape 保证读→写能字节级还原，不会弄坏 hosts 里原有的中文注释。"""
        try:
            return self._hosts_file.read_text(encoding='utf-8', errors='surrogateescape')
        except Exception:
            return ''

    def _write_hosts(self, text: str) -> None:
        self._hosts_file.write_text(text, encoding='utf-8', errors='surrogateescape')

    def _hosts_writable(self) -> bool:
        try:
            with open(self._hosts_file, 'a', encoding='utf-8', errors='surrogateescape'):
                pass
            return True
        except Exception:
            return False

    def _hosts_accel_block(self, begin: str = None, end: str = None) -> Dict[str, str]:
        """读 hosts 里某分类的加速块 → {domain: ip}。begin/end 传分类专属标记。"""
        begin = begin or HOSTS_ACCEL_BEGIN
        end = end or HOSTS_ACCEL_END
        out: Dict[str, str] = {}
        inside = False
        try:
            for line in self._read_hosts().splitlines():
                s = line.strip()
                if s == begin:
                    inside = True
                    continue
                if s == end:
                    inside = False
                    continue
                if not inside or not s or s.startswith('#'):
                    continue
                parts = s.split()
                if len(parts) >= 2:
                    for d in parts[1:]:
                        out[d.lower()] = parts[0]
        except Exception:
            pass
        return out

    def _drop_accel_block(self, text: str, begin: str = None, end: str = None) -> str:
        begin = begin or HOSTS_ACCEL_BEGIN
        end = end or HOSTS_ACCEL_END
        kept, inside = [], False
        for line in text.splitlines():
            s = line.strip()
            if s == begin:
                inside = True
                continue
            if s == end:
                inside = False
                continue
            if not inside:
                kept.append(line)
        return '\n'.join(kept).rstrip('\r\n') + '\n'

    def _flush_dns(self) -> bool:
        try:
            r = subprocess.run(['ipconfig', '/flushdns'], capture_output=True, timeout=20,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return r.returncode == 0
        except Exception:
            return False

    def _doh_query(self, provider: str, domain: str, timeout: float = 4.0) -> List[str]:
        """DoH（dns-json）查 A 记录，绕开被污染的系统 DNS。"""
        try:
            with httpx.Client(verify=False, timeout=timeout, trust_env=True) as c:
                r = c.get(provider, params={'name': domain, 'type': 'A'},
                          headers={'accept': 'application/dns-json'})
                if r.status_code != 200:
                    return []
                out = []
                for a in (r.json().get('Answer') or []):
                    try:
                        if int(a.get('type', 0)) != 1:
                            continue
                    except Exception:
                        continue
                    ip = str(a.get('data') or '').strip()
                    if ip.count('.') == 3 and all(x.isdigit() for x in ip.split('.')):
                        out.append(ip)
                return out
        except Exception:
            return []

    @staticmethod
    def _system_resolve(domain: str) -> List[str]:
        try:
            infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
            return sorted({i[4][0] for i in infos if ':' not in i[4][0]})
        except Exception:
            return []

    @staticmethod
    def _is_local_ip(ip: str) -> bool:
        """回环 / 内网 / 链路本地地址。这类解析结果说明域名被本地反代接管了，
        不能当加速目标写进 hosts（写进去等于把流量导回本机，绕死）。"""
        ip = (ip or '').strip()
        if not ip:
            return True
        if ':' in ip:
            return True
        p = ip.split('.')
        if len(p) != 4:
            return True
        try:
            a, b = int(p[0]), int(p[1])
        except Exception:
            return True
        return (a == 127 or a == 0 or a == 10 or a == 169 and b == 254
                or a == 192 and b == 168
                or a == 172 and 16 <= b <= 31)

    def _detect_local_accel(self) -> Dict:
        """检测本机是否已有「本地反代型」Steam 加速器在跑（Steam 社区 302 / Steam++ / Watt Toolkit 等）。
        它们把 Steam 域名解析到 127.0.0.1 并在本地 443 监听，与 hosts 优选方案互斥。"""
        info = {'active': False, 'process': None, 'pid': None, 'domains': []}
        all_domains = []
        for cat in ACCEL_CATEGORIES.values():
            all_domains += [t[0] for t in cat['domains']]
        for d in all_domains:
            try:
                ips = {i[4][0] for i in socket.getaddrinfo(d, 443, proto=socket.IPPROTO_TCP)}
            except Exception:
                continue
            if any(self._is_local_ip(x) for x in ips):
                info['domains'].append(d)
        info['active'] = bool(info['domains'])
        if not info['active']:
            return info

        enc = locale.getpreferredencoding(False)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=20,
                               encoding=enc, errors='ignore', creationflags=flags)
            pid = None
            for line in (r.stdout or '').splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0].upper().startswith('TCP') \
                        and parts[1].startswith('127.0.0.1:443') and parts[3] == 'LISTENING':
                    pid = parts[4]
                    break
            if pid:
                info['pid'] = pid
                r2 = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                                    capture_output=True, timeout=20, encoding=enc,
                                    errors='ignore', creationflags=flags)
                txt = (r2.stdout or '').strip()
                if txt and 'No tasks' not in txt:
                    info['process'] = txt.split()[0]
        except Exception:
            pass
        return info

    @staticmethod
    def _probe_steam_ip(ip: str, domain: str, timeout: float = 3.0, port: int = 443) -> Dict:
        """TCP → TLS → HTTP 三段实测，返回毫秒耗时与综合得分。

        TLS 阶段**强校验证书必须匹配域名**：这一步同时承担「筛掉 DNS 污染」的职责 ——
        被污染的域名会解析到别人的 IP（例如 steamcommunity.com 被解析到 Facebook 段），
        那些 IP 的证书跟目标域名对不上，直接判死，绝不允许写进 hosts。
        """
        t0 = time.perf_counter()
        sock = ss = None
        try:
            sock = socket.create_connection((ip, port), timeout=timeout)
            tcp_ms = (time.perf_counter() - t0) * 1000
            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            try:
                ss = ctx.wrap_socket(sock, server_hostname=domain)
            except ssl.SSLCertVerificationError:
                return {'ip': ip, 'ok': False, 'error': 'cert_mismatch'}
            tls_ms = (time.perf_counter() - t0) * 1000
            ss.settimeout(timeout)
            ss.sendall(
                f'HEAD / HTTP/1.1\r\nHost: {domain}\r\n'
                'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n'
                'Accept: */*\r\nConnection: close\r\n\r\n'.encode())
            ss.recv(64)
            total_ms = (time.perf_counter() - t0) * 1000
            return {'ip': ip, 'ok': True,
                    'tcp_ms': round(tcp_ms, 1), 'tls_ms': round(tls_ms, 1),
                    'total_ms': round(total_ms, 1),
                    'score': round(tcp_ms * 0.35 + total_ms * 0.65, 1)}
        except Exception as e:
            return {'ip': ip, 'ok': False, 'error': type(e).__name__}
        finally:
            for s in (ss, sock):
                try:
                    if s:
                        s.close()
                except Exception:
                    pass

    def steam_accel_status(self) -> Dict:
        return self.accel_status('steam')

    def accel_status(self, category: str = 'steam') -> Dict:
        cat = ACCEL_CATEGORIES.get(category, ACCEL_CATEGORIES['steam'])
        applied = self._hosts_accel_block(cat['begin'], cat['end'])
        return {'success': True, 'category': category, 'label': cat['label'],
                'enabled': bool(applied), 'applied': applied, 'count': len(applied),
                'admin': self.is_admin(), 'writable': self._hosts_writable(),
                'local_accel': self._detect_local_accel(),
                'hosts_path': str(self._hosts_file)}

    def steam_accel_scan(self, domains: List[str] | None = None,
                         max_ip_per_domain: int = 8) -> Dict:
        return self.accel_scan('steam', domains, max_ip_per_domain)

    def accel_scan(self, category: str = 'steam',
                   domains: List[str] | None = None,
                   max_ip_per_domain: int = 8) -> Dict:
        """并发 DoH 解析 + 真实测速，为每个域名挑最快 IP。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        cat = ACCEL_CATEGORIES.get(category, ACCEL_CATEGORIES['steam'])
        want = set(domains or [])
        targets = [t for t in cat['domains'] if not want or t[0] in want] or list(cat['domains'])

        pool: Dict[str, List[str]] = {}
        with ThreadPoolExecutor(max_workers=16) as ex:
            futs = {ex.submit(self._doh_query, p, d): d
                    for d, _, _ in targets for p in STEAM_ACCEL_DOH}
            for f in as_completed(futs):
                d = futs[f]
                try:
                    ips = f.result() or []
                except Exception:
                    ips = []
                bucket = pool.setdefault(d, [])
                for ip in ips:
                    if ip not in bucket:
                        bucket.append(ip)

        for d, _, _ in targets:
            bucket = pool.setdefault(d, [])
            for ip in self._system_resolve(d):
                if ip not in bucket:
                    bucket.append(ip)

        local_accel = self._detect_local_accel()
        for d in list(pool):
            pool[d] = [ip for ip in pool[d] if not self._is_local_ip(ip)]

        probed: Dict[str, List[Dict]] = {d: [] for d, _, _ in targets}
        with ThreadPoolExecutor(max_workers=32) as ex:
            job = {}
            for d, _, _ in targets:
                for ip in pool.get(d, [])[:max_ip_per_domain]:
                    job[ex.submit(self._probe_steam_ip, ip, d)] = d
            for f in as_completed(job):
                d = job[f]
                try:
                    r = f.result()
                except Exception:
                    r = None
                if r:
                    probed[d].append(r)

        applied = self._hosts_accel_block(cat['begin'], cat['end'])
        rows = []
        for d, group, desc in targets:
            cands = sorted(probed.get(d, []),
                           key=lambda x: (not x.get('ok'), x.get('score', 1e9)))
            alive = [c for c in cands if c.get('ok')]
            poisoned = bool(cands) and not alive and all(
                c.get('error') == 'cert_mismatch' for c in cands)
            if alive:
                reason = ''
            elif poisoned:
                reason = '解析被污染（候选 IP 的证书都不是这个域名）—— hosts 优选救不了，要用本地反代型加速器'
            elif not cands:
                reason = '没拿到任何候选 IP —— 本机 DNS 解析异常'
            else:
                reason = '候选 IP 全部连不上（该域名多半被污染 / 被墙）—— hosts 优选无效，要用本地反代型加速器'
            rows.append({'domain': d, 'group': group, 'desc': desc,
                         'candidates': cands[:8],
                         'best': alive[0] if alive else None,
                         'poisoned': poisoned, 'reason': reason,
                         'current': applied.get(d)})
        return {'success': True, 'category': category, 'label': cat['label'], 'domains': rows,
                'admin': self.is_admin(), 'writable': self._hosts_writable(),
                'local_accel': local_accel, 'applied': applied,
                'hosts_path': str(self._hosts_file)}

    def steam_accel_apply(self, entries: List[Dict]) -> Dict:
        return self.accel_apply('steam', entries)

    def accel_apply(self, category: str, entries: List[Dict]) -> Dict:
        """把优选 IP 写进指定分类的 hosts 加速块（先备份，再整体替换旧块）。"""
        cat = ACCEL_CATEGORIES.get(category, ACCEL_CATEGORIES['steam'])
        pairs = []
        for e in (entries or []):
            d = str(e.get('domain') or '').strip().lower()
            ip = str(e.get('ip') or '').strip()
            if not d or ip.count('.') != 3 or not all(x.isdigit() for x in ip.split('.')):
                continue
            pairs.append((d, ip))
        if not pairs:
            return {'success': False, 'message': '没有可写入的加速条目。'}

        backup_path = None
        try:
            backup_dir = self.project_root / 'userdata' / 'hosts_backup'
            backup_dir.mkdir(parents=True, exist_ok=True)
            if self._hosts_file.exists():
                backup_path = backup_dir / f'hosts_{time.strftime("%Y%m%d_%H%M%S")}.bak'
                shutil.copy2(self._hosts_file, backup_path)
        except Exception:
            pass

        try:
            text = self._drop_accel_block(self._read_hosts(), cat['begin'], cat['end'])
            block = [cat['begin'],
                     f'# 由 大轩巴入库器mini v{CURRENT_VERSION} 生成 · {time.strftime("%Y-%m-%d %H:%M:%S")}',
                     f'# 还原：工具箱 → {cat["label"]}加速 → 一键还原']
            block += [f'{ip}\t{d}' for d, ip in pairs]
            block.append(cat['end'])
            self._write_hosts(text.rstrip('\r\n') + '\n\n' + '\n'.join(block) + '\n')
        except PermissionError:
            return {'success': False, 'need_admin': True,
                    'message': '写入 hosts 需要管理员权限 —— 请点「以管理员身份重启」后重试。'}
        except Exception as e:
            return {'success': False, 'message': f'写入 hosts 失败：{e}'}

        flushed = self._flush_dns()
        return {'success': True, 'category': category, 'count': len(pairs),
                'domains': [d for d, _ in pairs],
                'backup': str(backup_path) if backup_path else None, 'dns_flushed': flushed,
                'message': f'已为 {len(pairs)} 个域名写入优选 IP' + ('，DNS 缓存已刷新' if flushed else '')}

    def steam_accel_restore(self) -> Dict:
        return self.accel_restore('steam')

    def accel_restore(self, category: str) -> Dict:
        """移除指定分类 hosts 里的加速块（先备份）。"""
        cat = ACCEL_CATEGORIES.get(category, ACCEL_CATEGORIES['steam'])
        try:
            backup_dir = self.project_root / 'userdata' / 'hosts_backup'
            backup_dir.mkdir(parents=True, exist_ok=True)
            if self._hosts_file.exists():
                shutil.copy2(self._hosts_file, backup_dir / f'hosts_{time.strftime("%Y%m%d_%H%M%S")}.bak')
        except Exception:
            pass

        n = len(self._hosts_accel_block(cat['begin'], cat['end']))
        try:
            self._write_hosts(self._drop_accel_block(self._read_hosts(), cat['begin'], cat['end']))
        except PermissionError:
            return {'success': False, 'need_admin': True,
                    'message': '修改 hosts 需要管理员权限 —— 请点「以管理员身份重启」后重试。'}
        except Exception as e:
            return {'success': False, 'message': f'还原失败：{e}'}

        flushed = self._flush_dns()
        return {'success': True, 'category': category, 'removed': n, 'dns_flushed': flushed,
                'message': f'已移除加速记录（{n} 条）' + ('，DNS 缓存已刷新' if flushed else '')}

    def accel_hostsfree_apply(self, category: str, entries: List[Dict]) -> Dict:
        """保存某分类的「域名→IP」映射到 config，供启动时注入 Chromium --host-resolver-rules。"""
        cat = ACCEL_CATEGORIES.get(category, ACCEL_CATEGORIES['steam'])
        pairs = {}
        for e in (entries or []):
            d = str(e.get('domain') or '').strip().lower()
            ip = str(e.get('ip') or '').strip()
            if not d or ip.count('.') != 3 or not all(x.isdigit() for x in ip.split('.')):
                continue
            pairs[d] = ip
        if not pairs:
            return {'success': False, 'message': '没有可写入的加速条目。'}
        cfg = self._load_config_sync() or {}
        hf = cfg.setdefault('accel_hostsfree', {})
        hf[category] = pairs
        self._save_config_sync(cfg)
        self.config = cfg
        return {'success': True, 'category': category, 'count': len(pairs),
                'message': '已保存免hosts加速映射，重启应用后内置浏览器即走优选IP（不改动系统hosts）。',
                'need_restart': True}

    def accel_hostsfree_restore(self, category: str) -> Dict:
        cfg = self._load_config_sync() or {}
        hf = cfg.get('accel_hostsfree', {}) or {}
        removed = category in hf
        if removed:
            del hf[category]
            self._save_config_sync(cfg)
            self.config = cfg
        return {'success': True, 'category': category, 'removed': removed,
                'message': '已移除该分类免hosts加速映射，重启应用后生效。', 'need_restart': True}

    def accel_hostsfree_status(self) -> Dict:
        cfg = self._load_config_sync() or {}
        hf = cfg.get('accel_hostsfree', {}) or {}
        total = sum(len(v) for v in hf.values())
        return {'success': True, 'enabled': bool(hf), 'categories': list(hf.keys()),
                'count': total, 'maps': hf}

    def build_hostsfree_rules(self) -> str:
        """生成 Chromium --host-resolver-rules 字符串（仅重定向已启用分类的域名→IP）。"""
        cfg = self._load_config_sync() or {}
        hf = cfg.get('accel_hostsfree', {}) or {}
        rules = []
        for cat, pairs in hf.items():
            for d, ip in pairs.items():
                rules.append(f'MAP {d} {ip}')
        if not rules:
            return ''
        rules.append('MAP * *')
        return ','.join(rules)

    def steam_diagnose(self) -> Dict:
        """体检 Steam 环境：返回逐项检查结果，同时给出可执行的修复动作。"""
        checks: List[Dict] = []
        fixes: List[Dict] = []

        def add(cid, name, ok, detail, level=None, fix=None):
            item = {"id": cid, "name": name, "ok": bool(ok), "detail": detail,
                    "level": level or ("ok" if ok else "error")}
            checks.append(item)
            if fix:
                fixes.append(fix)

        sp = self.get_steam_path()
        sp_ok = bool(sp and sp.exists())
        detail = str(sp) if sp_ok else '找不到 Steam 目录'
        if not sp_ok:
            reg = self._steam_registry_paths()
            detail += ('（注册表候选：' + ' / '.join(reg) + '）') if reg else '（注册表里也没有记录，请手动指定）'
        add('steam_path', 'Steam 安装路径', sp_ok, detail)

        running = self._steam_running()
        add('steam_running', 'Steam 客户端进程', True,
            '正在运行' if running else '未运行（新入库的清单要重启 Steam 才生效）',
            level='info' if running else 'warn')
        if running:
            fixes.append({"id": "restart_steam", "name": "重启 Steam",
                          "desc": "清掉旧缓存状态，让新入库的清单立即生效"})

        if sp_ok:
            writable = False
            probe = sp / '.dxb_write_test'
            try:
                probe.write_text('ok', encoding='utf-8')
                writable = True
            except Exception:
                pass
            finally:
                try:
                    probe.unlink(missing_ok=True)
                except Exception:
                    pass
            add('write_perm', 'Steam 目录写权限', writable,
                '可写入，入库不受影响' if writable
                else '不可写入 —— 请用管理员身份运行本程序，或把 Steam 装到非系统盘')

        if sp_ok:
            try:
                du = shutil.disk_usage(str(sp))
                free_gb = du.free / (1024 ** 3)
                ok = free_gb >= 5
                add('disk_space', '磁盘剩余空间', ok,
                    f'{free_gb:.1f} GB 可用' + ('' if ok else ' —— 空间不足会导致下载/更新失败（Steam 报 磁盘写入错误）'),
                    level='ok' if ok else 'warn')
            except Exception:
                pass

        try:
            st = self.get_steam_status()
            kernel = st.get('kernel', 'none')
            kn = {'steamtools': 'SteamTools', 'greenluma': 'GreenLuma（DLL 注入）',
                  'opensteamtool': 'OpenSteamTool（清单导入）'}.get(kernel, '')
            add('kernel', '入库内核', kernel != 'none',
                f'已检测到 {kn}' if kernel != 'none' else '未检测到内核（SteamTools / GreenLuma / OpenSteamTool 均未安装）',
                level='ok' if kernel != 'none' else 'warn')
        except Exception:
            pass

        hosts_hits = self._hosts_steam_entries()
        add('hosts', 'hosts 屏蔽检查', not hosts_hits,
            '未发现屏蔽 Steam 的记录' if not hosts_hits
            else f'发现 {len(hosts_hits)} 条 Steam 相关记录（可能被加速器/管家改写，会导致商店打不开）：' + '；'.join(hosts_hits[:3]),
            level='ok' if not hosts_hits else 'warn')
        if hosts_hits:
            fixes.append({"id": "fix_hosts", "name": "注释掉 hosts 里的 Steam 记录",
                          "desc": "改写前会备份 hosts 到 userdata，可随时还原"})

        la = self._detect_local_accel()
        la_proc = la.get('process') or '本地加速器'
        la_pid = f'（PID {la["pid"]}）' if la.get('pid') else ''
        add('local_accel', '本地加速器占用', not la['active'],
            '未检测到本地反代型加速器' if not la['active']
            else (f'检测到 {la_proc}{la_pid} 正在接管 Steam 域名'
                  f'（{len(la["domains"])} 个解析到 127.0.0.1）。'
                  '它和「Steam 加速」的 hosts 优选会互相覆盖，建议二选一。'),
            level='ok' if not la['active'] else 'warn')

        if sp_ok:
            hc = sp / 'appcache' / 'httpcache'
            if hc.is_dir():
                sz = self._dir_size(hc)
                big = sz > 400 * 1024 * 1024
                add('httpcache', 'Steam 网页缓存', not big,
                    f'{self.fmt_size(sz)}' + (' —— 偏大，容易导致商店/登录页异常，建议清理' if big else '，正常'),
                    level='ok' if not big else 'warn')
                if big:
                    fixes.append({"id": "clean_httpcache", "name": "清理 Steam 网页缓存",
                                  "desc": "删除 appcache/httpcache，Steam 会自动重建（安全，需先关掉 Steam）"})

        if sp_ok:
            residue = []
            for root in self._steam_library_roots(sp):
                dld = root / 'steamapps' / 'downloading'
                if not dld.is_dir():
                    continue
                try:
                    for p in dld.iterdir():
                        if p.is_dir() and not (root / 'steamapps' / f'appmanifest_{p.name}.acf').exists():
                            residue.append(str(p))
                except Exception:
                    continue
            add('downloading_residue', '下载残留清理', not residue,
                '没有残留' if not residue else f'发现 {len(residue)} 个没有对应清单的下载残留目录（会让 Steam 反复校验/卡更新）',
                level='ok' if not residue else 'warn')
            if residue:
                fixes.append({"id": "clean_downloading", "name": "清理下载残留",
                              "desc": f'删除 {len(residue)} 个孤儿下载缓存目录（不碰已安装的游戏）'})

        store_ok = self._net_probe('https://store.steampowered.com/login/')
        api_ok = self._net_probe('https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/')
        add('network', 'Steam 服务连通性', store_ok or api_ok,
            f'商店：{"通" if store_ok else "不通"}，API：{"通" if api_ok else "不通"}'
            + ('' if (store_ok or api_ok) else ' —— 检查网络/代理/加速器，或先修复 hosts'),
            level='ok' if (store_ok or api_ok) else 'error')

        bad = [c for c in checks if c['level'] == 'error']
        warn = [c for c in checks if c['level'] == 'warn']
        summary = ('一切正常' if not bad and not warn
                   else f'{len(bad)} 项异常、{len(warn)} 项提醒')
        return {"success": True, "checks": checks, "fixes": fixes,
                "summary": summary, "issues": len(bad), "warnings": len(warn),
                "steam_path": str(sp) if sp else None}

    def steam_repair(self, actions: List[str]) -> Dict:
        """执行诊断里给出的修复动作。每步独立，单步失败不影响其它。"""
        actions = [str(a) for a in (actions or [])]
        results: List[Dict] = []
        sp = self.get_steam_path()
        self.steam_path = sp

        def rec(action, ok, message):
            results.append({"action": action, "success": bool(ok), "message": message})

        if 'fix_hosts' in actions:
            hp = Path(r'C:\Windows\System32\drivers\etc\hosts')
            try:
                backup_dir = self.project_root / 'userdata' / 'hosts_backup'
                backup_dir.mkdir(parents=True, exist_ok=True)
                if hp.exists():
                    shutil.copy2(hp, backup_dir / f'hosts_{time.strftime("%Y%m%d_%H%M%S")}.bak')
                lines = hp.read_text(encoding='utf-8', errors='ignore').splitlines() if hp.exists() else []
                kept, n = [], 0
                for line in lines:
                    s = line.strip()
                    if s and not s.startswith('#') and 'steam' in s.lower():
                        kept.append('# [大轩巴已注释] ' + line)
                        n += 1
                    else:
                        kept.append(line)
                hp.write_text('\n'.join(kept) + '\n', encoding='utf-8')
                rec('fix_hosts', True, f'已注释 {n} 条 Steam 记录（原文件已备份）')
            except PermissionError:
                rec('fix_hosts', False, '没有权限写 hosts —— 请用管理员身份运行本程序')
            except Exception as e:
                rec('fix_hosts', False, f'修复 hosts 失败：{e}')

        if 'clean_httpcache' in actions:
            if not sp or not sp.exists():
                rec('clean_httpcache', False, '未找到 Steam 目录')
            else:
                hc = sp / 'appcache' / 'httpcache'
                if not hc.exists():
                    rec('clean_httpcache', True, '网页缓存目录不存在，无需清理')
                else:
                    freed = self._dir_size(hc, 3.0)
                    try:
                        shutil.rmtree(hc, ignore_errors=True)
                        rec('clean_httpcache', not hc.exists(),
                            f'已清理网页缓存（约 {self.fmt_size(freed)}）' if not hc.exists()
                            else '部分文件被占用未能删除，请先完全退出 Steam 再试')
                    except Exception as e:
                        rec('clean_httpcache', False, f'清理失败：{e}')

        if 'clean_downloading' in actions:
            if not sp or not sp.exists():
                rec('clean_downloading', False, '未找到 Steam 目录')
            else:
                n = 0
                for root in self._steam_library_roots(sp):
                    dld = root / 'steamapps' / 'downloading'
                    if not dld.is_dir():
                        continue
                    try:
                        for p in list(dld.iterdir()):
                            if p.is_dir() and not (root / 'steamapps' / f'appmanifest_{p.name}.acf').exists():
                                shutil.rmtree(p, ignore_errors=True)
                                if not p.exists():
                                    n += 1
                    except Exception:
                        continue
                rec('clean_downloading', True, f'已清理 {n} 个孤儿下载目录' if n else '没有需要清理的残留')

        if 'restart_steam' in actions:
            try:
                ok = self.restart_steam()
                rec('restart_steam', ok, '已重启 Steam' if ok else '重启 Steam 失败，请检查 Steam 路径')
            except Exception as e:
                rec('restart_steam', False, f'重启 Steam 失败：{e}')

        ok_all = all(r['success'] for r in results) if results else False
        return {"success": ok_all, "results": results,
                "message": '修复完成。' if ok_all else '部分修复项未成功，请看下面的明细。'}

    def free_games_list(self, query: str = "", max_items: int = 400) -> Dict:
        """用 Steam 官方搜索接口（maxprice=free）分页抓取免费游戏，最多 max_items 个。
        AppID 从 logo URL 的 /apps/<id>/ 中提取。"""
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        games: List[Dict] = []
        seen = set()
        try:
            import httpx as _httpx
            with _httpx.Client(verify=False, timeout=30) as cli:
                start = 0
                while len(games) < max_items:
                    params = {'query': query, 'start': start, 'count': 50,
                              'maxprice': 'free', 'supportedlang': 'schinese',
                              'cc': 'CN', 'l': 'schinese', 'json': 1}
                    r = cli.get("https://store.steampowered.com/search/results/",
                                params=params, headers=headers)
                    r.raise_for_status()
                    items = r.json().get('items', [])
                    if not items:
                        break
                    for it in items:
                        logo = it.get('logo') or ''
                        m = re.search(r'/apps/(\d+)/', logo)
                        appid = m.group(1) if m else ''
                        name = (it.get('name') or '').strip()
                        if not appid or appid in seen:
                            continue
                        seen.add(appid)
                        games.append({
                            "appid": appid,
                            "name": name,
                            "header_image": f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
                        })
                        if len(games) >= max_items:
                            break
                    start += 50
            return {"success": True, "games": games, "total": len(games)}
        except Exception as e:
            self.log.error(f"获取免费游戏失败: {self.stack_error(e)}")
            return {"success": False, "message": f"获取免费游戏失败: {e}", "games": [], "total": 0}

    def featured_games(self) -> Dict:
        """游戏推荐页数据：特惠 / 热销 / 新品 / 即将推出（Steam 官方 featuredcategories）。"""
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        sections_meta = [("specials", "今日特惠"), ("top_sellers", "热销榜"),
                         ("new_releases", "新品上架"), ("coming_soon", "即将推出")]
        try:
            import httpx as _httpx
            with _httpx.Client(verify=False, timeout=25) as cli:
                r = cli.get("https://store.steampowered.com/api/featuredcategories",
                            params={'cc': 'CN', 'l': 'schinese'}, headers=headers)
                r.raise_for_status()
                js = r.json()
            sections = []
            for key, title in sections_meta:
                items = (js.get(key) or {}).get('items') or []
                games = []
                for it in items:
                    appid = str(it.get('id') or '').strip()
                    if not appid.isdigit():
                        continue
                    games.append({
                        "appid": appid,
                        "name": (it.get('name') or '').strip(),
                        "image": (it.get('header_image') or it.get('large_capsule_image')
                                  or it.get('small_capsule_image') or ''),
                        "discount_percent": it.get('discount_percent') or 0,
                        "original_price": it.get('original_price'),
                        "final_price": it.get('final_price'),
                        "currency": it.get('currency') or 'CNY',
                    })
                if games:
                    sections.append({"key": key, "title": title, "games": games})
            if not sections:
                return {"success": False, "message": "未获取到推荐数据，请检查网络。", "sections": []}
            return {"success": True, "sections": sections}
        except Exception as e:
            self.log.error(f"获取推荐数据失败: {self.stack_error(e)}")
            return {"success": False, "message": f"获取推荐数据失败: {e}", "sections": []}

    _STEAM_IMG_HOSTS = (
        'https://cdn.cloudflare.steamstatic.com/steam/apps/{id}/header.jpg',
        'https://cdn.akamai.steamstatic.com/steam/apps/{id}/header.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/header.jpg',
        'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{id}/header.jpg',
        'https://steamcdn-a.akamaihd.net/steam/apps/{id}/header.jpg',
        'https://media.st.dl.eccdnx.com/steam/apps/{id}/header.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/header_schinese.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/capsule_616x353.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/capsule_231x87.jpg',
        'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{id}/library_hero.jpg',
        'https://cdn.cloudflare.steamstatic.com/steam/apps/{id}/capsule_231x87.jpg',
        'https://cdn.cloudflare.steamstatic.com/steam/apps/{id}/library_600x900.jpg',
    )

    _IMG_ALLOW_SUFFIX = (
        '.steamstatic.com', '.akamaihd.net', '.eccdnx.com',
    )

    def _is_allowed_image_url(self, url: str) -> bool:
        try:
            from urllib.parse import urlparse
            u = urlparse(url or '')
            if u.scheme not in ('http', 'https'):
                return False
            host = (u.hostname or '').lower()
            return any(host == s.lstrip('.') or host.endswith(s) for s in self._IMG_ALLOW_SUFFIX)
        except Exception:
            return False

    def steam_image_cache_dir(self) -> Path:
        d = self.project_root / 'userdata' / 'img_cache'
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _download_image(self, url: str, cache_file: Path) -> bytes | None:
        """下载单张图片，成功后写缓存。"""
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            import httpx as _httpx
            with _httpx.Client(verify=False, timeout=15, follow_redirects=True) as cli:
                r = cli.get(url, headers=headers)
                if r.status_code == 200 and len(r.content) > 1024:
                    try:
                        cache_file.write_bytes(r.content)
                    except Exception:
                        pass
                    return r.content
        except Exception:
            return None
        return None

    def fetch_image_by_url(self, url: str, appid: str = '') -> bytes | None:
        """按完整 URL 抓图（推荐页的 header_image 用），带域名白名单与落盘缓存。"""
        if not self._is_allowed_image_url(url):
            return None
        key = str(appid or '').strip()
        if not key or not key.isdigit():
            key = 'u' + str(abs(hash(url)))[:15]
        cache = self.steam_image_cache_dir() / f'{key}.jpg'
        if cache.exists() and cache.stat().st_size > 1024:
            try:
                return cache.read_bytes()
            except Exception:
                pass
        return self._download_image(url, cache)

    def _steam_appdetails_one(self, appid: str) -> Dict:
        """查询单个 appid 的商店详情。
        ⚠️ appdetails 用逗号一次传多个 appid 会返回 HTTP 400（2026-09 实测），
           所以这里严格只查单个 appid。失败返回 {}，绝不抛异常。"""
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            import httpx as _httpx
            with _httpx.Client(verify=False, timeout=15) as cli:
                r = cli.get('https://store.steampowered.com/api/appdetails',
                            params={'appids': str(appid), 'l': 'schinese', 'cc': 'CN'},
                            headers=headers)
                if r.status_code != 200:
                    return {}
                val = (r.json() or {}).get(str(appid)) or {}
                if isinstance(val, dict) and val.get('success'):
                    return val.get('data') or {}
        except Exception:
            return {}
        return {}

    def fetch_steam_image(self, appid: str, url: str = '') -> bytes | None:
        """抓 Steam 封面图并落盘缓存。
        webview 直连 CDN 常一片空白（DNS/热链/超时），统一由本地服务代理：
          1) 调用方给了 url（推荐页 header_image，含 hash 路径）→ 直接下载
          2) 模板候选依次回退（老游戏的 header.jpg 一般有效）
          3) 模板全挂 → appdetails 拿官方 header_image（新游戏只能这样拿到真实地址）
        """
        appid = str(appid or '').strip()
        if url:
            data = self.fetch_image_by_url(url, appid)
            if data:
                return data
        if not appid.isdigit():
            return None
        cache = self.steam_image_cache_dir() / f'{appid}.jpg'
        if cache.exists() and cache.stat().st_size > 1024:
            try:
                return cache.read_bytes()
            except Exception:
                pass
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            import httpx as _httpx
            with _httpx.Client(verify=False, timeout=12, follow_redirects=True) as cli:
                for tpl in self._STEAM_IMG_HOSTS:
                    u = tpl.format(id=appid)
                    try:
                        r = cli.get(u, headers=headers)
                        if r.status_code == 200 and len(r.content) > 1024:
                            try:
                                cache.write_bytes(r.content)
                            except Exception:
                                pass
                            return r.content
                    except Exception:
                        continue
        except Exception as e:
            self.log.warning(f'获取封面失败 {appid}: {e}')
        info = self._steam_appdetails_one(appid)
        for key in ('header_image', 'capsule_image', 'capsule_imagev5', 'background'):
            u = info.get(key)
            if u:
                got = self._download_image(u, cache)
                if got:
                    return got
        return None

    def free_account_info(self, cookie: str) -> Dict:
        """用 steamLoginSecure cookie 获取账号名/头像/钱包余额。"""
        if not cookie or 'steamLoginSecure' not in cookie:
            return {"success": False, "message": "请提供有效的 steamLoginSecure Cookie。"}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                   'Cookie': cookie.strip()}
        try:
            import httpx as _httpx
            name, avatar = "", ""
            with _httpx.Client(verify=False, timeout=30, follow_redirects=True) as cli:
                try:
                    pr = cli.get("https://steamcommunity.com/my/profile?json=1", headers=headers)
                    if pr.ok:
                        pj = pr.json()
                        name = pj.get('personaName') or pj.get('name') or name
                        avatar = pj.get('avatarFull') or pj.get('avatar') or avatar
                except Exception as e:
                    self.log.warning(f"获取 Steam 个人资料失败: {e}")
                balance, currency = None, ""
                try:
                    wr = cli.get("https://store.steampowered.com/api/userwalletinfo/v1/", headers=headers)
                    if wr.ok:
                        wj = wr.json()
                        balance = wj.get('wallet_balance')
                        currency = wj.get('wallet_country') or wj.get('currency') or ""
                except Exception as e:
                    self.log.warning(f"获取钱包余额失败: {e}")
            if not name and balance is None:
                return {"success": False, "message": "Cookie 无效或已过期，无法读取账号信息。"}
            return {"success": True, "name": name, "avatar": avatar,
                    "balance": balance, "currency": currency}
        except Exception as e:
            self.log.error(f"读取账号信息失败: {self.stack_error(e)}")
            return {"success": False, "message": f"读取账号信息失败: {e}"}

    def inject_free_games(self, appids: List[str], name_map: Dict[str, str] = None) -> Dict:
        """把免费游戏批量永久入库：在解锁器 lua 目录为每个 AppID 写 addappid 文件。
        已存在的跳过（幂等），文件保留即永久有效。"""
        name_map = name_map or {}
        try:
            if not self.steam_path:
                self.steam_path = self.get_steam_path()
            if not self.steam_path or not self.steam_path.exists():
                return {"success": False, "message": "未找到有效的 Steam 路径。", "injected": 0, "skipped": 0}
            lua_dir = self.lua_output_dir()
            lua_dir.mkdir(parents=True, exist_ok=True)

            injected, skipped, names = 0, 0, []
            seen = set()
            for raw in appids:
                appid = str(raw).strip()
                if not appid.isdigit() or appid in seen:
                    continue
                seen.add(appid)
                target = lua_dir / f"{appid}.lua"
                if target.exists():
                    skipped += 1
                    continue
                gname = name_map.get(appid, "")
                lines = [
                    "-- 大轩巴入库器mini · 免费游戏永久入库",
                    f"-- AppID: {appid}" + (f"  名称: {gname}" if gname else ""),
                    "-- 永久生效：如需移除请删除本文件或在入库管理中删除",
                    f"addappid({appid})  -- {gname or appid}",
                ]
                target.write_text("\n".join(lines) + "\n", encoding='utf-8')
                injected += 1
                names.append(gname or appid)
            self.log.info(f"免费游戏永久入库完成：新增 {injected} 个，已存在跳过 {skipped} 个 -> {lua_dir}")
            return {"success": True, "injected": injected, "skipped": skipped,
                    "dir": str(lua_dir), "names": names[:20]}
        except Exception as e:
            self.log.error(f"免费游戏入库失败: {self.stack_error(e)}")
            return {"success": False, "message": f"入库失败: {e}", "injected": 0, "skipped": 0}


    async def _fetch_game_name_for_manager(self, appid: str) -> str:
        """为文件管理器异步获取游戏名称，并使用缓存。现在使用小黑盒API。"""
        if not appid or not appid.isdigit():
            return "无效AppID"
        if appid in self.name_cache:
            return self.name_cache[appid]

        url = f"https://api.xiaoheihe.cn/game/share_game_detail?appid={appid}"
        try:
            response = await self.client.get(url, headers={'User-Agent': 'DaXuanBa-Rukuqi/1.0'})
            response.raise_for_status()
            html_content = response.text
            
            title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
            
            if title_match:
                name = title_match.group(1).strip()
                if " - 小黑盒" in name:
                    name = name.replace(" - 小黑盒", "").strip()
                self.name_cache[appid] = name
                return name
            
            return "名称未找到"
        except Exception as e:
            self.log.warning(f"从小黑盒获取 AppID {appid} 的名称失败: {e}")
            return "获取失败"
            
    async def get_managed_files(self) -> Dict:
        """扫描所有相关目录，返回文件信息，并批量获取游戏名称。"""
        if not self.steam_path or not self.steam_path.exists():
            return {"error": "Steam路径未配置或无效。"}

        file_data = {"st": [], "gl": [], "assistant": []}
        all_appids_to_fetch = set()

        st_path = self.steam_path / 'config' / 'stplug-in'
        gl_path = self.steam_path / 'AppList'

        if st_path.exists():
            file_data['st'], st_appids = self._scan_st_files(st_path)
            all_appids_to_fetch.update(st_appids)

        if gl_path.exists():
            file_data['gl'], gl_appids = self._scan_generic_files(gl_path, ".txt")
            all_appids_to_fetch.update(gl_appids)

        appids_to_fetch = [appid for appid in all_appids_to_fetch if appid not in self.name_cache]
        if appids_to_fetch:
            tasks = [self._fetch_game_name_for_manager(appid) for appid in appids_to_fetch]
            results = await asyncio.gather(*tasks)
            for appid, name in zip(appids_to_fetch, results):
                self.name_cache[appid] = name

        for category in file_data:
            for item in file_data[category]:
                if item['appid'] in self.name_cache:
                    item['game_name'] = self.name_cache[item['appid']]
        
        return file_data

    def _scan_st_files(self, directory: Path) -> Tuple[List[Dict], set]:
        """扫描SteamTools目录，返回文件数据和AppID集合。"""
        data, appids = [], set()
        file_data_map = {}
        try:
            for filename in os.listdir(directory):
                if filename.endswith(".lua") and filename != "steamtools.lua":
                    content = (directory / filename).read_text(encoding='utf-8', errors='ignore')
                    match = re.search(r'addappid\s*\(\s*(\d+)', content)
                    appid = match.group(1) if match else "N/A"
                    if appid.isdigit():
                        appids.add(appid)
                        file_data_map[appid] = {"filename": filename, "appid": appid, "game_name": "加载中...", "status": "ok"}
            
            st_lua_path = directory / "steamtools.lua"
            if st_lua_path.exists():
                data.append({"filename": "steamtools.lua", "appid": "N/A", "game_name": "SteamTools核心文件", "status": "core_file"})
                content = st_lua_path.read_text(encoding='utf-8', errors='ignore')
                unlocked_appids = set(re.findall(r'addappid\s*\(\s*(\d+)', content))
                for appid in unlocked_appids:
                    if appid not in file_data_map:
                        appids.add(appid)
                        file_data_map[appid] = {"filename": f"缺少 {appid}.lua", "appid": appid, "game_name": "加载中...", "status": "unlocked_only"}
        except Exception as e:
            self.log.error(f"扫描SteamTools目录失败: {e}")
        
        data.extend(sorted(file_data_map.values(), key=lambda item: int(item.get('appid', 0)), reverse=True))
        return data, appids

    def _scan_generic_files(self, directory: Path, extension: str) -> Tuple[List[Dict], set]:
        """扫描通用目录（如GreenLuma），返回文件数据和AppID集合。"""
        data, appids = [], set()
        try:
            files = [f for f in os.listdir(directory) if f.endswith(extension)]
            for filename in files:
                file_path = directory / filename

                if extension == ".txt":
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read().strip()
                            if content.isdigit():
                                appid = content
                            else:
                                appid = Path(filename).stem
                    except Exception as e:
                        self.log.warning(f"读取GreenLuma文件 {filename} 失败: {e}")
                        appid = Path(filename).stem
                else:
                    appid = Path(filename).stem

                if appid.isdigit():
                    appids.add(appid)
                    data.append({"filename": filename, "appid": appid, "game_name": "加载中...", "status": "ok"})
        except Exception as e:
            self.log.error(f"扫描目录 {directory} 失败: {e}")

        data.sort(key=lambda x: int(x.get('appid', 0)) if x.get('appid', '0').isdigit() else 0, reverse=True)
        return data, appids
    
    def delete_managed_files(self, file_type: str, items: List[Dict]) -> Dict:
        """根据类型和项目列表删除文件, 并清理关联的manifest。"""
        if not self.steam_path or not self.steam_path.exists():
            return {"success": False, "message": "Steam路径无效。"}
        
        base_path = None
        if file_type == 'st':
            base_path = self.steam_path / 'config' / 'stplug-in'
        elif file_type == 'gl':
            base_path = self.steam_path / 'AppList'
        
        if not base_path:
            return {"success": False, "message": f"未知的类型: {file_type}。"}

        deleted_count, failed, manifests_deleted_count = 0, [], 0
        
        for item in items:
            try:
                if file_type == 'st' and item.get('status') != 'core_file' and item.get('appid', 'N/A').isdigit():
                    self._modify_st_lua_for_delete(item['appid'])

                filename = item.get('filename')
                if filename and "缺少" not in filename:
                    file_path = base_path / filename
                    if file_path.exists() and file_path.is_file():
                        if file_type == 'st' and filename.endswith('.lua'):
                            try:
                                content = file_path.read_text(encoding='utf-8', errors='ignore')
                                gids = re.findall(r'setManifestid\s*\(\s*\d+\s*,\s*"(\d+)"\s*\)', content)
                                depotcache_paths = [
                                    self.steam_path / 'depotcache',
                                    self.steam_path / 'config' / 'depotcache'
                                ]
                                for gid in gids:
                                    for cache_path in depotcache_paths:
                                        if cache_path.exists():
                                            for mf in cache_path.glob(f'*_{gid}.manifest'):
                                                if mf.exists():
                                                    os.remove(mf)
                                                    manifests_deleted_count += 1
                            except Exception as e:
                                self.log.error(f"清理 {filename} 的清单时失败: {e}")
                        
                        os.remove(file_path)
                        deleted_count += 1
            except Exception as e:
                failed.append(f"{item.get('filename', item.get('appid'))}: {e}")

        message = f"成功处理 {len(items) - len(failed)}/{len(items)} 个条目。"
        if deleted_count > 0:
            message += f" 删除了 {deleted_count} 个文件。"
        if manifests_deleted_count > 0:
             message += f" 清理了 {manifests_deleted_count} 个关联清单文件。"
        if failed:
            message += f" 失败条目: {', '.join(failed)}"
        
        return {"success": not failed, "message": message}


    def _modify_st_lua_for_delete(self, appid: str):
        """从steamtools.lua中移除一个解锁条目。"""
        st_lua_path = self.steam_path / 'config' / 'stplug-in' / "steamtools.lua"
        if not st_lua_path.exists(): return

        try:
            content = st_lua_path.read_text(encoding='utf-8', errors='ignore')
            pattern = re.compile(r'^\s*addappid\s*\(\s*' + re.escape(appid) + r'[^)]*\)\s*$', re.MULTILINE)
            new_content, count = pattern.subn('', content)
            
            if count > 0:
                new_content_cleaned = "\n".join(line for line in new_content.splitlines() if line.strip())
                st_lua_path.write_text(new_content_cleaned + "\n" if new_content_cleaned else "", encoding='utf-8')
                self.log.info(f"已从 steamtools.lua 移除 AppID {appid} 的解锁条目。")
        except Exception as e:
            self.log.error(f"修改 steamtools.lua 以删除 AppID {appid} 时失败: {e}")
            raise
            

    def get_custom_github_repos(self) -> List[Dict]:
        """获取自定义GitHub仓库列表"""
        custom_repos = self.config.get("Custom_Repos", {}).get("github", [])
        validated_repos = []
        
        for repo in custom_repos:
            if isinstance(repo, dict) and 'name' in repo and 'repo' in repo:
                validated_repos.append(repo)
            else:
                self.log.warning(f"无效的自定义GitHub仓库配置: {repo}")
        
        return validated_repos

    def get_custom_zip_repos(self) -> List[Dict]:
        """获取自定义ZIP仓库列表"""
        custom_repos = self.config.get("Custom_Repos", {}).get("zip", [])
        validated_repos = []
        
        for repo in custom_repos:
            if isinstance(repo, dict) and 'name' in repo and 'url' in repo:
                if '{app_id}' in repo['url']:
                    validated_repos.append(repo)
                else:
                    self.log.warning(f"自定义ZIP仓库URL缺少{{app_id}}占位符: {repo}")
            else:
                self.log.warning(f"无效的自定义ZIP仓库配置: {repo}")
        
        return validated_repos

    async def process_custom_zip_manifest(self, app_id: str, repo_config: Dict, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        """处理自定义ZIP清单库"""
        repo_name = repo_config.get('name', '未知仓库')
        url_template = repo_config.get('url', '')
        
        download_url = url_template.replace('{app_id}', app_id)
        
        return await self._process_zip_manifest_generic(app_id, download_url, f"自定义ZIP库 ({repo_name})", self.unlocker_type, False, add_all_dlc, patch_depot_key)

    def get_all_github_repos(self) -> List[str]:
        """获取所有GitHub仓库（内置+自定义）"""
        builtin_repos = ['Auiowu/ManifestAutoUpdate', 'SteamAutoCracks/ManifestHub']
        custom_repos = [repo['repo'] for repo in self.get_custom_github_repos()]
        return builtin_repos + custom_repos

    SOURCE_PROBE: Dict[str, Any] = {
        "search": None,
        "Auiowu/ManifestAutoUpdate":      ("https://github.com/Auiowu/ManifestAutoUpdate", 95),
        "SteamAutoCracks/ManifestHub":    ("https://github.com/SteamAutoCracks/ManifestHub", 90),
        "ikun0014/ManifestHub":           ("https://github.com/ikun0014/ManifestHub", 88),
        "Masaiki/ManifestAutoUpdate":     ("https://github.com/Masaiki/ManifestAutoUpdate", 85),
        "wxy1343/ManifestAutoUpdate":     ("https://github.com/wxy1343/ManifestAutoUpdate", 82),
        "Cyberbolt/ManifestAutoUpdate":   ("https://github.com/Cyberbolt/ManifestAutoUpdate", 80),
        "Fairyvmos/bruh-hub":             ("https://github.com/Fairyvmos/bruh-hub", 78),
        "Cracko298/ManifestHub":          ("https://github.com/Cracko298/ManifestHub", 75),
        "printedwaste":                   ("https://api.printedwaste.com/", 70),
        "steamdatabase":                  ("https://steamdatabase.s3.eu-north-1.amazonaws.com/", 68),
        "furcate":                        ("https://furcate.eu/", 64),
        "cysaw":                          ("https://cysaw.top/", 60),
        "walftech":                       ("https://walftech.com/", 55),
        "steamautocracks_v2":             ("https://steamui.com/", 50),
        "sudama":                         ("https://steam.ddxnb.cn/", 52),
        "buqiuren":                       ("https://steamui.com/", 50),
    }

    _source_test_cache: Dict[str, Any] = {"ts": 0.0, "availability": None, "recommended": None}
    _SOURCE_CACHE_FILE = "source_probe_cache.json"
    _SOURCE_CACHE_TTL = 6 * 3600

    @staticmethod
    def _load_source_cache() -> Dict[str, Any]:
        """读落盘的源探测缓存（跨进程，省掉每次启动的 3-8 秒探测）。
        「全部源都不可用」这种结果一定是网络/代理异常，直接丢弃，不能让用户
        一开机就只剩兜底源。"""
        try:
            p = Path(tempfile.gettempdir()) / DxbBackend._SOURCE_CACHE_FILE
            if p.exists() and (time.time() - p.stat().st_mtime) < DxbBackend._SOURCE_CACHE_TTL:
                d = json.loads(p.read_text(encoding="utf-8"))
                av = d.get("availability")
                if av and any(av.get(v) for v in av):
                    d["ts"] = time.time()
                    return d
        except Exception:
            pass
        return {"ts": 0.0, "availability": None, "recommended": None}

    @staticmethod
    def _save_source_cache(cache: Dict[str, Any]) -> None:
        try:
            p = Path(tempfile.gettempdir()) / DxbBackend._SOURCE_CACHE_FILE
            p.write_text(json.dumps({"availability": cache.get("availability"),
                                     "recommended": cache.get("recommended")},
                                    ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    async def _probe_one_source(self, value: str, url: str):
        """探测单个源根域名可达性（连接失败/超时 => 不可用）"""
        try:
            r = await self.client.get(url, timeout=3.0, follow_redirects=True)
            return value, (r.status_code < 500)
        except Exception:
            return value, False

    async def test_sources(self) -> Tuple[Dict[str, bool], str | None]:
        """并发探测所有内置源；返回 {value: 可用布尔} 与推荐源 value。
        进程内缓存 300s、落盘缓存 6h。"""
        now = time.time()
        cache = DxbBackend._source_test_cache
        if not cache.get("availability"):
            cache.update(DxbBackend._load_source_cache())
        if cache.get("availability") and (now - cache.get("ts", 0.0)) < 300:
            return cache["availability"], cache["recommended"]

        results: Dict[str, bool] = {}
        for value, spec in DxbBackend.SOURCE_PROBE.items():
            if spec is None:
                results[value] = True

        tasks = {
            value: asyncio.create_task(self._probe_one_source(value, spec[0]))
            for value, spec in DxbBackend.SOURCE_PROBE.items() if spec is not None
        }
        for value, t in tasks.items():
            v, ok = await t
            results[v] = ok
            self.log.info(f"清单源探测 {v}: {'可用' if ok else '不可用(剔除)'}")

        avail = [v for v, ok in results.items()
                 if ok and DxbBackend.SOURCE_PROBE.get(v) is not None]
        avail.sort(key=lambda v: DxbBackend.SOURCE_PROBE[v][1], reverse=True)
        recommended = avail[0] if avail else None

        if not avail:
            self.log.warning("所有清单源探测均失败（疑似断网/代理异常），本次按全部可用处理且不写入缓存")
            results = {v: True for v in results}
            recommended = next((v for v, spec in DxbBackend.SOURCE_PROBE.items()
                                if spec is not None), "search")
            return results, recommended

        cache.update(ts=now, availability=results, recommended=recommended)
        DxbBackend._save_source_cache(cache)
        return results, recommended

    async def http_get_safe(self, url: str, timeout: int = 30, max_retries: int = 3, retry_delay: float = 1.0) -> httpx.Response | None:
        """安全的HTTP GET请求，带错误处理和重试机制"""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                current_timeout = timeout if attempt == 0 else min(timeout * (attempt + 1), 60)
                
                response = await self.client.get(url, timeout=current_timeout)
                if response.status_code == 200:
                    if attempt > 0:
                        self.log.info(f"HTTP请求在第 {attempt + 1} 次尝试后成功: {url}")
                    return response
                else:
                    self.log.warning(f"HTTP请求失败，状态码: {response.status_code} - {url} (尝试 {attempt + 1}/{max_retries})")
                    if response.status_code in [429, 503, 502, 504]:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                            continue
                    return None
                    
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException) as e:
                last_exception = e
                self.log.warning(f"HTTP请求超时: {url} (尝试 {attempt + 1}/{max_retries}) - {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                    
            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                last_exception = e
                self.log.warning(f"HTTP连接错误: {url} (尝试 {attempt + 1}/{max_retries}) - {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                    
            except Exception as e:
                last_exception = e
                self.log.error(f"HTTP请求异常: {url} (尝试 {attempt + 1}/{max_retries}) - {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                break
        
        self.log.error(f"HTTP请求在 {max_retries} 次尝试后仍然失败: {url} - 最后异常: {last_exception}")
        return None

    async def get_dlc_ids_safe(self, appid: str) -> List[str]:
        """安全的DLC ID获取函数，支持多数据源回退 (ddxnb -> steamcmd -> steam store)"""
        self.log.info(f"正在获取 AppID {appid} 的DLC信息...")

        def parse_steamcmd_style_json(json_data: dict) -> List[str]:
            try:
                info = json_data.get("data", {}).get(str(appid), {})
                dlc_str = info.get("extended", {}).get("listofdlc", "") or info.get("common", {}).get("listofdlc", "")
                if dlc_str:
                    return sorted(filter(str.isdigit, map(str.strip, dlc_str.split(","))), key=int)
            except Exception:
                pass
            return []

        self.log.debug(f"尝试从 ddxnb源 获取 AppID {appid} 的DLC...")
        data = await self.http_get_safe(f"https://steam.ddxnb.cn/v1/info/{appid}", timeout=20, max_retries=2)
        if data:
            try:
                dlc_ids = parse_steamcmd_style_json(data.json())
                if dlc_ids:
                    self.log.info(f"从 ddxnb源 成功获取到 {len(dlc_ids)} 个DLC")
                    return dlc_ids
                self.log.debug(f"ddxnb源 中 AppID {appid} 没有DLC信息或解析为空")
            except Exception as e:
                self.log.warning(f"解析 ddxnb源 响应失败: {e}")
        else:
            self.log.warning(f"无法从 ddxnb源 获取 AppID {appid} 的数据")

        self.log.debug(f"尝试从 SteamCMD API 获取 AppID {appid} 的DLC...")
        data = await self.http_get_safe(f"https://api.steamcmd.net/v1/info/{appid}", timeout=20, max_retries=2)
        if data:
            try:
                dlc_ids = parse_steamcmd_style_json(data.json())
                if dlc_ids:
                    self.log.info(f"从 SteamCMD API 成功获取到 {len(dlc_ids)} 个DLC")
                    return dlc_ids
                self.log.debug(f"SteamCMD API 中 AppID {appid} 没有DLC信息")
            except Exception as e:
                self.log.warning(f"解析 SteamCMD API 响应失败: {e}")
        else:
            self.log.warning(f"无法从 SteamCMD API 获取 AppID {appid} 的数据")
        
        self.log.debug(f"尝试从 Steam 官方 API 获取 AppID {appid} 的DLC...")
        api_variants = [
            f"https://store.steampowered.com/api/appdetails?appids={appid}&l=schinese",
            f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english",
            f"https://store.steampowered.com/api/appdetails?appids={appid}"
        ]
        
        for api_url in api_variants:
            data = await self.http_get_safe(api_url, timeout=25, max_retries=2, retry_delay=2.0)
            if data:
                try:
                    j = data.json()
                    app_data = j.get(str(appid), {})
                    if app_data.get("success") and "data" in app_data:
                        dlc_list = app_data["data"].get("dlc", [])
                        if dlc_list:
                            dlc_ids = [str(d) for d in dlc_list]
                            self.log.info(f"从 Steam 官方 API 成功获取到 {len(dlc_ids)} 个DLC")
                            return dlc_ids
                except Exception as e:
                    self.log.warning(f"解析 Steam 官方 API 响应失败 ({api_url}): {e}")
                    continue
        
        self.log.info(f"未找到 AppID {appid} 的DLC信息（已尝试所有数据源）")
        return []

    async def get_depots_safe(self, appid: str) -> List[Tuple[str, str, int, str]]:
        """安全的Depot获取函数，返回 (depot_id, manifest_id, size, source) 元组列表"""
        self.log.info(f"正在获取 AppID {appid} 的Depot信息...")
        
        def parse_steamcmd_style_depots(json_data: dict) -> List[Tuple[str, str, int, str]]:
            out = []
            try:
                info = json_data.get("data", {}).get(str(appid), {})
                depots = info.get("depots", {})
                if depots:
                    for depot_id, depot_info in depots.items():
                        if not isinstance(depot_info, dict): continue
                        manifest_info = depot_info.get("manifests", {}).get("public")
                        if not isinstance(manifest_info, dict): continue
                        
                        manifest_id = manifest_info.get("gid")
                        size = int(manifest_info.get("download", 0))
                        dlc_appid = depot_info.get("dlcappid")
                        source_label = f"DLC:{dlc_appid}" if dlc_appid else "主游戏"
                        
                        if manifest_id:
                            out.append((depot_id, manifest_id, size, source_label))
            except Exception:
                pass
            return out

        self.log.debug(f"尝试从 ddxnb源 获取 AppID {appid} 的Depot...")
        data = await self.http_get_safe(f"https://steam.ddxnb.cn/v1/info/{appid}", timeout=20, max_retries=2)
        if data:
            try:
                out = parse_steamcmd_style_depots(data.json())
                if out:
                    self.log.info(f"从 ddxnb源 成功获取到 {len(out)} 个Depot")
                    return out
                if "data" in data.json():
                     self.log.debug(f"ddxnb源 返回数据中无Depot信息")
            except Exception as e:
                self.log.warning(f"解析 ddxnb源 Depot 信息失败: {e}")
        else:
            self.log.warning(f"无法从 ddxnb源 获取 AppID {appid} 的Depot数据")

        self.log.debug(f"尝试从 SteamCMD API 获取 AppID {appid} 的Depot...")
        data = await self.http_get_safe(f"https://api.steamcmd.net/v1/info/{appid}", timeout=20, max_retries=2)
        if data:
            try:
                out = parse_steamcmd_style_depots(data.json())
                if out:
                    self.log.info(f"从 SteamCMD API 成功获取到 {len(out)} 个Depot")
                    return out
            except Exception as e:
                self.log.warning(f"解析 SteamCMD API Depot 信息失败: {e}")
        else:
            self.log.warning(f"无法从 SteamCMD API 获取 AppID {appid} 的Depot数据")
        
        self.log.debug(f"尝试从 Steam 官方 API 获取 AppID {appid} 的Depot...")
        api_variants = [
            f"https://store.steampowered.com/api/appdetails?appids={appid}&l=schinese",
            f"https://store.steampowered.com/api/appdetails?appids={appid}&l=english",
            f"https://store.steampowered.com/api/appdetails?appids={appid}"
        ]
        
        for api_url in api_variants:
            data = await self.http_get_safe(api_url, timeout=25, max_retries=2, retry_delay=2.0)
            if data:
                try:
                    j = data.json()
                    app_data = j.get(str(appid), {})
                    if app_data.get("success") and "data" in app_data:
                        depots = app_data["data"].get("depots", {})
                        out = []
                        for depot_id, depot_info in depots.items():
                            if not isinstance(depot_info, dict): continue
                            manifest_info = depot_info.get("manifests", {}).get("public")
                            if not isinstance(manifest_info, dict): continue
                            
                            manifest_id = manifest_info.get("gid")
                            size = int(manifest_info.get("download", 0))
                            dlc_appid = depot_info.get("dlcappid")
                            source_label = f"DLC:{dlc_appid}" if dlc_appid else "主游戏"
                            
                            if manifest_id:
                                out.append((depot_id, manifest_id, size, source_label))
                        if out:
                            self.log.info(f"从 Steam 官方 API 成功获取到 {len(out)} 个Depot")
                            return out
                except Exception as e:
                    self.log.warning(f"解析 Steam 官方 API Depot 信息失败 ({api_url}): {e}")
                    continue
        
        self.log.info(f"未找到 AppID {appid} 的Depot信息（已尝试所有数据源）")
        return []

    def extract_workshop_id(self, input_text: str) -> str | None:
        """Extract workshop ID from URL or direct ID input"""
        input_text = input_text.strip()
        if not input_text:
            return None
        
        url_match = re.search(r"https?://steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)", input_text)
        if url_match:
            return url_match.group(1)
        
        if input_text.isdigit():
            return input_text
        
        return None


    async def _get_session_token(self) -> str | None:
        """获取manifest.steam.run会话令牌"""
        
        backup_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        
        try:
            self.log.info("正在获取会话令牌...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://manifest.steam.run/",
                "Origin": "https://manifest.steam.run",
                "Accept": "application/json, text/plain, */*",
            }
            
            session_resp = await self.client.post(
                "https://manifest.steam.run/api/session", 
                headers=headers,
                timeout=30
            )
            
            if session_resp.status_code == 200:
                data = session_resp.json()
                if "token" in data:
                    token = data["token"]
                    self.log.info(f"成功获取会话令牌: ...{token[-6:]}")
                    return token
            
            self.log.warning("会话令牌获取失败，使用备用令牌")
            
        except Exception as e:
            self.log.warning(f"获取会话令牌时出错: {e}，使用备用令牌")
        
        return backup_token


    async def get_workshop_depot_info(self, workshop_id: str) -> Tuple[str, str, str, str, str] | None:
        """Get depot and manifest info for workshop item with title"""
        try:
            self.log.info(f"正在查询创意工坊物品 {workshop_id} 的信息...")
            api_url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
            data = {
                'itemcount': 1,
                'publishedfileids[0]': workshop_id
            }
            
            max_retries, retry_delay = 3, 2
            for attempt in range(max_retries):
                try:
                    response = await self.client.post(api_url, data=data, timeout=30)
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    if 'response' not in result or 'publishedfiledetails' not in result['response'] or not result['response']['publishedfiledetails']:
                        self.log.error("API响应格式不正确或未找到物品详情")
                        return None
                    
                    details = result['response']['publishedfiledetails'][0]
                    
                    if int(details.get('result', 0)) != 1:
                        self.log.error(f"未找到创意工坊物品 {workshop_id}")
                        return None
                    
                    consumer_app_id = details.get('consumer_app_id')
                    hcontent_file = details.get('hcontent_file')
                    title = details.get('title', '未知标题')
                    file_url = details.get('file_url') or None
                    file_name = details.get('filename', 'resource.bin')

                    if not consumer_app_id or not hcontent_file:
                        self.log.error(f"创意工坊物品 '{title}' 缺少必要的信息 (App ID 或 Manifest ID)。")
                        return None

                    self.log.info(f"成功获取创意工坊物品信息:")
                    self.log.info(f"  标题: {title}")
                    self.log.info(f"  所属游戏 AppID: {consumer_app_id}")
                    self.log.info(f"  清单 ManifestID: {hcontent_file}")
                    if file_url:
                        self.log.info(f"  资源直链: {file_url}")
                    return str(consumer_app_id), str(hcontent_file), title, file_url, file_name
                    
                except httpx.RequestError as e:
                    if attempt < max_retries - 1:
                        self.log.warning(f"API请求失败，正在重试 ({attempt+1}/{max_retries})...")
                        await asyncio.sleep(retry_delay)
                    else:
                        self.log.error(f"API请求失败: {e}")
                        return None
                except Exception as e:
                    self.log.error(f"获取创意工坊物品信息出错: {self.stack_error(e)}")
                    return None
                    
        except Exception as e:
            self.log.error(f"获取创意工坊物品信息时发生错误: {self.stack_error(e)}")
            return None


    async def check_workshop_exists(self, workshop_id: str) -> Dict:
        """下载前先检测创意工坊物品是否存在（GetPublishedFileDetails）。
        返回 {exists, title, consumer_app_id, banned, reason}。"""
        try:
            api_url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
            data = {'itemcount': 1, 'publishedfileids[0]': workshop_id}
            for attempt in range(3):
                try:
                    resp = await self.client.post(api_url, data=data, timeout=30)
                    resp.raise_for_status()
                    result = resp.json()
                    details = result.get('response', {}).get('publishedfiledetails', [])
                    if not details:
                        return {"exists": False, "title": "", "consumer_app_id": None,
                                "banned": False, "reason": "API 响应为空"}
                    d = details[0]
                    if int(d.get('result', 0)) != 1:
                        return {"exists": False, "title": "", "consumer_app_id": None,
                                "banned": False, "reason": d.get('banned_text') or "物品不存在或已删除"}
                    consumer_app_id = str(d.get('consumer_app_id'))
                    title = d.get('title', '未知标题')
                    local_exists = False
                    if self.steam_path:
                        dl = self.steam_path / 'workshop' / 'downloads' / consumer_app_id / workshop_id
                        depot = self.steam_path / 'depotcache' / f"{consumer_app_id}_{d.get('hcontent_file')}.manifest"
                        local_exists = dl.is_dir() or depot.exists()
                    return {"exists": True, "title": title, "consumer_app_id": consumer_app_id,
                            "banned": False, "reason": "", "local_exists": local_exists}
                except httpx.RequestError as e:
                    if attempt < 2:
                        await asyncio.sleep(2)
                    else:
                        return {"exists": False, "title": "", "consumer_app_id": None,
                                "banned": False, "reason": f"网络请求失败: {e}"}
                except Exception as e:
                    return {"exists": False, "title": "", "consumer_app_id": None,
                            "banned": False, "reason": self.stack_error(e)}
        except Exception as e:
            return {"exists": False, "title": "", "consumer_app_id": None,
                    "banned": False, "reason": self.stack_error(e)}

    async def download_workshop_manifest(self, depot_id: str, manifest_id: str) -> bytes | None:
        """Download workshop manifest using new method from CLI version"""
        output_filename = f"{depot_id}_{manifest_id}.manifest"
        self.log.info(f"准备下载清单: {output_filename}")

        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                session_token = await self._get_session_token()
                if not session_token:
                    self.log.error("无法获取会话令牌")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                    return None
                
                self.log.info(f"正在请求清单下载链接... [Depot: {depot_id}, Manifest: {manifest_id}]")
                
                request_payload = {
                    "depot_id": str(depot_id),
                    "manifest_id": str(manifest_id),
                    "token": session_token
                }
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://manifest.steam.run/",
                    "Origin": "https://manifest.steam.run",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json"
                }
                
                await asyncio.sleep(2)
                
                code_response = await self.client.post(
                    "https://manifest.steam.run/api/request-code",
                    json=request_payload,
                    headers=headers,
                    timeout=60
                )
                
                if code_response.status_code == 429:
                    self.log.warning(f"请求频率过高，等待后重试...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(30)
                        continue
                    return None
                
                if code_response.status_code != 200:
                    self.log.error(f"请求失败，状态码: {code_response.status_code}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(10)
                        continue
                    return None
                
                try:
                    code_data = code_response.json()
                except:
                    self.log.error("服务器返回无效的JSON响应")
                    if attempt < max_retries - 1:
                        continue
                    return None
                
                download_url = code_data.get("download_url")
                if not download_url:
                    error_msg = code_data.get('error', code_data.get('message', '未知错误'))
                    self.log.error(f"请求下载链接失败: {error_msg}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(15)
                        continue
                    return None
                
                self.log.info(f"获取到下载链接")
                
                self.log.info("正在下载清单文件...")
                manifest_response = await self.client.get(download_url, timeout=180)
                
                if manifest_response.status_code != 200:
                    self.log.error(f"下载失败，状态码: {manifest_response.status_code}")
                    if attempt < max_retries - 1:
                        continue
                    return None
                
                manifest_content = manifest_response.content
                
                final_content = None
                
                if manifest_content.startswith(b'PK\x03\x04'):
                    self.log.info("检测到ZIP文件，正在自动解压...")
                    try:
                        with io.BytesIO(manifest_content) as mem_zip:
                            with zipfile.ZipFile(mem_zip, 'r') as z:
                                file_list = z.namelist()
                                if len(file_list) == 1:
                                    target_file = file_list[0]
                                    self.log.info(f"从ZIP中提取文件: {target_file}")
                                    final_content = z.read(target_file)
                                else:
                                    self.log.warning(f"ZIP包中文件数量不为1: {len(file_list)}")
                                    final_content = manifest_content
                    except Exception as e:
                        self.log.warning(f"处理ZIP文件时出错: {e}")
                        final_content = manifest_content
                else:
                    self.log.info("文件不是ZIP，将直接保存。")
                    final_content = manifest_content
                
                if not final_content:
                    self.log.error("最终文件内容为空")
                    if attempt < max_retries - 1:
                        continue
                    return None
                
                self.log.info(f"成功下载创意工坊清单，大小: {len(final_content)} 字节")
                return final_content
                
            except Exception as e:
                self.log.error(f"下载过程中出错: {e}")
                if attempt < max_retries - 1:
                    self.log.info(f"等待后重试... (尝试 {attempt + 2}/{max_retries})")
                    await asyncio.sleep(15)
                    continue
        
        self.log.error(f"下载清单 {output_filename} 失败：所有重试都失败了")
        return None

    async def process_workshop_item(self, workshop_input: str, download_resources: bool = True, copy_to_depot: bool = False) -> bool:
        """处理创意工坊物品：优先下载资源文件，可选同时写入 depotcache 清单。"""
        workshop_id = self.extract_workshop_id(workshop_input)
        if not workshop_id:
            self.log.error(f"无法从输入中提取有效的创意工坊ID: {workshop_input}")
            return False

        details = await self.get_workshop_depot_info(workshop_id)
        if not details:
            return False

        consumer_app_id, hcontent_file, title, file_url, file_name = details
        success_count = 0

        if download_resources:
            if file_url:
                downloaded = await self._download_workshop_resource(file_url, consumer_app_id, workshop_id, file_name)
                if downloaded:
                    success_count += 1
            else:
                self.log.warning("该创意工坊物品未提供官方资源直链，将跳过资源下载。可勾选“写入 depotcache 清单”让 Steam 客户端下载。")

        if copy_to_depot:
            manifest_content = await self.download_workshop_manifest(consumer_app_id, hcontent_file)
            if manifest_content:
                try:
                    output_filename = f"{consumer_app_id}_{hcontent_file}.manifest"
                    depot_cache_path = self.steam_path / 'depotcache'
                    depot_cache_path.mkdir(parents=True, exist_ok=True)
                    depot_file_path = depot_cache_path / output_filename
                    async with aiofiles.open(depot_file_path, 'wb') as f:
                        await f.write(manifest_content)
                    self.log.info(f"清单文件已保存到: {depot_file_path}")
                    success_count += 1
                except Exception as e:
                    self.log.error(f"保存创意工坊清单文件时出错: {self.stack_error(e)}")

        if success_count > 0:
            self.log.info(f"创意工坊物品处理完成。标题: {title}")
            return True
        else:
            self.log.error("未成功执行任何操作。")
            return False

    async def _download_workshop_resource(self, url: str, appid: str, workshop_id: str, file_name: str) -> bool:
        """下载创意工坊资源文件到 Steam/workshop/downloads/{appid}/{workshop_id}/"""
        try:
            self.log.info(f"正在下载创意工坊资源: {file_name}")
            r = await self.client.get(url, timeout=180)
            r.raise_for_status()
            data = r.content
            if not data:
                self.log.error("资源文件为空")
                return False

            out_dir = self.steam_path / 'workshop' / 'downloads' / appid / workshop_id
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / file_name
            async with aiofiles.open(out_path, 'wb') as f:
                await f.write(data)
            self.log.info(f"资源文件已保存到: {out_path} ({len(data)} 字节)")

            if file_name.lower().endswith('.zip'):
                try:
                    import zipfile
                    with zipfile.ZipFile(out_path, 'r') as z:
                        z.extractall(out_dir)
                    self.log.info(f"已自动解压资源到: {out_dir}")
                except Exception as e:
                    self.log.warning(f"自动解压资源失败: {e}")
            return True
        except Exception as e:
            self.log.error(f"下载创意工坊资源失败: {self.stack_error(e)}")
            return False

    async def _get_buqiuren_session_token(self) -> str | None:
        """获取不求人接口的会话令牌"""
        backup_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://manifest.steam.run/",
                "Origin": "https://manifest.steam.run",
                "Accept": "application/json, text/plain, */*",
            }
            
            session_resp = await self.client.post(
                "https://manifest.steam.run/api/session", 
                headers=headers,
                timeout=30
            )
            
            if session_resp.status_code == 200:
                data = session_resp.json()
                if "token" in data:
                    token = data["token"]
                    self.log.info(f"成功获取不求人会话令牌: ...{token[-6:]}")
                    return token
            
            self.log.warning("使用备用令牌")
            
        except Exception as e:
            self.log.warning(f"获取不求人会话令牌时出错: {e}")
        
        return backup_token

    async def _download_manifest_buqiuren(self, depot_id: str, manifest_id: str, depot_name: str) -> bool:
        """使用不求人接口下载清单"""
        output_filename = f"{depot_id}_{manifest_id}.manifest"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                session_token = await self._get_buqiuren_session_token()
                if not session_token:
                    self.log.error("无法获取会话令牌")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                    return False
                
                self.log.info(f"正在请求清单下载链接... [Depot: {depot_id}, Manifest: {manifest_id}]")
                
                request_payload = {
                    "depot_id": str(depot_id),
                    "manifest_id": str(manifest_id),
                    "token": session_token
                }
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://manifest.steam.run/",
                    "Origin": "https://manifest.steam.run",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json"
                }
                
                await asyncio.sleep(random.uniform(2, 5))
                
                code_response = await self.client.post(
                    "https://manifest.steam.run/api/request-code",
                    json=request_payload,
                    headers=headers,
                    timeout=60
                )
                
                if code_response.status_code == 429:
                    self.log.warning(f"请求频率过高，等待后重试...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(30)
                        continue
                    return False
                
                if code_response.status_code != 200:
                    self.log.error(f"请求失败，状态码: {code_response.status_code}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(10)
                        continue
                    return False
                
                try:
                    code_data = code_response.json()
                except:
                    self.log.error("服务器返回无效的JSON响应")
                    if attempt < max_retries - 1:
                        continue
                    return False
                
                download_url = code_data.get("download_url")
                if not download_url:
                    error_msg = code_data.get('error', code_data.get('message', '未知错误'))
                    self.log.error(f"请求下载链接失败: {error_msg}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(15)
                        continue
                    return False
                
                self.log.info(f"获取到下载链接")
                
                self.log.info("正在下载清单文件...")
                manifest_response = await self.client.get(download_url, timeout=180)
                
                if manifest_response.status_code != 200:
                    self.log.error(f"下载失败，状态码: {manifest_response.status_code}")
                    if attempt < max_retries - 1:
                        continue
                    return False
                
                manifest_content = manifest_response.content
                
                final_content = None
                
                if manifest_content.startswith(b'PK\x03\x04'):
                    self.log.info("检测到ZIP文件，正在自动解压...")
                    try:
                        with io.BytesIO(manifest_content) as mem_zip:
                            with zipfile.ZipFile(mem_zip, 'r') as z:
                                file_list = z.namelist()
                                if len(file_list) == 1:
                                    target_file = file_list[0]
                                    self.log.info(f"从ZIP中提取文件: {target_file}")
                                    final_content = z.read(target_file)
                                else:
                                    self.log.warning(f"ZIP包中文件数量不为1: {len(file_list)}")
                                    final_content = manifest_content
                    except Exception as e:
                        self.log.warning(f"处理ZIP文件时出错: {e}")
                        final_content = manifest_content
                else:
                    final_content = manifest_content
                
                if not final_content:
                    self.log.error("最终文件内容为空")
                    if attempt < max_retries - 1:
                        continue
                    return False
                
                if self.unlocker_type in ("steamtools", "opensteamtool"):
                    st_depot_path = self.steam_path / 'config' / 'depotcache'
                    gl_depot_path = self.steam_path / 'depotcache'
                    
                    st_depot_path.mkdir(parents=True, exist_ok=True)
                    gl_depot_path.mkdir(parents=True, exist_ok=True)
                    
                    (st_depot_path / output_filename).write_bytes(final_content)
                    self.log.info(f"清单已保存到: {st_depot_path / output_filename}")
                    
                    (gl_depot_path / output_filename).write_bytes(final_content)
                    self.log.info(f"清单已保存到: {gl_depot_path / output_filename}")
                else:
                    depot_path = self.steam_path / 'depotcache'
                    depot_path.mkdir(parents=True, exist_ok=True)
                    (depot_path / output_filename).write_bytes(final_content)
                    self.log.info(f"清单已保存到: {depot_path / output_filename}")
                
                self.log.info(f"成功下载清单: {depot_name} ({output_filename})")
                return True
                
            except Exception as e:
                self.log.error(f"下载过程中出错: {e}")
                if attempt < max_retries - 1:
                    self.log.info(f"等待后重试... (尝试 {attempt + 2}/{max_retries})")
                    await asyncio.sleep(15)
                    continue
        
        self.log.error(f"下载清单 {output_filename} 失败：所有重试都失败了")
        return False

    async def _get_cached_sudama_data(self) -> Dict:
        """
        核心函数：获取 Sudama 密钥数据
        逻辑：检查本地 sudama_cache.json -> 检查时间戳是否超过24小时 -> 下载或读取缓存
        """
        cache_file = self.project_root / "sudama_cache.json"
        current_time = time.time()
        one_day_seconds = 86400

        if cache_file.exists():
            try:
                async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                    cache_content = json.loads(await f.read())
                
                last_update = cache_content.get('timestamp', 0)
                if current_time - last_update < one_day_seconds:
                    self.log.info(f"使用本地缓存的密钥库 (上次更新: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_update))})")
                    return cache_content.get('data', {})
                else:
                    self.log.info("本地密钥缓存已超过24小时，准备从服务器同步最新数据...")
            except Exception as e:
                self.log.warning(f"读取本地缓存失败，将重新下载: {e}")

        url = "https://api.993499094.xyz/depotkeys.json"
        try:
            self.log.info(f"正在从 Sudama API ({url}) 下载全量密钥库...")
            response = await self.client.get(url, timeout=120)
            response.raise_for_status()
            
            data = response.json()
            
            if not isinstance(data, dict):
                self.log.error("API 返回的数据格式不正确 (应为 JSON 对象)")
                return {}

            cache_data = {
                "timestamp": current_time,
                "data": data
            }
            async with aiofiles.open(cache_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(cache_data, ensure_ascii=False))
            
            self.log.info(f"密钥库下载完成并缓存，共 {len(data)} 条数据。")
            return data

        except Exception as e:
            self.log.error(f"下载 Sudama 数据失败: {self.stack_error(e)}")
            if cache_file.exists():
                try:
                    self.log.warning("网络获取失败，尝试使用旧的本地缓存...")
                    async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                        return json.loads(await f.read()).get('data', {})
                except:
                    pass
            return {}


    async def _get_sudama_data(self) -> Dict[str, str]:
        """从 sudama API 获取所有密钥数据 (兼容性包装)"""
        return await self._get_cached_sudama_data()

    async def process_sudama_manifest(self, app_id: str, unlocker_type: str, use_st_auto_update: bool, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        """处理 Sudama 库清单"""
        try:
            self.log.info(f'正从 Sudama 库处理 AppID {app_id} 的清单...')
            
            depot_manifest_map = await self._get_depots_and_manifests_from_steamui(app_id)
            if not depot_manifest_map:
                self.log.error(f"未能从 API 获取到 AppID {app_id} 的 depot 信息")
                return False
            
            self.log.info(f"获取到 {len(depot_manifest_map)} 个 depot 及其 manifest")

            sudama_keys = await self._get_cached_sudama_data()
            if not sudama_keys:
                self.log.error("无法获取 Sudama 密钥库数据")
                return False

            valid_depots = {}
            for depot_id in depot_manifest_map.keys():
                if depot_id in sudama_keys:
                    key = sudama_keys[depot_id]
                    if key and str(key).strip():
                        valid_depots[depot_id] = str(key).strip()
                        self.log.info(f"在 Sudama 库中找到 depot {depot_id} 的密钥")
                else:
                    self.log.warning(f"Sudama 库中未找到 depot {depot_id} 的密钥")

            if not valid_depots:
                self.log.warning(f"AppID {app_id} 没有在 Sudama 库中找到任何有效的 depot 密钥")
                return False

            if unlocker_type in ("steamtools", "opensteamtool"):
                return await self._process_steamautocracks_v2_for_steamtools(
                    app_id, valid_depots, depot_manifest_map, use_st_auto_update, add_all_dlc, patch_depot_key, sudama_keys
                )
            else:
                return await self._process_steamautocracks_v2_for_greenluma(app_id, valid_depots)

        except Exception as e:
            self.log.error(f'处理 Sudama 库清单时出错: {self.stack_error(e)}')
            return False
            
            
    async def process_buqiuren_manifest(self, app_id: str) -> bool:
        """处理不求人库清单下载"""
        try:
            self.log.info(f'正从 清单不求人库 处理 AppID {app_id} 的清单...')
            
            depot_manifest_map = await self._get_depots_and_manifests_from_steamui(app_id)
            if not depot_manifest_map:
                self.log.error(f"未能从 steamui API 获取到 AppID {app_id} 的 depot 信息，请检查APP ID是否正确或API请求问题")
                return False
            
            self.log.info(f"从 steamui API 获取到 {len(depot_manifest_map)} 个 depot 及其 manifest")
            
            success_count = 0
            total_count = len(depot_manifest_map)
            
            for i, (depot_id, manifest_id) in enumerate(depot_manifest_map.items(), 1):
                self.log.info(f"处理进度: {i}/{total_count}")
                depot_name = f"Depot {depot_id}"
                
                if await self._download_manifest_buqiuren(depot_id, manifest_id, depot_name):
                    success_count += 1
                else:
                    self.log.warning(f"下载 depot {depot_id} 的清单失败")
                
                if i < total_count:
                    delay = random.uniform(10, 20)
                    self.log.info(f"等待 {delay:.1f} 秒后继续...")
                    await asyncio.sleep(delay)
            
            if success_count == 0:
                self.log.error(f"AppID {app_id} 没有成功下载任何清单")
                return False
            
            self.log.info(f"成功处理不求人库清单: 成功 {success_count}/{total_count}")
            return True
            
        except Exception as e:
            self.log.error(f'处理不求人库清单时出错: {self.stack_error(e)}')
            return False

    async def download_depotkeys_json(self) -> Dict | None:
        """
        获取 DepotKeys 数据。
        已修改：不再从 GitHub/ManifestHub 下载，而是直接复用 Sudama API 的缓存逻辑。
        这样 '修补创意工坊密钥' 功能也会使用 Sudama 的数据源。
        """
        self.log.info("正在获取 DepotKeys (来源: Sudama API)...")
        return await self._get_cached_sudama_data()

    async def process_steamautocracks_v2_manifest(self, app_id: str, unlocker_type: str, use_st_auto_update: bool, add_all_dlc: bool = False, patch_depot_key: bool = False) -> bool:
        """处理 SteamAutoCracks/ManifestHub(2) 清单库 - 使用 steamui API 获取 depot 和 manifest 信息"""
        try:
            self.log.info(f'正从 SteamAutoCracks/ManifestHub(2) 处理 AppID {app_id} 的清单...')
            
            depot_manifest_map = await self._get_depots_and_manifests_from_steamui(app_id)
            if not depot_manifest_map:
                self.log.error(f"未能从 steamui API 获取到 AppID {app_id} 的 depot 信息，请检查APP ID是否正确或API请求问题")
                return False
            
            self.log.info(f"从 steamui API 获取到 {len(depot_manifest_map)} 个 depot 及其 manifest")
            
            if 'IS_CN' not in os.environ:
                self.log.info("检测网络环境以优化下载源选择...")
                await self.checkcn()
            
            depotkeys_data = await self.download_depotkeys_json()
            if not depotkeys_data:
                self.log.error("无法获取 depotkeys 数据")
                return False
            
            valid_depots = {}
            for depot_id in depot_manifest_map.keys():
                if depot_id in depotkeys_data:
                    depotkey = depotkeys_data[depot_id]
                    if depotkey and str(depotkey).strip():
                        valid_depots[depot_id] = str(depotkey).strip()
                        self.log.info(f"找到 depot {depot_id} 的有效 depotkey: {depotkey}")
                    else:
                        self.log.warning(f"depot {depot_id} 的 depotkey 为空，自动跳过")
                else:
                    self.log.warning(f"未找到 depot {depot_id} 的 depotkey，自动跳过")
            
            if not valid_depots:
                self.log.warning(f"AppID {app_id} 没有找到任何有效的 depot 密钥，这是正常情况，可能此APP ID没有创意工坊密钥或者暂未收录，不影响本体使用")
                return False
            
            if unlocker_type in ("steamtools", "opensteamtool"):
                return await self._process_steamautocracks_v2_for_steamtools(app_id, valid_depots, depot_manifest_map, use_st_auto_update, add_all_dlc, patch_depot_key, depotkeys_data)
            else:
                return await self._process_steamautocracks_v2_for_greenluma(app_id, valid_depots)
                
        except Exception as e:
            self.log.error(f'处理 SteamAutoCracks/ManifestHub(2) 清单时出错: {self.stack_error(e)}')
            return False

    async def _get_depots_and_manifests_from_ddxnb(self, app_id: str) -> Dict[str, str]:
        """从备用API (steam.ddxnb.cn) 获取 depot 和对应的 manifest 信息"""
        try:
            url = f"https://steam.ddxnb.cn/v1/info/{app_id}"
            response = await self.client.get(url, timeout=20)
            response.raise_for_status()

            data = response.json()
            
            if data.get("status") != "success" or not data.get("data"):
                self.log.error(f"备用API返回错误或无数据 for AppID {app_id}，请检查APP ID是否正确或API请求问题")
                return {}

            app_data = data["data"].get(app_id)
            if not app_data or "depots" not in app_data:
                self.log.error(f"备用API响应中未找到 AppID {app_id} 的 depots 信息，请检查APP ID是否正确或API请求问题")
                return {}
            
            depots = app_data["depots"]
            depot_manifest_map = {}

            for depot_id, depot_info in depots.items():
                if not depot_id.isdigit():
                    continue

                if isinstance(depot_info, dict):
                    manifests = depot_info.get("manifests", {})
                    public_manifest = manifests.get("public", {})
                    manifest_id = public_manifest.get("gid")

                    if manifest_id:
                        depot_manifest_map[depot_id] = str(manifest_id)
                        self.log.info(f"从备用API发现有效 depot: {depot_id}, manifest: {manifest_id}")

            if depot_manifest_map:
                self.log.info(f"从备用API总共找到 {len(depot_manifest_map)} 个有效的 depot 及其 manifest")
            else:
                self.log.warning(f"备用API未找到 AppID {app_id} 的任何有效 depot-manifest 映射，请检查APP ID是否正确或API请求问题")

            return depot_manifest_map

        except Exception as e:
            self.log.error(f"从备用API (steam.ddxnb.cn) 获取 depot 信息失败: {e}")
            return {}

    async def _get_depots_and_manifests_from_steamui(self, app_id: str) -> Dict[str, str]:
        """从 steamui API 获取 depot 和对应的 manifest 信息，失败时使用备用API"""
        vdf_content = ""
        try:
            self.log.info(f"正从主API (steamui.com) 获取 AppID {app_id} 的信息...")
            url = f"https://steamui.com/api/get_appinfo.php?appid={app_id}"
            response = await self.client.get(url, timeout=20)
            response.raise_for_status()
            
            vdf_content = response.text
            
            import vdf
            data = vdf.loads(vdf_content)
            
            depot_manifest_map = {}
            
            for key, value in data.items():
                if key.isdigit() and isinstance(value, dict):
                    if 'manifests' in value and value['manifests']:
                        manifests = value['manifests']
                        if isinstance(manifests, dict) and 'public' in manifests:
                            public_manifest = manifests['public']
                            if isinstance(public_manifest, dict) and 'gid' in public_manifest:
                                manifest_id = public_manifest['gid']
                                depot_manifest_map[key] = manifest_id
            
            if not depot_manifest_map:
                if 'depots' in data:
                    depots = data['depots']
                    for depot_id, depot_info in depots.items():
                        if depot_id.isdigit() and isinstance(depot_info, dict):
                            if 'manifests' in depot_info and depot_info['manifests']:
                                manifests = depot_info['manifests']
                                if isinstance(manifests, dict) and 'public' in manifests:
                                    public_manifest = manifests['public']
                                    if isinstance(public_manifest, dict) and 'gid' in public_manifest:
                                        manifest_id = public_manifest['gid']
                                        depot_manifest_map[depot_id] = manifest_id
                
                if not depot_manifest_map:
                    for key, value in data.items():
                        if isinstance(value, dict) and 'depots' in value:
                            depots = value['depots']
                            for depot_id, depot_info in depots.items():
                                if depot_id.isdigit() and isinstance(depot_info, dict):
                                    if 'manifests' in depot_info and depot_info['manifests']:
                                        manifests = depot_info['manifests']
                                        if isinstance(manifests, dict) and 'public' in manifests:
                                            public_manifest = manifests['public']
                                            if isinstance(public_manifest, dict) and 'gid' in public_manifest:
                                                manifest_id = public_manifest['gid']
                                                depot_manifest_map[depot_id] = manifest_id

            if depot_manifest_map:
                self.log.info(f"从主API (steamui.com) 成功获取 {len(depot_manifest_map)} 个 depot。")
                return depot_manifest_map
            else:
                raise ValueError("主API响应成功，但未解析到任何depot信息，请检查APP ID是否正确或API请求问题")

        except Exception as e:
            self.log.warning(f"主API (steamui.com) 访问或解析失败: {e}。")
            if vdf_content:
                self.log.warning(f"主API返回内容预览: {vdf_content[:300]}...")
            self.log.info("正在尝试备用API (steam.ddxnb.cn)...")
        
        return await self._get_depots_and_manifests_from_ddxnb(app_id)

    async def _process_steamautocracks_v2_for_steamtools(self, app_id: str, valid_depots: Dict[str, str], depot_manifest_map: Dict[str, str], use_st_auto_update: bool, add_all_dlc: bool, patch_depot_key: bool, depotkeys_data: Dict) -> bool:
        """为 SteamTools 处理 SteamAutoCracks/ManifestHub(2) 清单"""
        try:
            stplug_path = self.lua_output_dir()
            
            lua_filename = f"{app_id}.lua"
            lua_filepath = stplug_path / lua_filename
            
            is_auto_update_mode = use_st_auto_update
            
            lines = []
            
            lines.append(f'addappid({app_id})')
            
            for depot_id, depotkey in valid_depots.items():
                lines.append(f'addappid({depot_id}, 1, "{depotkey}")')
            
            manifest_lines = []
            for depot_id in valid_depots.keys():
                if depot_id in depot_manifest_map:
                    manifest_id = depot_manifest_map[depot_id]
                    if is_auto_update_mode:
                        manifest_lines.append(f'--setManifestid({depot_id}, "{manifest_id}")')
                        self.log.info(f"添加注释的 manifest 映射（自动更新模式）: depot {depot_id} -> manifest {manifest_id}")
                    else:
                        manifest_lines.append(f'setManifestid({depot_id}, "{manifest_id}")')
                        self.log.info(f"添加 manifest 映射（固定版本）: depot {depot_id} -> manifest {manifest_id}")
            
            async with aiofiles.open(lua_filepath, mode="w", encoding="utf-8") as lua_file:
                await lua_file.write('\n'.join(lines) + '\n')
                if manifest_lines:
                    await lua_file.write('\n-- Manifests\n')
                    await lua_file.write('\n'.join(manifest_lines) + '\n')
            
            self.log.info(f"已为SteamTools生成解锁文件: {lua_filename}")
            
            if add_all_dlc:
                await self._add_free_dlcs_to_lua(app_id, lua_filepath)
            
            if patch_depot_key:
                self.log.info("开始修补创意工坊depotkey...")
                await self._patch_lua_with_existing_depotkeys(app_id, lua_filepath, depotkeys_data)
            
            return True
            
        except Exception as e:
            self.log.error(f'为 SteamTools 处理 SteamAutoCracks/ManifestHub(2) 清单时出错: {e}')
            return False

    async def _process_steamautocracks_v2_for_greenluma(self, app_id: str, valid_depots: Dict[str, str]) -> bool:
        """为 GreenLuma 处理 SteamAutoCracks/ManifestHub(2) 清单"""
        try:
            depots_config = {'depots': {depot_id: {"DecryptionKey": key} for depot_id, key in valid_depots.items()}}
            
            config_vdf_path = self.steam_path / 'config' / 'config.vdf'
            if await self.depotkey_merge(config_vdf_path, depots_config):
                self.log.info("已将密钥合并到 config.vdf")
            
            gl_ids = list(valid_depots.keys())
            gl_ids.append(app_id)
            await self.greenluma_add(list(set(gl_ids)))
            self.log.info("已添加到 GreenLuma")
            
            return True
            
        except Exception as e:
            self.log.error(f'为 GreenLuma 处理 SteamAutoCracks/ManifestHub(2) 清单时出错: {e}')
            return False
    
    async def _patch_lua_with_existing_depotkeys(self, app_id: str, lua_file_path: Path, depotkeys_data: Dict) -> bool:
        """使用已有的 depotkeys 数据修补 LUA 文件（避免重复下载）"""
        try:
            if app_id not in depotkeys_data:
                self.log.warning(f"没有此AppID的depotkey: {app_id}，这是正常情况，可能此APP ID没有创意功放密钥或者暂未收录，不影响本体使用")
                return False
            
            depotkey = depotkeys_data[app_id]
            
            if not depotkey or not str(depotkey).strip():
                self.log.warning(f"AppID {app_id} 的 depotkey 为空或无效，跳过修补: '{depotkey}，，这是正常情况，可能此APP ID没有创意功放密钥或者暂未收录，不影响本体使用'")
                return False
            
            depotkey = str(depotkey).strip()
            self.log.info(f"找到 AppID {app_id} 的有效 depotkey: {depotkey}")
            
            if not lua_file_path.exists():
                self.log.error(f"LUA文件不存在: {lua_file_path}")
                return False
            
            async with aiofiles.open(lua_file_path, 'r', encoding='utf-8') as f:
                lua_content = await f.read()
            
            lines = lua_content.strip().split('\n')
            new_lines = []
            app_id_line_removed = False
            
            for line in lines:
                line = line.strip()
                if line == f"addappid({app_id})":
                    new_lines.append(f'addappid({app_id},1,"{depotkey}")')
                    app_id_line_removed = True
                    self.log.info(f"已替换: addappid({app_id}) -> addappid({app_id},1,\"{depotkey}\")")
                else:
                    new_lines.append(line)
            
            if not app_id_line_removed:
                new_lines.append(f'addappid({app_id},1,"{depotkey}")')
                self.log.info(f"已添加新的 depotkey 条目: addappid({app_id},1,\"{depotkey}\")")
            
            async with aiofiles.open(lua_file_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(new_lines) + '\n')
            
            self.log.info(f"成功修补 LUA 文件的 depotkey: {lua_file_path.name}")
            return True
            
        except Exception as e:
            self.log.error(f"修补 LUA depotkey 时出错: {self.stack_error(e)}")
            return False

    async def patch_lua_with_depotkey(self, app_id: str, lua_file_path: Path) -> bool:
        """Patch LUA file with depotkey from SteamAutoCracks repository"""
        try:
            if 'IS_CN' not in os.environ:
                self.log.info("检测网络环境以优化下载源选择...")
                await self.checkcn()
            
            depotkeys_data = await self.download_depotkeys_json()
            if not depotkeys_data:
                self.log.error("无法获取 depotkeys 数据，跳过 depotkey 修补。")
                return False
            
            if app_id not in depotkeys_data:
                self.log.warning(f"没有此AppID的depotkey: {app_id}，，这是正常情况，可能此APP ID没有创意功放密钥或者暂未收录，不影响本体使用")
                return False
            
            depotkey = depotkeys_data[app_id]
            
            if not depotkey or not str(depotkey).strip():
                self.log.warning(f"AppID {app_id} 的 depotkey 为空或无效，跳过修补: '{depotkey}，这是正常情况，可能此APP ID没有创意功放密钥或者暂未收录，不影响本体使用'")
                return False
            
            depotkey = str(depotkey).strip()
            self.log.info(f"找到 AppID {app_id} 的有效 depotkey: {depotkey}")
            
            if not lua_file_path.exists():
                self.log.error(f"LUA文件不存在: {lua_file_path}")
                return False
            
            async with aiofiles.open(lua_file_path, 'r', encoding='utf-8') as f:
                lua_content = await f.read()
            
            lines = lua_content.strip().split('\n')
            new_lines = []
            app_id_line_removed = False
            
            for line in lines:
                line = line.strip()
                if line == f"addappid({app_id})":
                    new_lines.append(f'addappid({app_id},1,"{depotkey}")')
                    app_id_line_removed = True
                    self.log.info(f"已替换: addappid({app_id}) -> addappid({app_id},1,\"{depotkey}\")")
                else:
                    new_lines.append(line)
            
            if not app_id_line_removed:
                new_lines.append(f'addappid({app_id},1,"{depotkey}")')
                self.log.info(f"已添加新的 depotkey 条目: addappid({app_id},1,\"{depotkey}\")")
            
            async with aiofiles.open(lua_file_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(new_lines) + '\n')
            
            self.log.info(f"成功修补 LUA 文件的 depotkey: {lua_file_path.name}")
            return True
            
        except Exception as e:
            self.log.error(f"修补 LUA depotkey 时出错: {self.stack_error(e)}")
            return False

    def restart_steam(self) -> bool:
        if not self.steam_path:
            self.log.error("无法重启 Steam：未找到 Steam 路径。")
            return False
        steam_exe_path = self.steam_path / 'steam.exe'
        if not steam_exe_path.exists():
            self.log.error(f"无法启动 Steam：在 '{self.steam_path}' 目录下未找到 steam.exe。")
            return False
        try:
            self.log.info("正在尝试关闭正在运行的 Steam 进程...")
            res = close_steam()
            if res.get("already_closed"):
                self.log.info("未找到正在运行的 Steam 进程，将直接启动。")
            elif res.get("forced"):
                self.log.warning("Steam 没有自己退出，已强制结束进程。")
                try:
                    hc = Path(os.environ.get('LOCALAPPDATA', '')) / 'Steam' / 'htmlcache'
                    if hc.is_dir():
                        shutil.rmtree(hc, ignore_errors=True)
                        self.log.info("已清理可能被强杀写坏的 htmlcache。")
                except Exception:
                    pass
            else:
                self.log.info("Steam 已正常退出。")
            self.log.info("等待 3 秒以确保 Steam 完全关闭...")
            time.sleep(3)
            self.log.info(f"正在尝试从 '{steam_exe_path}' 启动 Steam...")
            subprocess.Popen([str(steam_exe_path)], creationflags=subprocess.DETACHED_PROCESS, close_fds=True)
            self.log.info("已发送重启 Steam 的指令。")
            return True
        except Exception as e:
            self.log.error(f"重启 Steam 失败: {self.stack_error(e)}")
            return False

    async def check_github_api_rate_limit(self) -> bool:
        github_token = self.config.get("Github_Personal_Token", "").strip()
        headers = {'Authorization': f'Bearer {github_token}'} if github_token else None
        if github_token: self.log.info("已配置GitHub Token。")
        else: self.log.warning("未找到GitHub Token。您的API请求将受到严格的速率限制。")
        url = 'https://api.github.com/rate_limit'
        try:
            r = await self.client.get(url, headers=headers)
            r.raise_for_status()
            rate_limit = r.json().get('resources', {}).get('core', {})
            remaining = rate_limit.get('remaining', 0)
            reset_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(rate_limit.get('reset', 0)))
            self.log.info(f'GitHub API剩余请求次数: {remaining}')
            if remaining == 0:
                self.log.error("GitHub API请求次数已用尽。")
                self.log.error(f"您的请求次数将于 {reset_time} 重置。")
                self.log.error("要提升请求上限，请在config.json文件中添加您的'Github_Personal_Token'。")
                return False
            return True
        except Exception as e:
            self.log.error(f'检查GitHub API速率限制失败: {self.stack_error(e)}')
            return False

    async def checkcn(self) -> bool:
        try:
            req = await self.client.get('https://mips.kugou.com/check/iscn?&format=json', timeout=5)
            body = req.json()
            is_cn = bool(body['flag'])
            os.environ['IS_CN'] = 'yes' if is_cn else 'no'
            if is_cn: self.log.info(f"检测到区域为中国大陆 ({body['country']})。将使用国内镜像。")
            else: self.log.info(f"检测到区域为非中国大陆 ({body['country']})。将直接使用GitHub。")
            return is_cn
        except Exception:
            os.environ['IS_CN'] = 'yes'
            self.log.warning('无法确定服务器位置，默认您在中国大陆。')
            return True

    def parse_lua_file_for_depots(self, lua_file_path: str) -> Dict:
        addappid_pattern = re.compile(r'addappid\((\d+),\s*1,\s*"([^"]+)"\)')
        depots = {}
        try:
            with open(lua_file_path, 'r', encoding='utf-8') as file:
                lua_content = file.read()
                for match in addappid_pattern.finditer(lua_content):
                    depots[match.group(1)] = {"DecryptionKey": match.group(2)}
        except Exception as e:
            self.log.error(f"解析lua文件 {lua_file_path} 出错: {e}")
        return depots

    async def depotkey_merge(self, config_path: Path, depots_config: dict) -> bool:
        if not config_path.exists():
            self.log.error('未找到Steam默认配置文件，您可能尚未登录。')
            return False
        try:
            async with aiofiles.open(config_path, encoding='utf-8') as f: content = await f.read()
            config_vdf = vdf.loads(content)
            steam = config_vdf.get('InstallConfigStore', {}).get('Software', {}).get('Valve') or \
                    config_vdf.get('InstallConfigStore', {}).get('Software', {}).get('valve')
            if steam is None:
                self.log.error('找不到Steam配置节。')
                return False
            depots = steam.setdefault('depots', {})
            depots.update(depots_config.get('depots', {}))
            async with aiofiles.open(config_path, mode='w', encoding='utf-8') as f:
                await f.write(vdf.dumps(config_vdf, pretty=True))
            self.log.info('成功将密钥合并到config.vdf。')
            return True
        except Exception as e:
            self.log.error(f'合并失败: {self.stack_error(e)}')
            return False

    async def _get_from_mirrors(self, sha: str, path: str, repo: str) -> bytes:
        """按可用性排序依次尝试下载。
        2026-09 实测：raw.githubusercontent.com 与 jsdelivr(cdn/fastly/gcore) 在国内可用，
        而 gh-proxy.org / cdn.gh-proxy.org / edgeone / fastgit / gh.llkk.cc / gh.akass.cn
        这些老代理全部超时或 404，所以把它们放到末尾做兜底。"""
        urls = [
            f'https://raw.githubusercontent.com/{repo}/{sha}/{path}',
            f'https://cdn.jsdelivr.net/gh/{repo}@{sha}/{path}',
            f'https://fastly.jsdelivr.net/gh/{repo}@{sha}/{path}',
            f'https://gcore.jsdelivr.net/gh/{repo}@{sha}/{path}',
            f'https://gh-proxy.com/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
            f'https://ghps.cc/https://github.com/{repo}/{sha}/{path}',
            f'https://ghproxy.cn/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
            f'https://ghproxy.net/https://raw.githubusercontent.com/{repo}/{sha}/{path}',
            f'https://gh-proxy.org/https://github.com/{repo}/{sha}/{path}',
            f'https://edgeone.gh-proxy.org/https://github.com/{repo}/{sha}/{path}',
            f'https://cdn.gh-proxy.org/https://github.com/{repo}/{sha}/{path}',
        ]
        last_error = ''
        for url in urls:
            try:
                r = await self.client.get(url, timeout=30)
                if r.status_code == 200:
                    self.log.info(f'下载成功: {path} (来自 {url.split("/")[2]})')
                    return r.content
                last_error = f'状态码: {r.status_code}'
                self.log.error(f'下载失败: {path} (来自 {url.split("/")[2]}) - {last_error}')
            except httpx.RequestError as e:
                last_error = f'错误: {type(e).__name__}'
                self.log.error(f'下载失败: {path} (来自 {url.split("/")[2]}) - {last_error}')
        raise Exception(f'尝试所有镜像后仍无法下载文件: {path}（最后错误 {last_error}）')

    async def greenluma_add(self, depot_id_list: list) -> bool:
        app_list_path = self.steam_path / 'AppList'
        try:
            for file in app_list_path.glob('*.txt'): file.unlink(missing_ok=True)
            depot_dict = { int(i.stem): int(i.read_text(encoding='utf-8').strip()) for i in app_list_path.iterdir() if i.is_file() and i.stem.isdecimal() and i.suffix == '.txt' }
            for depot_id in map(int, depot_id_list):
                if depot_id not in depot_dict.values():
                    index = max(depot_dict.keys(), default=-1) + 1
                    (app_list_path / f'{index}.txt').write_text(str(depot_id), encoding='utf-8')
                    depot_dict[index] = depot_id
            self.log.info(f"成功将 {len(depot_id_list)} 个ID添加到GreenLuma的AppList中。")
            return True
        except Exception as e:
            self.log.error(f'GreenLuma添加 AppID失败: {e}')
            return False
            
    async def _get_steamcmd_api_data(self, appid: str) -> Dict:
        try:
            resp = await self.client.get(f"https://api.steamcmd.net/v1/info/{appid}", timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.log.error(f"从 api.steamcmd.net 获取 AppID {appid} 数据失败: {e}")
            return {}

    async def _get_dlc_ids(self, appid: str) -> List[str]:
        """获取DLC ID列表，使用新的安全函数"""
        return await self.get_dlc_ids_safe(appid)

    async def _get_depots(self, appid: str) -> List[Dict]:
        """获取Depot信息列表，转换为旧格式兼容"""
        depot_tuples = await self.get_depots_safe(appid)
        return [
            {
                "depot_id": depot_id,
                "size": size,
                "dlc_appid": source.split(':')[1] if source.startswith('DLC:') else None
            }
            for depot_id, manifest_id, size, source in depot_tuples
        ]

    async def _add_free_dlcs_to_lua(self, app_id: str, lua_filepath: Path):
        self.log.info(f"开始为 AppID {app_id} 查找无密钥/无Depot的DLC...")
        try:
            all_dlc_ids = await self._get_dlc_ids(app_id)
            if not all_dlc_ids:
                self.log.info(f"AppID {app_id} 未找到任何DLC。")
                return

            tasks = [self._get_depots(dlc_id) for dlc_id in all_dlc_ids]
            results = await asyncio.gather(*tasks)

            depot_less_dlc_ids = [dlc_id for dlc_id, dlc_depots in zip(all_dlc_ids, results) if not dlc_depots]
            
            if not depot_less_dlc_ids:
                self.log.info(f"未找到适用于 AppID {app_id} 的无密钥/无Depot的DLC。")
                return

            async with self.lock:
                if not lua_filepath.exists():
                    self.log.error(f"目标LUA文件 {lua_filepath} 不存在，无法合并DLC。")
                    return

                async with aiofiles.open(lua_filepath, 'r', encoding='utf-8') as f:
                    existing_lines = [line.strip() for line in await f.readlines() if line.strip()]
                
                existing_appids = {match.group(1) for line in existing_lines if (match := re.search(r'addappid\((\d+)', line))}
                new_dlcs_to_add = [dlc_id for dlc_id in depot_less_dlc_ids if dlc_id not in existing_appids]
                
                if not new_dlcs_to_add:
                    self.log.info(f"所有找到的无Depot DLC均已存在于解锁文件中。无需添加。")
                    return

                self.log.info(f"找到 {len(new_dlcs_to_add)} 个新的无密钥/无Depot DLC，正在合并到 LUA 文件...")

                final_lines = set(existing_lines)
                for dlc_id in new_dlcs_to_add: final_lines.add(f"addappid({dlc_id})")

                def sort_key(line):
                    match_add = re.search(r'addappid\((\d+)', line)
                    if match_add: return (0, int(match_add.group(1)))
                    match_set = re.search(r'setManifestid\((\d+)', line)
                    if match_set: return (1, int(match_set.group(1)))
                    return (2, line)
                
                sorted_lines = sorted(list(final_lines), key=sort_key)

                async with aiofiles.open(lua_filepath, 'w', encoding='utf-8') as f:
                    await f.write('\n'.join(sorted_lines) + '\n')
            
            self.log.info(f"成功将 {len(new_dlcs_to_add)} 个新的无密钥/无Depot DLC合并到 {lua_filepath.name}")

        except Exception as e:
            self.log.error(f"添加无密钥DLC时出错: {self.stack_error(e)}")

    async def _process_zip_manifest_generic(self, app_id: str, download_url: str, source_name: str, unlocker_type: str, use_st_auto_update: bool, add_all_dlc: bool, patch_depot_key: bool = False) -> bool:
        zip_path = self.temp_path / f'{app_id}.zip'
        extract_path = self.temp_path / app_id
        try:
            self.temp_path.mkdir(exist_ok=True, parents=True)
            self.log.info(f'正从 {source_name} 下载 AppID {app_id} 的清单...')

            max_retries = 3 if 'cysaw' in source_name.lower() else 2
            last_error = None
            response = None
            for attempt in range(1, max_retries + 1):
                try:
                    response = await self.client.get(download_url, timeout=60)
                    response.raise_for_status()
                    break
                except Exception as e:
                    last_error = e
                    self.log.warning(f"{source_name} 下载尝试 {attempt}/{max_retries} 失败: {e}")
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)
            if response is None:
                raise last_error or Exception("下载失败")

            async with aiofiles.open(zip_path, 'wb') as f: await f.write(response.content)
            self.log.info('正在解压...')
            with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(extract_path)
            
            st_files = list(extract_path.glob('*.st'))
            if st_files:
                st_converter = STConverter()
                for st_file in st_files:
                    try:
                        lua_content = st_converter.convert_file(str(st_file))
                        (st_file.with_suffix('.lua')).write_text(lua_content, encoding='utf-8')
                        self.log.info(f'已转换 {st_file.name} -> {st_file.with_suffix(".lua").name}')
                    except Exception as e: self.log.error(f'转换 .st 文件 {st_file.name} 失败: {e}')

            manifest_files = list(extract_path.glob('*.manifest'))
            lua_files = list(extract_path.glob('*.lua'))
            
            if unlocker_type in ("steamtools", "opensteamtool"):
                self.log.info(f"解锁内核模式: {unlocker_type} (自动更新: {'已启用' if use_st_auto_update else '已禁用'})")
                stplug_path = self.lua_output_dir()
                
                all_depots = {}
                for lua_f in lua_files:
                    depots = self.parse_lua_file_for_depots(str(lua_f))
                    all_depots.update(depots)

                lua_filename = f"{app_id}.lua"
                lua_filepath = stplug_path / lua_filename
                async with aiofiles.open(lua_filepath, mode="w", encoding="utf-8") as lua_file:
                    await lua_file.write(f'addappid({app_id})\n')
                    for depot_id, info in all_depots.items():
                        await lua_file.write(f'addappid({depot_id}, 1, "{info["DecryptionKey"]}")\n')

                    for manifest_f in manifest_files:
                        match = re.search(r'(\d+)_(\w+)\.manifest', manifest_f.name)
                        if match:
                            line = f'setManifestid({match.group(1)}, "{match.group(2)}")\n'
                            if use_st_auto_update: await lua_file.write('--' + line)
                            else: await lua_file.write(line)
                self.log.info(f"已为 SteamTools 生成解锁文件: {lua_filename}")

                if add_all_dlc:
                    await self._add_free_dlcs_to_lua(app_id, lua_filepath)

                if patch_depot_key:
                    self.log.info("开始修补创意工坊depotkey...")
                    await self.patch_lua_with_depotkey(app_id, lua_filepath)

            else:
                self.log.info(f'检测到 GreenLuma/标准模式，将处理来自 {source_name} 的文件。')
                if not manifest_files:
                    self.log.warning(f"在来自 {source_name} 的压缩包中未找到 .manifest 文件。")
                    return False

                steam_depot_path = self.steam_path / 'depotcache'
                for f in manifest_files:
                    shutil.copy2(f, steam_depot_path / f.name)
                    self.log.info(f'已复制清单: {f.name}')
                
                all_depots = {}
                for lua in lua_files:
                    depots = self.parse_lua_file_for_depots(str(lua))
                    all_depots.update(depots)
                if all_depots:
                    await self.depotkey_merge(self.steam_path / 'config' / 'config.vdf', {'depots': all_depots})

            self.log.info(f'成功处理来自 {source_name} 的清单。')
            return True
        except Exception as e:
            self.log.error(f'处理来自 {source_name} 的清单时出错: {self.stack_error(e)}')
            return False
        finally:
            if zip_path.exists(): zip_path.unlink(missing_ok=True)
            if extract_path.exists(): shutil.rmtree(extract_path)

    def _native_userdata_dir(self) -> Path | None:
        sp = self.get_steam_path()
        if not sp or not sp.exists():
            return None
        acct = self.steam_account()
        acc = str(acct.get("accountid") or "").strip()
        if acc and (sp / 'userdata' / acc).is_dir():
            return sp / 'userdata' / acc
        ud = sp / 'userdata'
        if ud.is_dir():
            cands = [p for p in ud.iterdir() if p.is_dir() and p.name not in ('0', 'anonymous')]
            if len(cands) == 1:
                return cands[0]
            if cands:
                return max(cands, key=lambda p: p.stat().st_mtime)
        return None

    async def native_unlock(self, app_id: str, game_name: str = "") -> bool:
        """把 app_id 写进 Steam 账号的 localconfig.vdf 完成「入库」。"""
        app_id = str(app_id or '').strip()
        if not app_id.isdigit():
            self.log.error(f"AppID 无效：{app_id!r}")
            return False
        ud = self._native_userdata_dir()
        if not ud:
            self.log.error("自研入库失败：找不到 userdata 目录，"
                           "请先在这台电脑上登录一次 Steam 客户端。")
            return False
        cfg = ud / 'config' / 'localconfig.vdf'
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            if cfg.exists():
                data = vdf.loads(cfg.read_text(encoding='utf-8', errors='ignore'))
                bak = cfg.with_suffix('.vxbak')
                if not bak.exists():
                    shutil.copy2(cfg, bak)
            else:
                data = {'UserLocalConfigStore': {'Software': {'Valve': {'Steam': {}}}}}
            store = data.setdefault('UserLocalConfigStore', {})
            sw = store.setdefault('Software', {})
            valve = sw.setdefault('Valve', {})
            steam = valve.setdefault('Steam', {})
            apps = steam.setdefault('Apps', {})
            entry = apps.setdefault(app_id, {})
            if not isinstance(entry, dict):
                entry = {}
                apps[app_id] = entry
            entry['LastPlayed'] = str(entry.get('LastPlayed') or 0)
            entry['Playtime'] = str(entry.get('Playtime') or 0)
            entry['FlatpakAppID'] = str(entry.get('FlatpakAppID') or '')
            if game_name:
                entry['DisplayName'] = game_name
            entry['DXBUnlockedBy'] = 'native'
            cfg.write_text(vdf.dumps(data, pretty=True), encoding='utf-8')
            self.log.info(f"自研入库完成：{app_id}"
                          + (f"（{game_name}）" if game_name else "")
                          + f" → {cfg}")
            return True
        except Exception as e:
            self.log.error(f"自研入库失败（写 {cfg} 出错）：{self.stack_error(e)}")
            return False

    async def process_zip_source(self, app_id: str, tool_type: str, unlocker_type: str, use_st_auto_update: bool, add_all_dlc: bool, patch_depot_key: bool = False) -> bool:
        if unlocker_type == 'native':
            return await self.native_unlock(app_id)
        source_map = {
            "printedwaste": "https://api.printedwaste.com/gfk/download/{app_id}",
            "cysaw": "https://cysaw.top/uploads/{app_id}.zip",
            "furcate": "https://furcate.eu/files/{app_id}.zip",
            "walftech": "https://walftech.com/proxy.php?url=https%3A%2F%2Fsteamgames554.s3.us-east-1.amazonaws.com%2F{app_id}.zip",
            "steamdatabase": "https://steamdatabase.s3.eu-north-1.amazonaws.com/{app_id}.zip",
            "steamautocracks_v2": "special",
            "buqiuren": "special",
            "sudama": "special"
        }
        source_name_map = { 
            "printedwaste": "SWA V2 (printedwaste)", 
            "cysaw": "Cysaw", 
            "furcate": "Furcate", 
            "walftech": "Walftech", 
            "steamdatabase": "SteamDatabase",
            "steamautocracks_v2": "SteamAutoCracks/ManifestHub(2)"
        }
        
        if tool_type == "steamautocracks_v2":
            return await self.process_steamautocracks_v2_manifest(app_id, unlocker_type, use_st_auto_update, add_all_dlc, patch_depot_key)
        if tool_type == "buqiuren":
            return await self.process_buqiuren_manifest(app_id)
            
        if tool_type == "sudama":
            return await self.process_sudama_manifest(app_id, unlocker_type, use_st_auto_update, add_all_dlc, patch_depot_key)
            
        custom_zip_repos = self.get_custom_zip_repos()
        for repo_config in custom_zip_repos:
            if tool_type == f"custom_zip_{repo_config['name']}":
                return await self.process_custom_zip_manifest(app_id, repo_config, add_all_dlc, patch_depot_key)
        
        url_template = source_map.get(tool_type)
        source_name = source_name_map.get(tool_type)
        if not url_template or not source_name:
            self.log.error(f"未知的压缩包源: {tool_type}")
            return False
        download_url = url_template.format(app_id=app_id)
        return await self._process_zip_manifest_generic(app_id, download_url, source_name, unlocker_type, use_st_auto_update, add_all_dlc, patch_depot_key)

    async def fetch_branch_info(self, url: str, headers: Dict) -> Dict | None:
        try:
            r = await self.client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403: self.log.error("GitHub API请求次数已用尽。")
            elif e.response.status_code != 404: self.log.error(f"从 {url} 获取信息失败: {self.stack_error(e)}")
            return None
        except Exception as e:
            self.log.error(f'从 {url} 获取信息时发生意外错误: {self.stack_error(e)}')
            return None
            
    async def search_all_repos_for_appid(self, app_id: str, repos: List[str] = None) -> List[Dict]:
        """Search for app_id in all GitHub repositories (builtin + custom)"""
        if repos is None:
            repos = self.get_all_github_repos()
        
        github_token = self.config.get("Github_Personal_Token", "")
        headers = {'Authorization': f'Bearer {github_token}'} if github_token else None
        tasks = [self._search_single_repo(app_id, repo, headers) for repo in repos]
        results = await asyncio.gather(*tasks)
        return [res for res in results if res]

    async def _search_single_repo(self, app_id: str, repo: str, headers: Dict) -> Dict | None:
        self.log.info(f"正在仓库 {repo} 中搜索 AppID: {app_id}")
        url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
        r_json = await self.fetch_branch_info(url, headers)
        if r_json and 'commit' in r_json:
            tree_url = r_json['commit']['commit']['tree']['url']
            r2_json = await self.fetch_branch_info(tree_url, headers)
            if r2_json and 'tree' in r2_json:
                self.log.info(f"在 {repo} 中找到清单。")
                return {'repo': repo, 'sha': r_json['commit']['sha'], 'tree': r2_json['tree'], 'update_date': r_json["commit"]["commit"]["author"]["date"]}
        return None

    async def process_github_manifest(self, app_id: str, repo: str, unlocker_type: str, use_st_auto_update: bool, add_all_dlc: bool, patch_depot_key: bool = False) -> bool:
        if unlocker_type == 'native':
            return await self.native_unlock(app_id)
        github_token = self.config.get("Github_Personal_Token", "")
        headers = {'Authorization': f'Bearer {github_token}'} if github_token else None
        
        url = f'https://api.github.com/repos/{repo}/branches/{app_id}'
        r_json = await self.fetch_branch_info(url, headers)
        if not (r_json and 'commit' in r_json):
            self.log.error(f'无法获取 {repo} 中 {app_id} 的分支信息。如果该清单在此仓库中不存在，这是正常现象。')
            return False
        
        sha, tree_url = r_json['commit']['sha'], r_json['commit']['commit']['tree']['url']
        r2_json = await self.fetch_branch_info(tree_url, headers)
        if not (r2_json and 'tree' in r2_json):
            self.log.error(f'无法获取 {repo} 中 {app_id} 的文件列表。')
            return False
            
        all_files_in_tree = r2_json.get('tree', [])
        files_to_download = all_files_in_tree[:]
        
        if unlocker_type in ("steamtools", "opensteamtool") and use_st_auto_update:
            files_to_download = [item for item in all_files_in_tree if not item['path'].endswith('.manifest')]
        
        if not files_to_download and all_files_in_tree: self.log.info("没有需要下载的文件（可能是因为自动更新模式跳过了所有文件）。")
        if not all_files_in_tree:
            self.log.warning(f"仓库 {repo} 的分支 {app_id} 为空。")
            return True

        try:
            downloaded_files = {}
            if files_to_download:
                tasks = [self._get_from_mirrors(sha, item['path'], repo) for item in files_to_download]
                downloaded_contents = await asyncio.gather(*tasks)
                downloaded_files = {item['path']: content for item, content in zip(files_to_download, downloaded_contents)}
        except Exception as e:
            self.log.error(f"下载文件失败，正在中止对 {app_id} 的处理: {e}")
            return False
        
        all_manifest_paths_in_tree = [item['path'] for item in all_files_in_tree if item['path'].endswith('.manifest')]
        downloaded_manifest_paths = [p for p in downloaded_files if p.endswith('.manifest')]
        key_vdf_path = next((p for p in downloaded_files if "key.vdf" in p.lower()), None)
        all_depots = {}
        if key_vdf_path:
            try:
                depots_config = vdf.loads(downloaded_files[key_vdf_path].decode('utf-8'))
                all_depots = depots_config.get('depots', {})
            except Exception as e: self.log.error(f"解析 key.vdf 失败: {e}")

        if unlocker_type in ("steamtools", "opensteamtool"):
            self.log.info(f"解锁内核模式: {unlocker_type} (自动更新: {'已启用' if use_st_auto_update else '已禁用'})")
            stplug_path = self.lua_output_dir()
            lua_filename = f"{app_id}.lua"
            lua_filepath = stplug_path / lua_filename
            async with aiofiles.open(lua_filepath, mode="w", encoding="utf-8") as lua_file:
                await lua_file.write(f'addappid({app_id})\n')
                for depot_id, info in all_depots.items():
                    key = info.get("DecryptionKey", "")
                    await lua_file.write(f'addappid({depot_id}, 1, "{key}")\n')
                for manifest_file_path in all_manifest_paths_in_tree:
                    match = re.search(r'(\d+)_(\w+)\.manifest', Path(manifest_file_path).name)
                    if match:
                        line = f'setManifestid({match.group(1)}, "{match.group(2)}")\n'
                        if use_st_auto_update: await lua_file.write('--' + line)
                        else: await lua_file.write(line)
            self.log.info(f"已为 SteamTools 生成解锁文件: {app_id}.lua")
            
            if add_all_dlc:
                await self._add_free_dlcs_to_lua(app_id, lua_filepath)

            if patch_depot_key:
                self.log.info("开始修补创意工坊depotkey...")
                await self.patch_lua_with_depotkey(app_id, lua_filepath)

        else:
            self.log.info("检测到 GreenLuma/标准模式，将复制 .manifest 文件到 depotcache。")
            if not downloaded_manifest_paths:
                self.log.error("GreenLuma 模式需要 .manifest 文件，但未能找到或下载。")
                return False
            
            depot_cache_path = self.steam_path / 'depotcache'
            for path in downloaded_manifest_paths:
                filename = Path(path).name
                (depot_cache_path / filename).write_bytes(downloaded_files[path])
                self.log.info(f"已为 GreenLuma 保存清单: {filename}")
            
            if all_depots:
                await self.depotkey_merge(self.steam_path / 'config' / 'config.vdf', {'depots': all_depots})
                gl_ids = list(all_depots.keys())
                gl_ids.append(app_id)
                await self.greenluma_add(list(set(gl_ids)))
                self.log.info("已合并密钥并添加到GreenLuma。")

        self.log.info(f'清单最后更新时间: {r_json["commit"]["commit"]["author"]["date"]}')
        return True
    
    def extract_app_id(self, user_input: str) -> str | None:
        match = re.search(r"/app/(\d+)", user_input) or re.search(r"steamdb\.info/app/(\d+)", user_input)
        if match: return match.group(1)
        return user_input if user_input.isdigit() else None

    async def craft_opensteamtool_lua(self, appid: str, include_depotkeys: bool = True, include_manifests: bool = True) -> Tuple[str, str, Dict]:
        """手搓 OpenSteamTool 风格 lua：仅用官方源（Steam 商店 API + SteamCMD 官方 appinfo 镜像），
        不调用任何第三方密钥库。返回 (lua文本, 文件名, 信息字典)。
        """
        appid = self.extract_app_id(appid) or appid.strip()
        if not appid or not appid.isdigit():
            raise ValueError("无效的 AppID，请输入数字或 Steam 链接。")
        info: Dict[str, Any] = {"appid": appid, "name": "", "depots": [], "depotkeys": {}, "manifests": {}}
        try:
            headers = {'User-Agent': 'DaXuanBa-Injector'}
            d = await self._fetch_store_appdetails(appid, headers)
            if d:
                info["name"] = d.get("name", "")
        except Exception as e:
            self.log.warning(f"获取游戏名失败: {e}")
        depot_manifest: Dict[str, str] = {}
        try:
            raw = await self._get_steamcmd_api_data(appid) or {}
            info_root = (raw.get("data", {}) or {}).get(str(appid), {}) or {}
            depots_cfg = info_root.get("depots", {}) or {}
            for dep_id, dep_cfg in depots_cfg.items():
                if not str(dep_id).isdigit() or not isinstance(dep_cfg, dict):
                    continue
                gid = str((dep_cfg.get("manifests", {}) or {}).get("public", {}).get("gid", "") or "")
                depot_manifest[str(dep_id)] = gid
            if depot_manifest:
                self.log.info(f"从 SteamCMD 官方 appinfo 获取到 {len(depot_manifest)} 个 depot。")
            else:
                self.log.warning("SteamCMD 官方 appinfo 中未找到 depot 信息。")
        except Exception as e:
            self.log.warning(f"获取 depot/manifest 失败: {e}")
        lines = [
            "-- 大轩巴入库器mini · 手搓 OpenSteamTool lua（官方源）",
            f"-- AppID: {appid}" + (f"  名称: {info['name']}" if info['name'] else ""),
            "-- 放入 Steam 根目录的 config\\lua\\ 下自动加载",
            f"addappid({appid})  -- 解锁游戏 {info['name'] or appid}",
        ]
        for dep, gid in depot_manifest.items():
            lines.append(f"addappid({dep})  -- depot {dep}")
            if include_manifests and gid:
                lines.append(f'setManifestid({dep}, "{gid}")')
        lua = "\n".join(lines) + "\n"
        filename = f"{appid}.lua"
        info["depots"] = list(depot_manifest.keys())
        info["manifests"] = depot_manifest
        self.log.info(f"已手搓 lua: appid={appid} name={info['name']} depots={len(depot_manifest)} (仅官方源，无第三方密钥)")
        return lua, filename, info

    def _normalize_name(self, s: str) -> str:
        """归一化：去空白、去标点、转小写，便于模糊比较。"""
        s = (s or '').lower()
        s = re.sub(r'[^0-9a-z\u4e00-\u9fff]', '', s)
        return s

    def _rank_game_results(self, query: str, items: List[Dict]) -> List[Dict]:
        """对搜索结果做相似度重排：名称包含/子序列/分词命中优先，避免逐字完全匹配。"""
        q = self._normalize_name(query)
        if not q:
            return items
        def score(item):
            n = self._normalize_name(item.get('name', ''))
            if not n:
                return 0
            if n == q:
                return 100
            if q in n or n in q:
                return 80
            it = iter(n)
            if all(c in it for c in q):
                return 60
            for tok in re.split(r'[\s\-_]+', q):
                if len(tok) >= 2 and tok in n:
                    return 40
            return 10
        scored = [(score(it), it) for it in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for s, it in scored if s >= 10]

    async def find_appid_by_name(self, game_name: str) -> List[Dict]:
        """搜索游戏名称 -> AppID，支持直接输入 AppID、多区域 Steam 搜索、SteamDB、小黑盒备用。"""
        try:
            self.log.info(f"正在尝试搜索游戏: {game_name}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            if game_name.isdigit():
                appid = game_name
                detail = await self._fetch_store_appdetails(appid, headers)
                if detail:
                    self.log.info(f"直接命中 AppID: {appid}")
                    return [detail]

            steam_regions = [
                {'l': 'schinese', 'cc': 'CN'},
                {'l': 'english', 'cc': 'US'},
                {'l': 'tchinese', 'cc': 'TW'},
            ]
            for region in steam_regions:
                try:
                    r = await self.client.get(
                        "https://store.steampowered.com/api/storesearch",
                        params={'term': game_name, **region},
                        headers=headers, timeout=20
                    )
                    r.raise_for_status()
                    resp_json = r.json()
                    raw_data = resp_json.get('items', []) if isinstance(resp_json, dict) else []
                    games_list = []
                    for item in raw_data:
                        appid = item.get('id') or item.get('appid')
                        name = item.get('name')
                        image = item.get('tiny_image') or item.get('header_image') or item.get('image')
                        if appid and name:
                            games_list.append({'appid': str(appid), 'name': name, 'header_image': image})
                    if games_list:
                        games_list = self._rank_game_results(game_name, games_list)
                        self.log.info(f"成功找到 {len(games_list)} 个结果")
                        return games_list
                except Exception as e:
                    self.log.debug(f"Steam 搜索 ({region}) 失败: {e}")
                    continue

            self.log.info("Steam 官方搜索无结果，尝试 SteamDB 搜索...")
            steamdb_results = await self._search_steamdb(game_name, headers)
            if steamdb_results:
                return steamdb_results

            self.log.info("尝试小黑盒备用搜索...")
            fallback = await self._find_appid_fallback(game_name, headers)
            if fallback:
                return fallback

            self.log.warning("未找到相关游戏。")
        except Exception as e:
            self.log.error(f"搜索游戏 '{game_name}' 失败: {self.stack_error(e)}")
        return []

    async def _fetch_store_appdetails(self, appid: str, headers: Dict) -> Dict | None:
        """通过 Steam Store appdetails 获取单个 AppID 信息"""
        try:
            r = await self.client.get(
                "https://store.steampowered.com/api/appdetails",
                params={'appids': appid, 'l': 'schinese', 'cc': 'CN'},
                headers=headers, timeout=20
            )
            r.raise_for_status()
            data = r.json()
            app_data = data.get(appid, {})
            if app_data.get('success') and app_data.get('data'):
                d = app_data['data']
                return {
                    'appid': appid,
                    'name': d.get('name', '未知游戏'),
                    'header_image': d.get('header_image', '')
                }
        except Exception as e:
            self.log.debug(f"appdetails 查询失败: {e}")
        return None

    async def _search_steamdb(self, game_name: str, headers: Dict) -> List[Dict]:
        """通过 SteamDB 搜索页面抓取结果"""
        try:
            r = await self.client.get(
                "https://steamdb.info/api/ExtensionSearch/",
                params={'q': game_name},
                headers={**headers, 'Accept': 'application/json'},
                timeout=20
            )
            if r.status_code == 200:
                data = r.json()
                out = []
                for item in data.get('data', []):
                    appid = item.get('appid')
                    name = item.get('name')
                    if appid and name:
                        out.append({'appid': str(appid), 'name': name, 'header_image': ''})
                if out:
                    self.log.info(f"SteamDB 搜索找到 {len(out)} 个结果")
                    return out
        except Exception as e:
            self.log.debug(f"SteamDB 搜索失败: {e}")
        return []

    async def _find_appid_fallback(self, game_name: str, headers: Dict) -> List[Dict]:
        try:
            api = "https://steamapi.xiaoheihe.cn/v1/search?query=" + quote(game_name)
            r = await self.client.get(api, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
            out = []
            items = data.get('data', {}).get('items') or data.get('items') or []
            for it in items:
                appid = it.get('appid') or it.get('id')
                name = it.get('name') or it.get('title')
                if appid and name:
                    out.append({'appid': str(appid), 'name': name, 'header_image': it.get('img') or it.get('image') or ''})
            return out
        except Exception:
            return []

    async def cleanup_temp_files(self):
        try:
            if self.temp_path.exists():
                shutil.rmtree(self.temp_path)
                self.log.info('临时文件已清理。')
        except Exception as e:
            self.log.error(f'清理临时文件失败: {self.stack_error(e)}')

    async def migrate(self, st_use: bool):
        directory = self.steam_path / "config" / "stplug-in"
        if st_use and directory.exists():
            self.log.info('检测到SteamTools, 正在检查是否有旧文件需要迁移...')
            for file in directory.glob("Cai_unlock_*.lua"):
                new_filename = directory / file.name.replace("Cai_unlock_", "")
                try:
                    file.rename(new_filename)
                    self.log.info(f'已重命名: {file.name} -> {new_filename.name}')
                except Exception as e:
                    self.log.error(f'重命名失败 {file.name}: {e}')



GH_DL_PROXIES = [
    "",
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://gh.llkk.cc/",
    "https://ghproxy.net/",
]

GREENLUMA_REPO = "ehgen0ng/wuhu"
GREENLUMA_BRANCH = "master"
GREENLUMA_DIR = "archive/go/utils/GreenLuma"
GREENLUMA_FILES = ["DLLInjector.exe", "GreenLuma_2025_x64.dll", "DLLInjector.ini", "GreenLuma2025.txt"]

GREENLUMA_STEALTH_REPO = "Cranch-fur/GreenLuma-GUI"
GREENLUMA_STEALTH_ASSET_EXT = ".zip"
GREENLUMA_STEALTH_INNER = "GreenLuma.dll"
GREENLUMA_STEALTH_DLL = "user32.dll"
GREENLUMA_STEALTH_BAK = "user32.dll.dxb_bak"
GREENLUMA_STEALTH_MARKER = "greenluma_stealth_version.txt"
GREENLUMA_STEALTH_MIN_SIZE = 60000

STEAMTOOLS_SITE = "https://steamtools.net"
STEAMTOOLS_PAGE = STEAMTOOLS_SITE + "/download"
STEAMTOOLS_RES_RE = re.compile(r'res/st-setup-([0-9]+(?:\.[0-9]+)+)\.exe', re.I)
STEAMTOOLS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_DEAD_STEAMTOOLS_REPOS = {"steamtools/staupdater"}

INSTALLER_EXT = ".exe"

KERNEL_SPECS: Dict[str, Dict[str, Any]] = {
    "native": {
        "name": "自研入库（无需内核）",
        "short": "不装任何 DLL，程序直接写 Steam 库",
        "desc": "程序自己把 AppID 写进本机 Steam 账号的库清单（localconfig.vdf），"
                "不需要装 OpenSteamTool / SteamTools / GreenLuma 任何一个，"
                "不往 Steam 目录丢任何 DLL，Steam 绝对不会因此起不来。"
                "代价是不带 depot 密钥：入库能成功，之后 Steam 下载时会因为缺密钥失败。",
        "source": "builtin",
        "builtin": True,
        "repos": [],
        "asset_prefer": [],
        "asset_exts": [],
        "target": "none",
        "marker": "",
        "extra_dirs": [],
    },
    "opensteamtool": {
        "name": "OpenSteamTool",
        "short": "清单导入内核",
        "desc": "装到 Steam 主目录，lua 清单目录 config\\lua。与 SteamTools 二选一。",
        "source": "github",
        "repos": ["OpenSteam001/OpenSteamTool"],
        "asset_prefer": ["release"],
        "asset_exts": [".zip", ".7z"],
        "target": "steam_root",
        "marker": "opensteamtool_version.txt",
        "extra_dirs": ["config/lua"],
            "root_files": ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"],
    },
    "steamtools": {
        "name": "SteamTools",
        "short": "稳定入库内核（官方安装包）",
        "desc": "三个内核里唯一的安装包（steamtools.net 官方 NSIS）。下载完直接运行它："
                "管理员下 /S 静默安装、全程无窗口；普通权限则弹官方安装向导让你自己点。"
                "装完 Steam 主目录会有 hid.dll / XInput1_4.dll / dwmapi.dll，"
                "config\\stplug-in 放 lua 清单。",
        "source": "official",
        "site": STEAMTOOLS_SITE,
        "repos": [],
        "asset_prefer": [],
        "asset_exts": [INSTALLER_EXT],
        "installer": True,
        "silent_args": ["/S"],
        "target": "stplug",
        "marker": "steamtools_version.txt",
        "extra_dirs": [],
    },
    "greenluma": {
        "name": "GreenLuma",
        "short": "DLL 入库（两种形态）",
        "desc": "默认装「隐身版」：改写版 user32.dll 放进 Steam 主目录，启动 Steam 自动生效——"
                "无注入器、无管理员、无窗口，也不怕 Steam 更新。另可选「注入版」（DLLInjector.exe，"
                "对 Steam 版本敏感）。AppList 里放 AppID。",
        "source": "wuhu",
        "repos": [],
        "asset_prefer": [],
        "asset_exts": [],
        "target": "steam_root",
        "marker": "greenluma_version.txt",
        "extra_dirs": ["AppList"],
        "root_files": ["GreenLuma_2025_x64.dll", "DLLInjector.exe"],
        "modes": ["stealth", "inject"],
        "default_mode": "stealth",
    },
}


def close_steam(timeout: int = 45) -> Dict[str, Any]:
    """关闭 Steam：先请它自己退（-shutdown），退不掉才 taskkill /F。

    为什么不能一上来就 /F：被强杀的 Steam 会留下半成品
    %LOCALAPPDATA%\\Steam\\htmlcache，下次启动 CEF 起不来（不弹窗、日志刷
    "Failed creating offscreen shared JS context" + GPU 崩溃循环）。这是实测踩过的坑。
    """
    pids = []
    try:
        r = run_hidden(['tasklist', '/fi', 'imagename eq steam.exe', '/nh'], timeout=20)
        for line in (r.stdout or "").splitlines():
            m = re.search(r'steam\.exe\s+(\d+)', line, re.I)
            if m:
                pids.append(int(m.group(1)))
    except Exception:
        pass
    if not pids:
        return {"ok": True, "already_closed": True, "forced": False}

    try:
        exe = None
        sp = _current_steam_root()
        if sp and (sp / 'steam.exe').exists():
            exe = str(sp / 'steam.exe')
        if exe:
            subprocess.Popen([exe, '-shutdown'], cwd=str(sp),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    for _ in range(int(timeout / 1.5)):
        time.sleep(1.5)
        r = run_hidden(['tasklist', '/fi', 'imagename eq steam.exe', '/nh'], timeout=15)
        if 'steam.exe' not in (r.stdout or "").lower():
            return {"ok": True, "already_closed": False, "forced": False}

    r = run_hidden(['taskkill', '/F', '/IM', 'steam.exe'], timeout=30)
    time.sleep(1.0)
    return {"ok": True, "already_closed": False, "forced": True,
            "raw": (r.stdout or '').strip()[:200]}


def _current_steam_root() -> Path | None:
    """尽力定位 Steam 根目录（给 close_steam 用，拿不到就返回 None）。"""
    try:
        for cand in (r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam',
                     r'D:\Steam', r'E:\Steam'):
            p = Path(cand)
            if (p / 'steam.exe').exists():
                return p
    except Exception:
        pass
    return None


def run_hidden(args, cwd=None, timeout: int = 120):
    """无窗口跑子进程并取回输出。

    中文 Windows 下 tasklist/taskkill/net 输出是 GBK，text=True 默认按 UTF-8 解会炸，
    所以统一按系统首选编码解码 + errors='ignore'。
    """
    flags = 0x08000000 if sys.platform == 'win32' else 0
    si = None
    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
    try:
        return subprocess.run(
            args, cwd=cwd, timeout=timeout, startupinfo=si, creationflags=flags,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding=locale.getpreferredencoding(False), errors='ignore',
        )
    except Exception as e:
        class _R:
            returncode = -1
            stdout = f'执行失败: {e}'
        return _R()


_TH32CS_SNAPMODULE = 0x00000008
_TH32CS_SNAPMODULE32 = 0x00000010
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _MODULEENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong),
                ("th32ModuleID", ctypes.c_ulong),
                ("th32ProcessID", ctypes.c_ulong),
                ("GlblcntUsage", ctypes.c_ulong),
                ("ProccntUsage", ctypes.c_ulong),
                ("modBaseAddr", ctypes.c_void_p),
                ("modBaseSize", ctypes.c_ulong),
                ("hModule", ctypes.c_void_p),
                ("szModule", ctypes.c_char * 256),
                ("szExePath", ctypes.c_char * 260)]


def process_modules(pid: int) -> List[Tuple[str, str]]:
    """枚举指定进程已加载的模块 → [(模块名, 完整路径)]。非 Windows / 失败返回 []。"""
    if sys.platform != 'win32':
        return []
    try:
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        h = k32.CreateToolhelp32Snapshot(_TH32CS_SNAPMODULE | _TH32CS_SNAPMODULE32, int(pid))
        if not h or h == _INVALID_HANDLE_VALUE:
            return []
        out: List[Tuple[str, str]] = []
        me = _MODULEENTRY32()
        me.dwSize = ctypes.sizeof(_MODULEENTRY32)
        try:
            ok = k32.Module32First(ctypes.c_void_p(h), ctypes.byref(me))
            while ok:
                out.append((me.szModule.decode('mbcs', 'ignore'),
                            me.szExePath.decode('mbcs', 'ignore')))
                ok = k32.Module32Next(ctypes.c_void_p(h), ctypes.byref(me))
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
        return out
    except Exception:
        return []


class KernelHub:
    """内核（OpenSteamTool / SteamTools / GreenLuma）状态 + 下载 + 安装。"""
    def __init__(self, backend):
        self.b = backend
        self.log = backend.log

    def _client(self):
        """KernelHub 也可能被 _quick_backend()（没走 async with）实例化，client 可能是 None。"""
        c = getattr(self.b, 'client', None)
        if c is None:
            c = httpx.AsyncClient(verify=False, trust_env=True)
            self.b.client = c
        return c

    def local_status(self, kind: str) -> Dict[str, Any]:
        spec = KERNEL_SPECS.get(kind)
        if not spec:
            return {"ok": False, "error": "未知内核"}
        sp = self.b.get_steam_path()
        out: Dict[str, Any] = {"kind": kind, "name": spec["name"], "short": spec.get("short", ""),
                               "desc": spec.get("desc", ""), "installed": False, "version": "",
                               "steam_path": str(sp) if sp else None, "files": [], "applist": 0}
        if not sp or not sp.exists():
            out["error"] = "没有检测到 Steam 目录"
            return out
        if kind == "native":
            acct = self.b.steam_account()
            out["installed"] = True
            out["builtin"] = True
            out["version"] = CURRENT_VERSION
            out["account"] = acct
            out["files"] = []
            out["note"] = ("程序自带能力，无需下载安装"
                           + (f"；已识别本机 Steam 账号 {acct.get('persona') or acct.get('steamid64')}"
                              if acct.get("logged_in") else "；未读到本机登录账号，仍可写入库清单"))
            return out
        if kind == "greenluma":
            inject_files = [n for n in ["GreenLuma_2025_x64.dll", "DLLInjector.exe", "LumaCore.dll"]
                            if (sp / n).exists()]
            out["inject"] = {"installed": bool(inject_files), "files": inject_files,
                             "version": self._read_marker(sp / KERNEL_SPECS['greenluma']['marker'])}
            out["stealth"] = self.greenluma_stealth_state()
            ad = sp / 'AppList'
            if ad.is_dir():
                try:
                    out["applist"] = sum(1 for _ in ad.glob('*.txt'))
                except Exception:
                    out["applist"] = 0
            out["files"] = ([GREENLUMA_STEALTH_DLL] if out["stealth"]["installed"] else []) + inject_files
            out["installed"] = out["stealth"]["installed"] or out["inject"]["installed"]
            out["modes"] = list(KERNEL_SPECS['greenluma'].get("modes") or [])
            out["mode"] = ("stealth" if out["stealth"]["installed"]
                           else ("inject" if out["inject"]["installed"] else ""))
            out["version"] = (out["stealth"]["version"] if out["stealth"]["installed"]
                              else (out["inject"]["version"] if out["inject"]["installed"] else ""))
        elif kind == "steamtools":
            d = sp / 'config' / 'stplug-in'
            st_files: List[str] = []
            lua_n = 0
            if d.is_dir():
                try:
                    st_files = [p.name for p in d.iterdir()][:6]
                    lua_n = sum(1 for _ in d.glob('*.lua'))
                except Exception:
                    st_files, lua_n = [], 0
            proxies = [n for n in ('hid.dll', 'XInput1_4.dll', 'dwmapi.dll') if (sp / n).exists()]
            out["files"] = st_files + [n for n in proxies if n not in st_files]
            out["lua_count"] = lua_n
            out["installed"] = bool((sp / 'hid.dll').exists() or lua_n)
        else:
            lua = sp / 'config' / 'lua'
            dll_ok = (sp / 'OpenSteamTool.dll').exists()
            lua_ok = lua.is_dir() and any(lua.glob('*.lua'))
            out["installed"] = dll_ok or lua_ok
            out["files"] = [n for n in ["OpenSteamTool.dll", "dwmapi.dll", "xinput1_4.dll"] if (sp / n).exists()]
        if not out.get("version"):
            out["version"] = self._read_marker(sp / spec["marker"])
        return out

    @staticmethod
    def _read_marker(path: Path) -> str:
        try:
            if path.exists():
                return path.read_text(encoding='utf-8').strip()
        except Exception:
            pass
        return ""

    def all_local(self) -> Dict[str, Any]:
        return {k: self.local_status(k) for k in KERNEL_SPECS}

    async def remote_latest(self, kind: str) -> Dict[str, Any]:
        """查远端最新版本（纯 API/HTTP，不开浏览器）。返回 {ok, version, url, note}"""
        spec = KERNEL_SPECS.get(kind)
        if not spec:
            return {"ok": False, "error": "未知内核"}
        if spec.get("builtin"):
            return {"ok": True, "version": CURRENT_VERSION, "repo": "builtin",
                    "note": "程序自带，无需下载"}
        if spec.get("source") == "wuhu":
            return await self._remote_greenluma()
        if spec.get("source") == "official":
            off = await self._steamtools_latest()
            custom = self._steamtools_repo_override()
            if off.get("ok") or not custom:
                return off
            repos = [custom]
        else:
            repos = list(spec.get("repos") or [])
            if kind == "opensteamtool":
                custom = (self.b.config.get('opensteamtool_repo') or '').strip()
                if custom:
                    repos = [custom]
        for repo in repos:
            try:
                tag, asset = await self._latest_release(repo, spec)
                if tag:
                    return {"ok": True, "version": tag, "repo": repo,
                            "asset": asset[1] if asset else "", "url": asset[0] if asset else "",
                            "note": ""}
            except Exception as e:
                self.log.warning(f"查询 {repo} 最新发布失败：{e}")
        return {"ok": False, "note": "查询远端版本失败（网络或仓库不可达）。"}

    def _steamtools_repo_override(self) -> str:
        """用户自填的 SteamTools 镜像仓库；早先写死过的死值一律当没填。"""
        v = str(self.b.config.get('steamtools_repo') or '').strip()
        if not v or v.lower() in _DEAD_STEAMTOOLS_REPOS:
            return ""
        return v

    async def _steamtools_latest(self) -> Dict[str, Any]:
        """SteamTools 官方最新安装包版本（纯 HTTP，两步扒 SPA bundle，不开浏览器）。

        官方站是 CF 保护的 SPA，HTML 里没有直链，所以：
          1) GET /download  → 从 HTML 里找 /assets/index-*.js
          2) GET 那个 js    → 正则 res/st-setup-<ver>.exe
        """
        ua = {"User-Agent": STEAMTOOLS_UA}
        try:
            c = self._client()
            r = await c.get(STEAMTOOLS_PAGE, headers=ua, timeout=25, follow_redirects=True)
            if r.status_code != 200:
                return {"ok": False, "note": f"SteamTools 官方下载页返回 HTTP {r.status_code}"
                                             "（站点挂在 Cloudflare 后面，偶尔会拦）。"}
            m = re.search(r'/assets/index-[\w.\-]+\.js', r.text)
            if not m:
                return {"ok": False, "note": "官方下载页结构变了，没找到资源清单，无法取版本号。"}
            js = await c.get(STEAMTOOLS_SITE + m.group(0), headers=ua, timeout=30,
                             follow_redirects=True)
            if js.status_code != 200:
                return {"ok": False, "note": f"取官方资源清单失败（HTTP {js.status_code}）。"}
            hit = STEAMTOOLS_RES_RE.search(js.text)
            if not hit:
                return {"ok": False, "note": "官方资源清单里没解析到安装包文件名，无法取版本号。"}
            ver = hit.group(1)
            return {"ok": True, "version": ver, "repo": STEAMTOOLS_SITE,
                    "asset": f"st-setup-{ver}.exe", "installer": True,
                    "url": f"{STEAMTOOLS_SITE}/res/st-setup-{ver}.exe",
                    "note": f"来源：steamtools.net 官方安装包（NSIS，约 10MB）"}
        except Exception as e:
            return {"ok": False, "note": f"取 SteamTools 官方版本失败：{str(e)[:110]}"}

    async def _remote_greenluma(self) -> Dict[str, Any]:
        """GreenLuma 远端版本（两种形态分别查，避免拿注入版的版本号糊弄隐身版）。

        · 隐身版（默认）：Cranch-fur/GreenLuma-GUI 的 release，tag 形如 v1.3_GL1.8.7；
        · 注入版：wuhu 仓库的 GreenLuma2025.txt。
        """
        sver, _surl = await self._stealth_latest()
        iver = ""
        txt = await self._fetch_raw("GreenLuma2025.txt")
        if txt:
            m = re.search(r'GreenLuma\s+20\d\d[ \t]+([0-9]+(?:\.[0-9]+)+)', txt)
            if m:
                iver = m.group(1)
        if not sver and not iver:
            return {"ok": False, "note": "无法从下载源解析 GreenLuma 版本（可能要手动配镜像）。"}
        notes = []
        if not sver:
            notes.append("隐身版源没取到")
        if not iver:
            notes.append("注入版版本号未解析")
        return {"ok": bool(sver), "version": sver or iver,
                "repo": GREENLUMA_STEALTH_REPO, "asset": GREENLUMA_STEALTH_INNER,
                "stealth_version": sver, "inject_version": iver,
                "note": "；".join(notes)}

    async def _stealth_latest(self) -> Tuple[str, str]:
        """取 GreenLuma 隐身版最新 zip 直链（GitHub release，纯 API，不开浏览器）。"""
        try:
            api = f"https://api.github.com/repos/{GREENLUMA_STEALTH_REPO}/releases/latest"
            token = (self.b.config.get("Github_Personal_Token") or "").strip()
            headers = {"User-Agent": "DaXuanBa-Injector"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            r = await self._client().get(api, headers=headers, timeout=20)
            if r.status_code != 200:
                return "", ""
            rel = r.json()
            tag = str(rel.get("tag_name") or "").strip()
            url = ""
            for a in (rel.get("assets") or []):
                nm = str(a.get("name") or "")
                if nm.lower().endswith(GREENLUMA_STEALTH_ASSET_EXT):
                    url = a.get("browser_download_url") or ""
                    break
            m = re.search(r'GL[ _]?([0-9]+(?:\.[0-9]+)+)', tag, re.I)
            return (m.group(1) if m else tag), url
        except Exception as e:
            self.log.warning(f"查询 GreenLuma 隐身版失败：{e}")
            return "", ""

    async def _latest_release(self, repo: str, spec: Dict) -> Tuple[str, Tuple[str, str] | None]:
        api = f"https://api.github.com/repos/{repo}/releases/latest"
        token = (self.b.config.get("Github_Personal_Token") or "").strip()
        headers = {"User-Agent": "DaXuanBa-Injector"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = await self._client().get(api, headers=headers, timeout=20)
        if r.status_code != 200:
            return "", None
        rel = r.json()
        tag = str(rel.get("tag_name") or "").strip()
        assets = rel.get("assets") or []
        best = None
        prefer = [p.lower() for p in (spec.get("asset_prefer") or [])]
        exts = [e.lower() for e in (spec.get("asset_exts") or [])]
        for want in prefer:
            for a in assets:
                nm = str(a.get("name") or "")
                if want in nm.lower() and any(nm.lower().endswith(e) for e in exts):
                    best = (a.get("browser_download_url"), nm)
                    break
            if best:
                break
        if not best:
            for a in assets:
                nm = str(a.get("name") or "")
                if any(nm.lower().endswith(e) for e in exts):
                    best = (a.get("browser_download_url"), nm)
                    break
        return tag, best

    def _raw_urls(self, name: str) -> List[str]:
        path = f"{GREENLUMA_DIR}/{name}"
        base = [
            f"https://raw.githubusercontent.com/{GREENLUMA_REPO}/{GREENLUMA_BRANCH}/{path}",
            f"https://cdn.jsdelivr.net/gh/{GREENLUMA_REPO}@{GREENLUMA_BRANCH}/{path}",
            f"https://fastly.jsdelivr.net/gh/{GREENLUMA_REPO}@{GREENLUMA_BRANCH}/{path}",
            f"https://gcore.jsdelivr.net/gh/{GREENLUMA_REPO}@{GREENLUMA_BRANCH}/{path}",
        ]
        out = list(base)
        for u in base[:2]:
            out.append(f"https://gh-proxy.com/{u}")
        return out

    async def _fetch_raw(self, name: str) -> str:
        for u in self._raw_urls(name):
            try:
                r = await self._client().get(u, timeout=30, follow_redirects=True)
                if r.status_code == 200 and r.content:
                    return r.content.decode('utf-8', 'ignore')
            except Exception:
                continue
        return ""

    async def _download_to(self, url: str, dest: Path, on_progress=None, label: str = "") -> bool:
        """下载（带镜像回退 + 真实进度）。url 为 github 链接时自动尝试加速前缀。

        steamtools.net 挂在 Cloudflare 后面，**裸请求（无 UA）一律 403**，
        所以这里统一带浏览器 UA，别的地方漏带就会下不到安装包。
        """
        cands = [url]
        if "github.com" in url or "raw.githubusercontent.com" in url:
            cands = [p + url for p in GH_DL_PROXIES]
        headers = {"User-Agent": STEAMTOOLS_UA}
        dest.parent.mkdir(parents=True, exist_ok=True)
        last_err = ""
        for i, u in enumerate(cands):
            try:
                async with self._client().stream("GET", u, headers=headers,
                                                follow_redirects=True, timeout=180) as r:
                    if r.status_code != 200:
                        last_err = f"HTTP {r.status_code}"
                        continue
                    total = int(r.headers.get("content-length") or 0)
                    got = 0
                    with open(dest, 'wb') as f:
                        async for chunk in r.aiter_bytes(65536):
                            f.write(chunk)
                            got += len(chunk)
                            if on_progress:
                                pct = int(got * 100 / total) if total else 0
                                on_progress(pct, f"下载{label} {got // 1024}KB" + (f"/{total // 1024}KB" if total else ""))
                if dest.exists() and dest.stat().st_size > 0:
                    return True
            except Exception as e:
                last_err = str(e)[:120]
                continue
        self.log.error(f"下载失败（{len(cands)} 个通道都试过）：{last_err}")
        return False

    def _extract(self, archive: Path, out_dir: Path) -> bool:
        """解压 zip / 7z（7z 需要可选依赖 py7zr）。"""
        name = archive.name.lower()
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if name.endswith('.7z'):
                try:
                    import py7zr
                except Exception:
                    self.log.warning("发布包是 7z 但缺少 py7zr，无法自动解压。")
                    return False
                with py7zr.SevenZipFile(archive, 'r') as z:
                    z.extractall(out_dir)
                return True
            if name.endswith('.rar'):
                self.log.warning("暂不支持 rar，请把包内文件解出来再手动放。")
                return False
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(out_dir)
            return True
        except Exception as e:
            self.log.error(f"解压失败：{e}")
            return False

    def _copy_to_steam(self, kind: str, src_dir: Path, sp: Path) -> List[str]:
        """把解压出来的东西放进正确的目录，返回实际落地的文件名。"""
        spec = KERNEL_SPECS[kind]
        placed: List[str] = []
        if spec["target"] == "stplug":
            dst = sp / 'config' / 'stplug-in'
            dst.mkdir(parents=True, exist_ok=True)
            for p in src_dir.rglob('*'):
                if p.is_file():
                    shutil.copy2(p, dst / p.name)
                    placed.append(p.name)
            return placed
        wanted = [n.lower() for n in spec.get("root_files", [])]
        found = {}
        for p in src_dir.rglob('*'):
            if p.is_file() and p.name.lower() in wanted:
                found[p.name.lower()] = p
        if kind == "greenluma":
            for p in src_dir.rglob('*'):
                if p.is_file() and (p.name.lower().startswith('greenluma') or
                                    p.name.lower() in ('dllinjector.exe', 'dllinjector.ini')):
                    found.setdefault(p.name.lower(), p)
        if not found:
            for p in src_dir.rglob('*.dll'):
                found.setdefault(p.name.lower(), p)
        for p in found.values():
            shutil.copy2(p, sp / p.name)
            placed.append(p.name)
        if kind == "greenluma" and (sp / 'DLLInjector.exe').exists():
            self._write_dllinjector_ini(sp)
        for d in spec.get("extra_dirs", []):
            try:
                (sp / d).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        return placed

    def _write_dllinjector_ini(self, sp: Path):
        """写 DLLInjector.ini：绝对路径 + 假父进程(explorer) + 隐身文件，跳过交互式设置工具。

        这些项一个都不能省。少了 EnableFakeParentProcess，steam.exe 的父进程就是
        DLLInjector（控制台程序），Steam 起来会立刻退；少了 CreateFiles/NoQuestion.bin，
        GreenLuma 还会弹询问框（无窗口跑就卡住）。之前精简成 8 行就是「注入完 Steam 一闪就没」的元凶。
        """
        steam_exe = sp / 'steam.exe'
        dll = sp / 'GreenLuma_2025_x64.dll'
        if not dll.exists():
            cands = sorted(sp.glob('GreenLuma*x64.dll'))
            if cands:
                dll = cands[0]
        lines = [
            "[DllInjector]",
            "AllowMultipleInstancesOfDLLInjector = 0",
            "UseFullPathsFromIni = 1",
            "",
            "# Exe to start, if you use stealth mode, remove \"-inhibitbootstrap\"",
            f"Exe = {steam_exe}",
            "CommandLine =",
            "",
            "# Dll to inject",
            f"Dll = {dll}",
            "",
            "# Export to call in dll",
            "Export = Init",
            "",
            "# Check if call to export returned positive value",
            "CheckReturnValue = 0",
            "",
            "# Wait for started exe to close before exiting the DllInjector process.",
            "WaitForProcessTermination = 0",
            "",
            "# Set a fake parent process",
            "# 注意：EnableFakeParentProcess=1 需要管理员权限，普通权限下 DLLInjector 会直接卡死/失败，",
            "# 所以这里保持 0（官方默认发行版的 ini 也是「二选一」，普通启动不需要假父进程）。",
            "EnableFakeParentProcess = 0",
            "FakeParentProcess = explorer.exe",
            "",
            "EnableMitigationsOnChildProcess = 0",
            "",
            "DEP = 1",
            "SEHOP = 1",
            "HeapTerminate = 1",
            "ForceRelocateImages = 1",
            "BottomUpASLR = 1",
            "HighEntropyASLR = 1",
            "RelocationsRequired = 1",
            "StrictHandleChecks = 0",
            "Win32kSystemCallDisable = 0",
            "ExtensionPointDisable = 1",
            "CFG = 1",
            "CFGExportSuppression = 1",
            "StrictCFG = 1",
            "DynamicCodeDisable = 0",
            "DynamicCodeAllowOptOut = 0",
            "BlockNonMicrosoftBinaries = 0",
            "FontDisable = 1",
            "NoRemoteImages = 1",
            "NoLowLabelImages = 1",
            "PreferSystem32 = 0",
            "RestrictIndirectBranchPrediction = 1",
            "SpeculativeStoreBypassDisable = 0",
            "ShadowStack = 0",
            "ContextIPValidation = 0",
            "BlockNonCETEHCONT = 0",
            "BlockFSCTL = 0",
            "",
            "# 自动创建这两个文件 → 隐身模式 + 不再弹询问框（无窗口运行必须）",
            "CreateFiles = 2",
            "FileToCreate_1 = StealthMode.bin",
            "FileToCreate_2 = NoQuestion.bin",
            "",
            "Use4GBPatch = 0",
            "FileToPatch_1 =",
            "",
            "BootImage = ",
            "BootImageWidth = 0",
            "BootImageHeight = 0",
            "BootImageXOffest = 0",
            "BootImageYOffest = 0",
            "",
        ]
        try:
            (sp / 'DLLInjector.ini').write_text('\r\n'.join(lines), encoding='utf-8')
            self.log.info("已写入完整 DLLInjector.ini（假父进程 + 隐身 + 免询问）")
        except Exception as e:
            self.log.warning(f"写 DLLInjector.ini 失败：{e}")

    def _downloads_dir(self) -> Path:
        """安装包落地目录：exe 同目录的 downloads\\，重启后还在，用户能自己重跑。"""
        d = Path(getattr(self.b, 'project_root', None) or Path.cwd()) / 'downloads'
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def _is_admin(self) -> bool:
        try:
            return bool(DxbBackend.is_admin())
        except Exception:
            return False

    def run_installer(self, exe: Path, silent_args=None, wait: int = 1800) -> Dict[str, Any]:
        """运行官方安装包（SteamTools 这类「安装包型」内核）。

        规矩：**是管理员就无窗口静默装**（NSIS 的 /S，CREATE_NO_WINDOW）；
        不是管理员就老实弹官方安装向导让用户自己点，不假装已经装好了。
        """
        exe = Path(exe)
        if not exe.exists():
            return {"success": False, "message": f"安装包不存在：{exe}"}
        if sys.platform != 'win32':
            return {"success": False, "message": "只有 Windows 才能运行安装包。"}
        admin = self._is_admin()
        args = [str(a) for a in (silent_args or [])]
        if admin and args:
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                p = subprocess.Popen(
                    [str(exe)] + args, cwd=str(exe.parent), startupinfo=si,
                    creationflags=0x08000000,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                return {"success": False, "admin": True, "silent": True,
                        "message": f"启动静默安装失败：{e}"}
            try:
                rc = p.wait(timeout=wait)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
                return {"success": False, "admin": True, "silent": True,
                        "message": f"静默安装超过 {max(1, wait // 60)} 分钟还没结束，已放弃等待。"
                                   "多半被杀软拦了，或者安装包在等交互。"
                                   "也可以到 downloads 目录手动双击那个安装包看看。"}
            self.log.info(f"静默安装 {exe.name} 结束，返回码 {rc}")
            return {"success": rc == 0, "admin": True, "silent": True, "returncode": rc,
                    "message": ("管理员模式：已 /S 静默安装完成，全程没有窗口。"
                                if rc == 0 else
                                f"静默安装返回码 {rc}，不一定装成功了，"
                                f"可以到 downloads 目录手动双击 {exe.name} 跑一遍看看。")}
        try:
            os.startfile(str(exe))
        except Exception as e:
            return {"success": False, "admin": False, "silent": False,
                    "message": f"打开安装包失败：{e}"}
        self.log.info(f"已打开官方安装向导：{exe}")
        return {"success": True, "admin": False, "silent": False, "wizard": True,
                "message": "当前不是管理员，已打开官方安装向导——请按提示点完。\n"
                           "装完回来点「重新检测」看结果。\n"
                           "想全程无窗口静默装：用管理员身份重启本程序，再点一次这个按钮。"}

    async def install(self, kind: str, on_progress=None, force: bool = True,
                      mode: str = "") -> Dict[str, Any]:
        """下载 + 安装一个内核，返回 {success, message, version, files}

        mode 只有 GreenLuma 用：stealth = 隐身版 user32.dll（默认），inject = 注入版 DLLInjector。
        """
        spec = KERNEL_SPECS.get(kind)
        if not spec:
            return {"success": False, "message": "未知内核"}
        if spec.get("builtin"):
            return {"success": True, "version": CURRENT_VERSION, "files": [],
                    "message": "自研入库无需安装，已直接可用（不往 Steam 目录写任何文件）。"}
        sp = self.b.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "没有检测到 Steam 目录，先在设置页指定 Steam 路径。"}

        if kind == "greenluma":
            mode = (mode or spec.get("default_mode") or "stealth").strip().lower()
            if mode == "stealth":
                return await self.install_greenluma_stealth(on_progress=on_progress)

        def prog(pct, msg):
            if on_progress:
                try:
                    on_progress(pct, msg)
                except Exception:
                    pass

        tmp = self.b.temp_path / f'kernel_{kind}'
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)

        if kind == "greenluma":
            ok_all = True
            for i, name in enumerate(GREENLUMA_FILES):
                prog(int(i * 90 / len(GREENLUMA_FILES)), f"下载 {name}")
                dest = tmp / name
                got = False
                for u in self._raw_urls(name):
                    if await self._download_to_single(u, dest):
                        got = True
                        break
                if not got and name != 'DLLInjector.ini' and name != 'GreenLuma2025.txt':
                    ok_all = False
                    self.log.error(f"{name} 下载失败（所有通道都不通）。")
            if not ok_all:
                return {"success": False, "message": "GreenLuma 组件下载失败，检查网络后重试。"}
            prog(92, "释放到 Steam 主目录")
            placed = self._copy_to_steam(kind, tmp, sp)
            remote = await self._remote_greenluma()
            ver = remote.get("inject_version") or remote.get("version") or "GreenLuma 2025"
            try:
                (sp / spec["marker"]).write_text(ver, encoding='utf-8')
            except Exception:
                pass
            shutil.rmtree(tmp, ignore_errors=True)
            prog(100, "安装完成")
            self.log.info(f"GreenLuma 已装到 Steam 主目录：{placed}")
            return {"success": True, "message": f"GreenLuma 已安装到 {sp}", "version": ver, "files": placed}

        latest = await self.remote_latest(kind)
        if not latest.get("ok") or not latest.get("url"):
            return {"success": False, "message": latest.get("note") or "没有可用的下载源"}
        url, aname = latest["url"], latest.get("asset") or f"{kind}.zip"
        prog(2, f"下载 {aname}")
        arc = tmp / aname
        if not await self._download_to(url, arc, on_progress=lambda p, m: prog(2 + int(p * 0.73), m), label=f" {aname}"):
            return {"success": False, "message": "下载失败，检查网络/加速后重试。"}

        if spec.get("installer") and str(aname).lower().endswith(INSTALLER_EXT):
            keep = self._downloads_dir() / str(aname)
            kept = True
            try:
                shutil.copy2(arc, keep)
            except Exception:
                keep, kept = arc, False
            prog(76, "运行官方安装包")
            res = self.run_installer(keep, spec.get("silent_args") or [])
            if res.get("success"):
                landed = [n for n in ('hid.dll', 'XInput1_4.dll', 'dwmapi.dll')
                          if (sp / n).exists()]
                if not landed:
                    try:
                        reg = self.b._steam_registry_paths()
                    except Exception:
                        reg = []
                    where = reg[0] if reg else "注册表里记录的 Steam 目录"
                    msg = (f"安装程序跑完了，但 {sp} 下没有任何 SteamTools 组件 —— "
                           f"它多半按 {where} 装到别的 Steam 去了。请确认设置里的 Steam 路径，"
                           f"或把程序以管理员身份运行后重试。")
                    self.log.error(msg)
                    res["success"] = False
                    res["message"] = msg
                    res["landed"] = []
                else:
                    try:
                        (sp / spec["marker"]).write_text(str(latest.get("version") or aname),
                                                         encoding='utf-8')
                    except Exception:
                        pass
                    res["landed"] = landed
            res.update({"version": str(latest.get("version") or aname),
                        "files": [str(aname)], "installer": str(keep)})
            if kept:
                shutil.rmtree(tmp, ignore_errors=True)
            prog(100 if res.get("success") else 0, res.get("message") or "")
            return res

        prog(78, "解压")
        ex = tmp / 'x'
        if not self._extract(arc, ex):
            return {"success": False, "message": "解压失败（可能是 7z/rar，需要本地手动解压）。"}
        prog(88, "释放到 Steam")
        placed = self._copy_to_steam(kind, ex, sp)
        try:
            (sp / spec["marker"]).write_text(str(latest.get("version") or aname), encoding='utf-8')
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        prog(100, "安装完成")
        self.log.info(f"{spec['name']} 已安装：{placed}")
        return {"success": True, "message": f"{spec['name']} 已安装到 {sp}",
                "version": str(latest.get("version") or aname), "files": placed}

    async def _download_to_single(self, url: str, dest: Path) -> bool:
        """单通道下载（wuhu raw 已经带多镜像列表，这里不再加前缀）。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = await self._client().get(url, timeout=60, follow_redirects=True,
                                         headers={"User-Agent": STEAMTOOLS_UA})
            if r.status_code == 200 and r.content:
                dest.write_bytes(r.content)
                return True
        except Exception:
            pass
        return False

    async def install_from_local(self, kind: str, filename: str, data: bytes, on_progress=None) -> Dict[str, Any]:
        """从本地文件安装。

        · 上传的是安装包（.exe，比如 SteamTools 官方的 st-setup-x.y.z.exe）→ 直接运行它；
        · 上传的是 zip / 7z → 解压后把文件释放到 Steam 对应目录。
        """
        sp = self.b.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "没有检测到 Steam 目录。"}
        if kind not in KERNEL_SPECS:
            return {"success": False, "message": "未知内核"}
        tmp = self.b.temp_path / f'kernel_local_{kind}'
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        arc = tmp / (filename or 'pkg.zip')
        arc.write_bytes(data)

        if str(filename or '').lower().endswith(INSTALLER_EXT):
            keep = self._downloads_dir() / Path(filename).name
            kept = True
            try:
                shutil.copy2(arc, keep)
            except Exception:
                keep, kept = arc, False
            if on_progress:
                on_progress(60, "运行本地安装包")
            res = self.run_installer(keep, KERNEL_SPECS[kind].get("silent_args") or [])
            if res.get("success"):
                try:
                    (sp / KERNEL_SPECS[kind]["marker"]).write_text("本地安装包", encoding='utf-8')
                except Exception:
                    pass
            res.update({"files": [Path(filename).name], "installer": str(keep)})
            if kept:
                shutil.rmtree(tmp, ignore_errors=True)
            if on_progress:
                on_progress(100 if res.get("success") else 0, res.get("message") or "")
            return res

        if on_progress:
            on_progress(40, "解压本地安装包")
        ex = tmp / 'x'
        if not self._extract(arc, ex):
            return {"success": False, "message": "解压失败：只支持 zip / 7z（7z 需 py7zr）。"}
        if on_progress:
            on_progress(70, "释放到 Steam")
        placed = self._copy_to_steam(kind, ex, sp)
        try:
            (sp / KERNEL_SPECS[kind]["marker"]).write_text("本地安装包", encoding='utf-8')
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        if on_progress:
            on_progress(100, "安装完成")
        if not placed:
            return {"success": False, "message": "包里没找到可释放的文件，确认你传的是正确的安装包。"}
        return {"success": True, "message": f"已从本地包安装 {KERNEL_SPECS[kind]['name']}", "files": placed}

    def _steam_pids(self) -> List[int]:
        """当前 steam.exe 的 PID 列表（tasklist 输出是 GBK，按系统编码解）。"""
        r = run_hidden(['tasklist', '/FI', 'imagename eq steam.exe', '/FO', 'CSV', '/NH'], timeout=25)
        pids: List[int] = []
        for line in (r.stdout or '').splitlines():
            parts = [x.strip().strip('"') for x in line.split(',')]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.append(int(parts[1]))
        return pids

    def stealth_loaded(self) -> bool:
        """steam.exe 是否真的加载了 Steam 主目录下那份 user32.dll（= 隐身版生效）。

        隐身版不写任何日志、界面上也看不出来，唯一可靠判据是查进程模块路径：
        系统那份在 C:\\Windows\\System32，我们这份在 Steam 主目录。
        """
        sp = self.b.get_steam_path()
        if not sp or sys.platform != 'win32':
            return False
        root = str(sp).rstrip('\\/').lower()
        for pid in self._steam_pids():
            for name, path in process_modules(pid):
                if name.lower() == GREENLUMA_STEALTH_DLL and path.lower().startswith(root):
                    return True
        return False

    def greenluma_stealth_state(self) -> Dict[str, Any]:
        sp = self.b.get_steam_path()
        out: Dict[str, Any] = {"installed": False, "version": "", "path": None,
                               "size": 0, "loaded": False, "backup": None}
        if not sp:
            return out
        dst = sp / GREENLUMA_STEALTH_DLL
        if dst.exists():
            out["installed"] = True
            out["path"] = str(dst)
            try:
                out["size"] = dst.stat().st_size
            except OSError:
                pass
            out["version"] = self._read_marker(sp / GREENLUMA_STEALTH_MARKER)
        if (sp / GREENLUMA_STEALTH_BAK).exists():
            out["backup"] = str(sp / GREENLUMA_STEALTH_BAK)
        out["loaded"] = self.stealth_loaded()
        return out

    async def install_greenluma_stealth(self, on_progress=None) -> Dict[str, Any]:
        """下载 GreenLuma 隐身版 → Steam 主目录 user32.dll（原文件先备份）。"""
        def prog(p, m=""):
            if on_progress:
                try:
                    on_progress(p, m)
                except Exception:
                    pass
        sp = self.b.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "没有检测到 Steam 目录。"}
        tmp = Path(tempfile.mkdtemp(prefix='dxb_gls_'))
        try:
            prog(4, "查询隐身版最新版本")
            ver, url = await self._stealth_latest()
            if not url:
                return {"success": False, "message": "拿不到 GreenLuma 隐身版下载地址（网络不通或仓库不可达）。"}
            prog(12, f"下载 GreenLuma {ver or ''} 隐身版")
            zp = tmp / ('greenluma_stealth' + GREENLUMA_STEALTH_ASSET_EXT)
            if not await self._download_to(url, zp,
                                           on_progress=lambda p, m: prog(12 + int(p * 0.56), m),
                                           label=" GreenLuma 隐身版"):
                return {"success": False, "message": "下载 GreenLuma 隐身版失败（各镜像都不通）。"}
            prog(72, "解包")
            outdir = tmp / 'out'
            if not self._extract(zp, outdir):
                return {"success": False, "message": "GreenLuma 隐身版压缩包解压失败。"}
            dll = None
            for p in outdir.rglob('*'):
                if p.is_file() and p.name.lower() == GREENLUMA_STEALTH_INNER.lower():
                    dll = p
                    break
            if dll is None:
                for p in outdir.rglob('*.dll'):
                    dll = p
                    break
            if dll is None:
                return {"success": False, "message": f"压缩包里没找到 {GREENLUMA_STEALTH_INNER}。"}
            if dll.stat().st_size < GREENLUMA_STEALTH_MIN_SIZE:
                return {"success": False,
                        "message": f"取到的 {dll.name} 只有 {dll.stat().st_size} 字节，体积异常，已中止。"}
            prog(86, "释放到 Steam 主目录")
            dst = sp / GREENLUMA_STEALTH_DLL
            bak = sp / GREENLUMA_STEALTH_BAK
            if dst.exists() and not bak.exists():
                try:
                    shutil.copy2(dst, bak)
                except Exception as e:
                    self.log.warning(f"备份原 user32.dll 失败：{e}")
            shutil.copy2(dll, dst)
            (sp / GREENLUMA_STEALTH_MARKER).write_text(ver or 'unknown', encoding='utf-8')
            (sp / 'AppList').mkdir(parents=True, exist_ok=True)
            prog(100, "安装完成")
            self.log.info(f"GreenLuma 隐身版已装到 {dst}（{dll.stat().st_size} B）")
            return {"success": True, "mode": "stealth", "version": ver or 'unknown',
                    "files": [GREENLUMA_STEALTH_DLL],
                    "message": f"GreenLuma {ver or ''} 隐身版已装到 {dst}"
                               f"（原 user32.dll 已备份为 {GREENLUMA_STEALTH_BAK}）。\n\n"
                               "以后直接启动 Steam 就行：不需要注入器、不需要管理员、没有任何窗口。"
                               "AppID 放到 Steam 主目录的 AppList 文件夹。"}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def uninstall_greenluma_stealth(self) -> Dict[str, Any]:
        """移除隐身版：有备份就还原原 user32.dll，没备份直接删。"""
        sp = self.b.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "没有检测到 Steam 目录。"}
        dst = sp / GREENLUMA_STEALTH_DLL
        bak = sp / GREENLUMA_STEALTH_BAK
        try:
            if dst.exists():
                dst.unlink()
            restored = False
            if bak.exists():
                shutil.move(str(bak), str(dst))
                restored = True
            mk = sp / GREENLUMA_STEALTH_MARKER
            if mk.exists():
                mk.unlink()
        except Exception as e:
            return {"success": False, "message": f"移除失败：{e}"}
        return {"success": True, "mode": "stealth",
                "message": "已移除 GreenLuma 隐身版（user32.dll）。"
                           + ("原来的 user32.dll 已从备份还原。" if restored else "")
                           + "\n\n重启 Steam 后生效。"}

    def greenluma_log_tail(self, lines: int = 40) -> List[str]:
        """读 GreenLuma 自己写的日志（判断注入到底走到哪一步的真凭据）。"""
        sp = self.b.get_steam_path()
        if not sp:
            return []
        p = sp / 'GreenLuma_2025.log'
        if not p.exists():
            return []
        try:
            return p.read_text(encoding='utf-8', errors='ignore').splitlines()[-lines:]
        except Exception:
            return []

    def conflict_check(self) -> Dict[str, Any]:
        """检测内核共存冲突（纯检测，不动用户文件）。

        OpenSteamTool 靠劫持 dwmapi.dll / xinput1_4.dll 这类代理 DLL 把代码塞进 steam.exe；
        GreenLuma 又往 steam.exe 里挂二十来个 MinHook 钩子。两个一起挂，
        Steam 经常「起来一下就退」。所以三内核能同时*安装*，但运行时最好只启一个。
        """
        out = {"ok": True, "proxies": [], "greenluma": [], "stealth": False, "message": ""}
        sp = self.b.get_steam_path()
        if not sp or not sp.exists():
            return out
        out["proxies"] = [n for n in ('dwmapi.dll', 'xinput1_4.dll', 'winmm.dll', 'version.dll')
                          if (sp / n).exists()]
        out["greenluma"] = [n for n in ('GreenLuma_2025_x64.dll', 'DLLInjector.exe')
                            if (sp / n).exists()]
        out["stealth"] = (sp / GREENLUMA_STEALTH_DLL).exists()
        if out["proxies"] and (out["greenluma"] or out["stealth"]):
            out["ok"] = False
            names = []
            if out["greenluma"]:
                names.append("GreenLuma 注入版")
            if out["stealth"]:
                names.append("GreenLuma 隐身版（user32.dll）")
            out["message"] = (
                "OpenSteamTool 的代理 DLL（%s）和 %s 同时挂在 Steam 主目录。"
                "两者都会往 steam.exe 里挂钩子，一起用很容易让 Steam 启动后立刻退出。"
                "建议二选一：要用 GreenLuma 就把这些代理 DLL 移出 Steam 目录。"
                % ('、'.join(out["proxies"]), ' 和 '.join(names)))
        return out

    def injection_status(self) -> Dict[str, Any]:
        """真实检测：steam.exe 是否在跑、有没有加载 GreenLuma（注入版 / 隐身版）。

        module_details 是给「离线注入」页用的模块明细：同一个 user32.dll 会被 Steam
        同时加载两份（System32 一份、Steam 目录一份），只有 Steam 目录那份才是 GreenLuma
        隐身版，所以必须按「完整路径是否在 Steam 根目录下」区分，光看模块名会认错。
        """
        out = {"steam_running": False, "injected": False, "modules": [],
               "stealth": False, "module_details": [], "steam_path": ""}
        if sys.platform != 'win32':
            return out
        try:
            sp = self.b.get_steam_path()
            out["steam_path"] = str(sp) if sp else ""
        except Exception:
            pass
        r = run_hidden(['tasklist', '/fi', 'imagename eq steam.exe', '/m'], timeout=25)
        text = r.stdout or ""
        out["steam_running"] = 'steam.exe' in text.lower()
        mods = []
        for m in re.finditer(r'(GreenLuma[\w.\-]*\.dll|LumaCore[\w.\-]*\.dll)', text, re.I):
            if m.group(1) not in mods:
                mods.append(m.group(1))
        if out["steam_running"] and self.stealth_loaded():
            out["stealth"] = True
            mods.append(f"{GREENLUMA_STEALTH_DLL}（隐身版）")
        out["modules"] = mods
        out["injected"] = bool(mods)
        out["module_details"] = self.steam_module_details()
        return out

    def steam_module_details(self) -> List[Dict[str, Any]]:
        """枚举 steam.exe 实际加载的模块，标出哪些来自 Steam 根目录（= 内核 DLL）。"""
        out: List[Dict[str, Any]] = []
        sp = None
        try:
            sp = self.b.get_steam_path()
        except Exception:
            pass
        root = str(sp).lower().rstrip('\\/') if sp else ''
        for pid in self._steam_pids():
            for name, path in process_modules(pid):
                low = (path or '').lower()
                is_dxb = bool(root) and low.startswith(root + '\\') and (
                    low.endswith('user32.dll') or 'greenluma' in low or 'lumacore' in low
                    or low.endswith('opensteamtool.dll') or 'steamtools' in low)
                if is_dxb or low.endswith('user32.dll') or 'greenluma' in low:
                    out.append({"pid": pid, "module": name, "path": path, "from_steam": is_dxb})
        return out

    def _launch_plain(self, sp: Path, kind: str, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """不起注入器，直接拉 steam.exe —— 隐身版 GreenLuma / 代理 DLL 都由 Steam 自己加载。"""
        exe = sp / 'steam.exe'
        if not exe.exists():
            return {"success": False, "message": f"没找到 {exe}"}
        close_steam()
        time.sleep(1.2)
        try:
            subprocess.Popen([str(exe)], cwd=str(sp))
        except Exception as e:
            return {"success": False, "message": f"启动 Steam 失败：{e}"}
        if kind != 'stealth':
            return {"success": True, "message": "已启动 Steam（内核 DLL 会随进程自动加载）。",
                    "injection": self.injection_status()}
        loaded = False
        for _ in range(8):
            time.sleep(2)
            if self.stealth_loaded():
                loaded = True
                break
        st = self.injection_status()
        if loaded:
            msg = ("GreenLuma 隐身版已生效：steam.exe 加载了 Steam 主目录下的 user32.dll。\n"
                   "没有注入器、没有管理员、没有任何窗口；AppID 放在 Steam 主目录的 AppList 文件夹。")
            if conflict and not conflict.get("ok", True):
                msg += "\n\n⚠ " + conflict["message"]
            return {"success": True, "message": msg, "injection": st, "conflict": conflict}
        if st["steam_running"]:
            return {"success": False,
                    "message": "Steam 起来了，但没检测到它加载 Steam 主目录下的 user32.dll。\n\n"
                               "可能是安全软件拦了，或 Steam 走了别的启动方式（比如 bin\\x86launcher.exe）。"
                               "重启 Steam 再试一次；仍不行就用 OpenSteamTool / SteamTools 入库。",
                    "injection": st, "conflict": conflict}
        return {"success": False,
                "message": "Steam 启动后立刻退出了。\n\n"
                           "先点「移除隐身版」把 Steam 主目录里的 user32.dll 拿掉，确认 Steam 能正常启动，"
                           "再考虑换 OpenSteamTool / SteamTools 入库。",
                "injection": st, "conflict": conflict}

    async def _launch_inject(self, sp: Path, injector: Path,
                             conflict: Dict[str, Any]) -> Dict[str, Any]:
        """DLLInjector.exe 无窗口注入启动（注入版；对 Steam 版本敏感）。"""
        if not injector.exists():
            return {"success": False, "message": "没找到 DLLInjector.exe，先在下载管理里装 GreenLuma（注入版）。"}
        close_steam()
        time.sleep(1.5)
        run_hidden([str(injector)], cwd=str(sp), timeout=60)
        st = self.injection_status()
        for _ in range(6):
            time.sleep(2)
            st = self.injection_status()
            if st["injected"]:
                break
        if st["injected"]:
            return {"success": True,
                    "message": "已通过 DLLInjector 无窗口注入 GreenLuma，并拉起 Steam。",
                    "injection": st, "conflict": conflict}
        log = self.greenluma_log_tail(60)
        sig_fail = [l for l in log if 'Failed' in l]
        if not st["steam_running"]:
            msg = "GreenLuma 注入已执行（全程无窗口），但 Steam 起来后立刻退出了。"
            if sig_fail:
                msg += "\n\nGreenLuma 日志里的关键失败行：\n· " + "\n· ".join(sig_fail[:4])
                msg += ("\n\n这说明注入版的特征码跟你当前 Steam 构建对不上——注入版天生怕 Steam 更新。"
                        "\n建议改用「GreenLuma 隐身版」（不靠特征码扫描，对新 Steam 更耐用），"
                        "或用 OpenSteamTool / SteamTools 入库。")
            elif conflict and not conflict.get("ok", True):
                msg += "\n\n" + conflict["message"]
            else:
                msg += "\n\n没读到 GreenLuma 日志：检查 DLLInjector.ini 路径，或看安全软件是否拦了注入。"
            return {"success": False, "message": msg, "injection": st,
                    "log_tail": log[-12:], "conflict": conflict}
        return {"success": False,
                "message": "Steam 在跑，但没检测到 GreenLuma 模块（可能被杀软拦下）。"
                           + (("\n\n" + conflict["message"]) if conflict and not conflict.get("ok", True) else ""),
                "injection": st, "conflict": conflict}

    async def launch_steam(self, mode: str = "auto") -> Dict[str, Any]:
        """启动 Steam。

        - greenluma_stealth / stealth：隐身版（Steam 目录里的 user32.dll），普通启动即可；
        - greenluma：装了隐身版就走隐身版，否则回落到注入版；
        - greenluma_inject / inject：强制走 DLLInjector.exe 注入；
        - normal / auto：普通启动，代理 DLL（OpenSteamTool 等）随进程自动加载。
        """
        sp = self.b.get_steam_path()
        if not sp or not sp.exists():
            return {"success": False, "message": "没有检测到 Steam 目录。"}
        mode = (mode or 'auto').strip().lower()
        stealth = self.greenluma_stealth_state()
        injector = sp / 'DLLInjector.exe'
        conflict = self.conflict_check()

        if mode in ('greenluma_stealth', 'stealth'):
            if not stealth['installed']:
                return {"success": False,
                        "message": "还没装 GreenLuma 隐身版（Steam 主目录里没有 user32.dll）。"
                                   "先在「下载管理」里点 GreenLuma 的下载安装。"}
            return self._launch_plain(sp, 'stealth', conflict)

        if mode in ('greenluma_inject', 'inject'):
            return await self._launch_inject(sp, injector, conflict)

        if mode == 'greenluma':
            if stealth['installed']:
                return self._launch_plain(sp, 'stealth', conflict)
            return await self._launch_inject(sp, injector, conflict)

        return self._launch_plain(sp, 'normal', conflict)


NET_PROBE_TARGETS = [
    ("Steam 商店", "https://store.steampowered.com/api/appdetails?appids=730"),
    ("Steam 社区", "https://steamcommunity.com/"),
    ("Steam API", "https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/"),
    ("Steam 图片", "https://cdn.akamai.steamstatic.com/steam/apps/730/header.jpg"),
    ("GitHub API", "https://api.github.com/rate_limit"),
]


def _ver_tuple(v: str):
    """把 "1.4.8" / "v2.15" 这种版本串转成可比较的元组（用于内核版本对比）。"""
    m = re.match(r'v?(\d+(?:\.\d+)*)', str(v or '').strip())
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split('.'))


def kernel_update_state(local: str, remote: str, installed: bool = True) -> str:
    """返回 none（没远端信息）/ install（没装，有新版可装）/ latest（已是最新）/ update（可更新）/ unknown

    「没装过」和「装了但版本旧」是两回事：以前一律显示「可更新」，
    用户会看到「可更新」但 SteamTools 压根没装，纯粹误导。
    """
    if not remote:
        return "none"
    if not installed:
        return "install"
    if not local:
        return "unknown"
    lt, rt = _ver_tuple(local), _ver_tuple(remote)
    if lt == (0,) or rt == (0,):
        return "unknown"
    n = max(len(lt), len(rt))
    lt = lt + (0,) * (n - len(lt))
    rt = rt + (0,) * (n - len(rt))
    if lt < rt:
        return "update"
    return "latest"


async def net_selftest(timeout: float = 6.0, mode: str = "direct") -> Dict[str, Any]:
    """真实打一遍关键域名，返回每个域名的连通性/耗时。

    mode='direct' → 强制直连（忽略系统代理，回答“能不能不加速”）；
    mode='proxy'  → 走当前配置（自定义代理或系统环境变量）。
    两个都跑，前端就能明确告诉用户“直连到底行不行、差在哪”。
    """
    if mode == "direct":
        client = httpx.AsyncClient(verify=False, trust_env=False)
    else:
        proxy = ''
        try:
            cfg = DxbBackend()._load_config_sync() or {}
            proxy = str(cfg.get('network_proxy') or '').strip()
        except Exception:
            proxy = ''
        kw = dict(verify=False, trust_env=True)
        if proxy:
            kw['proxy'] = proxy if '://' in proxy else f'http://{proxy}'
        client = httpx.AsyncClient(**kw)

    async def probe(name: str, url: str):
        t0 = time.perf_counter()
        try:
            r = await client.get(url, timeout=timeout, follow_redirects=True)
            ms = int((time.perf_counter() - t0) * 1000)
            ok = r.status_code < 500
            return {"name": name, "ok": ok, "status": r.status_code, "ms": ms,
                    "error": "" if ok else f"HTTP {r.status_code}"}
        except Exception as e:
            ms = int((time.perf_counter() - t0) * 1000)
            return {"name": name, "ok": False, "status": 0, "ms": ms, "error": type(e).__name__}

    try:
        results = await asyncio.gather(*[probe(n, u) for n, u in NET_PROBE_TARGETS])
    finally:
        try:
            await client.aclose()
        except Exception:
            pass
    ok_count = sum(1 for r in results if r["ok"])
    return {"mode": mode, "ok": ok_count == len(results), "ok_count": ok_count,
            "total": len(results), "results": [dict(r) for r in results]}