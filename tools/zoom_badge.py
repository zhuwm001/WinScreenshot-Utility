# -*- coding: utf-8 -*-
"""把主界面底部的徽标放大，检查小尺寸下的清晰度。"""
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
crop = img.copy(160, 230, 160, 60)
crop = crop.scaled(crop.width() * 3, crop.height() * 3, Qt.KeepAspectRatio,
                   Qt.SmoothTransformation)
crop.save(os.path.join(ROOT, "build", "badge_zoom.png"))
print("ok")
