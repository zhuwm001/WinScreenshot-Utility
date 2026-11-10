# -*- coding: utf-8 -*-
"""文字标注交互测试：回车换行、点外部完成、再次点击进入编辑。"""
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
from PyQt5.QtGui import QColor, QFont, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)
import overlay as ov  # noqa: E402

W, H = 800, 520


def make_shot():
    pm = QPixmap(W, H)
    pm.fill(QColor("#F3F6FB"))
    p = QPainter(pm)
    p.fillRect(0, 0, W, 48, QColor("#2B3240"))
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

# 框选
send_mouse(o, QEvent.MouseButtonPress, QPoint(80, 80))
send_mouse(o, QEvent.MouseMove, QPoint(700, 460))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(700, 460))
app.processEvents()
print("selection:", o._sel.getRect())

o._switch_tool(ov.T_TEXT)

# 1) 点击空白处 -> 出现输入框
click(o, QPoint(140, 150))
app.processEvents()
edit = o._text_edit
print("[1] 输入框出现:", edit is not None)

# 2) 输入两行：第一行 + 回车 + 第二行
QTest.keyClicks(edit, "hello")
QTest.keyClick(edit, Qt.Key_Return)
QTest.keyClicks(edit, "world")
app.processEvents()
raw = edit.toPlainText()
print("[2] 回车后内容:", raw.replace("\n", "\\n"), "-> 是换行不是复制:", raw == "hello\nworld")
print("    输入时截图未结束:", o.isVisible(), "items:", len(o._items))

# 3) 点击输入框以外 -> 自动完成输入
click(o, QPoint(520, 380))
app.processEvents()
texts = [i.text for i in o._items if i.kind == ov.T_TEXT]
print("[3] 点外部后已提交:", o._text_edit is None, "| 文字项:", texts)

# 4) 再点这段文字 -> 重新进入编辑
click(o, QPoint(150, 160))
app.processEvents()
print("[4] 再次进入编辑:", o._text_edit is not None,
      "| 带出原文:", o._text_edit.toPlainText().replace("\n", "\\n") if o._text_edit else "")

# 5) 追加内容后按 Esc -> 完成编辑而不是取消截图
QTest.keyClicks(o._text_edit, "!!")
QTest.keyClick(o._text_edit, Qt.Key_Escape)
app.processEvents()
print("[5] Esc 完成编辑:", o._text_edit is None, "| 截图仍在:", o.isVisible(),
      "| 文字项:", [i.text.replace("\n", "\\n") for i in o._items if i.kind == ov.T_TEXT])

# 6) 清空文字 -> 该条标注被删除
before = len(o._items)
click(o, QPoint(150, 160))
app.processEvents()
o._text_edit.selectAll()
QTest.keyClick(o._text_edit, Qt.Key_Delete)
click(o, QPoint(600, 400))
app.processEvents()
print("[6] 清空后删除该条:", len(o._items) == before - 1, "| items:", len(o._items))

o.grab().save(os.path.join(ROOT, "build", "text_flow.png"))
print("done")
