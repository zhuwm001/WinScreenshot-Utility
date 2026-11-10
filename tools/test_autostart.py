# -*- coding: utf-8 -*-
"""验证开机启动：注册表读写、路径刷新、设置对话框联动。全部用临时项名，不碰真实启动项。"""
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
from PyQt5.QtWidgets import QApplication  # noqa: E402

import autostart  # noqa: E402

autostart.VALUE_NAME = "WoAiJieTu_SelfTest"
TEST_NAME = autostart.VALUE_NAME

def check(label, cond):
    print(("PASS  " if cond else "FAIL  ") + label)
    return cond

results = []
try:
    # 0. 环境干净
    autostart.apply(False)
    results.append(check("初始状态无启动项", not autostart.is_enabled()))
    print("   launch_command =", autostart.launch_command())

    # 1. 打开
    ok, msg = autostart.apply(True)
    results.append(check("勾选后写入成功 (%s)" % (msg or "ok"), ok and autostart.is_enabled()))
    results.append(check("写入的命令与期望一致", autostart.current_command() == autostart.launch_command()))
    results.append(check("命令带 --autostart 参数", "--autostart" in autostart.current_command()))

    # 2. 重复打开幂等
    ok, msg = autostart.apply(True)
    results.append(check("重复勾选不出错", ok and autostart.current_command() == autostart.launch_command()))

    # 3. 关闭
    ok, msg = autostart.apply(False)
    results.append(check("取消勾选后删除成功", ok and not autostart.is_enabled()))

    # 4. 重复关闭幂等
    ok, msg = autostart.apply(False)
    results.append(check("重复取消不出错", ok and not autostart.is_enabled()))

    # 5. 模拟路径变化后 sync 自动修复
    autostart.apply(True)
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, TEST_NAME, 0, winreg.REG_SZ, r'"C:\old\path\我爱截图.exe" --autostart')
    results.append(check("旧路径已写入", autostart.current_command() != autostart.launch_command()))
    ok, msg = autostart.sync(True)
    results.append(check("sync 修复为当前路径", ok and autostart.current_command() == autostart.launch_command()))

    # 6. 对话框联动
    app = QApplication(sys.argv)
    from app_config import config
    from settings_dialog import SettingsDialog

    before = bool(config.get("auto_start"))
    dlg = SettingsDialog(config, lambda s: (True, ""))
    results.append(check("对话框勾选状态与配置一致", dlg.chk_auto.isChecked() == before))

    dlg.chk_auto.setChecked(not before)
    dlg.accept()
    results.append(check("保存后配置已更新", bool(config.get("auto_start")) == (not before)))
    results.append(check("保存后注册表与勾选一致", autostart.is_enabled() == (not before)))

    # 还原
    dlg2 = SettingsDialog(config, lambda s: (True, ""))
    dlg2.chk_auto.setChecked(before)
    dlg2.accept()
    results.append(check("还原后注册表同步", autostart.is_enabled() == before))
finally:
    autostart.apply(False)
    left = autostart.is_enabled()
    print("cleanup: 启动项已清空" if not left else "cleanup: 仍有残留!")
    print("\n%d/%d passed" % (sum(1 for r in results if r), len(results)))
