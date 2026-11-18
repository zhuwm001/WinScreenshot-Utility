# -*- coding: utf-8 -*-
"""全局热键。

两级实现：

* 首选 ``WH_KEYBOARD_LL`` 低级键盘钩子 —— 它在系统把按键投递给前台程序之前执行，
  所以别的程序开着下拉框 / 右键菜单 / 模态弹窗时依然能拦到，而且可以把按键
  "吞掉"，前台程序不会因为收到 Ctrl+Alt+A 而把自己的弹窗关掉。
  RegisterHotKey 在这些场景下并不总是可靠：前台窗口属于管理员权限进程时会被
  UIPI 挡掉，部分程序（含游戏、远程桌面、带键盘钩子的应用）也会先吃掉按键。
* 钩子装不上时退回 ``RegisterHotKey`` + Qt 原生事件过滤器。
"""
import ctypes
import time
from ctypes import wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter, QObject, QTimer, pyqtSignal

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

# ---- 低级键盘钩子相关 ----
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_LRESULT = ctypes.c_ssize_t

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                     wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = _LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM)]


_HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

# ---------------------------------------------------------------- 注入按键留痕
# 有的机器上，别的程序（划词翻译、剪贴板工具、键鼠宏、驱动）会在用户拖完选区后
# 自己塞一个 Ctrl+C 进前台窗口。遮罩收到就跟用户真的按了一样，截图当场被复制关闭，
# 于是表现成"工具条一闪就没了"。低级钩子能拿到 LLKHF_INJECTED 标志，
# 这里把"注入的按键"记下来，遮罩据此判断这一下该不该理。
LLKHF_INJECTED = 0x10

_INJECTED_KEYS = []          # [(monotonic 时刻, vkCode)]
_INJECTED_KEEP = 0.8         # 只留最近 0.8 秒，够覆盖事件排队


def _note_injected(vk: int):
    now = time.monotonic()
    _INJECTED_KEYS.append((now, int(vk)))
    while _INJECTED_KEYS and now - _INJECTED_KEYS[0][0] > _INJECTED_KEEP:
        _INJECTED_KEYS.pop(0)


def was_injected(vk: int, window: float = 0.35) -> bool:
    """最近 window 秒内有没有一条"别的程序注入"的 vk 按键。"""
    if not _INJECTED_KEYS:
        return False
    now = time.monotonic()
    for ts, k in reversed(_INJECTED_KEYS):
        if now - ts > window:
            break
        if k == int(vk):
            return True
    return False


def injected_count() -> int:
    """当前缓存里有多少条注入记录（测试用）。"""
    return len(_INJECTED_KEYS)


def clear_injected():
    _INJECTED_KEYS[:] = []


# ---------------------------------------------------------------- 键名映射
MODIFIER_ALIASES = {
    "CTRL": MOD_CONTROL, "CONTROL": MOD_CONTROL,
    "ALT": MOD_ALT,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN, "WINDOWS": MOD_WIN, "META": MOD_WIN, "SUPER": MOD_WIN,
}

SPECIAL_KEYS = {
    "PRINTSCREEN": 0x2C, "PRTSC": 0x2C, "SNAPSHOT": 0x2C,
    "INSERT": 0x2D, "INS": 0x2D, "DELETE": 0x2E, "DEL": 0x2E,
    "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PGUP": 0x21, "PAGEDOWN": 0x22, "PGDN": 0x22,
    "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "RETURN": 0x0D,
    "BACKSPACE": 0x08, "ESC": 0x1B, "ESCAPE": 0x1B,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "`": 0xC0, "~": 0xC0,
    "-": 0xBD, "_": 0xBD,
    "=": 0xBB, "+": 0xBB,
    "[": 0xDB, "{": 0xDB,
    "]": 0xDD, "}": 0xDD,
    "\\": 0xDC, "|": 0xDC,
    ";": 0xBA, ":": 0xBA,
    "'": 0xDE, '"': 0xDE,
    ",": 0xBC, "<": 0xBC,
    ".": 0xBE, ">": 0xBE,
    "/": 0xBF, "?": 0xBF,
}

# 反查：VK -> 显示名（仅用于从键盘事件生成字符串）
VK_NAMES = {
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
    0x21: "PageUp", 0x22: "PageDown", 0x20: "Space", 0x09: "Tab", 0x0D: "Enter",
    0x08: "Backspace", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0xC0: "`", 0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xDC: "\\",
    0xBA: ";", 0xDE: "'", 0xBC: ",", 0xBE: ".", 0xBF: "/",
}


