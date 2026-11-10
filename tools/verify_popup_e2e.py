# -*- coding: utf-8 -*-
"""端到端：真实安装版 + 一个"失去焦点就消失"的弹出面板。

流程：弹出面板 -> 按真实快捷键 -> 等到遮罩出现 -> 框选面板区域 -> Enter 复制
      -> 读剪贴板，检查截到的图里有没有面板的颜色。

用真实快捷键（读 config.json），所以不依赖某个固定的组合。
"""
import ctypes
import json
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

from PyQt5.QtCore import QEvent, QPoint, QRect, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

import hotkey as hk  # noqa: E402

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EXE = os.path.expandvars(r"%LOCALAPPDATA%\Programs\我爱截图\我爱截图.exe")
CFG = os.path.expandvars(r"%APPDATA%\我爱截图\config.json")
COLOR = (200, 30, 200)
POPUP = QRect(560, 360, 280, 190)
SEL = QRect(POPUP.adjusted(-40, -40, 40, 40))

ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


def pump(ms=150):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.008)


# ---------------------------------------------------------------- SendInput
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


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

MOD_VK = {hk.MOD_CONTROL: 0x11, hk.MOD_ALT: 0x12, hk.MOD_SHIFT: 0x10, hk.MOD_WIN: 0x5B}


def _send(inp):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def key_event(vk, up=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    _send(inp)


def mouse_event(flags, x=0, y=0):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(x, y, 0, flags, 0, 0)
    _send(inp)


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
    key_event(vk)
    key_event(vk, True)
    time.sleep(0.03)
    for v in reversed(mod_vks):
        key_event(v, True)


# ---------------------------------------------------------------- 弹出面板
class FakeDropdown(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setGeometry(POPUP)
        self.closed_by_focus = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*COLOR))
        p.drawRoundedRect(self.rect(), 8, 8)

    def event(self, e):
        if e.type() in (QEvent.WindowDeactivate, QEvent.FocusOut):
            self.closed_by_focus = True
            self.hide()
        return super().event(e)


# ---------------------------------------------------------------- 窗口查找
def app_pid():
    out = user32.FindWindowW(None, None)
    # 用进程名找 pid
    import subprocess
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq 我爱截图.exe", "/FO", "CSV", "/NH"],
                       capture_output=True)
    txt = r.stdout.decode("mbcs", "ignore").strip()
    for line in txt.splitlines():
        parts = line.split('","')
        if len(parts) > 1:
            try:
                return int(parts[1])
            except ValueError:
                continue
    return None


def find_overlay_window(pid):
    """找出该进程的全屏可见窗口（遮罩层）。"""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if w >= user32.GetSystemMetrics(0) and h >= user32.GetSystemMetrics(1):
            found.append((hwnd, w, h))
        return True

    user32.EnumWindows(cb, 0)
    return found


# ---------------------------------------------------------------- 开始
def main():
    cfg = json.load(open(CFG, encoding="utf-8"))
    seq = cfg.get("hotkey", "")
    mods, vk = hk.parse_sequence(seq)
    print("配置里的快捷键:", seq, "-> mods=%s vk=%s" % (mods, vk))
    check("能解析配置里的快捷键", vk is not None, seq)

    # 清空剪贴板，便于判断是不是这次截图写进去的
    app.clipboard().clear()
    pump(120)

    popup = FakeDropdown()
    popup.show()
    popup.raise_()
    popup.activateWindow()
    pump(350)
    check("弹出面板已显示", popup.isVisible())

    send_hotkey(mods, vk)
    pump(900)
    print("浮层是否因失焦关闭:", popup.closed_by_focus)

    pid = app_pid()
    wins = find_overlay_window(pid) if pid else []
    print("进程 pid:", pid, "| 全屏窗口:", wins)
    check("按快捷键后截图遮罩被唤起", bool(wins), wins)
    if not wins:
        return

    # 框选包含面板的一块区域（遮罩此时是全屏置顶的）
    p1 = SEL.topLeft() + QPoint(40, 30)
    p2 = SEL.bottomRight()
    mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, *screen_to_abs(p1.x(), p1.y()))
    pump(80)
    mouse_event(MOUSEEVENTF_LEFTDOWN)
    for i in range(1, 9):
        pt = QPoint(p1.x() + (p2.x() - p1.x()) * i // 8,
                    p1.y() + (p2.y() - p1.y()) * i // 8)
        mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                    *screen_to_abs(pt.x(), pt.y()))
        pump(40)
    mouse_event(MOUSEEVENTF_LEFTUP)
    pump(250)

    # Enter = 复制到剪贴板
    key_event(0x0D)
    key_event(0x0D, True)
    pump(700)

    img = app.clipboard().image()
    print("剪贴板图片:", img.width(), "x", img.height())
    check("截图结果进了剪贴板", not img.isNull() and img.width() > 100,
          "%dx%d" % (img.width(), img.height()))

    if not img.isNull():
        oy = SEL.top() + 30
        px = int((POPUP.center().x() - SEL.left()) * img.width() / max(1, SEL.width()))
        py = int((POPUP.center().y() - oy) * img.height() / max(1, (SEL.bottom() - oy)))
        px = max(0, min(px, img.width() - 1))
        py = max(0, min(py, img.height() - 1))
        c = img.pixelColor(px, py).getRgb()[:3]
        print("截图里面板位置的颜色:", c, "期望接近", COLOR)
        check("截图里保住了弹出面板的内容", 
              all(abs(a - b) <= 40 for a, b in zip(c, COLOR)), c)

        img.save(os.path.join(ROOT, "build", "popup_e2e.png"))

    pump(200)
    popup.close()


main()
print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
