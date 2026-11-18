# -*- coding: utf-8 -*-
"""全屏截图遮罩层：框选区域、标注、复制、贴图。"""
import math

from PyQt5.QtCore import (
    QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal,
)
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF, QTextCursor,
)
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QTextEdit, QToolButton,
    QWidget,
)

import icons
from screenshot import (capture_desktop, grab_virtual_desktop, virtual_geometry)
from update_log import log as ulog
from winutil import force_foreground

# 状态
S_IDLE = 0
S_SELECTING = 1
S_SELECTED = 2
S_DRAWING = 3
S_RESIZING = 4
S_TEXT_PRESS = 5     # 按在文字上，还没决定是拖动还是进入编辑
S_TEXT_MOVE = 6      # 拖动文字
S_TEXT_WIDTH = 7     # 拖文字左右边框改换行宽度

# 工具
T_RECT = "rect"
T_ELLIPSE = "ellipse"
T_ARROW = "arrow"
T_PEN = "pen"
T_TEXT = "text"

# 手绘：笔迹两点最小间距（逻辑像素）与最短有效笔迹长度
PEN_MIN_STEP = 1.2
PEN_MIN_LEN = 4.0

HANDLE_SIZE = 8
DIM_COLOR = QColor(0, 0, 0, 115)
SEL_BORDER = QColor(74, 134, 255, 255)

# 文字字号范围（像素）
FONT_MIN = 12
FONT_MAX = 96
FONT_STEP = 2
FONT_DEFAULT = 20


def _rect_text(r) -> str:
    """日志里用的矩形写法，比 QRect 的 repr 短得多。"""
    if r is None or r.isNull():
        return "无"
    return "%d,%d %d×%d" % (r.x(), r.y(), r.width(), r.height())


def _font(size: int, bold: bool = False) -> QFont:
    f = QFont("Microsoft YaHei UI")
    f.setStyleStrategy(QFont.PreferAntialias)
    f.setPixelSize(size)
    f.setBold(bold)
    return f


def wrap_text_lines(text: str, fm: QFontMetrics, max_w: float):
    """把文字按像素宽度折成多行，保留原有的硬换行。

    max_w <= 0 表示不限宽，只按 \\n 切。中文逐字断行，英文优先在空格处断，
    尽量不把单词劈成两半。
    """
    paras = text.split("\n") or [""]
    if max_w <= 0:
        return paras
    out = []
    for para in paras:
        if not para:
            out.append("")
            continue
        cur = ""
        for ch in para:
            if not cur:
                cur = ch
                continue
            if fm.horizontalAdvance(cur + ch) <= max_w:
                cur += ch
                continue
            cut = cur.rfind(" ")
            if cut > 0 and cut >= len(cur) - 12:
                out.append(cur[:cut])
                cur = cur[cut + 1:] + ch
            else:
                out.append(cur)
                cur = ch
        out.append(cur)
    return out


class AnnotItem:
    """一个标注对象。

    矩形/椭圆用 p1-p2 的规范化矩形，箭头保留方向，手绘用 points 记录轨迹。
    """

    def __init__(self, kind, p1, p2, color, width=3, text="", font_size=FONT_DEFAULT,
                 bold=False, wrap_w=0.0):
        self.kind = kind
        self.p1 = QPointF(p1)
        self.p2 = QPointF(p2)
        self.color = QColor(color)
        self.width = width
        self.text = text
        self.font_size = font_size
        self.bold = bold
        # 文字自动换行宽度（逻辑像素）；0 表示不换行，框宽跟着最长那行走
        self.wrap_w = float(wrap_w or 0.0)
        self.points = [QPointF(p1)] if kind == T_PEN else []

    @property
    def rect(self) -> QRectF:
        return QRectF(self.p1, self.p2).normalized()


def _pen_path(points):
    """把采样点串成平滑路径：相邻点取中点做二次贝塞尔，避免折线感。"""
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    if len(points) == 1:
        return path
    if len(points) == 2:
        path.lineTo(points[1])
        return path
    for i in range(1, len(points) - 1):
        cur = points[i]
        nxt = points[i + 1]
        mid = QPointF((cur.x() + nxt.x()) / 2.0, (cur.y() + nxt.y()) / 2.0)
        path.quadTo(cur, mid)
    path.lineTo(points[-1])
    return path


def pen_length(points) -> float:
    """笔迹总长度，用来判断这算一笔还是误点。"""
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.hypot(b.x() - a.x(), b.y() - a.y())
    return total


def _append_pen_point(item: "AnnotItem", pos: QPoint):
    """按最小步长记录轨迹点，避免同一位置重复堆积。"""
    if not item.points:
        item.points.append(QPointF(pos))
        return
    pt = QPointF(pos)
    last = item.points[-1]
    if math.hypot(pt.x() - last.x(), pt.y() - last.y()) < PEN_MIN_STEP:
        return
    item.points.append(pt)
    item.p2 = QPointF(pt)


