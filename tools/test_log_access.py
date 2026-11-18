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

print("5) 兜底截图不会越攒越多：只留最近 20 张，超出从最旧的删")
shots = update_log.shots_dir()
os.makedirs(shots, exist_ok=True)
for i in range(25):
    p = os.path.join(shots, "shot_%02d.png" % i)
    with open(p, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 512)
    os.utime(p, (1000 + i, 1000 + i))          # 制造先后顺序
dropped = update_log.prune_shots()
left = sorted(os.listdir(shots))
check(dropped == 5, "删掉了最旧的 5 张", "dropped=%d" % dropped)
check(len(left) == update_log.SHOT_KEEP, "剩 20 张", "left=%d" % len(left))
check(left[0] == "shot_05.png" and left[-1] == "shot_24.png", "留下的是最新的 20 张")

print("6) 总量上限也生效（与张数上限取先到的）")
dropped = update_log.prune_shots(keep=100, max_bytes=2 * 1024)
check(dropped >= 10, "体积超限时按大小裁（520B/张，2KB 只够留 3 张）", "dropped=%d" % dropped)
total = sum(os.path.getsize(os.path.join(shots, n)) for n in os.listdir(shots))
check(total <= 2 * 1024, "裁后总量不超上限", "%d 字节" % total)

print("7) 占用统计：日志与兜底图都算进去")
update_log.log("再来一行")
u = update_log.usage()
check(u["log"] > 0, "update.log 计入")
check(u["shots"] > 0 and u["shot_count"] > 0, "兜底图计入")
txt = update_log.usage_text()
check("MB" in txt or "KB" in txt, "占用文案带单位", txt)
check("张" in txt, "给出张数", txt)

print("8) 环境行不因缺屏信息而抛异常（拿不到屏幕时只跳过）")
class _Boom(object):
    pass
try:
    main._log_env()
    ok = True
except Exception as e:                       # noqa: BLE001
    ok = False
    print("     ", e)
check(ok, "重复调用不抛异常")

print("9) 历史日志整份都是 0x00：改名留证，另起一份能读的（不然发过来一个字都没有）")
_broken = update_log.log_path()
with open(_broken, "wb") as f:
    f.write(b"\x00" * 3000)
update_log._BROKEN_CHECKED = False               # 模拟"进程刚启动，第一次写日志"
update_log.log("重建后的第一行")
_tail = [l for l in update_log.read(60) if "重建后的第一行" in l]
check(len(_tail) == 1, "新日志里能读到刚写的那行")
check(os.path.exists(_broken + ".broken"), "坏日志被改名留证，没有直接删掉")
with open(_broken, "rb") as f:
    raw = f.read()
check(raw.count(0) == 0, "新文件里没有空字节", "%d 个 0x00" % raw.count(0))
check("空字节" in raw.decode("utf-8", errors="replace"), "重建时补了一条说明")

print("10) durable 行照样写、照样读（只多了落盘）")
update_log.log("这条要落盘", durable=True)
check(any("这条要落盘" in l for l in update_log.read(60)), "durable=True 正常写入")

print()
if FAILED:
    print("失败 %d 项：%s" % (len(FAILED), "；".join(FAILED)))
    sys.exit(1)
print("全部通过")
