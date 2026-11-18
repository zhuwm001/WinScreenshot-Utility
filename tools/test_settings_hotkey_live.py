# -*- coding: utf-8 -*-
"""回归测试：设置窗口开着的时候，截图热键必须还能用。

背景：别人反馈「软件打开了设置界面就没法截图了」。根因是 open_settings()
里为了录快捷键，把全局热键在整个 dlg.exec_() 期间都停掉了 —— 录键只需要
停几百毫秒，却被放大成"设置页开着就一直是死的"。

这份测试盯两件事：
    1. 只有「正在录快捷键」的那一刻发出 True，其余时间都是 False
    2. 录完 / 取消录制 / 焦点移走，都要把 True 收回去（否则热键永久失效）

用法：
    python tools/test_settings_hotkey_live.py
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

from PyQt5.QtCore import QEvent, Qt  # noqa: E402
from PyQt5.QtGui import QFocusEvent, QKeyEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import app_config  # noqa: E402
from app_config import DEFAULTS  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILS.append(name)


def make_dialog(cfg):
    return SettingsDialog(cfg, lambda seq: True, None,
                          update_info=None, probe_hotkey=lambda seq: None)


def key(widget, code, mods):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, code, mods))


print("1) 平时不发信号（等于热键保持可用）")
cfg = dict(DEFAULTS)
cfg["hotkey"] = "Ctrl+Shift+V"
dlg = make_dialog(cfg)
events = []
dlg.hotkey_recording.connect(events.append)
check("构造完没有发出任何启用/禁用", events == [], events)

print("2) 点进输入框 -> 只在录制期间禁用")
dlg.hotkey_edit.begin_recording()
check("开始录制时发一次 True", events == [True], events)
dlg.hotkey_edit.begin_recording()          # 重复调用不应重复发
check("重复开始不重复发", events == [True], events)

print("3) 录到新组合 -> 立刻收回禁用")
key(dlg.hotkey_edit, Qt.Key_T, Qt.ControlModifier)
check("录完发 False", events == [True, False], events)
check("录到的组合正确", dlg.hotkey_edit.value() == "Ctrl+T", dlg.hotkey_edit.value())

print("4) 取消录制（Esc / 焦点移走）也要收回")
dlg.hotkey_edit.begin_recording()
key(dlg.hotkey_edit, Qt.Key_Escape, Qt.NoModifier)
check("Esc 后回到 False", events == [True, False, True, False], events)

print("5) 焦点移走同样收回")
dlg.hotkey_edit.begin_recording()
# offscreen 平台下控件拿不到真焦点，直接投递失焦事件（走到的是同一条代码路径）
dlg.hotkey_edit.focusOutEvent(QFocusEvent(QEvent.FocusOut))
check("失焦后回到 False", events[-1] is False, events)

dlg.close()
app.processEvents()

print()
if FAILS:
    print("失败 %d 项：" % len(FAILS))
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("全部通过")
