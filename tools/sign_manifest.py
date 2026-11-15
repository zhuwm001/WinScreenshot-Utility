# -*- coding: utf-8 -*-
"""CI 用：给安装包生成签名清单 latest.json。

用法：
    set UPDATE_SIGNING_KEY=<base64 seed>       # 本机测试才用环境变量
    python tools/sign_manifest.py --exe installer/WoAiJieTu-Setup-v1.1.1.exe \
        --version 1.1.1 --notes dist/release_body.md --out dist/latest.json

私钥只从环境变量 UPDATE_SIGNING_KEY 读（GitHub Actions Secret），
不落盘、不进命令行参数（避免出现在进程列表 / 日志里）。
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import manifest  # noqa: E402


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 256), b""):
            h.update(block)
    return h.hexdigest()


def read_notes(path: str, limit: int = 6000) -> str:
    if not path or not os.path.exists(path):
        return ""
    raw = io.open(path, encoding="utf-8-sig", errors="replace").read()
    raw = raw.replace("\r\n", "\n").strip()
    if len(raw) > limit:
        raw = raw[:limit].rstrip() + "\n…"
    return raw


def build_payload(exe: str, version: str, repo: str, tag: str, notes: str = "") -> dict:
    name = os.path.basename(exe)
    url = "https://github.com/%s/releases/download/%s/%s" % (repo, tag, name)
    return {
        "schema": manifest.SCHEMA,
        "repo": repo,
        "version": version,
        "tag": tag,
        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "notes": notes,
        "asset": {
            "name": name,
            "size": os.path.getsize(exe),
            "sha256": sha256_file(exe),
            "url": url,
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True, help="安装包路径")
    ap.add_argument("--version", required=True, help="版本号，如 1.1.1")
    ap.add_argument("--repo", default="zhuwm001/WinScreenshot-Utility")
    ap.add_argument("--tag", default="", help="默认 v<version>")
    ap.add_argument("--notes", default="", help="更新说明文件（markdown）")
    ap.add_argument("--out", default="dist/latest.json")
    ap.add_argument("--allow-empty-key", action="store_true",
                    help="仅本地演练：没有私钥时生成未签名清单（绝不用于发布）")
    args = ap.parse_args(argv)

    version = args.version.strip().lstrip("vV")
    tag = (args.tag or ("v" + version)).strip()
    notes = read_notes(args.notes)
    payload = build_payload(args.exe, version, args.repo, tag, notes)

    key = os.environ.get("UPDATE_SIGNING_KEY", "").strip()
    if not key:
        if not args.allow_empty_key:
            print("错误：环境变量 UPDATE_SIGNING_KEY 为空，无法签名。"
                  "（本地演练可加 --allow-empty-key）", file=sys.stderr)
            return 2
        doc = {"payload": payload, "signature": ""}
        print("警告：生成了未签名清单，只能本地测试！", file=sys.stderr)
    else:
        try:
            seed = base64.b64decode(key)
        except Exception:
            print("错误：UPDATE_SIGNING_KEY 不是合法的 base64", file=sys.stderr)
            return 2
        if len(seed) != 32:
            print("错误：UPDATE_SIGNING_KEY 解码后应为 32 字节，实际 %d" % len(seed),
                  file=sys.stderr)
            return 2
        doc = manifest.build(payload, seed)

        # 自检：签完立刻用内置公钥验一遍，防止私钥/公钥不配对导致全员更新失败
        ok, reason = manifest.verify_document(doc)
        if ok is None:
            print("错误：签名自检失败 —— %s" % reason, file=sys.stderr)
            print("      多半是 UPDATE_SIGNING_KEY 和 src/manifest.py 里的 PUBKEY_HEX 不匹配",
                  file=sys.stderr)
            return 3

    out = args.out
    d = os.path.dirname(os.path.abspath(out))
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("版本   : %s (%s)" % (version, tag))
    print("安装包 : %s  %.2f MB" % (payload["asset"]["name"],
                                 payload["asset"]["size"] / 1048576.0))
    print("sha256 : %s" % payload["asset"]["sha256"])
    print("签名   : %s" % ("已签名，自检通过" if key else "未签名"))
    print("输出   : %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
