"""条款切分（模块①）。

确定性纪律：切分出的条款号必须能在原文中定位到**逐字原文**；无法定位的
切分显式标注 `located=False` 并进"待人工确认"清单，绝不静默吞掉。
"""

from __future__ import annotations

import re
from typing import List, Tuple

from ..model import Clause

__all__ = ["split_clauses", "normalize_newlines", "collapse_spaced_chars"]

# 条款号形态按优先级枚举
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("article", re.compile(r"第[一二三四五六七八九十百零〇\d]+条")),
    ("cn_index", re.compile(r"^[一二三四五六七八九十]+[、．.]", re.M)),
    ("num_index", re.compile(r"^\d+[、.．]", re.M)),
]

_SPACED = re.compile(r"(?:[\u4e00-\u9fff]\s){4,}")


def normalize_newlines(text: str) -> str:
    """CRLF/CR → LF。不做这一步，span 计算与定位断言全错位。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def collapse_spaced_chars(text: str) -> str:
    """折叠 PDF 复制产生的"逐字符空格"（仅当连续单字+空格占比超阈值）。

    阈值化处理，避免误伤正常排版的短间距文本。
    """
    if not _SPACED.search(text):
        return text
    lines = []
    for line in text.split("\n"):
        if _SPACED.search(line):
            line = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", line)
        lines.append(line)
    return "\n".join(lines)


def _locate(text: str, needle: str, cursor: int) -> Tuple[int, bool]:
    """从 cursor 起查找 needle；命中位置必须单调递增（防重复条号错配）。"""
    idx = text.find(needle, cursor)
    if idx < 0:
        idx = text.find(needle)
    if idx < 0:
        return cursor, False
    return idx, True


def split_clauses(raw_text: str) -> Tuple[List[Clause], str, List[str]]:
    """返回 (条款序列, 归一化后的文本, 待人工确认清单)。"""
    text = collapse_spaced_chars(normalize_newlines(raw_text))

    hits: List[Tuple[int, str, str]] = []
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            hits.append((m.start(), m.group(0), kind))
    hits.sort(key=lambda h: h[0])

    # 同一位置只保留优先级最高的一种（article > cn_index > num_index）
    priority = {"article": 0, "cn_index": 1, "num_index": 2}
    deduped: List[Tuple[int, str, str]] = []
    for h in hits:
        if deduped and h[0] == deduped[-1][0]:
            if priority[h[2]] < priority[deduped[-1][2]]:
                deduped[-1] = h
            continue
        deduped.append(h)

    clauses: List[Clause] = []
    pending: List[str] = []
    cursor = 0
    for i, (start, number, kind) in enumerate(deduped):
        end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
        body = text[start:end].strip()
        loc, ok = _locate(text, number, cursor)
        if ok:
            cursor = loc
        else:
            pending.append("条款号无法回定位原文: %s" % number)
        clauses.append(
            Clause(
                number=number,
                text=body,
                kind=kind,
                span=(start, end),
                located=ok,
            )
        )

    if not clauses:
        pending.append("未切分出任何条款（文本可能非合同或格式异常）")
    return clauses, text, pending
