; 大轩巴入库器mini 安装程序（NSIS）
; 编译要求：文件必须是 UTF-8 with BOM，否则中文 Windows 下 Makensis 按 GBK 解析会乱码。
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinMessages.nsh"

Name "大轩巴入库器mini 安装程序"
OutFile "dist_installer\大轩巴入库器mini-安装包.exe"
InstallDir "$LOCALAPPDATA\Programs\大轩巴入库器mini"
InstallDirRegKey HKCU "Software\DXB\大轩巴入库器mini" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID LZMA
SetCompressorDictSize 32

; ---------------- 品牌常量 ----------------
!define APP_NAME   "大轩巴入库器mini"
!define APP_EXE    "${APP_NAME}.exe"
!define SM_FOLDER  "${APP_NAME}"
!define REG_ROOT   "Software\DXB\${APP_NAME}"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

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

LangString MSG_CORE ${MUI_LANG_SIMPCHINESE} "加速内核已一并装上（目录 accel\），不装也行，应用内可以联网重新下载。"

; ---------------- 安装 ----------------
Section "主程序" SEC01
    SectionIn 1 RO
    SetOutPath $INSTDIR
    File "/oname=${APP_EXE}" "stage\${APP_EXE}"
    File "stage\assets\icon.ico"
    File "stage\使用说明.txt"

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

    ; 让「开始菜单 / 桌面」立刻刷新，免得用户装完看不到图标以为没装
    System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd

Section "-" SEC00
    DetailPrint "$(MSG_CORE)"
SectionEnd

LangString MSG_DESC ${MUI_LANG_SIMPCHINESE} "大轩巴入库器mini：Steam 免费游戏真入库 + 成就注入 + 网络加速。"

; ---------------- 卸载 ----------------
Section "卸载" SEC03
    SectionIn 1 RO
    SetOutPath $INSTDIR

    Delete "$DESKTOP\${APP_NAME}.lnk"
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
    IfFileExists $0 0 +2
    ExecShell "open" "$0"
    Sleep 3000
FunctionEnd
