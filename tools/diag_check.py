# -*- coding: utf-8 -*-
"""跑一次真实的 UpdateChecker，看它走哪条通道、各花多久。

只打印信号和耗时，不改任何状态；用来验证「超时→备用通道」这条兜底还在。
"""
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

import qt_env  # noqa: E402

qt_env.setup()

from PyQt5.QtCore import QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from update import UpdateChecker  # noqa: E402

app = QApplication(sys.argv)
t0 = time.time()


def show(kind):
    return lambda arg: print("  [%.2fs] %s: %s"
                             % (time.time() - t0, kind,
                                getattr(arg, "version", arg)))


checker = UpdateChecker()
checker.found.connect(show("found"))
checker.latest.connect(show("latest"))
checker.failed.connect(show("failed"))
checker.check()

QTimer.singleShot(60000, app.quit)
app.exec_()
