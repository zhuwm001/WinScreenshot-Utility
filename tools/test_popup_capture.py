# -*- coding: utf-8 -*-
"""还原"下拉框抓不到"的根因。

构造一个「失去焦点就自动关闭」的浮层（真实下拉框/右键菜单就是这样），
然后对比两种抓屏时机：

  · 现在（先抓屏，再动窗口）            -> 画面里有浮层
  · 以前（延迟 120/220ms 再抓）         -> 浮层已经消失，抓出来是干净的背景

同时验证分层窗口（Chrome/Electron 下拉框是分层窗口）能被抓图接口拿到。
"""
import ctypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import QEvent, QPoint, QRect, Qt  # noqa: E402
from PyQt5.QtGui import QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

import screenshot as sc  # noqa: E402

COLOR = (200, 30, 200)          # 品红，方便在截图里认出来
POPUP = QRect(500, 320, 260, 180)
ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


class FakeDropdown(QWidget):
    """失去激活就自己关掉的浮层 —— 和真实下拉框、右键菜单的行为一致。"""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)   # 走分层窗口
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setGeometry(POPUP)
        self.hidden_by_deactivate = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.transparent)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(Qt.red)
        # 用纯色填满，方便取色（透明背景 -> 分层窗口）
        from PyQt5.QtGui import QColor
        p.setBrush(QColor(*COLOR))
        p.drawRoundedRect(self.rect(), 8, 8)

    def event(self, e):
        if e.type() in (QEvent.WindowDeactivate, QEvent.FocusOut):
            self.hide()
            self.hidden_by_deactivate = True
        return super().event(e)


class OtherWindow(QWidget):
    """用来"抢走焦点"的普通窗口。"""

    def __init__(self, color="#F3F6FC", title="其他窗口"):
        super().__init__()
        self.setWindowTitle(title)
        self.setGeometry(120, 120, 420, 260)
        self.setStyleSheet("background: %s;" % color)
        self.bg = color


def pump(ms=120):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def sample(shot, vgeo, pt):
    dpr = shot.devicePixelRatio() or 1.0
    x = int((pt.x() - vgeo.x()) * dpr)
    y = int((pt.y() - vgeo.y()) * dpr)
    return shot.toImage().pixelColor(x, y).getRgb()[:3]


def near(a, b, tol=30):
    return all(abs(int(x) - int(y)) <= tol for x, y in zip(a, b))


other = OtherWindow()
other.show()
pump(150)

popup = FakeDropdown()
popup.show()
popup.raise_()
popup.activateWindow()
pump(250)
check("浮层正常显示且未因失焦隐藏", popup.isVisible() and not popup.hidden_by_deactivate,
      "visible=%s" % popup.isVisible())

# ---------- 1) 现在的时机：按快捷键的瞬间就抓 ----------
t0 = time.time()
shot_now, vgeo = sc.grab_virtual_desktop()
grab_cost = (time.time() - t0) * 1000
inside = QRect(POPUP).center()
p_now = sample(shot_now, vgeo, inside)
print("浮层内取色(=按键瞬间抓):", p_now, "| 抓屏耗时 %.1fms" % grab_cost)
check("按键瞬间抓屏，浮层内容在画面里", near(p_now, COLOR), p_now)
check("抓屏足够快（< 60ms，不影响手感）", grab_cost < 60, "%.1fms" % grab_cost)

# ---------- 2) 以前的时机：切换/隐藏窗口之后再过 120~220ms 才抓 ----------
other.raise_()
other.activateWindow()
pump(250)
check("浮层因失去焦点已自动消失（模拟真实下拉框）", not popup.isVisible(),
      "hidden_by_deactivate=%s" % popup.hidden_by_deactivate)

shot_late, vgeo2 = sc.grab_virtual_desktop()
p_late = sample(shot_late, vgeo2, inside)
print("浮层内取色(延迟 250ms 抓):", p_late)
check("延迟抓屏时浮层内容已经没了（旧实现的问题）", not near(p_late, COLOR), p_late)

# ---------- 3) 隐藏自身后补抓：不能把自己的窗口截进去 ----------
GREEN = (40, 200, 90)
self_win = OtherWindow("#28C85A", "自己的窗口")
self_win.setGeometry(760, 520, 300, 200)
self_win.show()
self_win.raise_()
pump(200)

shot, vgeo = sc.grab_virtual_desktop()
p_before = sample(shot, vgeo, self_win.geometry().center())
check("抓图里能看见自己的窗口（补前）", near(p_before, GREEN), p_before)

rect = QRect(self_win.frameGeometry())
self_win.hide()
pump(120)
sc.patch_region(shot, vgeo, rect)
p_after = sample(shot, vgeo, rect.center())
check("隐藏后补抓，自己的窗口已从图里去掉",
      not near(p_after, GREEN), p_after)

# 补抓只影响自己那块，别处内容不该被动过
p_other = sample(shot, vgeo, QRect(POPUP).center())
print("补抓后浮层位置取色:", p_other)

# ---------- 4) 补抓时机：120ms 时补出来的内容要和稳定后一致 ----------
ORANGE = (255, 149, 0)
win3 = OtherWindow("#FF9500", "第三窗口")
win3.setGeometry(200, 620, 320, 200)
win3.show()
win3.raise_()
pump(250)

shot3, vgeo3 = sc.grab_virtual_desktop()
rect3 = QRect(win3.frameGeometry())
win3.hide()
pump(120)                       # 与 main.py 里的补抓延时一致
sc.patch_region(shot3, vgeo3, rect3)
a = sample(shot3, vgeo3, rect3.center())

pump(450)                       # 等画面彻底稳定后再抓一次作为"真相"
truth, vgeo4 = sc.grab_virtual_desktop()
b = sample(truth, vgeo4, rect3.center())
print("120ms 补抓:", a, "| 稳定后:", b)
check("120ms 补抓的内容与稳定后一致", near(a, b, 6), (a, b))

for w in (popup, other, self_win):
    try:
        w.close()
    except Exception:
        pass
pump(100)

print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)
