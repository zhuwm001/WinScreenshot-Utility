# -*- coding: utf-8 -*-
"""全屏抓图：把多显示器画面拼成一张 QPixmap。

核心要点（直接决定能不能抓到下拉框、右键菜单，以及第二块屏是不是黑的）：

1. **逐显示器抓**。每个显示器单独 ``CreateDC("\\\\.\\DISPLAYn")`` 再 BitBlt，
   而不是从整个"虚拟桌面"的 DC 一次性抓。混合显卡（核显 + 独显）、两块屏
   DPI 不同、HDR 显示器上，桌面 DC 抓第二块屏会返回一整块黑，逐屏抓才稳。
2. 抓的时候带 ``CAPTUREBLT``。``QScreen::grabWindow`` 走普通 BitBlt，分层窗口
   （WS_EX_LAYERED）会被跳过 —— Chrome / Electron 的下拉列表、悬浮面板、工具
   提示正好都是分层窗口。
3. 进程按"物理像素"工作（``set_process_dpi_awareness``），否则系统会把窗口
   坐标虚拟化，第二块屏的坐标对不上，抓出来就是黑的。
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

MONITORINFOF_PRIMARY = 1
MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                     wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                     ctypes.c_void_p)


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


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
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p,
                                       MONITORENUMPROC, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR,
                                   ctypes.POINTER(_MONITORINFOEXW)]
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
                            ctypes.POINTER(_BITMAPINFO), wintypes.UINT]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL


# ---------------------------------------------------------------- DPI 感知
def set_process_dpi_awareness() -> str:
    """把进程切成"按物理像素"工作模式，必须在创建 QApplication 之前调用。

    不做这一步：系统会把整个窗口坐标按主屏 DPI 缩放后再告诉我们，
    第二块屏（尤其缩放比例不同的）坐标就对不上，抓图结果是黑的或错位的。
    返回实际生效的级别，失败时返回 "unaware"（程序照旧能跑）。
    """
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):   # PMv2
            return "per-monitor-v2"
    except Exception:
        pass
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.c_int
        if shcore.SetProcessDpiAwareness(2) == 0:                      # per-monitor
            return "per-monitor"
    except Exception:
        pass
    try:
        if user32.SetProcessDPIAware():
            return "system"
    except Exception:
        pass
    return "unaware"


# ---------------------------------------------------------------- 显示器枚举
def enum_monitors():
    """枚举全部显示器：``[{"device": "\\\\.\\DISPLAY1", "rect": QRect, "primary": bool}]``。

    rect 是物理像素坐标（进程 DPI 感知时与真实分辨率一致）。
    """
    found = []

    def _cb(hmon, hdc, lprc, data):
        mi = _MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            found.append({
                "device": mi.szDevice,
                "rect": QRect(r.left, r.top, r.right - r.left, r.bottom - r.top),
                "primary": bool(mi.dwFlags & MONITORINFOF_PRIMARY),
            })
        return True

    try:
        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    except Exception:
        return []
    return found


def virtual_geometry() -> QRect:
    """所有显示器的逻辑坐标并集（Qt 口径，遮罩窗口就用这个几何）。"""
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


# ---------------------------------------------------------------- GDI 抓图
def _blt_from_dc(hdc_src, x, y, w, h):
    """从任意 DC 抓 (x, y, w, h) 这一块，返回 QImage（32 位，无 alpha）。"""
    if w <= 0 or h <= 0 or not hdc_src:
        return QImage()
    hdc_mem = hbmp = old_obj = None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_src)
        if not hdc_mem:
            return QImage()
        hbmp = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
        if not hbmp:
            return QImage()
        old_obj = gdi32.SelectObject(hdc_mem, hbmp)
        if not gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_src, x, y,
                            SRCCOPY | CAPTUREBLT):
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


def _is_blank(img: QImage) -> bool:
    """整块图是不是纯黑 —— 用来识别"这块屏没抓到"而不是"这块屏本来就是黑的"。

    阈值取 99.9%：只要有一个非黑像素就认为抓到了内容。真实画面几乎不可能
    全黑，所以这里判"黑"基本等同于判定"抓丢了"。
    """
    if img.isNull():
        return True
    if img.format() != QImage.Format_RGB32:
        img = img.convertToFormat(QImage.Format_RGB32)
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return True
    stride = img.bytesPerLine()
    ptr = img.constBits()
    try:
        ptr.setsize(img.byteCount())
    except AttributeError:
        ptr.setsize(img.sizeInBytes())
    data = bytes(ptr)

    step = max(1, int((w * h / 8000.0) ** 0.5))
    dark = total = 0
    for y in range(0, h, step):
        row = y * stride
        for x in range(0, w, step):
            i = row + x * 4
            if data[i] < 8 and data[i + 1] < 8 and data[i + 2] < 8:
                dark += 1
            total += 1
    return total > 0 and dark / float(total) > 0.999


def _screen_by_name(screens, device):
    """按 GDI 设备名找对应的 QScreen（Windows 上 QScreen.name() 就是 \\\\.\\DISPLAYn）。"""
    for s in screens:
        if s.name() == device:
            return s
    return None


def grab_monitor_rect(mon, sub_rect=None) -> QImage:
    """抓某个显示器的一块（默认整屏），返回物理像素 QImage。

    先走该显示器自己的 DC；失败或抓到一整块黑时，用 Qt 的 grabWindow 再试一次，
    谁的内容更"有东西"就用谁 —— 这条兜底是多屏黑屏的最后一道保险。
    """
    full = mon["rect"]
    sub = QRect(0, 0, full.width(), full.height()) if sub_rect is None else sub_rect
    if sub.isEmpty():
        return QImage()

    img = QImage()
    hdc = gdi32.CreateDCW(mon["device"], None, None, None)
    if hdc:
        try:
            img = _blt_from_dc(hdc, sub.x(), sub.y(), sub.width(), sub.height())
        finally:
            gdi32.DeleteDC(hdc)

    if img.isNull() or _is_blank(img):
        alt = _grab_via_qt(mon, sub)
        if not alt.isNull() and (img.isNull() or not _is_blank(alt)):
            img = alt
    return img


def _grab_via_qt(mon, sub):
    """用 Qt 逐屏抓一块，作为 GDI 失败时的兜底。"""
    app = QApplication.instance()
    if app is None:
        return QImage()
    screen = _screen_by_name(app.screens(), mon["device"])
    if screen is None:
        return QImage()
    pm = screen.grabWindow(0)
    if pm.isNull():
        return QImage()
    img = pm.toImage()
    # Qt 的 grabWindow 给的是该屏原始像素，按 sub 在屏内的偏移裁出来
    sx = img.width() / float(max(1, mon["rect"].width()))
    sy = img.height() / float(max(1, mon["rect"].height()))
    if abs(sx - 1.0) > 0.02 or abs(sy - 1.0) > 0.02:
        sub = QRect(int(sub.x() * sx), int(sub.y() * sy),
                    max(1, int(sub.width() * sx)), max(1, int(sub.height() * sy)))
    return img.copy(sub.intersected(img.rect()))


def grab_rect_physical(rect: QRect) -> QImage:
    """抓屏幕上的一块物理像素区域（可能跨屏，逐屏拼）。"""
    if rect.isEmpty():
        return QImage()
    mons = enum_monitors()
    if not mons:
        hdc = user32.GetDC(None)
        if not hdc:
            return QImage()
        try:
            return _blt_from_dc(hdc, rect.x(), rect.y(), rect.width(), rect.height())
        finally:
            user32.ReleaseDC(None, hdc)

    out = QImage(rect.size(), QImage.Format_RGB32)
    out.fill(Qt.black)
    painter = QPainter(out)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        for mon in mons:
            inter = rect.intersected(mon["rect"])
            if inter.isEmpty():
                continue
            part = grab_monitor_rect(
                mon, inter.translated(-mon["rect"].x(), -mon["rect"].y()))
            if part.isNull():
                continue
            painter.drawImage(inter.topLeft() - rect.topLeft(), part)
    finally:
        painter.end()
    return out


# ---------------------------------------------------------------- 对外接口
def grab_screens():
    """逐屏抓，返回 ``[(QScreen, QPixmap)]``。

    每块 QPixmap 是**该屏原生像素**，devicePixelRatio 已设成这块屏自己的缩放比例，
    所以拿到之后可以直接按逻辑尺寸贴到任何地方。
    """
    app = QApplication.instance()
    if app is None:
        return []
    by_name = dict((m["device"], m) for m in enum_monitors())
    result = []
    for screen in app.screens():
        mon = by_name.get(screen.name())
        img = grab_monitor_rect(mon) if mon else QImage()
        pm = QPixmap.fromImage(img) if not img.isNull() else screen.grabWindow(0)
        if not pm.isNull():
            pm.setDevicePixelRatio(float(screen.devicePixelRatio()) or 1.0)
        result.append((screen, pm))
    return result


def compose_screens(pairs, vgeo, dpr) -> QPixmap:
    """把逐屏抓的图按逻辑坐标拼成一整张（devicePixelRatio = dpr）。"""
    shot = QPixmap(max(1, int(round(vgeo.width() * dpr))),
                   max(1, int(round(vgeo.height() * dpr))))
    shot.setDevicePixelRatio(dpr)
    shot.fill(Qt.black)
    painter = QPainter(shot)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        for screen, pm in pairs:
            if pm is None or pm.isNull():
                continue
            geo = screen.geometry()
            target = QRectF(geo.x() - vgeo.x(), geo.y() - vgeo.y(),
                            geo.width(), geo.height())
            img = pm.toImage()
            img.setDevicePixelRatio(1.0)     # 用原始像素 + 显式目标矩形，避免二次缩放
            painter.drawImage(target, img)
    finally:
        painter.end()
    return shot


class DesktopShot(object):
    """一次抓屏的结果：逐屏原生图 + 整张逻辑矩形。

    为什么要留逐屏原生图：两块屏缩放比例不一样时（主屏 150% + 副屏 100%），
    一个跨越两屏的窗口在系统层面只会按一个 DPI 渲染，另一块屏必然错位 ——
    所以这种情况要"一屏一个遮罩"，每块屏用自己的原图。
    """

    def __init__(self, vgeo, pairs, dpr, mixed=None):
        self.vgeo = QRect(vgeo)
        self.screens = list(pairs)          # [(QScreen, QPixmap)]
        self.dpr = float(dpr)
        self._composite = None
        self._mixed = mixed                 # 测试时可强制指定

    @property
    def is_mixed(self) -> bool:
        if self._mixed is not None:
            return bool(self._mixed)
        ratios = set()
        for s, pm in self.screens:
            ratios.add(round(float(s.devicePixelRatio()) or 1.0, 3))
        return len(ratios) > 1

    def composite(self) -> QPixmap:
        """整张桌面（缩放比例统一时用；混合缩放时只作为兜底）。"""
        if self._composite is None:
            self._composite = compose_screens(self.screens, self.vgeo, self.dpr)
        return self._composite

    def patch(self, logical_rect: QRect):
        """把屏幕上的一块重新抓一次，覆盖到各屏原图上（补掉自己的窗口）。"""
        if logical_rect.isEmpty():
            return
        for idx, (screen, pm) in enumerate(self.screens):
            geo = screen.geometry()
            inter = geo.intersected(logical_rect)
            if inter.isEmpty() or pm is None or pm.isNull():
                continue
            # 逻辑 -> 该屏原图像素
            sx = pm.width() / float(max(1, geo.width()))
            sy = pm.height() / float(max(1, geo.height()))
            phys = QRect(int(round((inter.x() - geo.x()) * sx)),
                         int(round((inter.y() - geo.y()) * sy)),
                         max(1, int(round(inter.width() * sx))),
                         max(1, int(round(inter.height() * sy))))
            mon = None
            for m in enum_monitors():
                if m["device"] == screen.name():
                    mon = m
                    break
            if mon is None:
                continue
            img = grab_monitor_rect(
                mon, phys.translated(mon["rect"].x(), mon["rect"].y()))
            if img.isNull():
                continue
            painter = QPainter(pm)
            try:
                painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
                painter.drawImage(phys, img)
            finally:
                painter.end()
            self.screens[idx] = (screen, pm)
        self._composite = None

    def screen_at(self, logical_rect: QRect):
        """这块逻辑区域落在哪块屏上（取重叠面积最大的）。"""
        best = None
        area = 0
        for screen, _ in self.screens:
            inter = screen.geometry().intersected(logical_rect)
            if inter.isEmpty():
                continue
            a = inter.width() * inter.height()
            if a > area:
                area, best = a, screen
        return best


def capture_desktop() -> DesktopShot:
    """抓一次整个桌面，返回含逐屏原图的 :class:`DesktopShot`。"""
    app = QApplication.instance()
    if app is None:
        return DesktopShot(QRect(), [], 1.0)
    vg = virtual_geometry()
    primary = app.primaryScreen()
    dpr = float(primary.devicePixelRatio()) if primary else 1.0
    if dpr <= 0:
        dpr = 1.0
    return DesktopShot(vg, grab_screens(), dpr)


def grab_virtual_desktop():
    """抓取整个虚拟桌面，返回 (QPixmap, 逻辑矩形)（兼容旧接口）。"""
    desk = capture_desktop()
    if not desk.screens:
        return QPixmap(), QRect()
    return desk.composite(), desk.vgeo


def patch_region(pixmap: QPixmap, vgeo: QRect, logical_rect: QRect):
    """把屏幕上一块区域重新抓下来贴到已有截图上（逻辑坐标）。

    用途：先抓全屏保证内容完整，再隐藏自己的窗口，最后只把被窗口遮住的那块
    重新抓一次覆盖回去 —— 既不会漏掉别的程序的下拉框，也不会把自己的窗口截进去。
    """
    if pixmap is None or pixmap.isNull() or logical_rect.isEmpty():
        return pixmap

    phys_rect = logical_to_physical(logical_rect)
    if phys_rect.isEmpty():
        return pixmap

    img = grab_rect_physical(phys_rect)
    if img.isNull():
        return pixmap
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        rel = logical_rect.translated(-vgeo.x(), -vgeo.y())
        painter.drawImage(QRectF(rel), img, QRectF(img.rect()))
    finally:
        painter.end()
    return pixmap


def logical_to_physical(logical_rect: QRect) -> QRect:
    """逻辑坐标 -> 物理像素（按该区域所在那块屏自己的缩放比例换算）。"""
    app = QApplication.instance()
    screens = list(app.screens()) if app else []

    screen = None
    best = 0
    for s in screens:
        inter = s.geometry().intersected(logical_rect)
        if inter.isEmpty():
            continue
        area = inter.width() * inter.height()
        if area > best:
            best, screen = area, s

    mon = None
    if screen is not None:
        for m in enum_monitors():
            if m["device"] == screen.name():
                mon = m
                break

    if screen is None or mon is None:
        # 兜底：整个虚拟桌面统一换算
        phys = virtual_screen_physical()
        vg = virtual_geometry()
        if phys.isEmpty() or vg.width() <= 0 or vg.height() <= 0:
            return QRect()
        lx = phys.width() / float(vg.width())
        ly = phys.height() / float(vg.height())
        return QRect(int(round(phys.x() + (logical_rect.x() - vg.x()) * lx)),
                     int(round(phys.y() + (logical_rect.y() - vg.y()) * ly)),
                     max(1, int(round(logical_rect.width() * lx))),
                     max(1, int(round(logical_rect.height() * ly))))

    sg = screen.geometry()
    mr = mon["rect"]
    lx = mr.width() / float(max(1, sg.width()))
    ly = mr.height() / float(max(1, sg.height()))
    return QRect(int(round(mr.x() + (logical_rect.x() - sg.x()) * lx)),
                 int(round(mr.y() + (logical_rect.y() - sg.y()) * ly)),
                 max(1, int(round(logical_rect.width() * lx))),
                 max(1, int(round(logical_rect.height() * ly))))
