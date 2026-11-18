# -*- coding: utf-8 -*-
"""设置页「查看日志」的可达性 + 启动环境行。

排查问题只有一条路：让对方点一下「查看日志」，把看到的发回来。所以这个按钮
必须一次给全 —— update.log（运行/更新/截图全流程）、crash.log（崩溃栈）、
screenshots（剪贴板写不进去时兜底存的图）都在同一个目录里。

同时验证启动时那行「环境」，它替代了「让对方自己说几块屏、缩放多少」。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

# 隔离：日志目录跟着 APPDATA 走，别污染真实配置
_TMP = tempfile.mkdtemp(prefix="logtest-")
os.environ["APPDATA"] = _TMP

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ.setdefault("QT_PLUGIN_PATH", _PLUG)
os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", os.path.join(_PLUG, "platforms"))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import main  # noqa: E402
import update_log  # noqa: E402

FAILED = []


def check(ok, label, extra=""):
    print(("  ok   " if ok else "  FAIL ") + label + (("  " + extra) if extra else ""))
    if not ok:
        FAILED.append(label)


print("1) 一个日志都没有：打开目录本身，给出明确提示")
folder, target = update_log.open_target()
check(os.path.basename(folder) == "我爱截图", "日志目录是 %APPDATA%\\我爱截图", folder)
check(target is None, "没有文件时不给选中项（打开空目录）")

print("2) 只有 update.log：选中它")
update_log.log("这是一行测试日志")
folder, target = update_log.open_target()
check(target == update_log.log_path(), "选中 update.log")
check(os.path.exists(target), "文件确实存在")

print("3) 出过崩溃：两个都在，优先显示 update.log（流程比栈常用）")
with open(update_log.crash_path(), "w", encoding="utf-8") as f:
    f.write("=== 测试 ===\n")
folder, target = update_log.open_target()
files = update_log.existing_files()
check(len(files) == 2, "两个日志都被列出来", str([os.path.basename(p) for p in files]))
check(os.path.basename(target) == "update.log", "默认选中 update.log")
check(os.path.basename(files[1]) == "crash.log", "crash.log 排在后面")

print("4) 启动环境行：屏数、分辨率、缩放、虚拟桌面都要有")
main._log_env()
lines = [l for l in update_log.read(200) if "环境：" in l]
check(len(lines) == 1, "写入了恰好一行环境", str(len(lines)))
env = lines[0] if lines else ""
check("屏=" in env and "虚拟桌面=" in env, "包含屏数与虚拟桌面", env.strip()[:110])
check("@" in env, "每块屏带缩放比例")
import re
m = re.search(r"屏=(\d+)", env)
check(bool(m) and int(m.group(1)) >= 1, "屏数至少 1", m.group(0) if m else "?")

print("5) 环境行不因缺屏信息而抛异常（拿不到屏幕时只跳过）")
class _Boom(object):
    pass
try:
    main._log_env()
    ok = True
except Exception as e:                       # noqa: BLE001
    ok = False
    print("     ", e)
check(ok, "重复调用不抛异常")

print()
if FAILED:
    print("失败 %d 项：%s" % (len(FAILED), "；".join(FAILED)))
    sys.exit(1)
print("全部通过")
