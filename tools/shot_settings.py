import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import qt_env  # noqa: E402

qt_env.setup()
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="shotcfg-")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv)

import settings_dialog as sd  # noqa: E402
import update_log  # noqa: E402
from app_config import config  # noqa: E402

update_log.log("设置页截图用的一行日志")

dlg = sd.SettingsDialog(config, lambda s: (True, ""))
dlg.show()
for _ in range(10):
    app.processEvents()
img = dlg.grab()
img.save(os.path.join(ROOT, "build", "diag_settings_log.png"))
print("size", dlg.width(), dlg.height())
print("chk_update", dlg.chk_update.geometry(), "可见", dlg.chk_update.isVisible())
print("占用文案", dlg.lbl_log_usage.text())
dlg.close()
