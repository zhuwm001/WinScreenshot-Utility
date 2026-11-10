# -*- coding: utf-8 -*-
"""精确验证：用 Qt 报告的按钮坐标去真实点击。"""
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

from main_window import MainWindow  # noqa: E402

user32 = ctypes.WinDLL("user32")
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

win = MainWindow("Ctrl+Alt+A")
win.move(300, 200)
win.show()
for _ in range(8):
    app.processEvents()

print("窗口 geometry:", win.geometry())
print("container geometry:", win._container.geometry())
print("X 按钮 rect(容器内):", win.btn_close.geometry())
c = win.btn_close.mapToGlobal(win.btn_close.rect().center())
print("X 按钮全局中心:", c.x(), c.y())
print("min 按钮全局中心:", win.btn_min.mapToGlobal(win.btn_min.rect().center()))


def do_click():
    user32.SetCursorPos(c.x(), c.y())
    app.processEvents()
    import time
    time.sleep(0.3)
    print("光标位置:", end=" ")
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    print(pt.x, pt.y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("已点击")


win.close_requested.connect(lambda: print(">>> close_requested 触发"))


def check():
    print("点击后可见:", win.isVisible())


QTimer.singleShot(400, do_click)
QTimer.singleShot(1200, check)
QTimer.singleShot(1600, app.quit)
app.exec_()
