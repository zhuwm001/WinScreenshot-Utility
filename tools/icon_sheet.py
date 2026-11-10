# -*- coding: utf-8 -*-
"""把图标按大尺寸画到深色底上，方便肉眼检查细节。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import PyQt5  # noqa: E402
_PLUG = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_PLUGIN_PATH"] = _PLUG
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_PLUG, "platforms")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
import icons  # noqa: E402

kinds = ["rect", "ellipse", "arrow", "text", "color", "undo", "pin", "save", "copy", "close"]
big = 96
cell = big + 30
sheet = QPixmap(cell * len(kinds), cell + 40)
sheet.fill(QColor("#18181C"))
p = QPainter(sheet)
p.setRenderHint(QPainter.SmoothPixmapTransform, True)
for i, k in enumerate(kinds):
    pm = icons.render(k, big, QColor("#FFFFFF"), 2.2)
    p.drawPixmap(i * cell + 15, 15, big, big, pm)
    p.setPen(QColor("#9AA3B2"))
    f = p.font()
    f.setPixelSize(14)
    p.setFont(f)
    p.drawText(i * cell + 15, cell + 20, k)
p.end()
sheet.save(os.path.join(ROOT, "build", "icon_sheet.png"))
print("saved", sheet.width(), "x", sheet.height())
