# -*- coding: utf-8 -*-
"""把「个人徽标」重排成紧凑版：字号不变，蓝底胶囊收紧贴字。

原图上下留白很大（字只占高度的 24%），缩到「字高 10.5px」后框显得空。
这里的做法是拆层重建：
  1) 在蓝色底板内定位白色文字，量出文字的真实宽高
  2) 从纯底板区域逐行取平均色，得到一条垂直渐变
  3) 按「文字 + 少量内边距」重画一个圆角胶囊，填充这条渐变
  4) 把原分辨率的文字层叠回去（所以字号完全不变）
  5) 整体缩放到目标字高，出 1x~4x

注意：原图内嵌的那圈白色装饰弧线不保留 —— 它的比例依赖大留白，
收紧后必然变形，留着反而糊成一团。

用法：
    python tools/make_badge_compact.py --src "C:\\...\\个人徽标.jpg" --text-h 10.5

四个可调参数（都不用改代码）：
    --text-h   字高（逻辑像素），决定徽标整体大小，默认 10.5
    --pad-y    上下留白，单位是「字高的倍数」，默认 0.40
    --pad-x    左右留白，单位是「字高的倍数」，默认 0.55
    --radius   圆角半径，单位是「底板高度的比例」，默认 0.34（0.5 = 完全胶囊）
改完 --text-h 或留白后宽度会变，记得同步 src/main_window.py（脚本会打印要改的值）。
"""
import argparse
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

WHITE = 205   # 判为「白色文字/装饰」的阈值


def content_bbox(im, thr=8):
    bg = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im.convert("RGB"), bg).convert("L")
    return diff.point(lambda v: 255 if v > thr else 0).getbbox()


def find_text(im):
    """复用已验证的「蓝色区内白像素行分布」判定，返回文字带上下界。"""
    import make_badge_photo as PHOT
    y0, y1 = PHOT.text_height(im)
    if y0 is None:
        raise RuntimeError("没找到白色文字")
    return y0, y1


def text_x_range(im, y0, y1, thr=20, margin=0.08):
    """列密度找文字左右边界：跳过两侧背景白和细装饰线。"""
    rgb = im.convert("RGB")
    px = rgb.load()
    w = rgb.width
    lo, hi = int(w * margin), int(w * (1 - margin))
    cols = {}
    for x in range(lo, hi):
        c = 0
        for y in range(y0, y1 + 1):
            r, g, b = px[x, y]
            if r > WHITE and g > WHITE and b > WHITE:
                c += 1
        cols[x] = c
    # 最长的连续「够密」区段；字母之间、词间空格允许 60px 以内断档
    segs = []
    start = None
    last_hit = None
    for x in range(lo, hi):
        if cols[x] >= thr:
            if start is None:
                start = x
            last_hit = x
        elif start is not None and x - last_hit > 150:
            segs.append((start, last_hit))
            start = None
    if start is not None:
        segs.append((start, last_hit))
    if not segs:
        raise RuntimeError("没找到文字左右边界")
    best = max(segs, key=lambda s: s[1] - s[0])
    return best[0], best[1]


