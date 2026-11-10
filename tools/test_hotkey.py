# -*- coding: utf-8 -*-
"""验证全局热键：注册、冲突提示、回滚、WM_HOTKEY 触发。"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import Qt, QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import hotkey as hk  # noqa: E402

print("normalize:", hk.normalize_sequence("alt+ctrl+a"))
print("normalize F1:", hk.normalize_sequence("ctrl+F1"))
print("parse PrintScreen:", hk.parse_sequence("Ctrl+Shift+PrintScreen"))

mgr = hk.HotkeyManager(app)
fired = {"n": 0}
mgr.activated.connect(lambda: fired.__setitem__("n", fired["n"] + 1))

ok, msg = mgr.register("Ctrl+Alt+A")
print("register Ctrl+Alt+A ->", ok, msg, "| current:", mgr.current)

# 模拟另一个程序占用 Ctrl+Alt+B
hk.user32.RegisterHotKey(None, 9191, hk.MOD_CONTROL | hk.MOD_ALT, 0x42)

ok2, msg2 = mgr.register("Ctrl+Alt+B")
print("register Ctrl+Alt+B (被占用) ->", ok2, "| msg:", msg2)
print("失败后当前热键应为旧值:", mgr.current)

hk.user32.UnregisterHotKey(None, 9191)
ok3, msg3 = mgr.register("Ctrl+Alt+B")
print("释放后注册 Ctrl+Alt+B ->", ok3, "| current:", mgr.current)

# 只按一个键应被拒绝
ok4, msg4 = mgr.register("A")
print("register 'A' ->", ok4, "| msg:", msg4)
print("当前仍是:", mgr.current)

# 通过 PostThreadMessage 投递 WM_HOTKEY，验证事件过滤器
tid = ctypes.windll.kernel32.GetCurrentThreadId()
ctypes.windll.user32.PostThreadMessageW(tid, hk.WM_HOTKEY, mgr._HOTKEY_ID, 0)

QTimer.singleShot(400, app.quit)
app.exec_()
print("WM_HOTKEY 触发次数:", fired["n"])

mgr.unregister()
print("unregister 后:", mgr.current)
