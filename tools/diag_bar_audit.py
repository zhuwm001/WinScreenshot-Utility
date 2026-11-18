# -*- coding: utf-8 -*-
"""诊断：框选结束后 150ms 的工具条自检到底有没有跑、亮度是多少。

用来回答一个具体问题 —— 用户日志里「框选完成」后面直接就是「复制前剪贴板」，
中间没有自检行，是自检没跑，还是跑了但条件不满足？
顺便对比「拖拽后盲按 Ctrl+C」的日志形态。
"""
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

from PyQt5.QtCore import QEvent, QEventLoop, QPoint, QPointF, QRect, Qt, QTimer  # noqa: E402
from PyQt5.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import overlay as ov  # noqa: E402
import update_log  # noqa: E402

W, H = 1280, 720


def shot(w, h):
    pm = QPixmap(w, h)
    pm.setDevicePixelRatio(1.0)
    pm.fill(QColor("#E9EEF6"))
    p = QPainter(pm)
    p.fillRect(0, 0, w, 56, QColor("#2B3240"))
    p.end()
    return pm


def send_mouse(o, etype, pos):
    if etype == QEvent.MouseMove:
        button, buttons = Qt.NoButton, Qt.LeftButton
    elif etype == QEvent.MouseButtonPress:
        button, buttons = Qt.LeftButton, Qt.LeftButton
    else:
        button, buttons = Qt.LeftButton, Qt.NoButton
    e = QMouseEvent(etype, QPointF(pos), QPointF(o.mapToGlobal(pos)),
                    button, buttons, Qt.NoModifier)
    QApplication.sendEvent(o, e)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def new_overlay():
    o = ov.CaptureOverlay("#FF3B30")
    o._shot = shot(W, H)
    o._vgeo = QRect(0, 0, W, H)
    o._dpr = 1.0
    o.setGeometry(QRect(0, 0, W, H))
    o.show()
    wait(60)
    return o


def tail(n=12):
    return [ln.rstrip() for ln in update_log.read(n)]


print("A) 正常拖拽，等 300ms 看自检")
o = new_overlay()
before = len(update_log.read(240))
send_mouse(o, QEvent.MouseButtonPress, QPoint(200, 160))
send_mouse(o, QEvent.MouseMove, QPoint(720, 560))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(720, 560))
wait(320)
print("  遮罩还活着=%s 工具条可见=%s 亮度=%s"
      % (o.isVisible(), o._bar.isVisible(),
         ("%.1f" % o._probe_bar_luminance()) if o._probe_bar_luminance() is not None else "取不到"))
print("  --- 新增日志 ---")
for ln in update_log.read(240)[before:]:
    print("  " + ln.rstrip())
o.close()
wait(60)

print()
print("B) 拖拽后立刻按 Ctrl+C（模拟盲按快捷键）")
o = new_overlay()
before = len(update_log.read(240))
send_mouse(o, QEvent.MouseButtonPress, QPoint(200, 160))
send_mouse(o, QEvent.MouseMove, QPoint(700, 540))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(700, 540))
ke = QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.ControlModifier)
QApplication.sendEvent(o, ke)
wait(320)
print("  --- 新增日志 ---")
for ln in update_log.read(240)[before:]:
    print("  " + ln.rstrip())

print()
print("C) 拖拽后点工具条按钮（正常路径）")
o = new_overlay()
before = len(update_log.read(240))
send_mouse(o, QEvent.MouseButtonPress, QPoint(200, 160))
send_mouse(o, QEvent.MouseMove, QPoint(700, 540))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(700, 540))
wait(200)
o._bar.btn_copy.click()
wait(120)
print("  --- 新增日志 ---")
for ln in update_log.read(240)[before:]:
    print("  " + ln.rstrip())
