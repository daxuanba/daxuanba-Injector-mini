; 大轩巴入库器mini 安装程序（NSIS）
; 编译要求：文件必须是 UTF-8 with BOM，否则中文 Windows 下 Makensis 按 GBK 解析会乱码。
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinMessages.nsh"

Name "大轩巴入库器mini 安装程序"
OutFile "dist_installer\大轩巴入库器mini-安装包.exe"
; 安装目录用纯英文：避免中文路径在快捷方式 / 注册表 / 应用列表上的各种坑，
; 用户也能一眼找到（C:\Users\<你>\AppData\Local\Programs\DXB-Mini）
InstallDir "$LOCALAPPDATA\Programs\DXB-Mini"
InstallDirRegKey HKCU "Software\DXB\DXB-Mini" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID LZMA
SetCompressorDictSize 32

; MUI_ICON 是 MUI 宏的入参，必须写成 !define，写成裸命令会让编译直接 abort
!define MUI_ICON  "stage\assets\icon.ico"
!define MUI_UNICON "stage\assets\icon.ico"
BrandingText "大轩巴"

; ---------------- 品牌常量 ----------------
; APP_VERSION 由 build_installer.py 从 backend.CURRENT_VERSION 注入，
; 免得每次发版只改 backend / about.html 却漏了这里（v2.27 之前 DisplayVersion 就停在 2.26）
!define APP_VERSION "2.36"
!define APP_NAME   "大轩巴入库器mini"
!define APP_EXE    "${APP_NAME}.exe"
!define SM_FOLDER  "${APP_NAME}"
!define REG_ROOT   "Software\DXB\DXB-Mini"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\DXB-Mini"

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

; ---- 完成页：带「立即启动」勾选框 + 真启动函数 ----
!define MUI_FINISHPAGE_TITLE "安装完成"
!define MUI_FINISHPAGE_TEXT "大轩巴入库器mini 已经装好了。勾选下面选项可以立刻启动应用。"
!define MUI_FINISHPAGE_BUTTON "完成(&F)"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ${APP_NAME}(&R)"
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchApp"

!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

LangString MSG_CORE 2052 "加速内核已一并装上（目录 accel\），不装也行，应用内可以联网重新下载。"
LangString MSG_DESC 2052 "大轩巴入库器mini：Steam 免费游戏真入库 + 成就注入 + 网络加速。"

; ---------------- 安装 ----------------
Section "主程序" SEC01
    SectionIn 1 RO
    ; 先保证目录一定存在：以前出过「装完目录是空壳」的怪事，
    ; 目录被创建但文件没落进去时，至少用户能看见这个目录是应用自己建的。
    CreateDirectory "$INSTDIR"
    SetOutPath $INSTDIR
    File "/oname=${APP_EXE}" "stage\${APP_EXE}"
    File "stage\使用说明.txt"
    ; 注意：NSIS 的 File 不递归时会「去掉源路径的最后一个目录」，
    ; 直接 File "stage\assets\icon.ico" 会装成 $INSTDIR\stage\icon.ico（错！）
    ; 所以先切到 assets 再用 /oname 固定文件名。
    SetOutPath $INSTDIR\assets
    File "/oname=icon.ico" "stage\assets\icon.ico"
    SetOutPath $INSTDIR

    ; 加速内核：落盘后进程显示名就是应用自己，任务管理器里不出现第三方加速程序名
    SetOutPath $INSTDIR\accel
    File "/oname=${APP_EXE}" "stage\accel\${APP_EXE}"

    WriteUninstaller $INSTDIR\uninstall.exe

    WriteRegStr HKCU "${REG_ROOT}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "${REG_ROOT}" "Version" "Installer"
    ; 应用列表 / 控制面板卸载项
    WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\assets\icon.ico,0"
    WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "大轩巴"
    WriteRegStr HKCU "${UNINST_KEY}" "NoModify" "1"
    WriteRegStr HKCU "${UNINST_KEY}" "NoModifyPath" "1"
    WriteRegStr HKCU "${UNINST_KEY}" "NoChangeStartMenu" "1"
    WriteRegStr HKCU "${UNINST_KEY}" "NoRepair" "1"
    ; App Paths：让「运行」菜单 / start 命令能按名字找到它
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\${APP_EXE}" "" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "${UNINST_KEY}" "URLInfoAbout" "https://github.com/daxuanba/daxuanba-Injector-mini"

    ; 装到哪了，白纸黑字写给用户：桌面一份「安装位置.txt」，装完不用满盘找
    WriteIniStr "$DESKTOP\${APP_NAME} 安装位置.txt" "安装位置" "路径" "$INSTDIR"
    DetailPrint "已安装到：$INSTDIR"

    ; 「退出码 0 但安装目录是空壳」以前最难查：安装看着成功、文件其实没落地。
    ; 这里硬校验一次主程序在不在，不在就直接把话说清楚（多半是杀软隔离），
    ; 不再静默假装成功。
    IfFileExists "$INSTDIR\${APP_EXE}" ExeOk
    DetailPrint "警告：主程序没有落到安装目录！"
    MessageBox MB_ICONEXCLAMATION|MB_OK \
        "主程序文件没有落到安装目录：$\n$\n    $INSTDIR$\n$\n$\n多半是杀毒/安全软件把文件隔离了（这类程序被报毒很常见）。$\n请到「Windows 安全中心 → 病毒和威胁防护 → 保护历史记录 → 允许项」里放行本程序，再重新安装一次。$\n如果是 360 / 火绒 之类，请把本程序目录加进白名单。"
    ExeOk:
