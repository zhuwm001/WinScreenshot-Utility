# -*- coding: utf-8 -*-
"""直接验证关闭按钮的行为链。"""
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

from PyQt5.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

from main_window import MainWindow  # noqa: E402

win = MainWindow("Ctrl+Alt+A")
events = []
win.close_requested.connect(lambda: events.append("close_requested"))
win.hide_requested.connect(lambda: events.append("hide_requested"))

win.move(-3000, -3000)
win.show()
for _ in range(5):
    app.processEvents()

c = win.btn_close.mapToGlobal(win.btn_close.rect().center())
print("X 按钮全局坐标:", c.x(), c.y(), "| 窗口:", win.geometry())

win.btn_close.click()
for _ in range(5):
    app.processEvents()
print("click() 后事件:", events, "| 可见:", win.isVisible())


def step2():
    win.show()
    for _ in range(3):
        app.processEvents()
    print("---- 直接调用 close() ----")
    win.close()
    for _ in range(5):
        app.processEvents()
    print("close() 后事件:", events, "| 可见:", win.isVisible())


QTimer.singleShot(200, step2)
QTimer.singleShot(900, app.quit)
app.exec_()
