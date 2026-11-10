# -*- coding: utf-8 -*-
"""检查齿轮按钮的 tooltip 是否真的会弹出（全屏截图，等待更久）。"""
import ctypes
import os
import subprocess
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "build")
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "我爱截图", "我爱截图.exe")


def shot_full(name):
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$vs=[Windows.Forms.SystemInformation]::VirtualScreen;"
        "$b=New-Object Drawing.Bitmap $vs.Width,$vs.Height;"
        "$g=[Drawing.Graphics]::FromImage($b);"
        "$g.CopyFromScreen($vs.X,$vs.Y,0,0,$b.Size);$g.Dispose();"
        f"$b.Save('{os.path.join(OUT, name)}',[Drawing.Imaging.ImageFormat]::Png);$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
time.sleep(0.8)
proc = subprocess.Popen([EXE])
time.sleep(7)

found = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    if buf.value == "我爱截图" and user32.IsWindowVisible(hwnd):
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
    return True


user32.EnumWindows(cb, 0)
x, y, w, h = found[0]
print("window:", found)

hwnd = user32.FindWindowW(None, "我爱截图")
user32.SetForegroundWindow(hwnd)
time.sleep(0.6)

gx = x + w - 20 - 24 - 14 - 28 - 10 - 28 - 24
gy = y + 20 + 18 + 14

# 先移动到别处，再移进齿轮，确保产生新的 enter 事件
user32.SetCursorPos(gx - 200, gy + 100)
time.sleep(0.4)
user32.SetCursorPos(gx, gy)
time.sleep(3.0)
shot_full("g2_full.png")
print("cursor at", gx, gy)
print("foreground:", user32.GetForegroundWindow() == hwnd)

subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
print("done")
