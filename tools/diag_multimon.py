# -*- coding: utf-8 -*-
"""诊断多显示器抓屏：逐屏对比"桌面 DC"与"显示器 DC"两种抓法的结果。

用法：
    python tools/diag_multimon.py [输出目录]

输出：
    1) 每台显示器的设备名、物理矩形、是否为当前进程的主屏
    2) 两种抓法各自得到的图，算平均亮度和"全黑像素占比"，>99% 视为抓到黑屏
    3) 把每台显示器的截图存成 PNG，方便肉眼核对
"""
import ctypes
import os
import sys
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
BI_RGB = 0
DIB_RGB_COLORS = 0
MONITORINFOF_PRIMARY = 1
MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                     wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                     ctypes.c_void_p)


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p,
                                       MONITORENUMPROC, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                            ctypes.c_void_p]
gdi32.CreateDCW.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                         wintypes.DWORD]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                            wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFO), wintypes.UINT]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


def enum_monitors():
    out = []

    def cb(hmon, hdc, lprc, data):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            out.append({"hmon": hmon, "device": mi.szDevice,
                        "rect": (mi.rcMonitor.left, mi.rcMonitor.top,
                                 mi.rcMonitor.right - mi.rcMonitor.left,
                                 mi.rcMonitor.bottom - mi.rcMonitor.top),
                        "primary": bool(mi.dwFlags & MONITORINFOF_PRIMARY)})
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out


def grab_with(src_dc, x, y, w, h):
    """从给定 DC 抓一块，返回 (bytes, w, h) 或 None。"""
    hdc_mem = gdi32.CreateCompatibleDC(src_dc)
    hbmp = gdi32.CreateCompatibleBitmap(src_dc, w, h)
    if not hdc_mem or not hbmp:
        return None
    old = gdi32.SelectObject(hdc_mem, hbmp)
    try:
        if not gdi32.BitBlt(hdc_mem, 0, 0, w, h, src_dc, x, y,
                            SRCCOPY | CAPTUREBLT):
            return None
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bi),
                               DIB_RGB_COLORS):
            return None
        return buf.raw
    finally:
        if old:
            gdi32.SelectObject(hdc_mem, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)


def stats(raw, w, h):
    """返回 (平均亮度, 纯黑像素占比)。"""
    if raw is None:
        return None
    step = 4 * max(1, (w * h) // 40000)      # 抽样，够判断黑白
    total = 0
    dark = 0
    s = 0
    n = 0
    for i in range(0, len(raw) - 3, step):
        b, g, r = raw[i], raw[i + 1], raw[i + 2]
        v = (b + g + r) / 3.0
        s += v
        n += 1
        if v < 8:
            dark += 1
    return (s / max(1, n), dark / max(1, n))


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "multimon")
    os.makedirs(outdir, exist_ok=True)

    mons = enum_monitors()
    print("显示器数量：%d" % len(mons))
    for m in mons:
        print("  %-14s rect=(%d,%d) %dx%d  primary=%s"
              % (m["device"], m["rect"][0], m["rect"][1], m["rect"][2],
                 m["rect"][3], m["primary"]))

    hdc_desktop = user32.GetDC(None)
    print("\n桌面 DC = %r" % hdc_desktop)

    for idx, m in enumerate(mons):
        x, y, w, h = m["rect"]
        print("\n--- %s ---" % m["device"])

        # 1) 桌面 DC（当前实现走的就是这条路）
        raw = grab_with(hdc_desktop, x, y, w, h)
        st = stats(raw, w, h)
        print("  桌面DC BitBlt : " + ("失败" if st is None else
              "亮度 %.1f / 纯黑占比 %.1f%%" % (st[0], st[1] * 100)))
        if raw:
            save(raw, w, h, os.path.join(outdir, "desktop_%d.png" % idx))

        # 2) 该显示器自己的 DC
        hdc_mon = gdi32.CreateDCW(m["device"], None, None, None)
        if not hdc_mon:
            print("  显示器DC     : CreateDC 失败 err=%d"
                  % ctypes.get_last_error())
        else:
            raw2 = grab_with(hdc_mon, 0, 0, w, h)
            st2 = stats(raw2, w, h)
            print("  显示器DC BitBlt: " + ("失败" if st2 is None else
                  "亮度 %.1f / 纯黑占比 %.1f%%" % (st2[0], st2[1] * 100)))
            if raw2:
                save(raw2, w, h, os.path.join(outdir, "device_%d.png" % idx))
            gdi32.DeleteDC(hdc_mon)

    user32.ReleaseDC(None, hdc_desktop)
    print("\n图片已存到 %s" % outdir)
    return 0


def save(raw, w, h, path):
    try:
        from PyQt5.QtGui import QImage
        from PyQt5.QtCore import QImage as _  # noqa
    except Exception:
        return
    img = QImage(raw, w, h, w * 4, QImage.Format_RGB32).copy()
    img.save(path)


if __name__ == "__main__":
    sys.exit(main())
