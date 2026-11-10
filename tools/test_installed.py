# -*- coding: utf-8 -*-
"""端到端验证：启动已安装程序 -> 模拟全局热键 -> 截图取证 -> Esc 退出遮罩。"""
import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "build")

EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "我爱截图", "我爱截图.exe")

user32 = ctypes.WinDLL("user32", use_last_error=True)
VK_CONTROL, VK_MENU, VK_A, VK_ESCAPE = 0x11, 0x12, 0x41, 0x1B
KEYUP = 2


def key(seq):
    for vk in seq:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
    for vk in reversed(seq):
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.03)


def shot(name):
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$b=New-Object Drawing.Bitmap([Windows.Forms.SystemInformation]::VirtualScreen.Width),"
        "([Windows.Forms.SystemInformation]::VirtualScreen.Height);"
        "$g=[Drawing.Graphics]::FromImage($b);"
        "$g.CopyFromScreen([Windows.Forms.SystemInformation]::VirtualScreen.X,"
        "[Windows.Forms.SystemInformation]::VirtualScreen.Y,0,0,$b.Size);"
        f"$b.Save('{os.path.join(OUT, name)}',[Drawing.Imaging.ImageFormat]::Png);"
        "$g.Dispose();$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


print("exe:", EXE, os.path.exists(EXE))
proc = subprocess.Popen([EXE])
time.sleep(6)
print("process running:", proc.poll() is None)
shot("verify_main.png")

# 模拟 Ctrl+Alt+A
key([VK_CONTROL, VK_MENU, VK_A])
time.sleep(2.0)
shot("verify_overlay.png")

# Esc 关闭遮罩
key([VK_ESCAPE])
time.sleep(1.2)
shot("verify_after.png")

proc.terminate()
time.sleep(0.8)
print("done")
