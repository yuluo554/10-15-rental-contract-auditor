"""判定引擎（模块③）。

零政策字面量纪律：本模块**不含任何政策数值**——全部阈值来自规则包。
判定语义见 plan/03 §4：

- `skipped` 只给"原文明确写了适用情形"的项（applies_if 不满足）
- 无条件义务缺失 = `noncompliant`（绝不记 skipped）
- 一条规则都不适用 → 整体 `not_assessed`（绝不输出 compliant）
"""

from __future__ import annotations

import operator
from decimal import Decimal
from typing import Any, Dict, List

from ..model import (
    STATUS_COMPLIANT,
    STATUS_NONCOMPLIANT,
    STATUS_SKIPPED,
    STATUS_UNKNOWN,
    Finding,
    LeaseCard,
)
from .ruleset import Rule, Ruleset

__all__ = ["check_card"]

_OPS = {
    "<=": operator.le,
    "<": operator.lt,
    ">=": operator.ge,
    ">": operator.gt,
    "==": operator.eq,
}


def _as_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return value


def _applicability(rule: Rule, card: LeaseCard) -> str:
    """applies_if 三态判定：applies / not_applies / indeterminate。

    **关键区分**（防"把没做记成不用做"的反向陷阱）：
    - 已知主体不满足适用条件 → not_applies（原文明确写了适用情形限制）→ skipped
    - 主体未知，无法确定是否适用 → indeterminate → **unknown（不是 skipped）**

    若把 indeterminate 记成 skipped，等于替用户断言"这条不适用"——合规结论虚高。
    """
    cond = rule.applies_if or {}
    party = cond.get("party")
    if party and "any" not in party:
        if card.party == "unknown":
            return "indeterminate"
        if card.party not in party:
            return "not_applies"
    kinds = cond.get("lease_kind")
    if kinds and "any" not in kinds:
        if card.lease_kind not in kinds:
            return "not_applies"
    return "applies"


def _applies(rule: Rule, card: LeaseCard) -> bool:
    return _applicability(rule, card) == "applies"


def _reason_indeterminate(rule: Rule) -> str:
    cond = rule.applies_if or {}
    party = cond.get("party") or []
    return (
        "无法确定合同主体（合同未载明出租人为%s），本规则是否适用存疑，"
        "需人工确认主体性质后重新判定" % "/".join(party)
    )


def _reason_skipped(rule: Rule, card: LeaseCard) -> str:
    cond = rule.applies_if or {}
    bits = []
    if cond.get("party") and "any" not in cond["party"]:
        bits.append("适用主体限于 %s（本合同主体判定为 %s）" % ("/".join(cond["party"]), card.party))
    if cond.get("lease_kind") and "any" not in cond["lease_kind"]:
        bits.append(
            "适用房屋类型限于 %s（本合同为 %s）" % ("/".join(cond["lease_kind"]), card.lease_kind)
        )
    return "；".join(bits) or "适用条件不满足"


def _mk(rule: Rule, status: str, reason: str, **kw: Any) -> Finding:
    return Finding(
        rule_id=rule.rule_id,
        title=rule.title,
        status=status,
        check_type=rule.check_type,
        effect=rule.effect,
        severity=rule.severity,
        scope=rule.scope,
        reason=reason,
        param=rule.param,
        op=rule.op,
        unit=rule.unit,
        clause=rule.clause,
        quote=rule.quote,
        source_id=rule.source_id,
        **kw
    )


def _limit_words(op: str) -> tuple:
    """按运算符给出「合规/违规」两侧的方向措辞。

    上限类（<= / <）与下限类（>= / >）方向相反——把下限义务描述成"未超过规则上限"
    会让读者把"租期不得少于一年"误读成"租期不得超过一年"，是**方向性失真**
    （比措辞粗糙更严重：它把义务说反了）。
    """
    if op in (">=", ">"):
        return "不低于规则下限", "低于规则下限"
    return "未超过规则上限", "超过规则上限"


def _check_numeric(rule: Rule, card: LeaseCard) -> Finding:
    if rule.op is None or rule.value is None:
        # 无数值阈值的"提示/程序性"条目：不构成可判定的数值义务
        return _mk(rule, STATUS_UNKNOWN, "该条无明确数值阈值，无法作数值判定")
    field = card.get(rule.param) if rule.param else None
    if field is None or not field.observed:
        # 阈值照挂：规则**有**限值，只是合同侧没观测到——报告里把限值一并列出，
        # 否则读者看到 "<= —" 会误以为该条本身没有数值口径。
        return _mk(
            rule,
            STATUS_UNKNOWN,
            "合同未载明或无法抽取「%s」，无法判定" % (rule.param or rule.title),
            limit=rule.value,
        )
    observed = _as_decimal(field.value)
    limit = _as_decimal(rule.value)
    cmp = _OPS.get(rule.op)
    if cmp is None:
        return _mk(rule, STATUS_UNKNOWN, "未知运算符 %s，无法判定" % rule.op)
    ok = cmp(observed, limit)
    status = STATUS_COMPLIANT if ok else STATUS_NONCOMPLIANT
    ok_words, bad_words = _limit_words(rule.op)
    reason = "约定 %s%s，%s %s%s" % (
        observed,
        rule.unit or "",
        ok_words if ok else bad_words,
        limit,
        rule.unit or "",
    )
    return _mk(rule, status, reason, observed=field.value, limit=rule.value)


