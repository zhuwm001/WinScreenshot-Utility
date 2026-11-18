# -*- coding: utf-8 -*-
"""诊断：设置窗口在「没有配置文件」的机器上，各选项的实际显示与宽度。

用途：复现「别人装完打开设置，自动检查更新没勾上」这类问题。
做法：把 APPDATA 指到临时目录（等价于全新安装、没有 config.json），
构造真实的 SettingsDialog，量出每个控件的勾选状态和可视位置。

用法：
    python tools/diag_settings.py            # 100%
    set QT_SCALE_FACTOR=1.5 && python tools/diag_settings.py
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

# 必须在 import app_config 之前落定：config 是模块级单例，路径在导入时确定
_tmp = tempfile.mkdtemp(prefix="woaijietu_diag_")
os.environ["APPDATA"] = _tmp

from PyQt5.QtCore import QPoint, Qt                            # noqa: E402
from PyQt5.QtWidgets import QApplication                       # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

import settings_dialog as sd                                   # noqa: E402
from app_config import config, config_path                     # noqa: E402


def right_in_dialog(dlg, w) -> bool:
    """控件的右边缘是否在对话框可视范围内（超出就是被裁掉了）。"""
    if w.isHidden():
        return False
    p = w.mapTo(dlg, QPoint(w.width(), 0))
    return p.x() <= dlg.width()


def main():
    app = QApplication(sys.argv)
    print("APPDATA =", os.environ["APPDATA"])
    print("config 存在?", os.path.exists(config_path()))
    print("check_update 配置值 =", config.get("check_update"))
    print("当前缩放 =", app.devicePixelRatio(), "系统字体 =", app.font().pointSizeF())

    dlg = sd.SettingsDialog(config, lambda s: (True, ""), None,
                            probe_hotkey=lambda s: (True, ""))
    dlg.show()
    app.processEvents()

    print("\n窗口宽度 = %d，sizeHint = %d，minimumSizeHint = %d"
          % (dlg.width(), dlg.sizeHint().width(), dlg.minimumSizeHint().width()))

    items = [
        ("截图时隐藏窗口", dlg.chk_hide),
        ("隐藏到托盘", dlg.rb_tray),
        ("直接退出", dlg.rb_exit),
        ("开机自动启动", dlg.chk_auto),
        ("自动检查更新", dlg.chk_update),
    ]
    print("\n%-16s %-8s %-8s %-8s %s" % ("控件", "勾选", "宽度", "右边缘在窗口内", "x 坐标"))
    for name, w in items:
        checked = w.isChecked() if hasattr(w, "isChecked") else "-"
        x = w.mapTo(dlg, QPoint(0, 0)).x() if not w.isHidden() else -1
        print("%-16s %-8s %-8s %-12s %s"
              % (name, checked, w.width(), right_in_dialog(dlg, w), x))

    print("\n快捷键输入框 =", repr(dlg.hotkey_edit.value()))
    print("版本文字 =", repr(dlg.lbl_version.text()))
    dlg.close()
    shutil.rmtree(_tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
