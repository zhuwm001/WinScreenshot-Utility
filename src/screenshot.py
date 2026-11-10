# -*- coding: utf-8 -*-
"""全屏抓图：把多显示器画面拼成一张 QPixmap。

两个要点（直接决定能不能抓到下拉框、右键菜单这类"点了才出现"的界面）：

1. 用 GDI BitBlt 且带 ``CAPTUREBLT`` 标志。``QScreen::grabWindow`` 走的是
   普通 BitBlt，分层窗口（WS_EX_LAYERED）会被跳过 —— Chrome / Electron 的
   下拉列表、部分应用的悬浮面板、工具提示正好都是分层窗口，这就是"截图里
   看不到下拉框"的主要原因。
2. 只提供"立刻抓"的接口，抓图时机由调用方保证（在隐藏窗口、激活遮罩之前）。
"""
import ctypes
from ctypes import wintypes

from PyQt5.QtCore import QRect, QRectF, Qt
from PyQt5.QtGui import QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
BI_RGB = 0

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

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
                            ctypes.POINTER(_BITMAPINFO), wintypes.UINT]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL


def virtual_geometry() -> QRect:
    """所有显示器的逻辑坐标并集。"""
    app = QApplication.instance()
    rect = QRect()
    for screen in app.screens():
        rect = rect.united(screen.geometry())
    if rect.isEmpty():
        rect = app.primaryScreen().geometry()
    return rect


def virtual_screen_physical() -> QRect:
    """整个虚拟桌面的物理像素矩形（Win32 口径，含负坐标）。"""
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if w <= 0 or h <= 0:
        return QRect()
    return QRect(x, y, w, h)


def grab_rect_physical(rect: QRect) -> QImage:
    """用带 CAPTUREBLT 的 BitBlt 抓屏幕的一块物理像素区域。

    含分层窗口（下拉列表、工具提示、浮动面板），这是 Qt 自带接口抓不到的部分。
    """
    if rect.isEmpty():
        return QImage()
    w, h = rect.width(), rect.height()

    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        return QImage()
    hdc_mem = None
    hbmp = None
    old_obj = None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            return QImage()
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        if not hbmp:
            return QImage()
        old_obj = gdi32.SelectObject(hdc_mem, hbmp)

        ok = gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen,
                          rect.x(), rect.y(), SRCCOPY | CAPTUREBLT)
        if not ok:
            return QImage()

        bi = _BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = w
        bi.bmiHeader.biHeight = -h          # 负值 = 自上而下
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bi.bmiHeader.biCompression = BI_RGB

        buf = ctypes.create_string_buffer(w * h * 4)
        got = gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bi),
                              DIB_RGB_COLORS)
        if not got:
            return QImage()
        # buf 是临时内存，必须 copy 出来再交给 QImage
        return QImage(buf, w, h, w * 4, QImage.Format_RGB32).copy()
    finally:
        if hdc_mem and old_obj:
            gdi32.SelectObject(hdc_mem, old_obj)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)


def grab_virtual_desktop():
    """抓取整个虚拟桌面。

    返回 (QPixmap, 逻辑矩形)。QPixmap 的 devicePixelRatio 已设为屏幕缩放比例，
    可以直接用逻辑坐标绘制到全屏窗口上。
    """
    app = QApplication.instance()
    screens = app.screens()
    if not screens:
        return QPixmap(), QRect()

    vg = virtual_geometry()
    primary = app.primaryScreen()
    dpr = float(primary.devicePixelRatio()) if primary else 1.0
    if dpr <= 0:
        dpr = 1.0

    # ---- 首选：一次性 GDI 抓整个虚拟桌面（CAPTUREBLT）----
    phys = virtual_screen_physical()
    if not phys.isEmpty():
        expect_w = int(round(vg.width() * dpr))
        expect_h = int(round(vg.height() * dpr))
        # 尺寸对得上才用（混合 DPI 多屏时沿用下面的逐屏 Qt 方案）
        if abs(phys.width() - expect_w) <= 2 and abs(phys.height() - expect_h) <= 2:
            img = grab_rect_physical(phys)
            if not img.isNull():
                shot = QPixmap.fromImage(img)
                shot.setDevicePixelRatio(dpr)
                return shot, vg

    # ---- 回退：逐屏 Qt 抓，再按逻辑坐标拼 ----
    shot = QPixmap(int(round(vg.width() * dpr)), int(round(vg.height() * dpr)))
    shot.setDevicePixelRatio(dpr)
    shot.fill(Qt.black)

    painter = QPainter(shot)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    try:
        for screen in screens:
            geo = screen.geometry()
            pm = screen.grabWindow(0)
            if pm.isNull():
                continue
            target = QRectF(geo.x() - vg.x(), geo.y() - vg.y(), geo.width(), geo.height())
            painter.drawPixmap(target, pm, QRectF(pm.rect()))
    finally:
        painter.end()

    return shot, vg


def patch_region(pixmap: QPixmap, vgeo: QRect, logical_rect: QRect):
    """把屏幕上一块区域重新抓下来贴到已有截图上（逻辑坐标）。

    用途：先抓全屏保证内容完整，再隐藏自己的窗口，最后只把被窗口遮住的那块
    重新抓一次覆盖回去 —— 既不会漏掉别的程序的下拉框，也不会把自己的窗口截进去。
    """
    if pixmap is None or pixmap.isNull() or logical_rect.isEmpty():
        return pixmap
    dpr = float(pixmap.devicePixelRatio()) or 1.0
    rel = logical_rect.translated(-vgeo.x(), -vgeo.y())
    phys = QRect(int(round(rel.x() * dpr)), int(round(rel.y() * dpr)),
                 int(round(rel.width() * dpr)), int(round(rel.height() * dpr)))
    phys.translate(int(round(vgeo.x() * dpr)), int(round(vgeo.y() * dpr)))

    img = grab_rect_physical(phys)
    if img.isNull():
        return pixmap
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        target = QRectF(rel)
        painter.drawImage(target, img, QRectF(img.rect()))
    finally:
        painter.end()
    return pixmap
