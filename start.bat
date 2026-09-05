@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 自动探测 Python：常见 conda / 系统 Python / py 启动器
set "PY="
if exist "G:\miniconda3\python.exe" set "PY=G:\miniconda3\python.exe"
if exist "C:\ProgramData\miniconda3\python.exe" set "PY=C:\ProgramData\miniconda3\python.exe"
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY set "PY=python"

echo 使用 Python: %PY%
"%PY%" server.py
pause
