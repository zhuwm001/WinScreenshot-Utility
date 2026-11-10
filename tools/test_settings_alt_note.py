# -*- coding: utf-8 -*-
"""设置界面里"含 Alt 的快捷键截不到多级菜单"这条说明的验证。

检查三件事：
1. 快捷键卡片里常驻一条说明，提到 Alt 会导致菜单收起（不是一闪而过的提示）；
2. 录到不含 Alt 的组合时，不出现那条黄色警告；
3. 录到含 Alt 的组合（Alt+Z / Ctrl+Alt+A）时，黄色警告立刻出现并说明原因。
"""
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
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication(sys.argv)

from app_config import config  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

ok_all = []


def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


dlg = SettingsDialog(config, lambda seq: (True, ""), None)

# 1) 常驻说明
texts = [w.text() for w in dlg.findChildren(QLabel)]
note = [t for t in texts if "Alt" in t and "收起" in t]
check("卡片里有常驻说明（Alt 会让菜单收起）", bool(note), note[:1])
if note:
    check("说明足够短（不超过 90 字）", len(note[0]) <= 90, "%d 字" % len(note[0]))

# 2) 不含 Alt 的组合：不报警
dlg.hotkey_edit.set_value("Ctrl+Shift+S")
app.processEvents()
check("Ctrl+Shift+S 不显示 Alt 警告", dlg.lbl_alt.isHidden(), dlg.lbl_alt.text())
check("Ctrl+Shift+S 警告文本为空", dlg.lbl_alt.text() == "", dlg.lbl_alt.text())

# 3) 含 Alt 的组合：立刻警告
for seq in ("Alt+Z", "Ctrl+Alt+A", "Alt+Shift+Q"):
    dlg.hotkey_edit.set_value(seq)
    app.processEvents()
    txt = dlg.lbl_alt.text()
    check("%s 显示 Alt 警告" % seq, (not dlg.lbl_alt.isHidden()) and bool(txt), txt)
    check("%s 警告里说明会截不到菜单" % seq, ("菜单" in txt) and ("Alt" in txt), txt)
    check("%s 警告里给了替代方案" % seq, "Ctrl+Shift+" in txt, txt)

# 4) 再改回不含 Alt：警告消失
dlg.hotkey_edit.set_value("Ctrl+Q")
app.processEvents()
check("改回 Ctrl+Q 后警告消失", dlg.lbl_alt.isHidden())

# 5) 对话框打开时若已存的是 Alt 组合，也要直接显示警告
dlg2 = SettingsDialog(config, lambda seq: (True, ""), None)
dlg2.hotkey_edit.set_value("Alt+Z")
app.processEvents()
check("再次打开时 Alt 组合仍会显示警告", (not dlg2.lbl_alt.isHidden()))

print("\n结果: %d/%d 通过" % (sum(ok_all), len(ok_all)))
sys.exit(0 if all(ok_all) else 1)

