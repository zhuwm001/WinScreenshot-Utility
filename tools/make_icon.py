# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico（多尺寸）。"""
import os
from PIL import Image, ImageDraw

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
SIZE = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_icon():
    S = SIZE
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ---- 圆角矩形底：左上偏蓝，右下偏紫的渐变 ----
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    c1 = (74, 134, 255)
    c2 = (139, 92, 246)
    for y in range(S):
        for x in range(0, S, 4):
            t = (x / S * 0.45) + (y / S * 0.55)
            col = lerp(c1, c2, min(1.0, t))
            for k in range(4):
                if x + k < S:
                    px[x + k, y] = col
    # 圆角遮罩
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.225), fill=255)
    bg.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, bg)

    d = ImageDraw.Draw(img)

    # ---- 取景框四角（白色 L 形）----
    white = (255, 255, 255, 255)
    pad = int(S * 0.245)
    arm = int(S * 0.155)
    w = int(S * 0.062)
    r = w // 2
    L, T, R, B = pad, pad, S - pad, S - pad

    def corner(x, y, dx, dy):
        # 横向臂
        d.rounded_rectangle(
            [min(x, x + dx * arm) - r, y - r, max(x, x + dx * arm) + r, y + r],
            radius=r, fill=white)
        # 纵向臂
        d.rounded_rectangle(
            [x - r, min(y, y + dy * arm) - r, x + r, max(y, y + dy * arm) + r],
            radius=r, fill=white)

    corner(L, T, 1, 1)
    corner(R, T, -1, 1)
    corner(L, B, 1, -1)
    corner(R, B, -1, -1)

    # ---- 中间的小圆点 + 环形 ----
    cx, cy = S // 2, S // 2
    ro = int(S * 0.085)
    ri = int(S * 0.038)
    d.ellipse([cx - ro, cy - ro, cx + ro, cy + ro], fill=white)
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=(0, 0, 0, 0))

    img = img.resize((256, 256), Image.LANCZOS)

    os.makedirs(OUT_DIR, exist_ok=True)
    ico_path = os.path.join(OUT_DIR, "app.ico")
    img.save(ico_path, format="ICO",
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    # 顺便存一张 png 供界面/文档使用
    img.save(os.path.join(OUT_DIR, "app.png"), format="PNG")
    print("icon ->", ico_path)


if __name__ == "__main__":
    make_icon()