def key_name_from_vk(vk: int) -> str:
    """把虚拟键码转成配置里使用的键名。"""
    if 0x70 <= vk <= 0x87:            # F1 - F24
        return "F%d" % (vk - 0x70 + 1)
    if 0x30 <= vk <= 0x39:            # 0-9
        return chr(vk)
    if 0x41 <= vk <= 0x5A:            # A-Z
        return chr(vk)
    if 0x60 <= vk <= 0x69:            # 小键盘 0-9
        return "Num%d" % (vk - 0x60)
    return VK_NAMES.get(vk, "")


def parse_sequence(sequence: str):
    """'Ctrl+Alt+A' -> (mods, vk)；无法解析时返回 (None, None)。"""
    if not sequence:
        return None, None
    mods = 0
    vk = None
    for raw in sequence.replace(" ", "").split("+"):
        if not raw:
            continue
        token = raw.upper()
        if token in MODIFIER_ALIASES:
            mods |= MODIFIER_ALIASES[token]
        elif token in SPECIAL_KEYS:
            vk = SPECIAL_KEYS[token]
        elif len(token) == 1 and (token.isalnum()):
            vk = ord(token)
        elif token.startswith("F") and token[1:].isdigit() and 1 <= int(token[1:]) <= 24:
            vk = 0x70 + int(token[1:]) - 1
        elif token.startswith("NUM") and token[3:].isdigit():
            vk = 0x60 + int(token[3:])
        else:
            return None, None
    if vk is None:
        return None, None
    return mods, vk


def normalize_sequence(sequence: str) -> str:
    """统一显示顺序：Ctrl+Alt+Shift+Win+Key"""
    if not sequence:
        return ""
    mods, vk = parse_sequence(sequence)
    if vk is None:
        return sequence
    parts = []
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    name = key_name_from_vk(vk)
    if not name:
        for k, v in SPECIAL_KEYS.items():
            if v == vk:
                name = k.title()
                break
    parts.append(name or "?")
    return "+".join(parts)


def contains_alt(sequence: str) -> bool:
    """组合键里是否含 Alt。

    含 Alt 的快捷键有个 Windows 层面的硬限制：别的软件展开多级菜单 / 下拉框时，
    Alt 一按下系统就把菜单收起来（低级键盘钩子连"吞掉这个键"都拦不住），
    等主键到达时画面里已经没有菜单了。所以界面上要就此提示用户。
    """
    mods, vk = parse_sequence(sequence)
    return vk is not None and bool(mods & MOD_ALT)


# ---------------------------------------------------------------- 低级键盘钩子
class _KeyboardHook(QObject):
    """WH_KEYBOARD_LL 钩子：系统把按键交给前台程序之前就会回调到这里。

    在回调里只做"是不是目标组合"的判断（要求极快，系统有超时限制：
    回调超过 LowLevelHooksTimeout（默认 300ms）钩子会被静默摘掉），
    真正的动作通过 QTimer.singleShot(0) 挪回事件循环执行。

    注意：回调里只能做键位匹配，绝对不能抓屏 —— 抓屏要几十毫秒，
    放在回调里会让钩子被系统摘掉，热键就"失灵"了。
    """

    triggered = pyqtSignal()

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        self._mods = 0
        self._vk = None
        self._enabled = True
        self._holding = False        # 已经吞下按下、还在等抬起（忽略长按重复）
        self._proc = _HOOKPROC(self._hook_proc)   # 必须一直持有，否则被回收后崩溃
        self._hhook = None
        self._install()

    # ---------- 安装 / 卸载 ----------
    def _install(self):
        try:
            hmod = kernel32.GetModuleHandleW(None)
            self._hhook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, hmod, 0)
        except Exception:
            self._hhook = None
        return bool(self._hhook)

    @property
    def available(self) -> bool:
        return bool(self._hhook)

    def close(self):
        if self._hhook:
            try:
                user32.UnhookWindowsHookEx(self._hhook)
            except Exception:
                pass
            self._hhook = None

    def refresh(self) -> bool:
        """自检并重装钩子。

        Windows 规定低级钩子回调超过 LowLevelHooksTimeout（默认 300ms）就会被
        静默移除，之后热键就"失灵"了。定时重装一次，避免出现这种假死。
        先装新的再撤旧的，中间不会有空窗。
        """
        old = self._hhook
        new = self._install()
        if new and old:
            try:
                user32.UnhookWindowsHookEx(old)
            except Exception:
                pass
        elif old and not new:
            self._hhook = old          # 新装失败就留着旧的
        self._holding = False
        return bool(self._hhook)

    # ---------- 配置 ----------
    def set_sequence(self, mods: int, vk: int):
        self._mods = int(mods)
        self._vk = int(vk) if vk is not None else None
        self._holding = False

    def clear_sequence(self):
        self._vk = None
        self._holding = False
        self._mods = 0

    def set_enabled(self, on: bool):
        self._enabled = bool(on)

    # ---------- 回调 ----------
    def _hook_proc(self, n_code, w_param, l_param):
        if n_code < 0:
            return user32.CallNextHookEx(None, n_code, w_param, l_param)
        try:
            kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            vk = int(kb.vkCode)
            # 先留痕：注入的按键不论是不是我们的热键，都要能被遮罩那边查到
            if kb.flags & LLKHF_INJECTED:
                _note_injected(vk)

            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if self._holding and vk == self._vk:
                    return 1                     # 长按自动重复：继续吞掉，不再触发
                if self._enabled and self._vk is not None and vk == self._vk \
                        and _mods_down() == self._mods:
                    self._holding = True
                    QTimer.singleShot(0, self._fire)
                    return 1                     # 吞掉按键：前台程序收不到，弹窗不会被关掉
            elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                if self._holding and vk == self._vk:
                    self._holding = False
                    return 1
        except Exception:
            pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _fire(self):
        if self._enabled:
            self.triggered.emit()


