# -*- coding: utf-8 -*-
"""生成「by tiamma」银色金属徽标（亮银拉丝底板 + 白色字）。

与 make_badge.py（深色板 + 镀铬字）互补：这套是「银底白字」，字号与界面
QLabel#author（11px）一致，用作主窗口底部署名。

用法：
    python tools/make_badge_silver.py
    python tools/make_badge_silver.py --text "by tiamma" --out build\\badge_silver

输出（都在 --out 目录）：
    by-tiamma-silver-90.png    1x
    by-tiamma-silver-180.png   2x
    by-tiamma-silver-360.png   3x
    by-tiamma-silver-720.png   4x
    by-tiamma-silver-hole-720.png   文字镂空版（露出下层背景）
"""
import argparse
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FONT_BOLD = r"C:\Windows\Fonts\msyh.ttc"     # 微软雅黑 Regular，与界面同族同字重
FONT_FALLBACK = r"C:\Windows\Fonts\arial.ttf"

# 亮银拉丝：自上而下的镀铬色带（RGB）
CHROME_STOPS = [
    (0.00, (255, 255, 255)),
    (0.03, (248, 250, 253)),
    (0.10, (228, 234, 241)),
    (0.26, (168, 178, 190)),
    (0.40, (112, 122, 136)),
    (0.50, (94, 103, 117)),    # 中段暗带，托住白字
    (0.62, (122, 132, 146)),
    (0.76, (180, 189, 201)),
    (0.88, (240, 244, 250)),   # 底部反光
    (0.95, (228, 234, 242)),
    (1.00, (152, 162, 176)),
]


def _load_font(size):
    for p in (FONT_BOLD, FONT_FALLBACK):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _chrome_field(W, H):
    """垂直多段镀铬渐变（内部 1px 列插值再横向拉伸，速度快）。"""
    col = Image.new("RGB", (1, H))
    stops = CHROME_STOPS
    for y in range(H):
        t = y / max(1, H - 1)
        c = stops[-1][1]
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                c = tuple(c0[j] + (c1[j] - c0[j]) * k for j in range(3))
                break
        col.putpixel((0, y), tuple(int(v) for v in c))
    return col.resize((W, H), Image.BILINEAR)


