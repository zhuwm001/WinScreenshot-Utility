# -*- coding: utf-8 -*-
"""设置页开着的时候能不能截图（回归测试）。

出过两次问题，方向正好相反：

  v1.3.2：设置页用 exec_() 打开，那是**应用级模态**，遮罩照样出现，但 Qt 把
          鼠标事件全拦在模态窗口那边 —— 用户看到的是"灰了但框不动"。
  v1.3.3：改成非模态解决了框不动，但设置页变成无父的独立窗口，
          关掉主窗口它还在，而且截图时会被一起藏掉 —— 用户就截不到设置页本身。

现在的约定是：**窗口模态**（只挡主窗口，不挡遮罩）+ 截图期间设置页保持可见。
这个测试盯四件事：

  1. 设置页是 WindowModal，且父窗口是主界面
  2. 遮罩能收到鼠标（框选状态真的会变），说明没被模态拦住
  3. 截图期间设置页**仍然可见**（用户要截的就是它）
  4. 关掉设置页后热键恢复、不留模态残留

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

print("1) 设置页是窗口模态，挂在主界面下面")
ctrl.open_settings()
pump(200)
dlg = ctrl._settings_dlg
check("设置页已打开", dlg is not None and dlg.isVisible())
check("窗口模态是 WindowModal", dlg.windowModality() == Qt.WindowModal,
      str(dlg.windowModality()))
check("父窗口是主界面", dlg.parent() is ctrl.win, str(dlg.parent()))

print("2) 设置页开着也能框选")
ctrl.start_capture()
pump(400)
check("遮罩已建立", ctrl.overlay is not None)
check("截图期间设置页仍然可见", dlg.isVisible())

if ctrl.overlay is not None:
    ov = ctrl.overlay.overlays[0]
    # 直接给遮罩发鼠标事件：应用级模态时这些事件会被 Qt 拦掉，
    # 窗口模态下遮罩不是父窗口的子窗口，必须能到控件上。
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

print("3) 截图结束后设置页还在原处")
check("设置页仍然可见", dlg.isVisible())
check("遮罩已收尾", ctrl.overlay is None)

print("4) 关掉设置页：热键恢复、不留模态残留")
dlg.reject()
pump(150)
check("控制器不再持有设置页", ctrl._settings_dlg is None)
check("没有残留模态窗口", QApplication.activeModalWidget() is None,
      str(QApplication.activeModalWidget()))

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "；".join(FAIL)))
    sys.exit(1)
print("全部通过（%d 项）" % len(PASS))
