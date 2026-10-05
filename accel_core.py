"""大轩巴加速核心：加速内核管理（下载 / 启停 / 订阅 / 节点 / 系统代理）。

设计约束：
- 内核不随 exe 打包（60MB，塞进去太笨重），首次使用时自动从 GitHub Release 拉取。
- 不启用 TUN（需要管理员提权），走系统代理 + SOCKS/HTTP 端口，Steam 能读系统代理设置。
- 内核落地后一律改名为「大轩巴入库器mini.exe」（应用自己的名字），
  任务管理器 / 网络里只看到应用名，不出现第三方的加速程序名。
  旧版本下载的 mihomo-*.exe 会在首次调用时静默改名复用，不浪费已下载流量。
- 中止时按精确名收，绝不 taskkill 泛杀。
"""

import io
import json
import os
import re
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import winreg
import zipfile
from typing import Dict, List, Optional

MIHOMO_REPO = "MetaCubeX/mihomo"
# v3 构建支持 Hysteria2 / TUIC 等新协议，优先挑它
MIHOMO_ASSET_RE = re.compile(r'mihomo-windows-amd64-v3-go\d+-v([\d.]+)\.zip', re.I)
# 进程显示名 = 应用自己的名字（任务管理器里不出现第三方加速程序名）
CORE_NAME = "大轩巴入库器mini.exe"
LEGACY_CORE_NAMES = ("mihomo-core.exe", "mihomo-windows-amd64-v3-go125.exe")
CONFIG_NAME = "config.yaml"
LOG_NAME = "accel.log"
APP_NAME = "大轩巴入库器mini"

HTTP_PORT = 7890
SOCKS_PORT = 7891
CONTROL_PORT = 9090
CONTROL_HOST = "127.0.0.1"
CONTROL_SECRET = ""

PAC_NONE = ""


def _load_yaml(text: str):
    """订阅可能是裸 yaml，也可能是 base64/二次编码的字符串，都兜住。"""
    try:
        import yaml
        data = yaml.safe_load(text)
    except Exception:
        data = None
    if isinstance(data, str):
        try:
            import base64
            data = yaml.safe_load(base64.b64decode(data).decode('utf-8', 'ignore'))
        except Exception:
            try:
                data = yaml.safe_load(data)
            except Exception:
                data = None
    return data if isinstance(data, dict) else None


def _ua() -> Dict[str, str]:
    return {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }


def latest_release_info() -> Dict:
    """查上游最新版与下载直链，失败抛出由调用方转成人话。"""
    url = "https://api.github.com/repos/%s/releases/latest" % MIHOMO_REPO
    req = urllib.request.Request(url, headers=_ua())
    data = json.load(urllib.request.urlopen(req, timeout=25))
    tag = str(data.get('tag_name') or '')

    asset_name = ''
    asset_url = ''
    prefer = None
    for a in data.get('assets') or []:
        name = str(a.get('name') or '')
        if not name.lower().endswith('.zip'):
            continue
        if 'windows-amd64' not in name.lower():
            continue
        m = MIHOMO_ASSET_RE.search(name)
        if not m:
            continue
        prefer = (int(m.group(1).replace('.', '')), name)
        if not asset_name:
            asset_name, asset_url = name, str(a.get('browser_download_url') or '')
    if prefer and prefer[1]:
        asset_name, asset_url = prefer[1], ''
        for a in data.get('assets') or []:
            if str(a.get('name') or '') == asset_name:
                asset_url = str(a.get('browser_download_url') or '')
    if not asset_url:
        asset_url = ("https://github.com/%s/releases/download/%s/%s"
                     % (MIHOMO_REPO, tag, asset_name))
    return {'tag': tag, 'name': asset_name, 'url': asset_url}


DEFAULT_CONFIG = """\
# 大轩巴加速 · 内核配置（由应用生成，节点来源于订阅链接）
mixed-port: %(http)d
allow-lan: false
bind-address: '*'
mode: rule
log-level: info
external-controller: %(host)s:%(ctrl)d
external-ui: ''
secret: '%(secret)s'
ipv6: false
find-process-mode: always

dns:
  enable: true
  listen: 0.0.0.0:53
  enhanced-mode: redir-host
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - https://dns.alidns.com/resolve
    - https://doh.pub/dns-query
  fallback:
    - 1.1.1.1
  fallback-filter:
    type: geoip
    geoip-code: CN
    no-resolve: true

proxies: []
proxy-groups: []
rules:
  - MATCH,DIRECT
"""


