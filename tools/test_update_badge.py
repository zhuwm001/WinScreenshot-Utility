# -*- coding: utf-8 -*-
"""「发现新版本」提示与界面文案自检。

覆盖：
    1. 主界面绿箭头：默认隐藏 / 有新版出现 / 点击发信号 / 四个按钮间距
    2. 设置页绿箭头：有新版才出现，点击后关掉设置并把请求交给主程序
    3. 更新弹窗文案：按钮叫「确定」、不出现 Ed25519 / sha256 / GitHub 之类开发者措辞
    4. 隐藏到托盘的提示：每次都弹（不再只弹第一次）
    5. 右下角提示本身确实能显示出来

用法：
    python tools/test_update_badge.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

from PyQt5.QtWidgets import QApplication            # noqa: E402

app = QApplication(sys.argv)

import main as app_main                             # noqa: E402
import main_window                                  # noqa: E402
import settings_dialog                              # noqa: E402
import update_dialog as ud                          # noqa: E402
from app_config import config                       # noqa: E402
from toast import Toast                             # noqa: E402
from update import ReleaseInfo                      # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


info = ReleaseInfo(version="1.1.7", asset_url="https://example.com/a.exe",
                   asset_name="WoAiJieTu-Setup-v1.1.7.exe",
                   asset_size=30 * 1024 * 1024, notes_text="· 修复若干问题",
                   published_at="2026-11-17T02:00:00Z", signed=True)
no_installer = ReleaseInfo(version="1.1.7", notes_text="x", signed=True)


# ---------------------------------------------------------------- 主界面
print("\n== 主界面绿箭头 ==")
w = main_window.MainWindow("Ctrl+Alt+A")
w.show()
app.processEvents()
check("默认不显示绿箭头", w.btn_update.isHidden())
check("绿箭头排在设置按钮前", w.btn_update.x() < w.btn_settings.x())

fired = []
w.update_requested.connect(lambda: fired.append(1))
w.btn_update.click()
check("点绿箭头会请求打开更新窗口", len(fired) == 1, str(fired))

w.set_update_available(info)
app.processEvents()
check("查到新版本后出现绿箭头", not w.btn_update.isHidden())
tip = w.btn_update.toolTip()
check("悬停提示含「发现新版本」", "发现新版本" in tip, tip)
check("悬停提示带版本号", "1.1.7" in tip, tip)

gap = w.btn_settings.x() - (w.btn_update.x() + w.btn_update.width())
check("四个按钮间距收紧（<=6px）", 0 < gap <= 6, "%dpx" % gap)
xs = [b.x() for b in (w.btn_update, w.btn_settings, w.btn_min, w.btn_close)]
check("四个按钮自左向右排列", xs == sorted(xs) and len(set(xs)) == 4, str(xs))
check("四个按钮宽度一致",
      len({b.width() for b in (w.btn_update, w.btn_settings, w.btn_min, w.btn_close)}) == 1)

w.set_update_available(None)
check("没有新版本时收起绿箭头", w.btn_update.isHidden())
w.close()

# ---------------------------------------------------------------- 设置页
print("\n== 设置页绿箭头 ==")
sd = settings_dialog.SettingsDialog(config, lambda s: (True, ""))
check("没有新版本时不显示", sd.btn_update.isHidden())
sd.close()

sd2 = settings_dialog.SettingsDialog(config, lambda s: (True, ""), None,
                                     update_info=info)
sd2.show()
app.processEvents()
check("有新版本时显示", not sd2.btn_update.isHidden())
check("箭头提示带版本号", "1.1.7" in sd2.btn_update.toolTip(), sd2.btn_update.toolTip())
sd2.btn_update.click()
app.processEvents()
check("点箭头后请求主程序打开更新窗口", sd2.wants_update)
check("设置窗口随即关闭", sd2.isHidden())

# ---------------------------------------------------------------- 弹窗文案
print("\n== 更新弹窗文案 ==")
latest = ud.UpdateDialog(mode=ud.MODE_LATEST)
check("已是最新：按钮是「确定」", latest.btn_go.text() == "确定", latest.btn_go.text())
body = latest.box.toPlainText()
check("已是最新：正文不提 GitHub 缓存", "GitHub" not in body, body)
check("已是最新：正文说清无需更新", "无需更新" in body, body)
check("统一叫「打开发布页」", latest.btn_page.text() == "打开发布页",
      latest.btn_page.text())
latest.close()

new = ud.UpdateDialog(info=info, mode=ud.MODE_NEW)
body = new.box.toPlainText()
check("新版本：正文不出现 Ed25519", "Ed25519" not in body)
check("新版本：正文不出现 sha256", "sha256" not in body)
check("新版本：保留签名说明（说人话）", "签名校验" in body, body)
check("新版本：副标题标注签名已校验", "签名已校验" in new.lbl_sub.text(),
      new.lbl_sub.text())
check("新版本：主按钮是「立即更新」", new.btn_go.text() == "立即更新", new.btn_go.text())
new.close()

err = ud.UpdateDialog(mode=ud.MODE_ERROR, message="网络连接失败。")
check("失败：按钮是「重试」", err.btn_go.text() == "重试", err.btn_go.text())
check("失败：副按钮是「关闭」", err.btn_close.text() == "关闭", err.btn_close.text())
err.close()

# ---------------------------------------------------------------- 托盘提示
print("\n== 隐藏到托盘的提示 ==")
title, text = app_main.tray_tip("Ctrl+Alt+A")
check("标题是「已隐藏到托盘」", title == "已隐藏到托盘", title)
check("正文带快捷键", "Ctrl+Alt+A" in text, text)
check("正文说明仍在后台运行", "后台运行" in text, text)
_, text2 = app_main.tray_tip("")
check("没设快捷键时不出现空占位", "快捷键" not in text2, text2)

src = io.open(os.path.join(ROOT, "src", "main.py"), encoding="utf-8").read()
start = src.index("def hide_to_tray")
body = src[start:src.index("def on_main_close", start)]
check("隐藏到托盘每次都提示（没有只弹一次的门闩）", "_tray_tip_shown" not in body)
check("隐藏到托盘确实调用了提示", "Toast.show_toast" in body)

# ---------------------------------------------------------------- 提示本身
print("\n== 右下角提示能否显示 ==")
t1 = Toast.show_toast(*app_main.tray_tip("Ctrl+Alt+A"), kind="info")
t2 = Toast.show_toast("已复制到剪贴板", "可直接到其他窗口按 Ctrl+V 粘贴。", kind="check")
app.processEvents()
check("隐藏托盘提示可见", t1.isVisible())
check("复制提示可见", t2.isVisible())
scr = app.primaryScreen().availableGeometry()
g = t1.geometry()
check("提示落在屏幕可见范围内",
      g.right() <= scr.right() + 2 and g.bottom() <= scr.bottom() + 2,
      "(%d,%d)" % (g.x(), g.y()))
t1.close()
t2.close()

# ---------------------------------------------------------------- 汇总
print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
if FAIL:
    for name in FAIL:
        print("  失败：" + name)
sys.exit(1 if FAIL else 0)
