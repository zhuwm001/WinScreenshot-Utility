# -*- coding: utf-8 -*-
"""反复截图的完整流程测试：截完一次之后，下一次快捷键还能不能唤起遮罩。

覆盖三条收尾路径：回车复制、Esc 取消、图钉贴到桌面。
（之前出现过"截过一次之后热键就再也不响应"，根因就是收尾路径没把
 self.overlay 清掉，后续全被"已经在截图"的判断挡住了。）
"""
import ctypes
import os
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

from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtNetwork import QLocalServer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

import hotkey as hk  # noqa: E402
import main as appmain  # noqa: E402
from app_config import config  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", wintypes.WPARAM)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


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


def mouse_event(flags, x=0, y=0):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(x, y, 0, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def screen_to_abs(x, y):
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    return (int((x - vx) * 65535 / max(1, vw - 1)),
            int((y - vy) * 65535 / max(1, vh - 1)))


def send_hotkey(mods, vk):
    mod_vks = [MOD_VK[m] for m in (hk.MOD_CONTROL, hk.MOD_ALT, hk.MOD_SHIFT, hk.MOD_WIN)
               if mods & m]
    for v in mod_vks:
        key_event(v)
        time.sleep(0.03)
    time.sleep(0.04)
    key_event(vk)
    key_event(vk, True)
    time.sleep(0.03)
    for v in reversed(mod_vks):
        key_event(v, True)


def pump(ms=200):
    # 注意：processEvents() 不处理 DeferredDelete，WA_DeleteOnClose 的窗口要等
    # 真正的 exec_() 循环才会析构。测试里手动补上这一步，行为才和实际运行一致。
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        app.sendPostedEvents(None, 52)      # 52 = QEvent.DeferredDelete
        time.sleep(0.008)


def drag(p1, p2):
    mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, *screen_to_abs(p1.x(), p1.y()))
    pump(80)
    mouse_event(MOUSEEVENTF_LEFTDOWN)
    for i in range(1, 9):
        pt = QPoint(p1.x() + (p2.x() - p1.x()) * i // 8,
                    p1.y() + (p2.y() - p1.y()) * i // 8)
        mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, *screen_to_abs(pt.x(), pt.y()))
        pump(40)
    mouse_event(MOUSEEVENTF_LEFTUP)
    pump(250)


ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


server = QLocalServer()
QLocalServer.removeServer("WoAiJieTu.Test.Cycle")
server.listen("WoAiJieTu.Test.Cycle")
ctrl = appmain.AppController(app, server)
ctrl.start(silent=False)
pump(400)
ctrl.win.hide()
pump(300)

seq = config.get("hotkey")
mods, vk = hk.parse_sequence(seq)
print("快捷键:", seq)

P1, P2 = QPoint(420, 320), QPoint(820, 620)

# ---------- 1) 回车复制 ----------
send_hotkey(mods, vk)
pump(700)
check("1 热键唤起遮罩", ctrl.overlay is not None)
drag(P1, P2)
if ctrl.overlay is not None:
    check("1 框选出选区", not ctrl.overlay._sel.isNull(), ctrl.overlay._sel)
key_event(0x0D)          # Enter = 复制
key_event(0x0D, True)
pump(800)
check("1 回车后遮罩已关闭", ctrl.overlay is None)
check("1 图片进了剪贴板", not app.clipboard().image().isNull())

send_hotkey(mods, vk)
pump(800)
check("1 复制之后再按快捷键，仍能唤起", ctrl.overlay is not None)
ctrl.overlay._cancel()
pump(400)

# ---------- 2) Esc 取消 ----------
send_hotkey(mods, vk)
pump(700)
check("2 热键唤起遮罩", ctrl.overlay is not None)
pump(400)                # 等遮罩真正拿到键盘焦点
key_event(0x1B)
key_event(0x1B, True)
pump(700)
check("2 Esc 后遮罩已关闭", ctrl.overlay is None)
send_hotkey(mods, vk)
pump(800)
check("2 取消之后再按快捷键，仍能唤起", ctrl.overlay is not None)
ctrl.overlay._cancel()
pump(400)

# ---------- 3) 图钉贴图 ----------
send_hotkey(mods, vk)
pump(700)
check("3 热键唤起遮罩", ctrl.overlay is not None)
drag(P1, P2)
pump(300)
key_event(0x72)          # F3 = 贴图
key_event(0x72, True)
pump(900)
check("3 贴图窗口已出现", ctrl.overlay is None)
send_hotkey(mods, vk)
pump(800)
check("3 贴图之后再按快捷键，仍能唤起", ctrl.overlay is not None)
ctrl.overlay._cancel()
pump(400)

# ---------- 4) 隐藏/显示主界面后还能用 ----------
ctrl.show_main()
pump(300)
ctrl.hide_to_tray()
pump(300)
send_hotkey(mods, vk)
pump(800)
check("4 隐藏到托盘后再按快捷键，仍能唤起", ctrl.overlay is not None)
ctrl.overlay._cancel()
pump(300)

ctrl.quit_app()
pump(200)
print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
