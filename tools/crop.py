# -*- coding: utf-8 -*-
"""裁剪 + 放大一张图片，便于人工核对细节。

    python tools/crop.py <in.png> <out.png> x y w h [scale]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin

qt_env.setup()

from PyQt5.QtGui import QImage
from PyQt5.QtCore import Qt


def main(argv):
    if len(argv) < 7:
        print("用法: crop.py in.png out.png x y w h [scale]")
        return 2
    src, dst = argv[1], argv[2]
    x, y, w, h = (int(v) for v in argv[3:7])
    scale = int(argv[7]) if len(argv) > 7 else 3
    img = QImage(src)
    if img.isNull():
        print("读不到", src)
        return 1
    crop = img.copy(x, y, w, h).scaled(w * scale, h * scale,
                                       Qt.IgnoreAspectRatio, Qt.FastTransformation)
    crop.save(dst)
    print("saved", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
