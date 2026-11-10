# -*- coding: utf-8 -*-
"""图钉/钉子图标方案对比 第二轮。"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
W = QColor(255, 255, 255)


def f(p, s, w):
    """圆顶帽 + 大幅收窄 + 针（正视图钉）"""
    cap = QRectF(s * .26, s * .13, s * .48, s * .32)
    path = QPainterPath()
    path.arcMoveTo(cap, 180)
    path.arcTo(cap, 180, 180)
    p.drawPath(path)
    p.drawLine(QPointF(s * .26, s * .29), QPointF(s * .42, s * .54))
    p.drawLine(QPointF(s * .74, s * .29), QPointF(s * .58, s * .54))
    p.drawLine(QPointF(s * .42, s * .54), QPointF(s * .58, s * .54))
    p.drawLine(QPointF(s * .50, s * .54), QPointF(s * .50, s * .86))


def g(p, s, w):
    """扁头 + 锥形钉身 + 尖（钉子正视图）"""
    head = QPainterPath()
    head.addRoundedRect(QRectF(s * .28, s * .13, s * .44, s * .10), s * .05, s * .05)
    p.drawPath(head)
    p.drawLine(QPointF(s * .40, s * .23), QPointF(s * .465, s * .70))
    p.drawLine(QPointF(s * .60, s * .23), QPointF(s * .535, s * .70))
    p.drawLine(QPointF(s * .465, s * .70), QPointF(s * .50, s * .89))
    p.drawLine(QPointF(s * .535, s * .70), QPointF(s * .50, s * .89))


def h(p, s, w):
    """实心剪影：圆顶帽 + 收窄 + 针"""
    path = QPainterPath()
    cap = QRectF(s * .24, s * .14, s * .52, s * .34)
    path.moveTo(s * .24, s * .31)
    path.arcTo(cap, 180, 180)
    path.lineTo(s * .60, s * .52)
    path.lineTo(s * .54, s * .52)
    path.lineTo(s * .50, s * .86)
    path.lineTo(s * .46, s * .52)
    path.lineTo(s * .40, s * .52)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(W))
    p.drawPath(path)


def i(p, s, w):
    """斜放的图钉（30°）"""
    ang = math.radians(-45)
    ca, sa = math.cos(ang), math.sin(ang)
    cx, cy = s * .46, s * .24

    def rot(x, y):
        dx, dy = x - cx, y - cy
        return QPointF(cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)

    cap = QRectF(s * .26, s * .06, s * .40, s * .36)
    path = QPainterPath()
    path.arcMoveTo(cap, 180)
    path.arcTo(cap, 180, 180)
    p.save()
    p.translate(cx, cy)
    p.rotate(-45)
    p.translate(-cx, -cy)
    p.drawPath(path)
    p.drawLine(QPointF(s * .26, s * .24), QPointF(s * .42, s * .48))
    p.drawLine(QPointF(s * .66, s * .24), QPointF(s * .54, s * .48))
    p.drawLine(QPointF(s * .42, s * .48), QPointF(s * .54, s * .48))
    p.drawLine(QPointF(s * .48, s * .48), QPointF(s * .48, s * .84))
    p.restore()


variants = [("F", f), ("G", g), ("H", h), ("I", i)]
big, cell = 100, 200
sheet = QPixmap(cell * len(variants), big + 110)
sheet.fill(QColor("#18181C"))
p = QPainter(sheet)
p.setRenderHint(QPainter.Antialiasing, True)
fnt = p.font()
fnt.setPixelSize(14)
for i, (name, fn) in enumerate(variants):
    x = i * cell + 20
    p.save()
    p.translate(x, 10)
    p.setPen(QPen(W, 2.2 * big / 21, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    fn(p, big, 2.2 * big / 21)
    p.restore()
    for j, size in enumerate((21, 32)):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing, True)
        q.scale(size / 100.0, size / 100.0)
        q.setPen(QPen(W, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        q.setBrush(Qt.NoBrush)
        fn(q, 100, 2.2)
        q.end()
        p.drawPixmap(x + 20 + j * 50, big + 30, size, size, pm)
    p.setPen(QColor("#9AA3B2"))
    p.setFont(fnt)
    p.drawText(x, big + 90, "variant " + name)

p.end()
sheet.save(os.path.join(ROOT, "build", "pin_variants2.png"))
print("ok")
