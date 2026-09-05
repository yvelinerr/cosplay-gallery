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

rem 首次运行生成随机访问令牌（保存在 data\token.txt）
if not exist "data\token.txt" (
  "%PY%" -c "import secrets;print(secrets.token_hex(16))" > "data\token.txt"
)
set /p TOKEN=<"data\token.txt"

rem 尝试放行防火墙（需管理员权限；失败则提示手动添加）
netsh advfirewall firewall delete rule name="CosplayGallery 8765" >nul 2>&1
netsh advfirewall firewall add rule name="CosplayGallery 8765" dir=in action=allow protocol=TCP localport=8765 >nul 2>&1
if errorlevel 1 (
  echo [提示] 如局域网无法访问，请用管理员身份运行:
  echo        netsh advfirewall firewall add rule name="CosplayGallery" dir=in action=allow protocol=TCP localport=8765
)

echo ================================================================
echo   共享模式已启动（监听 0.0.0.0:8765）
echo   访问令牌: %TOKEN%
echo   请把令牌发给要访问的人，对方打开页面后输入即可
echo   （自己本机访问: http://127.0.0.1:8765 也要输入一次）
echo   公网访问需配合内网穿透，见 README 中的「远程共享」
echo ================================================================
set "HOST=0.0.0.0"
set "ACCESS_TOKEN=%TOKEN%"
"%PY%" server.py
pause
