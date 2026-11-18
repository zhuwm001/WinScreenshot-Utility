# -*- coding: utf-8 -*-
"""对比不同齿轮图标在小尺寸下的可辨识度。"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

from PyQt5.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

COLOR = QColor("#5B6474")


def draw(kind, s, p):
    c = QPointF(s / 2, s / 2)
    pen = QPen(COLOR, max(1.0, s * 0.10), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if kind == "A":  # 6 齿轮廓（当前）
        r_out, r_root = s * 0.33, s * 0.255
        steps = 24
        path = QPainterPath()
        for i in range(steps + 1):
            ang = 2 * math.pi * i / steps - math.pi / 2
            r = r_out if (i % 4) in (0, 1) else r_root
            pt = QPointF(c.x() + math.cos(ang) * r, c.y() + math.sin(ang) * r)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(c, s * 0.085, s * 0.085)

    elif kind == "B":  # 圆环 + 8 个外凸小齿
        r_ring = s * 0.255
        p.drawEllipse(c, r_ring, r_ring)
        p.drawEllipse(c, s * 0.075, s * 0.075)
        p.setPen(QPen(COLOR, max(1.0, s * 0.13), Qt.SolidLine, Qt.RoundCap))
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(
                QPointF(c.x() + math.cos(a) * r_ring * 0.98, c.y() + math.sin(a) * r_ring * 0.98),
                QPointF(c.x() + math.cos(a) * s * 0.46, c.y() + math.sin(a) * s * 0.46),
            )

    elif kind == "C":  # 圆环 + 8 个圆头短齿
        r_ring = s * 0.24
        p.drawEllipse(c, r_ring, r_ring)
        p.drawEllipse(c, s * 0.07, s * 0.07)
        p.setPen(QPen(COLOR, s * 0.14, Qt.SolidLine, Qt.RoundCap))
        for i in range(8):
            a = math.radians(i * 45 + 22.5)
            p.drawLine(
                QPointF(c.x() + math.cos(a) * r_ring * 0.9, c.y() + math.sin(a) * r_ring * 0.9),
                QPointF(c.x() + math.cos(a) * s * 0.42, c.y() + math.sin(a) * s * 0.42),
            )

    elif kind == "D":  # 实心齿轮 + 镂空中心
        r_out, r_root = s * 0.44, s * 0.33
        steps = 32
        path = QPainterPath()
        for i in range(steps + 1):
            ang = 2 * math.pi * i / steps - math.pi / 2
            r = r_out if (i % 4) in (0, 1) else r_root
            pt = QPointF(c.x() + math.cos(ang) * r, c.y() + math.sin(ang) * r)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(COLOR)
        p.drawPath(path)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(c, s * 0.10, s * 0.10)


def sheet():
    app = QApplication(sys.argv)
    scale = 6
    cell = 32 * scale
    pad = 14
    cols = 4
    img = QPixmap(cols * (cell + pad) + pad, 3 * (cell + pad) + pad + 24)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    labels = ["A", "B", "C", "D"]
    sizes = [15, 16, 18]
    for col, kind in enumerate(labels):
        for row, size in enumerate(sizes):
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            pp = QPainter(pm)
            pp.setRenderHint(QPainter.Antialiasing, True)
            draw(kind, size, pp)
            pp.end()
            x = pad + col * (cell + pad)
            y = pad + row * (cell + pad)
            p.drawPixmap(x, y + 20, pm.scaled(cell, cell, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            p.setPen(QColor("#333"))
            p.drawText(x + 2, y + 14, "%s / %dpx" % (kind, size))
    p.end()
    img.save(os.path.join(ROOT, "build", "gear_variants.png"))
    print("saved", img.width(), img.height())


sheet()
