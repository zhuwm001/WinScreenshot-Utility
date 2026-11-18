# -*- coding: utf-8 -*-
"""静默安装的提示卡片：文案、位置、不抢焦点、能关掉。

更新时会先关掉主程序再后台装文件，中间十几秒没有任何界面。这张卡片是那段时间
唯一的说明，所以盯三件事：文案说的是不是在装、摆的位置看不看得见、会不会把
用户正在操作的窗口抢走焦点。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402

qt_env.setup()

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import install_notice  # noqa: E402
import main  # noqa: E402

FAILED = []


def check(ok, label, extra=""):
    print(("  ok   " if ok else "  FAIL ") + label + (("  " + extra) if extra else ""))
    if not ok:
        FAILED.append(label)


print("1) 文案与参考的更新提示一致，只换了名称")
check(install_notice.NOTICE_TITLE == "我爱截图", "标题是软件名", install_notice.NOTICE_TITLE)
check(install_notice.NOTICE_TEXT == "正在安装更新，更新完成后将自动重启应用。",
      "正文一字不差", install_notice.NOTICE_TEXT)

print("2) 尺寸与位置：够宽、摆在屏幕上半部、不越界")
n = install_notice.InstallNotice()
n.popup()
for _ in range(6):
    app.processEvents()
scr = app.primaryScreen().availableGeometry()
check(n.width() >= 420, "窗口宽度够放下一行说明", "%d px" % n.width())
check(n.height() >= 90, "高度足够两行文字", "%d px" % n.height())
check(scr.contains(n.frameGeometry()), "整块卡片都在屏幕可视区内",
      "卡片 %s / 屏幕 %s" % (n.frameGeometry(), scr))
center_off = abs(n.frameGeometry().center().x() - scr.center().x())
check(center_off <= 2, "水平居中", "偏差 %d px" % center_off)
ratio = (n.y() - scr.top()) / float(scr.height())
check(0.10 <= ratio <= 0.28, "垂直位置在上部但不贴顶", "y=%.0f%%" % (ratio * 100))

print("3) 不抢焦点、置顶")
flags = n.windowFlags()
check(bool(flags & Qt.WindowDoesNotAcceptFocus), "不接收焦点")
check(bool(flags & Qt.WindowStaysOnTopHint), "置顶显示")
check(n.testAttribute(Qt.WA_ShowWithoutActivating), "显示时不激活")

print("4) 图标画出来了")
icons = [w for w in n.findChildren(QLabel) if w.pixmap() is not None
         and not w.pixmap().isNull()]
check(bool(icons), "卡片里有图标", "%d 个" % len(icons))
if icons:
    pm = icons[0].pixmap()
    check(pm.width() >= 40 and pm.height() >= 40,
          "图标尺寸正常", "%dx%d" % (pm.width(), pm.height()))

print("5) 卡片不会自己消失（由程序退出或装完后关闭）")
check(n.isVisible(), "显示后保持可见")
n.close()
for _ in range(3):
    app.processEvents()
check(not n.isVisible(), "调用关闭后消失")

print("6) 卡片停留时间与安装程序的等待对得上")
check(800 <= main.INSTALL_NOTICE_MS <= 4000, "停留时长在合理范围",
      "%d ms" % main.INSTALL_NOTICE_MS)
check(main.INSTALL_NOTICE_MS <= 3000, "不超过安装程序开始安装前的等待（3 秒）",
      "否则卡片还没消失文件就被动了")

print()
if FAILED:
    print("失败 %d 项：%s" % (len(FAILED), "；".join(FAILED)))
    sys.exit(1)
print("全部通过")
