# -*- coding: utf-8 -*-
"""配置读写：%APPDATA%\\我爱截图\\config.json"""
import json
import os
import re

APP_NAME = "我爱截图"
APP_ID = "WoAiJieTu"
APP_VERSION = "1.2.5"

DEFAULTS = {
    "config_schema": 2,              # 配置结构版本，用于旧配置迁移
    "hotkey": "Ctrl+Shift+A",         # 截图快捷键（不含 Alt：Alt 组合截不到展开着的菜单）
    "hide_self": True,               # 截图时隐藏自身界面
    "close_action": "tray",          # 点关闭：tray=最小化到托盘 / exit=退出程序
    "pen_color": "#FF3B30",          # 标记颜色
    "text_size": 20,                 # 文字标注字号（像素）
    "text_bold": False,              # 文字标注是否粗体
    "auto_start": False,             # 开机自启
    "check_update": True,            # 自动检查新版本（启动一次 + 常驻每 12 小时）
    "update_last_check": 0,          # 上次检查更新的时间戳
    "update_last_result": "",        # 上次检查的结果（已是最新 / 发现新版本 x / 检查失败）
}

CURRENT_SCHEMA = 2

# 布尔型配置项：JSON 里被写成 null / "false" / 0 时统一按类型校正，
# 避免「配置里少了或写坏了」导致开关显示成关闭（例如自动检查更新默认是开的）。
BOOL_KEYS = ("hide_self", "auto_start", "text_bold", "check_update")

# 设置窗口里能改的项。恢复默认时就按这些键回滚。
# 其余键（update_last_check / update_last_result）是运行状态，不属于「设置」。
SETTING_KEYS = ("hotkey", "hide_self", "close_action", "auto_start",
                "check_update", "pen_color", "text_size", "text_bold")

# 纯运行状态：恢复默认不该把它们清掉（否则「上次检查」会变回暂无记录）
STATE_KEYS = ("update_last_check", "update_last_result")

COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def as_bool(value, fallback=False) -> bool:
    """把配置里的值规整成布尔；认不出来就用默认值。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
    return bool(fallback)


def as_choice(value, choices, fallback):
    """枚举型配置：不在候选里就用默认值（大小写、空白都容忍）。"""
    if isinstance(value, str):
        low = value.strip().lower()
        for c in choices:
            if low == str(c).lower():
                return c
    return fallback


def as_int(value, fallback: int, low: int = None, high: int = None) -> int:
    """整数型配置：转不动或越界就用默认值。"""
    try:
        num = int(value)
    except (TypeError, ValueError):
        return int(fallback)
    if low is not None and num < low:
        return int(fallback)
    if high is not None and num > high:
        return int(fallback)
    return num


def as_color(value, fallback: str) -> str:
    """#RRGGBB 形式的颜色；写坏了回默认，避免画出透明或黑块。"""
    if isinstance(value, str) and COLOR_RE.match(value.strip()):
        return value.strip().upper()
    return fallback


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


class Config:
    """极简配置容器，读写 JSON，带默认值兜底。"""

    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    # ---------- 基础 ----------
    def load(self):
        existed = os.path.exists(config_path())
        try:
            # utf-8-sig：别的编辑器/脚本存盘时可能带 BOM，容忍它
            with open(config_path(), "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                try:
                    old = int(data.get("config_schema", 1))
                except (TypeError, ValueError):
                    old = 1
                if old < CURRENT_SCHEMA:
                    # v1 的文字标注默认加粗，v2 起改成常规字重
                    data["text_bold"] = False
                    data["config_schema"] = CURRENT_SCHEMA
                for k, v in data.items():
                    if k in DEFAULTS:
                        self._data[k] = v
        except Exception:
            pass
        for key in BOOL_KEYS:
            self._data[key] = as_bool(self._data.get(key), DEFAULTS[key])
        # 其余设置项同样规整：配置被手工改坏时也回默认，而不是带着错值跑
        self._data["close_action"] = as_choice(
            self._data.get("close_action"), ("tray", "exit"), DEFAULTS["close_action"])
        self._data["text_size"] = as_int(
            self._data.get("text_size"), DEFAULTS["text_size"], 12, 96)
        self._data["pen_color"] = as_color(
            self._data.get("pen_color"), DEFAULTS["pen_color"])
        self._data["config_schema"] = CURRENT_SCHEMA
        hotkey = str(self._data.get("hotkey") or "").strip()
        self._data["hotkey"] = hotkey or DEFAULTS["hotkey"]
        if not existed:
            # 首次运行就把默认配置落盘：以后再读到的就是明确的值，
            # 不会出现「文件不存在」和「值写坏了」两种状态混在一起。
            self.save()

    def reset_settings(self):
        """把所有用户设置项恢复成默认值（不含运行状态）。"""
        for key in SETTING_KEYS:
            self._data[key] = DEFAULTS[key]

    def save(self):
        try:
            with open(config_path(), "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("保存配置失败:", e)

    # ---------- 访问 ----------
    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value


config = Config()
