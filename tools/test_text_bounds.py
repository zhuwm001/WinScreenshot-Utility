# -*- coding: utf-8 -*-
"""回归测试：文字不能跑出选区。

背景：有用户框选一块区域后打字，文字框按内容自然宽度一直往右长，超出了选区；
截图是按选区裁剪的，超出去的部分直接被切掉 —— 看到的是"字写好了却截不全"。
这里钉住四条：
  1. 打到选区右边界时输入框就地换行，不越界
  2. 落字后文字包围盒完整落在选区内
  3. 在选区底部打字时，整段文字被顶回选区内
  4. 先把选区缩小，已写好的文字会被收回来（换行/上移）
顺带确认导出尺寸始终等于选区尺寸，不会因为标注出界而变大变小。
"""
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

from PyQt5.QtCore import QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFontMetrics, QImage, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import overlay as ov  # noqa: E402

TEXT = "这是一段很长的测试文字用来验证是否会超出选区的右边界导致截图被裁掉"
fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def make_overlay(sel=QRect(60, 60, 400, 300)):
    img = QPixmap(1000, 700)
    img.fill(QColor("#334455"))
    w = ov.CaptureOverlay(shot=img, vgeo=QRect(0, 0, 1000, 700), show_hint=False)
    w._sel = QRect(sel)
    w._state = ov.S_SELECTED
    w._tool = ov.T_TEXT
    w.show()
    for _ in range(2):
        app.processEvents()
    return w


def type_text(w, x, y, text=TEXT, size=20):
    """模拟：在 (x,y) 点一下 -> 打字 -> 提交。"""
    w._start_text(QPoint(x, y), None)
    edit = w._text_edit
    edit.setPlainText(text)
    w._fit_text_edit()
    app.processEvents()
    return edit


print("1) 靠近右边界打字：输入框不越界、就地换行")
w = make_overlay()
sel = QRect(w._sel)
edit = type_text(w, sel.right() - 40, sel.top() + 40)
g = edit.geometry()
check(g.right() <= sel.right() + 1,
      "输入框右边没有超出选区：edit.right=%d sel.right=%d" % (g.right(), sel.right()))
check(edit.lineWrapMode() == edit.WidgetWidth, "自动切成按宽度换行")
check(g.height() > QFontMetrics(ov._font(20)).lineSpacing() * 1.5,
      "换行后输入框变高：%d" % g.height())
w._commit_text()
app.processEvents()
it = w._items[-1]
r = ov.text_rect(it)
check(r.right() <= sel.right() - 3,
      "落字后包围盒右边在选区内：%.1f <= %d" % (r.right(), sel.right() - 3))
check(it.wrap_w > 0, "自动记下了换行宽度：%.1f" % it.wrap_w)

img = w._export()
check(img.width() == sel.width() and img.height() == sel.height(),
      "导出尺寸仍等于选区：%dx%d" % (img.width(), img.height()))
w.close()
app.processEvents()

print("2) 在选区底部打字：整段被顶回选区内")
w = make_overlay()
sel = QRect(w._sel)
type_text(w, sel.left() + 20, sel.bottom() - 30)
w._commit_text()
app.processEvents()
it = w._items[-1]
r = ov.text_rect(it)
check(r.bottom() <= sel.bottom() - 3,
      "包围盒底边在选区内：%.1f <= %d" % (r.bottom(), sel.bottom() - 3))
check(r.top() >= sel.top() - 1, "上移之后依然在选区内：%.1f" % r.top())
w.close()
app.processEvents()

print("3) 先写字再缩小选区：文字被收回来")
w = make_overlay(QRect(60, 60, 700, 400))
it = ov.AnnotItem(ov.T_TEXT, QPointF(80, 80), QPointF(80, 80), QColor("#FF3B30"),
                  3, text=TEXT, font_size=20)
w._items.append(it)
w._sel = QRect(60, 60, 220, 200)       # 缩小成窄条
w._clamp_text_items()
app.processEvents()
r = ov.text_rect(it)
check(r.right() <= w._sel.right() - 3,
      "文字右边收进新选区：%.1f <= %d" % (r.right(), w._sel.right() - 3))
check(r.bottom() <= w._sel.bottom() - 3,
      "文字底边收进新选区：%.1f <= %d" % (r.bottom(), w._sel.bottom() - 3))
check(it.wrap_w > 0, "自动换行宽度被压缩：%.1f" % it.wrap_w)
w.close()
app.processEvents()

print("4) 其他标注出界：导出尺寸不受影响")
w = make_overlay()
sel = QRect(w._sel)
a = ov.AnnotItem(ov.T_ARROW, QPointF(sel.left() + 10, sel.top() + 10),
                 QPointF(sel.right() + 300, sel.bottom() + 300),
                 QColor("#FF3B30"), 3)
w._items.append(a)
img = w._export()
check(img.width() == sel.width() and img.height() == sel.height(),
      "箭头拖到选区外，导出仍是 %dx%d" % (img.width(), img.height()))
p = img.pixelColor(img.width() - 2, img.height() // 2)
check(True, "导出取样不报错：%s" % p.name())
w.close()
app.processEvents()

print()
if fails:
    print("失败 %d 项：" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通过")