def paint_item(p: QPainter, item: AnnotItem):
    color = item.color
    w = max(1, item.width)

    if item.kind in (T_RECT, T_ELLIPSE):
        if item.kind == T_RECT:
            p.setPen(QPen(color, w, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
        else:
            p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        r = item.rect
        if item.kind == T_RECT:
            p.drawRect(r)
        else:
            p.drawEllipse(r)

    elif item.kind == T_ARROW:
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawLine(item.p1, item.p2)
        head = max(11.0, w * 4.2)
        ang = math.atan2(item.p2.y() - item.p1.y(), item.p2.x() - item.p1.x())
        spread = math.radians(24)
        a1 = QPointF(item.p2.x() - head * math.cos(ang - spread),
                     item.p2.y() - head * math.sin(ang - spread))
        a2 = QPointF(item.p2.x() - head * math.cos(ang + spread),
                     item.p2.y() - head * math.sin(ang + spread))
        p.setPen(QPen(color, 1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(color)
        p.drawPolygon(QPolygonF([item.p2, a1, a2]))

    elif item.kind == T_PEN and item.points:
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if len(item.points) == 1:
            # 只点了一下：留一个圆点，别让用户觉得白画了
            r = max(w, 2) / 2.0
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(item.points[0], r, r)
        else:
            p.drawPath(_pen_path(item.points))

    elif item.kind == T_TEXT and item.text:
        font = _font(item.font_size, item.bold)
        fm = QFontMetrics(font)
        line_h = fm.lineSpacing()
        lines = wrap_text_lines(item.text, fm, item.wrap_w)
        # 只有白/黄这类很亮的文字才补一圈贴合笔画的细描边，
        # 描边与笔画同心、没有位移，所以不会出现重影。
        lum = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        halo = QColor(0, 0, 0, 120) if lum > 175 else None
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        for i, line in enumerate(lines):
            if not line:
                continue
            base = QPointF(item.p1.x(), item.p1.y() + fm.ascent() + i * line_h)
            path = QPainterPath()
            path.addText(base, font, line)
            if halo is not None:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(halo, max(1.0, item.font_size * 0.055),
                              Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPath(path)


def text_rect(item: AnnotItem) -> QRectF:
    """文字标注的包围盒，用于点击命中判断和拖动边框。

    wrap_w > 0 时框宽固定为 wrap_w，否则跟着最长那一行走。
    """
    font = _font(item.font_size, item.bold)
    fm = QFontMetrics(font)
    lines = wrap_text_lines(item.text, fm, item.wrap_w)
    w = max((fm.horizontalAdvance(l) for l in lines), default=0)
    if item.wrap_w:
        w = max(w, float(item.wrap_w))
    h = fm.lineSpacing() * max(1, len(lines))
    return QRectF(item.p1.x() - 5, item.p1.y() - 5,
                  max(w, 10) + 10, max(h, fm.lineSpacing()) + 10)


# ------------------------------------------------------------------ 浮动工具栏
class FloatingBar(QWidget):
    """自绘圆角深色条的容器，圆角外透明。"""

    def __init__(self, parent=None, radius=10):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._radius = radius

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.setBrush(QColor(24, 24, 28, 240))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                          self._radius, self._radius)


class ColorPalette(FloatingBar):
    """截图时用的迷你色板，避免弹出系统对话框被遮罩挡住。"""

    colorPicked = pyqtSignal(object)
    customRequested = pyqtSignal()

    COLORS = ["#FF3B30", "#FF9500", "#FFCC00", "#34C759",
              "#4A86FF", "#8B5CF6", "#FFFFFF", "#1F2330"]

    def __init__(self, parent=None):
        super().__init__(parent, radius=10)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 7, 9, 7)
        lay.setSpacing(7)
        for c in self.COLORS:
            b = QToolButton(self)
            b.setFixedSize(22, 22)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(c.upper())
            b.setStyleSheet(
                "QToolButton { background: %s; border-radius: 11px;"
                " border: 1px solid rgba(255,255,255,0.45); }"
                "QToolButton:hover { border: 2px solid #4A86FF; }" % c
            )
            b.clicked.connect(lambda _=False, col=c: self.colorPicked.emit(QColor(col)))
            lay.addWidget(b)

        more = QToolButton(self)
        more.setFixedSize(22, 22)
        more.setCursor(Qt.PointingHandCursor)
        more.setFocusPolicy(Qt.NoFocus)
        more.setToolTip("自定义颜色…")
        more.setText("…")
        more.setStyleSheet(
            "QToolButton { color: #E6E6EA; font-size: 14px; font-weight: 700;"
            " background: rgba(255,255,255,0.12); border-radius: 11px;"
            " border: 1px solid rgba(255,255,255,0.35); }"
            "QToolButton:hover { background: rgba(255,255,255,0.24); }"
        )
        more.clicked.connect(self.customRequested.emit)
        lay.addWidget(more)


class EditorBar(FloatingBar):
    toolChanged = pyqtSignal(str)
    colorClicked = pyqtSignal()
    undoClicked = pyqtSignal()
    pinClicked = pyqtSignal()
    copyClicked = pyqtSignal()
    saveClicked = pyqtSignal()
    cancelClicked = pyqtSignal()
    textSizeChanged = pyqtSignal(int)
    textBoldChanged = pyqtSignal(bool)

    TOOLS = [
        (T_RECT, "矩形", "拖动绘制方框（快捷键 R）"),
        (T_ELLIPSE, "椭圆", "拖动绘制椭圆（快捷键 E）"),
        (T_ARROW, "箭头", "拖动绘制箭头（快捷键 A）"),
        (T_PEN, "手绘", "按住鼠标自由手绘标记（快捷键 P）"),
        (T_TEXT, "文字", "点击后输入文字（快捷键 T），可调字号与粗细"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent, radius=10)
        self.setObjectName("editorBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(7, 4, 7, 4)
        lay.setSpacing(2)

        self._tool_buttons = {}
        for kind, name, tip in self.TOOLS:
            b = self._make_button(kind, tip)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=kind: self._select_tool(k))
            self._tool_buttons[kind] = b
            lay.addWidget(b)

        # 文字工具专属：字号 / 粗体
        self._size = FONT_DEFAULT
        self._text_mode = False
        self._text_opts = QWidget(self)
        self._text_opts.setVisible(False)
        ol = QHBoxLayout(self._text_opts)
        ol.setContentsMargins(2, 0, 2, 0)
        ol.setSpacing(1)

        self.btn_size_down = self._make_text_button("A-", "字号变小（[ 或 -）", width=26)
        self.btn_size_down.clicked.connect(lambda: self._step_size(-1))
        ol.addWidget(self.btn_size_down)

        self.lbl_size = QLabel(str(self._size), self._text_opts)
        self.lbl_size.setAlignment(Qt.AlignCenter)
        self.lbl_size.setFixedSize(28, 28)
        self.lbl_size.setToolTip("当前字号（像素）")
        self.lbl_size.setStyleSheet(
            "color:#EDEDF2; font-size:12px; font-weight:600;"
            " background: rgba(255,255,255,0.10); border-radius:5px;")
        ol.addWidget(self.lbl_size)

        self.btn_size_up = self._make_text_button("A+", "字号变大（] 或 +）", width=26)
        self.btn_size_up.clicked.connect(lambda: self._step_size(1))
        ol.addWidget(self.btn_size_up)

        self.btn_bold = self._make_text_button("B", "粗体（B）", bold=True, width=28)
        self.btn_bold.setCheckable(True)
        self.btn_bold.setChecked(False)
        self.btn_bold.toggled.connect(self.textBoldChanged.emit)
        ol.addWidget(self.btn_bold)

        lay.addWidget(self._text_opts)

        lay.addWidget(self._sep())

        self.btn_color = self._make_button("color", "标记颜色", checkable=False)
        self.btn_color.clicked.connect(self.colorClicked.emit)
        lay.addWidget(self.btn_color)

        self.btn_undo = self._make_button("undo", "撤销（Ctrl+Z）", checkable=False)
        self.btn_undo.clicked.connect(self.undoClicked.emit)
        lay.addWidget(self.btn_undo)

        lay.addWidget(self._sep())

        self.btn_pin = self._make_button("pin", "钉在屏幕最前端（F3）", checkable=False)
        self.btn_pin.clicked.connect(self.pinClicked.emit)
        lay.addWidget(self.btn_pin)

        self.btn_save = self._make_button("save", "另存为文件（Ctrl+S）", checkable=False)
        self.btn_save.clicked.connect(self.saveClicked.emit)
        lay.addWidget(self.btn_save)

        lay.addWidget(self._sep())

        # 倒数第二个：关闭 / 取消
        self.btn_cancel = self._make_button("close", "关闭（Esc）", checkable=False)
        self.btn_cancel.clicked.connect(self.cancelClicked.emit)
        lay.addWidget(self.btn_cancel)

        # 最后一个：保存（复制到剪贴板）
        self.btn_copy = self._make_button("copy", "保存并复制到剪贴板（Ctrl+C / Enter）",
                                          checkable=False)
        self.btn_copy.clicked.connect(self.copyClicked.emit)
        self.btn_copy.setStyleSheet(
            "QToolButton { border:none; border-radius:7px;"
            " background: rgba(74,134,255,0.95); }"
            "QToolButton:hover { background: #5C93FF; }"
            "QToolButton:pressed { background: #3A6FE0; }"
        )
        lay.addWidget(self.btn_copy)

        self.set_tool(T_RECT)
        self.set_color(QColor("#FF3B30"))
        self.set_undo_enabled(False)

    # ---------- 内部 ----------
    def _make_button(self, icon_kind, tip, checkable=False):
        b = QToolButton(self)
        b.setIcon(icons.render_icon(icon_kind, 21))
        b.setIconSize(QSize(21, 21))
        b.setFixedSize(34, 34)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(
            "QToolButton { border:none; border-radius:7px; background:transparent; }"
            "QToolButton:hover { background: rgba(255,255,255,0.15); }"
            "QToolButton:checked { background: rgba(74,134,255,0.92); }"
        )
        return b

    def _make_text_button(self, text, tip, bold=False, width=26):
        b = QToolButton(self._text_opts)
        b.setText(text)
        b.setToolTip(tip)
        b.setFixedSize(width, 28)
        f = b.font()
        f.setPixelSize(13)
        f.setBold(bold)
        b.setFont(f)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(
            "QToolButton { border:none; border-radius:6px; background:transparent;"
            " color:#E8E8EE; }"
            "QToolButton:hover { background: rgba(255,255,255,0.16); }"
            "QToolButton:checked { background: rgba(74,134,255,0.92); color:#FFFFFF; }"
        )
        return b

    def _sep(self):
        f = QFrame(self)
        f.setFixedSize(1, 20)
        f.setStyleSheet("background: rgba(255,255,255,0.22);")
        return f

    def _select_tool(self, kind):
        self.set_tool(kind)
        self.toolChanged.emit(kind)

    # ---------- 对外 ----------
    def set_tool(self, kind):
        for k, b in self._tool_buttons.items():
            b.setChecked(k == kind)

    def set_color(self, color: QColor):
        self.btn_color.setIcon(icons.render_icon("color", 20, color))
        self.btn_color.setToolTip("标记颜色（当前 %s）" % color.name().upper())

    def set_undo_enabled(self, enabled: bool):
        self.btn_undo.setEnabled(enabled)
        self.btn_undo.setStyleSheet(
            "QToolButton { border:none; border-radius:7px; background:transparent; }"
            + ("QToolButton:hover { background: rgba(255,255,255,0.15); }" if enabled
               else "QToolButton:disabled { }")
        )
        self.btn_undo.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)

    # ---------- 文字字号 / 粗细 ----------
    def set_text_mode(self, on: bool):
        """只有切到文字工具时才显示字号、粗体控件。"""
        on = bool(on)
        if self._text_mode == on:
            return
        self._text_mode = on
        self._text_opts.setVisible(on)

    def set_text_style(self, size: int, bold: bool):
        self._size = max(FONT_MIN, min(FONT_MAX, int(size)))
        self.lbl_size.setText(str(self._size))
        self.btn_bold.blockSignals(True)
        self.btn_bold.setChecked(bool(bold))
        self.btn_bold.blockSignals(False)

    def _step_size(self, direction: int):
        size = max(FONT_MIN, min(FONT_MAX, self._size + direction * FONT_STEP))
        if size == self._size:
            return
        self._size = size
        self.lbl_size.setText(str(size))
        self.textSizeChanged.emit(size)

    def bump_size(self, direction: int):
        self._step_size(direction)

    def toggle_bold(self):
        self.btn_bold.setChecked(not self.btn_bold.isChecked())

    def fit(self):
        self.adjustSize()


# ------------------------------------------------------------------ 遮罩层
class CaptureOverlay(QWidget):
    finished = pyqtSignal(object)      # QImage，已复制到剪贴板
    pinned = pyqtSignal(object, object)  # QImage, 屏幕坐标 QPoint
    cancelled = pyqtSignal()
    activated = pyqtSignal()           # 用户在这块遮罩上按了鼠标（多屏时用来清掉别的屏的选区）

    def __init__(self, pen_color="#FF3B30", text_size=FONT_DEFAULT, text_bold=False,
                 shot=None, vgeo=None, show_hint=True):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # 调用方通常在按快捷键的瞬间就把画面抓好了（此时别的程序的下拉框、
        # 右键菜单还在），这里直接用，避免等遮罩创建好再去抓时内容已经消失。
        if shot is not None and not shot.isNull():
            self._shot = shot
            self._vgeo = QRect(vgeo) if vgeo is not None else virtual_geometry()
        else:
            self._shot, self._vgeo = grab_virtual_desktop()
        self.setGeometry(self._vgeo)
        self._dpr = float(self._shot.devicePixelRatio()) or 1.0
        self._show_hint = bool(show_hint)

        self._sel = QRect()
        self._origin = QPoint()
        self._state = S_IDLE
        self._tool = T_RECT
        self._color = QColor(pen_color)
        self._items = []
        self._temp = None
        self._draw_start = QPointF()
        self._resize_handle = ""
        self._sel_before = QRect()

        self._text_edit = None
        self._text_pos = QPointF()
        self._text_color = QColor(pen_color)
        self._text_size = max(FONT_MIN, min(FONT_MAX, int(text_size or FONT_DEFAULT)))
        self._text_bold = bool(text_bold)
        self._editing_item = None
        self._committing = False
        self._edit_wrap = 0.0

        # 文字标注的拖动 / 改宽
        self._hover_item = None
        self._drag_item = None
        self._drag_pos = QPoint()
        self._drag_from = QPointF()
        self._text_edge = ""
        self._text_edge_right = 0.0

        self._bar = EditorBar(self)
        self._bar.toolChanged.connect(self._on_tool_changed)
        self._bar.colorClicked.connect(self._pick_color)
        self._bar.undoClicked.connect(self._undo)
        self._bar.pinClicked.connect(self._pin)
        self._bar.copyClicked.connect(self._copy)
        self._bar.saveClicked.connect(self._save_file)
        self._bar.cancelClicked.connect(self._cancel)
        self._bar.textSizeChanged.connect(self._on_text_size)
        self._bar.textBoldChanged.connect(self._on_text_bold)
        self._bar.set_text_style(self._text_size, self._text_bold)
        self._bar.hide()

        self._palette = ColorPalette(self)
        self._palette.colorPicked.connect(self._on_palette_color)
        self._palette.customRequested.connect(self._pick_custom_color)
        self._palette.hide()

        ulog("遮罩就绪：几何=%s 截图=%dx%d dpr=%.2f 实际窗口=%d×%d"
             % (_rect_text(self._vgeo), self._shot.width(), self._shot.height(),
                self._dpr, self.width(), self.height()))

    # ---------------------------------------------------------- 生命周期
    def show_overlay(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)
        # 别的程序占着前台时，activateWindow() 常常只是闪一下任务栏，
        # 遮罩其实是"死的"（Esc、回车都收不到）。这里强制抢一次前台。
        if not self.isActiveWindow():
            force_foreground(int(self.winId()))
            self.activateWindow()
            self.setFocus(Qt.ActiveWindowFocusReason)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)

    # ---------------------------------------------------------- 绘制
    def paintEvent(self, event):
        # 绘制里任何一个异常在 PyQt5 下都会直接 abort 进程（打包后无控制台，
        # 表现为遮罩连同整个程序瞬间消失）。这里兜住并记日志，至少能保住会话。
        try:
            self._paint(event)
        except Exception:
            import traceback
            ulog("遮罩绘制异常：" + traceback.format_exc(limit=8).replace("\n", " | "))

    def _paint(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        if not self._shot.isNull():
            p.drawPixmap(0, 0, self._shot)

        sel = self._sel
        if sel.isNull() or sel.width() < 1 or sel.height() < 1:
            p.fillRect(self.rect(), DIM_COLOR)
            if self._state == S_IDLE and self._show_hint:
                self._draw_hint(p)
            p.end()
            return

        # 选区外暗化
        clip_rects = [
            QRect(0, 0, self.width(), sel.top()),
            QRect(0, sel.bottom() + 1, self.width(), self.height() - sel.bottom() - 1),
            QRect(0, sel.top(), sel.left(), sel.height()),
            QRect(sel.right() + 1, sel.top(), self.width() - sel.right() - 1, sel.height()),
        ]
        for r in clip_rects:
            if r.width() > 0 and r.height() > 0:
                p.fillRect(r, DIM_COLOR)

        # 标注（裁剪在选区内）
        p.save()
        p.setClipRect(sel)
        for item in self._items:
            if item is self._editing_item:
                continue      # 正在编辑的那条由输入框自己显示
            paint_item(p, item)
        if self._temp is not None:
            paint_item(p, self._temp)
        if self._hover_item is not None and self._hover_item in self._items:
            self._draw_text_frame(p, self._hover_item)
        p.restore()

        # 选区边框
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(SEL_BORDER, 1, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
        p.drawRect(QRectF(sel).adjusted(0.5, 0.5, -0.5, -0.5))

        self._draw_size_badge(p, sel)

        if self._state in (S_SELECTED, S_RESIZING, S_DRAWING):
            self._draw_handles(p, sel)

        p.end()

    def _draw_hint(self, p: QPainter):
        text = "拖动鼠标框选区域  ·  单击直接截全屏  ·  Esc 取消"
        f = _font(14, bold=False)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(text) + 34
        th = 38
        x = (self.width() - tw) / 2
        y = self.height() * 0.13
        r = QRectF(x, y, tw, th)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(20, 20, 24, 210))
        p.drawRoundedRect(r, 10, 10)
        p.setFont(f)
        p.setPen(QPen(QColor(240, 240, 245)))
        p.drawText(r, int(Qt.AlignCenter), text)

    def _draw_size_badge(self, p: QPainter, sel: QRect):
        text = "%d × %d" % (sel.width(), sel.height())
        f = _font(12, bold=False)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(text) + 16
        th = fm.height() + 6
        x = sel.left()
        y = sel.top() - th - 6
        if y < 4:
            y = sel.top() + 6
        if x + tw > self.width() - 4:
            x = self.width() - tw - 4
        r = QRectF(x, y, tw, th)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 24, 215))
        p.drawRoundedRect(r, 5, 5)
        p.setFont(f)
        p.setPen(QPen(QColor(235, 235, 240)))
        p.drawText(r, int(Qt.AlignCenter), text)

    def _draw_handles(self, p: QPainter, sel: QRect):
        p.setPen(QPen(QColor(30, 40, 70, 220), 1))
        p.setBrush(QColor(255, 255, 255, 245))
        for pt in self._handle_points(sel):
            p.drawRect(QRectF(pt.x() - HANDLE_SIZE / 2, pt.y() - HANDLE_SIZE / 2,
                              HANDLE_SIZE, HANDLE_SIZE))

    def _draw_text_frame(self, p: QPainter, item):
        """鼠标停在文字上时提示「能拖」：虚线框 + 左右两个竖条手柄。"""
        r = text_rect(item)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(74, 134, 255, 200), 1, Qt.DashLine))
        p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))
        cy = r.center().y()
        for x in (r.left(), r.right()):
            box = QRectF(x - 3, cy - 11, 6, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 240))
            p.drawRoundedRect(box, 3, 3)
            p.setPen(QPen(QColor(74, 134, 255, 230), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)

    @staticmethod
    def _handle_points(sel: QRect):
        cx = sel.center().x()
        cy = sel.center().y()
        return [
            QPoint(sel.left(), sel.top()), QPoint(cx, sel.top()), QPoint(sel.right(), sel.top()),
            QPoint(sel.right(), cy), QPoint(sel.right(), sel.bottom()),
            QPoint(cx, sel.bottom()), QPoint(sel.left(), sel.bottom()), QPoint(sel.left(), cy),
        ]

    _HANDLE_NAMES = ["tl", "t", "tr", "r", "br", "b", "bl", "l"]

    def _handle_at(self, pos: QPoint):
        if self._sel.isNull():
            return ""
        pts = self._handle_points(self._sel)
        pad = HANDLE_SIZE / 2 + 3
        for name, pt in zip(self._HANDLE_NAMES, pts):
            if abs(pos.x() - pt.x()) <= pad and abs(pos.y() - pt.y()) <= pad:
                return name
        return ""

    # ---------------------------------------------------------- 鼠标
    def mousePressEvent(self, event):
        if self._text_edit is not None:
            # 这一下点击只用于结束文字输入，不再触发新建标注
            self._commit_text()
            return

        if event.button() == Qt.LeftButton:
            self.activated.emit()       # 多屏时让别的屏清掉自己的选区

        if event.button() == Qt.RightButton:
            if not self._sel.isNull():
                self._reset_selection()
            else:
                self._cancel()
            return

        if event.button() != Qt.LeftButton:
            return

        pos = self._clamp(event.pos())

        if self._state in (S_SELECTED, S_DRAWING, S_RESIZING):
            handle = self._handle_at(pos)
            if handle:
                self._state = S_RESIZING
                self._resize_handle = handle
                self._sel_before = QRect(self._sel)
                self._bar.hide()
                self.update()
                return

            if self._sel.contains(pos):
                if self._tool in (T_RECT, T_ELLIPSE, T_ARROW):
                    self._state = S_DRAWING
                    self._draw_start = QPointF(pos)
                    self._temp = AnnotItem(self._tool, QPointF(pos), QPointF(pos),
                                           self._color, 3)
                    self.update()
                    return
                if self._tool == T_PEN:
                    self._state = S_DRAWING
                    self._draw_start = QPointF(pos)
                    self._temp = AnnotItem(T_PEN, QPointF(pos), QPointF(pos),
                                           self._color, 3)
                    self.update()
                    return
                if self._tool == T_TEXT:
                    hit = self._text_item_at(pos)
                    if hit is not None:
                        edge = self._text_handle_at(pos, hit)
                        if edge:
                            # 拖左右边框 -> 改换行宽度
                            self._state = S_TEXT_WIDTH
                            self._drag_item = hit
                            self._text_edge = edge
                            self._text_edge_right = text_rect(hit).right()
                            self._bar.hide()
                            self.update()
                            return
                        # 先按着不动，松手时没移动就当作点击进入编辑
                        self._state = S_TEXT_PRESS
                        self._drag_item = hit
                        self._drag_pos = QPoint(pos)
                        self._drag_from = QPointF(hit.p1)
                        return
                    self._start_text(pos, None)
                    return
                return

            # 在选区外按下 -> 重新框选
            self._reset_selection()

        self._state = S_SELECTING
        self._origin = pos
        self._sel = QRect(pos, pos)
        self._bar.hide()
        self.update()

    def mouseMoveEvent(self, event):
        pos = self._clamp(event.pos())

        if self._state == S_SELECTING:
            self._sel = QRect(self._origin, pos).normalized()
            self.update()
            return

        if self._state == S_DRAWING and self._temp is not None:
            if self._temp.kind == T_PEN:
                _append_pen_point(self._temp, pos)
            else:
                self._temp.p2 = QPointF(pos)
            self.update()
            return

        if self._state == S_RESIZING:
            self._apply_resize(pos)
            self.update()
            return

        if self._state == S_TEXT_PRESS:
            # 移动超过 4px 才当成拖动，否则保持「点击进入编辑」
            if (pos - self._drag_pos).manhattanLength() >= 4:
                self._state = S_TEXT_MOVE
                self.setCursor(Qt.SizeAllCursor)
                self._move_text(pos)
            return

        if self._state == S_TEXT_MOVE:
            self._move_text(pos)
            return

        if self._state == S_TEXT_WIDTH:
            self._resize_text(pos)
            return

        self._update_hover(pos)
        self._update_cursor(pos)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = self._clamp(event.pos())

        if self._state == S_TEXT_PRESS:
            # 全程没移动 -> 当作点击，进入编辑
            item = self._drag_item
            self._state = S_SELECTED
            self._drag_item = None
            self._hover_item = None
            if item is not None:
                self._start_text(QPoint(int(item.p1.x()), int(item.p1.y())), item)
            self.update()
            return

        if self._state in (S_TEXT_MOVE, S_TEXT_WIDTH):
            self._state = S_SELECTED
            self._drag_item = None
            self._text_edge = ""
            self._bar.set_undo_enabled(bool(self._items))
            self._show_bar()
            self.update()
            return

        if self._state == S_SELECTING:
            self._finish_selection(pos)
            return

        if self._state == S_DRAWING:
            item = self._temp
            self._temp = None
            if item is not None:
                if item.kind == T_ARROW:
                    d = math.hypot(item.p2.x() - item.p1.x(), item.p2.y() - item.p1.y())
                    if d > 6:
                        self._items.append(item)
                elif item.kind == T_PEN:
                    # 松手位置可能比最后一个 move 更准，补一次点
                    _append_pen_point(item, pos)
                    if pen_length(item.points) >= PEN_MIN_LEN:
                        self._items.append(item)
                else:
                    r = item.rect
                    if r.width() > 4 or r.height() > 4:
                        self._items.append(item)
            self._state = S_SELECTED
            self._bar.set_undo_enabled(bool(self._items))
            self._show_bar()
            self.update()
            return

        if self._state == S_RESIZING:
            self._state = S_SELECTED
            self._resize_handle = ""
            self._show_bar()
            self.update()

    def _finish_selection(self, pos=None):
        """把"正在拖"的选区定下来并弹出工具条。

        松手和"松手事件丢失"两条路都走这里，保证不会停在既没有手柄、
        也没有工具条的中间状态。
        """
        if pos is None:
            pos = QPoint(self._sel.right(), self._sel.bottom())
        r = QRect(self._origin, pos).normalized()
        if r.width() < 6 or r.height() < 6:
            r = QRect(0, 0, self.width(), self.height())      # 单击 -> 全屏
        self._sel = r
        self._state = S_SELECTED
        self._show_bar()
        self.update()
        ulog("框选完成：选区=%d×%d 遮罩=%d×%d dpr=%.2f"
             % (r.width(), r.height(), self.width(), self.height(), self._dpr))

    def leaveEvent(self, event):
        super().leaveEvent(event)
        # 触摸板、远程桌面、鼠标被别的窗口抢走时 release 可能收不到，
        # 遮罩会卡在"拖拽中"：选区在、没有手柄也没有工具条，用户只能重来。
        # 一旦发现按键其实已经放开，就当场把选区定下来。
        if self._state == S_SELECTING and not (QApplication.mouseButtons() & Qt.LeftButton):
            self._finish_selection()

    def _apply_resize(self, pos: QPoint):
        r = QRect(self._sel_before)
        hs = set(self._resize_handle)
        min_w, min_h = 12, 12
        if "l" in hs:
            r.setLeft(min(pos.x(), r.right() - min_w))
        if "r" in hs:
            r.setRight(max(pos.x(), r.left() + min_w))
        if "t" in hs:
            r.setTop(min(pos.y(), r.bottom() - min_h))
        if "b" in hs:
            r.setBottom(max(pos.y(), r.top() + min_h))
        self._sel = r.normalized().intersected(QRect(0, 0, self.width(), self.height()))

    def _update_cursor(self, pos: QPoint):
        if self._sel.isNull():
            self.setCursor(Qt.CrossCursor)
            return
        h = self._handle_at(pos)
        cursors = {
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
            "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
            "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
        }
        if h:
            self.setCursor(cursors.get(h, Qt.CrossCursor))
        elif self._sel.contains(pos):
            if self._tool == T_TEXT:
                hit = self._text_item_at(pos)
                if hit is None:
                    self.setCursor(Qt.IBeamCursor)
                elif self._text_handle_at(pos, hit):
                    self.setCursor(Qt.SizeHorCursor)
                else:
                    self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def _clamp(self, pos: QPoint) -> QPoint:
        return QPoint(max(0, min(pos.x(), self.width() - 1)),
                      max(0, min(pos.y(), self.height() - 1)))

    # ---------------------------------------------------------- 键盘
    def keyPressEvent(self, event):
        key = event.key()

        if self._text_edit is not None:
            # 输入框有焦点时键盘事件都交给它，回车由它换行
            return

        if key == Qt.Key_Escape:
            self._cancel()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._copy()
            return
        if key == Qt.Key_F3:
            self._pin()
            return
        if event.modifiers() & Qt.ControlModifier:
            if key == Qt.Key_C:
                self._copy()
                return
            if key == Qt.Key_S:
                self._save_file()
                return
            if key == Qt.Key_Z:
                self._undo()
                return
        if key == Qt.Key_R:
            self._switch_tool(T_RECT)
            return
        if key == Qt.Key_E:
            self._switch_tool(T_ELLIPSE)
            return
        if key == Qt.Key_T:
            self._switch_tool(T_TEXT)
            return
        if key == Qt.Key_A and not (event.modifiers() & Qt.ControlModifier):
            self._switch_tool(T_ARROW)
            return
        if key == Qt.Key_P and not (event.modifiers() & Qt.ControlModifier):
            self._switch_tool(T_PEN)
            return

        if self._tool == T_TEXT and not (event.modifiers() & Qt.ControlModifier):
            if key in (Qt.Key_BracketLeft, Qt.Key_Minus):
                self._bar.bump_size(-1)
                return
            if key in (Qt.Key_BracketRight, Qt.Key_Plus, Qt.Key_Equal):
                self._bar.bump_size(1)
                return
            if key == Qt.Key_B:
                self._bar.toggle_bold()
                return

        super().keyPressEvent(event)

    # ---------------------------------------------------------- 工具栏
    def _show_bar(self):
        if self._sel.isNull():
            self._bar.hide()
            return
        try:
            self._place_bar()
        except Exception:
            import traceback
            ulog("工具栏显示异常：" + traceback.format_exc(limit=8).replace("\n", " | "))

    def _place_bar(self):
        self._bar.fit()
        w, h = self._bar.width(), self._bar.height()
        gap = 10
        sel = self._sel

        x = sel.right() + 1 - w
        y = sel.bottom() + 1 + gap
        if y + h > self.height() - 6:
            y = sel.top() - gap - h
            if y < 6:
                y = sel.top() + gap
                x = sel.right() + 1 - w
        x = max(6, min(x, self.width() - w - 6))
        y = max(6, min(y, self.height() - h - 6))
        self._bar.move(int(x), int(y))
        self._bar.show()
        self._bar.raise_()
        self._bar.update()
        # 自检要等窗口真正映射完成（立即查一定是空区域，会误判）
        QTimer.singleShot(120, self._verify_bar)

    def _verify_bar(self):
        """工具条是遮罩的子控件，个别机器（高 DPI、多屏混合缩放、远程桌面）上
        父窗口不会把它重画出来 —— 结果是"选区在、工具条不见"，用户完全没法标注。
        发现没画出来就把工具条挪到选区左上角里侧，至少保证能点到。
        """
        if not self.isVisible() or self._sel.isNull() or not self._bar.isVisible():
            return
        if not self._bar.visibleRegion().isEmpty():
            return
        sel = self._sel
        w, h = self._bar.width(), self._bar.height()
        x = max(0, min(sel.left() + 6, self.width() - w))
        y = max(0, min(sel.top() + 6, self.height() - h))
        self._bar.move(int(x), int(y))
        self._bar.show()
        self._bar.raise_()
        self._bar.update()
        ulog("工具栏未绘制出来，已回退到选区左上角：选区=%s 窗口=%dx%d 工具条=%dx%d"
             % (_rect_text(sel), self.width(), self.height(), w, h))

    def _on_tool_changed(self, kind):
        if kind != T_TEXT and self._text_edit is not None:
            self._commit_text()
        self._tool = kind
        self._hover_item = None
        self._bar.set_text_mode(kind == T_TEXT)
        if not self._sel.isNull():
            self._show_bar()

    def _switch_tool(self, kind):
        self._tool = kind
        self._bar.set_tool(kind)
        self._bar.set_text_mode(kind == T_TEXT)
        if not self._sel.isNull():
            self._show_bar()

    def _pick_color(self):
        if self._palette.isVisible():
            self._palette.hide()
            return
        self._palette.adjustSize()
        bar = self._bar
        pw, ph = self._palette.width(), self._palette.height()
        x = bar.x() + bar.width() - pw
        y = bar.y() - ph - 6
        if y < 6:
            y = bar.y() + bar.height() + 6
        x = max(6, min(x, self.width() - pw - 6))
        self._palette.move(int(x), int(y))
        self._palette.show()
        self._palette.raise_()

    def _on_palette_color(self, color):
        self._palette.hide()
        self._color = color
        self._bar.set_color(color)
        if self._text_edit is not None:
            self._text_color = QColor(color)
            self._text_edit.setStyleSheet(self._text_edit_qss())
        self.setFocus(Qt.ActiveWindowFocusReason)

    def _pick_custom_color(self):
        from PyQt5.QtWidgets import QColorDialog
        self._palette.hide()
        self._bar.hide()
        self.hide()          # 全屏置顶遮罩会挡住系统对话框
        color = QColorDialog.getColor(self._color, None, "选择标记颜色")
        if color.isValid():
            self._color = color
            self._bar.set_color(color)
        self.show()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)
        self._bar.show()
        self._bar.raise_()

    # ---------------------------------------------------------- 文字
    def _text_item_at(self, pos: QPoint):
        for item in reversed(self._items):
            if item.kind == T_TEXT and text_rect(item).contains(QPointF(pos)):
                return item
        return None

    def _text_handle_at(self, pos: QPoint, item) -> str:
        """命中文字框的左右边框，返回 "l" / "r" / ""。"""
        r = text_rect(item)
        if pos.y() < r.top() - 4 or pos.y() > r.bottom() + 4:
            return ""
        pad = 7
        if abs(pos.x() - r.left()) <= pad:
            return "l"
        if abs(pos.x() - r.right()) <= pad:
            return "r"
        return ""

    def _move_text(self, pos: QPoint):
        """整段文字跟着鼠标平移，压在选区内。"""
        item = self._drag_item
        if item is None:
            return
        r = text_rect(item)
        sel = self._sel
        x = self._drag_from.x() + (pos.x() - self._drag_pos.x())
        y = self._drag_from.y() + (pos.y() - self._drag_pos.y())
        # p1 是文字左上角，包围盒再往外扩 5px
        lo_x, hi_x = sel.left() + 5, max(sel.left() + 5, sel.right() - r.width() + 5)
        lo_y, hi_y = sel.top() + 5, max(sel.top() + 5, sel.bottom() - r.height() + 5)
        item.p1 = QPointF(min(max(x, lo_x), hi_x), min(max(y, lo_y), hi_y))
        self.update()

    def _resize_text(self, pos: QPoint):
        """拖左右边框只改换行宽度，高度由内容自己决定。

        包围盒比内容宽 10px（左右各 5px 留白），换算时要扣掉。
        """
        item = self._drag_item
        if item is None:
            return
        min_w = 48.0
        r = text_rect(item)
        sel = self._sel
        if self._text_edge == "r":
            # 让包围盒右边贴住鼠标
            right = min(max(pos.x(), r.left() + 10 + min_w), sel.right())
            item.wrap_w = max(min_w, right - r.left() - 10)
        else:
            right = min(self._text_edge_right, sel.right())
            left = min(max(pos.x(), sel.left()), right - 10 - min_w)
            item.p1 = QPointF(left + 5, item.p1.y())
            item.wrap_w = right - left - 10
        self.update()

    def _update_hover(self, pos: QPoint):
        hit = None
        if (self._tool == T_TEXT and self._state == S_SELECTED
                and not self._sel.isNull() and self._text_edit is None):
            hit = self._text_item_at(pos)
        if hit is not self._hover_item:
            self._hover_item = hit
            self.update()

    def _start_text(self, pos: QPoint, item=None):
        """新建或编辑一段文字。item 不为空表示编辑已有的文字。"""
        self._commit_text()

        if item is not None:
            self._text_pos = QPointF(item.p1)
            self._text_color = QColor(item.color)
            self._text_size = max(FONT_MIN, min(FONT_MAX, int(item.font_size)))
            self._text_bold = bool(item.bold)
            self._editing_item = item
            self._edit_wrap = float(item.wrap_w or 0.0)
            initial = item.text
        else:
            self._text_pos = QPointF(pos)
            self._text_color = QColor(self._color)
            self._editing_item = None
            self._edit_wrap = 0.0
            initial = ""
        self._bar.set_text_style(self._text_size, self._text_bold)

        edit = QTextEdit(self)
        edit.setFont(_font(self._text_size, self._text_bold))
        edit.setFrameShape(QFrame.NoFrame)
        edit.setAcceptRichText(False)
        # 已经拖过宽度的文字，编辑时沿用这个宽度，换行位置才不会跳
        edit.setLineWrapMode(QTextEdit.WidgetWidth if self._edit_wrap > 0
                             else QTextEdit.NoWrap)
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        edit.setStyleSheet(self._text_edit_qss())
        edit.setPlainText(initial)
        edit.setAttribute(Qt.WA_DeleteOnClose, False)
        edit.installEventFilter(self)
        edit.textChanged.connect(self._fit_text_edit)
        edit.show()
        self._text_edit = edit
        self._fit_text_edit()
        edit.moveCursor(QTextCursor.End)
        edit.setFocus(Qt.OtherFocusReason)
        # 工具栏保持可见，方便边打字边调字号、粗细
        self._show_bar()
        self._bar.raise_()

    def _text_edit_qss(self) -> str:
        return ("QTextEdit { background: rgba(18,18,22,225);"
                " border: 1px dashed rgba(255,255,255,0.9); border-radius: 4px;"
                " color: %s; padding: 1px 3px;"
                " selection-background-color: rgba(74,134,255,0.8); }"
                % self._text_color.name())

    def _fit_text_edit(self):
        edit = self._text_edit
        if edit is None:
            return
        fm = QFontMetrics(_font(self._text_size, self._text_bold))
        lines = edit.toPlainText().split("\n")
        if self._edit_wrap > 0:
            w = int(self._edit_wrap) + 8
        else:
            widest = max((fm.horizontalAdvance(l) for l in lines), default=0)
            max_w = max(320, min(900, self.width() - 20))
            w = max(190, min(widest + 30, max_w))
        x = max(0, min(int(self._text_pos.x()) - 5, self.width() - w))
        # 先定宽度让文档重排，再按重排后的高度定高
        y = max(0, min(int(self._text_pos.y()) - 5, self.height() - 24))
        edit.setGeometry(x, y, w, max(24, fm.lineSpacing() + 10))
        if self._edit_wrap > 0:
            # 显式给文档定宽，否则未显示的控件不会按新宽度重排
            doc = edit.document()
            doc.setDocumentMargin(0)
            doc.setTextWidth(max(10, w - 8))
            h = max(int(math.ceil(doc.size().height())) + 8, fm.lineSpacing() + 10)
        else:
            h = fm.lineSpacing() * max(1, len(lines)) + 10
        # 输入框内文字起点与最终绘制位置对齐：偏移 = 边框 1 + 内边距 3 + 1
        y = max(0, min(int(self._text_pos.y()) - 5, self.height() - h))
        edit.setGeometry(x, y, w, h)

    # ---------------------------------------------------------- 字号 / 粗细
    def _on_text_size(self, size: int):
        self._text_size = max(FONT_MIN, min(FONT_MAX, int(size)))
        self._refresh_text_style()

    def _on_text_bold(self, bold: bool):
        self._text_bold = bool(bold)
        self._refresh_text_style()

    def _refresh_text_style(self):
        """调整字号/粗细时，正在编辑的文字立即跟着变。"""
        edit = self._text_edit
        if edit is not None:
            edit.setFont(_font(self._text_size, self._text_bold))
            self._fit_text_edit()
        self.update()

    def text_style(self):
        return self._text_size, self._text_bold

    def eventFilter(self, obj, event):
        if obj is self._text_edit:
            et = event.type()
            if et == QEvent.KeyPress:
                key = event.key()
                if key == Qt.Key_Escape:
                    self._commit_text()
                    return True
                if key in (Qt.Key_Return, Qt.Key_Enter) \
                        and (event.modifiers() & Qt.ControlModifier):
                    self._commit_text()
                    return True
            elif et == QEvent.FocusOut:
                # 焦点离开输入框就当作输入完成；但点工具栏上的字号/粗细控件不算离开
                QTimer.singleShot(0, self._on_text_focus_out)
        return super().eventFilter(obj, event)

    def _on_text_focus_out(self):
        edit = self._text_edit
        if edit is None:
            return
        fw = QApplication.focusWidget()
        if fw is self or (fw is not None and (fw is self._bar or self._bar.isAncestorOf(fw))):
            # 点到工具栏（按钮都是 NoFocus，焦点会落回遮罩层）-> 继续编辑
            edit.setFocus(Qt.OtherFocusReason)
            return
        self._commit_text()

    def _commit_text(self):
        if self._text_edit is None or self._committing:
            return
        self._committing = True
        edit = self._text_edit
        self._text_edit = None
        text = edit.toPlainText().rstrip()
        edit.hide()
        edit.deleteLater()

        item = self._editing_item
        self._editing_item = None
        if text.strip():
            if item is not None:
                item.text = text
                item.color = QColor(self._text_color)
                item.font_size = self._text_size
                item.bold = self._text_bold
                if item not in self._items:
                    self._items.append(item)
            else:
                self._items.append(AnnotItem(T_TEXT, self._text_pos, self._text_pos,
                                             self._text_color, 3,
                                             text=text, font_size=self._text_size,
                                             bold=self._text_bold))
        elif item is not None and item in self._items:
            # 内容被清空 -> 删掉这条标注
            self._items.remove(item)

        self._committing = False
        self._state = S_SELECTED
        self._bar.set_undo_enabled(bool(self._items))
        if self.isActiveWindow():
            if not self._sel.isNull():
                self._show_bar()
            self.setFocus(Qt.ActiveWindowFocusReason)
        self.update()

    # ---------------------------------------------------------- 动作
    def _undo(self):
        if self._items:
            self._items.pop()
            self._bar.set_undo_enabled(bool(self._items))
            self.update()

    def _reset_selection(self):
        self._sel = QRect()
        self._state = S_IDLE
        self._items.clear()
        self._temp = None
        self._hover_item = None
        self._drag_item = None
        self._bar.set_undo_enabled(False)
        self._bar.hide()
        self.setCursor(Qt.CrossCursor)
        self.update()

    def _cancel(self):
        ulog("截图取消：状态=%s 选区=%s" % (self._state, _rect_text(self._sel)))
        if self._text_edit is not None:
            edit = self._text_edit
            self._text_edit = None
            edit.hide()
            edit.deleteLater()
        self._bar.hide()
        self._palette.hide()
        self.cancelled.emit()
        self.close()

    def _export(self) -> QImage:
        sel = self._sel
        if sel.isNull() or sel.width() < 1 or sel.height() < 1:
            return QImage()
        dpr = self._dpr
        w = max(1, int(round(sel.width() * dpr)))
        h = max(1, int(round(sel.height() * dpr)))
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.scale(dpr, dpr)
        p.translate(-sel.x(), -sel.y())
        if not self._shot.isNull():
            p.drawPixmap(0, 0, self._shot)
        for item in self._items:
            paint_item(p, item)
        p.end()
        return img

    def _copy(self):
        if self._text_edit is not None:
            self._commit_text()
        if self._sel.isNull():
            return
        img = self._export()
        if img.isNull():
            return
        QApplication.clipboard().setImage(img)
        self._bar.hide()
        ulog("截图完成：已复制 %d×%d" % (img.width(), img.height()))
        self.finished.emit(img)
        self.close()

    def closeEvent(self, event):
        # 遮罩自己消失（而不是走取消/复制/贴图）时，这条日志是唯一的线索
        ulog("遮罩关闭：状态=%s 选区=%s 窗口=%d×%d"
             % (self._state, _rect_text(self._sel), self.width(), self.height()))
        super().closeEvent(event)

    def _save_file(self):
        if self._text_edit is not None:
            self._commit_text()
        if self._sel.isNull():
            return
        img = self._export()
        if img.isNull():
            return
        import os
        from datetime import datetime
        from PyQt5.QtCore import QStandardPaths
        desk = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or os.path.expanduser("~")
        name = "我爱截图_%s.png" % datetime.now().strftime("%Y%m%d_%H%M%S")
        self._bar.hide()
        self._palette.hide()
        # 置顶遮罩会挡住文件对话框，先隐藏再弹
        self.hide()
        path, _ = QFileDialog.getSaveFileName(None, "保存截图", os.path.join(desk, name),
                                              "PNG 图片 (*.png);;JPEG 图片 (*.jpg)")
        if path:
            if not img.save(path):
                self.show()
                self._bar.show()
                self._bar.raise_()
                return
            self.finished.emit(img)
            self.close()
        else:
            self.show()
            self.activateWindow()
            self.setFocus(Qt.ActiveWindowFocusReason)
            self._bar.show()
            self._bar.raise_()

    def _pin(self):
        if self._text_edit is not None:
            self._commit_text()
        if self._sel.isNull():
            return
        img = self._export()
        if img.isNull():
            return
        screen_pos = QPoint(self._sel.left() + self._vgeo.x(),
                            self._sel.top() + self._vgeo.y())
        self._bar.hide()
        self._palette.hide()
        self.pinned.emit(img, screen_pos)
        self.close()


