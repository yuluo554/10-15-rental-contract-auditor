"""要素抽取：条款序列 → 合同卡片（模块③的输入）。

防幻觉纪律：每个字段的 evidence.clause_text 必须是合同原文的**子串**
（`assert evidence.clause_text in raw_text`），不是子串即丢弃该字段。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional, Tuple

from ..model import Clause, Evidence, Field, LeaseCard

__all__ = ["build_card", "to_decimal", "q2"]

_CITY_HINTS = [
    ("北京", ("北京", "京", "北京市")),
    ("上海", ("上海", "沪", "上海市")),
]

_ENTERPRISE_HINTS = ("住房租赁企业", "租赁企业", "房地产经纪", "中介", "托管公司", "公寓管理")
# 公司后缀：合同甲方常见"XX有限公司"形态，不写"住房租赁企业"字样也应识别为企业主体
_COMPANY_SUFFIX = ("有限公司", "有限责任公司", "股份有限公司", "合伙企业", "分公司")
_INDIVIDUAL_HINTS = ("个人出租", "房东", "自然人")

_CN_NUM = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
    "七": 7, "八": 8, "九": 9, "十": 10,
}


def q2(value: Decimal) -> Decimal:
    """量化到两位小数（精度约定，非政策数值——可豁免零字面量门禁）。"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_decimal(text: str) -> Optional[Decimal]:
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _cn_to_int(text: str) -> Optional[int]:
    if text in _CN_NUM:
        return _CN_NUM[text]
    if text.startswith("十") and len(text) == 2 and text[1] in _CN_NUM:
        return 10 + _CN_NUM[text[1]]
    if len(text) == 2 and text[0] in _CN_NUM and text[1] == "十":
        return _CN_NUM[text[0]] * 10
    if len(text) == 3 and text[0] in _CN_NUM and text[1] == "十" and text[2] in _CN_NUM:
        return _CN_NUM[text[0]] * 10 + _CN_NUM[text[2]]
    return None


def _num_pattern() -> str:
    """数字形态：阿拉伯或中文数字（含"两"，合同口语里"两年/两个月"常见）。"""
    return r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十]+)"


def _parse_num(text: str) -> Optional[Decimal]:
    text = text.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return to_decimal(text)
    val = _cn_to_int(text)
    return Decimal(val) if val is not None else None


# 中文租期表述：合同常写"半年""一年半"而不是"6 个月""18 个月"。
# 不抽到会让保租房租期下限规则判 unknown 而非 noncompliant（**漏报**）。
# 形态拆开匹配："X年半" → X+0.5 年；裸"半年" → 0.5 年（无前导数字）。
_TERM_HALF_YEARS = re.compile(
    r"(?:租赁期限|租期)(?:为|：|:)?\s*(?P<v>[一二两三四五六七八九十\d]+)\s*年半"
)
_TERM_HALF_ONLY = re.compile(r"(?:租赁期限|租期)(?:为|：|:)?\s*半年")


def _cn_half_years(text: str) -> Optional[Tuple[Decimal, str]]:
    """"X年半" / "半年" → (年数, 命中原文)。未命中返回 None。"""
    m = _TERM_HALF_YEARS.search(text)
    if m:
        base = _parse_num(m.group("v"))
        if base is not None:
            return base + Decimal("0.5"), m.group(0)
    m = _TERM_HALF_ONLY.search(text)
    if m:
        return Decimal("0.5"), m.group(0)
    return None


def _find(text: str, patterns: List[str]) -> Optional[Tuple[Decimal, str]]:
    """按模式顺序找第一个命中，返回 (值, 命中原文片段)。"""
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        raw = m.group("v") if "v" in m.groupdict() else m.group(1)
        val = _parse_num(raw)
        if val is not None:
            return val, m.group(0)
    return None