class MihomoManager:
    def __init__(self, base_dir: str):
        self.dir = os.path.abspath(base_dir)
        self.core = os.path.join(self.dir, CORE_NAME)
        self.config = os.path.join(self.dir, CONFIG_NAME)
        self.logfile = os.path.join(self.dir, LOG_NAME)
        self._proc: Optional[subprocess.Popen] = None
        try:
            os.makedirs(self.dir, exist_ok=True)
        except Exception:
            pass

    # ---------------------------------------------------------------- 内核

    def _migrate_legacy_core(self) -> None:
        """旧版下好的内核（mihomo-windows-*.exe）改名成应用名复用，不重新下载。"""
        if os.path.isfile(self.core):
            return
        try:
            for n in os.listdir(self.dir):
                if not n.lower().startswith('mihomo') or not n.lower().endswith('.exe'):
                    continue
                p = os.path.join(self.dir, n)
                if os.path.isfile(p) and os.path.getsize(p) > 100000:
                    os.replace(p, self.core)
                    return
        except Exception:
            pass

    def core_exists(self) -> bool:
        self._migrate_legacy_core()
        return os.path.isfile(self.core) and os.path.getsize(self.core) > 100000

    def core_version(self) -> str:
        if not self.core_exists():
            return ''
        try:
            out = subprocess.run([self.core, '-v'], capture_output=True,
                                 timeout=10, encoding='utf-8', errors='ignore')
            return (out.stdout or out.stderr or '').strip()[:80]
        except Exception:
            return ''

    def ensure_core(self, on_progress=None) -> Dict:
        """缺内核就自动下载，返回 {'ok':bool, 'message':str, 'version':str}。"""
        if self.core_exists():
            return {'ok': True, 'message': '内核已就绪', 'version': self.core_version()}
        try:
            info = latest_release_info()
        except Exception as e:
            return {'ok': False, 'message': '获取内核版本失败：%s' % e}

        tmp = os.path.join(self.dir, '.core-download.tmp')
        try:
            with open(tmp + '.zip', 'wb') as f:
                req = urllib.request.Request(info['url'], headers=_ua())
                with urllib.request.urlopen(req, timeout=180) as r:
                    total = int(r.headers.get('Content-Length') or 0)
                    got = 0
                    while True:
                        chunk = r.read(262144)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if on_progress and total:
                            try:
                                on_progress(got, total)
                            except Exception:
                                pass
            with zipfile.ZipFile(tmp + '.zip') as z:
                names = [n for n in z.namelist()
                         if n.lower().endswith('.exe') and ('mihomo' in n.lower()
                                                            or 'clash' in n.lower())]
                if not names:
                    return {'ok': False, 'message': '内核压缩包里没找到可执行文件'}
                with z.open(names[0]) as src, open(tmp, 'wb') as dst:
                    dst.write(src.read())
            os.replace(tmp, self.core)
        except Exception as e:
            return {'ok': False, 'message': '内核下载失败：%s' % e}
        finally:
            for p in (tmp, tmp + '.zip'):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
        if not self.core_exists():
            return {'ok': False, 'message': '内核下载完成但文件异常'}
        return {'ok': True, 'message': '内核已下载', 'version': self.core_version()}

    # ---------------------------------------------------------------- 配置

    def build_default_config(self) -> None:
        with open(self.config, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_CONFIG % {'http': HTTP_PORT, 'host': CONTROL_HOST,
                                      'ctrl': CONTROL_PORT, 'secret': CONTROL_SECRET})

    def apply_subscription(self, url: str) -> Dict:
        """拉取 clash/mihomo 订阅并落盘，返回节点数与状态。"""
        sub = (url or '').strip()
        if not re.match(r'^https?://', sub, re.I):
            return {'ok': False, 'message': '订阅链接不是合法的 http/https 地址'}
        try:
            req = urllib.request.Request(sub, headers=_ua())
            body = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')
        except Exception as e:
            return {'ok': False, 'message': '订阅拉取失败：%s' % e}
        return self.apply_config_text(body)

    def apply_config_text(self, text: str) -> Dict:
        data = _load_yaml(text)
        if not isinstance(data, dict):
            return {'ok': False, 'message': '订阅内容不是有效的配置文件'}
        proxies = data.get('proxies') or []
        if not proxies and not (data.get('proxy-providers') or data.get('proxy_groups')):
            return {'ok': False, 'message': '订阅里没有节点（proxies 为空）'}
        data.setdefault('mixed-port', HTTP_PORT)
        data['allow-lan'] = False
        data['mode'] = 'rule'
        data['log-level'] = 'info'
        data['external-controller'] = '%s:%d' % (CONTROL_HOST, CONTROL_PORT)
        data['secret'] = CONTROL_SECRET
        data.setdefault('ipv6', False)
        data.setdefault('find-process-mode', 'always')
        dns = data.get('dns')
        if not isinstance(dns, dict):
            dns = {}
        dns.setdefault('enable', True)
        dns.setdefault('enhanced-mode', 'redir-host')
        dns.setdefault('fake-ip-range', '198.18.0.1/16')
        dns.setdefault('nameserver', ['https://dns.alidns.com/resolve',
                                      'https://doh.pub/dns-query'])
        data['dns'] = dns
        if not data.get('rules'):
            data['rules'] = ['MATCH,DIRECT']
        with open(self.config, 'w', encoding='utf-8') as f:
            import yaml as _y
            _y.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
        return {'ok': True, 'message': '配置已更新', 'nodes': len(proxies),
                'groups': len(data.get('proxy-groups') or [])}

    def config_status(self) -> Dict:
        if not os.path.isfile(self.config):
            return {'exists': False, 'nodes': 0}
        try:
            import yaml
            with open(self.config, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            return {'exists': True,
                    'nodes': len(data.get('proxies') or []),
                    'groups': len(data.get('proxy-groups') or [])}
        except Exception as e:
            return {'exists': True, 'nodes': 0, 'error': str(e)}

    # ---------------------------------------------------------------- 进程

    def running(self) -> bool:
        if self._proc is not None:
            return self._proc.poll() is None
        return self._port_open(CONTROL_PORT)

    @staticmethod
    def _port_open(port: int) -> bool:
        for _ in range(20):
            try:
                with socket.create_connection((CONTROL_HOST, port), timeout=0.6):
                    return True
            except OSError:
                time.sleep(0.3)
        return False

    def _control(self, path: str, method: str = 'GET', data: Optional[bytes] = None,
                 timeout: float = 8.0) -> Optional[Dict]:
        if not self.running():
            return None
        url = 'http://%s:%d%s' % (CONTROL_HOST, CONTROL_PORT, path)
        req = urllib.request.Request(url, data=data, method=method, headers=_ua())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode('utf-8', 'ignore')
            return json.loads(raw) if raw.strip().startswith(('{', '[')) else None
        except Exception:
            return None

    def start(self) -> Dict:
        if not self.core_exists():
            r = self.ensure_core()
            if not r['ok']:
                return {'ok': False, 'message': r['message']}
        if not os.path.isfile(self.config) or self.config_status().get('nodes', 0) == 0:
            self.build_default_config()
        logf = None
        try:
            # 内核输出必须落盘：解析失败/端口占用只是 fatal 一行日志，
            # 丢掉 stdout 的话用户只能看到「启动后立刻退出」这种废话。
            logf = open(self.logfile, 'ab', buffering=0)
            self._proc = subprocess.Popen(
                [self.core, '-d', self.dir, '-f', CONFIG_NAME],
                cwd=self.dir, stdin=subprocess.DEVNULL,
                stdout=logf, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as e:
            return {'ok': False, 'message': '内核启动失败：%s' % e}
        for _ in range(40):
            if self._port_open(CONTROL_PORT):
                return {'ok': True, 'message': '加速已启动',
                        'version': self.core_version()}
            if self._proc.poll() is not None and not self._port_open(CONTROL_PORT):
                return {'ok': False, 'message': self._tail_log(), 'log': self.logfile}
            time.sleep(0.4)
        return {'ok': False, 'message': '内核启动超时（端口 %d 可能被占）' % CONTROL_PORT,
                'log': self.logfile}

    def stop(self) -> Dict:
        p = self._proc
        self._proc = None
        if p is not None and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=6)
                return {'ok': True, 'message': '加速已停止'}
            except Exception:
                try:
                    p.kill()
                    return {'ok': True, 'message': '加速已停止（强制）'}
                except Exception as e:
                    return {'ok': False, 'message': '停止失败：%s' % e}
        if self.running():
            try:
                subprocess.run(['taskkill', '/F', '/IM', CORE_NAME, '/T'],
                               capture_output=True, timeout=10)
            except Exception:
                pass
            return {'ok': True, 'message': '已结束残留的内核进程'}
        return {'ok': True, 'message': '加速本来就没在跑'}

    def _tail_log(self, lines: int = 6) -> str:
        try:
            with open(self.logfile, 'r', encoding='utf-8', errors='ignore') as f:
                body = [x.strip() for x in f.readlines() if x.strip()]
            return ('内核启动失败：%s' % ' | '.join(body[-lines:]))[:400]
        except Exception:
            return '内核启动后立刻退出'

    def status(self) -> Dict:
        st = self.config_status()
        cur = self._control('/proxies') or {}
        return {'running': self.running(),
                'core': self.core_exists(),
                'version': self.core_version(),
                'core_path': self.core,
                'sub': st,
                'current': (self._control('/proxies') or {}).get('current', '') if cur else ''}

    # ---------------------------------------------------------------- 节点

    def nodes(self) -> Dict:
        data = self._control('/proxies') or {}
        if not data:
            return {'ok': False, 'message': '内核没在跑，或控制接口连不上'}
        items: List[Dict] = []
        for name, v in (data.get('proxies') or {}).items():
            if name in ('GLOBAL', 'DIRECT', 'REJECT') or 'naming' not in v:
                continue
            items.append({'name': name, 'type': v.get('type', ''),
                          'now': (v.get('now') or '')})
        items.sort(key=lambda x: x['name'])
        return {'ok': True, 'current': data.get('current', ''), 'nodes': items}

    def select(self, name: str) -> Dict:
        body = json.dumps({'name': str(name or ''), 'type': 'direct'}).encode('utf-8')
        r = self._control('/proxies/%s' % urllib.parse.quote(str(name or ''), safe=''),
                          method='PUT', data=body)
        if r is None:
            return {'ok': False, 'message': '切换节点失败（内核未运行或节点不存在）'}
        return {'ok': True, 'message': '已切换到 %s' % name, 'current': name}

    def delay_test(self, name: str = '') -> Dict:
        """对节点做延迟测试，返回可用列表。"""
        target = name or ''
        url = '/proxies/%s/delay' % urllib.parse.quote(target, safe='') if target else '/proxies/delay'
        body = json.dumps({'url': 'https://store.steampowered.com', 'timeout': 5000}).encode('utf-8')
        r = self._control(url, method='POST', data=body)
        if not isinstance(r, list):
            return {'ok': False, 'message': '延迟测试失败（内核未运行）'}
        out = [{'name': x.get('name', ''), 'delay': x.get('delay', 0)} for x in r if x.get('delay')]
        out.sort(key=lambda x: (x['delay'] if x['delay'] else 10 ** 6))
        return {'ok': True, 'nodes': out}


# ------------------------------------------------------------------ 系统代理

REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
WM_SETTINGCHANGE = 0x001A
HWND_BROADCAST = 0xFFFF


def system_proxy_state() -> Dict:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            val, _ = winreg.QueryValueEx(k, 'ProxyEnable')
            return {'enabled': bool(val), 'server': _reg_str(k, 'ProxyServer')}
    except FileNotFoundError:
        return {'enabled': False, 'server': ''}


def _reg_str(k, name: str, default: str = '') -> str:
    try:
        v, _ = winreg.QueryValueEx(k, name)
        return str(v or default)
    except OSError:
        return default


def _notify() -> None:
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, 0, 0x0002, 3000, None)
    except Exception:
        pass


def set_system_proxy(enable: bool, server: str = '127.0.0.1:%d' % HTTP_PORT) -> Dict:
    """开关系统代理（仅改 HKCU，不动系统级，卸载残留风险低）。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, 'ProxyServer', 0, winreg.REG_SZ, server)
                winreg.SetValueEx(k, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
                try:
                    winreg.DeleteValue(k, 'AutoConfigURL')
                except OSError:
                    pass
            else:
                winreg.SetValueEx(k, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
        _notify()
        return {'ok': True, 'message': '系统代理已%s' % ('开启' if enable else '关闭')}
    except Exception as e:
        return {'ok': False, 'message': '设置系统代理失败：%s' % e}
