# -*- coding: utf-8 -*-
"""补充验证：设置对话框、关闭到托盘、单实例唤醒、贴图窗口。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "build")

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "我爱截图", "我爱截图.exe")
VK_CONTROL, VK_MENU, VK_A, VK_F3, VK_ESCAPE = 0x11, 0x12, 0x41, 0x72, 0x1B
KEYUP = 2


def press(seq):
    for vk in seq:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
    for vk in reversed(seq):
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.03)


def click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def drag(x1, y1, x2, y2):
    user32.SetCursorPos(x1, y1)
    time.sleep(0.15)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.1)
    for i in range(1, 13):
        user32.SetCursorPos(int(x1 + (x2 - x1) * i / 12), int(y1 + (y2 - y1) * i / 12))
        time.sleep(0.02)
    time.sleep(0.1)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def shot(name, crop=None, scale=1):
    extra = ""
    if crop:
        x, y, w, h = crop
        extra += f"$b=$b.Clone([Drawing.Rectangle]::new({x},{y},{w},{h}),$b.PixelFormat);"
    if scale != 1:
        extra += f"$b=New-Object Drawing.Bitmap $b,([int]($b.Width*{scale})),([int]($b.Height*{scale}));"
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$vs=[Windows.Forms.SystemInformation]::VirtualScreen;"
        "$b=New-Object Drawing.Bitmap $vs.Width,$vs.Height;"
        "$g=[Drawing.Graphics]::FromImage($b);"
        "$g.CopyFromScreen($vs.X,$vs.Y,0,0,$b.Size);$g.Dispose();"
        + extra
        + f"$b.Save('{os.path.join(OUT, name)}',[Drawing.Imaging.ImageFormat]::Png);$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


def visible_windows(pid):
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


print("1) 启动")
proc = subprocess.Popen([EXE])
time.sleep(7)
wins = visible_windows(proc.pid)
print("   窗口:", wins)

# 主窗口位置推算
mx, my, mw, mh = 736, 349, 448, 342
for w in wins:
    if w[0] == "我爱截图":
        mx, my, mw, mh = w[1], w[2], w[3], w[4]
        break

print("2) 打开设置")
click(mx + 78, my + mh - 88)
time.sleep(1.5)
shot("w1_settings.png")

print("3) 关闭设置")
press([VK_ESCAPE])
time.sleep(0.8)

print("4) 点关闭按钮 -> 应最小化到托盘")
click(mx + mw - 30, my + 30)
time.sleep(1.5)
wins = visible_windows(proc.pid)
print("   可见窗口数:", len(wins), "| 进程存活:", proc.poll() is None)
shot("w2_after_close.png")

print("5) 再次运行 exe -> 单实例应唤醒原窗口")
p2 = subprocess.run([EXE], timeout=20)
time.sleep(2.0)
wins = visible_windows(proc.pid)
print("   第二个实例退出码:", p2.returncode, "| 现在可见窗口数:", len(wins))

print("6) 热键截图 + F3 贴图")
press([VK_CONTROL, VK_MENU, VK_A])
time.sleep(2.2)
drag(300, 250, 1000, 700)
time.sleep(0.8)
press([VK_F3])
time.sleep(1.8)
shot("w3_pinned.png")
wins = visible_windows(proc.pid)
print("   贴图后窗口:", wins)

proc.terminate()
time.sleep(0.8)
print("done")
