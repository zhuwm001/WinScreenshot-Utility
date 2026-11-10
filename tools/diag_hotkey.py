# -*- coding: utf-8 -*-
"""诊断：Qt 原生事件过滤器能否收到线程消息 WM_HOTKEY。"""
import ctypes
import os
import sys
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

user32 = ctypes.WinDLL("user32", use_last_error=True)


class Spy(QAbstractNativeEventFilter):
    """不继承 QObject，只实现原生事件过滤器。"""

    def __init__(self):
        super().__init__()
        self.total = 0
        self.hotkeys = 0

    def nativeEventFilter(self, event_type, message):
        self.total += 1
        try:
            m = wintypes.MSG.from_address(int(message))
            if m.message == 0x0312:
                self.hotkeys += 1
                print("  >> 收到 WM_HOTKEY wParam=", m.wParam)
        except Exception as exc:
            print("  parse err", exc)
        return False, 0


spy = Spy()
app.installNativeEventFilter(spy)
w = QWidget()
w.setGeometry(-3000, -3000, 200, 120)
w.show()

# 注册热键
ok = user32.RegisterHotKey(None, 0x1234, 0x0002 | 0x0001, ord("A"))
print("RegisterHotKey:", ok, "err:", ctypes.get_last_error())

tid = ctypes.windll.kernel32.GetCurrentThreadId()
print("thread id:", tid)


def fire():
    r = user32.PostThreadMessageW(tid, 0x0312, 0x1234, 0)
    print("PostThreadMessage:", r, "err:", ctypes.get_last_error())


QTimer.singleShot(200, fire)
QTimer.singleShot(900, app.quit)
app.exec_()

print("native events:", spy.total, "hotkey events:", spy.hotkeys)
user32.UnregisterHotKey(None, 0x1234)
