# -*- coding: utf-8 -*-
"""生成徽标展示图（浅底 / 深底 / 纯字版），用于给别人看效果或放进品牌包。"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BADGE_DIR = os.path.join(ROOT, "build", "badge")

W, H = 1400, 780
BG_LIGHT = (255, 255, 255)
BG_DARK = (22, 24, 28)
TEXT = (120, 128, 140)
FONT = r"C:\Windows\Fonts\msyh.ttc"


def main():
    sheet = Image.new("RGB", (W, H), (247, 248, 251))
    d = ImageDraw.Draw(sheet)

    badge = Image.open(os.path.join(BADGE_DIR, "by-tiamma-badge-1024.png")).convert("RGBA")
    letters = Image.open(os.path.join(BADGE_DIR, "by-tiamma-letters-1024.png")).convert("RGBA")

    # 左：浅色底，右：深色底
    panel_w, panel_h = 640, 300
    panes = [((30, 90), BG_LIGHT, "浅色背景", "1024 × 274 px"),
             ((730, 90), BG_DARK, "深色背景", "1024 × 274 px")]
    for (x, y), bg, title, sub in panes:
        d.rounded_rectangle((x, y, x + panel_w, y + panel_h), radius=18, fill=bg,
                            outline=(228, 232, 240))
        b = badge.resize((500, int(500 * badge.height / badge.width)), Image.LANCZOS)
        sheet.paste(b, (x + (panel_w - b.width) // 2, y + 96), b)
        f = ImageFont.truetype(FONT, 26)
        d.text((x + 26, y + 24), title, font=f, fill=TEXT if bg == BG_LIGHT else (150, 158, 170))
        f2 = ImageFont.truetype(FONT, 20)
        d.text((x + 26, y + panel_h - 44), sub, font=f2,
               fill=(170, 176, 188) if bg == BG_LIGHT else (110, 118, 130))

    # 下：纯字版，放在深色底上（银字在浅底上本来就该配深色背景）
    y0 = 430
    d.rounded_rectangle((30, y0, 1370, y0 + 300), radius=18, fill=(17, 18, 21),
                        outline=(40, 43, 49))
    lt = letters.resize((700, int(700 * letters.height / letters.width)), Image.LANCZOS)
    sheet.paste(lt, ((W - lt.width) // 2, y0 + 130), lt)
    d.text((56, y0 + 24), "纯字版（透明背景，无底板）", font=ImageFont.truetype(FONT, 26),
           fill=(150, 158, 170))
    d.text((56, y0 + 262), "底色由你决定，适合深色界面或视频角标", font=ImageFont.truetype(FONT, 20),
           fill=(110, 118, 130))

    out = os.path.join(BADGE_DIR, "预览.png")
    sheet.save(out)
    print("saved", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
