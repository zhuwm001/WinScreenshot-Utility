# -*- coding: utf-8 -*-
"""检查已安装程序的窗口是否可见、位置、是否在最前。"""
import ctypes
import os
import subprocess
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND

EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "我爱截图", "我爱截图.exe")
proc = subprocess.Popen([EXE])
time.sleep(6)

# 枚举进程的顶层窗口
windows = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def enum_proc(hwnd, lparam):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == proc.pid and user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        windows.append((hwnd, buf.value, r.left, r.top, r.right - r.left, r.bottom - r.top))
    return True


user32.EnumWindows(enum_proc, 0)
print("pid:", proc.pid)
for w in windows:
    print("  hwnd=%s title=%r rect=(%d,%d) size=%dx%d" % w)

fg = user32.GetForegroundWindow()
print("foreground hwnd:", fg, "| is our window:", any(fg == w[0] for w in windows))

proc.terminate()
time.sleep(0.5)
