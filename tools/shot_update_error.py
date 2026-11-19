# -*- coding: utf-8 -*-
"""把「检查更新失败」这一屏渲染出来看看，确认新文案放得下、不挤。

用法：python tools/shot_update_error.py
产物：build/preview_update_error.png / build/preview_update_error_pac.png
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402

qt_env.setup()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import update_dialog as ud  # noqa: E402

CASES = [
    ("preview_update_error.png",
     "连接 GitHub 超时（12 秒无响应）。请确认网络畅通、代理已开启；"
     "如果代理按域名分流，请让 github.com 与 release-assets.githubusercontent.com "
     "都走代理。"),
    ("preview_update_error_pac.png",
     "连接 GitHub 超时（12 秒无响应）。系统启用了代理自动配置脚本（PAC），"
     "本程序用不了它，请把代理软件切换成「系统代理」或「TUN / 全局」模式后重试。"),
]

out = os.path.join(ROOT, "build")
from PyQt5.QtTest import QTest  # noqa: E402

for name, msg in CASES:
    dlg = ud.UpdateDialog(message=msg, mode=ud.MODE_ERROR)
    dlg.set_error(msg)
    dlg.show()
    dlg.raise_()
    QTest.qWait(400)                  # 等字体加载与首帧绘制，否则 grab 到的是空壳
    app.processEvents()
    path = os.path.join(out, name)
    dlg.grab().save(path)
    box = dlg.box
    print("%-34s 弹窗 %dx%d  正文框 %dx%d  需要 %d px"
          % (name, dlg.width(), dlg.height(), box.width(), box.height(),
             box.document().size().height()))
    dlg.close()
