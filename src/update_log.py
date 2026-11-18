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


def crash_path() -> str:
    return os.path.join(config_dir(), "crash.log")


def folder() -> str:
    return config_dir()


def shots_dir() -> str:
    """剪贴板写不进去时兜底存的图，跟日志放一起。"""
    return os.path.join(config_dir(), "screenshots")


def existing_files():
    """目录里实际存在的日志文件，按该看的先后排好。

    排查时「运行与更新全流程」在 update.log，「崩溃与异常栈」在 crash.log，
    两个都要看，所以设置页打开的是目录而不是单个文件。
    """
    out = []
    for p in (log_path(), crash_path()):
        if os.path.exists(p):
            out.append(p)
    return out


def open_target():
    """设置页点「查看日志」时该打开什么：返回 (目录, 要选中的文件或 None)。"""
    files = existing_files()
    return folder(), (files[0] if files else None)


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


# 兜底截图是「剪贴板写不进去」时的救急文件，用户把图拿走后就没意义了。
# 一个截图 1–3MB，不设上限会一直攒，这是整个目录里唯一会无限增长的东西。
SHOT_KEEP = 20
SHOT_MAX_BYTES = 30 * 1024 * 1024


def prune_shots(keep: int = SHOT_KEEP, max_bytes: int = SHOT_MAX_BYTES) -> int:
    """只留最近 keep 张、总量不超过 max_bytes，超出的从最旧的删。返回删了几张。"""
    d = shots_dir()
    try:
        items = []
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if name.lower().endswith(".png") and os.path.isfile(p):
                items.append((os.path.getmtime(p), p))
    except Exception:
        return 0
    items.sort(reverse=True)          # 新的在前
    removed = 0
    total = 0
    for i, (_, p) in enumerate(items):
        try:
            size = os.path.getsize(p)
        except Exception:
            continue
        if i < keep and total + size <= max_bytes:
            total += size
            continue
        try:
            os.remove(p)
            removed += 1
        except Exception:
            pass
    return removed


def usage() -> dict:
    """当前占用：日志、崩溃记录、兜底截图各多少字节、几张图。"""
    def size_of(path):
        try:
            return os.path.getsize(path)
        except Exception:
            return 0

    shots = 0
    count = 0
    try:
        for name in os.listdir(shots_dir()):
            p = os.path.join(shots_dir(), name)
            if os.path.isfile(p):
                shots += size_of(p)
                count += 1
    except Exception:
        pass
    return {
        "log": size_of(log_path()),
        "log_old": size_of(log_path() + ".1"),
        "crash": size_of(crash_path()),
        "crash_old": size_of(crash_path() + ".1"),
        "shots": shots,
        "shot_count": count,
    }


def usage_text() -> str:
    """给设置页看的一句话占用说明。"""
    u = usage()
    total = u["log"] + u["log_old"] + u["crash"] + u["crash_old"] + u["shots"]
    if total <= 0:
        return "暂无日志记录"
    if total < 1024 * 1024:
        size = "共 %d KB" % max(1, int(round(total / 1024.0)))
    else:
        size = "共 %.1f MB" % (total / 1048576.0)
    parts = [size]
    if u["shot_count"]:
        parts.append("兜底图 %d 张" % u["shot_count"])
    return "　".join(parts)
