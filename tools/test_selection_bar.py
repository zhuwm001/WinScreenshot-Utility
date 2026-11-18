# -*- coding: utf-8 -*-
"""回归测试：框选结束后工具条必须在、且不能用"拖拽卡住"的状态困住用户。

背景：有用户反馈"框选完选区还在，但标记、字体那些按钮全都没出来"。
现场只有一段手机拍的视频，看不出是工具条没绘制，还是松手事件丢了。
所以这里把两种情况都钉住：
  1. 正常松手 -> 选区定下来 + 工具条可见 + 位置在遮罩内
  2. 松手事件丢失（触摸板/远程桌面/被别的窗口抢）-> leaveEvent 兜底收尾
  3. 每一步都写进 update.log，出问题时能靠日志还原现场
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


def send(o, etype, pos=None):
    if etype == QEvent.Leave:
        QApplication.sendEvent(o, QEvent(QEvent.Leave))
        return
    if etype == QEvent.MouseMove:
        button, buttons = Qt.NoButton, Qt.LeftButton
    elif etype == QEvent.MouseButtonPress:
        button, buttons = Qt.LeftButton, Qt.LeftButton
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


print("1) 正常松手")
o = new_overlay()
send(o, QEvent.MouseButtonPress, QPoint(200, 160))
send(o, QEvent.MouseMove, QPoint(720, 560))
send(o, QEvent.MouseButtonRelease, QPoint(720, 560))
app.processEvents()
check(o._state == ov.S_SELECTED, "状态变成 S_SELECTED")
check(o._sel.width() > 400 and o._sel.height() > 300, "选区保留：%s" % o._sel)
check(o._bar.isVisible(), "工具条可见")
bar = o._bar.geometry()
check(QRect(0, 0, W, H).contains(bar), "工具条在遮罩内：%s" % bar)
check(bar.width() >= 380 and bar.height() >= 36, "工具条尺寸正常：%dx%d"
      % (bar.width(), bar.height()))
o.close()
app.processEvents()

print("2) 松手事件丢失（leaveEvent 兜底）")
o = new_overlay()
send(o, QEvent.MouseButtonPress, QPoint(300, 200))
send(o, QEvent.MouseMove, QPoint(800, 500))
check(o._state == ov.S_SELECTING, "拖拽中：选区=%s" % o._sel)
send(o, QEvent.Leave)                      # 没有 release，直接离开
app.processEvents()
check(o._state == ov.S_SELECTED, "离开后自动收尾：状态=%d" % o._state)
check(o._sel.width() > 400, "选区保留：%s" % o._sel)
check(o._bar.isVisible(), "工具条仍然出现")
o.close()
app.processEvents()

print("3) 松手后不按 Esc，直接再拖一次")
o = new_overlay()
send(o, QEvent.MouseButtonPress, QPoint(100, 100))
send(o, QEvent.MouseMove, QPoint(400, 300))
send(o, QEvent.MouseButtonRelease, QPoint(400, 300))
app.processEvents()
send(o, QEvent.MouseButtonPress, QPoint(900, 600))       # 选区外按下
send(o, QEvent.MouseMove, QPoint(1100, 690))
send(o, QEvent.MouseButtonRelease, QPoint(1100, 690))
app.processEvents()
check(o._sel.left() >= 880, "重新框选生效：%s" % o._sel)
check(o._bar.isVisible(), "工具条跟着新选区出现")
o.close()
app.processEvents()

print("4) 日志里留下了现场")
text = "".join(update_log.read(60))
check("框选完成" in text, "记录了框选完成")
check("遮罩关闭" in text, "记录了遮罩关闭")

print()
if fails:
    print("失败 %d 项：" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通过")
