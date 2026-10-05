; 大轩巴入库器mini 安装程序（NSIS）
; 编译要求：文件必须是 UTF-8 with BOM，否则中文 Windows 下 Makensis 按 GBK 解析会乱码。
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"

Name "大轩巴入库器mini 安装程序"
OutFile "dist_installer\大轩巴入库器mini-安装包.exe"
InstallDir "$LOCALAPPDATA\Programs\大轩巴入库器mini"
InstallDirRegKey HKCU "Software\DXB\大轩巴入库器mini" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID LZMA
SetCompressorDictSize 32

!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

LangString MSG_RUN ${MUI_LANG_SIMPCHINESE} "安装完成。是否现在启动大轩巴入库器mini？"
LangString MSG_CORE ${MUI_LANG_SIMPCHINESE} "加速内核已一并装上（目录 accel\），不装也行，应用内可以联网重新下载。"

Section "主程序" SEC01
    SectionIn 1
    SetOutPath $INSTDIR
    File "/oname=大轩巴入库器mini.exe" "stage\大轩巴入库器mini.exe"
    File "stage\assets\icon.ico"
    File "stage\使用说明.txt"

    ; 加速内核：落盘后进程显示名就是应用自己，任务管理器里不出现第三方加速程序名
    SetOutPath $INSTDIR\accel
    File "/oname=大轩巴入库器mini.exe" "stage\accel\大轩巴入库器mini.exe"

    WriteUninstaller $INSTDIR\uninstall.exe
    WriteRegStr HKCU "Software\DXB\大轩巴入库器mini" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\大轩巴入库器mini" "DisplayName" "大轩巴入库器mini"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\大轩巴入库器mini" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\大轩巴入库器mini" "DisplayIcon" "$INSTDIR\大轩巴入库器mini.exe,0"
SectionEnd

Section "快捷方式" SEC02
    SectionIn 1
    CreateDirectory "$STARTMENU\大轩巴入库器mini"
    CreateShortCut "$STARTMENU\大轩巴入库器mini\大轩巴入库器mini.lnk" "$INSTDIR\大轩巴入库器mini.exe" "" "$INSTDIR\assets\icon.ico" 0
    CreateShortCut "$DESKTOP\大轩巴入库器mini.lnk" "$INSTDIR\大轩巴入库器mini.exe" "" "$INSTDIR\assets\icon.ico" 0
SectionEnd

LangString MSG_DESC ${MUI_LANG_SIMPCHINESE} "大轩巴入库器mini：Steam 免费游戏真入库 + 成就注入 + 网络加速。"

Section "-" SEC00
    DetailPrint "$(MSG_CORE)"
SectionEnd

Section "卸载" SEC03
    SectionIn 1
    Delete "$DESKTOP\大轩巴入库器mini.lnk"
    Delete "$STARTMENU\大轩巴入库器mini\大轩巴入库器mini.lnk"
    RMDir /r "$STARTMENU\大轩巴入库器mini"
    Delete "$INSTDIR\uninstall.exe"
    Delete "$INSTDIR\使用说明.txt"
    RMDir /r "$INSTDIR\accel"
    RMDir /r "$INSTDIR\assets"
    Delete "$INSTDIR\大轩巴入库器mini.exe"
    RMDir "$INSTDIR"
    DeleteRegKey HKCU "Software\DXB\大轩巴入库器mini"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\大轩巴入库器mini"
SectionEnd
