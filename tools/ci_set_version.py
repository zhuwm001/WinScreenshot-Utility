# -*- coding: utf-8 -*-
"""CI 用：把 installer.iss 里的版本号改成指定值。

保持原文件的编码状态（原来有没有 UTF-8 BOM 就写回什么），
因为 Inno Setup 对含中文的脚本是否按 UTF-8 解析跟 BOM 有关。

用法：python tools/ci_set_version.py 1.2.0
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ISS = ROOT / "installer.iss"
PATTERN = r'#define MyAppVersion "[^"]*"'


def main(argv):
    if len(argv) != 2:
        print("用法: python tools/ci_set_version.py <版本号，如 1.2.0>")
        return 2

    ver = argv[1].strip().lstrip("vV")
    if not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        print("版本号必须是 x.y.z 形式，收到: %r" % argv[1])
        return 2

    raw = ISS.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")

    new_text, count = re.subn(PATTERN, '#define MyAppVersion "%s"' % ver, text)
    if count != 1:
        print("在 %s 里找到 %d 处 MyAppVersion，预期 1 处，未修改" % (ISS, count))
        return 1

    if new_text == text:
        print("installer.iss 已是 %s，无需改动" % ver)
        return 0

    ISS.write_bytes((b"\xef\xbb\xbf" if has_bom else b"") + new_text.encode("utf-8"))
    print("installer.iss -> %s（BOM: %s）" % (ver, "保留" if has_bom else "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
