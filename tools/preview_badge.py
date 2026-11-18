# -*- coding: utf-8 -*-
"""把「发现新版本」的箭头长什么样留成图片，方便人工核对（不联网、不装东西）。

    python tools/preview_badge.py
输出：build/badge/main.png、build/badge/settings.png
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

from PyQt5.QtCore import Qt                       # noqa: E402
from PyQt5.QtWidgets import QApplication          # noqa: E402

import screenshot as sc                           # noqa: E402
from app_config import APP_VERSION, config        # noqa: E402
from main_window import MainWindow                # noqa: E402
from settings_dialog import SettingsDialog        # noqa: E402
from update import ReleaseInfo                    # noqa: E402


def pump(ms=400):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def main():
    sc.set_process_dpi_awareness()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)                  # noqa: F841

    ver = APP_VERSION[:-1] + "99"
    info = ReleaseInfo(version=ver, asset_size=28 * 1024 * 1024,
                       notes_text="· 「发现新版本」绿箭头换成纯箭头样式",
                       published_at="2026-11-17T02:00:00Z", signed=True)

    out = os.path.join(ROOT, "build", "badge")
    os.makedirs(out, exist_ok=True)

    w = MainWindow("Ctrl+Shift+A")
    w.center_on_screen()
    w.show()
    w.set_update_available(info)
    pump()
    w.grab().save(os.path.join(out, "main.png"))

    sd = SettingsDialog(config, lambda s: (True, ""), None, update_info=info)
    sd.show()
    pump()
    sd.set_check_result("发现新版本 %s" % ver)
    pump()
    sd.grab().save(os.path.join(out, "settings.png"))

    # README 用的那张主界面图：默认没有新版本，绿箭头不出现
    w.set_update_available(None)
    pump(200)
    docs = os.path.join(ROOT, "docs", "screenshot.png")
    w.grab().save(docs)
    print("saved to", out, "and", docs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
