# -*- coding: utf-8 -*-
"""主窗口：标题 + 截图按钮 + 设置。"""
from PyQt5.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QToolButton, QVBoxLayout, QWidget,
)

import icons
import theme
from app_config import APP_NAME, APP_VERSION
from paths import asset

# ---------------- 署名徽标（换图只改这三行） ----------------
# 逻辑显示宽度（px），必须等于 1x 图的实际宽度
BADGE_WIDTH = 69
# 可用的图片档位，必须等于 assets 里文件名中的数字（1x/2x/3x/4x 真实像素）
BADGE_TIERS = (69, 138, 207, 276)
# 文件名前缀，实际文件是 <前缀>-<宽度>.png
BADGE_PREFIX = "badge-letters"


def _force_foreground(hwnd: int):
    """把窗口顶到最前：短暂置顶再取消，绕过 Windows 的前台窗口限制。"""
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        flags = 0x0002 | 0x0001 | 0x0040  # NOMOVE | NOSIZE | SHOWWINDOW
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


class MainWindow(QWidget):
    capture_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    update_requested = pyqtSignal()
    hide_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    close_requested = pyqtSignal()

    MARGIN = 20

    def __init__(self, hotkey_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(APP_NAME)
        ico = asset("app.ico")
        self._icon = QIcon(ico) if ico and QIcon(ico).availableSizes() else icons.render_icon("camera", 32)
        self.setWindowIcon(self._icon)
        self.setFixedSize(448, 308)

        self._dragging = False
        self._drag_offset = QPoint()
        self._update_info = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
        outer.setSpacing(0)

        self._container = QFrame(self)
        self._container.setObjectName("container")
        self._container.setAttribute(Qt.WA_StyledBackground, True)
        self._container.installEventFilter(self)
        outer.addWidget(self._container)

        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(24, 36, 66, 70))
        self._container.setGraphicsEffect(shadow)

        self._build_ui(hotkey_text)

        self.setStyleSheet(theme.main_window_qss() + """
        QFrame#container {
            background: #FFFFFF;
            border: 1px solid #E9EDF5;
            border-radius: 16px;
        }
        """)

    # ------------------------------------------------------------------ UI
    def _build_ui(self, hotkey_text: str):
        lay = QVBoxLayout(self._container)
        lay.setContentsMargins(24, 18, 24, 20)
        lay.setSpacing(0)

        # ---------- 标题栏 ----------
        head = QHBoxLayout()
        head.setSpacing(10)

        logo = QLabel(self._container)
        pm = QPixmap(asset("app.png"))
        if pm.isNull():
            pm = icons.render("camera", 34, QColor(theme.PRIMARY))
        logo.setPixmap(pm.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(34, 34)
        head.addWidget(logo)

        txt_box = QVBoxLayout()
        txt_box.setSpacing(1)
        title = QLabel(APP_NAME, self._container)
        title.setObjectName("title")
        sub = QLabel("截图 · 标注 · 贴图 · 复制", self._container)
        sub.setObjectName("subtitle")
        txt_box.addWidget(title)
        txt_box.addWidget(sub)
        head.addLayout(txt_box)
        head.addStretch(1)

        # 右上角四个按钮：更新提示（仅有新版本时出现）· 设置 · 隐藏 · 关闭
        winbtns = QHBoxLayout()
        winbtns.setSpacing(5)

        self.btn_update = self._title_button("update", "发现新版本", 18)
        self.btn_update.clicked.connect(self.update_requested.emit)
        self.btn_update.hide()
        winbtns.addWidget(self.btn_update)

        self.btn_settings = self._title_button("settings", "设置", 17, 1.8)
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        winbtns.addWidget(self.btn_settings)

        self.btn_min = self._title_button("minimize", "隐藏到桌面右下角")
        self.btn_min.clicked.connect(self.hide_requested.emit)
        winbtns.addWidget(self.btn_min)

        self.btn_close = self._title_button("close", "关闭")
        self.btn_close.clicked.connect(self.close)
        winbtns.addWidget(self.btn_close)

        head.addLayout(winbtns)

        lay.addLayout(head)
        lay.addSpacing(20)

        # ---------- 开始截图 ----------
        self.btn_capture = QPushButton("开始截图", self._container)
        self.btn_capture.setObjectName("capture")
        self.btn_capture.setFixedHeight(62)
        self.btn_capture.setCursor(Qt.PointingHandCursor)
        self.btn_capture.clicked.connect(self.capture_requested.emit)
        lay.addWidget(self.btn_capture)

        lay.addSpacing(11)

        self.lbl_hotkey = QLabel(self._container)
        self.lbl_hotkey.setObjectName("hotkeyBadge")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        self.set_hotkey_text(hotkey_text)
        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge_row.addWidget(self.lbl_hotkey)
        badge_row.addStretch(1)
        lay.addLayout(badge_row)

        lay.addSpacing(14)

        lay.addStretch(1)

        tip = QLabel("按 <b>Ctrl+C</b> 复制 · <b>Ctrl+S</b> 存盘 · 点图钉置顶", self._container)
        tip.setObjectName("subtitle")
        tip.setTextFormat(Qt.RichText)
        tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(tip)

        author = QLabel(self._container)
        author.setPixmap(self._badge_pixmap(BADGE_WIDTH))
        author.setAlignment(Qt.AlignCenter)
        lay.addSpacing(10)
        lay.addWidget(author)

    @staticmethod
    def _badge_pixmap(width: int) -> QPixmap:
        """署名徽标：按需要的物理像素挑最贴近的原生尺寸图，避免缩放发虚。"""
        dpr = 1.0
        screen = QApplication.primaryScreen()
        if screen is not None:
            dpr = max(1.0, float(screen.devicePixelRatio()))
        need = int(round(width * dpr))
        for w in BADGE_TIERS:
            if w >= need:
                pm = QPixmap(asset("%s-%d.png" % (BADGE_PREFIX, w)))
                if pm.isNull():
                    continue
                if pm.width() != need:
                    # 缩放比不是整数（如 150%）时补一次缩放，保证逻辑宽度一致
                    pm = pm.scaled(need, max(1, int(round(pm.height() * need / pm.width()))),
                                   Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                pm.setDevicePixelRatio(dpr)
                return pm
        return QPixmap()

    def _title_button(self, icon_kind, tip, size=14, pen=1.6):
        b = QToolButton(self._container)
        b.setObjectName("winbtn")
        b.setIcon(icons.render_icon(icon_kind, size, QColor(theme.TEXT_SUB), pen))
        b.setIconSize(QSize(size, size))
        b.setFixedSize(28, 28)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    # ------------------------------------------------------------------ 对外
    def set_hotkey_text(self, text: str):
        self.lbl_hotkey.setText("截图快捷键  %s" % (text or "未设置"))

    def set_update_available(self, info):
        """有新版本时在标题栏亮出绿箭头；传 None 收起。"""
        self._update_info = info
        if info is None:
            self.btn_update.setToolTip("发现新版本")
            self.btn_update.hide()
            return
        ver = (getattr(info, "version", "") or "").strip()
        self.btn_update.setToolTip("发现新版本 %s，点击查看" % ver if ver
                                  else "发现新版本，点击查看")
        self.btn_update.show()

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.center() - self.rect().center() + QPoint(0, -20))

    def show_and_raise(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        _force_foreground(int(self.winId()))

    # ------------------------------------------------------------------ 行为
    def eventFilter(self, obj, event):
        if obj is self._container:
            et = event.type()
            if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                if event.pos().y() < 64:
                    self._dragging = True
                    self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
                    return True
            elif et == QEvent.MouseMove and self._dragging:
                self.move(event.globalPos() - self._drag_offset)
                return True
            elif et == QEvent.MouseButtonRelease:
                self._dragging = False
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        # 窗口整体透明，圆角由 container 绘制；这里只需清屏
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.end()

    def closeEvent(self, event):
        # 交给控制器决定：退出还是最小化到托盘
        event.ignore()
        self.close_requested.emit()
