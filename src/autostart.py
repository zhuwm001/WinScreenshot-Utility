# -*- coding: utf-8 -*-
"""开机自启：写 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run。

用当前用户注册表，不需要管理员权限，也不会触发 UAC。
写入的命令带 --autostart 参数，程序据此登录后静默启动到托盘。
"""
import os
import sys

import paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WoAiJieTu"
AUTOSTART_ARG = "--autostart"


def _winreg():
    import winreg  # 仅 Windows 有
    return winreg


def launch_command() -> str:
    """开机时执行的命令行：优先用 exe 自身，源码运行时退回 pythonw。"""
    if getattr(sys, "frozen", False):
        return '"%s" %s' % (sys.executable, AUTOSTART_ARG)

    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(pyw):
        exe = pyw
    script = os.path.join(paths.app_root(), "src", "main.py")
    return '"%s" "%s" %s' % (exe, script, AUTOSTART_ARG)


def current_command() -> str:
    """读取当前登记的启动命令；没登记则返回空串。"""
    try:
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            except OSError:
                return ""
            return str(value or "").strip()
    except Exception:
        return ""


def is_enabled() -> bool:
    return bool(current_command())


def apply(enabled: bool):
    """按开关写入或删除启动项，返回 (ok, message)。"""
    try:
        winreg = _winreg()
    except Exception:
        return False, "当前系统不支持开机启动设置。"

    try:
        if enabled:
            cmd = launch_command()
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
            if current_command() != cmd:
                return False, "开机启动项写入后校验失败，请稍后重试。"
            return True, ""

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except OSError:
                pass  # 本来就不存在
        return True, ""
    except PermissionError:
        return False, "没有权限修改开机启动项，请检查安全软件的限制。"
    except OSError as e:
        return False, "修改开机启动项失败：%s" % e


def sync(enabled: bool):
    """启动时校正注册表：开关为开但条目缺失或路径变了就重写，为关就清掉。"""
    if enabled:
        if current_command() != launch_command():
            return apply(True)
        return True, ""
    if is_enabled():
        return apply(False)
    return True, ""
