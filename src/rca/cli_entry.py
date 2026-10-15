"""CLI 冻结入口（PyInstaller `Analysis([...])` 的脚本）。

**为什么单独一个模块**：PyInstaller 把 spec 里的脚本当**顶层 `__main__`** 执行，
脚本内的**相对导入**会直接
`ImportError: attempted relative import with no known parent package`
（M5 首次实构建实测踩到：`from . import __version__` 让 `rca-cli.exe` 一启动就崩）。
故冻结入口一律用**绝对导入**，且只做 argv 转发——判定逻辑仍在 `rca.cli`，不复制。
"""

from __future__ import annotations

import sys
from typing import List, Optional

__all__ = ["main"]


def main(argv: Optional[List[str]] = None) -> int:
    from rca.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