def _evidence(
    raw_text: str, clauses: List[Clause], fragment: str, number: Optional[str] = None
) -> Evidence:
    """构造证据：clause_text 必须是原文子串（硬断言，否则降级为 None）。"""
    if fragment not in raw_text:
        return Evidence(clause_number=number, clause_text=None, char_span=None)
    start = raw_text.find(fragment)
    if number is None:
        for c in clauses:
            if c.span[0] <= start < c.span[1]:
                number = c.number
                break
    return Evidence(clause_number=number, clause_text=fragment, char_span=(start, start + len(fragment)))


def _detect_city(text: str) -> Optional[str]:
    head = text[:400]
    for city, hints in _CITY_HINTS:
        for h in hints:
            if h in head:
                return city
    for city, hints in _CITY_HINTS:
        for h in hints:
            if h in text:
                return city
    return None


def _detect_party(text: str) -> str:
    head = text[:1500]
    for h in _ENTERPRISE_HINTS:
        if h in head:
            return "enterprise"
    for suf in _COMPANY_SUFFIX:
        if suf in head:
            return "enterprise"
    for h in _INDIVIDUAL_HINTS:
        if h in head:
            return "individual"
    return "unknown"


def _detect_lease_kind(text: str) -> str:
    if "保障性租赁住房" in text or "保租房" in text:
        return "affordable"
    return "ordinary"


