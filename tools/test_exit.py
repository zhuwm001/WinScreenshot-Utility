# -*- coding: utf-8 -*-
"""验证关闭行为设置为「直接退出程序」时，点关闭会结束程序。"""
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

config.set("close_action", "exit")

server = QLocalServer()
server.listen("WoAiJieTu.diag.exit")
ctrl = AppController(app, server)
ctrl.start()


def fire():
    print("关闭前进程存活，调用 on_main_close()")
    ctrl.on_main_close()


QTimer.singleShot(400, fire)
QTimer.singleShot(4000, lambda: (print("超时：没有退出"), app.quit()))
rc = app.exec_()
print("事件循环已退出，返回码 =", rc, "| 说明 quit 被正常调用")
