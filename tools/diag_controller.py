# -*- coding: utf-8 -*-
"""直接验证控制器处理关闭请求的行为。"""
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

from PyQt5.QtCore import Qt, QTimer  # noqa: E402
from PyQt5.QtNetwork import QLocalServer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from app_config import config  # noqa: E402
from main import AppController  # noqa: E402

print("close_action =", config.get("close_action"), "| hide_self =", config.get("hide_self"))

server = QLocalServer()
server.listen("WoAiJieTu.diag.close")
ctrl = AppController(app, server)
ctrl.start()
for _ in range(5):
    app.processEvents()
print("启动后可见:", ctrl.win.isVisible())


def step():
    print("调用 on_main_close()")
    ctrl.on_main_close()
    for _ in range(6):
        app.processEvents()
    print("关闭后可见:", ctrl.win.isVisible(), "| 托盘可见:", ctrl.tray.isVisible())

    print("再次显示")
    ctrl.show_main()
    for _ in range(5):
        app.processEvents()
    print("show_main 后可见:", ctrl.win.isVisible())

    print("emit close_requested（模拟点 X）")
    ctrl.win.close_requested.emit()
    for _ in range(6):
        app.processEvents()
    print("结果可见:", ctrl.win.isVisible())


QTimer.singleShot(500, step)
QTimer.singleShot(2500, app.quit)
app.exec_()
