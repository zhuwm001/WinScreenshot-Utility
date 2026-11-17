# -*- coding: utf-8 -*-
"""检查更新对话框：有新版本 / 已是最新 / 检查失败，三种状态共用一个窗口。"""
import datetime

from PyQt5.QtCore import QRectF, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QColor, QLinearGradient, QPainter, QPen, QPixmap,
)
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser,
    QVBoxLayout,
)
from PyQt5.QtGui import QDesktopServices

import theme
from app_config import APP_NAME, APP_VERSION
from update import InstallerDownloader

MODE_NEW = "new"
MODE_LATEST = "latest"
MODE_ERROR = "error"


def _badge_pixmap(size: int = 40) -> QPixmap:
    """一个蓝紫渐变的圆 + 向下的箭头，代表"下载新版本"。"""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    r = QRectF(0.5, 0.5, size - 1, size - 1)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(theme.PRIMARY))
    grad.setColorAt(1, QColor(theme.ACCENT))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    p.drawEllipse(r)
    # 箭头
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(2.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    cx, cy = size / 2.0, size / 2.0
    p.drawLine(int(cx), int(cy - 8), int(cx), int(cy + 6))
    p.drawLine(int(cx - 5), int(cy + 1), int(cx), int(cy + 6))
    p.drawLine(int(cx + 5), int(cy + 1), int(cx), int(cy + 6))
    p.drawLine(int(cx - 7), int(cy + 10), int(cx + 7), int(cy + 10))
    p.end()
    return pm


class UpdateDialog(QDialog):
    """下载自己管，装不装交给外面（外面要负责退出进程）。"""

    ready_to_install = pyqtSignal(str)     # 安装包已下好，路径
    retry_requested = pyqtSignal()

    def __init__(self, info=None, message: str = "", mode: str = MODE_NEW,
                 parent=None):
        super().__init__(parent)
        self.info = info
        self.mode = mode
        self._error_text = message or ""
        self._downloader = None
        self._busy = False

        self.setWindowTitle("检查更新 - %s" % APP_NAME)
        self.setStyleSheet(theme.dialog_qss() + self._extra_qss())
        self.setMinimumWidth(560)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(14)

        # ---------------- 标题 ----------------
        head = QHBoxLayout()
        head.setSpacing(12)
        icon = QLabel(self)
        icon.setPixmap(_badge_pixmap(40))
        icon.setFixedSize(40, 40)
        head.addWidget(icon, 0, Qt.AlignTop)

        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.lbl_title = QLabel(self)
        self.lbl_title.setObjectName("upTitle")
        self.lbl_sub = QLabel(self)
        self.lbl_sub.setObjectName("hint")
        self.lbl_sub.setWordWrap(True)
        titles.addWidget(self.lbl_title)
        titles.addWidget(self.lbl_sub)
        head.addLayout(titles, 1)
        root.addLayout(head)

        # ---------------- 正文 ----------------
        self.box = QTextBrowser(self)
        self.box.setObjectName("notesBox")
        self.box.setOpenExternalLinks(True)
        self.box.setFixedHeight(168)
        root.addWidget(self.box)

        # ---------------- 进度 ----------------
        self.lbl_status = QLabel("", self)
        self.lbl_status.setObjectName("hint")
        self.bar = QProgressBar(self)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.lbl_status.hide()
        self.bar.hide()
        root.addWidget(self.lbl_status)
        root.addWidget(self.bar)

        # ---------------- 按钮 ----------------
        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_page = QPushButton("打开发布页", self)
        self.btn_page.clicked.connect(self._open_page)
        btns.addWidget(self.btn_page)
        btns.addStretch(1)
        self.btn_close = QPushButton("稍后", self)
        self.btn_close.clicked.connect(self.reject)
        btns.addWidget(self.btn_close)
        self.btn_go = QPushButton("立即更新", self)
        self.btn_go.setObjectName("primary")
        self.btn_go.setDefault(True)
        self.btn_go.clicked.connect(self._on_primary)
        btns.addWidget(self.btn_go)
        root.addLayout(btns)

        self._fill()

    # ---------------------------------------------------------------- 样式
    @staticmethod
    def _extra_qss() -> str:
        return """
        QLabel#upTitle {
            font-size: 17px;
            font-weight: 600;
            color: %(text)s;
        }
        QTextBrowser#notesBox {
            background: %(soft)s;
            border: 1px solid #EAEEF6;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 13px;
            color: %(text)s;
        }
        QProgressBar {
            background: #EDF1F8;
            border: none;
            border-radius: 3px;
        }
        QProgressBar::chunk {
            background: %(primary)s;
            border-radius: 3px;
        }
        """ % {"text": theme.TEXT, "soft": theme.BG_SOFT,
               "primary": theme.PRIMARY}

    # ---------------------------------------------------------------- 三种状态
    def _fill(self):
        if self.mode == MODE_NEW:
            self._fill_new()
        elif self.mode == MODE_LATEST:
            self._fill_latest()
        else:
            self._fill_error()

    def _fill_new(self):
        info = self.info
        self.lbl_title.setText("发现新版本 %s" % (info.version if info else ""))
        bits = ["当前版本 %s" % APP_VERSION]
        if info is not None:
            if info.size_text:
                bits.append("安装包 %s" % info.size_text)
            day = _short_date(info.published_at)
            if day:
                bits.append("发布于 %s" % day)
            if getattr(info, "signed", False):
                bits.append("签名已校验")
        self.lbl_sub.setText(" · ".join(bits))

        text = (info.notes_text if info is not None else "") or "该版本未提供更新说明。"
        if info is not None and getattr(info, "signed", False):
            text = "此版本已通过作者签名校验。\n\n" + text
        if not info or not info.has_installer:
            text += "\n\n该版本未提供安装包，请点击「打开发布页」手动下载。"
            self.btn_go.setText("打开发布页")
        else:
            self.btn_go.setText("立即更新")
        self.box.setPlainText(text)

    def _fill_latest(self):
        self.lbl_title.setText("已是最新版本")
        self.lbl_sub.setText("当前版本 %s" % APP_VERSION)
        self.box.setPlainText("当前已是最新版本，无需更新。")
        self.box.setFixedHeight(64)
        self.btn_go.setText("确定")
        self.btn_go.clicked.disconnect()
        self.btn_go.clicked.connect(self.accept)
        self.btn_close.hide()

    def _fill_error(self):
        self.lbl_title.setText("检查更新失败")
        self.lbl_sub.setText("当前版本 %s" % APP_VERSION)
        self.box.setPlainText((self._error_text or "") +
                              "\n\n可以点「打开发布页」手动确认是否有新版本。")
        self.box.setFixedHeight(110)
        self.btn_go.setText("重试")
        self.btn_go.clicked.disconnect()
        self.btn_go.clicked.connect(self._on_retry)
        self.btn_close.setText("关闭")

    # 错误文案由外面（构造参数 / set_error）塞进来
    def set_error(self, message: str):
        self._error_text = message or "未知错误。"
        self._fill_error()

    # ---------------------------------------------------------------- 按钮
    def _on_retry(self):
        self.retry_requested.emit()
        self.accept()

    def _open_page(self):
        url = (self.info.page_url if self.info else "") or \
              "https://github.com/zhuwm001/WinScreenshot-Utility/releases/latest"
        QDesktopServices.openUrl(QUrl(url))

    def _on_primary(self):
        # 已最新 / 失败 两种状态下按钮已换成别的处理
        if self.mode != MODE_NEW:
            return
        if self.info is None or not self.info.has_installer:
            self._open_page()
            return
        self._start_download()

    # ---------------------------------------------------------------- 下载
    def _start_download(self):
        if self._busy:
            return
        self._busy = True
        self.btn_go.setEnabled(False)
        self.btn_go.setText("正在下载…")
        self.btn_page.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.bar.setValue(0)
        self.bar.show()
        self.lbl_status.setText("正在准备下载…")
        self.lbl_status.show()

        self._downloader = InstallerDownloader(self)
        self._downloader.progress.connect(self._on_progress)
        self._downloader.done.connect(self._on_done)
        self._downloader.failed.connect(self._on_failed)
        self._downloader.start(self.info)

    def _on_progress(self, got, total):
        if self.bar.isHidden():
            self.bar.show()
            self.lbl_status.show()
        if total > 0:
            pct = max(0, min(100, int(got * 100 / total)))
            self.bar.setValue(pct)
            self.lbl_status.setText("正在下载 %s / %s" % (_mb(got), _mb(total)))
        else:
            self.lbl_status.setText("正在下载 %s" % _mb(got))

    def _on_done(self, path):
        self.bar.setValue(100)
        self.lbl_status.setText("下载完成，正在安装，软件会自动重新打开…")
        self.btn_go.setText("正在安装…")
        self.ready_to_install.emit(path)

    def _on_failed(self, message):
        self._busy = False
        self.bar.hide()
        self.lbl_status.setText("下载失败：%s" % message)
        self.lbl_status.setStyleSheet("color: %s; font-size: 12px;" % theme.DANGER)
        self.lbl_status.show()
        self.btn_go.setEnabled(True)
        self.btn_go.setText("重试")
        self.btn_page.setEnabled(True)
        self.btn_close.setEnabled(True)
        try:
            self.btn_go.clicked.disconnect()
        except TypeError:
            pass
        self.btn_go.clicked.connect(self._start_download)

    # ---------------------------------------------------------------- 生命周期
    def closeEvent(self, event):
        # 下载中就悄悄掐掉，别留半个文件
        if self._downloader is not None and self._busy:
            try:
                self._downloader._abort()
            except Exception:
                pass
        super().closeEvent(event)


def _mb(num) -> str:
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "0 MB"
    if num >= 1024 * 1024:
        return "%.1f MB" % (num / 1024.0 / 1024.0)
    return "%.0f KB" % (num / 1024.0)


def _short_date(iso: str) -> str:
    """'2026-11-15T13:20:00Z' -> '2026-11-15'（转成本地日期，看个大概就行）"""
    if not iso:
        return ""
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        return dt.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return iso[:10]
