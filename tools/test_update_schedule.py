# -*- coding: utf-8 -*-
"""更新检查时机自检。

背景：曾经出现过「重新打开软件 -> 明明有新版本却没提示」。根因有两个：
    1. 托盘程序「重新打开」只是唤醒已有进程，进程根本没重启，启动检查不跑；
    2. 启动检查与定时检查各写了一套判断，容易改着改着就断了。

现在的规则（用户确认过）：
    启动进程查一次、常驻每 12 小时查一次、手动随时查；
    托盘里再打开一次（唤醒已有进程）**不查** —— 那不是新会话。

所有入口都走 request_update_check() + check_allowed() 一套判断。

覆盖：
    1. 12 小时节流的边界
    2. 三种触发来源的放行规则
    3. 接线检查（谁调用谁，防止再分裂出第二套判断）
    4. 设置页「上次检查」文案（时间 + 结果）
    5. 更新结果回执（决定弹不弹「更新完成」）

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
    def __init__(self, ts, result=""):
        self._ts = ts
        self._result = result

    def get(self, key, default=None):
        if key == "update_last_check":
            return self._ts
        if key == "update_last_result":
            return self._result
        return default


def main_():
    app = QApplication(sys.argv)      # noqa: F841
    now = time.time()
    print("更新检查时机自检")

    print("\n== 常驻期间的 12 小时节流 ==")
    check("间隔常量是 12 小时", main.UPDATE_INTERVAL == 12 * 3600,
          str(main.UPDATE_INTERVAL))
    check("从没查过 -> 该查", main.update_due(0, now=now) is True)
    check("11 小时前查过 -> 还不查", main.update_due(now - 11 * 3600, now=now) is False)
    check("11 小时 59 分 -> 还不查",
          main.update_due(now - (12 * 3600 - 60), now=now) is False)
    check("12 小时整 -> 该查", main.update_due(now - 12 * 3600, now=now) is True)
    check("13 小时前查过 -> 该查", main.update_due(now - 13 * 3600, now=now) is True)
    check("时间戳是脏数据 -> 该查", main.update_due("oops", now=now) is True)

    print("\n== 三种触发来源共用一套判断 ==")
    # 启动：每次启动都查，不看节流
    check("启动：刚查过也要查",
          main.check_allowed(main.CHECK_STARTUP, last_ts=now - 60, now=now) is True)
    check("启动：关掉自动检查就不查",
          main.check_allowed(main.CHECK_STARTUP, now=now, enabled=False) is False)
    # 定时
    check("定时：不到 12 小时不查",
          main.check_allowed(main.CHECK_TIMER, last_ts=now - 3600, now=now) is False)
    check("定时：满 12 小时查",
          main.check_allowed(main.CHECK_TIMER, last_ts=now - 13 * 3600, now=now) is True)
    check("定时：关掉自动检查就不查",
          main.check_allowed(main.CHECK_TIMER, last_ts=0, now=now, enabled=False) is False)
    # 手动
    check("手动：随时查",
          main.check_allowed(main.CHECK_MANUAL, last_ts=now, now=now) is True)
    check("手动：关掉自动检查也能查",
          main.check_allowed(main.CHECK_MANUAL, now=now, enabled=False) is True)
    check("只有三种触发来源（没有第四种）",
          not hasattr(main, "CHECK_WAKE"))

    print("\n== 接线检查（防止再分裂出第二套判断） ==")
    src = io.open(main.__file__, encoding="utf-8").read()
    start = src.index("def _startup_update_check")
    end = src.index("def _schedule_update_check", start)
    body = src[start:end]
    check("启动检查里没有读 update_last_check",
          "update_last_check" not in body,
          "命中说明又被节流挡住了")
    check("启动检查走统一入口（CHECK_STARTUP）",
          "request_update_check(CHECK_STARTUP)" in body)
    check("启动检查不用等太久", main.UPDATE_DELAY_MS <= 3000,
          "%d ms" % main.UPDATE_DELAY_MS)
    sched = src[src.index("def _schedule_update_check"):
                src.index("def request_update_check")]
    check("定时检查走统一入口（CHECK_TIMER）",
          "request_update_check(CHECK_TIMER)" in sched)
    check("托盘菜单走统一入口（CHECK_MANUAL）",
          "request_update_check(CHECK_MANUAL)" in src)
    # 「重新打开」= 唤醒已有进程，不是新会话，不该查
    wake = src[src.index("def _on_second_instance"):
               src.index("# ------------------------------------------------------------ 窗口")]
    check("唤醒已有进程时不查更新", "request_update_check" not in wake)
    tray = src[src.index("def _on_tray_activated"):src.index("def _on_second_instance")]
    check("从托盘打开窗口也不查更新", "request_update_check" not in tray)
    check("不再有第二套 check_updates 判断",
          "def check_updates" not in src)
    check("启动时启动了常驻轮询定时器", "self._update_timer.start()" in src)
    check("公共入口只有一处发请求", src.count("UpdateChecker(self)") == 1)
    check("每次检查的决定都进日志", "ulog(" in src)

    print("\n== 设置页「上次检查」文案 ==")
    txt = SettingsDialog._last_check_text(FakeCfg(0))
    check("没有记录", "暂无记录" in txt, txt)
    check("不把检查频率塞进设置页",
          "12 小时" not in SettingsDialog._last_check_text(FakeCfg(int(now))))

    txt = SettingsDialog._last_check_text(FakeCfg(int(now), "已是最新版本"))
    check("今天", "今天" in txt, txt)
    check("带上结果：已是最新版本", "已是最新版本" in txt, txt)

    txt = SettingsDialog._last_check_text(FakeCfg(int(now), "发现新版本 1.2.0"))
    check("带上结果：发现新版本", "发现新版本 1.2.0" in txt, txt)

    yest = datetime.datetime.now() - datetime.timedelta(days=1)
    txt = SettingsDialog._last_check_text(FakeCfg(int(yest.timestamp())))
    check("昨天", "昨天" in txt, txt)

    old = datetime.datetime(2020, 1, 2, 3, 4)
    txt = SettingsDialog._last_check_text(FakeCfg(int(old.timestamp())))
    check("更早显示完整日期", "2020-01-02" in txt, txt)

    print("\n== 检查结果文案 ==")
    check("发现新版本", main.check_result_text("found", "1.2.0") == "发现新版本 1.2.0")
    check("发现新版本但版本不明", main.check_result_text("found", "") == "发现新版本")
    check("已是最新", main.check_result_text("latest") == "已是最新版本")
    check("失败", main.check_result_text("failed") == "检查失败")
    check("失败时带上原因",
          main.check_result_text("failed", reason="连接 GitHub 超时。") ==
          "检查失败：连接 GitHub 超时", main.check_result_text("failed", reason="连接 GitHub 超时。"))
    check("原因太长要截断",
          len(main.check_result_text("failed", reason="啊" * 80)) < 40)
    check("未知不硬凑", main.check_result_text("") == "")
    check("短原因原样保留", main.short_reason("代理没开") == "代理没开")
    check("去掉句号", main.short_reason("超时。") == "超时")

    print("\n== 更新结果回执（决定弹不弹「更新完成」） ==")
    check("没有回执", main.update_outcome({}, "1.2.0") == "")
    check("版本不明不乱报", main.update_outcome({"version": ""}, "1.2.0") == "")
    check("装到了目标版本 -> 成功",
          main.update_outcome({"version": "1.2.0"}, "1.2.0") == "done")
    check("跨版本（比目标还新）-> 成功",
          main.update_outcome({"version": "1.2.0"}, "1.3.0") == "done")
    check("还停在旧版本 -> 失败",
          main.update_outcome({"version": "1.2.0"}, "1.1.9") == "failed")
    check("回到更早版本也算失败",
          main.update_outcome({"version": "1.2.0"}, "1.1.0") == "failed")

    print("\n== 其它接线 ==")
    check("启动时会回报更新结果", "self._notify_update_result)" in src)
    check("安装前会落回执", "write_pending(" in src)
    check("安装目录不可写时不硬静默", "install_dir_writable(" in src)

    print("\n通过 %d，失败 %d" % (len(PASS), len(FAIL)))
    if FAIL:
        for n in FAIL:
            print("  失败：" + n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main_())
