# -*- coding: utf-8 -*-
"""渲染界面到 PNG 用于检查，窗口移到屏幕外不影响桌面。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

# 这台机器的 Python 装在含中文的路径下，Qt 默认找不到插件，显式指定
import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

import main_window  # noqa: E402
import settings_dialog  # noqa: E402
from app_config import config  # noqa: E402

out = os.path.join(ROOT, "build")
OFFSCREEN = (-4000, -4000)


def snap(widget, name, times=6):
    widget.move(*OFFSCREEN)
    widget.show()
    for _ in range(times):
        app.processEvents()
    widget.grab().save(os.path.join(out, name))
    widget.hide()
    print(name, widget.size().width(), "x", widget.size().height())


w = main_window.MainWindow("Ctrl+Alt+A")
snap(w, "preview_main.png")

w2 = main_window.MainWindow("Ctrl+Shift+PrintScreen")
snap(w2, "preview_main2.png")

dlg = settings_dialog.SettingsDialog(config, lambda s: (True, ""))
snap(dlg, "preview_settings.png")

dlg2 = settings_dialog.SettingsDialog(config, lambda s: (False, "快捷键 %s 已被其他程序占用，请重新设置" % s))
dlg2.lbl_error.setText("快捷键 Ctrl+Alt+A 已被其他程序占用，请重新设置")
dlg2.lbl_error.show()
snap(dlg2, "preview_settings_err.png")

print("done")
