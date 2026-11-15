# -*- coding: utf-8 -*-
"""更新对话框 / 设置对话框的外观与状态自检（不联网、不真装东西）。

    python tools/test_update_ui.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import screenshot as sc  # noqa: E402
import update as up  # noqa: E402
import update_dialog as ud  # noqa: E402
from app_config import APP_VERSION, config  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

PASS = FAIL = 0


def dlg2_bar_hidden(dlg):
    """对话框没 show 时子控件 isVisible() 恒为 False，只能看 hidden 标志。"""
    return dlg.bar.isHidden()


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [ok]   %s%s" % (name, ("  " + detail) if detail else ""))
    else:
        FAIL += 1
        print("  [FAIL] %s%s" % (name, ("  " + detail) if detail else ""))


def fake_info(portable_ok=True):
    return up.ReleaseInfo(
        version="1.1.0",
        tag="v1.1.0",
        title="我爱截图 v1.1.0",
        notes="",
        notes_text="· 修复双显示器副屏截成黑块\n· 新增自动更新，装完自动重开\n· 更新说明支持长文本滚动",
        page_url="https://github.com/zhuwm001/WinScreenshot-Utility/releases/tag/v1.1.0",
        asset_name="我爱截图_安装包_v1.1.0.exe",
        asset_url="https://x/setup.exe",
        asset_size=29000000,
        digest="",
        published_at="2026-11-15T13:20:00Z",
    )


def main():
    sc.set_process_dpi_awareness()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)

    print("更新界面自检  软件版本 %s" % APP_VERSION)
    print("  屏幕缩放 %s  安装版=%s"
          % ([round(s.devicePixelRatio(), 2) for s in app.screens()], up.is_installed_copy()))

    # ---------------- 有新版本（安装版） ----------------
    print("\n== 有新版本 ==")
    dlg = ud.UpdateDialog(info=fake_info(), mode=ud.MODE_NEW)
    dlg._portable = False
    dlg._fill()
    check("标题带版本号", "1.1.0" in dlg.lbl_title.text(), dlg.lbl_title.text())
    check("副标题显示当前版本", APP_VERSION in dlg.lbl_sub.text(), dlg.lbl_sub.text())
    check("副标题显示大小", "27.7 MB" in dlg.lbl_sub.text(), dlg.lbl_sub.text())
    check("正文有更新内容", "副屏" in dlg.box.toPlainText())
    check("按钮是立即更新", dlg.btn_go.text() == "立即更新", dlg.btn_go.text())
    check("进度条默认隐藏", dlg.bar.isHidden())
    h = dlg.sizeHint().height()
    check("高度不超过 720 逻辑像素", h <= 720, "h=%d" % h)

    print("\n== 下载进度 ==")
    dlg._on_progress(10 * 1024 * 1024, 29 * 1024 * 1024)
    check("进度条出现", not dlg2_bar_hidden(dlg))
    check("进度值合理", 30 <= dlg.bar.value() <= 40, str(dlg.bar.value()))
    check("状态文字带 MB", "MB" in dlg.lbl_status.text(), dlg.lbl_status.text())
    dlg._on_progress(29 * 1024 * 1024, 29 * 1024 * 1024)
    check("下满 100%", dlg.bar.value() == 100)

    got = {}
    dlg.ready_to_install.connect(lambda p: got.update(path=p))
    dlg._on_done(r"C:\Temp\wojietu-setup-1.1.0.exe")
    check("发出安装信号", got.get("path", "").endswith(".exe"), str(got))
    check("完成后按钮变安装中", "安装" in dlg.btn_go.text(), dlg.btn_go.text())

    print("\n== 下载失败 ==")
    dlg2 = ud.UpdateDialog(info=fake_info(), mode=ud.MODE_NEW)
    dlg2._busy = True
    dlg2._on_failed("网络连接失败：Connection refused")
    check("显示失败原因", "Connection refused" in dlg2.lbl_status.text())
    check("按钮变重试", dlg2.btn_go.text() == "重试", dlg2.btn_go.text())
    check("重试按钮可用", dlg2.btn_go.isEnabled())
    check("进度条收起", dlg2.bar.isHidden())
    dlg2.close()

    # ---------------- 免安装版 ----------------
    print("\n== 免安装版（只给下载页） ==")
    dlg3 = ud.UpdateDialog(info=fake_info(), mode=ud.MODE_NEW)
    dlg3._portable = True
    dlg3._fill()
    check("按钮改成下载安装包", dlg3.btn_go.text() == "下载安装包", dlg3.btn_go.text())
    check("正文提示免安装版", "免安装版" in dlg3.box.toPlainText())
    dlg3.close()

    # ---------------- 已是最新 / 失败 ----------------
    print("\n== 已是最新 ==")
    dlg4 = ud.UpdateDialog(mode=ud.MODE_LATEST)
    check("标题已是最新", dlg4.lbl_title.text() == "已是最新版本")
    check("按钮是「好」", dlg4.btn_go.text() == "好", dlg4.btn_go.text())
    check("隐藏稍后按钮", not dlg4.btn_close.isVisible())
    dlg4.close()

    print("\n== 检查失败 ==")
    dlg5 = ud.UpdateDialog(mode=ud.MODE_ERROR, message="仓库或 Release 不可访问（HTTP 404）。")
    check("标题检查失败", dlg5.lbl_title.text() == "检查更新失败")
    check("显示错误原文", "404" in dlg5.box.toPlainText())
    check("按钮是重试", dlg5.btn_go.text() == "重试", dlg5.btn_go.text())
    dlg5.close()

    # ---------------- 设置对话框 ----------------
    print("\n== 设置对话框 ==")
    sd = SettingsDialog(config, lambda seq: (True, ""))
    check("显示当前版本", APP_VERSION in sd.lbl_version.text(), sd.lbl_version.text())
    check("自动检查更新默认开", sd.chk_update.isChecked())
    values = sd._read_form()
    check("提交值含 check_update", "check_update" in values, str(values))
    sh = sd.sizeHint().height()
    print("     设置窗口尺寸 %dx%d" % (sd.sizeHint().width(), sh))
    check("设置窗口不超过 720 高", sh <= 720, "h=%d" % sh)
    sd.close()

    # ---------------- 弹窗外观留档 ----------------
    outdir = os.path.join(ROOT, "build", "update_ui")
    os.makedirs(outdir, exist_ok=True)
    shot = ud.UpdateDialog(info=fake_info(), mode=ud.MODE_NEW)
    shot._portable = False
    shot._fill()
    shot.show()
    app.processEvents()
    shot.grab().save(os.path.join(outdir, "dialog_new.png"))
    shot._on_progress(12 * 1024 * 1024, 29 * 1024 * 1024)
    app.processEvents()
    shot.grab().save(os.path.join(outdir, "dialog_download.png"))
    shot.close()

    sd2 = SettingsDialog(config, lambda seq: (True, ""))
    sd2.show()
    app.processEvents()
    sd2.grab().save(os.path.join(outdir, "settings.png"))
    sd2.close()
    print("\n截图已存到 %s" % outdir)

    print("\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
