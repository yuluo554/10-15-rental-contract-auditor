"""冻结态验收：中立目录 + 剥离 PATH 跑 CLI 通路。

纪律（plan/05 §6）：**别在仓库树内跑**——CWD 上溯会命中仓库 data，
"内嵌数据"验了个寂寞（假结果陷阱）。

用法：
    py -3.12 -X utf8 tools/verify_package.py --dist dist/rca-cli
    py -3.12 -X utf8 tools/verify_package.py --dist dist/rca-gui --gui-selftest
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 禁区成分：只匹配 dist **顶层**（依赖包自带的同名子目录不算泄露）
FORBIDDEN_TOP_LEVEL = ("plan", "tests", "_private", ".git", "src", "tools")


def _exe_names() -> dict:
    return {"cli": "rca-cli.exe", "gui": "rca-gui.exe"}


def _find_exe(dist: Path, kind: str) -> Path:
    name = _exe_names()[kind]
    cand = dist / name
    if cand.is_file():
        return cand
    # onedir 布局：exe 在 dist/<name>/<name>.exe
    for p in dist.rglob(name):
        return p
    raise FileNotFoundError("未找到 exe %s（dist=%s）" % (name, dist))


def check_top_level(dist: Path) -> list:
    problems = []
    for child in sorted(dist.iterdir()):
        if child.name in FORBIDDEN_TOP_LEVEL:
            problems.append("dist 顶层出现禁区成分: %s" % child.name)
    return problems


def _neutral_run(exe: Path, args: list) -> subprocess.CompletedProcess:
    """中立目录 + 剥离 PATH 下运行（防 CWD 上溯命中仓库 data）。"""
    with tempfile.TemporaryDirectory() as td:
        env = {"SystemRoot": os.environ.get("SystemRoot", ""), "TEMP": td, "TMP": td}
        return subprocess.run(
            [str(exe)] + args,
            cwd=td,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )


def verify(dist: Path, gui_selftest: bool) -> int:
    problems = check_top_level(dist)
    if problems:
        for p in problems:
            print("FAIL " + p)
        return 1

    try:
        exe = _find_exe(dist, "gui" if gui_selftest else "cli")
    except FileNotFoundError as exc:
        print("FAIL %s" % exc)
        return 1
    print("待验 exe: %s" % exe)

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "selftest.json"
        proc = _neutral_run(exe, ["--selftest", str(out)])
        print("selftest 退出码: %d" % proc.returncode)
        if proc.stdout.strip():
            print(proc.stdout.strip()[:800])
        if proc.returncode != 0:
            problems.append("冻结态自检非零退出")
        if not out.is_file():
            problems.append("自检未写出结论文件")
        else:
            payload = json.loads(out.read_text(encoding="utf-8"))
            if not payload.get("frozen"):
                problems.append("自检未报告 frozen=true（可能跑的不是冻结态）")
            if payload.get("data_dir_in_dist") is not True:
                problems.append(
                    "数据目录未落在 exe 目录内（内嵌数据失效，会回头读开发机仓库）"
                )
            if payload.get("bj_rule_count", 0) <= 0:
                problems.append("规则数为 0")

    if problems:
        print("\n验收未通过：")
        for p in problems:
            print("  - %s" % p)
        return 1
    print("PACKAGE_VERIFY_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="冻结态验收（中立目录 + 剥离 PATH）")
    ap.add_argument("--dist", required=True, help="dist 目录")
    ap.add_argument("--gui-selftest", action="store_true", help="验 GUI exe")
    args = ap.parse_args(argv)
    dist = Path(args.dist)
    if not dist.is_dir():
        print("FAIL dist 目录不存在: %s" % dist)
        return 1
    return verify(dist, args.gui_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
