# -*- coding: utf-8 -*-
"""实机验证：文字工具的字号 / 粗细控件。

流程：启动安装好的程序 -> 热键截图 -> 框选 -> 切文字工具 -> 用快捷键调字号/字重 ->
粘贴一段文字 -> 截图检查工具栏与文字效果 -> Esc 取消，检查配置是否记住字号。
"""
import ctypes
import json
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

VK_CONTROL, VK_MENU, VK_A, VK_ENTER, VK_ESC = 0x11, 0x12, 0x41, 0x0D, 0x1B
VK_T, VK_B, VK_V = 0x54, 0x42, 0x56
VK_BRACKET_RIGHT = 0xDD
KEYUP = 2
LDOWN, LUP = 0x0002, 0x0004

BAR_CROP = (735, 772, 570, 78)


def press(seq):
    for vk in seq:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.04)
    for vk in reversed(seq):
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.04)


def tap(vk, times=1):
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.12)


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


def set_clipboard(text):
    """用 Win32 API 写剪贴板，比 Qt 的拷贝更即时（不依赖消息循环）。"""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HGLOBAL]
    data = text.encode("utf-16-le") + b"\x00\x00"
    h = k32.GlobalAlloc(0x0002, len(data))
    p = k32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(h)
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.1)
    u32.EmptyClipboard()
    u32.SetClipboardData(13, h)      # CF_UNICODETEXT
    u32.CloseClipboard()


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


subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
time.sleep(0.8)

print("启动已安装的程序")
proc = subprocess.Popen([EXE])
time.sleep(7)
print("  主窗口:", window_rect("我爱截图"))

print("热键 + 框选")
press([VK_CONTROL, VK_MENU, VK_A])
time.sleep(2.2)
drag(300, 200, 1250, 780)
time.sleep(0.9)

print("切到文字工具（T）")
tap(VK_T)
time.sleep(0.6)
shot("f1_bar_20.png", crop=BAR_CROP, scale=2)

print("按 ] 四次（20 -> 28），按 B 取消粗体")
tap(VK_BRACKET_RIGHT, 4)
time.sleep(0.4)
tap(VK_B)
time.sleep(0.5)
shot("f2_bar_28_regular.png", crop=BAR_CROP, scale=2)

print("点选区内空白处 -> 粘贴文字")
click(430, 330)
time.sleep(0.6)
set_clipboard("字号 28 · 常规字重\n按 ] 放大，按 B 切换粗体")
time.sleep(0.5)
press([VK_CONTROL, VK_V])
time.sleep(0.9)
shot("f3_editing.png", crop=(300, 200, 960, 590))
press([VK_CONTROL, VK_ENTER])
time.sleep(0.9)
shot("f4_committed.png", crop=(300, 200, 960, 590))

cfg_path = os.path.join(os.environ["APPDATA"], "我爱截图", "config.json")
print("Esc 取消截图")
press([VK_ESC])
time.sleep(1.6)
shot("f5_after_esc.png", crop=(700, 300, 560, 400))
print("  主窗口回来了（说明遮罩已关闭）:", window_rect("我爱截图"))
try:
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    print("  配置记住的字号/字重:", cfg.get("text_size"), cfg.get("text_bold"))
except Exception as e:
    print("  读取配置失败:", e)

subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
print("done")
