# -*- coding: utf-8 -*-
"""验证全局热键钩子：能触发、能吞键、可临时停用、长按不重复触发。

关键点：钩子必须在前台程序之前拿到按键并"吞掉"，否则前台程序收到
Ctrl+Alt+A 会把自己打开的下拉框/菜单关掉 —— 这正是之前丢内容的另一半原因。
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

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import hotkey as hk  # noqa: E402

user32 = ctypes.windll.user32

# ---------------------------------------------------------------- SendInput
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", wintypes.WPARAM)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

VK_CONTROL, VK_MENU = 0x11, 0x12
VK_A, VK_B = 0x41, 0x42


def key_event(vk, up=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def press(mods, vk, repeats=1):
    """发一次组合键。repeats>1 时模拟长按：连续 KEYDOWN、没有中间的 KEYUP。"""
    for v in mods:
        key_event(v)
    for _ in range(repeats):
        key_event(vk)
        if repeats == 1:
            key_event(vk, True)
    if repeats > 1:
        time.sleep(0.02)
        key_event(vk, True)
    for v in reversed(mods):
        key_event(v, True)


def pump(ms=220):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.008)


ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


class Receiver(QWidget):
    """模拟"前台程序"：记录自己收到了哪些按键。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("前台窗口")
        self.setGeometry(200, 160, 480, 300)
        self.setStyleSheet("background: #FFFFFF;")
        self.received = []

    def keyPressEvent(self, event):
        self.received.append(int(event.key()))
        super().keyPressEvent(event)


mgr = hk.HotkeyManager(app)
fired = {"n": 0}
mgr.activated.connect(lambda: fired.__setitem__("n", fired["n"] + 1))
print("钩子可用:", mgr.using_hook)

check("使用低级键盘钩子", mgr.using_hook)

ok, msg = mgr.register("Ctrl+Alt+A")
check("注册 Ctrl+Alt+A", ok, msg)

recv = Receiver()
recv.show()
recv.raise_()
recv.activateWindow()
pump(300)
user32.SetForegroundWindow(int(recv.winId()))
pump(200)

# ---------- 1) 正常触发，并且按键被吞掉 ----------
before = len(recv.received)
press([VK_CONTROL, VK_MENU], VK_A)
pump(320)
got = recv.received[before:]
print("前台窗口收到:", got, "| 触发次数:", fired["n"])
check("钩子触发一次", fired["n"] == 1, fired["n"])
# 修饰键（Ctrl/Alt）本身不吞，主键 A 必须被吞掉
check("主键被吞掉，前台程序收不到 A", Qt.Key_A not in got, got)
check("修饰键不受影响（只吞主键）",
      Qt.Key_Control in got or Qt.Key_Alt in got, got)

# ---------- 2) 长按自动重复只触发一次 ----------
before = len(recv.received)
press([VK_CONTROL, VK_MENU], VK_A, repeats=5)
pump(350)
got = recv.received[before:]
check("长按重复不重复触发", fired["n"] == 2, fired["n"])
check("长按期间主键一直被吞", Qt.Key_A not in got, got)

# ---------- 3) 别的组合键不受影响 ----------
before = len(recv.received)
press([VK_CONTROL], VK_B)
pump(260)
got = recv.received[before:]
check("非热键组合照常传给前台程序", Qt.Key_B in got, got)
check("非热键组合不触发截图", fired["n"] == 2, fired["n"])

# ---------- 4) 修饰键不匹配时也不触发 ----------
before = len(recv.received)
press([VK_CONTROL], VK_A)
pump(260)
got = recv.received[before:]
check("只按 Ctrl+A 不触发", fired["n"] == 2, fired["n"])
check("只按 Ctrl+A 时 A 照常传给前台", Qt.Key_A in got, got)

# ---------- 5) 停用后既不触发也不吞键（录快捷键时用） ----------
mgr.set_enabled(False)
before = len(recv.received)
press([VK_CONTROL, VK_MENU], VK_A)
pump(300)
got = recv.received[before:]
check("停用后不触发", fired["n"] == 2, fired["n"])
check("停用后不吞键", Qt.Key_A in got, got)
mgr.set_enabled(True)

# ---------- 6) 换成 Ctrl+Alt+B 后旧键失效 ----------
ok, msg = mgr.register("Ctrl+Alt+B")
check("改绑 Ctrl+Alt+B", ok, msg)
n = fired["n"]
press([VK_CONTROL, VK_MENU], VK_A)
pump(260)
check("旧组合不再触发", fired["n"] == n, fired["n"])
press([VK_CONTROL, VK_MENU], VK_B)
pump(300)
check("新组合能触发", fired["n"] == n + 1, fired["n"])

# ---------- 7) 被占用组合仍然报冲突 ----------
user32.RegisterHotKey(None, 9311, hk.MOD_CONTROL | hk.MOD_ALT, 0x43)   # Ctrl+Alt+C
ok2, msg2 = mgr.register("Ctrl+Alt+C")
print("注册被占用的 Ctrl+Alt+C ->", ok2, msg2)
check("被占用时报冲突", not ok2 and "占用" in (msg2 or ""), msg2)
user32.UnregisterHotKey(None, 9311)
check("冲突后保留原热键", mgr.current == "Ctrl+Alt+B", mgr.current)

# ---------- 8) 钩子自检重装后仍然可用 ----------
n = fired["n"]
mgr._refresh_hook()
pump(150)
press([VK_CONTROL, VK_MENU], VK_B)
pump(300)
check("钩子重装后依然能触发", fired["n"] == n + 1, fired["n"])

mgr.close()
recv.close()
pump(100)
print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
