# -*- coding: utf-8 -*-
"""贴图窗口：把截图钉在屏幕最前端。"""
import os
from datetime import datetime

from PyQt5.QtCore import QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QFileDialog, QMenu, QWidget

_ALIVE = []          # 保持引用，避免被回收


class PinWindow(QWidget):
    MIN_SCALE = 0.15
    MAX_SCALE = 6.0

    def __init__(self, image: QImage, screen_pos: QPoint, screen_dpr: float = 1.0):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.OpenHandCursor)
        self.setWindowTitle("")
        self.setToolTip("拖动移动 · 滚轮缩放 · Ctrl+滚轮调透明度 · 双击/Esc 关闭")

        self._img = image
        self._dpr = screen_dpr if screen_dpr > 0 else 1.0
        self._base = QSize(max(1, int(round(image.width() / self._dpr))),
                           max(1, int(round(image.height() / self._dpr))))
        self._scale = 1.0
        self._opacity = 1.0
        self._hover = False
        self._dragging = False
        self._drag_offset = QPoint()

        self.setWindowOpacity(1.0)
        self.setGeometry(QRect(screen_pos, self._base))
        self._keep_on_screen()
        _ALIVE.append(self)

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.drawImage(self.rect(), self._img)
        # 双层边框：外圈深色保证任何底色上都看得见，内圈白色提亮
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(74, 134, 255) if self._hover else QColor(40, 48, 66, 165), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.setPen(QPen(QColor(255, 255, 255, 190), 1))
        p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        p.end()

    # ------------------------------------------------------------ 交互
    def enterEvent(self, event):
        self._hover = True
        self.setCursor(Qt.OpenHandCursor)
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            self.setFocus(Qt.MouseFocusReason)
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_menu(event.globalPos())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.OpenHandCursor)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.close()

    def wheelEvent(self, event):
        steps = event.angleDelta().y()
        if steps == 0:
            return
        if event.modifiers() & Qt.ControlModifier:
            self._opacity = max(0.15, min(1.0, self._opacity + (0.06 if steps > 0 else -0.06)))
            self.setWindowOpacity(self._opacity)
            return

        factor = 1.12 if steps > 0 else 1 / 1.12
        new_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, self._scale * factor))
        if abs(new_scale - self._scale) < 1e-4:
            return

        old_size = self.size()
        new_w = max(24, int(round(self._base.width() * new_scale)))
        new_h = max(24, int(round(self._base.height() * new_scale)))
        local = event.pos()
        ratio_x = local.x() / max(1, old_size.width())
        ratio_y = local.y() / max(1, old_size.height())

        pos = self.pos()
        nx = pos.x() + local.x() - new_w * ratio_x
        ny = pos.y() + local.y() - new_h * ratio_y
        self._scale = new_scale
        self.setGeometry(int(round(nx)), int(round(ny)), new_w, new_h)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key_C and (event.modifiers() & Qt.ControlModifier):
            self._copy()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------ 菜单
    def _show_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; border: 1px solid #E6EAF2; border-radius: 8px;"
            " padding: 5px; font-family: 'Microsoft YaHei UI'; font-size: 13px; }"
            "QMenu::item { padding: 7px 22px 7px 14px; border-radius: 5px; color: #1F2330; }"
            "QMenu::item:selected { background: #F2F6FF; color: #4A86FF; }"
            "QMenu::separator { height: 1px; background: #EEF1F7; margin: 4px 6px; }"
        )
        menu.addAction("复制图片", self._copy)
        menu.addAction("保存为文件…", self._save)
        menu.addSeparator()
        menu.addAction("恢复原始大小", self._reset_scale)
        menu.addAction("透明度 100%", self._reset_opacity)
        menu.addSeparator()
        menu.addAction("关闭此贴图", self.close)
        menu.exec_(global_pos)

    def _copy(self):
        QApplication.clipboard().setImage(self._img)

    def _save(self):
        desk = os.path.join(os.path.expanduser("~"), "Desktop")
        name = "我爱截图_%s.png" % datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(self, "保存贴图", os.path.join(desk, name),
                                              "PNG 图片 (*.png);;JPEG 图片 (*.jpg)")
        if path:
            self._img.save(path)

    def _reset_scale(self):
        self._scale = 1.0
        self.setGeometry(QRect(self.pos(), self._base))

    def _reset_opacity(self):
        self._opacity = 1.0
        self.setWindowOpacity(1.0)

    # ------------------------------------------------------------ 其他
    def _keep_on_screen(self):
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        pos = self.pos()
        w = min(self.width(), avail.width())
        h = min(self.height(), avail.height())
        x = min(max(pos.x(), avail.left()), avail.right() - w + 1)
        y = min(max(pos.y(), avail.top()), avail.bottom() - h + 1)
        self.setGeometry(x, y, w, h)

    def closeEvent(self, event):
        if self in _ALIVE:
            _ALIVE.remove(self)
        super().closeEvent(event)
