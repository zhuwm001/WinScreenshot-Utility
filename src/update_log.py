# -*- coding: utf-8 -*-
"""更新检查日志：%APPDATA%\\我爱截图\\update.log

「明明该提示新版本，却什么都没发生」这种事，光看界面是分辨不出来的：
到底没查、查失败了、还是查到了但判定为已是最新？三种情况界面上完全一样。
所以每次检查都往这个文件里记几行，出问题时把这个文件发出来就能定位。

日志只保留最近 MAX_LINES 行，不会无限长。任何写日志的异常都会被吞掉 ——
记日志是辅助功能，绝不能因为它把更新本身弄坏。
"""
import datetime
import os

from app_config import config_dir

MAX_LINES = 240
MAX_BYTES = 200 * 1024


def log_path() -> str:
    return os.path.join(config_dir(), "update.log")


def _trim(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_LINES:])
    except Exception:
        pass


def log(message: str):
    """写一行带时间戳的日志（同一个时间点连写多行也没问题）。"""
    try:
        path = log_path()
        is_new = not os.path.exists(path)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = "%s  %s\n" % (stamp, str(message).replace("\n", " "))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        if is_new or os.path.getsize(path) > MAX_BYTES:
            _trim(path)
    except Exception:
        pass


def read(max_lines: int = MAX_LINES):
    """读回最后若干行（给设置页「查看日志」用）。"""
    try:
        with open(log_path(), "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()[-max_lines:]
    except Exception:
        return []
