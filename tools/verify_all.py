# -*- coding: utf-8 -*-
"""综合验证：主界面、热键、框选、复制到剪贴板、托盘区、贴图窗口。"""
import ctypes
import os
import subprocess
import sys
import time

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

VK_CONTROL, VK_MENU, VK_A, VK_ENTER, VK_ESCAPE = 0x11, 0x12, 0x41, 0x0D, 0x1B
KEYUP = 2
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004


def press(seq):
    for vk in seq:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
    for vk in reversed(seq):
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.03)


def drag(x1, y1, x2, y2):
    user32.SetCursorPos(x1, y1)
    time.sleep(0.15)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    steps = 12
    for i in range(1, steps + 1):
        user32.SetCursorPos(int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.02)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def shot(name, crop=None, scale=1):
    crop_args = ""
    if crop:
        x, y, w, h = crop
        crop_args = f"$b=$b.Clone([Drawing.Rectangle]::new({x},{y},{w},{h}),$b.PixelFormat);"
    scale_args = ""
    if scale != 1:
        scale_args = (
            f"$b=New-Object Drawing.Bitmap $b,([int]($b.Width*{scale})),([int]($b.Height*{scale}));"
        )
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$vs=[Windows.Forms.SystemInformation]::VirtualScreen;"
        "$b=New-Object Drawing.Bitmap $vs.Width,$vs.Height;"
        "$g=[Drawing.Graphics]::FromImage($b);"
        "$g.CopyFromScreen($vs.X,$vs.Y,0,0,$b.Size);$g.Dispose();"
        + crop_args
        + scale_args
        + f"$b.Save('{os.path.join(OUT, name)}',[Drawing.Imaging.ImageFormat]::Png);$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


print("启动程序")
proc = subprocess.Popen([EXE])
time.sleep(7)
print("  运行中:", proc.poll() is None)
shot("v1_main.png")

print("触发热键 Ctrl+Alt+A")
press([VK_CONTROL, VK_MENU, VK_A])
time.sleep(2.2)
shot("v2_overlay.png")

print("框选区域")
drag(260, 220, 1180, 760)
time.sleep(1.0)
shot("v3_selected.png")

print("按 Enter 复制")
press([VK_ENTER])
time.sleep(1.5)
shot("v4_after.png")

print("读取剪贴板")
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
img = app.clipboard().image()
print("  剪贴板图片:", img.width(), "x", img.height())
if not img.isNull():
    img.save(os.path.join(OUT, "v5_clipboard.png"))

print("托盘区放大")
shot("v6_tray.png", crop=(1500, 990, 420, 90), scale=3)

proc.terminate()
time.sleep(0.8)
print("done")
