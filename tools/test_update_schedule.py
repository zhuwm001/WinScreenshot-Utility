# -*- coding: utf-8 -*-
"""更新检查时机自检。

背景：曾经出现过「手动查过一次 -> 重启软件 -> 明明有新版本却不提示」，
原因是启动检查也看 6 小时节流，而手动检查会把时间戳刷新。

覆盖：
    1. 节流判定的边界（0 / 5 小时 / 6 小时整 / 7 小时）
    2. 启动检查不读节流时间戳（防止改回去）
    3. 设置页「上次检查」文案的几种情况

用法：
    python tools/test_update_schedule.py
"""
import datetime
import io
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt5.QtWidgets import QApplication            # noqa: E402

import main                                         # noqa: E402
from settings_dialog import SettingsDialog          # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


class FakeCfg:
    def __init__(self, ts):
        self._ts = ts

    def get(self, key, default=None):
        return self._ts if key == "update_last_check" else default


def main_():
    app = QApplication(sys.argv)      # noqa: F841
    now = time.time()
    print("更新检查时机自检")

    print("\n== 常驻期间的 6 小时节流 ==")
    check("从没查过 -> 该查", main.update_due(0, now=now) is True)
    check("5 小时前查过 -> 还不查", main.update_due(now - 5 * 3600, now=now) is False)
    check("6 小时整 -> 该查", main.update_due(now - 6 * 3600, now=now) is True)
    check("7 小时前查过 -> 该查", main.update_due(now - 7 * 3600, now=now) is True)
    check("时间戳是脏数据 -> 该查", main.update_due("oops", now=now) is True)

    print("\n== 启动检查不受节流影响 ==")
    src = io.open(main.__file__, encoding="utf-8").read()
    start = src.index("def _startup_update_check")
    end = src.index("def _schedule_update_check", start)
    body = src[start:end]
    check("启动检查里没有读 update_last_check",
          "update_last_check" not in body,
          "命中说明又被节流挡住了")
    check("启动检查只受「自动检查」开关控制",
          'config.get("check_update")' in body)
    check("启动时会调用启动检查（而不是节流那一路）",
          "self._startup_update_check()" in src)

    print("\n== 设置页「上次检查」文案 ==")
    txt = SettingsDialog._last_check_text(FakeCfg(0))
    check("没有记录", "还没有记录" in txt, txt)

    txt = SettingsDialog._last_check_text(FakeCfg(int(now)))
    check("今天", "今天" in txt, txt)

    yest = datetime.datetime.now() - datetime.timedelta(days=1)
    txt = SettingsDialog._last_check_text(FakeCfg(int(yest.timestamp())))
    check("昨天", "昨天" in txt, txt)

    old = datetime.datetime(2020, 1, 2, 3, 4)
    txt = SettingsDialog._last_check_text(FakeCfg(int(old.timestamp())))
    check("更早显示完整日期", "2020-01-02" in txt, txt)

    print("\n通过 %d，失败 %d" % (len(PASS), len(FAIL)))
    if FAIL:
        for n in FAIL:
            print("  失败：" + n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main_())