def _mods_down() -> int:
    """当前按住的修饰键（钩子里拿不到，只能查异步键盘状态）。"""
    mods = 0
    if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
        mods |= MOD_CONTROL
    if user32.GetAsyncKeyState(VK_MENU) & 0x8000:
        mods |= MOD_ALT
    if user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
        mods |= MOD_SHIFT
    if (user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or \
            (user32.GetAsyncKeyState(VK_RWIN) & 0x8000):
        mods |= MOD_WIN
    return mods


# ---------------------------------------------------------------- 管理器
class _NativeFilter(QAbstractNativeEventFilter):
    """独立的原生事件过滤器。

    注意：不能与 QObject 多重继承，否则 PyQt 不会回调 nativeEventFilter。
    """

    def __init__(self, manager):
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, event_type, message):
        return self._manager.handle_native_event(event_type, message)


class HotkeyManager(QObject):
    """全局热键，触发时发出 activated 信号。

    两条路同时上：
    * 低级键盘钩子 —— 能抢在前台程序之前拿到按键并"吞掉"，菜单/下拉框
      打开时也不会把人家关掉；
    * RegisterHotKey —— 作为兜底。钩子万一被系统悄悄摘掉、或被其它程序
      的安全策略挡住时，系统热键依然能唤起截图。
    两条路都触发时用 300ms 去重，不会截两次。
    """

    activated = pyqtSignal()
    _HOTKEY_ID = 0xA1B2
    _PROBE_ID = 0xA1B9
    _DEDUPE = 0.30

    def __init__(self, app):
        QObject.__init__(self, app)
        self._app = app
        self._registered = False
        self._current = ""            # 当前已注册的规范化字符串
        self._mods = 0
        self._vk = None
        self._backup_ok = False       # RegisterHotKey 兜底是否生效
        self._last_fire = 0.0
        self._enabled = True
        self._filter = _NativeFilter(self)
        app.installNativeEventFilter(self._filter)

        self._hook = _KeyboardHook(self)
        self._hook.triggered.connect(self._fire)
        self._using_hook = self._hook.available

        # 钩子有被系统静默移除的可能，定期自检重装
        self._keepalive = QTimer(self)
        self._keepalive.timeout.connect(self._refresh_hook)
        if self._using_hook:
            self._keepalive.start(15000)

    def _fire(self):
        """统一出口：钩子和系统热键都可能触发，这里去重。"""
        now = time.time()
        if now - self._last_fire < self._DEDUPE:
            return
        self._last_fire = now
        self.activated.emit()

    # ---------- 兜底热键 ----------
    def _install_backup(self):
        """再注册一份系统热键，作为钩子失效时的兜底。"""
        self._clear_backup()
        if not self._registered or self._vk is None or not self._enabled:
            return
        try:
            self._backup_ok = bool(user32.RegisterHotKey(
                None, self._HOTKEY_ID, self._mods | MOD_NOREPEAT, self._vk))
        except Exception:
            self._backup_ok = False

    def _clear_backup(self):
        if self._backup_ok:
            try:
                user32.UnregisterHotKey(None, self._HOTKEY_ID)
            except Exception:
                pass
        self._backup_ok = False

    def _refresh_hook(self):
        if not self._hook.refresh():
            # 重装失败（极少见）就退回纯 RegisterHotKey，保证还能用
            self._using_hook = False
            self._keepalive.stop()
            self._install_backup()

    # ---------- 原生消息（兜底路径） ----------
    def handle_native_event(self, event_type, message):
        try:
            et = bytes(event_type)
        except Exception:
            et = event_type
        if et in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == self._HOTKEY_ID:
                    self._fire()
                    return True, 0
            except Exception:
                pass
        return False, 0

    # ---------- 注册 ----------
    @staticmethod
    def _probe(mods: int, vk: int):
        """只探测组合是否被别的程序注册（不改变状态）。返回 (可用, 错误码)。"""
        ctypes.set_last_error(0)
        if user32.RegisterHotKey(None, HotkeyManager._PROBE_ID, mods | MOD_NOREPEAT, vk):
            user32.UnregisterHotKey(None, HotkeyManager._PROBE_ID)
            return True, 0
        return False, ctypes.get_last_error()

    def can_register(self, sequence: str) -> bool:
        """试注册一次判断是否被占用（不改变当前状态）。"""
        ok, _ = self.probe_conflict(sequence)
        return ok

    def probe_conflict(self, sequence: str):
        """只探测、不动现有热键。返回 (可用, 给用户看的提示)。

        设置里录完组合键后 0.3 秒就会调一次，所以这里**绝对不能**改
        self._registered / self._hook 的任何状态 —— 用户还在犹豫，随时可能按取消。
        """
        mods, vk = parse_sequence(sequence)
        if vk is None:
            return False, "无法识别的快捷键，请重新设置"
        # 系统约定：至少需要一个修饰键，否则会拦截普通输入
        if mods == 0:
            return False, "快捷键至少需要包含 Ctrl / Alt / Shift / Win 中的一个"
        ok, err = self._probe(mods, vk)
        if ok:
            return True, ""
        name = normalize_sequence(sequence)
        if err and err != ERROR_HOTKEY_ALREADY_REGISTERED:
            return False, "快捷键 %s 注册失败（错误码 %d），请更换其他组合" % (name, err)
        return False, "快捷键 %s 已被其他程序占用，请重新设置" % name

    def register(self, sequence: str):
        """注册热键。返回 (成功与否, 提示信息)。失败时保持原热键不变。"""
        mods, vk = parse_sequence(sequence)
        if vk is None:
            return False, "无法识别的快捷键，请重新设置"
        if mods == 0:
            return False, "快捷键至少需要包含 Ctrl / Alt / Shift / Win 中的一个"

        new_seq = normalize_sequence(sequence)
        if self._registered and new_seq == self._current:
            return True, ""

        old_seq = self._current
        old_valid = self._registered

        # 先探测占用，避免和别的程序重复响应
        ok, err = self._probe(mods, vk)
        if not ok:
            msg = "快捷键 %s 已被其他程序占用，请重新设置" % new_seq
            if err and err != ERROR_HOTKEY_ALREADY_REGISTERED:
                msg = "快捷键 %s 注册失败（错误码 %d），请更换其他组合" % (new_seq, err)
            return False, msg

        if old_valid:
            self.unregister()

        if self._using_hook:
            self._hook.clear_sequence()
            self._hook.set_sequence(mods, vk)
        else:
            if not user32.RegisterHotKey(None, self._HOTKEY_ID, mods | MOD_NOREPEAT, vk):
                if old_valid and old_seq:
                    self._restore(old_seq)
                return False, "快捷键 %s 注册失败，请更换其他组合" % new_seq

        self._mods, self._vk = mods, vk
        self._registered = True
        self._current = new_seq
        if self._using_hook:
            # 钩子可用时再挂一份系统热键兜底：万一钩子被系统摘掉，
            # 快捷键依然能唤起截图（就是老版本的行为）
            self._install_backup()
        return True, ""

    def _restore(self, sequence: str):
        mods, vk = parse_sequence(sequence)
        if vk is None:
            return
        if self._using_hook:
            self._hook.set_sequence(mods, vk)
        else:
            user32.RegisterHotKey(None, self._HOTKEY_ID, mods | MOD_NOREPEAT, vk)
        self._mods, self._vk = mods, vk
        self._registered = True
        self._current = normalize_sequence(sequence)
        if self._using_hook:
            self._install_backup()

    def unregister(self):
        self._clear_backup()
        if self._using_hook:
            self._hook.clear_sequence()
        else:
            user32.UnregisterHotKey(None, self._HOTKEY_ID)
        self._registered = False
        self._mods, self._vk = 0, None
        self._current = ""

    def set_enabled(self, on: bool):
        """临时关掉触发（例如在设置里录快捷键时，避免按到旧组合就截图）。"""
        self._enabled = bool(on)
        self._hook.set_enabled(on)
        if on:
            if self._registered:
                self._install_backup()
        else:
            self._clear_backup()

    def close(self):
        self.unregister()
        self._hook.close()

    @property
    def using_hook(self) -> bool:
        return self._using_hook

    @property
    def current(self) -> str:
        return self._current
