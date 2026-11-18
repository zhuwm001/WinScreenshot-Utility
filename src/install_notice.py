# -*- coding: utf-8 -*-
"""更新安装期间的提示卡片。

静默安装的过程是：主程序退出 → 安装程序在后台替换文件 → 新版启动。中间十几秒
屏幕上什么都没有，用户分不清是在装还是崩了。原来只在右下角弹一个 2.5 秒的
toast，程序一关它也消失，等于没提示。

这里换成一张明显的卡片，等主程序退出时再消失，之后由安装程序的进度窗口接着
显示到装完。文案沿用常见软件更新的说法，避免用户猜测。
"""
from PyQt5.QtCore import QPropertyAnimation, QSize, Qt
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)

from paths import asset

NOTICE_TITLE = "我爱截图"
NOTICE_TEXT = "正在安装更新，更新完成后将自动重启应用。"

SHADOW = 18          # 窗口内为投影预留的空白
CARD_MIN_WIDTH = 420


class InstallNotice(QWidget):
    """一张不会自己消失的提示卡片：什么时候关由调用方决定。"""

    def __init__(self, title: str = NOTICE_TITLE, text: str = NOTICE_TEXT,
                 parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.NoDropShadowWindowHint
                         | Qt.WindowDoesNotAcceptFocus)
        # 顶层窗口用半透明背景是 Qt 支持的用法（子控件上才是未定义行为）
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle(title)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        outer.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("noticeCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setMinimumWidth(CARD_MIN_WIDTH)
        outer.addWidget(card)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(20, 30, 60, 60))
        card.setGraphicsEffect(shadow)

        row = QHBoxLayout(card)
        row.setContentsMargins(22, 20, 26, 20)
        row.setSpacing(16)

        icon = QLabel(card)
        icon.setPixmap(_app_icon(44))
        icon.setFixedSize(44, 44)
        row.addWidget(icon, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(6)
        lbl_title = QLabel(title, card)
        lbl_title.setObjectName("noticeTitle")
        col.addWidget(lbl_title)
        lbl_text = QLabel(text, card)
        lbl_text.setObjectName("noticeText")
        lbl_text.setWordWrap(True)
        col.addWidget(lbl_text)
        row.addLayout(col, 1)

        self.setStyleSheet("""
        QFrame#noticeCard {
            background: #FFFFFF;
            border: 1px solid #E4E7EC;
            border-radius: 12px;
        }
        QLabel#noticeTitle {
            font-family: "Microsoft YaHei UI";
            font-size: 16px;
            font-weight: 600;
            color: #1A1C22;
        }
        QLabel#noticeText {
            font-family: "Microsoft YaHei UI";
            font-size: 14px;
            color: #5A6170;
        }
        """)

        self._anim = None

    # ------------------------------------------------------------ 显示
    def popup(self):
        """屏幕水平居中、靠上摆：显眼又不挡着正在看的窗口。"""
        self.adjustSize()
        scr = QApplication.primaryScreen()
        if scr is not None:
            geo = scr.availableGeometry()
            x = geo.center().x() - self.width() // 2
            y = geo.top() + int(geo.height() * 0.18)
            self.move(int(x), int(y))
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim

    def close_now(self):
        self.close()

    @classmethod
    def popup_notice(cls, title: str = NOTICE_TITLE, text: str = NOTICE_TEXT,
                     parent=None) -> "InstallNotice":
        n = cls(title, text, parent)
        n.popup()
        return n


def _app_icon(size: int):
    ico = QIcon(asset("app.ico"))
    if ico.isNull():
        ico = QIcon(asset("app.png"))
    pm = ico.pixmap(QSize(size, size))
    return pm