def _check_deadline(rule: Rule, card: LeaseCard) -> Finding:
    if rule.op is None or rule.value is None:
        # 程序性/补充性条款（如法定补充规则）：无阈值，判"是否已约定"更合适
        if rule.param and card.get(rule.param).observed:
            declared = card.get(rule.param).value
            if declared is True:
                return _mk(rule, STATUS_COMPLIANT, "合同已约定该项期限")
            if declared is False:
                return _mk(
                    rule,
                    STATUS_UNKNOWN,
                    "合同未约定该项，依本条法定补充规则处理（非法定违反，仅提示）",
                )
        return _mk(rule, STATUS_UNKNOWN, "该条为程序性补充规则，无数值阈值，无法作数值判定")
    return _check_numeric(rule, card)


def _looks_like_lease_contract(card: LeaseCard) -> bool:
    """文本是否可识别为租赁合同。

    必要性：对**非合同文本**（一段说明文字、片段）判"缺失法定要素 = noncompliant"
    是**假 noncompliant**——比 unknown 更糟（冤枉用户，且把"这不是合同"说成
    "你的合同不合格"）。不可识别时返回 False，由调用方判 unknown。
    """
    text_field = card.get("contract_text")
    text = text_field.value if text_field and text_field.value else ""
    if not text:
        return False
    has_keyword = any(k in text for k in ("租赁", "出租", "承租", "租金", "押金"))
    return has_keyword and bool(card.clauses)


def _check_elements(rule: Rule, card: LeaseCard) -> Finding:
    """定性检查项：按要素别名表逐项匹配合同文本。

    别名表是必要的——用法条的逐字措辞去匹配合同会把"已约定但措辞不同"
    误判成"缺失"，产生**假 noncompliant**（比 unknown 更糟：冤枉用户）。
    """
    text_field = card.get("contract_text")
    text = text_field.value if text_field and text_field.value else ""
    elements = getattr(rule, "elements", None) or []
    if not elements:
        return _mk(rule, STATUS_UNKNOWN, "规则未登记要素清单，无法判定")
    if not text:
        return _mk(rule, STATUS_UNKNOWN, "无合同文本，无法判定要素完整性")
    if not _looks_like_lease_contract(card):
        # 不是可识别的租赁合同 → 未观测（"没看到"而非"缺失"）
        return _mk(
            rule,
            STATUS_UNKNOWN,
            "输入文本不构成可识别的租赁合同，无法评估要素完整性（未观测，非缺失）",
        )

    missing: List[str] = []
    for item in elements:
        if isinstance(item, dict):
            name = item.get("name", "")
            aliases = list(item.get("aliases") or [])
            candidates = [name] + aliases if name else aliases
        else:
            name = str(item)
            candidates = [name]
        if not any(c and c in text for c in candidates):
            missing.append(name)

    if not missing:
        return _mk(rule, STATUS_COMPLIANT, "法定要素全部载明（%d 项）" % len(elements))
    return _mk(
        rule,
        STATUS_NONCOMPLIANT,
        "缺失法定要素 %d 项：%s（建议补充）" % (len(missing), "、".join(missing)),
    )


def _check_prohibition(rule: Rule, card: LeaseCard) -> Finding:
    """禁止性/提示性条款：本项目不针对租客合同判定，归条件触发栏。"""
    return _mk(rule, STATUS_SKIPPED, "该条为监管裁量/提示性条款，不针对本合同判定")


_DISPATCH = {
    "numeric_limit": _check_numeric,
    "deadline_obligation": _check_deadline,
    "element_completeness": _check_elements,
    "text_prohibition": _check_prohibition,
}


def check_card(card: LeaseCard, ruleset: Ruleset) -> List[Finding]:
    """对合同卡片逐条判定。同一规则包版本 + 同一输入 = 同一输出。"""
    findings: List[Finding] = []
    for rule in ruleset.rules:
        applicability = _applicability(rule, card)
        if applicability == "not_applies":
            findings.append(_mk(rule, STATUS_SKIPPED, _reason_skipped(rule, card)))
            continue
        if applicability == "indeterminate":
            # 主体未知 → unknown（不是 skipped）：绝不替用户断言"这条不适用"
            findings.append(_mk(rule, STATUS_UNKNOWN, _reason_indeterminate(rule)))
            continue
        handler = _DISPATCH.get(rule.check_type)
        if handler is None:
            findings.append(
                _mk(rule, STATUS_UNKNOWN, "未知判定类型 %s，无法判定" % rule.check_type)
            )
            continue
        findings.append(handler(rule, card))
    return findings
