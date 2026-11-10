# -*- coding: utf-8 -*-
"""启动已安装的程序并截图主窗口，用于人工核对界面。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PyQt5.QtGui import QGuiApplication

user32 = ctypes.WinDLL("user32", use_last_error=True)
EXE = os.path.expandvars(r"%LOCALAPPDATA%\Programs\我爱截图\我爱截图.exe")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build")


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
            found.append((buf.value, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return found


def main():
    subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
    time.sleep(0.6)
    proc = subprocess.Popen([EXE])
    time.sleep(6.0)

    wins = windows_of(proc.pid)
    print("windows:", wins)
    target = next((w for w in wins if w[0] == "我爱截图"), None)
    if not target:
        print("主窗口没出现")
        return 1

    _, x, y, w, h = target
    user32.SetForegroundWindow(user32.FindWindowW(None, "我爱截图"))
    time.sleep(0.8)

    app = QGuiApplication(sys.argv)
    screen = app.primaryScreen()
    path = os.path.join(OUT, "check_author.png")
    screen.grabWindow(0, x, y, w, h).save(path)
    print("saved", path, w, "x", h)
    proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
