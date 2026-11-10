# -*- coding: utf-8 -*-
"""生成「by tiamma」银色金属徽标（深色底板 + 镀铬字）。

用法：
    python tools/make_badge.py                 # 默认生成 by tiamma 全套
    python tools/make_badge.py --text "TIAMMA" --out build\\badge_tiamma

输出：
    by-tiamma-badge-1024.png   深色圆角板 + 金属字（透明背景）
    by-tiamma-badge-512.png
    by-tiamma-badge-256.png
    by-tiamma-letters-1024.png 只有金属字，无底板（透明背景）
设计分辨率 1024×276，内部按 3 倍超采样绘制再降采样，边缘干净。
"""
import argparse
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SS = 3                     # 超采样倍数
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"


def _shift(img, dx, dy):
    """整体平移，空出来的地方填 0。"""
    out = Image.new(img.mode, img.size, 0)
    out.paste(img, (dx, dy))
    return out


def metal_text(text, font, tracking=0.0):
    """返回 (RGBA 金属字图层, 掩码)，已按 SS 超采样绘制。"""
    # 1) 先量字宽，用于居中
    probe = ImageDraw.Draw(Image.new("L", (10, 10)))
    widths = [probe.textlength(ch, font=font) for ch in text]
    track = tracking * font.size
    total_w = sum(widths) + track * (len(text) - 1)
    bbox = probe.textbbox((0, 0), text, font=font)
    ascent, descent = font.getmetrics()
    h = ascent + descent
    w = int(total_w) + 40

    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    sw = max(1, int(font.size * 0.016))   # 稍微加重笔画，接近参考图的粗体密度
    x = 20.0
    for ch, cw in zip(text, widths):
        d.text((x, 0), ch, font=font, fill=255, stroke_width=sw, stroke_fill=255)
        x += cw + track

    # 2) 垂直方向的镀铬渐变（顶部亮银 → 中段灰银 → 底部回亮）
    stops = [
        (0.00, (253, 254, 255)),
        (0.16, (235, 240, 247)),
        (0.40, (190, 199, 210)),
        (0.50, (218, 226, 236)),
        (0.64, (172, 181, 193)),
        (0.84, (205, 213, 223)),
        (1.00, (238, 244, 250)),
    ]
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                grad.putpixel((0, y), tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3)))
                break
    grad = grad.resize((w, h), Image.BILINEAR)

    # 3) 用浮雕效果做斜角高光/阴影，再与渐变做 overlay 混合
    emb = mask.filter(ImageFilter.EMBOSS)
    # 增强浮雕对比度（128 为中性），但别太猛，否则字面出现硬邦邦的色带
    emb = emb.point(lambda v: max(0, min(255, int(128 + (v - 128) * 1.55))))
    metal = ImageChops.overlay(grad, emb.convert("RGB"))

    # 4) 细拉丝：轻微水平噪声，让金属不那么"塑料"
    noise = Image.effect_noise((w, h), 26).convert("L").filter(ImageFilter.GaussianBlur(0.4))
    noise = noise.point(lambda v: 128 + (v - 128) // 3)
    metal = ImageChops.overlay(metal, noise.convert("RGB"))

    # 5) 轻微锐化，让镀铬的转折更"硬"一点
    metal = metal.filter(ImageFilter.UnsharpMask(
        radius=max(1.0, font.size * 0.02), percent=90, threshold=1))

    rgba = metal.convert("RGBA")
    rgba.putalpha(mask)
    return rgba, mask


def build(text, out_w=1024):
    """按目标宽度原生绘制（内部超采样），小尺寸也不会因为缩放大图而发虚。"""
    ss = 3 if out_w >= 768 else 4
    h = int(round(out_w * 0.268))
    W, H = out_w * ss, h * ss
    pad_x = int(W * 0.055)
    pad_y = int(H * 0.155)
    px = ss                      # 1 个输出像素对应的内部像素

    # ---------- 底板 ----------
    plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    radius = int(H * 0.16)
    # 垂直渐变（上略亮、下压暗），营造金属/亚克力板的厚度感
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / max(1, H - 1)
        top = (34, 37, 42)
        bot = (11, 12, 14)
        grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t ** 0.9) for i in range(3)))
    grad = grad.resize((W, H))
    plate_shape = Image.new("L", (W, H), 0)
    ImageDraw.Draw(plate_shape).rounded_rectangle(
        (0, 0, W - 1, H - 1), radius=radius, fill=255)
    plate.paste(grad, (0, 0), plate_shape)

    # 顶部内高光 + 底部内阴影，像金属倒角
    edge = ImageChops.subtract(plate_shape, _shift(plate_shape, 0, px))
    edge = edge.filter(ImageFilter.GaussianBlur(px * 0.4)).point(lambda v: int(v * 0.30))
    plate.paste(Image.new("RGBA", (W, H), (255, 255, 255, 255)), (0, 0), edge)
    low = ImageChops.subtract(plate_shape, _shift(plate_shape, 0, -px))
    low = low.filter(ImageFilter.GaussianBlur(px * 0.4)).point(lambda v: int(v * 0.55))
    plate.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), low)

    # 外描边
    d = ImageDraw.Draw(plate)
    d.rounded_rectangle((1, 1, W - 2, H - 2), radius=radius,
                        outline=(0, 0, 0, 90), width=px)

    # ---------- 文字 ----------
    target_w = W - pad_x * 2
    lo, hi = 10, H
    font = ImageFont.truetype(FONT_BOLD, 10)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        f = ImageFont.truetype(FONT_BOLD, mid)
        bb = ImageDraw.Draw(Image.new("L", (8, 8))).textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= target_w and bb[3] - bb[1] <= (H - pad_y * 2):
            lo, font = mid, f
        else:
            hi = mid - 1

    layer, mask = metal_text(text, font)
    bb = mask.getbbox()
    layer = layer.crop(bb)
    tw, th = layer.size
    tx = (W - tw) // 2
    # 有 descender（y 的尾巴）时按字面墨迹居中会显得偏下，往上抬一点做视觉居中
    ty = (H - th) // 2 - int(H * 0.012)

    # 文字下方的暗投影，让字"浮"起来
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    smask = Image.new("L", (W, H), 0)
    smask.paste(layer.getchannel("A"), (tx, ty + int(H * 0.008)))
    smask = smask.filter(ImageFilter.GaussianBlur(px * 1.0)).point(lambda v: int(v * 0.85))
    shadow.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), smask)
    plate = Image.alpha_composite(plate, shadow)

    # 文字外圈的深色描边，避免亮字直接压在亮底板上发糊；
    # 小尺寸（≤160px 宽）下这圈描边会吃掉笔画细节，直接省略。
    if out_w > 160:
        ring = mask.crop(bb).filter(ImageFilter.MaxFilter(2 * px + 1))
        ring_layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ring_layer.paste(Image.new("RGBA", (tw, th), (6, 7, 9, 235)), (0, 0), ring)
        outline = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        outline.paste(ring_layer, (tx, ty))
        plate = Image.alpha_composite(plate, outline)
    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    text_layer.paste(layer, (tx, ty))
    composed = Image.alpha_composite(plate, text_layer)

    badge = composed.resize((out_w, h), Image.LANCZOS)
    letters = text_layer.resize((max(1, tw // ss), max(1, th // ss)), Image.LANCZOS)
    return badge, letters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="by tiamma")
    ap.add_argument("--prefix", default="by-tiamma")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "badge"))
    ap.add_argument("--desktop", default="")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    created = []
    badge, letters = build(args.text, 1024)
    for w in (1024, 512, 256, 208, 128, 104):
        img = badge if w == 1024 else build(args.text, w)[0]
        p = os.path.join(args.out, "%s-badge-%d.png" % (args.prefix, w))
        img.save(p)
        created.append(p)
    p = os.path.join(args.out, "%s-letters-1024.png" % args.prefix)
    letters.save(p)
    created.append(p)

    if args.desktop:
        os.makedirs(args.desktop, exist_ok=True)
        for src in created:
            dst = os.path.join(args.desktop, os.path.basename(src))
            with open(src, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read())

    for p in created:
        im = Image.open(p)
        print("%-52s %dx%d" % (os.path.basename(p), im.width, im.height))


if __name__ == "__main__":
    main()
