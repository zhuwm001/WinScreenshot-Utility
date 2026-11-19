# -*- coding: utf-8 -*-
"""设置页开着的时候能不能截图（回归测试）。

出过的 bug：设置页用 exec_() 打开，那是**应用级模态**，遮罩照样出现，但 Qt 把
鼠标事件全拦在模态窗口那边 —— 用户看到的是"灰了但框不动"，按 Esc 把设置关掉
之后又能框了。所以这个测试盯三件事：

  1. 设置页打开后没有模态窗口（activeModalWidget() 必须是 None）
  2. 设置页开着也能起截图：遮罩建得起来、能收到鼠标
  3. 截图期间设置页被藏起来（配置了「截图时隐藏窗口」），结束后放回来

用法：
    python tools/test_settings_capture.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# 配置与日志都写临时目录，别碰真实的 %APPDATA%
_TMP = tempfile.mkdtemp(prefix="setcap-")
os.environ["APPDATA"] = _TMP

import qt_env  # noqa: E402

qt_env.setup()

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtNetwork import QLocalServer  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import main as m  # noqa: E402
from app_config import config  # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def pump(ms=250):
    QTest.qWait(ms)


config.set("hide_self", True)
config.save()

server = QLocalServer()
ctrl = m.AppController(app, server)

print("1) 设置页不是模态窗口")
ctrl.open_settings()
pump(200)
dlg = ctrl._settings_dlg
check("设置页已打开", dlg is not None and dlg.isVisible())
check("没有应用级模态窗口", QApplication.activeModalWidget() is None,
      str(QApplication.activeModalWidget()))
check("窗口自身不是模态", not dlg.isModal())

print("2) 设置页开着也能起截图")
ctrl.start_capture()
pump(400)
check("遮罩已建立", ctrl.overlay is not None)
check("截图期间设置页被藏起来", not dlg.isVisible())
check("仍然没有模态窗口", QApplication.activeModalWidget() is None)

if ctrl.overlay is not None:
    ov = ctrl.overlay.overlays[0]
    # 直接给遮罩发鼠标事件：模态在的时候这些事件会被 Qt 拦掉，
    # 换成非模态后必须能到控件上，框选状态才会从 IDLE 变成 SELECTING。
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, QPoint(60, 60))
    pump(60)
    QTest.mouseMove(ov, QPoint(220, 180))
    pump(60)
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, QPoint(220, 180))
    pump(150)
    sel = getattr(ov, "_sel", None)
    check("鼠标能把选区拉出来", sel is not None and sel.width() > 100 and sel.height() > 60,
          "%s" % (sel,))
    ov._cancel()
    pump(250)

print("3) 截图结束后设置页回来了")
check("设置页重新可见", dlg.isVisible())
check("遮罩已收尾", ctrl.overlay is None)

print("4) 关掉设置页：热键恢复、不留模态残留")
dlg.reject()
pump(150)
check("控制器不再持有设置页", ctrl._settings_dlg is None)
check("没有残留模态窗口", QApplication.activeModalWidget() is None)

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "；".join(FAIL)))
    sys.exit(1)
print("全部通过（%d 项）" % len(PASS))
