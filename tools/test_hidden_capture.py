# -*- coding: utf-8 -*-
"""复现/验证：主界面显示、隐藏到托盘、最小化 三种状态下，热键都要能唤起截图。

用真实 SendInput 发快捷键，用真实 AppController，跟安装版行为一致。
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
from PyQt5.QtNetwork import QLocalServer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

import hotkey as hk  # noqa: E402
import main as appmain  # noqa: E402
from app_config import config  # noqa: E402

user32 = ctypes.windll.user32

# ---------------------------------------------------------------- SendInput
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


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


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
    time.sleep(0.03)
    key_event(vk)
    key_event(vk, True)
    time.sleep(0.03)
    for v in reversed(mod_vks):
        key_event(v, True)


def pump(ms=200):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.008)


ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


def close_overlay(ctrl):
    if ctrl.overlay is not None:
        ctrl.overlay._cancel()
    pump(200)


# ---------------------------------------------------------------- 启动
server = QLocalServer()
QLocalServer.removeServer("WoAiJieTu.Test.Hidden")
server.listen("WoAiJieTu.Test.Hidden")

ctrl = appmain.AppController(app, server)
seq = config.get("hotkey")
mods, vk = hk.parse_sequence(seq)
print("快捷键:", seq, "mods=%s vk=%s" % (mods, vk), "| 钩子:", ctrl.hotkey.using_hook)

ctrl.start(silent=False)
pump(500)

# ---------- A) 主界面显示 ----------
check("A1 主界面显示", ctrl.win.isVisible())
send_hotkey(mods, vk)
pump(600)
check("A2 主界面显示时热键唤起遮罩", ctrl.overlay is not None)
close_overlay(ctrl)

# ---------- B) 隐藏到托盘 ----------
ctrl.hide_to_tray()
pump(400)
check("B1 主界面已隐藏", not ctrl.win.isVisible())
send_hotkey(mods, vk)
pump(600)
check("B2 隐藏到托盘后热键唤起遮罩", ctrl.overlay is not None)
close_overlay(ctrl)

# ---------- C) 最小化 ----------
ctrl.show_main()
pump(300)
ctrl.win.showMinimized()
pump(400)
print("最小化后 isVisible=%s isMinimized=%s" %
      (ctrl.win.isVisible(), ctrl.win.isMinimized()))
send_hotkey(mods, vk)
pump(600)
check("C1 最小化后热键唤起遮罩", ctrl.overlay is not None)
close_overlay(ctrl)
pump(300)

# ---------- D) 连续两次（上次刚结束再按） ----------
ctrl.show_main()
pump(300)
send_hotkey(mods, vk)
pump(600)
first = ctrl.overlay is not None
close_overlay(ctrl)
send_hotkey(mods, vk)
pump(600)
check("D1 连续两次都能唤起", first and ctrl.overlay is not None)
close_overlay(ctrl)

# ---------- E) 钩子失效后靠 RegisterHotKey 兜底 ----------
print("兜底热键已注册:", ctrl.hotkey._backup_ok)
check("钩子可用时同时注册了系统热键兜底", ctrl.hotkey._backup_ok)
ctrl.hotkey._hook.close()              # 模拟系统把低级钩子摘掉
time.sleep(0.2)
send_hotkey(mods, vk)
pump(800)
check("钩子失效后仍能唤起遮罩（兜底路径）", ctrl.overlay is not None)
close_overlay(ctrl)

ctrl.quit_app()
pump(200)
print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
