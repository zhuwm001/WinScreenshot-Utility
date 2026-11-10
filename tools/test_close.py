# -*- coding: utf-8 -*-
"""验证关闭按钮 -> 最小化到托盘，以及托盘单击恢复。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]


def click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.25)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.1)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def windows_of(pid):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            found.append((hwnd, buf.value, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return found


env = dict(os.environ)
env["QT_PLUGIN_PATH"] = os.path.join(os.path.dirname(os.path.dirname(
    __import__("PyQt5").__file__)), "PyQt5", "Qt5", "plugins")
env["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(env["QT_PLUGIN_PATH"], "platforms")

proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "src", "main.py")],
                        cwd=ROOT, env=env)
time.sleep(7)
wins = windows_of(proc.pid)
print("启动后窗口:", wins)

target = next((w for w in wins if w[1] == "我爱截图"), None)
if not target:
    print("没找到主窗口")
    proc.terminate()
    sys.exit(1)

hwnd, _, x, y, w, h = target
user32.SetForegroundWindow(hwnd)      # 排除被其他窗口遮挡的干扰
time.sleep(0.6)
print(f"点关闭按钮 ({x + 388}, {y + 62})")
click(x + 388, y + 62)             # X 按钮在窗口内的相对位置 (388, 62)
time.sleep(1.5)
wins = windows_of(proc.pid)
print("点击后可见窗口数:", len(wins), "| 进程存活:", proc.poll() is None)

time.sleep(2)
print("再看一次（等托盘提示气泡）:", len(windows_of(proc.pid)))

proc.terminate()
time.sleep(0.5)
print("done")
