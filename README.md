<div align="center">
  <img src="app_icon.png" alt="大轩巴入库器mini" width="128">
</div>

# 大轩巴入库器mini

> 一个 exe、一个内核、真入库。

Windows 桌面小工具，用来管理 Steam 入库清单、领取免费游戏、查看 DLC、识别已有入库记录。
内嵌网页界面，双击即用，不需要安装。

## 下载

从 [Releases · v1.0.0](https://github.com/daxuanba/daxuanba-Injector-mini/releases/tag/v1.0.0)
下载 `Daxuanba-Injector-mini.exe`（单文件，约 32 MB）。

程序目录只放这一个 exe；配置、日志、缓存、加速内核全部在
`%APPDATA%\DaXuanBa\DXB-Mini`（旧配置自动迁移）。卸载时删掉 exe 和这个目录即可。

## 功能

- **一个内核**：只内置 [大轩巴万能内核](https://github.com/daxuanba/daxuanba-steam-core)，
  文件分发型，按游戏 exe 位数把对应 DLL 放到游戏目录；不需要 GreenLuma / SteamTools / OpenSteamTool。
- **真入库**：免费游戏走 Steam 官方接口，提交前后各复查一次账号真实拥有列表，
  只有确实新增才算成功；不写本地假记录。
- **登录**：用户名 + 密码 + 邮箱验证码 / Steam 令牌，邮箱只显示后缀（如 `***@qq.com`）。
- **入库来源识别**：扫 Steam 的 `config/lua`、`config/stplug-in`、`AppList`，
  按数字 AppID 认出是哪个游戏、由哪个工具写入，并给出识别依据。
- **DLC**：只有有 DLC 的游戏才显示小按钮，弹窗展示原图标、名称和真实拥有状态；
  没 DLC 不显示，DLC 不作为单独入库项。
- **网络加速**：应用启动即自动开启，节点列表可选。
- **手搓 lua**：生成并写入本地解锁清单，明确标注这不是 Steam 账号入库。

## 相关

- 内核仓库：[daxuanba-steam-core](https://github.com/daxuanba/daxuanba-steam-core)
- 本仓库只发布二进制与说明文档，不含源代码。
