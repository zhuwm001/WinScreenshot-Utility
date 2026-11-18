# -*- coding: utf-8 -*-
"""回归测试：别的程序往遮罩里灌 Ctrl+C 时，截图不能被它复制掉。

背景：某台机器上框选完，工具条刚出现就被"Ctrl+C"结束掉，粘贴出来还是旧内容。
日志显示每次距框选都不到 150ms —— 人手按不了这么快，是别的程序（划词翻译、
剪贴板工具、键鼠宏）在拖拽结束后自己塞了一个 Ctrl+C 进前台窗口。

两道关：
  1. 注入识别 —— 低级钩子带 LLKHF_INJECTED 标志
  2. 时间护栏 —— 框选后 300ms 内的完成类操作一律不理（钩子没装上时的兜底）

用法：
    python tools/test_injected_key.py
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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import hotkey  # noqa: E402
import overlay as ov  # noqa: E402

W, H = 1280, 720
FAILS = []


def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILS.append(name)


def alive(o) -> bool:
    """遮罩还开着吗。复制/取消后会 WA_DeleteOnClose，对象随之失效。"""
    try:
        return bool(o.isVisible())
    except RuntimeError:
        return False


def bar_alive(o) -> bool:
    try:
        return bool(o._bar.isVisible())
    except RuntimeError:
        return False


def shot(w, h):
    pm = QPixmap(w, h)
    pm.setDevicePixelRatio(1.0)
    pm.fill(QColor("#E9EEF6"))
    p = QPainter(pm)
    p.fillRect(0, 0, w, 56, QColor("#2B3240"))
    p.end()
    return pm


def drag(o, a=QPoint(200, 160), b=QPoint(700, 540)):
    for etype, pos, btn, btns in (
            (QEvent.MouseButtonPress, a, Qt.LeftButton, Qt.LeftButton),
            (QEvent.MouseMove, b, Qt.NoButton, Qt.LeftButton),
            (QEvent.MouseButtonRelease, b, Qt.LeftButton, Qt.NoButton)):
        QApplication.sendEvent(o, QMouseEvent(
            etype, QPointF(pos), QPointF(o.mapToGlobal(pos)), btn, btns, Qt.NoModifier))


def press(o, code, mods=Qt.NoModifier):
    QApplication.sendEvent(o, QKeyEvent(QEvent.KeyPress, code, mods))


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


print("1) 注入缓存本身")
hotkey.clear_injected()
check("初始为空", not hotkey.was_injected(0x43))
hotkey._note_injected(0x43)
check("记下 C 之后能查到", hotkey.was_injected(0x43))
check("别的键不受影响", not hotkey.was_injected(0x0D))
check("窗口外查不到", not hotkey.was_injected(0x43, window=-1.0))
hotkey.clear_injected()

print("2) 框选刚结束的 300ms：Ctrl+C 不理，遮罩留住")
o = new_overlay()
drag(o)
check("框选成立、工具条在", o._sel.width() > 400 and bar_alive(o))
press(o, Qt.Key_C, Qt.ControlModifier)
app.processEvents()
check("遮罩还开着（没被复制掉）", alive(o))
check("选区还在", alive(o) and o._sel.width() > 400)

print("3) 过了护栏时间，真的 Ctrl+C 能正常复制")
o._sel_done_ts -= 1.0           # 假装已经过了一秒
press(o, Qt.Key_C, Qt.ControlModifier)
app.processEvents()
check("遮罩正常关闭", not alive(o))

print("4) 注入的 Ctrl+C：即使过了护栏时间也拦住")
hotkey.clear_injected()
o = new_overlay()
drag(o)
o._sel_done_ts -= 1.0
hotkey._note_injected(0x43)      # 模拟别的程序发出来的 C
press(o, Qt.Key_C, Qt.ControlModifier)
app.processEvents()
check("注入的 Ctrl+C 被忽略", alive(o))
check("工具条还在", bar_alive(o))
hotkey.clear_injected()
press(o, Qt.Key_C, Qt.ControlModifier)
app.processEvents()
check("同一时刻人手按的 Ctrl+C 照常生效", not alive(o))

print("5) Esc 只查注入、不查时间：拖错了要能立刻取消")
o = new_overlay()
drag(o)
press(o, Qt.Key_Escape)
app.processEvents()
check("刚框选完按 Esc 立刻取消", not alive(o))

o = new_overlay()
drag(o)
o._sel_done_ts -= 1.0
hotkey.clear_injected()
hotkey._note_injected(0x1B)      # 别的程序塞了个 Esc
press(o, Qt.Key_Escape)
app.processEvents()
check("注入的 Esc 被忽略", alive(o))
hotkey.clear_injected()
try:
    o.close()
except RuntimeError:
    pass
app.processEvents()

print()
if FAILS:
    print("失败 %d 项：" % len(FAILS))
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("全部通过")
