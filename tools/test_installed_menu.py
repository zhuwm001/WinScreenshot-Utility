# -*- coding: utf-8 -*-
"""黑盒验证安装版：别的程序开着多级菜单时按快捷键，菜单有没有被留在画面里。

流程：安装版启动 -> 点最小化（收到托盘）-> 拉起"工程造价软件"模拟程序并展开
两级菜单 -> 发送快捷键 -> 截屏，检查遮罩下面的画面里还留着菜单（灰白的长条），
而不是只剩宿主窗口的品红底色。

用不含 Alt 的 Ctrl+Shift+Z：Alt 组合会被 Windows 的菜单机制吃掉（见 README）。
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "build")
os.makedirs(OUT, exist_ok=True)

EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "我爱截图", "我爱截图.exe")
CFG = os.path.expandvars(r"%APPDATA%\我爱截图\config.json")
INFO = os.path.join(OUT, "menu_rects.json")
HOTKEY = "Ctrl+Shift+Z"

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
        time.sleep(0.04)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.04)


def windows_of(pid):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append((hwnd, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return out


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def analyze(im):
    """在截屏里找宿主窗口（品红）和它里面的菜单（灰白长条）。

    遮罩会把画面整体压暗，所以判断用的是"三个通道接近"而不是绝对亮度。
    不依赖宿主报的坐标（它是不感知 DPI 的进程，坐标换算不可靠）。
    """
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    mag = 0
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y][:3]
            if r > 70 and g < 70 and b > 70 and abs(r - b) < 40:
                mag += 1
                x0 = min(x0, x)
                y0 = min(y0, y)
                x1 = max(x1, x)
                y1 = max(y1, y)
    if x1 < 0:
        return 0, None, 0
    gray = 0
    for y in range(y0, y1 + 1, 2):
        for x in range(x0, x1 + 1, 2):
            r, g, b = px[x, y][:3]
            if r > 90 and abs(r - g) < 14 and abs(g - b) < 14:
                gray += 1
    return mag, (x0, y0, x1, y1), gray


# ---------------------------------------------------------------- 准备
shutil.copyfile(CFG, CFG + ".bak")
cfg = json.load(open(CFG, encoding="utf-8"))
cfg["hotkey"] = HOTKEY
json.dump(cfg, open(CFG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"], capture_output=True)
time.sleep(0.8)

host = None
proc = None
try:
    proc = subprocess.Popen([EXE])
    time.sleep(6)
    main = [w for w in windows_of(proc.pid) if w[3] > 200 and w[4] > 200]
    check("安装版启动", proc.poll() is None and bool(main), main[:1])

    if main:
        hwnd, x, y, w, h = main[0]
        # 直接发"最小化"系统命令，比点按钮稳（按钮位置会随界面调整而变）
        user32.PostMessageW(hwnd, 0x0112, 0xF020, 0)   # WM_SYSCOMMAND / SC_MINIMIZE
        time.sleep(1.0)
        rest = [t for t in windows_of(proc.pid) if t[3] > 400 and t[4] > 400]
        check("最小化后主界面收起（在托盘里）", not rest, rest)

    # 别的程序打开多级菜单
    if os.path.exists(INFO):
        os.remove(INFO)
    host = subprocess.Popen([sys.executable, os.path.join(HERE, "win32_menu_host.py")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rects = None
    for _ in range(120):
        time.sleep(0.1)
        if os.path.exists(INFO):
            try:
                rects = json.load(open(INFO, encoding="utf-8"))
            except Exception:
                rects = None
            if rects and rects.get("sub"):
                break
    check("模拟软件的两级菜单已展开", bool(rects and rects.get("sub")), rects)

    # 按 Ctrl+Shift+Z
    key([0x11, 0x10, 0x5A])
    time.sleep(1.3)

    # 遮罩是全屏置顶窗口：屏幕正中/子菜单位置上的窗口应该属于安装版进程
    probe = (rects["sub"] if rects and rects.get("sub") else None)
    if probe:
        pt = wintypes.POINT(probe[0] + probe[2] // 2, probe[1] + probe[3] // 2)
    else:
        pt = wintypes.POINT(800, 500)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.WindowFromPoint(pt), ctypes.byref(pid))
    check("按 %s 后遮罩出现（安装版）" % HOTKEY, pid.value == proc.pid, pid.value)

    from PIL import ImageGrab
    shot = ImageGrab.grab(all_screens=True)
    path = os.path.join(OUT, "installed_menu_shot.png")
    shot.save(path)

    mag, box, gray = analyze(shot)
    print("宿主窗口:", mag, "| 范围:", box, "| 菜单像素:", gray)
    check("截屏里能看到宿主窗口", mag > 2000, mag)
    check("遮罩下面留住了菜单（含子菜单）", gray > 800, gray)
    print("截图已保存:", path)

    key([0x1B])        # Esc 收掉遮罩
    time.sleep(0.8)
finally:
    if host is not None:
        host.terminate()
    if proc is not None and proc.poll() is None:
        proc.terminate()
    shutil.copyfile(CFG + ".bak", CFG)

print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
