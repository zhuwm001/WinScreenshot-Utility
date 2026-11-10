# -*- coding: utf-8 -*-
"""把「纯字版」徽标（透明底金属渐变字）缩成界面用的署名徽标。

和 make_badge_compact.py 的区别：这张图没有底板、只有字，所以不重排、不加留白，
只做「按字高等比缩放 + 出多档倍率」。

小尺寸（10px 上下）会踩两个坑，这里都处理了：
  1) 透明区 RGB 是黑的，直接缩放会把黑色渗进边缘 → 灰边。
     做法：先预乘 alpha 再缩放，最后反预乘。
  2) 原图是浅银渐变，压到白底上几乎看不见。
     做法：按 255 拉对比（保持纯白高光不变）+ 轻微加粗 + 轻锐化。

用法：
    python tools\\make_badge_letters.py --src "...\\by-tiamma-letters-1024.png" --ink-h 9.6

参数：
    --ink-h     字高（逻辑像素，含字母上下缘的墨迹），9.6 = 比界面 12px 提示字小一号
    --darken    亮度压缩系数，1.0 保持原图；越大越深，默认 1.5
    --gain      alpha 增益，让边缘更实，默认 1.35
    --embolden  加粗核大小（在 master 分辨率上加），0 = 不加，默认 3
    --sharpen   缩放后的锐化强度，0 = 不锐化，默认 0.5
    --sizes     输出倍率，默认 1,2,3,4
"""
import argparse
import os

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_letters(src):
    """裁到 alpha 非空范围，返回 RGBA master。"""
    im = Image.open(src).convert("RGBA")
    box = im.getchannel("A").getbbox()
    if box is None:
        raise RuntimeError("图片全透明，没有可用的字")
    return im.crop(box)


def darken(im, factor):
    """按 255 拉对比：255 - (255-c)*factor，纯白高光仍是纯白。"""
    if factor == 1.0:
        return im
    r, g, b, a = im.split()
    lut = [max(0, min(255, int(round(255 - (255 - v) * factor)))) for v in range(256)]
    return Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))


def alpha_gain(im, factor):
    if factor == 1.0:
        return im
    r, g, b, a = im.split()
    a = a.point(lambda v: min(255, int(round(v * factor))))
    return Image.merge("RGBA", (r, g, b, a))


def embolden(im, size):
    if not size or size < 3:
        return im
    r, g, b, a = im.split()
    a = a.filter(ImageFilter.MaxFilter(size if size % 2 else size + 1))
    return Image.merge("RGBA", (r, g, b, a))


def resize_premultiplied(im, size):
    """预乘 alpha 后缩放，避免透明区黑色渗进边缘造成灰边。"""
    black = Image.new("RGBA", im.size, (0, 0, 0, 255))
    pre = Image.alpha_composite(black, im).convert("RGB").resize(size, Image.LANCZOS)
    a = im.getchannel("A").resize(size, Image.LANCZOS)
    pr, pg, pb = pre.split()
    out = Image.new("RGBA", size)
    pa, prl, pgl, pbl = a.load(), pr.load(), pg.load(), pb.load()
    res = out.load()
    for y in range(size[1]):
        for x in range(size[0]):
            av = pa[x, y]
            if av == 0:
                res[x, y] = (0, 0, 0, 0)
            else:
                k = 255.0 / av
                res[x, y] = (min(255, int(prl[x, y] * k)),
                             min(255, int(pgl[x, y] * k)),
                             min(255, int(pbl[x, y] * k)), av)
    return out


def build(src, ink_h=9.6, darken_f=1.5, gain=1.35, emb=3, sharpen=0.5, sizes=(1, 2, 3, 4)):
    master = load_letters(src)
    master = embolden(master, emb)
    master = alpha_gain(master, gain)
    master = darken(master, darken_f)

    # 高度取整后反算宽度，保证和原图同一长宽比（否则会出现横向压扁/拉长）
    h1 = max(4, int(round(ink_h)))
    w1 = max(4, int(round(master.width * h1 / master.height)))

    out = {}
    for mul in sizes:
        size = (int(round(w1 * mul)), int(round(h1 * mul)))
        im = resize_premultiplied(master, size)
        if sharpen:
            im = im.filter(ImageFilter.UnsharpMask(
                radius=max(0.5, 0.6 * mul), percent=int(sharpen * 100), threshold=0))
        out[int(round(w1 * mul))] = im
    return out, (w1, h1)


def main():
    ap = argparse.ArgumentParser(description="透明底金属字 → 界面署名徽标（等比缩放）")
    ap.add_argument("--src", default=os.path.expanduser(
        r"~\Desktop\by tiamma 徽标\by-tiamma-letters-1024.png"))
    ap.add_argument("--ink-h", type=float, default=9.6)
    ap.add_argument("--darken", type=float, default=1.5)
    ap.add_argument("--gain", type=float, default=1.35)
    ap.add_argument("--embolden", type=int, default=3)
    ap.add_argument("--sharpen", type=float, default=0.5)
    ap.add_argument("--sizes", default="1,2,3,4")
    ap.add_argument("--prefix", default="badge-letters")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "badge_letters"))
    args = ap.parse_args()

    muds = tuple(float(x) for x in args.sizes.replace(" ", "").split(",") if x)
    imgs, (w1, h1) = build(args.src, args.ink_h, args.darken, args.gain,
                           args.embolden, args.sharpen, muds)

    os.makedirs(args.out, exist_ok=True)
    print("字高 %.2f  darken %.2f  gain %.2f  加粗核 %d" %
          (args.ink_h, args.darken, args.gain, args.embolden))
    print("逻辑尺寸 %dx%d（1x）" % (w1, h1))
    tiers = []
    for w, im in imgs.items():
        p = os.path.join(args.out, "%s-%d.png" % (args.prefix, w))
        im.save(p)
        tiers.append(w)
        print("  %s  %dx%d" % (os.path.basename(p), im.width, im.height))

    tiers_txt = ", ".join(str(t) for t in tiers) + ("," if len(tiers) == 1 else "")
    print("\n复制到 assets\\ 后，同步 src\\main_window.py：")
    print("  author.setPixmap(self._badge_pixmap(%d))" % w1)
    print('  asset("%s-%%d.png" %% w)' % args.prefix)
    print("  for w in (%s):" % tiers_txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
