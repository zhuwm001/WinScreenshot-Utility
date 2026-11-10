# -*- coding: utf-8 -*-
"""右下角消息提示：3 秒自动消失，也可以点右上角关闭。"""
from PyQt5.QtCore import QPropertyAnimation, QRectF, QSize, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QToolButton, QVBoxLayout, QWidget,
)

import icons

MARGIN = 12          # 距屏幕边缘
GAP = 10             # 多条之间的间距
SHADOW = 12          # 窗口内为投影预留的空白

KIND_COLORS = {
    "info": "#4A86FF",
    "check": "#34C759",
    "warn": "#FF9500",
}
KIND_GLYPHS = {
    "info": "i",
    "check": "✓",
    "warn": "!",
}


def _badge(kind: str, size: int = 34) -> QPixmap:
    app = QApplication.instance()
    dpr = float(app.primaryScreen().devicePixelRatio()) if app and app.primaryScreen() else 1.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(KIND_COLORS.get(kind, KIND_COLORS["info"])))
    p.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    f = QFont("Segoe UI")
    f.setPixelSize(int(size * 0.56))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(0, 1, size, size, int(Qt.AlignCenter), KIND_GLYPHS.get(kind, "i"))
    p.end()
    return pm


class Toast(QWidget):
    """桌面右下角的消息卡片，自动消失 + 可点关闭。"""

    _alive = []

    def __init__(self, title: str, text: str = "", kind: str = "info",
                 timeout: int = 3000, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle(title)

        self._timeout = max(800, int(timeout))
        self._closing = False
        self._anim_in = None
        self._anim_out = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        outer.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("toastCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(card)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(20, 30, 60, 70))
        card.setGraphicsEffect(shadow)

        row = QHBoxLayout(card)
        row.setContentsMargins(14, 12, 10, 12)
        row.setSpacing(11)

        badge = QLabel(card)
        badge.setPixmap(_badge(kind))
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        row.addWidget(badge, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_title = QLabel(title, card)
        lbl_title.setObjectName("toastTitle")
        col.addWidget(lbl_title)
        if text:
            lbl_text = QLabel(text, card)
            lbl_text.setObjectName("toastText")
            lbl_text.setWordWrap(True)
            col.addWidget(lbl_text)
        row.addLayout(col, 1)

        btn = QToolButton(card)
        btn.setObjectName("toastClose")
        btn.setIcon(icons.render_icon("close", 12, QColor("#98A2B3"), 1.7))
        btn.setIconSize(QSize(12, 12))
        btn.setFixedSize(20, 20)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip("关闭")
        btn.clicked.connect(self.dismiss)
        row.addWidget(btn, 0, Qt.AlignTop)

        self.setStyleSheet("""
        QFrame#toastCard {
            background: #FFFFFF;
            border: 1px solid #E7EBF3;
            border-radius: 12px;
        }
        QLabel#toastTitle {
            font-family: "Microsoft YaHei UI";
            font-size: 13px;
            font-weight: 600;
            color: #1F2330;
        }
        QLabel#toastText {
            font-family: "Microsoft YaHei UI";
            font-size: 12px;
            color: #6B7280;
        }
        QToolButton#toastClose {
            border: none;
            border-radius: 5px;
            background: transparent;
        }
        QToolButton#toastClose:hover {
            background: #F0F2F7;
        }
        """)

        self.setFixedWidth(336)

    # ------------------------------------------------------------ 显示
    def popup(self):
        self.adjustSize()
        Toast._alive.append(self)
        Toast._relayout()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim_in = anim

        QTimer.singleShot(self._timeout, self.dismiss)

    def dismiss(self):
        if self._closing:
            return
        self._closing = True
        if self in Toast._alive:
            Toast._alive.remove(self)
        Toast._relayout()

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(170)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self.close)
        anim.start()
        self._anim_out = anim

    def closeEvent(self, event):
        if self in Toast._alive:
            Toast._alive.remove(self)
        Toast._relayout()
        super().closeEvent(event)

    # ------------------------------------------------------------ 布局
    @classmethod
    def _relayout(cls):
        if not cls._alive:
            return
        scr = QApplication.primaryScreen()
        if scr is None:
            return
        geo = scr.availableGeometry()
        y = geo.bottom() + 1 - MARGIN
        for t in reversed(cls._alive):
            y -= t.height()
            t.move(geo.right() + 1 - MARGIN - t.width(), y)
            y -= GAP

    # ------------------------------------------------------------ 便捷入口
    @classmethod
    def show_toast(cls, title: str, text: str = "", kind: str = "info",
                   timeout: int = 3000) -> "Toast":
        t = cls(title, text, kind, timeout)
        t.popup()
        return t
