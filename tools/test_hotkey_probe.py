# -*- coding: utf-8 -*-
"""快捷键「是否被占用」当场检测自检。

背景：以前只有点「保存」那一刻才发现冲突，用户录完组合键看不出任何反馈，
改成一个能用的组合后旧的红色报错还赖着不走，看起来就像这个功能坏了。

现在的行为：录完组合键 0.3 秒内自动探测，2 秒内一定给结果；换组合就重查，
旧报错当场清掉。

覆盖：
    1. 录完立刻出现「正在检查」，2 秒内变成真实结果（占用 / 可用）
    2. 换一个组合后旧报错马上消失
    3. 探测接口不会改动当前热键（只是问一句）
    4. 真机上 RegisterHotKey 被别的程序占用时 probe_conflict 能识别出来

用法：
    python tools/test_hotkey_probe.py
"""
import io
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

from PyQt5.QtWidgets import QApplication            # noqa: E402

app = QApplication(sys.argv)

import hotkey as hk                                # noqa: E402
import main as app_main                             # noqa: E402
import settings_dialog as sd_mod                    # noqa: E402
import theme                                        # noqa: E402
from app_config import config                       # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def pump(ms):
    """跑一小段事件循环（让 QTimer / singleShot 有机会触发）。"""
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def style_has(label, color):
    return color.lower() in (label.styleSheet() or "").lower()


print("快捷键占用检测自检")

# ---------------------------------------------------------------- 假探测
print("\n== 录完组合键 2 秒内给结果 ==")
BUSY = "Ctrl+Alt+A"
calls = []


def fake_probe(seq):
    calls.append(seq)
    if seq.upper() == BUSY.upper():
        return False, "快捷键 %s 已被其他程序占用，请重新设置" % seq
    return True, ""


sd = sd_mod.SettingsDialog(config, lambda s: (True, ""), None, probe_hotkey=fake_probe)
sd.show()
app.processEvents()
check("刚打开设置时不打扰（没有状态行）", sd.lbl_hotkey_state.isHidden())

sd.hotkey_edit.set_value(BUSY)          # 模拟用户录完组合键
check("录完立刻显示「正在检查」",
      "正在检查" in sd.lbl_hotkey_state.text(), sd.lbl_hotkey_state.text())
pump(600)                                # 0.6 秒 —— 远小于要求的 2 秒
txt = sd.lbl_hotkey_state.text()
check("2 秒内给出结果", "已被其他程序占用" in txt, txt)
check("占用的提示是红色的", style_has(sd.lbl_hotkey_state, theme.DANGER),
      sd.lbl_hotkey_state.styleSheet())
check("输入框同时标红", sd.hotkey_edit.property("invalid") == "true",
      str(sd.hotkey_edit.property("invalid")))
check("探测真的发生了", BUSY in calls, str(calls))

print("\n== 换一个能用的组合 ==")
free = "Ctrl+Shift+F9"
sd.hotkey_edit.set_value(free)
check("旧的红色报错立刻消失",
      sd.lbl_error.isHidden() and sd.lbl_error.text() == "",
      sd.lbl_error.text())
check("先显示正在检查新组合",
      "正在检查" in sd.lbl_hotkey_state.text(), sd.lbl_hotkey_state.text())
pump(600)
txt = sd.lbl_hotkey_state.text()
check("给出「可以使用」", "可以使用" in txt, txt)
check("可用的提示是绿色的", style_has(sd.lbl_hotkey_state, theme.SUCCESS),
      sd.lbl_hotkey_state.styleSheet())
check("输入框恢复常态", sd.hotkey_edit.property("invalid") == "false",
      str(sd.hotkey_edit.property("invalid")))

print("\n== 探测不会动现有热键 ==")
src = io.open(os.path.join(ROOT, "src", "hotkey.py"), encoding="utf-8").read()
start = src.index("def probe_conflict")
body = src[start:src.index("def register", start)]
check("probe_conflict 里没有 unregister", "unregister(" not in body)
check("probe_conflict 里不碰钩子序列", "_hook.set_sequence" not in body)
check("probe_conflict 不写 _registered", "_registered =" not in body)

main_src = io.open(os.path.join(ROOT, "src", "main.py"), encoding="utf-8").read()
check("主程序把探测接口传给了设置页", "probe_hotkey=self._probe_hotkey" in main_src)
check("主程序探测走 probe_conflict",
      "self.hotkey.probe_conflict(" in main_src)

# ---------------------------------------------------------------- 真机
print("\n== 真机：模拟别的程序占住 Ctrl+Alt+F9 ==")
mgr = hk.HotkeyManager(app)
mgr.register("Ctrl+Shift+F11")
before = mgr.current

VK_F9 = 0x78
occupied = bool(hk.user32.RegisterHotKey(None, 9193, hk.MOD_CONTROL | hk.MOD_ALT, VK_F9))
check("模拟占用已生效", occupied)
ok, msg = mgr.probe_conflict("Ctrl+Alt+F9")
check("探测到被占用", ok is False, str(ok))
check("提示是「已被其他程序占用」", "已被其他程序占用" in msg, msg)
ok2, _ = mgr.probe_conflict("Ctrl+Shift+F10")
check("没被占用的组合判定为可用", ok2 is True)
check("探测完当前热键没变", mgr.current == before, "%s -> %s" % (before, mgr.current))
hk.user32.UnregisterHotKey(None, 9193)

ok3, msg3 = mgr.probe_conflict("A")
check("缺修饰键会被指出来", ok3 is False and "Ctrl" in msg3, msg3)
ok4, msg4 = mgr.probe_conflict("Ctrl+Shift+NotAKey")
check("认不出的组合有提示", ok4 is False and msg4, msg4)
mgr.close()

print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
if FAIL:
    for name in FAIL:
        print("  失败：" + name)
sys.exit(1 if FAIL else 0)
