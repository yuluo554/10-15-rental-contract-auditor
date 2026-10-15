"""条款切分（模块①）。

确定性纪律：切分出的条款号必须能在原文中定位到**逐字原文**；无法定位的
切分显式标注 `located=False` 并进"待人工确认"清单，绝不静默吞掉。

**条号只认"定义位"**（K9 在解析层的对应物）：行首，或同一行内紧跟在句末标点
之后。正文里的交叉引用（"乙方应遵守第五条关于维修的约定"）同样是 `第X条`
形态，若一并当边界，会把上一条从中间劈开、并凭空造出一个不存在的条款——
报告随后把判定依据指向不存在的条号。这与 M1 修掉的 `derive_clause()` 条号
劫持是同一类缺陷（把"引用"当"定义"），只是发生在解析层。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..model import Clause

__all__ = ["split_clauses", "normalize_newlines", "collapse_spaced_chars"]

# 中文数字：含"百/零/〇"，条文号会出现"第一百二十条"这类形态
_CN_DIGITS = "一二三四五六七八九十百零〇"
_NUM_CLASS = r"[%s\d]" % _CN_DIGITS

# 条款号形态按优先级枚举
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # 第X条 / 第X条之一：修订条文的后缀必须并进**同一个**条号，
    # 否则"第一条之一"会先被匹配成"第一条"，与真正的第一条重复（实测踩过）。
    ("article", re.compile(r"第%s+条(?:之[一二三四五六七八九十]+)?" % _NUM_CLASS)),
    ("cn_index", re.compile(r"^[一二三四五六七八九十]+[、．.]", re.M)),
    ("paren_index", re.compile(r"^[（(][一二三四五六七八九十]+[）)]", re.M)),
    ("num_index", re.compile(r"^\d+[、.．]", re.M)),
]

# 同位置命中多种形态时的优先级
_PRIORITY = {"article": 0, "cn_index": 1, "paren_index": 2, "num_index": 3}

# 句末标点：单行合同里"…押金。第五条 …"的条号仍算定义位
_TERMINALS = "。；;！？：:"

# 引用**后随**形态：条号紧跟这些字样 = 引用（"第五条规定的除外"），不是条款起始
_CITATION_CONT = re.compile(r"(?:规定的除外|约定的除外|另有规定|另有约定|所列|所述|所指)")

# 引用**前导**形态：条号紧跟在这些词之后 = 疑似引用被误当边界。
# 只收"不能单独收尾成句"的动词/介词：`本合同`/`本条例`/`本办法` 这类名词短语
# 可以合法地结束一个正常句子（"…根据本合同" 换行 "第二条 …"），收进来会把**真条款**
# 误判成引用并吞掉；它们只出现在行内引用里，而那种形态已被定义位判定挡下。
_CITATION_LEAD = re.compile(
    r"(?:遵守|依照|依据|根据|按照|参照|符合|违反|适用|参见)\s*$"
)

# 前导检查的回看窗口：够容纳"乙方应遵守"+ 换行
_LEAD_WINDOW = 16

# 后随检查的窗口
_CONT_WINDOW = 8

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


def _is_definition_position(text: str, start: int) -> bool:
    """该位置的条号是否处于"定义位"（行首，或同句内紧跟句末标点）。

    正文交叉引用不在定义位——它前面是"遵守/依照"这类词，或句中任意实词。
    """
    line_start = text.rfind("\n", 0, start) + 1
    if not text[line_start:start].strip():
        return True
    i = start - 1
    while i >= 0 and text[i] in " \t\u3000":
        i -= 1
    return i >= 0 and text[i] in _TERMINALS


def _is_citation_continuation(text: str, start: int, number: str) -> bool:
    """条号后紧跟"规定的除外/所列/所述"等字样 → 引用，不是条款起始。"""
    tail = text[start + len(number): start + len(number) + _CONT_WINDOW].lstrip()
    return bool(_CITATION_CONT.match(tail))


def _has_citation_lead(text: str, start: int) -> bool:
    """条号紧跟在引用触发词之后 → 疑似"引用被误当边界"。

    覆盖 PDF 复制常见的**断行形态**（"乙方应遵守" 换行 "第五条…"）：
    这种形态条号确实落在行首，定义位判定放行，须靠本守门拦下——
    否则它会静默地劈开上一条正文（`located=True`，看着成功、实则错位）。
    """
    lookback = text[max(0, start - _LEAD_WINDOW):start].rstrip()
    return bool(_CITATION_LEAD.search(lookback))


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

    # 同一位置只保留优先级最高的一种（article > cn_index > paren_index > num_index）
    deduped: List[Tuple[int, str, str]] = []
    for h in hits:
        if deduped and h[0] == deduped[-1][0]:
            if _PRIORITY[h[2]] < _PRIORITY[deduped[-1][2]]:
                deduped[-1] = h
            continue
        deduped.append(h)

    # 第一道门：只留定义位。被挡下的多半是正文交叉引用——那是**正确**的引用用法，
    # 不是待人工确认项，故静默跳过（不写进清单，否则每份合同都刷一屏噪音）。
    pending: List[str] = []
    accepted: List[Tuple[int, str, str]] = []
    seen: set = set()
    for start, number, kind in deduped:
        if not _is_definition_position(text, start):
            continue
        if _is_citation_continuation(text, start, number):
            continue
        # 第二道门：定义位放行、但前导是引用触发词 → 误当边界。
        # 这一条**不能静默**：它正是"边界错但 located=True"的形态。
        if kind == "article" and _has_citation_lead(text, start):
            pending.append("疑似交叉引用被当作条款边界，已跳过：%s" % number)
            continue
        if number in seen:
            pending.append("重复条号，已跳过（回定位会互相错配）：%s" % number)
            continue
        seen.add(number)
        accepted.append((start, number, kind))

    clauses: List[Clause] = []
    cursor = 0
    for i, (start, number, kind) in enumerate(accepted):
        # 条款正文止于**下一个被接受的**边界，而不是下一个原始命中位置——
        # 否则被挡下的引用会从中间切断正文。
        end = accepted[i + 1][0] if i + 1 < len(accepted) else len(text)
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
