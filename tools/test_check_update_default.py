# -*- coding: utf-8 -*-
"""「自动检查更新」是否默认勾选，以及那一行会不会把复选框挤掉。

背景：默认值一直是 True，但用户可能看到「没勾」的界面，原因有两类：
    1. config.json 里的值缺失或被写成 null / "false" / 0，bool() 一转就成了关闭；
    2. 设置窗口太窄，版本号 + 绿箭头 + 立即检查 + 查看日志 把复选框挤出可视区。

覆盖：
    1. 默认值本身是 True
    2. 没有配置文件时是开启
    3. 配置里写坏（null / 字符串 / 数字）时按默认开启
    4. 用户自己关掉的（明确 false）要尊重，不能强行打勾
    5. 设置页的复选框跟着配置走；「恢复默认」会打回勾选
    6. 窗口最小宽度足够，复选框不会被压扁或挤出可视区

用法：
    python tools/test_check_update_default.py
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import app_config  # noqa: E402
from app_config import DEFAULTS, Config, as_bool  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


def fresh_config(contents):
    """在临时 APPDATA 下放一份 config.json，再全新加载一次。"""
    tmp = tempfile.mkdtemp(prefix="wojietu_cfg_")
    d = os.path.join(tmp, app_config.APP_NAME)
    os.makedirs(d, exist_ok=True)
    if contents is not None:
        with io.open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
            if isinstance(contents, str):
                f.write(contents)
            else:
                json.dump(contents, f, ensure_ascii=False)
    old = os.environ.get("APPDATA")
    os.environ["APPDATA"] = tmp
    try:
        return Config()
    finally:
        if old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old


print("== 默认值 ==")
check("默认值是开启", DEFAULTS["check_update"] is True, DEFAULTS["check_update"])

print("\n== 没有配置文件 ==")
cfg = fresh_config(None)
check("全新安装后是开启", cfg.get("check_update") is True, cfg.get("check_update"))

print("\n== 配置写坏 ==")
for raw, want, label in [
    ({"check_update": None}, True, "null"),
    ({"check_update": "true"}, True, "字符串 true"),
    ({"check_update": "yes"}, True, "字符串 yes"),
    ({"check_update": 1}, True, "数字 1"),
    ({"check_update": "false"}, False, "字符串 false（明确关闭）"),
    ({"check_update": 0}, False, "数字 0（明确关闭）"),
    ({"check_update": False}, False, "布尔 false（用户自己关的）"),
]:
    c = fresh_config(raw)
    check("%s -> %s" % (label, "开启" if want else "关闭"),
          c.get("check_update") is want, c.get("check_update"))

print("\n== 缺 key / 文件坏掉 ==")
c = fresh_config({"hotkey": "Ctrl+Shift+A"})
check("配置里没有这一项时按默认开启", c.get("check_update") is True)
c = fresh_config("{ 这不是合法 JSON")
check("配置文件损坏时按默认开启", c.get("check_update") is True)

print("\n== as_bool 本身 ==")
check("认 True", as_bool(True, False) is True)
check("认 \"0\"", as_bool("0", True) is False)
check("认不出来时用兜底", as_bool("随便", True) is True)

print("\n== 设置页复选框 ==")
c = fresh_config(None)
dlg = SettingsDialog(c, lambda s: (True, ""), None, probe_hotkey=lambda s: (True, ""))
check("默认配置下是勾选状态", dlg.chk_update.isChecked())
dlg.chk_update.setChecked(False)
dlg._restore_defaults()
check("点「恢复默认」后重新勾上", dlg.chk_update.isChecked())
dlg._read_form()
check("表单读出来的也是开启", dlg._read_form()["check_update"] is True)

c2 = fresh_config({"check_update": False})
dlg2 = SettingsDialog(c2, lambda s: (True, ""), None, probe_hotkey=lambda s: (True, ""))
check("用户明确关掉时显示为未勾选", not dlg2.chk_update.isChecked())

print("\n== 布局不会被挤掉 ==")
dlg3 = SettingsDialog(c, lambda s: (True, ""), None, probe_hotkey=lambda s: (True, ""))
dlg3.show()
app.processEvents()
need = dlg3.sizeHint().width()
check("窗口最小宽度不小于自然宽度", dlg3.minimumWidth() >= need,
      "min=%d hint=%d" % (dlg3.minimumWidth(), need))
chk_small = dlg3.chk_update.sizeHint().width()
check("复选框没被压扁", dlg3.chk_update.width() >= chk_small,
      "w=%d hint=%d" % (dlg3.chk_update.width(), chk_small))
row_width = sum(w.width() for w in (dlg3.lbl_version, dlg3.btn_update,
                                    dlg3.btn_check, dlg3.btn_log, dlg3.chk_update))
check("版本号那一行整体能放下（含间距）",
      dlg3.minimumWidth() >= row_width,
      "min=%d 行合计=%d" % (dlg3.minimumWidth(), row_width))
dlg3.close()

print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)
