# -*- coding: utf-8 -*-
"""CI 用：把版本号同步写进 install .iss 和程序源码。

两处都要改，少一处就会出问题：
  - installer.iss      -> 安装包文件名 / 卸载列表里显示的版本
  - src/app_config.py  -> 程序运行时自己报的版本（更新检查就是拿它跟 Release 比）

保持原文件的编码状态（原来有没有 UTF-8 BOM 就写回什么），
因为 Inno Setup 对含中文的脚本是否按 UTF-8 解析跟 BOM 有关。

用法：python tools/ci_set_version.py 1.2.0
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

TARGETS = [
    (ROOT / "installer.iss", r'#define MyAppVersion "[^"]*"',
     '#define MyAppVersion "%s"'),
    (ROOT / "src" / "app_config.py", r'APP_VERSION = "[^"]*"',
     'APP_VERSION = "%s"'),
]


def _patch(path: pathlib.Path, pattern: str, template: str, ver: str) -> bool:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")

    new_text, count = re.subn(pattern, template % ver, text)
    if count != 1:
        raise SystemExit("%s 里匹配到 %d 处（预期 1 处），未修改" % (path.name, count))
    if new_text == text:
        print("%s 已是 %s" % (path.name, ver))
        return False

    path.write_bytes((b"\xef\xbb\xbf" if has_bom else b"") + new_text.encode("utf-8"))
    print("%s -> %s（BOM: %s）" % (path.name, ver, "保留" if has_bom else "无"))
    return True


def main(argv):
    if len(argv) != 2:
        print("用法: python tools/ci_set_version.py <版本号，如 1.2.0>")
        return 2

    ver = argv[1].strip().lstrip("vV")
    if not re.fullmatch(r"\d+\.\d+(\.\d+)?", ver):
        print("版本号必须是 x.y.z 形式，收到: %r" % argv[1])
        return 2

    changed = False
    for path, pattern, template in TARGETS:
        if not path.exists():
            raise SystemExit("找不到 %s" % path)
        changed = _patch(path, pattern, template, ver) or changed

    print("版本号同步完成：%s%s" % (ver, "" if changed else "（无改动）"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