SectionEnd

Section "快捷方式" SEC02
    SectionIn 1
    SetOutPath $INSTDIR

    ; ---- 开始菜单（主程序 + 卸载，两个都给，卸载项必须有）----
    CreateDirectory "$STARTMENU\${SM_FOLDER}"
    CreateShortCut "$STARTMENU\${SM_FOLDER}\${APP_NAME}.lnk" \
        "$INSTDIR\${APP_EXE}" "" "$INSTDIR\assets\icon.ico" 0 SW_SHOWNORMAL
    CreateShortCut "$STARTMENU\${SM_FOLDER}\卸载 ${APP_NAME}.lnk" \
        "$INSTDIR\uninstall.exe" "" "$INSTDIR\assets\icon.ico" 0 SW_SHOWNORMAL

    ; ---- 桌面 ----
    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" \
        "$INSTDIR\${APP_EXE}" "" "$INSTDIR\assets\icon.ico" 0 SW_SHOWNORMAL

    ; 这里不能调 System::Call 刷新资源管理器：makensis 自带目录里没有 system.dll，
    ; 运行中调用会直接报错中止安装。桌面/开始菜单由 Explorer 自己定时刷新。
SectionEnd

Section "-" SEC00
    DetailPrint "$(MSG_CORE)"
SectionEnd

; ---------------- 卸载 ----------------
Section "卸载" SEC03
    SectionIn 1 RO
    SetOutPath $INSTDIR

    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$DESKTOP\${APP_NAME} 安装位置.txt"
    Delete "$STARTMENU\${SM_FOLDER}\${APP_NAME}.lnk"
    Delete "$STARTMENU\${SM_FOLDER}\卸载 ${APP_NAME}.lnk"
    RMDir /r "$STARTMENU\${SM_FOLDER}"

    Delete "$INSTDIR\uninstall.exe"
    Delete "$INSTDIR\使用说明.txt"
    RMDir /r "$INSTDIR\accel"
    RMDir /r "$INSTDIR\assets"
    Delete "$INSTDIR\${APP_EXE}"
    RMDir "$INSTDIR"

    DeleteRegKey HKCU "${REG_ROOT}"
    DeleteRegKey HKCU "${UNINST_KEY}"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\${APP_EXE}"
SectionEnd

; ---------------- 完成页启动函数 ----------------
; pywebview 壳启动后窗口要一两秒才出来，ExecShell 是异步的，这里给足时间再报结果。
Function LaunchApp
    StrCpy $0 "$INSTDIR\${APP_EXE}"
    IfFileExists $0 0 LaunchFailed
    ExecShell "open" "$0"
    Sleep 3000
    Return
    LaunchFailed:
    ; NSIS 字符串里的换行只能用 $\n（$CRLF 会被挨着的中文粘成变量名、${CRLF} 直接不认）
    MessageBox MB_ICONEXCLAMATION "启动失败$\n$\n找不到：$0$\n$\n多半是被杀毒软件拦了，去安装目录手动运行一次试试。"
FunctionEnd
