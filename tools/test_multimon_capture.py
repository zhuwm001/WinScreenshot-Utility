# -*- coding: utf-8 -*-
"""多显示器抓屏自检：逐屏确认"不是黑的"。

用法：
    python tools/test_multimon_capture.py [输出目录]

和主程序保持一致的运行条件（DPI 感知 + Qt 缩放），这样在"主屏 150% + 副屏 100%"
这种混合缩放的机器上跑，才是真实场景。

判定：
    1. 每台显示器在自己的区域内，采样点里纯黑比例 < 2%
    2. 拼图尺寸 = 逻辑尺寸 × DPI 比例（允许 ±2px）
    3. 每块屏抓到的内容和它自己的原生抓图一致（抽样比对，验证没有错位/串屏）
    4. patch_region 补抓的一小块与整屏抓的内容一致
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

from PyQt5.QtCore import QRect, Qt                     # noqa: E402
from PyQt5.QtGui import QImage, QPixmap              # noqa: E402
from PyQt5.QtWidgets import QApplication             # noqa: E402

import screenshot as sc                              # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def dark_ratio(img: QImage, rect: QRect) -> float:
    rect = rect.intersected(img.rect())
    if rect.isEmpty():
        return 1.0
    step = max(1, int((rect.width() * rect.height() / 8000.0) ** 0.5))
    dark = total = 0
    for y in range(rect.top(), rect.bottom() + 1, step):
        for x in range(rect.left(), rect.right() + 1, step):
            c = img.pixel(x, y)
            if (c & 0xFF) < 8 and ((c >> 8) & 0xFF) < 8 and ((c >> 16) & 0xFF) < 8:
                dark += 1
            total += 1
    return dark / float(max(1, total))


def mean_diff(a: QImage, ra: QRect, b: QImage, rb: QRect) -> float:
    """两块区域缩放到同尺寸后抽样比对平均像素差（0~255）。"""
    ra = ra.intersected(a.rect())
    rb = rb.intersected(b.rect())
    if ra.isEmpty() or rb.isEmpty():
        return 255.0
    n = 400
    total = 0.0
    for i in range(n):
        fx = (i % 20) / 19.0
        fy = (i // 20) / 19.0
        ca = a.pixel(ra.left() + int(fx * (ra.width() - 1)),
                     ra.top() + int(fy * (ra.height() - 1)))
        cb = b.pixel(rb.left() + int(fx * (rb.width() - 1)),
                     rb.top() + int(fy * (rb.height() - 1)))
        total += (abs((ca & 0xFF) - (cb & 0xFF))
                  + abs(((ca >> 8) & 0xFF) - ((cb >> 8) & 0xFF))
                  + abs(((ca >> 16) & 0xFF) - ((cb >> 16) & 0xFF))) / 3.0
    return total / n


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "multimon")
    os.makedirs(outdir, exist_ok=True)

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

    mons = sc.enum_monitors()
    print("显示器 %d 台：" % len(mons))
    for m in mons:
        print("   %-14s 物理=%s  primary=%s"
              % (m["device"], m["rect"].getRect(), m["primary"]))

    print("\nQt 侧（逻辑坐标 / 缩放比例）：")
    for s in app.screens():
        print("   %-14s geo=%s dpr=%.2f"
              % (s.name(), s.geometry().getRect(), s.devicePixelRatio()))

    print("\n== 整屏抓取 ==")
    shot, vg = sc.grab_virtual_desktop()
    check("抓到了图", not shot.isNull(), "%dx%d" % (shot.width(), shot.height()))
    check("逻辑矩形非空", not vg.isEmpty(), str(vg.getRect()))

    dpr = float(shot.devicePixelRatio()) or 1.0
    exp_w = int(round(vg.width() * dpr))
    exp_h = int(round(vg.height() * dpr))
    check("拼图尺寸符合预期",
          abs(shot.width() - exp_w) <= 2 and abs(shot.height() - exp_h) <= 2,
          "实际 %dx%d / 期望 %dx%d" % (shot.width(), shot.height(), exp_w, exp_h))

    img = shot.toImage()
    img.save(os.path.join(outdir, "composite.png"))
    print("   拼图已存：%s" % os.path.join(outdir, "composite.png"))

    mons_by_name = dict((m["device"], m) for m in mons)
    collected = []
    for i, s in enumerate(app.screens()):
        geo = s.geometry()
        rel = geo.translated(-vg.x(), -vg.y())
        area = QRect(int(round(rel.x() * dpr)), int(round(rel.y() * dpr)),
                     int(round(rel.width() * dpr)), int(round(rel.height() * dpr)))
        ratio = dark_ratio(img, area)
        collected.append((s, area, ratio, i))
        img.copy(area).save(os.path.join(outdir, "screen_%d.png" % i))

        # 与原生逐屏抓图比对：验证内容没串屏、没缩放错位
        mon = mons_by_name.get(s.name())
        if mon:
            native = sc.grab_monitor_rect(mon)
            d = mean_diff(img, area, native, native.rect())
            check("%s 内容与原生一致" % s.name(), d < 12,
                  "平均像素差 %.1f" % d)

    # 锁屏 / 熄屏 / 远程桌面断开时整个桌面都是黑的，这种状态没法判断内容
    if collected and all(r >= 0.99 for _, _, r, _ in collected):
        print("   （当前屏幕全黑：锁屏 / 熄屏 / 远程断开，跳过画面内容检查）")
    else:
        for s, area, ratio, _ in collected:
            check("%s 不是黑屏" % s.name(), ratio < 0.02,
                  "纯黑占比 %.1f%%  区域=%s dpr=%.2f"
                  % (ratio * 100, area.getRect(), s.devicePixelRatio()))

    print("\n== DesktopShot.patch（补抓一小块）==")
    probe_logical = None
    if app.screens():
        g0 = app.screens()[0].geometry()
        probe_logical = QRect(g0.x() + 30, g0.y() + 30, 160, 100)
    if probe_logical is not None:
        phys = sc.logical_to_physical(probe_logical)
        check("逻辑->物理换算合理", not phys.isEmpty(), str(phys.getRect()))

        desk_a = sc.capture_desktop()
        desk_b = sc.capture_desktop()
        desk_b.patch(probe_logical)          # 补抓这一块（画面没变，结果应和整屏抓一致）
        a = desk_a.composite().toImage()
        b = desk_b.composite().toImage()
        rel = probe_logical.translated(-vg.x(), -vg.y())
        area = QRect(int(rel.x() * dpr), int(rel.y() * dpr),
                     int(rel.width() * dpr), int(rel.height() * dpr))
        d = mean_diff(a, area, b, area)
        check("补抓内容与全屏一致", d < 12, "平均像素差 %.1f" % d)

    print("\n%s：%d 项通过，%d 项失败"
          % ("全部通过" if not FAIL else "有失败项", len(PASS), len(FAIL)))
    for f in FAIL:
        print("   - " + f)
    print("图片目录：%s" % outdir)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