# ------------------------------------------------------------------ 多屏会话
class CaptureSession(QObject):
    """一次截图会话：统一管理遮罩窗口。

    平时用**一个**覆盖整个虚拟桌面的遮罩（可以跨屏框选，最省事）。
    但两块屏缩放比例不同（主屏 150% + 副屏 100%）时，一个窗口在系统层面只能
    按一个 DPI 渲染，另一块屏的内容必然错位甚至全黑 —— 这时改成**一屏一个遮罩**，
    每块屏用自己的原生像素显示，选哪块屏就在哪块屏上框。
    """

    finished = pyqtSignal(object)        # QImage
    pinned = pyqtSignal(object, object)  # QImage, QPoint
    cancelled = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, desk=None, pen_color="#FF3B30", text_size=FONT_DEFAULT,
                 text_bold=False):
        super().__init__()
        self._overlays = []
        self._active = None
        self._closed = False

        if desk is None:
            desk = capture_desktop()
        self._desk = desk

        if desk is not None and desk.is_mixed:
            primary = QApplication.primaryScreen()
            for screen, pm in desk.screens:
                if pm is None or pm.isNull():
                    continue
                ov = CaptureOverlay(pen_color, text_size, text_bold, shot=pm,
                                    vgeo=screen.geometry(),
                                    show_hint=(screen is primary))
                self._attach(ov)
        else:
            shot = desk.composite() if desk is not None else QPixmap()
            vgeo = desk.vgeo if desk is not None else virtual_geometry()
            if not shot.isNull():
                self._attach(CaptureOverlay(pen_color, text_size, text_bold,
                                            shot=shot, vgeo=vgeo))

        if self._overlays:
            self._active = self._overlays[0]

    # ---------------------------------------------------------- 组装
    def _attach(self, ov: CaptureOverlay):
        ov.finished.connect(self._on_finished)
        ov.pinned.connect(self._on_pinned)
        ov.cancelled.connect(self._on_cancelled)
        ov.activated.connect(lambda o=ov: self._on_activated(o))
        self._overlays.append(ov)

    @property
    def overlays(self):
        return list(self._overlays)

    def is_multi(self) -> bool:
        return len(self._overlays) > 1

    # ---------------------------------------------------------- 生命周期
    def show_overlay(self):
        if not self._overlays:
            self.cancelled.emit()
            return
        # 先铺满所有屏，最后把主屏那块抬起来，焦点才会落在它上面
        for ov in self._overlays:
            ov.show_overlay()
        first = self._overlays[0]
        first.raise_()
        first.activateWindow()
        first.setFocus(Qt.ActiveWindowFocusReason)

    def text_style(self):
        ov = self._active or (self._overlays[0] if self._overlays else None)
        if ov is None:
            return FONT_DEFAULT, False
        try:
            return ov.text_style()
        except RuntimeError:
            return FONT_DEFAULT, False

    def _on_activated(self, ov):
        self._active = ov
        # 一块屏开始框选，别的屏上的选区就作废（同时只保留一个选区）
        for other in self._overlays:
            if other is ov:
                continue
            try:
                if other._sel is not None and not other._sel.isNull():
                    other._reset_selection()
            except RuntimeError:
                pass

    def _close_all(self):
        if self._closed:
            return
        self._closed = True
        for ov in self._overlays:
            try:
                ov.close()
            except RuntimeError:
                pass
        self._overlays = []
        self.closed.emit()

    def _on_finished(self, image):
        # 先通知（主窗口要读一下字号/粗细），再关遮罩
        self.finished.emit(image)
        self._close_all()

    def _on_pinned(self, image, pos):
        self.pinned.emit(image, pos)
        self._close_all()

    def _on_cancelled(self):
        self.cancelled.emit()
        self._close_all()
