"""GUI 冻结入口（PyInstaller `Analysis([...])` 的脚本）。

**为什么单独一个模块**：PyInstaller 把 spec 里的脚本当**顶层 `__main__`** 执行，
脚本（及其函数体）内的**相对导入**会直接
`ImportError: attempted relative import with no known parent package`。
`rca/gui/app.py` 里是 `from ..engine.pipeline import ...`，直接当脚本打必然崩
（M5 首次实构建实测踩到）。故冻结入口用**绝对导入**，本身不含任何界面装配。

**窗口版 stdout 不接终端** → `--selftest <文件>` 是脚本化验收窗口 exe 的**唯一**通路
（plan/05 §6）。此处把该请求**路由到 CLI 的同一份 `selftest` 实现**，
避免验收逻辑出现第二处实现（双入口结论同源）。
"""

from __future__ import annotations

import sys
from typing import List, Optional

__all__ = ["main"]

EXIT_USAGE = 2

_USAGE = (
    "用法：rca-gui [--data <data目录>]\n"
    "      rca-gui --selftest <输出文件> [--data <data目录>]   # 脚本化验收通路\n"
    "      rca-gui --version"
)

# 只接受这些开关。**认可项之外的参数一律拒绝（exit 2）**——窗口版没有终端，
# 静默忽略参数会让"rca-gui check --input x.txt"看起来在跑、实则挂在事件循环里
# 永不返回（M5 验收实测踩到：冻结态验收超时 180s）。
_KNOWN_FLAGS = ("--selftest", "--data", "--version", "--help", "-h")


def _opt_value(argv: List[str], flag: str) -> Optional[str]:
    """取 `--flag <值>` 的值；缺值返回 None（由调用方按缺参处理）。"""
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def unknown_args(argv: List[str]) -> List[str]:
    """挑出无法识别的参数（含缺值的 `--data` 之后那个词不算，见下）。

    判定规则：跳过已知开关；`--data <值>` 的**值**是被消费掉的，不算未知。
    """
    out: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in _KNOWN_FLAGS:
            if a == "--data":
                i += 2  # 连同它的值一起跳过
                continue
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def selftest_argv(argv: List[str]) -> Optional[List[str]]:
    """把 GUI 侧 argv 规范化成 CLI `selftest` 的 argv；非自检请求返回 None。

    复用 `rca.cli.normalize_argv`（**单一实现源**）——窗口 exe 与 CLI exe
    的验收结论必须出自同一份解析，否则"双入口结论同源"只是句口号。
    """
    if "--selftest" not in argv:
        return None
    from rca.cli import normalize_argv

    tail = argv[argv.index("--selftest"):]
    if "--data" not in tail:
        data = _opt_value(argv, "--data")
        if data:
            tail = tail + ["--data", data]
    return normalize_argv(tail)


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    selftest = selftest_argv(args)
    if selftest is not None:
        from rca.cli import main as cli_main

        return cli_main(selftest)

    if "--version" in args:
        from rca import __version__

        print("rca-gui %s" % __version__)
        return 0

    if "--help" in args or "-h" in args:
        print(_USAGE)
        return 0

    bad = unknown_args(args)
    if bad:
        # 窗口版无终端：静默忽略会挂进事件循环、永不返回（验收器超时）。
        print("错误：无法识别的参数 %s\n\n%s" % (" ".join(bad), _USAGE), file=sys.stderr)
        return EXIT_USAGE

    from rca.gui.app import run_gui

    return run_gui(data_dir=_opt_value(args, "--data"))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
