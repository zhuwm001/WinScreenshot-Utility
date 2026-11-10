# -*- coding: utf-8 -*-
"""渲染右下角消息提示，检查外观、位置与自动消失。"""
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

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QToolButton  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

from toast import Toast  # noqa: E402

out = os.path.join(ROOT, "build")

t1 = Toast.show_toast("快捷键不可用", "快捷键 Ctrl+Alt+A 已被其他程序占用，请重新设置。",
                      kind="warn", timeout=3000)
for _ in range(20):
    app.processEvents()
    time.sleep(0.02)

t2 = Toast.show_toast("已复制到剪贴板", "可直接到其他窗口按 Ctrl+V 粘贴。", kind="check")
for _ in range(20):
    app.processEvents()
    time.sleep(0.02)

t3 = Toast.show_toast("已隐藏到托盘", "程序在桌面右下角继续运行，双击托盘图标可重新打开。", kind="info")
for _ in range(40):
    app.processEvents()
    time.sleep(0.02)

scr = app.primaryScreen()
geo = scr.availableGeometry()
img = scr.grabWindow(0, geo.right() - 420, geo.bottom() - 300, 420, 300)
img.save(os.path.join(out, "toast_stack.png"))
print("toast windows:", [(t.isVisible(), t.geometry().getRect()) for t in Toast._alive])

# 点右上角关闭按钮（模拟真实点击）
btn = t3.findChild(QToolButton, "toastClose")
print("close button found:", btn is not None)
QTest.mouseClick(btn, Qt.LeftButton)
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
print("after clicking close, alive:", len(Toast._alive))

# 等 3 秒自动消失
deadline = time.time() + 4.5
while time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)
print("after timeout alive:", len(Toast._alive))
print("done")
