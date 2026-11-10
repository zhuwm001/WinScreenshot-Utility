# -*- coding: utf-8 -*-
"""图钉图标方案对比 第三轮：实心剪影。"""
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
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
W = QColor(255, 255, 255)


def j(p, s, w):
    """实心：圆顶帽 + 收窄钉身 + 针（正视）"""
    cap = QRectF(s * .22, s * .12, s * .56, s * .36)
    path = QPainterPath()
    path.moveTo(s * .38, s * .50)
    path.lineTo(s * .22, s * .30)
    path.arcTo(cap, 180, -180)
    path.lineTo(s * .62, s * .50)
    path.lineTo(s * .535, s * .50)
    path.lineTo(s * .50, s * .88)
    path.lineTo(s * .465, s * .50)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(W)
    p.drawPath(path)


def k(p, s, w):
    """实心：圆帽 + 收窄 + 短针（更像按钉）"""
    cap = QRectF(s * .20, s * .14, s * .60, s * .40)
    path = QPainterPath()
    path.moveTo(s * .36, s * .54)
    path.lineTo(s * .20, s * .34)
    path.arcTo(cap, 180, -180)
    path.lineTo(s * .64, s * .54)
    path.lineTo(s * .545, s * .54)
    path.lineTo(s * .50, s * .90)
    path.lineTo(s * .455, s * .54)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(W)
    p.drawPath(path)
    # 帽上高光缺口，增加层次
    p.setBrush(QColor("#18181C"))
    p.drawEllipse(QPointF(s * .50, s * .30), s * .055, s * .055)


def l(p, s, w):
    """线条：扁帽 + 细长钉身 + 尖（钉子）"""
    head = QPainterPath()
    head.addRoundedRect(QRectF(s * .26, s * .12, s * .48, s * .12), s * .06, s * .06)
    p.drawPath(head)
    p.drawLine(QPointF(s * .50, s * .24), QPointF(s * .50, s * .70))
    p.drawLine(QPointF(s * .50, s * .70), QPointF(s * .44, s * .88))
    p.drawLine(QPointF(s * .50, s * .70), QPointF(s * .56, s * .88))


def m(p, s, w):
    """实心：斜 30° 的图钉"""
    p.save()
    p.translate(s * .48, s * .46)
    p.rotate(28)
    p.translate(-s * .48, -s * .46)
    cap = QRectF(s * .24, s * .08, s * .48, s * .34)
    path = QPainterPath()
    path.moveTo(s * .38, s * .44)
    path.lineTo(s * .24, s * .25)
    path.arcTo(cap, 180, -180)
    path.lineTo(s * .58, s * .44)
    path.lineTo(s * .525, s * .44)
    path.lineTo(s * .50, s * .72)
    path.lineTo(s * .475, s * .44)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(W)
    p.drawPath(path)
    p.restore()


variants = [("J", j), ("K", k), ("L", l), ("M", m)]
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
    for jj, size in enumerate((21, 28)):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing, True)
        q.scale(size / 100.0, size / 100.0)
        q.setPen(QPen(W, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        q.setBrush(Qt.NoBrush)
        fn(q, 100, 2.2)
        q.end()
        p.drawPixmap(x + 20 + jj * 46, big + 30, size, size, pm)
    p.setPen(QColor("#9AA3B2"))
    p.setFont(fnt)
    p.drawText(x, big + 90, "variant " + name)

p.end()
sheet.save(os.path.join(ROOT, "build", "pin_variants3.png"))
print("ok")

