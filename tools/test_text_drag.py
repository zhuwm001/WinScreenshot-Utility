# -*- coding: utf-8 -*-
"""文字标注交互自检（离屏，不依赖真实屏幕）。

覆盖：
    1. 不换行时框宽跟着最长那行走
    2. 拖右边框 -> 宽度变化、文字自动换行、高度变高
    3. 拖左边框 -> 右边界不动、左边跟着走
    4. 拖动文字 -> 位置平移，且压在选区内
    5. 单击（不移动）-> 进入编辑，不是移动
    6. 编辑已定宽的文字 -> 输入框沿用该宽度并自动换行
    7. 中文逐字断行，每行都不超过设定宽度

用法：
    python tools/test_text_drag.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, Qt      # noqa: E402
from PyQt5.QtGui import QColor, QFontMetrics, QMouseEvent, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication                        # noqa: E402

import overlay as ov                                            # noqa: E402

PASS = []
FAIL = []

TEXT = "这是一段比较长的测试文字，用来验证自动换行、拖动和边框缩放是否正常工作"


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def make_overlay():
    img = QPixmap(1200, 800)
    img.fill(QColor("#334455"))
    w = ov.CaptureOverlay(shot=img, vgeo=QRect(0, 0, 1200, 800), show_hint=False)
    w._sel = QRect(60, 60, 1100, 700)
    w._state = ov.S_SELECTED
    w._tool = ov.T_TEXT
    return w


def send(w, typ, pos, button=Qt.LeftButton):
    ev = QMouseEvent(typ, QPointF(pos), button, button, Qt.NoModifier)
    if typ == QEvent.MouseButtonPress:
        w.mousePressEvent(ev)
    elif typ == QEvent.MouseMove:
        w.mouseMoveEvent(ev)
    else:
        w.mouseReleaseEvent(ev)


def new_text(w, x=200, y=200, size=20, wrap=0.0):
    item = ov.AnnotItem(ov.T_TEXT, QPointF(x, y), QPointF(x, y), QColor("#FF3B30"),
                        3, text=TEXT, font_size=size, wrap_w=wrap)
    w._items.append(item)
    return item


def main():
    app = QApplication(sys.argv)
    print("文字标注交互自检")

    w = make_overlay()
    fm = QFontMetrics(ov._font(20))

    # ---------------- 1. 不换行 ----------------
    print("\n== 不换行 ==")
    it = new_text(w)
    r0 = ov.text_rect(it)
    check("未设宽度时框宽 = 最长行 + padding",
          abs(r0.width() - (fm.horizontalAdvance(TEXT) + 10)) <= 1,
          "%.1f" % r0.width())
    check("单行高度", abs(r0.height() - (fm.lineSpacing() + 10)) <= 1,
          "%.1f" % r0.height())

    # ---------------- 2. 拖右边框 ----------------
    print("\n== 拖右边框改宽 ==")
    it2 = new_text(w, y=400)
    right0 = ov.text_rect(it2).right()
    edge = ov.text_rect(it2).right() - 2
    send(w, QEvent.MouseButtonPress, QPoint(int(edge), int(ov.text_rect(it2).center().y())))
    check("按在右边框 -> 进入改宽状态", w._state == ov.S_TEXT_WIDTH, str(w._state))
    send(w, QEvent.MouseMove, QPoint(int(edge) - 300, int(ov.text_rect(it2).center().y())))
    send(w, QEvent.MouseButtonRelease, QPoint(int(edge) - 300, int(ov.text_rect(it2).center().y())))
    r2 = ov.text_rect(it2)
    check("宽度变小", it2.wrap_w > 0 and it2.wrap_w < r0.width(), "wrap=%.1f" % it2.wrap_w)
    check("框宽 = 拖动后的宽度 + 留白", abs(r2.width() - it2.wrap_w - 10) <= 2, "%.1f" % r2.width())
    check("高度变高（换行了）", r2.height() > r0.height() + 5,
          "%.1f -> %.1f" % (r0.height(), r2.height()))
    check("右边界跟着鼠标", abs(r2.right() - right0) <= 2 or r2.right() < right0,
          "%.1f" % r2.right())

    lines = ov.wrap_text_lines(TEXT, fm, it2.wrap_w)
    widest = max(fm.horizontalAdvance(l) for l in lines)
    check("每行都不超过设定宽度", widest <= it2.wrap_w + 1,
          "最宽 %.1f / 限宽 %.1f" % (widest, it2.wrap_w))
    check("确实拆成了多行", len(lines) >= 2, "%d 行" % len(lines))

    # ---------------- 3. 拖左边框 ----------------
    print("\n== 拖左边框 ==")
    it3 = new_text(w, x=420, y=560, wrap=300.0)
    left0 = ov.text_rect(it3).left()
    right_before = ov.text_rect(it3).right()
    send(w, QEvent.MouseButtonPress, QPoint(int(left0) + 1, int(ov.text_rect(it3).center().y())))
    send(w, QEvent.MouseMove, QPoint(int(left0) + 90, int(ov.text_rect(it3).center().y())))
    send(w, QEvent.MouseButtonRelease, QPoint(int(left0) + 90, int(ov.text_rect(it3).center().y())))
    r3 = ov.text_rect(it3)
    check("右边界没动", abs(r3.right() - right_before) <= 2,
          "%.1f -> %.1f" % (right_before, r3.right()))
    check("左边界向内收", r3.left() > left0 + 50, "%.1f -> %.1f" % (left0, r3.left()))
    check("宽度同步变小", abs(r3.width() - it3.wrap_w - 10) <= 2, "%.1f" % r3.width())

    # ---------------- 4. 拖动移动 ----------------
    print("\n== 拖动移动 ==")
    it4 = new_text(w, x=200, y=200, wrap=260.0)
    p1 = QPointF(it4.p1)
    c = ov.text_rect(it4).center()
    send(w, QEvent.MouseButtonPress, QPoint(int(c.x()), int(c.y())))
    check("按住文字不立刻移动", w._state == ov.S_TEXT_PRESS, str(w._state))
    send(w, QEvent.MouseMove, QPoint(int(c.x()) + 4, int(c.y()) + 2))
    check("移动超过阈值 -> 拖动中", w._state == ov.S_TEXT_MOVE, str(w._state))
    send(w, QEvent.MouseMove, QPoint(int(c.x()) + 60, int(c.y()) + 40))
    send(w, QEvent.MouseButtonRelease, QPoint(int(c.x()) + 60, int(c.y()) + 40))
    check("位置跟着平移", abs(it4.p1.x() - p1.x() - 60) <= 2 and abs(it4.p1.y() - p1.y() - 40) <= 2,
          "(%.0f, %.0f) -> (%.0f, %.0f)" % (p1.x(), p1.y(), it4.p1.x(), it4.p1.y()))
    check("松手后回到选中态", w._state == ov.S_SELECTED, str(w._state))
    check("拖动不改宽度", abs(it4.wrap_w - 260) <= 2, "%.1f" % it4.wrap_w)

    # ---------------- 5. 拖出选区被挡住 ----------------
    print("\n== 边界限制 ==")
    c = ov.text_rect(it4).center()
    send(w, QEvent.MouseButtonPress, QPoint(int(c.x()), int(c.y())))
    send(w, QEvent.MouseMove, QPoint(int(c.x()) + 5000, int(c.y()) + 5000))
    send(w, QEvent.MouseButtonRelease, QPoint(int(c.x()) + 5000, int(c.y()) + 5000))
    r4 = ov.text_rect(it4)
    check("不会拖出选区", w._sel.contains(r4.toRect().topLeft())
          and r4.right() <= w._sel.right() + 1 and r4.bottom() <= w._sel.bottom() + 1,
          "rect=(%.0f,%.0f,%.0f,%.0f)" % (r4.left(), r4.top(), r4.width(), r4.height()))

    # ---------------- 6. 单击进入编辑 ----------------
    print("\n== 单击进入编辑 ==")
    it5 = new_text(w, x=150, y=150, wrap=200.0)
    c = ov.text_rect(it5).center()
    send(w, QEvent.MouseButtonPress, QPoint(int(c.x()), int(c.y())))
    send(w, QEvent.MouseButtonRelease, QPoint(int(c.x()), int(c.y())))
    check("单击打开输入框", w._text_edit is not None)
    if w._text_edit is not None:
        g = w._text_edit.geometry()
        check("输入框沿用已定宽度", abs(g.width() - (int(it5.wrap_w) + 8)) <= 3, "%d" % g.width())
        check("输入框开了自动换行",
              w._text_edit.lineWrapMode() != ov.QTextEdit.NoWrap,
              str(w._text_edit.lineWrapMode()))
        single = fm.lineSpacing() + 10
        check("输入框按换行后高度撑开", g.height() > single + 10,
              "%d > %d" % (g.height(), single))
        w._commit_text()
    check("编辑结束宽度没丢", abs(it5.wrap_w - 200) <= 2, "%.1f" % it5.wrap_w)
    check("内容保持完整", it5.text == TEXT)

    # ---------------- 7. 光标提示 ----------------
    print("\n== 光标提示 ==")
    c = ov.text_rect(it5).center()
    w._update_cursor(QPoint(int(c.x()), int(c.y())))
    check("文字中间显示移动光标", w.cursor().shape() == Qt.SizeAllCursor,
          str(w.cursor().shape()))
    w._update_cursor(QPoint(int(ov.text_rect(it5).left()), int(c.y())))
    check("边框上显示横向缩放光标", w.cursor().shape() == Qt.SizeHorCursor,
          str(w.cursor().shape()))
    w._update_cursor(QPoint(20, 20))
    check("空白处恢复十字光标", w.cursor().shape() == Qt.CrossCursor,
          str(w.cursor().shape()))

    # ---------------- 8. 渲染不报错 ----------------
    print("\n== 渲染 ==")
    img = QPixmap(1200, 800)
    img.fill(QColor("#222222"))
    w.render(img)
    check("带文字的遮罩能正常渲染", not img.isNull() and img.width() == 1200)

    print("\n通过 %d，失败 %d" % (len(PASS), len(FAIL)))
    if FAIL:
        for n in FAIL:
            print("  失败：" + n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