def build_card(raw_text: str, clauses: List[Clause], pending: List[str]) -> LeaseCard:
    """从归一化文本 + 条款序列构造合同卡片。"""
    text = raw_text
    num = _num_pattern()
    fields = {}

    # 租赁期限（年 / 月）
    # "X年半"/"半年"必须先于通用"X 年"匹配：否则"一年半"会被通用式吃成"一 年"、
    # 丢掉"半"→ 1.00 年（**静默取错值**，比抽不到更危险）。
    half = _cn_half_years(text)
    got = None if half else _find(
        text,
        [
            r"租赁期限(?:为|：|:)?\s*(?P<v>%s)\s*年" % num,
            r"租期(?:为|：|:)?\s*(?P<v>%s)\s*年" % num,
            r"租赁期限(?:为|：|:)?\s*(?P<v>%s)\s*个月" % num,
            r"租赁期限(?:为|：|:)?\s*(?P<v>%s)\s*月" % num,
        ],
    )
    if half:
        val, frag = half
        fields["lease_term_years"] = Field(
            "lease_term_years", q2(val), "年（中文表述）", "high", _evidence(text, clauses, frag)
        )
    elif got:
        val, frag = got
        if "月" in frag and "年" not in frag:
            val = q2(val / Decimal(12))
            unit = "年（由月换算）"
        else:
            unit = "年"
        fields["lease_term_years"] = Field(
            "lease_term_years", q2(val), unit, "high", _evidence(text, clauses, frag)
        )
    else:
        fields["lease_term_years"] = Field("lease_term_years")

    # 押金（月租金 / 元）
    got = _find(
        text,
        [
            r"押金(?:为|：|:)?\s*(?P<v>%s)\s*个月(?:的)?租金" % num,
            r"押金(?:为|：|:)?\s*(?P<v>%s)\s*个月" % num,
        ],
    )
    if got:
        val, frag = got
        fields["deposit_months"] = Field(
            "deposit_months", q2(val), "月租金", "high", _evidence(text, clauses, frag)
        )
    else:
        fields["deposit_months"] = Field("deposit_months")

    # 单次收取租金（月租金）
    got = _find(
        text,
        [
            r"(?:单次|一次性)(?:收取|支付)(?:租金)?(?:数额)?(?:为|：|:)?\s*(?P<v>%s)\s*个月" % num,
            r"(?:押[一二三四五六七八九十\d]付[一二三四五六七八九十\d])",
            r"(?:一次|单次)(?:性)?(?:收取|支付)\s*(?P<v>%s)\s*个月(?:的)?租金" % num,
        ],
    )
    if got:
        val, frag = got
        if "押" in frag and "付" in frag:
            m = re.search(r"付([一二三四五六七八九十\d])", frag)
            val = _parse_num(m.group(1)) if m else None
        if val is not None:
            fields["rent_prepay_months"] = Field(
                "rent_prepay_months", q2(val), "月租金", "high", _evidence(text, clauses, frag)
            )
    if "rent_prepay_months" not in fields:
        fields["rent_prepay_months"] = Field("rent_prepay_months")

    # 备案期限（日）
    got = _find(
        text,
        [
            r"订立(?:之日)?起\s*(?P<v>%s)\s*(?:个)?日内(?:办理|进行|完成)?(?:登记)?备案" % num,
            r"(?P<v>%s)\s*(?:个)?日内(?:办理|完成)(?:住房租赁)?登记备案" % num,
        ],
    )
    if got:
        val, frag = got
        fields["filing_days"] = Field(
            "filing_days", q2(val), "日", "high", _evidence(text, clauses, frag)
        )
    else:
        fields["filing_days"] = Field("filing_days")

    # 出租登记（工作日）
    got = _find(
        text,
        [r"订立(?:之日)?起\s*(?P<v>%s)\s*个工作日内" % num],
    )
    if got:
        val, frag = got
        fields["lodging_reg_workdays"] = Field(
            "lodging_reg_workdays", q2(val), "工作日", "high", _evidence(text, clauses, frag)
        )
    else:
        fields["lodging_reg_workdays"] = Field("lodging_reg_workdays")

    # 押金退还（工作日）
    got = _find(
        text,
        [
            r"返还住房后\s*(?P<v>%s)\s*个工作日内(?:向承租人)?退还" % num,
            r"(?P<v>%s)\s*个工作日内(?:向承租人)?退还(?:剩余)?押金" % num,
        ],
    )
    if got:
        val, frag = got
        fields["deposit_refund_workdays"] = Field(
            "deposit_refund_workdays", q2(val), "工作日", "high", _evidence(text, clauses, frag)
        )
    else:
        fields["deposit_refund_workdays"] = Field("deposit_refund_workdays")

    # 企业备案（日）
    got = _find(
        text,
        [r"营业执照之日起\s*(?P<v>%s)\s*(?:个)?日内" % num],
    )
    if got:
        val, frag = got
        fields["enterprise_filing_days"] = Field(
            "enterprise_filing_days", q2(val), "日", "high", _evidence(text, clauses, frag)
        )
    else:
        fields["enterprise_filing_days"] = Field("enterprise_filing_days")

    # 押金条款是否载明（定性）
    dep_clause = "押金" in text
    fields["has_deposit_clause"] = Field(
        "has_deposit_clause",
        True if dep_clause else False,
        None,
        "high" if dep_clause else "low",
        _evidence(text, clauses, "押金") if dep_clause else None,
    )

    # 租金支付期限是否约定（定性）
    pay_declared = bool(re.search(r"(租金)?(?:按|每)(?:月|季|季度|年)(?:支付|支付一次|预付)", text))
    pay_frag = None
    if pay_declared:
        m = re.search(r"[^。\n]*?(?:租金)?(?:按|每)(?:月|季|季度|年)(?:支付|支付一次|预付)[^。\n]*", text)
        if m and m.group(0) in text:
            pay_frag = m.group(0)
    fields["rent_pay_period_declared"] = Field(
        "rent_pay_period_declared",
        True if pay_declared else False,
        None,
        "high" if pay_declared else "low",
        _evidence(text, clauses, pay_frag) if pay_frag else None,
    )

    # 法定要素完整性（民法典 704 条）——由 checker 用规则包的 elements 列表逐项判定
    fields["contract_text"] = Field("contract_text", text, None, "high", None)

    return LeaseCard(
        city=_detect_city(text),
        party=_detect_party(text),
        lease_kind=_detect_lease_kind(text),
        fields=fields,
        clauses=clauses,
        pending_manual=list(pending),
    )
