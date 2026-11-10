# -*- coding: utf-8 -*-
"""本轮改动的实机验证：主界面布局、隐藏到托盘提示、工具栏顺序、复制提示。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(ROOT, "build")

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "我爱截图", "我爱截图.exe")

VK_CONTROL, VK_MENU, VK_A, VK_ENTER = 0x11, 0x12, 0x41, 0x0D
KEYUP = 2
LDOWN, LUP = 0x0002, 0x0004


def press(seq):
    for vk in seq:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
    for vk in reversed(seq):
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.03)


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.2)
    user32.mouse_event(LDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    user32.mouse_event(LUP, 0, 0, 0, 0)


def drag(x1, y1, x2, y2):
    user32.SetCursorPos(int(x1), int(y1))
    time.sleep(0.2)
    user32.mouse_event(LDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    for i in range(1, 13):
        user32.SetCursorPos(int(x1 + (x2 - x1) * i / 12), int(y1 + (y2 - y1) * i / 12))
        time.sleep(0.02)
    time.sleep(0.12)
    user32.mouse_event(LUP, 0, 0, 0, 0)


def window_rect(title):
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value == title and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    found = []
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def shot(name, crop=None, scale=1):
    crop_args = ""
    if crop:
        x, y, w, h = crop
        crop_args = f"$b=$b.Clone([Drawing.Rectangle]::new({x},{y},{w},{h}),$b.PixelFormat);"
    scale_args = ""
    if scale != 1:
        scale_args = f"$b=New-Object Drawing.Bitmap $b,([int]($b.Width*{scale})),([int]($b.Height*{scale}));"
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$vs=[Windows.Forms.SystemInformation]::VirtualScreen;"
        "$b=New-Object Drawing.Bitmap $vs.Width,$vs.Height;"
        "$g=[Drawing.Graphics]::FromImage($b);"
        "$g.CopyFromScreen($vs.X,$vs.Y,0,0,$b.Size);$g.Dispose();"
        + crop_args + scale_args
        + f"$b.Save('{os.path.join(OUT, name)}',[Drawing.Imaging.ImageFormat]::Png);$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


def visible():
    r = window_rect("我爱截图")
    return r is not None


subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
time.sleep(0.8)

print("启动程序")
proc = subprocess.Popen([EXE])
time.sleep(7)
r = window_rect("我爱截图")
print("  主窗口:", r)
if not r:
    print("  窗口没出现，退出")
    sys.exit(1)
x, y, w, h = r
shot("r1_main.png", crop=(x, y, w, h))

print("点右上角「—」隐藏到托盘")
click(x + 390, y + 55)
time.sleep(0.7)
print("  主窗口还在:", visible())
shot("r2_hide_toast.png", crop=(1440, 780, 480, 300))
time.sleep(3.2)
shot("r3_toast_gone.png", crop=(1440, 780, 480, 300))
print("  3.2 秒后再截一张（用于确认提示已消失）")

print("再次启动 -> 单实例唤醒主界面")
subprocess.Popen([EXE])
time.sleep(4)
print("  主窗口回来了:", visible())

print("触发热键并框选")
press([VK_CONTROL, VK_MENU, VK_A])
time.sleep(2.2)
drag(300, 200, 1250, 780)
time.sleep(1.0)
shot("r4_toolbar.png", crop=(560, 740, 760, 120), scale=2)

print("按 Enter 复制")
press([VK_ENTER])
time.sleep(0.7)
shot("r5_copy_toast.png", crop=(1440, 780, 480, 300))
time.sleep(3.2)

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
img = app.clipboard().image()
print("  剪贴板图片:", img.width(), "x", img.height())

proc.terminate()
subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
print("done")
