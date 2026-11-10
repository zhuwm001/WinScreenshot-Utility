# -*- coding: utf-8 -*-
"""模拟框选 + 标注，验证遮罩层与导出逻辑。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import overlay as ov  # noqa: E402

W, H = 900, 600
out = os.path.join(ROOT, "build")


def make_shot():
    pm = QPixmap(W, H)
    pm.setDevicePixelRatio(1.0)
    pm.fill(QColor("#EEF2F8"))
    p = QPainter(pm)
    p.fillRect(0, 0, W, 64, QColor("#2B3240"))
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(22)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(24, 42, "模拟窗口标题 · Test Window")
    p.setPen(QColor("#98A2B3"))
    p.setBrush(QColor("#FFFFFF"))
    for i in range(6):
        p.drawRoundedRect(40, 100 + i * 76, 820, 60, 8, 8)
    p.end()
    return pm


def send_mouse(widget, etype, pos):
    if etype == QEvent.MouseMove:
        button, buttons = Qt.NoButton, Qt.LeftButton
    elif etype == QEvent.MouseButtonPress:
        button, buttons = Qt.LeftButton, Qt.LeftButton
    else:
        button, buttons = Qt.LeftButton, Qt.NoButton
    e = QMouseEvent(etype, QPointF(pos), QPointF(widget.mapToGlobal(pos)),
                    button, buttons, Qt.NoModifier)
    QApplication.sendEvent(widget, e)


def drag(widget, start, end):
    send_mouse(widget, QEvent.MouseButtonPress, start)
    send_mouse(widget, QEvent.MouseMove, end)
    send_mouse(widget, QEvent.MouseButtonRelease, end)


o = ov.CaptureOverlay("#FF3B30")
o.setGeometry(QRect(-3200, -3200, W, H))
o._shot = make_shot()
o._vgeo = QRect(0, 0, W, H)
o._dpr = 1.0
o.show()
for _ in range(4):
    app.processEvents()

# 1) 框选
drag(o, QPoint(110, 96), QPoint(700, 500))
app.processEvents()
print("selection:", o._sel)

# 2) 矩形
ov_tool = o
o._switch_tool(ov.T_RECT)
drag(o, QPoint(150, 130), QPoint(330, 220))

# 3) 椭圆（换蓝色）
o._color = QColor("#4A86FF")
o._bar.set_color(o._color)
o._switch_tool(ov.T_ELLIPSE)
drag(o, QPoint(380, 130), QPoint(560, 230))

# 4) 箭头
o._color = QColor("#34C759")
o._bar.set_color(o._color)
o._switch_tool(ov.T_ARROW)
drag(o, QPoint(180, 320), QPoint(420, 250))

# 5) 文字（多行）
o._color = QColor("#FF3B30")
o._bar.set_color(o._color)
o._switch_tool(ov.T_TEXT)
send_mouse(o, QEvent.MouseButtonPress, QPoint(430, 300))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(430, 300))
app.processEvents()
print("text editor:", o._text_edit is not None)
if o._text_edit is not None:
    o._text_edit.setPlainText("这里是文字标注\n第二行第二行\n第三行")
    o._commit_text()
app.processEvents()

# 5a) 用工具栏把字号调大、切成常规字重，再写一段
for _ in range(7):                      # 20 -> 34
    o._bar.bump_size(1)
o._bar.toggle_bold()                    # 粗体 -> 常规
app.processEvents()
print("text style:", o.text_style(), "label:", o._bar.lbl_size.text())
send_mouse(o, QEvent.MouseButtonPress, QPoint(150, 380))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(150, 380))
app.processEvents()
if o._text_edit is not None:
    o._text_edit.setPlainText("34px 常规字重")
    o._commit_text()
app.processEvents()
print("items style:", [(i.kind, i.font_size, i.bold) for i in o._items
                       if i.kind == ov.T_TEXT])
o._bar.set_text_style(20, True)
o._on_text_size(20)
o._on_text_bold(True)
app.processEvents()

# 5b) 再点一次这段文字 -> 应进入编辑已有文字
send_mouse(o, QEvent.MouseButtonPress, QPoint(450, 310))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(450, 310))
app.processEvents()
print("re-edit hit:", o._editing_item is not None,
      "editor:", o._text_edit is not None,
      "text:", o._text_edit.toPlainText().replace("\n", "|") if o._text_edit else "")
o._commit_text()
app.processEvents()

for _ in range(4):
    app.processEvents()

o.grab().save(os.path.join(out, "overlay_view.png"))
img = o._export()
img.save(os.path.join(out, "overlay_export.png"))
print("export size:", img.width(), "x", img.height())
print("items:", [i.kind for i in o._items])

# 撤销一次看是否生效
o._undo()
app.processEvents()
img2 = o._export()
print("after undo items:", [i.kind for i in o._items])

print("done")
