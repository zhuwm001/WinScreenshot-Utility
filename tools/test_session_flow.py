# -*- coding: utf-8 -*-
"""截图会话流程自检：框选 -> 回车复制 -> 所有遮罩关掉 -> 还能再来一次。

这条链路是多屏改造后最容易出问题的地方（遮罩从 1 个变成 N 个，
收尾时漏关一个，下次截图就会被"正在截图"的判断卡死）。

用合成图，QTest 直接给控件发鼠标/键盘事件，不依赖真实屏幕画面。

用法：
    python tools/test_session_flow.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt5.QtCore import QPoint, QRect, QRectF, Qt            # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPixmap             # noqa: E402
from PyQt5.QtTest import QTest                                # noqa: E402
from PyQt5.QtWidgets import QApplication                      # noqa: E402

import screenshot as sc                                       # noqa: E402
from overlay import CaptureSession                            # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def fake_pair(screen, hue):
    geo = screen.geometry()
    dpr = float(screen.devicePixelRatio()) or 1.0
    pm = QPixmap(int(geo.width() * dpr), int(geo.height() * dpr))
    pm.fill(QColor.fromHsv(hue % 360, 80, 190))
    p = QPainter(pm)
    p.setPen(QColor(255, 255, 255))
    p.drawLine(0, 0, pm.width(), pm.height())
    p.drawLine(pm.width(), 0, 0, pm.height())
    p.end()
    pm.setDevicePixelRatio(dpr)
    return screen, pm


def build_desk(app):
    vg = QRect()
    for s in app.screens():
        vg = vg.united(s.geometry())
    pairs = [fake_pair(s, 40 + i * 90) for i, s in enumerate(app.screens())]
    return sc.DesktopShot(vg, pairs, float(app.screens()[0].devicePixelRatio()))


def run_once(app, tag):
    """跑一次"框选 + 回车"，返回 (是否收到 finished, 图尺寸, 会话)。"""
    desk = build_desk(app)
    session = CaptureSession(desk, "#FF3B30", 20, False)
    got = {}
    session.finished.connect(lambda img: got.setdefault("img", img))
    session.closed.connect(lambda: got.setdefault("closed", True))
    session.show_overlay()
    app.processEvents()

    ov = session.overlays[0]
    dpr = float(ov._shot.devicePixelRatio()) or 1.0
    a = QPoint(40, 40)
    b = QPoint(240, 160)
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseMove(ov, b)
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, b)
    app.processEvents()

    sel = QRect(ov._sel)
    check("%s 框选生效" % tag, not sel.isNull(),
          "选区=%s" % str(sel.getRect()))

    QTest.keyClick(ov, Qt.Key_Return)
    app.processEvents()
    QTest.qWait(30)
    app.processEvents()

    img = got.get("img")
    check("%s 收到截图结果" % tag, img is not None and not img.isNull())
    if img is not None and not img.isNull():
        exp_w = int(round(sel.width() * dpr))
        exp_h = int(round(sel.height() * dpr))
        check("%s 输出尺寸按该屏 DPI 换算" % tag,
              abs(img.width() - exp_w) <= 2 and abs(img.height() - exp_h) <= 2,
              "实际 %dx%d / 期望 %dx%d (dpr=%.2f)"
              % (img.width(), img.height(), exp_w, exp_h, dpr))
    check("%s 所有遮罩都已关闭" % tag,
          not session.overlays and all(not o.isVisible() for o in []),
          "剩余 %d 个" % len(session.overlays))
    return session


def main():
    sc.set_process_dpi_awareness()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    app = QApplication(sys.argv)
    print("屏数：%d" % len(app.screens()))

    run_once(app, "第一次")
    # 再来一次：验证没有残留状态把第二次挡住
    run_once(app, "第二次")

    print("\n%s：%d 项通过，%d 项失败"
          % ("全部通过" if not FAIL else "有失败项", len(PASS), len(FAIL)))
    for f in FAIL:
        print("   - " + f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
