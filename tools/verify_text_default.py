# -*- coding: utf-8 -*-
"""实机验证：文字标注默认常规字重、笔画无重影。

流程：重置配置 -> 启动已安装程序 -> 热键截图 -> 框选 -> 文字工具 ->
粘贴一段文字（不按 B、不改字号）-> 提交 -> 回车复制 -> 从剪贴板取图检查。
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
VK_T, VK_V = 0x54, 0x56
KEYUP = 2
LDOWN, LUP = 0x0002, 0x0004


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


def set_clipboard_text(text):
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
    u32.SetClipboardData(13, h)
    u32.CloseClipboard()


def shot(name, crop=None):
    crop_args = ""
    if crop:
        x, y, w, h = crop
        crop_args = f"$b=$b.Clone([Drawing.Rectangle]::new({x},{y},{w},{h}),$b.PixelFormat);"
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$vs=[Windows.Forms.SystemInformation]::VirtualScreen;"
        "$b=New-Object Drawing.Bitmap $vs.Width,$vs.Height;"
        "$g=[Drawing.Graphics]::FromImage($b);"
        "$g.CopyFromScreen($vs.X,$vs.Y,0,0,$b.Size);$g.Dispose();"
        + crop_args
        + f"$b.Save('{os.path.join(OUT, name)}',[Drawing.Imaging.ImageFormat]::Png);$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


# 1) 配置回到默认：20px、不加粗
cfg_path = os.path.join(os.environ["APPDATA"], "我爱截图", "config.json")
try:
    cfg = json.load(open(cfg_path, encoding="utf-8"))
except Exception:
    cfg = {}
cfg.update({"config_schema": 2, "text_size": 20, "text_bold": False})
json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("配置:", cfg.get("text_size"), cfg.get("text_bold"))

subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
time.sleep(0.8)
proc = subprocess.Popen([EXE])
time.sleep(7)

print("热键 -> 框选")
press([VK_CONTROL, VK_MENU, VK_A])
time.sleep(2.2)
drag(380, 200, 1180, 720)
time.sleep(0.9)

print("文字工具 -> 点选区内 -> 粘贴")
tap(VK_T)
time.sleep(0.6)
shot("t0_toolbar.png", crop=(380, 700, 830, 130))
click(440, 280)
time.sleep(0.6)
set_clipboard_text("默认常规字重 20px\n第二行：检查有没有重影")
time.sleep(0.4)
press([VK_CONTROL, VK_V])
time.sleep(0.9)
shot("t1_editing.png", crop=(400, 240, 760, 260))

print("提交 -> 复制")
press([VK_CONTROL, VK_ENTER])
time.sleep(0.9)
shot("t2_committed.png", crop=(400, 240, 760, 260))
press([VK_ENTER])
time.sleep(1.4)

# 从剪贴板取回导出的图片
from PyQt5.QtWidgets import QApplication  # noqa: E402
app = QApplication(sys.argv)
img = QApplication.clipboard().image()
print("剪贴板图片:", img.width(), "x", img.height())
if not img.isNull():
    src = os.path.join(OUT, "t3_clip.png")
    img.save(src)
    # 裁出文字附近区域放大，便于检查笔画
    crop = img.copy(20, 20, 320, 90)
    crop.scaled(crop.width() * 3, crop.height() * 3).save(os.path.join(OUT, "t4_zoom.png"))

press([VK_ESC])
time.sleep(1.0)
subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
print("done")