def build(text="by tiamma", out_w=88, hole_text=False, font_px=11, base_w=88):
    """按目标宽度原生绘制（内部 4 倍超采样），返回 RGBA 图。

    out_w 是该档位的物理像素宽，base_w 是逻辑宽；字号固定为 font_px（逻辑 px），
    因此各档位缩放后视觉字号完全一致，和界面 QLabel 的 11px 对得上。
    """
    ss = 4
    dpr = out_w / float(base_w)
    u = ss * dpr                                    # 1 个逻辑像素对应的内部像素
    W, H = out_w * ss, int(round(26 * u))           # 逻辑 88×26
    px = max(1, int(round(u)))                      # 1 逻辑像素 ≈ 内部像素数
    radius = int(round(6 * u))

    # ---------------- 底板：亮银 + 拉丝 ----------------
    field = _chrome_field(W, H)
    # 水平拉丝：极轻的横向噪声，避免纯渐变的塑料感
    noise = Image.effect_noise((W, H), 18).convert("L")
    noise = noise.filter(ImageFilter.GaussianBlur(px * 0.5))
    noise = noise.point(lambda v: 128 + int((v - 128) * 0.55))
    field = ImageChops.overlay(field, noise.convert("RGB"))

    shape = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, W - 1, H - 1), radius=radius, fill=255)

    plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    plate.paste(field, (0, 0), shape)

    def _shift(img, dx, dy):
        out = Image.new(img.mode, img.size, 0)
        out.paste(img, (dx, dy))
        return out

    # 顶部内高光（1px 亮边）+ 底部内阴影，做出金属倒角
    top = ImageChops.subtract(shape, _shift(shape, 0, px))
    top = top.filter(ImageFilter.GaussianBlur(px * 0.35)).point(lambda v: int(v * 0.85))
    plate.paste(Image.new("RGBA", (W, H), (255, 255, 255, 255)), (0, 0), top)
    bot = ImageChops.subtract(shape, _shift(shape, 0, -px))
    bot = bot.filter(ImageFilter.GaussianBlur(px * 0.35)).point(lambda v: int(v * 0.45))
    plate.paste(Image.new("RGBA", (W, H), (70, 78, 90, 255)), (0, 0), bot)

    # 外描边：淡灰，明确边界又不抢眼
    ImageDraw.Draw(plate).rounded_rectangle(
        (0, 0, W - 1, H - 1), radius=radius, outline=(150, 158, 170, 150), width=px)

    # ---------------- 文字（字号锁定 font_px 逻辑像素） ----------------
    fs = max(6, int(round(font_px * u)))
    font = _load_font(fs)
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    bb = probe.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    limit = W - int(round(10 * u))
    if tw > limit:                                  # 只有超宽才等比缩，正常不会触发
        font = _load_font(max(6, int(fs * limit / tw)))
        bb = probe.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]

    sw = max(1, int(round(ss * 0.6)))               # 极轻加粗（约 0.15 物理 px）
    pos = ((W - tw) // 2 - bb[0], (H - th) // 2 - bb[1])
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text(pos, text, font=font, fill=255,
                              stroke_width=sw, stroke_fill=255)

    # 文字底部软投影，让白字从银面上浮起来
    smask = mask.filter(ImageFilter.GaussianBlur(ss * 0.8)).point(lambda v: int(v * 0.38))
    shadow = Image.new("RGBA", (W, H), (20, 26, 36, 0))
    shadow.putalpha(_shift(smask, 0, max(1, ss // 2)))
    plate = Image.alpha_composite(plate, shadow)

    if hole_text:
        # 镂空：把字挖掉，露出下层背景
        hole = Image.new("L", (W, H), 255)
        ImageDraw.Draw(hole).text(pos, text, font=font, fill=0,
                                  stroke_width=sw, stroke_fill=0)
        plate.putalpha(ImageChops.multiply(plate.getchannel("A"), hole))
    else:
        text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        text_layer.paste(Image.new("RGBA", (W, H), (255, 255, 255, 255)), (0, 0), mask)
        # 1 物理像素的暗描边，白字压在浅银上也不糊（按物理像素走，各档位粗细微一致）
        ring = mask.filter(ImageFilter.MaxFilter(2 * ss + 1))
        ring_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ring_layer.paste(Image.new("RGBA", (W, H), (48, 56, 70, 95)), (0, 0), ring)
        plate = Image.alpha_composite(plate, ring_layer)
        plate = Image.alpha_composite(plate, text_layer)

    return plate.resize((out_w, max(1, int(round(H / ss)))), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="by tiamma")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "badge_silver"))
    ap.add_argument("--sizes", default="88,176,352,704")
    ap.add_argument("--desktop", default="", help="额外拷贝到的目录")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    created = []
    for w in sizes:
        img = build(args.text, w)
        p = os.path.join(args.out, "by-tiamma-silver-%d.png" % w)
        img.save(p)
        created.append(p)

    hole = build(args.text, sizes[-1], hole_text=True)
    p = os.path.join(args.out, "by-tiamma-silver-hole-%d.png" % sizes[-1])
    hole.save(p)
    created.append(p)

    if args.desktop:
        os.makedirs(args.desktop, exist_ok=True)
        for src in created:
            dst = os.path.join(args.desktop, os.path.basename(src))
            if os.path.exists(dst):
                # 不覆盖用户已有文件
                base, ext = os.path.splitext(dst)
                n = 2
                while os.path.exists("%s-%d%s" % (base, n, ext)):
                    n += 1
                dst = "%s-%d%s" % (base, n, ext)
            with open(src, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read())

    for p in created:
        im = Image.open(p)
        print("%-40s %dx%d" % (os.path.basename(p), im.width, im.height))


if __name__ == "__main__":
    main()
