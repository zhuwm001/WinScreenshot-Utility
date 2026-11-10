# -*- coding: utf-8 -*-
"""把照片式徽标（白底 JPG）处理成界面可用的透明 PNG，并按目标字高等比缩放。

处理链路：
  1) 裁掉四周空白
  2) 用「饱和度主体 + 内部孔洞填充」把主体轮廓找出来，剪掉外围那圈雾状外发光
  3) 从边缘 flood fill，把与外界连通的白色变透明（内部白字/白弧不动）
  4) 按「文字墨迹高度 = 目标 px」等比缩放出 1x/2x/3x/4x 四档

用法：
    python tools/make_badge_photo.py --src "C:\\...\\个人徽标.jpg" --text-h 12
"""
import argparse
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def content_bbox(im, thr=8):
    bg = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im.convert("RGB"), bg).convert("L")
    diff = diff.point(lambda v: 255 if v > thr else 0)
    return diff.getbbox()


def body_mask(im, sat_thr=45, grow=25):
    """彩色主体的掩码：色差大的区域膨胀后，把被包住的白色（文字）补回来。"""
    rgb = im.convert("RGB")
    r, g, b = rgb.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    diff = ImageChops.subtract(mx, mn)
    body = diff.point(lambda v: 255 if v > sat_thr else 0)
    body = body.filter(ImageFilter.MaxFilter(grow))
    body = body.filter(ImageFilter.GaussianBlur(1.2)).point(lambda v: 255 if v > 110 else 0)

    # 反相后从边缘 flood fill：能连到外面的都是背景，剩下的孔洞（白字）保留
    inv = ImageChops.invert(body)
    w, h = inv.size
    seeds = ([(x, 0) for x in range(0, w, 7)] + [(x, h - 1) for x in range(0, w, 7)]
             + [(0, y) for y in range(0, h, 7)] + [(w - 1, y) for y in range(0, h, 7)])
    for s in seeds:
        if inv.getpixel(s) == 255:
            ImageDraw.floodfill(inv, s, 138, thresh=0)
    return inv.point(lambda v: 0 if v == 138 else 255)


def strip_white_bg(im, white_thr=238):
    """从四条边 flood fill 白色，只把与外部连通的白色变透明。"""
    rgb = im.convert("RGB")
    w, h = rgb.size
    r, g, b = rgb.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    white = mn.point(lambda v: 255 if v >= white_thr else 0)
    fill = white.copy()
    step = max(1, min(w, h) // 40)
    seeds = ([(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)]
             + [(0, y) for y in range(0, h, step)] + [(w - 1, y) for y in range(0, h, step)])
    for s in seeds:
        if fill.getpixel(s) == 255:
            ImageDraw.floodfill(fill, s, 128, thresh=0)
    alpha = fill.point(lambda v: 0 if v == 128 else 255)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def text_height(im, blue_thr=40, white_thr=238):
    """量白色文字的墨迹高度：蓝色区域内纯白像素的行分布里取最长连续段。"""
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    hitting = []
    for y in range(h):
        blues = [x for x in range(0, w, 2) if px[x, y][2] > px[x, y][0] + blue_thr]
        if len(blues) < 40:
            continue
        x0, x1 = min(blues), max(blues)
        if x1 - x0 < 100:
            continue
        cnt = 0
        for x in range(x0 + 6, x1 - 6, 2):
            r, g, b = px[x, y]
            if r > white_thr and g > white_thr and b > white_thr:
                cnt += 1
        if cnt > 25:
            hitting.append(y)
    if not hitting:
        return None, None
    best = (hitting[0], hitting[0])
    start = prev = hitting[0]
    for y in hitting[1:]:
        if y - prev > 6:
            if prev - start > best[1] - best[0]:
                best = (start, prev)
            start = y
        prev = y
    if prev - start > best[1] - best[0]:
        best = (start, prev)
    return best[0], best[1]


def process(src, text_h=12.0, out_dir=None, prefix="personal-badge", write_master=True):
    """返回 (逻辑宽, 逻辑高, 生成的 1x~4x 文件列表)。"""
    out_dir = out_dir or os.path.join(ROOT, "build", "personal_badge")
    os.makedirs(out_dir, exist_ok=True)

    im = Image.open(src).convert("RGB")
    im = im.crop(content_bbox(im))
    y0, y1 = text_height(im)
    if y0 is None:
        raise RuntimeError("没找到白色文字区域，无法按字高缩放")
    th = y1 - y0 + 1

    clear = strip_white_bg(im, white_thr=238)
    clear.putalpha(ImageChops.multiply(clear.getchannel("A"), body_mask(im)))
    bb = clear.getbbox()
    clear = clear.crop(bb)

    scale = text_h / th
    w1 = int(round(clear.width * scale))
    h1 = int(round(clear.height * scale))

    if write_master:
        clear.save(os.path.join(out_dir, "master.png"))

    made = []
    for mul in (1, 2, 3, 4):
        p = os.path.join(out_dir, "%s-%d.png" % (prefix, w1 * mul))
        clear.resize((w1 * mul, h1 * mul), Image.LANCZOS).save(p)
        made.append(p)
    return w1, h1, made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.expanduser(r"~\Desktop\个人徽标.jpg"))
    ap.add_argument("--text-h", type=float, default=12.0)
    ap.add_argument("--prefix", default="personal-badge")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "personal_badge"))
    args = ap.parse_args()

    w1, h1, made = process(args.src, args.text_h, args.out, args.prefix)
    print("文字高 %.0fpx → 逻辑尺寸 %dx%d" % (args.text_h, w1, h1))
    for p in made:
        print(os.path.basename(p), Image.open(p).size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
