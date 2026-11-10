# -*- coding: utf-8 -*-
"""把设置对话框渲染成图片，方便检查"Alt 组合键"这条说明的排版。"""
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

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QFont  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

from app_config import config  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

for label, value in (("settings_ctrl", "Ctrl+Shift+Z"), ("settings_alt", "Alt+Z")):
    dlg = SettingsDialog(config, lambda seq: (True, ""), None)
    dlg.hotkey_edit.set_value(value)
    dlg.resize(540, dlg.height())
    dlg.setFont(QFont("Microsoft YaHei UI", 9))
    dlg.show()
    for _ in range(8):
        app.processEvents()
    dlg.adjustSize()
    dlg.resize(540, dlg.height())
    for _ in range(8):
        app.processEvents()
    out = os.path.join(ROOT, "build", "%s.png" % label)
    dlg.grab().save(out)
    print(out, dlg.size().width(), "x", dlg.size().height())
    dlg.close()
