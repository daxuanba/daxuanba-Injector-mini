# -*- coding: utf-8 -*-
"""
大轩巴入库器mini · 发布上传脚本
================================
把 build_exe.py 产出的 exe 上传到 GitHub Releases，并用 release_body.json 作为发布说明。

用法（在真机、有网络环境下运行）：
    # 方式一：环境变量提供 token
    set GITHUB_TOKEN=ghp_xxx
    python upload_release.py

    # 方式二：把 token 写进同目录 gh_token.txt
    python upload_release.py

说明：
- tag 自动从 backend.py 的 CURRENT_VERSION 解析（如 2.5 -> v2.5），与 app 自更新逻辑保持一致。
- 资产名固定为 Daxuanba-Injector-mini.exe（ASCII，GitHub 资产名限制）；本地磁盘上的 exe 为中文名。
- 若同名 tag 已存在：更新说明 + 覆盖上传 exe 资产（先删旧资产）。
- 沙箱代理下若需跳过证书校验，设环境变量 UPLOAD_INSECURE=1（仅调试用）。
"""

import os
import re
import sys
import json
import requests
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = "daxuanba/daxuanba-Injector-mini"
API = f"https://api.github.com/repos/{REPO}"
LOCAL_EXE_NAME = "大轩巴入库器mini.exe"          # 本地构建产物（中文名）
ASSET_NAME = "Daxuanba-Injector-mini.exe"         # GitHub 资产名（ASCII）
TOKEN_FILE = BASE / "gh_token.txt"


def get_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    print("[错误] 未找到 GitHub Token：请设置环境变量 GITHUB_TOKEN，或把 token 写入 gh_token.txt")
    sys.exit(1)


def get_version_tag() -> str:
    bp = BASE / "backend.py"
    text = bp.read_text(encoding="utf-8")
    m = re.search(r"CURRENT_VERSION\s*=\s*['\"]([^'\"]+)['\"]", text)
    if not m:
        print("[错误] 无法从 backend.py 解析 CURRENT_VERSION")
        sys.exit(1)
    ver = m.group(1).strip()
    return f"v{ver}" if not ver.startswith("v") else ver


def get_body() -> str:
    p = BASE / "release_body.json"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return f"{ASSET_NAME} 发布"


def find_exe() -> Path:
    p = BASE / "dist" / LOCAL_EXE_NAME
    if p.exists():
        return p
    # 兜底：dist 下任意 exe
    for f in (BASE / "dist").glob("*.exe"):
        return f
    print(f"[错误] 未找到构建产物：{p}（请先运行 build_exe.py）")
    sys.exit(1)


def main():
    token = get_token()
    tag = get_version_tag()
    body = get_body()
    exe = find_exe()
    verify = os.environ.get("UPLOAD_INSECURE", "") != "1"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DaXuanBa-Injector",
    }

    print(f"[发布] repo={REPO} tag={tag}")
    print(f"[发布] 说明长度={len(body)} 资产={exe.name} -> {ASSET_NAME}")

    # 1) 查是否已存在该 tag 的 release
    r = requests.get(f"{API}/releases/tags/{tag}", headers=headers, verify=verify, timeout=30)
    release_id = None
    if r.status_code == 200:
        release_id = r.json().get("id")
        print(f"[发布] 已存在 release id={release_id}，将更新说明并覆盖资产")
    elif r.status_code == 404:
        # 创建 release
        cr = requests.post(
            f"{API}/releases",
            headers=headers,
            json={"tag_name": tag, "name": tag, "body": body, "draft": False, "prerelease": False},
            verify=verify,
            timeout=30,
        )
        if cr.status_code not in (200, 201):
            print(f"[错误] 创建 release 失败：{cr.status_code} {cr.text[:300]}")
            sys.exit(1)
        release_id = cr.json().get("id")
        print(f"[发布] 已创建 release id={release_id}")
    else:
        print(f"[错误] 查询 release 失败：{r.status_code} {r.text[:300]}")
        sys.exit(1)

    # 2) 删除已存在的同名资产（覆盖上传）
    rel = requests.get(f"{API}/releases/{release_id}", headers=headers, verify=verify, timeout=30).json()
    for asset in rel.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            print(f"[发布] 删除旧资产 id={asset['id']}")
            dr = requests.delete(f"{API}/releases/assets/{asset['id']}", headers=headers, verify=verify, timeout=30)
            if dr.status_code not in (200, 204):
                print(f"[警告] 删除旧资产失败：{dr.status_code}")

    # 3) 上传新资产
    up_headers = {**headers, "Content-Type": "application/octet-stream"}
    with open(exe, "rb") as f:
        ur = requests.post(
            f"{API}/releases/{release_id}/assets?name={ASSET_NAME}",
            headers=up_headers,
            data=f,
            verify=verify,
            timeout=600,
        )
    if ur.status_code not in (200, 201):
        print(f"[错误] 上传资产失败：{ur.status_code} {ur.text[:300]}")
        sys.exit(1)
    print(f"[发布] 资产上传成功：{ur.json().get('browser_download_url')}")

    # 4) 更新说明（创建时可能没带 body）
    pr = requests.patch(
        f"{API}/releases/{release_id}",
        headers=headers,
        json={"body": body, "name": tag},
        verify=verify,
        timeout=30,
    )
    if pr.status_code == 200:
        print("[发布] 发布说明已更新")
    else:
        print(f"[警告] 更新说明失败：{pr.status_code}")

    print("[完成] Release 已就绪：" + f"https://github.com/{REPO}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
