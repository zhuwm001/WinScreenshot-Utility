# -*- coding: utf-8 -*-
"""把主界面预览的标题栏放大，检查图标清晰度。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
img = QImage(os.path.join(ROOT, "build", "preview_main.png"))
crop = img.copy(300, 20, 140, 60)
crop = crop.scaled(crop.width() * 3, crop.height() * 3, Qt.KeepAspectRatio,
                   Qt.SmoothTransformation)
out = os.path.join(ROOT, "build", "titlebar_zoom.png")
crop.save(out)
print("saved", out)
