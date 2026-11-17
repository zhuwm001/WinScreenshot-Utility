# -*- coding: utf-8 -*-
"""用 QPainter 现场绘制矢量图标，避免依赖外部图片资源。"""
import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QColor, QFont, QFontMetricsF, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF,
)
from PyQt5.QtWidgets import QApplication

WHITE = QColor(255, 255, 255)
# 「发现新版本」徽标用的绿色，比调色板里的绿略深一点，浅底上更清楚
UPDATE_GREEN = QColor("#22C55E")


def _dpr() -> float:
    app = QApplication.instance()
    if app and app.primaryScreen():
        return float(app.primaryScreen().devicePixelRatio()) or 1.0
    return 1.0


def render(kind: str, size: int = 32, color=WHITE, pen_width: float = 2.2) -> QPixmap:
    """把图标画到 QPixmap 上，自动适配高 DPI。"""
    dpr = _dpr()
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    try:
        _draw(p, kind, float(size), QColor(color), pen_width)
    finally:
        p.end()
    return pm


def render_icon(kind: str, size: int = 32, color=WHITE, pen_width: float = 2.2) -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(render(kind, s, color, pen_width))
    return icon


def _draw(p: QPainter, kind: str, s: float, color: QColor, w: float):
    pad = s * 0.20
    inner = s - pad * 2

    pen = QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if kind == "rect":
        p.drawRect(QRectF(pad, pad, inner, inner))

    elif kind == "ellipse":
        p.drawEllipse(QRectF(pad, pad, inner, inner))

    elif kind == "arrow":
        start = QPointF(pad, s - pad)
        end = QPointF(s - pad, pad)
        p.drawLine(start, end)
        _arrow_head(p, start, end, max(9.0, s * 0.26), color)

    elif kind == "pen":
        # 铅笔：斜 45°，笔杆描边 + 笔尖实心楔形，21px 下也能认出是铅笔头
        ux, uy = 0.7071, -0.7071
        vx, vy = 0.7071, 0.7071
        ox, oy = 0.16, 0.84        # 笔尖在左下
        hw = 0.13                  # 笔杆半宽（相对画布边长）

        def pt(t, off):
            return QPointF((ox + ux * t + vx * off) * s,
                           (oy + uy * t + vy * off) * s)

        tip = pt(0.0, 0.0)
        b1, b2 = pt(0.26, hw), pt(0.26, -hw)
        e1, e2 = pt(0.90, hw), pt(0.90, -hw)
        band1, band2 = pt(0.76, hw), pt(0.76, -hw)

        body = QPainterPath()
        body.moveTo(b1)
        body.lineTo(e1)
        body.lineTo(e2)
        body.lineTo(b2)
        body.closeSubpath()
        p.setBrush(Qt.NoBrush)
        p.drawPath(body)
        p.drawLine(band1, band2)      # 笔杆与笔帽的分界

        p.setPen(QPen(color, 1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([tip, b1, b2]))

    elif kind == "text":
        # 字母按包围盒居中，字号略大，视觉大小与其它线条图标保持一致
        f = QFont("Segoe UI")
        f.setPixelSize(max(6, int(round(s * 0.92))))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(color))
        tb = QFontMetricsF(f).tightBoundingRect("A")
        p.drawText(QPointF(s / 2 - tb.width() / 2 - tb.left(),
                           s / 2 - tb.height() / 2 - tb.top()), "A")

    elif kind == "color":
        p.setPen(QPen(WHITE, max(1.2, s * 0.055)))
        p.setBrush(color)
        r = inner * 0.5
        p.drawEllipse(QRectF(s / 2 - r, s / 2 - r, r * 2, r * 2))

    elif kind == "undo":
        path = QPainterPath()
        path.moveTo(s * 0.29, s * 0.76)
        path.lineTo(s * 0.29, s * 0.50)
        path.quadTo(s * 0.29, s * 0.26, s * 0.50, s * 0.26)
        path.quadTo(s * 0.71, s * 0.26, s * 0.71, s * 0.50)
        path.lineTo(s * 0.71, s * 0.66)
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.29, s * 0.78), QPointF(s * 0.20, s * 0.65))
        p.drawLine(QPointF(s * 0.29, s * 0.78), QPointF(s * 0.38, s * 0.65))

    elif kind == "pin":
        # 图钉：实心圆顶钉帽 + 收窄钉身 + 针尖（21px 下也能认出是图钉）
        cap = QRectF(s * 0.24, s * 0.12, s * 0.52, s * 0.34)
        path = QPainterPath()
        path.moveTo(s * 0.40, s * 0.44)
        path.lineTo(s * 0.26, s * 0.29)
        path.arcTo(cap, 180, -180)
        path.lineTo(s * 0.60, s * 0.44)
        path.lineTo(s * 0.535, s * 0.44)
        path.lineTo(s * 0.50, s * 0.88)
        path.lineTo(s * 0.465, s * 0.44)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPath(path)

    elif kind == "copy":
        # 后页只画右上两条边 + 前页描边，任何底色上都清晰
        p.drawLine(QPointF(s * 0.44, s * 0.16), QPointF(s * 0.80, s * 0.16))
        p.drawLine(QPointF(s * 0.80, s * 0.16), QPointF(s * 0.80, s * 0.56))
        p.drawRoundedRect(QRectF(s * 0.22, s * 0.32, s * 0.42, s * 0.52),
                          s * 0.05, s * 0.05)

    elif kind == "save":
        p.drawLine(QPointF(s * 0.5, s * 0.16), QPointF(s * 0.5, s * 0.62))
        _arrow_head(p, QPointF(s * 0.5, s * 0.16), QPointF(s * 0.5, s * 0.64), s * 0.22, color)
        p.drawLine(QPointF(s * 0.24, s * 0.80), QPointF(s * 0.76, s * 0.80))

    elif kind == "close":
        p.drawLine(QPointF(pad, pad), QPointF(s - pad, s - pad))
        p.drawLine(QPointF(s - pad, pad), QPointF(pad, s - pad))

    elif kind == "minimize":
        p.drawLine(QPointF(pad, s * 0.55), QPointF(s - pad, s * 0.55))

    elif kind == "settings":
        c = QPointF(s / 2, s / 2)
        r_out = s * 0.33
        r_root = s * 0.255
        teeth = 6
        steps = teeth * 4
        path = QPainterPath()
        for i in range(steps + 1):
            ang = 2 * math.pi * i / steps - math.pi / 2
            r = r_out if (i % 4) in (0, 1) else r_root
            pt = QPointF(c.x() + math.cos(ang) * r, c.y() + math.sin(ang) * r)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(c, s * 0.085, s * 0.085)

    elif kind == "camera":
        body = QRectF(pad * 0.8, s * 0.30, s - pad * 1.6, s * 0.50)
        p.drawRoundedRect(body, s * 0.09, s * 0.09)
        p.drawEllipse(QRectF(s * 0.38, s * 0.40, s * 0.24, s * 0.24))
        p.drawLine(QPointF(s * 0.42, s * 0.30), QPointF(s * 0.58, s * 0.30))

    elif kind == "check":
        p.drawLine(QPointF(pad, s * 0.52), QPointF(s * 0.42, s * 0.76))
        p.drawLine(QPointF(s * 0.42, s * 0.76), QPointF(s - pad * 0.8, s * 0.26))

    elif kind == "update":
        # 「发现新版本」标记：只保留向下的箭头和它下面那道横线，纯绿色、无底色。
        # （外面那层蓝色圆底 / 圆角方框都不要，免得在浅色标题栏上糊成一团。）
        cx = s / 2.0
        top, tip = s * 0.17, s * 0.60
        head = s * 0.19
        pen = QPen(UPDATE_GREEN, max(1.8, s * 0.115),
                   Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(cx, top), QPointF(cx, tip))
        p.drawLine(QPointF(cx - head, tip - head), QPointF(cx, tip))
        p.drawLine(QPointF(cx + head, tip - head), QPointF(cx, tip))
        p.drawLine(QPointF(cx - s * 0.27, s * 0.83), QPointF(cx + s * 0.27, s * 0.83))

    elif kind == "tray":
        # 托盘槽 + 向下的箭头（表示收进托盘）
        p.drawLine(QPointF(s * 0.16, s * 0.46), QPointF(s * 0.16, s * 0.82))
        p.drawLine(QPointF(s * 0.16, s * 0.82), QPointF(s * 0.84, s * 0.82))
        p.drawLine(QPointF(s * 0.84, s * 0.82), QPointF(s * 0.84, s * 0.46))
        p.drawLine(QPointF(s * 0.5, s * 0.14), QPointF(s * 0.5, s * 0.54))
        _arrow_head(p, QPointF(s * 0.5, s * 0.14), QPointF(s * 0.5, s * 0.58), s * 0.20, color)

    else:
        p.drawRect(QRectF(pad, pad, inner, inner))


def _arrow_head(p: QPainter, start: QPointF, end: QPointF, size: float, color: QColor):
    ang = math.atan2(end.y() - start.y(), end.x() - start.x())
    spread = math.radians(26)
    p1 = QPointF(end.x() - size * math.cos(ang - spread), end.y() - size * math.sin(ang - spread))
    p2 = QPointF(end.x() - size * math.cos(ang + spread), end.y() - size * math.sin(ang + spread))
    p.setBrush(QColor(color))
    p.setPen(QPen(color, 1))
    p.drawPolygon(QPolygonF([end, p1, p2]))
    p.setBrush(Qt.NoBrush)
