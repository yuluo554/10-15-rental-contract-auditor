"""官方来源快照抓取与冻结校验。

纪律（plan/02 §2）：
- 抓取脚本**不重写正文**，只做标签剥离与空白归一。
- 产物入仓后禁手改；`--check` 重抓并逐字节比对。
- 快照是被台账登记 sha256 的字节冻结件（`.gitattributes` 标 `-text`）。

用法：
    py -3.12 -X utf8 tools/fetch_sources.py            # 抓取并写入 data/knowledge/raw/
    py -3.12 -X utf8 tools/fetch_sources.py --check     # 重抓比对，输出 SOURCES_FROZEN_OK
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "knowledge" / "raw"
MANIFEST = ROOT / "data" / "knowledge" / "MANIFEST.json"

SOURCES = [
    {
        "source_id": "SRC-CN-CIVIL-CODE",
        "title": "《中华人民共和国民法典》",
        "doc_no": "主席令第四十五号",
        "effective_date": "2021-01-01",
        "url": "https://www.court.gov.cn/zixun/xiangqing/233181.html",
        "snapshot": "cn-civil-code.txt",
    },
    {
        "source_id": "SRC-BJ-HOUSING-RENTAL",
        "title": "《北京市住房租赁条例》",
        "doc_no": "北京市人民代表大会常务委员会公告〔十五届〕第 74 号",
        "effective_date": "2022-09-01",
        "url": "http://www.bjrd.gov.cn/rdzl/dfxfgk/dfxfg/202205/t20220527_2722977.html",
        "snapshot": "bj-housing-rental.txt",
    },
    {
        "source_id": "SRC-SH-HOUSING-RENTAL",
        "title": "《上海市住房租赁条例》",
        "doc_no": "上海市人民代表大会常务委员会公告〔十五届〕第 133 号",
        "effective_date": "2023-02-01",
        "url": "https://www.shanghai.gov.cn/bzxzlzfjbzc/20230418/8a0798aa5f444182a33065910f5b272c.html",
        "snapshot": "sh-housing-rental.txt",
    },
    {
        "source_id": "SRC-BJ-DEPOSIT-ESCROW",
        "title": "《北京市住房租赁押金托管和租金监管暂行办法》",
        "doc_no": "京建法〔2024〕8 号",
        "effective_date": "2024-10-01",
        "url": "https://zjw.beijing.gov.cn/bjjs/xxgk/zcwj2024/gfxwj40/xxyx/543372836/index.shtml",
        "snapshot": "bj-deposit-escrow.txt",
    },
]

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_WS = re.compile(r"[ \t\u3000]+")
_BLANK = re.compile(r"\n\s*\n+")


def _decode(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8/replace"


def strip_html(raw: bytes) -> tuple[str, str]:
    """剥离标签与空白归一。**不重写正文**（不改字、不补句）。"""
    text, enc = _decode(raw)
    text = _SCRIPT.sub("\n", text)
    text = _TAG.sub("\n", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS.sub(" ", text)
    text = _BLANK.sub("\n", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln), enc


def fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise OSError("HTTP %s for %s" % (resp.status, url))
        return resp.read()


def han_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def build_manifest() -> dict:
    entries = []
    for src in SOURCES:
        path = RAW_DIR / src["snapshot"]
        data = path.read_bytes()
        text = data.decode("utf-8")
        entries.append(
            {
                **{k: v for k, v in src.items() if k != "snapshot"},
                "snapshot": "data/knowledge/raw/%s" % src["snapshot"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "han_chars": han_count(text),
                "fetched_date": date.today().isoformat(),
            }
        )
    return {
        "note": "官方来源快照台账。快照为字节冻结件（.gitattributes 标 -text），禁手改。",
        "sources": entries,
    }


def cmd_fetch() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for src in SOURCES:
        raw = fetch(src["url"])
        text, enc = strip_html(raw)
        if han_count(text) < 500:
            print("抓取内容汉字数异常(%d)，疑非全文: %s" % (han_count(text), src["url"]))
            return 1
        out = RAW_DIR / src["snapshot"]
        out.write_bytes(text.encode("utf-8"))
        print(
            "已写入 %s  bytes=%d 汉字=%d 源编码=%s"
            % (src["snapshot"], out.stat().st_size, han_count(text), enc)
        )
    manifest = build_manifest()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    print("已写入台账 %s" % MANIFEST.relative_to(ROOT).as_posix())
    return 0


def cmd_check() -> int:
    if not MANIFEST.is_file():
        print("台账缺失: %s" % MANIFEST)
        return 1
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_snap = {s["snapshot"]: s for s in recorded["sources"]}
    problems = []
    for src in SOURCES:
        rel = "data/knowledge/raw/%s" % src["snapshot"]
        path = RAW_DIR / src["snapshot"]
        if not path.is_file():
            problems.append("快照缺失: %s" % rel)
            continue
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        want = by_snap.get(rel, {}).get("sha256")
        if want != actual:
            problems.append("sha256 失配: %s (台账 %s != 实际 %s)" % (rel, want, actual))
        if b"\r" in data:
            problems.append("快照含 CR（应为 LF）: %s" % rel)
    if problems:
        for p in problems:
            print("FAIL " + p)
        return 1
    print("SOURCES_FROZEN_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="官方来源快照抓取与冻结校验")
    ap.add_argument("--check", action="store_true", help="重抓比对（校验冻结态）")
    args = ap.parse_args(argv)
    return cmd_check() if args.check else cmd_fetch()


if __name__ == "__main__":
    raise SystemExit(main())
