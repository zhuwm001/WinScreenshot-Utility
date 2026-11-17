# -*- coding: utf-8 -*-
"""设置项默认值的全量自检。

背景：用户把 1.2.1 安装包发给别人，别人打开设置发现「自动检查更新」没勾。
根因不是默认值（DEFAULTS 里一直是 True），而是**显示**这一层不可靠：
    * 复选框挤在版本号那一行，窗口略窄就被压扁/挤出可视区；
    * 配置里的值被写成 null / "false" 之类，bool() 一转就成了关闭；
    * 「恢复默认」只回滚界面上看得见的 5 项，笔色/字号/粗体没回滚。

所以这份测试盯四件事：
    1. 首次安装（没有 config.json）时，每个选项的初始状态都必须等于默认值
    2. 用户改过且保存后，再打开必须按用户的设置显示（不是又回到默认）
    3. 「恢复默认」要把**所有**设置项回默认，运行状态（上次检查时间/结果）不动
    4. 界面显示与代码实际行为一致：显示为关闭时，程序真的不检查更新

用法：
    python tools/test_settings_defaults.py
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
import settings_dialog  # noqa: E402
from app_config import (  # noqa: E402
    DEFAULTS, SETTING_KEYS, STATE_KEYS, Config, as_bool, as_choice, as_color, as_int,
)
from settings_dialog import SettingsDialog  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


class temp_appdata(object):
    """把 APPDATA 指到临时目录：等价于「这台机器上从没装过本软件」。"""

    def __init__(self, contents=None):
        self.contents = contents

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="wojietu_set_")
        self.old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self.tmp
        if self.contents is not None:
            d = os.path.join(self.tmp, app_config.APP_NAME)
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, "config.json")
            with io.open(path, "w", encoding="utf-8") as f:
                if isinstance(self.contents, str):
                    f.write(self.contents)
                else:
                    json.dump(self.contents, f, ensure_ascii=False)
        return self

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self.old
        return False

    def read(self):
        path = os.path.join(self.tmp, app_config.APP_NAME, "config.json")
        if not os.path.exists(path):
            return None
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)


# 保存时会去写注册表；测试里换成空实现，别动本机真实的自启项
_real_apply = settings_dialog.autostart.apply
settings_dialog.autostart.apply = lambda enabled: (True, "")


def make_dialog(cfg):
    return SettingsDialog(cfg, lambda s: (True, ""), None, probe_hotkey=lambda s: (True, ""))


def controls(dlg):
    """界面上能改的 5 项 -> 当前状态的字典。"""
    return {
        "hide_self": dlg.chk_hide.isChecked(),
        "close_action": "exit" if dlg.rb_exit.isChecked() else "tray",
        "auto_start": dlg.chk_auto.isChecked(),
        "check_update": dlg.chk_update.isChecked(),
        "hotkey": dlg.hotkey_edit.value(),
    }


# ------------------------------------------------------------------ 1. 首次安装
print("== 首次安装（没有 config.json）==")
with temp_appdata() as env:
    cfg = Config()
    check("第一次运行就把 config.json 写出来了", env.read() is not None)
    saved = env.read() or {}
    check("落盘的值里 check_update 是开", saved.get("check_update") is True, saved.get("check_update"))
    for key in ("hide_self", "auto_start", "close_action", "hotkey"):
        check("落盘的 %s 等于默认值" % key, saved.get(key) == DEFAULTS[key],
              "%r vs %r" % (saved.get(key), DEFAULTS[key]))

    dlg = make_dialog(cfg)
    got = controls(dlg)
    for key in ("hide_self", "close_action", "auto_start", "check_update", "hotkey"):
        check("设置页 %s 显示默认值" % key, got[key] == DEFAULTS[key],
              "%r vs %r" % (got[key], DEFAULTS[key]))
    check("「截图时隐藏窗口」显示为开", dlg.chk_hide.isChecked())
    check("关闭行为显示为「隐藏到托盘」", dlg.rb_tray.isChecked() and not dlg.rb_exit.isChecked())
    check("「开机自动启动」显示为关", not dlg.chk_auto.isChecked())
    check("「自动检查更新」显示为开", dlg.chk_update.isChecked())
    check("快捷键显示 Ctrl+Shift+A", dlg.hotkey_edit.value() == "Ctrl+Shift+A")
    dlg.close()

# ------------------------------------------------------------------ 2. 用户设置优先
print("\n== 用户改过的设置优先于默认值 ==")
user_cfg = {
    "hide_self": False,
    "close_action": "exit",
    "auto_start": True,
    "check_update": False,
    "hotkey": "Ctrl+Alt+S",
}
with temp_appdata(user_cfg) as env:
    cfg = Config()
    dlg = make_dialog(cfg)
    got = controls(dlg)
    check("关掉的「截图时隐藏窗口」仍是关", got["hide_self"] is False)
    check("选过的「直接退出」仍是选中", got["close_action"] == "exit")
    check("打开过的「开机自启」仍是开", got["auto_start"] is True)
    check("关掉的「自动检查更新」仍是关", got["check_update"] is False)
    check("改过的快捷键仍是 Ctrl+Alt+S", got["hotkey"] == "Ctrl+Alt+S")
    dlg.close()

# ------------------------------------------------------------------ 3. 写坏的配置
print("\n== 配置被写坏时按默认值处理 ==")
for raw, key, expect, label in [
    ({"hide_self": None}, "hide_self", True, "hide_self=null"),
    ({"hide_self": "abc"}, "hide_self", True, "hide_self=乱码"),
    ({"check_update": "on"}, "check_update", True, "check_update=on"),
    ({"close_action": "Exit "}, "close_action", "exit", "close_action=Exit（大小写+空格）"),
    ({"close_action": "窗口"}, "close_action", "tray", "close_action=乱码"),
    ({"text_size": "big"}, "text_size", 20, "text_size=big"),
    ({"text_size": 999}, "text_size", 20, "text_size 越界"),
    ({"pen_color": "red"}, "pen_color", "#FF3B30", "pen_color=red"),
    ({"hotkey": "   "}, "hotkey", "Ctrl+Shift+A", "hotkey 空白"),
]:
    with temp_appdata(raw) as env:
        c = Config()
        check("%s -> %r" % (label, expect), c.get(key) == expect, c.get(key))

print("\n== 规整函数本身 ==")
check("as_bool 认 null", as_bool(None, True) is True)
check("as_bool 认字符串 false", as_bool("false", True) is False)
check("as_choice 容忍大小写", as_choice("EXIT", ("tray", "exit"), "tray") == "exit")
check("as_int 越界回默认", as_int(999, 20, 12, 96) == 20)
check("as_color 拒绝非法值", as_color("rgb(1,2,3)", "#FF3B30") == "#FF3B30")
check("as_color 统一成大写", as_color("#ff3b30", "#000000") == "#FF3B30")

# ------------------------------------------------------------------ 4. 恢复默认
print("\n== 恢复默认 ==")
dirty = {
    "hide_self": False, "close_action": "exit", "auto_start": True,
    "check_update": False, "hotkey": "Ctrl+Alt+S",
    "pen_color": "#00FF00", "text_size": 48, "text_bold": True,
    "update_last_check": 1700000000, "update_last_result": "发现新版本 9.9.9",
}
with temp_appdata(dirty) as env:
    cfg = Config()
    dlg = make_dialog(cfg)
    dlg._restore_defaults()
    got = controls(dlg)
    for key in ("hide_self", "close_action", "auto_start", "check_update", "hotkey"):
        check("界面 %s 回到默认" % key, got[key] == DEFAULTS[key],
              "%r vs %r" % (got[key], DEFAULTS[key]))
    check("界面上没显示的设置也标记为要回默认", dlg._reset_extras is True)

    dlg.accept()
    saved = env.read() or {}
    for key in SETTING_KEYS:
        check("保存后 %s 已是默认值" % key, saved.get(key) == DEFAULTS[key],
              "%r vs %r" % (saved.get(key), DEFAULTS[key]))
    for key in STATE_KEYS:
        check("运行状态 %s 不被恢复默认清掉" % key, saved.get(key) == dirty[key],
              "%r" % (saved.get(key),))

print("\n== 恢复默认后重新打开 ==")
with temp_appdata(dirty) as env:
    cfg = Config()
    dlg = make_dialog(cfg)
    dlg._restore_defaults()
    dlg.accept()
    cfg2 = Config()                   # 重新读盘，等于「关掉设置再打开」
    dlg2 = make_dialog(cfg2)
    got = controls(dlg2)
    for key in ("hide_self", "close_action", "auto_start", "check_update", "hotkey"):
        check("重开后 %s 仍是默认" % key, got[key] == DEFAULTS[key], got[key])
    dlg2.close()

print("\n== 只取消不保存时不能改配置 ==")
with temp_appdata(dirty) as env:
    cfg = Config()
    dlg = make_dialog(cfg)
    dlg._restore_defaults()
    dlg.reject()                      # 相当于点「取消」
    saved = env.read() or {}
    check("取消后 check_update 仍是用户关掉的状态", saved.get("check_update") is False,
          saved.get("check_update"))

# ------------------------------------------------------------------ 5. 界面与行为一致
print("\n== 界面显示与代码行为一致 ==")
import main as app_main  # noqa: E402

check("显示为关闭时，启动检查真的不发请求",
      app_main.check_allowed(app_main.CHECK_STARTUP, 0,
                             enabled=as_bool(False, True)) is False)
check("显示为开启时，启动检查会发请求",
      app_main.check_allowed(app_main.CHECK_STARTUP, 0,
                             enabled=as_bool(True, False)) is True)
check("显示为关闭时，定时检查也不发请求",
      app_main.check_allowed(app_main.CHECK_TIMER, 0,
                             enabled=as_bool(False, True)) is False)

src = io.open(os.path.join(ROOT, "src", "main.py"), encoding="utf-8").read()
check("启动时会校正开机启动项（注册表跟随设置）", "self._sync_autostart()" in src)
check("更新检查的开关读的是规整后的布尔",
      'enabled = as_bool(config.get("check_update"), True)' in src)

dlg_src = io.open(os.path.join(ROOT, "src", "settings_dialog.py"), encoding="utf-8").read()
check("设置页三个复选框都走 as_bool", dlg_src.count("as_bool(cfg.get(") == 3,
      dlg_src.count("as_bool(cfg.get("))
# as_bool(cfg.get( 里也含 "bool(cfg.get(" 这个子串，减掉才是真正的裸转换
bare = dlg_src.count("bool(cfg.get(") - dlg_src.count("as_bool(cfg.get(")
check("设置页没有裸 bool(cfg.get(...))", bare == 0, bare)

# ------------------------------------------------------------------ 6. 布局不会挤掉
print("\n== 复选框单独一行，任何宽度都看得见 ==")
with temp_appdata() as env:
    cfg = Config()
    dlg = make_dialog(cfg)
    dlg.show()
    app.processEvents()
    from PyQt5.QtCore import QPoint
    left_of_others = dlg.chk_hide.mapTo(dlg, QPoint(0, 0)).x()
    left_of_chk = dlg.chk_update.mapTo(dlg, QPoint(0, 0)).x()
    check("复选框与其它复选框左对齐（不在版本号那一行）",
          abs(left_of_chk - left_of_others) <= 2,
          "chk_update=%d chk_hide=%d" % (left_of_chk, left_of_others))
    right = dlg.chk_update.mapTo(dlg, QPoint(dlg.chk_update.width(), 0)).x()
    check("默认宽度下完整可见", right <= dlg.width(), "right=%d dlg=%d" % (right, dlg.width()))

    # 硬把窗口压窄（低于建议宽度），模拟别人机器上字体更宽、窗口更窄的情况
    dlg.setMinimumWidth(200)
    dlg.resize(360, dlg.height())
    app.processEvents()
    right = dlg.chk_update.mapTo(dlg, QPoint(dlg.chk_update.width(), 0)).x()
    check("窗口压到 360 后仍完整可见", right <= dlg.width(),
          "right=%d dlg=%d" % (right, dlg.width()))
    check("窗口压到 360 后文字没被截断",
          dlg.chk_update.width() >= dlg.chk_update.sizeHint().width(),
          "w=%d hint=%d" % (dlg.chk_update.width(), dlg.chk_update.sizeHint().width()))
    dlg.close()

settings_dialog.autostart.apply = _real_apply

print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)
