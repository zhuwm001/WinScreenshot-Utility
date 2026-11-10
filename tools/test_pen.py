# -*- coding: utf-8 -*-
"""验证手绘（铅笔）标注：图标、笔画采样、平滑路径、撤销与导出。"""
import math
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
from PyQt5.QtGui import (  # noqa: E402
    QColor, QFont, QMouseEvent, QPainter, QPixmap,
)
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import icons  # noqa: E402
import overlay as ov  # noqa: E402

W, H = 900, 620
out = os.path.join(ROOT, "build")
ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


def make_shot():
    pm = QPixmap(W, H)
    pm.setDevicePixelRatio(1.0)
    pm.fill(QColor("#F2F5FA"))
    p = QPainter(pm)
    p.fillRect(0, 0, W, 64, QColor("#2B3240"))
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(22)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(24, 42, "手绘标注测试")
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


def stroke(widget, points):
    """按住鼠标沿折线走一遍。"""
    send_mouse(widget, QEvent.MouseButtonPress, points[0])
    for pt in points[1:]:
        send_mouse(widget, QEvent.MouseMove, pt)
    send_mouse(widget, QEvent.MouseButtonRelease, points[-1])


# ---------------------------------------------------------------- 1. 图标
strip = QPixmap(5 * 96 + 20, 116)
strip.fill(QColor("#23262D"))
p = QPainter(strip)
kinds = ["rect", "ellipse", "arrow", "pen", "text"]
for i, k in enumerate(kinds):
    small = icons.render(k, 21)
    big = icons.render(k, 72)
    p.drawPixmap(20 + i * 96, 8, big)
    p.drawPixmap(20 + i * 96 + 26, 88, small)
p.end()
strip.save(os.path.join(out, "pen_icon_strip.png"))
check("铅笔图标可渲染", not icons.render("pen", 21).isNull())

# ---------------------------------------------------------------- 2. 遮罩层
o = ov.CaptureOverlay("#FF3B30")
o.setGeometry(QRect(-3200, -3200, W, H))
o._shot = make_shot()
o._vgeo = QRect(0, 0, W, H)
o._dpr = 1.0
o.show()
for _ in range(4):
    app.processEvents()

stroke(o, [QPoint(120, 90), QPoint(700, 520)])          # 框选
app.processEvents()
check("框选成功", o._sel.width() > 500, o._sel)

check("工具栏含铅笔按钮", ov.T_PEN in o._bar._tool_buttons)
o._switch_tool(ov.T_PEN)
check("切到手绘工具", o._tool == ov.T_PEN and o._bar._tool_buttons[ov.T_PEN].isChecked())

# 2a) 波浪线（模拟鼠标连续移动）
wave = [QPoint(160 + i * 4, 200 + int(36 * math.sin(i / 5.0))) for i in range(90)]
o._color = QColor("#FF3B30")
o._bar.set_color(o._color)
stroke(o, wave)
app.processEvents()
pen_items = [i for i in o._items if i.kind == ov.T_PEN]
check("产生一条手绘笔迹", len(pen_items) == 1)
if pen_items:
    it = pen_items[0]
    check("采样点数量合理", 20 <= len(it.points) <= len(wave) + 1,
          "%d 点" % len(it.points))
    check("笔迹长度 > 200", ov.pen_length(it.points) > 200,
          round(ov.pen_length(it.points), 1))
    check("颜色取自当前标记色", it.color.name().upper() == "#FF3B30")

# 2b) 竖直角折线
o._color = QColor("#4A86FF")
o._bar.set_color(o._color)
o._switch_tool(ov.T_PEN)
stroke(o, [QPoint(620, 300), QPoint(620, 380), QPoint(680, 380)])
app.processEvents()

# 2c) 只点一下（不应留下孤立点）
before = len(o._items)
send_mouse(o, QEvent.MouseButtonPress, QPoint(300, 460))
send_mouse(o, QEvent.MouseButtonRelease, QPoint(300, 460))
app.processEvents()
check("单击不产生笔迹", len(o._items) == before, "items=%d" % len(o._items))

# 2d) 采样点过密时不重复堆积
o._switch_tool(ov.T_PEN)
it_before = len([i for i in o._items if i.kind == ov.T_PEN])
send_mouse(o, QEvent.MouseButtonPress, QPoint(200, 440))
for _ in range(30):
    send_mouse(o, QEvent.MouseMove, QPoint(200, 440))     # 原地抖动 0 像素
send_mouse(o, QEvent.MouseButtonRelease, QPoint(200, 440))
app.processEvents()
check("原地抖动不产生笔迹", len(o._items) == before,
      "pen=%d" % len([i for i in o._items if i.kind == ov.T_PEN]))

# 2e) 快捷键 P 切工具
o._switch_tool(ov.T_RECT)
o.keyPressEvent(type("E", (), {"key": lambda s: Qt.Key_P,
                               "modifiers": lambda s: Qt.NoModifier})())
check("快捷键 P 切到手绘", o._tool == ov.T_PEN)

# 2f) 手绘笔迹可撤销
o._switch_tool(ov.T_PEN)
stroke(o, [QPoint(200, 470), QPoint(260, 480), QPoint(320, 460)])
app.processEvents()
n = len(o._items)
o._undo()
app.processEvents()
check("撤销移除最后一条手绘", len(o._items) == n - 1)
o._items.append(ov.AnnotItem(ov.T_PEN, QPointF(160, 440), QPointF(160, 440),
                             QColor("#FF9500"), 3))
o._items[-1].points = [QPointF(160, 440), QPointF(220, 455), QPointF(260, 425),
                       QPointF(300, 460)]
app.processEvents()

# ---------------------------------------------------------------- 3. 渲染与导出
for _ in range(4):
    app.processEvents()
o.grab().save(os.path.join(out, "pen_view.png"))
img = o._export()
img.save(os.path.join(out, "pen_export.png"))
check("导出图非空", not img.isNull() and img.width() > 500,
      "%dx%d" % (img.width(), img.height()))

print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
