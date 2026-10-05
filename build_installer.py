# -*- coding: utf-8 -*-
"""大轩巴入库器mini · NSIS 安装包构建

流程：
  1. 准备 stage/ 目录（主程序 exe + assets + 使用说明 + accel/ 内核）
     —— 内核在这里就改名成「大轩巴入库器mini.exe」，保证装完进程显示名 = 应用自己
  2. installer.nsi 加 UTF-8 BOM（否则中文 Windows 下 Makensis 按 GBK 读成乱码）
  3. 调 makensis 编译成 大轩巴入库器mini-安装包.exe

用法：python build_installer.py
"""
import io
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
STAGE = BASE / 'stage'
DIST = BASE / 'dist_installer'
NSIS = Path(r"C:\Program Files (x86)\NSIS\makensis.exe")
NSI = BASE / 'installer.nsi'
NAME = '大轩巴入库器mini'
CORE_NAME = '%s.exe' % NAME          # 内核落盘名 = 应用自己的名字
SRC_CORE_DIR = BASE / 'core'         # 已下载的官方内核


def log(msg):
    print('[安装包] %s' % msg, flush=True)


def app_version():
    """从 backend.py 读 CURRENT_VERSION，作为 nsi 的 APP_VERSION（版本只维护一处）。"""
    try:
        src = (BASE / 'backend.py').read_text(encoding='utf-8', errors='ignore')
        import re
        m = re.search(r'CURRENT_VERSION\s*=\s*["\']([\d.]+)["\']', src)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ''


def sync_nsi_version(ver):
    """把 APP_VERSION 写进 installer.nsi（保留 BOM，改动最小）。"""
    nsi = BASE / 'installer.nsi'
    raw = nsi.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    new, n = re.subn(r'(!define APP_VERSION ")[^"]+(")', r'\g<1>%s\g<2>' % ver, text)
    if not n:
        raise RuntimeError('installer.nsi 里找不到 !define APP_VERSION')
    out = new.encode('utf-8')
    if bom:
        out = b'\xef\xbb\xbf' + out
    nsi.write_bytes(out)
    return n


def find_core():
    for p in sorted(SRC_CORE_DIR.glob('*.exe')):
        if p.stat().st_size > 1_000_000:
            return p
    return None


def prepare():
    if STAGE.exists():
        shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)

    exe = None
    for p in (BASE / 'dist_enc' / (NAME + '.exe'), BASE / 'dist' / (NAME + '.exe')):
        if p.is_file():
            exe = p
            break
    if not exe:
        exe = Path(sys.executable)
    log('主程序：%s' % exe)
    shutil.copy2(exe, STAGE / (NAME + '.exe'))

    assets = BASE / 'assets'
    shutil.copytree(assets, STAGE / 'assets')

    core = find_core()
    if not core:
        log('[失败] core/ 下没有内核文件，请先跑一次「下载内核」')
        return False
    log('内核：%s（%d B）' % (core.name, core.stat().st_size))
    core_dir = STAGE / 'accel'
    core_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(core, core_dir / CORE_NAME)

    (STAGE / '使用说明.txt').write_text(README, encoding='utf-8')
    return True


README = """大轩巴入库器mini · 完整包
==========================

【目录结构】
  大轩巴入库器mini.exe          主程序（双击即用）
  assets/                       图标等资源
  accel/大轩巴入库器mini.exe     加速内核（进程显示名同主程序）
  accel/config.yaml             加速配置（第一次启动加速时自动生成）

【使用】
  1. 双击「大轩巴入库器mini.exe」启动。
  2. 加速页：粘贴节点订阅链接 -> 启动加速。
  3. 点「一键加速 Steam」走 127.0.0.1:7890，Steam 客户端读系统代理即可生效。
  4. 不加速了点「关闭系统代理」，别忘，否则全局流量都走代理。

【注意】
  - 加速需要节点订阅链接；没有订阅内核能起，但所有规则走 DIRECT。
  - 内核走系统代理（not TUN），需要管理员权限的 TUN 模式没开。
  - 不会替你关系统代理，卸载前请先手动关闭。
  - accel/ 整个目录别单独丢，改名字也无所谓，但别删（删了应用内可重新下载）。
"""


def patch_nsi_bom() -> bool:
    raw = NSI.read_bytes()
    if raw.startswith(b'\xef\xbb\xbf'):
        return True
    NSI.write_bytes(b'\xef\xbb\xbf' + raw)
    log('installer.nsi 已补 UTF-8 BOM（中文界面必需）')
    return True


def compile_nsis():
    DIST.mkdir(parents=True, exist_ok=True)
    before = set(DIST.glob('*.exe'))
    env = dict(os.environ)
    proc = subprocess.run([str(NSIS), '/V3', '/O-', str(NSI)],
                          cwd=str(BASE), env=env,
                          capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    out = (proc.stdout or '') + (proc.stderr or '')
    tail = [l for l in out.splitlines() if l.strip()][-25:]
    print('\n'.join(tail), flush=True)
    if proc.returncode != 0:
        log('[失败] makensis 退出码 %d' % proc.returncode)
        return None
    for p in set(DIST.glob('*.exe')) - before:
        return p
    for p in DIST.glob('*.exe'):
        return p
    return None


def main():
    t0 = time.time()
    ver = app_version()
    if ver:
        n = sync_nsi_version(ver)
        log('版本号同步：installer.nsi APP_VERSION = %s（改动 %d 处）' % (ver, n))
    if not prepare():
        return 1
    if not NSIS.exists():
        log('[失败] 找不到 makensis：%s' % NSIS)
        return 1
    patch_nsi_bom()
    out = compile_nsis()
    if not out:
        return 1
    log('完成：%s（%d B，用时 %.1fs）' % (out, out.stat().st_size, time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
