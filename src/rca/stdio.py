"""标准输出/错误流的 UTF-8 收口。

为什么需要它：Windows 控制台与 CI 管道默认用代码页编码（cp936 / cp1252），
非 ASCII 输出会抛 UnicodeEncodeError。本机习惯用 `py -X utf8` 掩盖了这一点，
但 CI 里 `python -m pytest` 不是我们敲的命令，没有 `-X utf8`。

做法：按 `stream.encoding` 探针决定是否 reconfigure——已经是 utf-8 就不动
（中文控制台 cp936 保持原样，避免把用户终端搞坏）。
"""

from __future__ import annotations

import sys

__all__ = ["ensure_utf8_stdio"]

_TARGET = "utf-8"


def _reconfigure(stream) -> None:
    encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
    if encoding == "utf8":
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding=_TARGET, errors="replace")
    except (ValueError, OSError, AttributeError):
        # 流已被重定向/关闭时无法 reconfigure——不是致命错误，保持原状
        pass


def ensure_utf8_stdio() -> None:
    """在可执行入口最早期调用一次。"""
    _reconfigure(sys.stdout)
    _reconfigure(sys.stderr)
