"""Release 附件确定性打包 + 附件台账。

纪律（plan/05 §9）：
- `ZIP_STORED` + 条目**显式 sort**（os.walk 顺序跨调用不稳定）+ 全条目固定 `date_time`
  → **两次独立打包逐字节一致**。
- 留档写清"可复跑的是哪一步"：**同 dist → 同 zip 字节**成立；
  **exe 构建本身不承诺跨机字节一致**。
- 附件名一律 **ASCII**（gh CLI 在 Git Bash 下会剥中文附件名）。
- 台账 JSON 由工具输出，避免手抄漂移。

用法：
    py -3.12 -X utf8 tools/build_release.py --dist dist/rca-cli --out _backups/release --name rca-cli-win64.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def build_zip(dist: Path, out_zip: Path, arc_root: str) -> Path:
    """确定性打包：条目排序 + 固定时间戳 + ZIP_STORED。"""
    entries = []
    for p in sorted(dist.rglob("*")):
        if p.is_file():
            entries.append(p)
    # 显式按相对路径排序（os.walk/rglob 顺序跨调用不稳定）
    entries.sort(key=lambda p: p.relative_to(dist).as_posix())

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_STORED) as zf:
        for p in entries:
            rel = "%s/%s" % (arc_root, p.relative_to(dist).as_posix())
            info = zipfile.ZipInfo(rel, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            zf.writestr(info, p.read_bytes())
    return out_zip


def ledger_entry(zip_path: Path) -> dict:
    data = zip_path.read_bytes()
    return {
        "asset_name": zip_path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "entries": len(zipfile.ZipFile(zip_path).namelist()),
    }


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="Release 附件确定性打包")
    ap.add_argument("--dist", required=True, help="dist 目录（如 dist/rca-cli）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--name", required=True, help="附件名（**必须 ASCII**）")
    ap.add_argument("--arc-root", default=None, help="压缩包内根目录名（默认取附件名去后缀）")
    ap.add_argument("--check", action="store_true", help="重打包并比对（验证确定性）")
    args = ap.parse_args(argv)

    if not args.name.isascii():
        print("FAIL 附件名必须为 ASCII（gh CLI 会剥中文名）: %s" % args.name)
        return 2

    dist = Path(args.dist)
    if not dist.is_dir():
        print("FAIL dist 目录不存在: %s" % dist)
        return 2

    out_dir = Path(args.out)
    arc_root = args.arc_root or Path(args.name).stem
    zip_path = out_dir / args.name

    if args.check:
        tmp = out_dir / ("%s.recheck" % args.name)
        build_zip(dist, tmp, arc_root)
        same = tmp.read_bytes() == zip_path.read_bytes()
        tmp.unlink()
        if not same:
            print("FAIL 两次打包字节不一致（确定性被破坏）")
            return 1
        print("RELEASE_ZIP_DETERMINISTIC_OK")
        return 0

    build_zip(dist, zip_path, arc_root)
    entry = ledger_entry(zip_path)
    ledger = out_dir / "release-ledger.json"
    ledger.write_bytes(
        (json.dumps({"assets": [entry]}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    print("已打包 %s" % zip_path)
    print("  bytes=%d sha256=%s entries=%d" % (entry["bytes"], entry["sha256"], entry["entries"]))
    print("台账已写入 %s" % ledger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
