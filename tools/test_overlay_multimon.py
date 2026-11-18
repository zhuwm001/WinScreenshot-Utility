# -*- coding: utf-8 -*-
"""多屏遮罩渲染自检（不依赖屏幕当前画面）。

思路：给每块屏喂一张**合成图**（带彩色网格 + 屏名），再让遮罩把它画出来，
然后用 ``QWidget.grab()`` 把遮罩自己的渲染结果拿回来逐像素比对。
这样锁屏、熄屏、远程桌面里也能跑，结果是确定的。

验证内容：
    1. 混合缩放 -> 一屏一个遮罩；统一缩放 -> 单个遮罩
    2. 每块遮罩的几何 = 对应屏幕的逻辑矩形
    3. 遮罩画出来的图 = 原图压暗后的样子（位置、缩放、有无黑块）
    4. 真实抓屏接口能拿到每块屏的原生像素

用法：
    python tools/test_overlay_multimon.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

from PyQt5.QtCore import QPoint, QRect, QRectF, Qt              # noqa: E402
from PyQt5.QtGui import (QColor, QFont, QImage, QPainter, QPen,  # noqa: E402
                         QPixmap)
from PyQt5.QtWidgets import QApplication                        # noqa: E402

import screenshot as sc                                         # noqa: E402
from overlay import CaptureSession, DIM_COLOR                   # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def make_pattern(w, h, tag, hue):
    """造一张有辨识度的测试图：色块底 + 网格 + 大字。"""
    pm = QPixmap(max(1, w), max(1, h))
    pm.fill(QColor.fromHsv(hue % 360, 90, 200))
    p = QPainter(pm)
    p.setPen(QPen(QColor(255, 255, 255, 150), 2))
    step = max(40, pm.width() // 12)
    for x in range(0, pm.width(), step):
        p.drawLine(x, 0, x, pm.height())
    for y in range(0, pm.height(), step):
        p.drawLine(0, y, pm.width(), y)
    p.setPen(QPen(QColor(20, 20, 20)))
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(max(18, pm.height() // 12))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, pm.width(), pm.height()), int(Qt.AlignCenter), tag)
    p.end()
    return pm


def compare(grabbed, expected, skip=None):
    """比对（expected 已压暗），返回 (吻合率, 平均亮度)。"""
    if grabbed.isNull() or expected.isNull():
        return 0.0, 0.0
    dim = 1.0 - DIM_COLOR.alpha() / 255.0
    w = min(grabbed.width(), expected.width())
    h = min(grabbed.height(), expected.height())
    n = ok = 0
    tot = 0.0
    for i in range(1600):
        fx = (i % 40) / 39.0
        fy = (i // 40) / 39.0
        x = int(fx * (w - 1))
        y = int(fy * (h - 1))
        if skip is not None and skip.contains(QPoint(x, y)):
            continue
        ca = grabbed.pixel(x, y)
        cb = expected.pixel(x, y)
        act = [(ca >> s) & 0xFF for s in (0, 8, 16)]
        exp = [((cb >> s) & 0xFF) * dim for s in (0, 8, 16)]
        tot += sum(act) / 3.0
        d = sum(abs(e - v) for e, v in zip(exp, act)) / 3.0
        if d <= 18:
            ok += 1
        n += 1
    return ok / float(max(1, n)), tot / float(max(1, n))


def main():
    level = sc.set_process_dpi_awareness()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    app = QApplication(sys.argv)
    print("DPI 感知级别：%s" % level)

    screens = app.screens()
    print("共 %d 块屏：" % len(screens))
    for s in screens:
        print("   %-14s geo=%s dpr=%.2f"
              % (s.name(), s.geometry().getRect(), s.devicePixelRatio()))

    vg = QRect()
    for s in screens:
        vg = vg.united(s.geometry())

    dpr0 = float(screens[0].devicePixelRatio())
    pairs = []
    for i, s in enumerate(screens):
        geo = s.geometry()
        dpr = float(s.devicePixelRatio()) or 1.0
        pm = make_pattern(int(geo.width() * dpr), int(geo.height() * dpr),
                          "屏%d" % (i + 1), 30 + i * 80)
        pm.setDevicePixelRatio(dpr)
        pairs.append((s, pm))

    print("\n== 混合缩放模式 ==")
    desk = sc.DesktopShot(vg, pairs, dpr0)
    expect_n = len(pairs) if desk.is_mixed else 1
    session = CaptureSession(desk, "#FF3B30", 20, False)
    check("遮罩数量", len(session.overlays) == expect_n,
          "is_mixed=%s 实际 %d / 期望 %d"
          % (desk.is_mixed, len(session.overlays), expect_n))
    session.show_overlay()
    app.processEvents()

    for ov in session.overlays:
        g = ov.geometry()
        owner = None
        for s, _ in pairs:
            if s.geometry() == g:
                owner = s
        print("   遮罩 %-16s dpr=%.2f" % (g.getRect(), ov._shot.devicePixelRatio()))
        if owner is None:
            check("遮罩几何贴合某块屏", False, str(g.getRect()))
            continue
        shot = ov._shot.toImage()
        shot.setDevicePixelRatio(1.0)
        got = ov.grab()
        got.setDevicePixelRatio(1.0)
        skip = None
        if ov._show_hint:
            skip = QRect(0, int(g.height() * 0.09), int(g.width()),
                         int(g.height() * 0.10))
        ratio, bright = compare(got.toImage(), shot, skip)
        check("%s 遮罩内容正确" % owner.name(),
              ratio >= 0.90 and bright > 20,
              "吻合率 %.0f%%  平均亮度 %.0f" % (ratio * 100, bright))

    for ov in session.overlays:
        try:
            ov.close()
        except RuntimeError:
            pass
    session._overlays = []
    app.processEvents()

    print("\n== 统一缩放模式（单个遮罩覆盖全桌面）==")
    desk2 = sc.DesktopShot(vg, pairs, dpr0, mixed=False)   # 强制单遮罩分支
    session2 = CaptureSession(desk2, "#FF3B30", 20, False)
    check("只有一个遮罩", len(session2.overlays) == 1,
          "实际 %d" % len(session2.overlays))
    session2.show_overlay()
    app.processEvents()
    if session2.overlays:
        ov = session2.overlays[0]
        panel = ov._shot.toImage()
        panel.setDevicePixelRatio(1.0)
        got = ov.grab()
        got.setDevicePixelRatio(1.0)
        skip = QRect(0, int(vg.height() * 0.09), int(vg.width()),
                     int(vg.height() * 0.10))
        ratio, bright = compare(got.toImage(), panel, skip)
        check("整屏遮罩内容正确", ratio >= 0.90 and bright > 20,
              "吻合率 %.0f%%  平均亮度 %.0f" % (ratio * 100, bright))
        try:
            ov.close()
        except RuntimeError:
            pass
    session2._overlays = []
    app.processEvents()

    print("\n== 真实抓屏接口 ==")
    live = sc.capture_desktop()
    check("每块屏都拿到原生图",
          len(live.screens) == len(screens) and
          all(pm is not None and not pm.isNull() for _, pm in live.screens),
          "%d / %d" % (len(live.screens), len(screens)))
    blank = 0
    for s, pm in live.screens:
        img = pm.toImage()
        n = 0
        tot = 0.0
        for i in range(400):
            x = int((i % 20) / 19.0 * (img.width() - 1))
            y = int((i // 20) / 19.0 * (img.height() - 1))
            c = img.pixel(x, y)
            tot += ((c & 0xFF) + ((c >> 8) & 0xFF) + ((c >> 16) & 0xFF)) / 3.0
            n += 1
        bright = tot / max(1, n)
        print("   %-14s %dx%d 平均亮度 %.0f"
              % (s.name(), pm.width(), pm.height(), bright))
        if bright < 3:
            blank += 1
    if blank == len(live.screens) and blank > 0:
        print("   （屏幕当前是锁屏 / 熄屏 / 远程断开状态，全黑属正常，接口调用本身没报错）")

    print("\n%s：%d 项通过，%d 项失败"
          % ("全部通过" if not FAIL else "有失败项", len(PASS), len(FAIL)))
    for f in FAIL:
        print("   - " + f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
