# -*- coding: utf-8 -*-
"""验证主界面右上角齿轮按钮能打开设置对话框。"""
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
LDOWN, LUP = 0x0002, 0x0004


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    user32.mouse_event(LDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    user32.mouse_event(LUP, 0, 0, 0, 0)


def windows():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append((buf.value, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return out


def shot(name, crop):
    x, y, w, h = crop
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$vs=[Windows.Forms.SystemInformation]::VirtualScreen;"
        "$b=New-Object Drawing.Bitmap $vs.Width,$vs.Height;"
        "$g=[Drawing.Graphics]::FromImage($b);"
        "$g.CopyFromScreen($vs.X,$vs.Y,0,0,$b.Size);$g.Dispose();"
        f"$b=$b.Clone([Drawing.Rectangle]::new({x},{y},{w},{h}),$b.PixelFormat);"
        f"$b.Save('{os.path.join(OUT, name)}',[Drawing.Imaging.ImageFormat]::Png);$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
time.sleep(0.8)
proc = subprocess.Popen([EXE])
time.sleep(7)

main = next(w for w in windows() if w[0] == "我爱截图")
x, y, w, h = main[1], main[2], main[3], main[4]
print("main:", main)

gx = x + w - 20 - 24 - 14 - 28 - 10 - 28 - 24
gy = y + 20 + 18 + 14
print("click gear at", gx, gy)
click(gx, gy)
time.sleep(1.6)

titles = [t for t, *_ in windows()]
print("windows now:", titles)
dlg = next((t for t in titles if t.startswith("设置")), None)
print("settings dialog:", dlg)
if dlg:
    win = next(w2 for w2 in windows() if w2[0] == dlg)
    _, dx, dy, dw, dh = win
    shot("h1_settings.png", (dx - 6, dy - 6, dw + 12, dh + 12))
    click(dx + dw - 34, dy + dh - 26)   # 取消按钮区域（大致）
    time.sleep(0.8)
print("after close, windows:", [t for t, *_ in windows()])

subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
print("done")
