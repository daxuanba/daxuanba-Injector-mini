# 大轩巴入库器网页版 (DaXuanBa Injector Mini)

大轩巴自研的 Steam 清单下载与一键入库工具。基于 Flask 提供现代化 Web 图形界面，可一键下载 Steam 游戏清单（Manifest）及密钥（DepotKey），并自动配置到 **SteamTools** 或 **GreenLuma**，实现便捷入库。

## ✨ 核心特性

- **智能环境检测**：自动识别本地 Steam 路径，判断使用 SteamTools 还是 GreenLuma。
- **多源清单下载**：内置多个清单库，支持自定义 GitHub 仓库 / ZIP 直链作为清单源。
- **DLC 自动补全**：自动抓取并整合缺失的免费 / 无 DepotKey 的 DLC（多数据源回退）。
- **创意工坊直连**：输入创意工坊物品 ID 或链接即可下载对应清单，支持 depotkey 修补。
- **可视化入库管理**：网格卡片展示已解锁游戏，一键清理冗余 `.lua` / `.txt` / `.manifest` 文件。
- **现代化 Web UI**：深色 / 浅色双模式、自定义背景壁纸、Socket.IO 实时日志流。
- **针对国内网络优化**：内置连通性检测，自动启用镜像加速下载。
- **QT6 桌面窗口**：自带桌面壳 `dxb_desktop.py`，网页内嵌，无需系统浏览器。

## 🚀 快速开始

### 方式一：下载整合包（推荐）
前往 [Releases](https://github.com/daxuanba/daxuanba-Injector-mini/releases) 下载最新打包版本，解压后双击 `.exe` 启动。程序自带 QT6 窗口，网页内嵌运行。

### 方式二：从源码运行
1. 安装依赖：
   ```bash
   pip install Flask Flask-SocketIO httpx aiofiles colorlog vdf ujson
   ```
2. 启动网页服务（会弹出端口选择窗口，默认 `5000`，启动后浏览器自动打开）：
   ```bash
   python app.py
   ```
3. 或使用 QT6 桌面窗口（推荐，网页内嵌、不调用系统浏览器）：
   ```bash
   pip install PySide6
   python dxb_desktop.py
   ```

## 💡 使用指南

1. 在「设置」填写 GitHub Personal Access Token（强烈建议，提升 API 限额，避免频率限制）。
2. 主页「游戏搜索」输入游戏名获取对应 AppID。
3. 选择清单源，按需勾选「启用自动更新 / 额外入库所有 DLC / 修补 depotkey」。
4. 点击「开始任务」，等待日志完成，再点「重启 Steam」使配置生效。

## ⚠️ 免责声明

本工具完全免费开源，仅供代码学习与技术交流。**严禁任何形式的商业化使用或打包倒卖！** 使用本工具修改 Steam 客户端所带来的一切后果（包括但不限于账号封禁）由使用者自行承担。

## 📜 许可证

[MIT License](LICENSE)
