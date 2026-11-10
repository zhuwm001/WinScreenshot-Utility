# -*- coding: utf-8 -*-
"""窗口置前的 Win32 小工具。

Windows 有个"前台窗口锁"：不是当前前台进程的程序，调 SetForegroundWindow
往往只会让任务栏闪一下，窗口还是没激活 —— 对截图遮罩来说就是"界面出来了，
但按 Esc 没反应、回车不复制"。这里用两种常规手段绕过：
先把窗口临时置顶，再抢前台；抢不到就把自己的输入队列挂到当前前台线程上，
抢完再摘掉。
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040

user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.SwitchToThisWindow.restype = None
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD,
                               ctypes.POINTER(wintypes.ULONG)]
user32.GetActiveWindow.restype = wintypes.HWND
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002


def force_foreground(hwnd: int) -> bool:
    """把窗口顶到最前并激活，尽量保证它能收到键盘。

    依次尝试几种常规手段，前一种被系统的前台窗口锁挡住就换下一种。
    最后一种会"假装按一下 Alt"—— Windows 只要看到本进程刚产生过输入事件，
    就会放行 SetForegroundWindow。走这一步说明用户已经按过截图快捷键、
    画面也已经抓好了，所以这时候 Alt 把别人的菜单关掉没有影响。
    """
    if not hwnd:
        return False
    h = wintypes.HWND(hwnd)
    try:
        user32.SetWindowPos(h, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    except Exception:
        pass

    if user32.SetForegroundWindow(h):
        return True

    try:
        user32.SwitchToThisWindow(h, True)
    except Exception:
        pass
    if user32.GetForegroundWindow() == hwnd:
        return True

    fg = user32.GetForegroundWindow()
    if fg and fg != hwnd:
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        cur_tid = kernel32.GetCurrentThreadId()
        if fg_tid and fg_tid != cur_tid:
            if user32.AttachThreadInput(cur_tid, fg_tid, True):
                try:
                    user32.BringWindowToTop(h)
                    user32.SetForegroundWindow(h)
                finally:
                    user32.AttachThreadInput(cur_tid, fg_tid, False)
            if user32.GetForegroundWindow() == hwnd:
                return True

    # 最后手段：制造一次本进程的键盘输入事件，换取前台切换权限
    try:
        user32.keybd_event(VK_MENU, 0, 0, None)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, None)
    except Exception:
        pass
    return bool(user32.SetForegroundWindow(h))
