# -*- coding: utf-8 -*-
"""回归测试：工具条"存在"必须等于"屏幕上看得见"。

背景：有用户框选完只看到选区、看不到任何按钮，随后右下角弹出「已复制到剪贴板」——
说明工具条其实在、也点得到（他正好点到了最右边的保存并复制），只是没被画出来。
根因是工具条作为**子控件**用了 WA_TranslucentBackground（Qt 只保证顶层窗口支持），
个别机器合成失败就整块不画。这里钉住四件事：
  1. 浮动条不再依赖透明属性，圆角靠遮罩，底色铺满不透明
  2. 自检靠采样屏幕像素，而不是 visibleRegion（后者只反映裁剪，抓不到本故障）
  3. 采到"没画出来"时自动升级成独立窗口，且位置不跳
  4. 升级后的窗口不抢焦点、遮罩关闭时会被收拾干净
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

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import overlay as ov  # noqa: E402
import update_log  # noqa: E402

W, H = 1280, 720
fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def shot(w, h):
    pm = QPixmap(w, h)
    pm.setDevicePixelRatio(1.0)
    pm.fill(QColor("#E9EEF6"))
    p = QPainter(pm)
    p.fillRect(0, 0, w, 56, QColor("#2B3240"))
    p.end()
    return pm


def send(o, etype, pos):
    if etype == QEvent.MouseButtonPress:
        button, buttons = Qt.LeftButton, Qt.LeftButton
    elif etype == QEvent.MouseMove:
        button, buttons = Qt.NoButton, Qt.LeftButton
    else:
        button, buttons = Qt.LeftButton, Qt.NoButton
    e = QMouseEvent(etype, QPointF(pos), QPointF(o.mapToGlobal(pos)),
                    button, buttons, Qt.NoModifier)
    QApplication.sendEvent(o, e)


def new_overlay():
    o = ov.CaptureOverlay("#FF3B30")
    o._shot = shot(W, H)
    o._vgeo = QRect(0, 0, W, H)
    o._dpr = 1.0
    o.setGeometry(QRect(0, 0, W, H))
    o.show()
    for _ in range(3):
        app.processEvents()
    return o


def select(o, a=(200, 160), b=(720, 560)):
    send(o, QEvent.MouseButtonPress, QPoint(*a))
    send(o, QEvent.MouseMove, QPoint(*b))
    send(o, QEvent.MouseButtonRelease, QPoint(*b))
    app.processEvents()


print("1) 浮动条不再依赖子控件透明合成")
o = new_overlay()
check(not o._bar.testAttribute(Qt.WA_TranslucentBackground),
      "工具条没有 WA_TranslucentBackground")
select(o)
bar = o._bar
check(not bar.mask().isEmpty(), "圆角靠遮罩实现：mask 非空（%d 个矩形）"
      % len(bar.mask().rects()))
img = bar.grab().toImage()
mid = img.pixelColor(img.width() // 2, img.height() // 2)
check(mid.alpha() == 255, "按钮区不透明：alpha=%d" % mid.alpha())
# 按钮之间才是底色：取顶部内边距那一条（工具栏上边距 4px，没有按钮）
bg = img.pixelColor(img.width() // 2, 2)
check(bg.alpha() == 255 and bg.red() < 60 and bg.green() < 60,
      "底色铺满且是深色：%s alpha=%d" % (bg.name(), bg.alpha()))
o.close()
app.processEvents()

print("2) 自检采到深色 -> 判定已绘制，不做任何升级")
o = new_overlay()
select(o)
real = ov.CaptureOverlay._probe_bar_luminance
o._probe_bar_luminance = lambda: 26.0
o._audit_bar()
check(o._bar_promoted is False, "亮度 26 时不升级成独立窗口")
check("工具条自检通过" in "".join(update_log.read(20)), "日志记录了自检通过")
o.close()
app.processEvents()

print("3) 自检采到亮色（=没画出来）-> 升级成独立窗口，位置不跳")
o = new_overlay()
select(o)
before = o.mapToGlobal(o._bar.geometry().topLeft())
o._probe_bar_luminance = lambda: 200.0
o._audit_bar()
app.processEvents()
check(o._bar_promoted is True, "亮度 200 时升级成独立窗口")
check(o._bar.isWindow(), "工具条真的变成顶层窗口")
after = o._bar.pos()
check(before == after, "位置不跳：%s -> %s" % (before, after))
check(o._bar.windowFlags() & Qt.WindowDoesNotAcceptFocus,
      "独立窗口不抢焦点（键盘仍归遮罩）")
check(o._sel.width() > 400, "选区没有被破坏：%s" % o._sel)
text = "".join(update_log.read(30))
check("工具条未绘制出来" in text, "日志记录了未绘制与回退")
o._audit_bar()                                  # 再查一次不该重复升级/崩
check(o._bar_promoted is True, "重复自检不会来回折腾")
o.close()
app.processEvents()
o._bar_promoted = False                          # close 已清理，复位后不再访问
check(not o._bar_promoted, "遮罩关闭后收拾了独立窗口")

print("4) 升级后色板同样走独立窗口，点颜色不崩")
o = new_overlay()
select(o)
o._probe_bar_luminance = lambda: 200.0
o._audit_bar()
o._pick_color()
app.processEvents()
check(o._palette_promoted is True, "色板跟着升级成独立窗口")
check(o._palette.isWindow(), "色板是顶层窗口")
o._on_palette_color(QColor("#34C759"))
app.processEvents()
check(o._color.name().upper() == "#34C759", "选色仍然生效：%s" % o._color.name())
o._probe_bar_luminance = real
o.close()
app.processEvents()

print("5) 独立窗口也画不出来 -> 退到遮罩内嵌绘制")
o = new_overlay()
select(o)
o._probe_bar_luminance = lambda: 200.0
o._audit_bar()                      # 第一次：升级成独立窗口
o._audit_bar()                      # 第二次：还不行，改由遮罩自己画
app.processEvents()
check(o._bar_promoted is True, "先升级成独立窗口")
check(o._bar_raster is not None, "再退到遮罩内嵌绘制（有图）")
o.repaint()
app.processEvents()
img = o.grab().toImage()
r = o._bar_rect_overlay()
c = img.pixelColor(r.center().x(), r.top() + 3)   # 顶部内边距那一条，避开按钮
check(c.lightness() < 90, "遮罩里画出了深色工具条：%s" % c.name())
check("工具条改用遮罩内嵌绘制" in "".join(update_log.read(30)),
      "日志记录了内嵌绘制")
o.close()
app.processEvents()

print("6) 正常情况下屏幕采样确实能读到深色工具条")
o = new_overlay()
select(o)
lum = o._probe_bar_luminance()
print("       实测亮度 = %s" % ("取不到" if lum is None else "%.0f" % lum))
check(lum is None or lum <= ov.BAR_DARK_LUMA,
      "实测亮度不高于阈值 %d（本机工具条确实画出来了）" % ov.BAR_DARK_LUMA)
o.close()
app.processEvents()

print()
if fails:
    print("失败 %d 项：" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通过")
