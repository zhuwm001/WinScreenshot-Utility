# -*- coding: utf-8 -*-
"""诊断：框选松手后，浮动工具栏到底有没有显示、在什么位置、尺寸多大。

模拟多种环境：
  - 正常单屏
  - 1400x900 逻辑屏（模拟 1080p@125% / 4K@200% 的逻辑尺寸）
  - 极小选区（贴近屏幕边缘）
  - 选区右下角紧贴屏幕边界
每种情况都输出 state / bar.isVisible / bar.geometry / bar.sizeHint，并把
遮罩抓图存到 build/ 下，便于肉眼核对。
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

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFont, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import overlay as ov  # noqa: E402

OUT = os.path.join(ROOT, "build")


def make_shot(w, h):
    pm = QPixmap(w, h)
    pm.setDevicePixelRatio(1.0)
    pm.fill(QColor("#EEF2F8"))
    p = QPainter(pm)
    p.fillRect(0, 0, w, 64, QColor("#2B3240"))
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(22)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(24, 42, "模拟窗口 %d x %d" % (w, h))
    p.end()
    return pm


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


def drag(widget, start, end):
    send_mouse(widget, QEvent.MouseButtonPress, start)
    send_mouse(widget, QEvent.MouseMove, end)
    send_mouse(widget, QEvent.MouseButtonRelease, end)


def check(desc, w, h, start, end, tag):
    o = ov.CaptureOverlay("#FF3B30")
    o._shot = make_shot(w, h)
    o._vgeo = QRect(0, 0, w, h)
    o._dpr = 1.0
    o.setGeometry(QRect(0, 0, w, h))
    o.show()
    for _ in range(3):
        app.processEvents()

    drag(o, QPoint(*start), QPoint(*end))
    for _ in range(3):
        app.processEvents()
    from PyQt5.QtTest import QTest
    QTest.qWait(220)          # 等工具条自检跑完，确认没有被误判挪位
    app.processEvents()

    bar = o._bar
    print("[%s] overlay=%dx%d sel=%s state=%s" % (desc, w, h, o._sel, o._state))
    print("      bar visible=%s geom=%s hint=%s parent=%s" % (
        bar.isVisible(), bar.geometry(), bar.sizeHint(),
        type(bar.parent()).__name__))
    inside = QRect(0, 0, w, h).intersected(bar.geometry()) == bar.geometry()
    print("      bar fully inside overlay=%s  bar_visible_part=%s"
          % (inside, bar.visibleRegion().boundingRect()))
    o.grab().save(os.path.join(OUT, "diag_sel_%s.png" % tag))
    o.close()
    for _ in range(2):
        app.processEvents()
    return bar.width(), bar.height()


print("screen:", app.primaryScreen().geometry(), "dpr:",
      app.primaryScreen().devicePixelRatio())

check("1080p 逻辑屏", 1920, 1040, (300, 200), (838, 630), "1920")
check("小逻辑屏 1366", 1366, 728, (200, 150), (738, 580), "1366")
check("窄屏 1280", 1280, 720, (100, 100), (638, 530), "1280")
check("贴右下角", 1920, 1040, (1300, 700), (1900, 1035), "corner")
check("超小选区", 1920, 1040, (500, 400), (505, 403), "tiny")
print("done")
