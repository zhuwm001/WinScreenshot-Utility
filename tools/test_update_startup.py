# -*- coding: utf-8 -*-
"""启动检查的「走真的流程」自检：进程起来 -> 查到新版本 -> 绿箭头亮。

为什么单独写一个：
    「重新打开软件却没提示新版本」这个毛病反复出现，光靠读代码看不出对错，
    必须真的把 AppController 跑起来。这里把网络那一步换成假的（必定返回新版本），
    其余全是真的：配置读写、启动检查、结果文案、主界面绿箭头。

用法：
    python tools/test_update_startup.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt5.QtCore import QObject, QTimer, pyqtSignal       # noqa: E402
from PyQt5.QtNetwork import QLocalServer                  # noqa: E402
from PyQt5.QtWidgets import QApplication                  # noqa: E402

import main as app_main                                   # noqa: E402
import update as up                                       # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


class FakeCfg:
    """内存配置：不碰用户真实的 config.json。"""

    def __init__(self, **kw):
        self.data = {"hotkey": "Ctrl+Shift+F12", "check_update": True,
                     "close_action": "tray", "auto_start": False,
                     "update_last_check": 0, "update_last_result": ""}
        self.data.update(kw)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        pass


class FakeChecker(QObject):
    """假的 UpdateChecker：50 毫秒后直接说「有新版本 9.9.9」。"""

    found = pyqtSignal(object)
    latest = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current = ""

    def check(self, current=up.APP_VERSION, timeout_ms=12000):
        self.current = current
        info = up.ReleaseInfo(
            version="9.9.9", tag="v9.9.9", title="我爱截图 9.9.9",
            notes="- 测试", notes_text="· 测试",
            page_url=up.RELEASE_PAGE,
            asset_name="WoAiJieTu-Setup-v9.9.9.exe",
            asset_url="https://github.com/x/y/releases/download/v9.9.9/a.exe",
            asset_size=1024, digest="sha256:" + "a" * 64,
            published_at="2026-11-17T03:00:00Z", sha256="a" * 64, signed=True,
        )
        QTimer.singleShot(50, lambda: self.found.emit(info))


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def main_():
    app = QApplication(sys.argv)
    print("启动检查全流程自检")

    cfg = FakeCfg()
    app_main.config = cfg
    app_main.UpdateChecker = FakeChecker
    # 真热键可能被占（软件正开着），这里不关心，别把模态设置窗口弹出来挡住
    app_main.AppController.open_settings = lambda self: None
    app_main.Toast.show_toast = staticmethod(lambda *a, **k: None)

    server = QLocalServer()
    ctrl = app_main.AppController(app, server)
    ctrl.start(silent=True)          # 相当于「双击图标、进程真起来了」

    print("\n== 启动 2 秒内应该开查 ==")
    pump(app, 2.6)
    check("启动确实发起了检查", ctrl._check_trigger == app_main.CHECK_STARTUP,
          str(ctrl._check_trigger))
    check("检查时间已写入配置", int(cfg.get("update_last_check") or 0) > 0)

    print("\n== 查到新版本之后 ==")
    pump(app, 0.6)
    info = ctrl._available_update
    check("记住了新版本", info is not None and info.version == "9.9.9",
          str(getattr(info, "version", "")))
    check("主界面绿箭头出现", not ctrl.win.btn_update.isHidden())
    check("箭头提示里有版本号", "9.9.9" in ctrl.win.btn_update.toolTip(),
          ctrl.win.btn_update.toolTip())
    check("设置页那行写了结果",
          cfg.get("update_last_result") == "发现新版本 9.9.9",
          str(cfg.get("update_last_result")))
    check("同一版本只弹一次窗（记住了弹过的版本）",
          ctrl._prompted_version == "9.9.9", ctrl._prompted_version)

    print("\n== 重新打开（已有进程被唤醒）不查更新 ==")
    before = int(cfg.get("update_last_check") or 0)
    ctrl._check_trigger = ""
    app_main.UpdateChecker = FakeChecker
    ctrl._on_second_instance()
    pump(app, 0.3)
    check("唤醒进程不会触发检查", ctrl._check_trigger == "", ctrl._check_trigger)
    check("检查时间没被改", int(cfg.get("update_last_check") or 0) == before)

    print("\n== 关掉自动检查后启动不查 ==")
    cfg.set("check_update", False)
    ctrl2 = app_main.AppController(app, QLocalServer())
    ctrl2.start(silent=True)
    pump(app, 2.6)
    check("关闭后启动不查", ctrl2._check_trigger == app_main.CHECK_TIMER,
          str(ctrl2._check_trigger))

    print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  失败：" + name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main_())
