# -*- coding: utf-8 -*-
"""字号 / 粗细测试：编辑时即时生效、提交后位置不跳、不同字重可区分。"""
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
from PyQt5.QtGui import QColor, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)
import overlay as ov  # noqa: E402

W, H = 760, 460
out = os.path.join(ROOT, "build")


def make_shot():
    pm = QPixmap(W, H)
    pm.fill(QColor("#F3F6FB"))
    p = QPainter(pm)
    p.fillRect(0, 0, W, 46, QColor("#2B3240"))
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


def click(widget, pos):
    send_mouse(widget, QEvent.MouseButtonPress, pos)
    send_mouse(widget, QEvent.MouseButtonRelease, pos)


o = ov.CaptureOverlay("#FF3B30")
o.setGeometry(QRect(-3200, -3200, W, H))
o._shot = make_shot()
o._vgeo = QRect(0, 0, W, H)
o._dpr = 1.0
o.show()
for _ in range(4):
    app.processEvents()

send_mouse(o, QEvent.MouseButtonPress, QPoint(40, 60))
send_mouse(o, QEvent.MouseMove, QPoint(720, 400))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(720, 400))
app.processEvents()

# --- 40px / 常规字重 ---
o._switch_tool(ov.T_TEXT)
for _ in range(10):                 # 20 -> 40
    o._bar.bump_size(1)
o._bar.toggle_bold()                # -> 常规
app.processEvents()
print("style:", o.text_style(), "opts visible:", o._bar._text_opts.isVisible())

click(o, QPoint(90, 110))
app.processEvents()
o._text_edit.setPlainText("40px 常规字重\n第二行")
app.processEvents()
print("editor font px:", o._text_edit.font().pixelSize(),
      "bold:", o._text_edit.font().bold())
o.grab().save(os.path.join(out, "fs_editing.png"))
o._commit_text()
app.processEvents()
o.grab().save(os.path.join(out, "fs_committed.png"))
item = [i for i in o._items if i.kind == ov.T_TEXT][-1]
print("committed item:", item.font_size, item.bold, "| text:", item.text.replace("\n", "|"))

# --- 14px / 粗体，对比区分度 ---
o._bar.set_text_style(14, True)
o._on_text_size(14)
o._on_text_bold(True)
app.processEvents()
click(o, QPoint(90, 300))
app.processEvents()
o._text_edit.setPlainText("14px 粗体小字")
o._commit_text()
app.processEvents()

# --- 重新编辑已有文字应带出它自己的字号与字重 ---
click(o, QPoint(110, 130))
app.processEvents()
print("re-edit adopts:", o.text_style(), "label:", o._bar.lbl_size.text(),
      "bold btn:", o._bar.btn_bold.isChecked())
o._commit_text()
app.processEvents()

o.grab().save(os.path.join(out, "fs_final.png"))
img = o._export()
print("export:", img.width(), "x", img.height())
print("items:", [(i.kind, i.font_size, i.bold) for i in o._items])
print("done")
