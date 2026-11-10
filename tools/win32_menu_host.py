# -*- coding: utf-8 -*-
"""独立的 Win32 宿主程序：开一个窗口并弹出一套多级菜单，模拟"工程造价软件"。

菜单保持打开若干秒，把菜单/子菜单的屏幕矩形写到 build/menu_rects.json，
供测试脚本判断截图里有没有留住菜单。
"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "build")
os.makedirs(OUT, exist_ok=True)
INFO = os.path.join(OUT, "menu_rects.json")

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEX(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEX)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetMenuItemRect.argtypes = [wintypes.HWND, wintypes.HMENU, wintypes.UINT,
                                   ctypes.POINTER(wintypes.RECT)]
user32.GetMenuItemRect.restype = wintypes.BOOL
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = LRESULT
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetSubMenu.argtypes = [wintypes.HMENU, ctypes.c_int]
user32.GetSubMenu.restype = wintypes.HMENU
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH

MN_GETHMENU = 0x01E1
HOST_BG = (200, 30, 200)
HOST_RECT = (140, 100, 900, 620)
MENU_AT = (170, 190)


@WNDPROC
def _wp(hwnd, msg, w, l):
    return user32.DefWindowProcW(hwnd, msg, w, l)


def move_to(x, y):
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    ax = int((x - vx) * 65535 / max(1, vw - 1))
    ay = int((y - vy) * 65535 / max(1, vh - 1))
    user32.mouse_event(0x8001, ax, ay, 0, 0)


def menu_windows():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lp):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if buf.value == "#32768" and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append((hwnd, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumWindows(cb, 0)
    return out


def main():
    hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WNDCLASSEX()
    wc.cbSize = ctypes.sizeof(WNDCLASSEX)
    wc.lpfnWndProc = _wp
    wc.hInstance = hinst
    wc.hbrBackground = gdi32.CreateSolidBrush(
        HOST_BG[2] << 16 | HOST_BG[1] << 8 | HOST_BG[0])
    wc.lpszClassName = "MenuHostWnd"
    user32.RegisterClassExW(ctypes.byref(wc))

    x, y, w, h = HOST_RECT
    hwnd = user32.CreateWindowExW(0, "MenuHostWnd", "工程造价软件（模拟）",
                                  0x00CF0000 | 0x10000000, x, y, w, h,
                                  None, None, hinst, None)
    user32.SetForegroundWindow(hwnd)
    user32.SetCursorPos(x + 300, y + 500)

    hmenu = user32.CreatePopupMenu()
    sub = user32.CreatePopupMenu()
    user32.AppendMenuW(sub, 0, 2001, "电力人工、机械价格水平库")
    user32.AppendMenuW(sub, 0, 2002, "储能人工、机械价格水平库")
    user32.AppendMenuW(sub, 0, 2003, "我的资源库")
    user32.AppendMenuW(sub, 0, 2004, "地区材料价格库")
    user32.AppendMenuW(hmenu, 0, 1001, "系统设置")
    user32.AppendMenuW(hmenu, 0, 1002, "概预算清单导入工具")
    user32.AppendMenuW(hmenu, 0, 1003, "定额附录查询")
    user32.AppendMenuW(hmenu, 0x10, sub, "数据库/文件更新")
    user32.AppendMenuW(hmenu, 0, 1005, "工程文件审核")

    # 先把菜单弹出来，主线程用另一个线程去 hover 打开子菜单
    state = {"menu": None, "sub": None, "hwnd": hwnd}

    import threading

    def hover():
        time.sleep(0.5)
        wins = menu_windows()
        if not wins:
            return
        state["menu"] = (wins[0][1], wins[0][2], wins[0][3], wins[0][4])
        # 用键盘导航打开子菜单：Down×4 落到"数据库/文件更新"，再按 Right 展开。
        # 比模拟鼠标悬停稳定（SetCursorPos/mouse_event 有时不会让菜单收到移动消息）
        for _ in range(4):
            user32.keybd_event(0x28, 0, 0, 0)          # Down
            user32.keybd_event(0x28, 0, 2, 0)
            time.sleep(0.12)
        user32.keybd_event(0x27, 0, 0, 0)              # Right
        user32.keybd_event(0x27, 0, 2, 0)
        time.sleep(0.8)
        wins = menu_windows()
        print("菜单窗口:", wins, flush=True)
        if wins:
            # 父菜单在最左边，子菜单在它右边
            wins.sort(key=lambda t: t[1])
            state["menu"] = (wins[0][1], wins[0][2], wins[0][3], wins[0][4])
            if len(wins) >= 2:
                state["sub"] = (wins[-1][1], wins[-1][2], wins[-1][3], wins[-1][4])
        json.dump({"host": HOST_RECT, "menu": state["menu"], "sub": state["sub"]},
                  open(INFO, "w"))
        print("记录:", state["menu"], state["sub"], flush=True)

    threading.Thread(target=hover, daemon=True).start()
    cmd = user32.TrackPopupMenu(hmenu, 0x0100, MENU_AT[0], MENU_AT[1], 0, hwnd, None)
    print("menu closed, cmd =", cmd)


if __name__ == "__main__":
    main()
    time.sleep(8)
