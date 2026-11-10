# -*- coding: utf-8 -*-
"""真实环境抓屏测试：全屏遮罩 1.8 秒后自动框选并导出。"""
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

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt, QTimer  # noqa: E402
from PyQt5.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

import overlay as ov  # noqa: E402


def send_mouse(widget, etype, pos):
    if etype == QEvent.MouseMove:
        button, buttons = Qt.NoButton, Qt.LeftButton
    elif etype == QEvent.MouseButtonPress:
        button, buttons = Qt.LeftButton, Qt.LeftButton
    else:
        button, buttons = Qt.LeftButton, Qt.NoButton
    e = QMouseEvent(etype, QPointF(pos), QPointF(widget.mapToGlobal(pos)),
                    button, buttons, Qt.NoModifier)
    QApplication.sendEvent(widget, e)


def drag(w, a, b):
    send_mouse(w, QEvent.MouseButtonPress, a)
    send_mouse(w, QEvent.MouseMove, b)
    send_mouse(w, QEvent.MouseButtonRelease, b)


o = ov.CaptureOverlay("#FF3B30")
print("virtual geometry:", o._vgeo, "| dpr:", o._dpr, "| shot:", o._shot.size())
o.show_overlay()

sel_w = min(700, o.width() - 200)
sel_h = min(420, o.height() - 200)
A = QPoint(100, 120)
B = QPoint(100 + sel_w, 120 + sel_h)


def step1():
    drag(o, A, B)


def step2():
    o._switch_tool(ov.T_RECT)
    drag(o, QPoint(180, 200), QPoint(400, 320))
    o._color = QColor("#4A86FF")
    o._bar.set_color(o._color)
    o._switch_tool(ov.T_ELLIPSE)
    drag(o, QPoint(450, 200), QPoint(730, 320))


def step3():
    img = o._export()
    img.save(os.path.join(ROOT, "build", "live_capture.png"))
    o.grab().save(os.path.join(ROOT, "build", "live_overlay.png"))
    print("export:", img.width(), "x", img.height(), "dpr:", img.devicePixelRatio())
    o.close()
    app.quit()


QTimer.singleShot(600, step1)
QTimer.singleShot(1000, step2)
QTimer.singleShot(1600, step3)
app.exec_()
print("ok")
