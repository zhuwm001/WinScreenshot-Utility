# -*- coding: utf-8 -*-
"""回归测试：复制必须"回读验证"，写不进剪贴板时不能谎报成功。

背景：有用户框选完，右下角弹了「已复制到剪贴板」，他去粘贴却只粘出 3 个字
（上一次留下的旧文本）—— 说明剪贴板其实没被写进去，而界面照样报了成功。
剪贴板会被剪贴板管理器、输入法、远程控制、安全软件短暂占用，setImage() 静默
失败时 Qt 不抛异常。所以这里钉住：
  1. 正常情况下写进去后回读一致，日志留痕
  2. 模拟写不进去：三次尝试后改存 PNG，并发出 copy_fallback
  3. 提示文案不能再说"已复制"
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
from PyQt5.QtGui import QColor, QImage, QMouseEvent, QPainter, QPixmap  # noqa: E402
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
    p.fillRect(0, 0, w, 60, QColor("#2B3240"))
    p.end()
    return pm


def send(o, etype, pos):
    if etype == QEvent.MouseButtonPress:
        button, buttons = Qt.LeftButton, Qt.LeftButton
    elif etype == QEvent.MouseMove:
        button, buttons = Qt.NoButton, Qt.LeftButton
    else:
        button, buttons = Qt.LeftButton, Qt.NoButton
    QApplication.sendEvent(o, QMouseEvent(etype, QPointF(pos), QPointF(o.mapToGlobal(pos)),
                                          button, buttons, Qt.NoModifier))


def new_overlay():
    o = ov.CaptureOverlay("#FF3B30")
    o._shot = shot(W, H)
    o._vgeo = QRect(0, 0, W, H)
    o._dpr = 1.0
    o.setGeometry(QRect(0, 0, W, H))
    o.show()
    for _ in range(3):
        app.processEvents()
    send(o, QEvent.MouseButtonPress, QPoint(200, 160))
    send(o, QEvent.MouseMove, QPoint(600, 460))
    send(o, QEvent.MouseButtonRelease, QPoint(600, 460))
    app.processEvents()
    return o


class DeadClipboard:
    """模拟"写不进去"的剪贴板：set 全部无效，image() 永远拿到旧东西。"""

    def __init__(self, stale=None):
        self._stale = stale or QImage()
        self.mimedata = None

    def setImage(self, img):
        return None

    def setPixmap(self, pm):
        return None

    def image(self):
        return self._stale

    def mimeData(self):
        return self.mimedata

    def setMimeData(self, md):
        self.mimedata = md


print("1) 正常写入：回读一致，日志留痕")
got = {}
o = new_overlay()
o.copy_fallback.connect(lambda p: got.setdefault("path", p))
o._copy()
for _ in range(3):
    app.processEvents()
img = QApplication.clipboard().image()
check(not img.isNull(), "剪贴板里确实有图")
check(img.width() > 300 and img.height() > 250,
      "尺寸对得上：%dx%d" % (img.width(), img.height()))
check("path" not in got, "正常情况不会走存文件兜底")
text = "".join(update_log.read(40))
check("剪贴板回读一致" in text, "日志记录了回读一致")
check("复制前剪贴板" in text, "日志记录了复制前的剪贴板内容（便于判断是否旧内容）")

print("2) 写不进去：三次尝试后改存文件，并发出 copy_fallback")
real_clipboard = QApplication.clipboard
QApplication.clipboard = lambda *a, **k: DeadClipboard()
got.clear()
o = new_overlay()
o.copy_fallback.connect(lambda p: got.setdefault("path", p))
o._copy()
app.processEvents()
QApplication.clipboard = real_clipboard
check("path" in got, "copy_fallback 发出了：%s" % got.get("path", "无"))
path = got.get("path", "")
check(bool(path) and path != "?", "给的是一条真实文件路径")
check(os.path.isfile(path) if path and path != "?" else False, "文件真的落盘了")
if path and path != "?" and os.path.isfile(path):
    saved = QImage(path)
    check(not saved.isNull() and saved.width() > 300, "落盘的图能正常打开：%dx%d"
          % (saved.width(), saved.height()))
    os.remove(path)
text = "".join(update_log.read(60))
check("剪贴板回读不一致" in text, "日志记录了回读不一致")
check("已改为存文件" in text, "日志记录了改用文件")

print("3) 提示文案随结果变化")
import inspect  # noqa: E402
src = inspect.getsource(__import__("main"))
check("已存为图片文件" in src, "失败时提示「已存为图片文件」")
check("剪贴板被其他程序占用" in src, "失败时说明了原因")
check('Toast.show_toast("已复制到剪贴板"' in src, "成功时仍然提示已复制")

print()
if fails:
    print("失败 %d 项：" % len(fails))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通过")
