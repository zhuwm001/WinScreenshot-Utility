# -*- coding: utf-8 -*-
"""渲染「正在安装更新」提示卡片，出一张预览图。

窗口是真的顶层窗口（不抢焦点、置顶），这里把它画到一张模拟桌面上，
方便看实际观感。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402

qt_env.setup()

from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

app = QApplication(sys.argv)

import install_notice  # noqa: E402


def main():
    n = install_notice.InstallNotice()
    n.show()
    for _ in range(8):
        app.processEvents()

    shot = n.grab()
    print("卡片窗口 %dx%d，在屏幕上会摆到 y=%.0f%%"
          % (n.width(), n.height(), 18))
    print("文案：%s / %s" % (install_notice.NOTICE_TITLE, install_notice.NOTICE_TEXT))

    # 模拟桌面：淡蓝灰渐变 + 一点点光晕，跟真实壁纸的明度接近
    canvas = QPixmap(920, 300)
    canvas.fill(QColor("#E8EDF3"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, 0, canvas.height())
    grad.setColorAt(0.0, QColor("#EAF0F7"))
    grad.setColorAt(1.0, QColor("#D9E2EC"))
    p.fillRect(canvas.rect(), grad)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 90))
    p.drawEllipse(120, -140, 560, 320)
    x = (canvas.width() - shot.width()) // 2
    y = (canvas.height() - shot.height()) // 2
    p.drawPixmap(QPoint(x, y), shot)
    p.end()

    out = os.path.join(ROOT, "build", "preview_install_notice.png")
    canvas.save(out)
    print("saved", out)

    # 第二张：放到一块 1080p 桌面上，看它在整屏里的位置和大小
    desk = QPixmap(1280, 720)
    desk.fill(QColor("#DCE4EE"))
    d = QPainter(desk)
    d.setRenderHint(QPainter.Antialiasing, True)
    g2 = QLinearGradient(0, 0, 1280, 720)
    g2.setColorAt(0.0, QColor("#E9F0F8"))
    g2.setColorAt(0.55, QColor("#CFDCEA"))
    g2.setColorAt(1.0, QColor("#B9C9DB"))
    d.fillRect(desk.rect(), g2)
    # 底部任务栏
    d.fillRect(0, 720 - 40, 1280, 40, QColor(28, 32, 40, 235))
    d.setPen(QColor(255, 255, 255, 190))
    f = d.font()
    f.setPixelSize(13)
    d.setFont(f)
    d.drawText(16, 720 - 15, "开始")
    d.end()
    # 卡片按 18% 的垂直位置摆，宽度按比例缩到 1280 宽的画面里
    scale = 1280 / 1920.0
    small = shot.scaled(int(shot.width() * scale), int(shot.height() * scale),
                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
    d2 = QPainter(desk)
    d2.setRenderHint(QPainter.SmoothPixmapTransform, True)
    x2 = (1280 - small.width()) // 2
    y2 = int(720 * 0.18) - int(install_notice.SHADOW * scale)
    d2.drawPixmap(QPoint(x2, y2), small)
    d2.end()
    out2 = os.path.join(ROOT, "build", "preview_install_notice_screen.png")
    desk.save(out2)
    print("saved", out2)
    n.close()


main()
