# -*- coding: utf-8 -*-
"""界面文案口吻检查：正式对外，不允许出现口语化表达。

做法不是抠源码字符串（注释里随便写都行），而是把界面真的构造出来，
把用户能看到的文字全捞一遍：标签、按钮、复选框、单选框、悬停提示、
窗口标题、更新说明正文。然后对着禁用词表逐条比。

覆盖：
    1. 设置窗口的全部可见文字
    2. 主界面（标题、快捷键行、四个按钮的悬停提示）
    3. 检查更新窗口的三种状态（有新版本 / 已是最新 / 检查失败）
    4. 更新出错时的中文提示（网络、TLS、HTTP 状态码）
    5. 快捷键占用/失败提示

用法：
    python tools/test_copy_tone.py
"""
import os
import re
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

from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractButton, QApplication, QLabel, QPlainTextEdit, QTextEdit, QWidget,
)

app = QApplication(sys.argv)

import hotkey as hk                                    # noqa: E402
import settings_dialog as sd                           # noqa: E402
import update as up                                    # noqa: E402
import update_dialog as ud                             # noqa: E402
from app_config import config                          # noqa: E402
from main_window import MainWindow                     # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("%s %s%s" % ("[OK]  " if cond else "[FAIL]", name,
                       ("  " + str(extra)) if extra else ""))


# 口语/内部说法：正式对外的界面里不该出现
BANNED = [
    "别用", "点这里", "换一个", "这个版本", "过一会儿", "又改回",
    "重开", "放心", "查不到", "顺手", "糊", "赖着", "弄", "咋", "啥",
    "搞定", "压根", "省得", "免得", "一按", "一会儿再说",
]


def collect(widget):
    """把一个窗口里用户能看到的文字全捞出来。"""
    out = [widget.windowTitle()]
    for w in widget.findChildren(QWidget):
        tip = w.toolTip()
        if tip:
            out.append(tip)
        if isinstance(w, QLabel):
            out.append(w.text())
        elif isinstance(w, QAbstractButton):
            out.append(w.text())
        elif isinstance(w, (QPlainTextEdit, QTextEdit)):
            out.append(w.toPlainText())
    return [t for t in out if t]


def offenders(texts):
    hit = []
    for t in texts:
        for bad in BANNED:
            if bad in t:
                hit.append((bad, t.strip().replace("\n", " / ")))
    return hit


def report(title, texts):
    hit = offenders(texts)
    check("%s：没有口语化表达" % title, not hit,
          hit[:3] if hit else "")


# ---------------------------------------------------------------- 设置窗口
print("== 设置窗口 ==")
dlg = sd.SettingsDialog(config, lambda seq: (True, ""), None,
                        probe_hotkey=lambda seq: (True, ""))
report("设置窗口", collect(dlg))

# 含 Alt 时当场弹出的那条黄字（默认隐藏，要主动触发才拿得到）
dlg.hotkey_edit.set_value("Alt+Z")
app.processEvents()
alt_note = dlg.lbl_alt.text()
check("Alt 警告文案无口语", not offenders([alt_note]), alt_note)
check("Alt 警告说明了原因与替代方案",
      ("Alt" in alt_note) and ("菜单" in alt_note) and ("Ctrl+Shift" in alt_note),
      alt_note)
dlg.close()

# 快捷键那一行状态文案
print("\n== 快捷键状态提示 ==")
for seq, ok, msg in [
    ("Ctrl+Shift+A", True, ""),
    ("Ctrl+Alt+F9", False, ""),
    ("Ctrl+Shift+Z", False, "快捷键 Ctrl+Shift+Z 已被其他程序占用，请重新设置"),
    ("Ctrl+Shift+Z", False, "快捷键 Ctrl+Shift+Z 注册失败（错误码 1409），请更换其他组合"),
]:
    text = sd.hotkey_state_text(ok, seq, msg)
    check("%s 的状态文案无口语" % seq, not offenders([text]), text)

# ---------------------------------------------------------------- 主界面
print("\n== 主界面 ==")
win = MainWindow("Ctrl+Shift+A")
report("主界面", collect(win))
info = up.ReleaseInfo(version="1.2.9", tag="v1.2.9", title="1.2.9",
                      notes_text="修复若干问题", page_url="https://github.com/x",
                      asset_name="setup.exe",
                      asset_url="https://github.com/x/setup.exe",
                      asset_size=12 * 1024 * 1024,
                      published_at="2026-11-17T10:00:00Z",
                      sha256="0" * 64, signed=True)
win.set_update_available(info)
report("主界面（有新版本）", collect(win))
win.close()

# ---------------------------------------------------------------- 更新窗口
print("\n== 检查更新窗口 ==")
for mode, kwargs, label in [
    (ud.MODE_NEW, {"info": info}, "有新版本"),
    (ud.MODE_NEW, {"info": up.ReleaseInfo(version="1.2.9", signed=False,
                                          notes_text="")}, "有新版本（无安装包）"),
    (ud.MODE_LATEST, {}, "已是最新"),
    (ud.MODE_ERROR, {"message": up._network_error("TLS initialization failed")},
     "检查失败"),
]:
    d = ud.UpdateDialog(mode=mode, **kwargs)
    report("更新窗口 - %s" % label, collect(d))
    d.close()

# ---------------------------------------------------------------- 错误提示
print("\n== 更新出错提示 ==")
samples = [
    up._http_hint(404),
    up._http_hint(403),
    up._http_hint(503),
    up._network_error("TLS initialization failed"),
    up._network_error("tunnel connection failed: 502"),
    up._network_error("Connection timed out"),
    up._network_error("Host not found"),
    up._network_error("Connection refused"),
    up._network_error(""),
]
for s in samples:
    check("错误文案无口语：%s" % s.split("（")[0][:18], not offenders([s]), s)

# ---------------------------------------------------------------- 托盘提示
print("\n== 托盘与提示 ==")
import main as app_main                                # noqa: E402
title, text = app_main.tray_tip("Ctrl+Shift+A")
check("隐藏到托盘的提示无口语", not offenders([title, text]), text)
check("检查结果文案无口语",
      not offenders([app_main.check_result_text("found", "1.2.9"),
                     app_main.check_result_text("latest"),
                     app_main.check_result_text("failed", reason="连接 GitHub 超时")]))

print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)
