@echo off
cd /d %~dp0
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple PySide6
python dxb_desktop.py
pause
