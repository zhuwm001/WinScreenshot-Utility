@echo off
chcp 65001 >nul
rem 源码方式启动（不打包），Qt 平台插件路径由 src\qt_env.py 自动处理
setlocal
cd /d "%~dp0"

set "PYW=F:\编程工具\python310\pythonw.exe"
if not exist "%PYW%" (
  where pythonw.exe >nul 2>nul
  if errorlevel 1 (
    echo 找不到 pythonw.exe，请先装 Python 3.10 + PyQt5，或改本文件里的路径。
    pause
    exit /b 1
  )
  set "PYW=pythonw.exe"
)

start "" "%PYW%" "src\main.py"
