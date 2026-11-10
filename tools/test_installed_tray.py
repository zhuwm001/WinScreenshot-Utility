# -*- coding: utf-8 -*-
"""黑盒验证安装版：主界面 -> 点"最小化(隐藏到托盘)" -> 按快捷键 -> 遮罩是否出现。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "build")
os.makedirs(OUT, exist_ok=True)

EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "我爱截图", "我爱截图.exe")
user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYUP = 2

ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


def key(vks):
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.03)


def find_windows(pid):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append({
                "hwnd": hwnd,
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "iconic": bool(user32.IsIconic(hwnd)),
                "rect": (r.left, r.top, r.right - r.left, r.bottom - r.top),
                "title": getattr(hwnd, "title", ""),
            })
        return True

    user32.EnumWindows(cb, 0)
    return out


def fullscreen_window(pid):
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    for w in find_windows(pid):
        x, y, ww, hh = w["rect"]
        if w["visible"] and ww >= sw - 4 and hh >= sh - 4:
            return w
    return None


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


MOD_VK = {"CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "WIN": 0x5B}


def hotkey_vks(seq):
    """'Ctrl+Shift+Z' -> [0x11, 0x10, 0x5A]"""
    out = []
    mods = []
    main_vk = None
    for token in (seq or "").split("+"):
        t = token.strip().upper()
        if t in MOD_VK:
            mods.append(t)
        elif len(t) == 1:
            main_vk = ord(t)
        elif t.startswith("F") and t[1:].isdigit():
            main_vk = 0x70 + int(t[1:]) - 1
    for m in mods:
        out.append(MOD_VK[m])
    if main_vk:
        out.append(main_vk)
    return out


subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
time.sleep(0.8)
proc = subprocess.Popen([EXE])
time.sleep(6)
check("安装版已启动", proc.poll() is None)
pid = proc.pid
wins = [w for w in find_windows(pid) if w["visible"] and w["rect"][2] > 200]
print("主窗口:", wins[:3])
check("找到主窗口", bool(wins), wins[:1])

if wins:
    # 主窗口不止一个候选（还有 Toast 之类），全部发一遍最小化最稳
    for w in wins:
        user32.PostMessageW(w["hwnd"], 0x0112, 0xF020, 0)
    time.sleep(0.9)
    still = [w for w in find_windows(pid)
             if w["visible"] and not w["iconic"] and w["rect"][2] > 200]
    check("最小化后主窗口不再挡着屏幕", not still, still[:1])

    # 按配置里的快捷键
    import json
    cfg = json.load(open(os.path.expandvars(r"%APPDATA%\我爱截图\config.json"),
                         encoding="utf-8-sig"))
    print("配置里的快捷键:", cfg.get("hotkey"))
    key(hotkey_vks(cfg.get("hotkey")))
    time.sleep(1.2)

    pt = wintypes.POINT(900, 500)
    fg_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.WindowFromPoint(pt), ctypes.byref(fg_pid))
    fs = fullscreen_window(pid)
    check("隐藏到托盘后快捷键唤起遮罩（安装版）",
          fs is not None or fg_pid.value == pid, fg_pid.value)

    shot = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
         "$b=New-Object Drawing.Bitmap([Windows.Forms.SystemInformation]::VirtualScreen.Width),"
         "([Windows.Forms.SystemInformation]::VirtualScreen.Height);"
         "$g=[Drawing.Graphics]::FromImage($b);"
         "$g.CopyFromScreen([Windows.Forms.SystemInformation]::VirtualScreen.X,"
         "[Windows.Forms.SystemInformation]::VirtualScreen.Y,0,0,$b.Size);"
         "$b.Save('%s',[Drawing.Imaging.ImageFormat]::Png);" % os.path.join(OUT, "installed_tray.png")],
        capture_output=True)
    print("截图返回码:", shot.returncode)

    key([0x1B])          # Esc 关掉遮罩
    time.sleep(0.8)

proc.terminate()
time.sleep(0.5)
print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
