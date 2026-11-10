# -*- coding: utf-8 -*-
"""真实 Win32 多级菜单 + 全局热键 的端到端测试。

场景：另一个进程（tools/win32_menu_host.py，模拟工程造价软件）打开了原生
两级菜单（父菜单 + "数据库/文件更新"的子菜单），此时按下截图快捷键，检查：

1. 遮罩被唤起，并且在最上层；
2. 截到的画面里菜单、子菜单都还在（不会因为它先消失就截了个空）；
3. 保存截图到 build/menu_shot.png，可人工放大确认。

父菜单/子菜单都通过键盘导航打开，位置稳定；宿主进程用独立进程，和真实
软件一致（跨进程）。
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
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtNetwork import QLocalServer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

import hotkey as hk  # noqa: E402
import main as appmain  # noqa: E402
from app_config import config  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

INFO = os.path.join(ROOT, "build", "menu_rects.json")
HOST_BG = (200, 30, 200)

user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]


def menu_windows_now():
    """当前系统里可见的 #32768 菜单窗口数量（多级菜单会 ≥2）。"""
    n = [0]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if buf.value == "#32768" and user32.IsWindowVisible(hwnd):
            n[0] += 1
        return True

    user32.EnumWindows(cb, 0)
    return n[0]

ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


# ---------------------------------------------------------------- SendInput
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

MOD_VK = {hk.MOD_CONTROL: 0x11, hk.MOD_ALT: 0x12, hk.MOD_SHIFT: 0x10, hk.MOD_WIN: 0x5B}


def key_event(vk, up=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def send_hotkey(mods, vk):
    mod_vks = [MOD_VK[m] for m in (hk.MOD_CONTROL, hk.MOD_ALT, hk.MOD_SHIFT, hk.MOD_WIN)
               if mods & m]
    for v in mod_vks:
        key_event(v)
        time.sleep(0.04)
    time.sleep(0.05)
    key_event(vk)
    key_event(vk, True)
    time.sleep(0.04)
    for v in reversed(mod_vks):
        key_event(v, True)


def pump(ms=200):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.008)


def near(c, t, tol=40):
    return all(abs(a - b) <= tol for a, b in zip(c, t))


def analyze(pix):
    """在截图里找宿主窗口（品红背景），再数它里面"浅色"像素有多少。

    不依赖坐标：宿主是不感知 DPI 的进程，它报的窗口矩形和截图的物理像素
    之间没有简单换算关系。直接用画面里的品红色定位最可靠。

    返回 (品红像素数, 品红区域矩形, 区域内的浅色像素数)。
    """
    img = pix.toImage()
    w, h = img.width(), img.height()
    magenta = 0
    light = 0
    x0, y0, x1, y1 = w, h, -1, -1
    step = 2
    for y in range(0, h, step):
        for x in range(0, w, step):
            c = img.pixelColor(x, y).getRgb()[:3]
            if near(c, HOST_BG, 18):
                magenta += 1
                if x < x0:
                    x0 = x
                if y < y0:
                    y0 = y
                if x > x1:
                    x1 = x
                if y > y1:
                    y1 = y
    if x1 < 0:
        return 0, None, 0
    # 只数宿主窗口内部（避开边框/title bar 之外的区域）里的浅色像素
    for y in range(y0, y1 + 1, step):
        for x in range(x0, x1 + 1, step):
            c = img.pixelColor(x, y).getRgb()[:3]
            if c[0] > 225 and c[1] > 225 and c[2] > 225:
                light += 1
    return magenta, (x0, y0, x1, y1), light


# ---------------------------------------------------------------- 启动被测程序
server = QLocalServer()
QLocalServer.removeServer("WoAiJieTu.Test.Menu")
server.listen("WoAiJieTu.Test.Menu")
ctrl = appmain.AppController(app, server)
ctrl.start(silent=False)
pump(400)
ctrl.win.hide()          # 用户常见状态：界面收起来，专心操作别的软件
pump(300)

# ---------------------------------------------------------------- 起宿主进程 + 菜单
if os.path.exists(INFO):
    os.remove(INFO)
host = subprocess.Popen([sys.executable, os.path.join(HERE, "win32_menu_host.py")],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT)
rects = None
for _ in range(120):
    pump(100)
    if os.path.exists(INFO):
        try:
            rects = json.load(open(INFO, encoding="utf-8"))
        except Exception:
            rects = None
        if rects and rects.get("sub"):
            break

print("菜单位置:", rects)
check("宿主程序的多级菜单已展开", bool(rects and rects.get("menu") and rects.get("sub")), rects)

seq = sys.argv[1] if len(sys.argv) > 1 else config.get("hotkey")
mods, vk = hk.parse_sequence(seq)
ctrl.hotkey.register(seq)
print("快捷键:", seq, "mods=%s vk=%s" % (mods, vk))

# ---------------------------------------------------------------- 按快捷键
print("按下前 修饰键:", hk._mods_down(), "| 目标:", mods,
      "| 屏幕上的菜单窗口:", menu_windows_now(), flush=True)
send_hotkey(mods, vk)
print("按下后 屏幕上的菜单窗口:", menu_windows_now(), flush=True)
pump(900)

ov = ctrl.overlay
check("按快捷键后遮罩被唤起", ov is not None)

if ov is not None and rects:
    shot = ov._shot
    print("截图尺寸:", shot.width(), "x", shot.height(), "dpr:", shot.devicePixelRatio())

    sx, sy, sw, sh = rects["sub"]
    # 子菜单上方看最上层窗口是不是我们的遮罩
    pt = wintypes.POINT(sx + max(1, sw // 2), sy + max(1, sh // 2))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.WindowFromPoint(pt), ctypes.byref(pid))
    check("遮罩在最上层（盖住子菜单）", pid.value == os.getpid(), pid.value)

    magenta, box, light = analyze(shot)
    print("宿主窗口像素:", magenta, "| 范围:", box, "| 其中的菜单浅色像素:", light)

    check("截图里能看到宿主窗口", magenta > 3000, magenta)
    # 菜单是浅灰底的矩形，展开时在宿主窗口里是一大块浅色；菜单被收起时一块都没有
    if hk.contains_alt(seq):
        # 已知限制：Alt 一按下，Windows 就把别人的菜单收起来（低级键盘钩子
        # 连"吞掉 Alt"都拦不住，实测菜单窗口直接消失）。设置界面里对此有说明。
        check("Alt 组合：菜单已被系统收起（已知限制，设置里已说明）", light == 0, light)
    else:
        check("截图里留住了菜单（含子菜单）", light > 1500, light)

    out = os.path.join(ROOT, "build", "menu_shot.png")
    shot.save(out)
    print("截图已保存:", out)

    ctrl.overlay._cancel()
    pump(300)

host.terminate()
pump(200)
ctrl.quit_app()
pump(200)
print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
