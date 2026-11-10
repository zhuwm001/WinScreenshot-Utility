# -*- coding: utf-8 -*-
"""图钉图标方案对比：同一尺寸下看哪个更像图钉。"""
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
from PyQt5.QtGui import (  # noqa: E402
    QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
W = QColor(255, 255, 255)


def a(p, s, w):
    """圆帽 + 帽沿 + 收窄钉身 + 针"""
    cap = QRectF(s * .28, s * .12, s * .44, s * .30)
    path = QPainterPath()
    path.arcMoveTo(cap, 180)
    path.arcTo(cap, 180, 180)
    p.drawPath(path)
    p.drawLine(QPointF(s * .24, s * .32), QPointF(s * .76, s * .32))
    p.drawLine(QPointF(s * .24, s * .32), QPointF(s * .24, s * .38))
    p.drawLine(QPointF(s * .76, s * .32), QPointF(s * .76, s * .38))
    p.drawLine(QPointF(s * .24, s * .38), QPointF(s * .76, s * .38))
    p.drawLine(QPointF(s * .42, s * .38), QPointF(s * .46, s * .60))
    p.drawLine(QPointF(s * .58, s * .38), QPointF(s * .54, s * .60))
    p.drawLine(QPointF(s * .46, s * .60), QPointF(s * .54, s * .60))
    p.drawLine(QPointF(s * .50, s * .60), QPointF(s * .50, s * .88))


def b(p, s, w):
    """圆头 + 圆锥身 + 针"""
    p.drawEllipse(QPointF(s * .5, s * .28), s * .17, s * .17)
    p.drawLine(QPointF(s * .36, s * .38), QPointF(s * .46, s * .58))
    p.drawLine(QPointF(s * .64, s * .38), QPointF(s * .54, s * .58))
    p.drawLine(QPointF(s * .46, s * .58), QPointF(s * .54, s * .58))
    p.drawLine(QPointF(s * .50, s * .58), QPointF(s * .50, s * .88))


def c(p, s, w):
    """实心剪影：横帽 + 梯形身 + 针"""
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(W))
    head = QPainterPath()
    head.addRoundedRect(QRectF(s * .28, s * .12, s * .44, s * .14), s * .05, s * .05)
    p.drawPath(head)
    body = QPolygonF([QPointF(s * .40, s * .26), QPointF(s * .60, s * .26),
                      QPointF(s * .555, s * .56), QPointF(s * .445, s * .56)])
    p.drawPolygon(body)
    needle = QPolygonF([QPointF(s * .47, s * .56), QPointF(s * .53, s * .56),
                        QPointF(s * .50, s * .90)])
    p.drawPolygon(needle)


def d(p, s, w):
    """斜向图钉（📌 风格）"""
    head = QRectF(s * .18, s * .12, s * .42, s * .42)
    path = QPainterPath()
    path.moveTo(s * .40, s * .46)
    path.lineTo(s * .64, s * .22)
    p.drawPath(path)
    p.drawEllipse(QPointF(s * .44, s * .20), s * .17, s * .17)
    # 针
    p.drawLine(QPointF(s * .32, s * .38), QPointF(s * .80, s * .86))
    p.setBrush(QColor(W))
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(s * .80, s * .86), QPointF(s * .62, s * .80),
                             QPointF(s * .74, s * .68)]))


def e(p, s, w):
    """图钉（俯视斜针）：大帽 + 短针 + 帽心"""
    cap = QRectF(s * .24, s * .10, s * .52, s * .34)
    p.drawRoundedRect(cap, s * .12, s * .12)
    p.drawLine(QPointF(s * .40, s * .44), QPointF(s * .46, s * .62))
    p.drawLine(QPointF(s * .60, s * .44), QPointF(s * .54, s * .62))
    p.drawLine(QPointF(s * .46, s * .62), QPointF(s * .54, s * .62))
    p.drawLine(QPointF(s * .50, s * .62), QPointF(s * .50, s * .88))


variants = [("A", a), ("B", b), ("C", c), ("D", d), ("E", e)]
big, cell = 100, 190
sheet = QPixmap(cell * len(variants), big + 110)
sheet.fill(QColor("#18181C"))
p = QPainter(sheet)
p.setRenderHint(QPainter.Antialiasing, True)
f = p.font()
f.setPixelSize(14)
for i, (name, fn) in enumerate(variants):
    x = i * cell + 20
    # 大图
    p.save()
    p.translate(x, 10)
    p.setPen(QPen(W, 2.2 * big / 21, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    fn(p, big, 2.2 * big / 21)
    p.restore()
    # 实际尺寸 21px
    for j, size in enumerate((21, 32)):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing, True)
        sc = size / 100.0
        q.scale(sc, sc)
        q.setPen(QPen(W, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        q.setBrush(Qt.NoBrush)
        fn(q, 100, 2.2)
        q.end()
        p.drawPixmap(x + 20 + j * 50, big + 30, size, size, pm)
    p.setPen(QColor("#9AA3B2"))
    p.setFont(f)
    p.drawText(x, big + 90, "variant " + name)

p.end()
sheet.save(os.path.join(ROOT, "build", "pin_variants.png"))
print("ok")