def gradient_from_plate(im, y0, y1):
    """逐行取「非白像素」的平均色，得到底板的垂直渐变（长度 = 行数）。"""
    rgb = im.convert("RGB")
    px = rgb.load()
    w = rgb.width
    xs = range(int(w * 0.12), int(w * 0.88), 3)
    rows = []
    for y in range(y0, y1 + 1):
        acc = [0, 0, 0]
        n = 0
        for x in xs:
            r, g, b = px[x, y]
            if min(r, g, b) < 235:            # 只要底板，跳过白字/白线/背景
                acc[0] += r
                acc[1] += g
                acc[2] += b
                n += 1
        if n:
            rows.append(tuple(v // n for v in acc))
    return rows


def build(src, text_h=10.5, pad_y=0.40, pad_x=0.55, radius_ratio=0.34):
    im = Image.open(src).convert("RGB")
    im = im.crop(content_bbox(im))
    y0, y1 = find_text(im)
    th = y1 - y0 + 1
    x0, x1 = text_x_range(im, y0, y1)
    tw = x1 - x0 + 1

    # ---- 底板：按原图渐变重画一个紧凑胶囊 ----
    grad = gradient_from_plate(im, y0 - int(th * 1.4), y1 + int(th * 1.4))
    H2 = int(round(th * (1 + 2 * pad_y)))
    W2 = int(round(tw + 2 * pad_x * th))
    radius = int(round(H2 * radius_ratio))

    strip = Image.new("RGB", (W2, H2))
    sp = strip.load()
    gh = len(grad)
    for y in range(H2):
        c = grad[min(gh - 1, int(y * gh / H2))]
        for x in range(W2):
            sp[x, y] = c

    shape = Image.new("L", (W2, H2), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, W2 - 1, H2 - 1), radius=radius, fill=255)

    plate = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    plate.paste(strip, (0, 0), shape)

    def _shift(img, dy):
        out = Image.new(img.mode, img.size, 0)
        out.paste(img, (0, dy))
        return out

    # 顶边高光 + 底边压暗，找回一点厚玻璃的感觉
    edge = ImageChops.subtract(shape, _shift(shape, max(1, H2 // 90)))
    edge = edge.filter(ImageFilter.GaussianBlur(H2 * 0.01)).point(lambda v: int(v * 0.55))
    plate.paste(Image.new("RGBA", (W2, H2), (255, 255, 255, 255)), (0, 0), edge)
    low = ImageChops.subtract(shape, _shift(shape, -max(1, H2 // 90)))
    low = low.filter(ImageFilter.GaussianBlur(H2 * 0.01)).point(lambda v: int(v * 0.30))
    plate.paste(Image.new("RGBA", (W2, H2), (6, 18, 48, 255)), (0, 0), low)

    # ---- 文字层：原分辨率，只取文字带内、左右边界之间的白色 ----
    rgb = im.convert("RGB")
    r, g, b = rgb.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    m = mn.point(lambda v: 255 if v > WHITE else 0)
    band = Image.new("L", rgb.size, 0)
    band.paste(m.crop((x0, y0, x1 + 1, y1 + 1)), (x0, y0))
    band = band.filter(ImageFilter.GaussianBlur(0.8))

    glyph = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    glyph.paste(Image.new("RGBA", (tw, th), (255, 255, 255, 255)), (0, 0),
                band.crop((x0, y0, x1 + 1, y1 + 1)))

    txt = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    txt.paste(glyph, ((W2 - tw) // 2, (H2 - th) // 2), glyph)
    composed = Image.alpha_composite(plate, txt)

    scale = text_h / th
    w1 = max(8, int(round(W2 * scale)))
    h1 = max(8, int(round(H2 * scale)))
    return composed.resize((w1, h1), Image.LANCZOS), (w1, h1)


def main():
    ap = argparse.ArgumentParser(description="把个人徽标重排成紧凑胶囊（字号不变、边框收紧）")
    ap.add_argument("--src", default=os.path.expanduser(r"~\Desktop\个人徽标.jpg"),
                    help="原始徽标图片（白底 JPG/PNG 都行）")
    ap.add_argument("--text-h", type=float, default=10.5,
                    help="字高（逻辑像素），10.5 与界面 12px 提示文字视觉等大")
    ap.add_argument("--pad-y", type=float, default=0.40,
                    help="上下留白 = 字高 × 该值，默认 0.40")
    ap.add_argument("--pad-x", type=float, default=0.55,
                    help="左右留白 = 字高 × 该值，默认 0.55")
    ap.add_argument("--radius", type=float, default=0.34,
                    help="圆角半径 = 底板高度 × 该值，0.5 为完全胶囊，默认 0.34")
    ap.add_argument("--sizes", default="1,2,3,4",
                    help="输出倍率，逗号分隔，默认 1,2,3,4（对应 100%%/200%%/300%%/400%% 缩放屏）")
    ap.add_argument("--prefix", default="personal-badge")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "personal_badge_compact"))
    args = ap.parse_args()

    muds = [float(x) for x in str(args.sizes).replace(" ", "").split(",") if x]

    os.makedirs(args.out, exist_ok=True)
    img, (w1, h1) = build(args.src, args.text_h, args.pad_y, args.pad_x, args.radius)
    print("字高 %.1f  上下留白 %.2f  左右留白 %.2f  圆角 %.2f"
          % (args.text_h, args.pad_y, args.pad_x, args.radius))
    print("逻辑尺寸 %dx%d（1x）" % (w1, h1))

    tiers = []
    for mul in muds:
        tw_, th_ = int(round(w1 * mul)), int(round(h1 * mul))
        p = os.path.join(args.out, "%s-%d.png" % (args.prefix, tw_))
        img.resize((tw_, th_), Image.LANCZOS).save(p)
        tiers.append(tw_)
        print("  %s  %dx%d" % (os.path.basename(p), tw_, th_))

    # 尺寸一变，界面里挑图的三处值必须跟着改，这里直接给出来
    tiers_txt = ", ".join(str(t) for t in tiers) + ("," if len(tiers) == 1 else "")
    print("\n把新图复制到 assets\\ 后，同步 src\\main_window.py 这三处：")
    print("  author.setPixmap(self._badge_pixmap(%d))" % w1)
    print("  for w in (%s):" % tiers_txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
