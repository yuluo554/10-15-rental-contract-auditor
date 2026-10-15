"""编排层：CLI 与 GUI 共用的公开函数组。

"同一个业务判断在项目里有几处实现？"——多于一处的就是上收没做完。
本模块是**唯一**的端到端编排入口：CLI 与 GUI 都只经这些函数取数。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from ..model import Finding, LeaseCard, Result, STATUS_NONCOMPLIANT
from ..parser.clauses import split_clauses
from ..parser.extract import build_card as _build_card_from_parts
from .checker import check_card
from .ruleset import RulesetError, effective_ruleset

__all__ = [
    "PipelineError",
    "build_card",
    "check_contract",
    "compute_result",
    "parameter_overview",
    "ruleset_overview",
    "diagnostics",
    "quantize",
]


class PipelineError(Exception):
    """编排层错误。CLI 映射为退出码 2。"""


def quantize(value: Any) -> Optional[str]:
    """展示口径：两位小数 ROUND_HALF_UP（精度约定，非政策数值）。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return str(value)


def build_card(text: str) -> LeaseCard:
    """合同文本 → 卡片（切分 + 抽取），并保留待人工确认清单。"""
    if not text or not text.strip():
        raise PipelineError("合同文本为空")
    clauses, normalized, pending = split_clauses(text)
    return _build_card_from_parts(normalized, clauses, pending)


def compute_result(
    text: str,
    city: str,
    data_dir: Optional[str] = None,
    scope: str = "calc",
) -> Result:
    """端到端：合同文本 + 城市 → 判定结果。CLI 与 GUI 共用此入口。"""
    try:
        ruleset = effective_ruleset(city, scope, data_dir)
    except RulesetError as exc:
        raise PipelineError(str(exc))

    card = build_card(text)
    findings = check_card(card, ruleset)

    obligations = [f for f in findings if f.effect != "conditional_institution"]
    triggers = [f for f in findings if f.effect == "conditional_institution"]

    # 引用型条目（scope=quota：监管裁量/提示性条款）——显式呈现在"条件触发栏"，
    # 绝不作为相对人义务参与判定（否则把监管裁量说成企业法定义务）。
    for rule in getattr(ruleset, "reference_rules", []) or []:
        triggers.append(
            Finding(
                rule_id=rule.rule_id,
                title=rule.title,
                status="reference",
                check_type=rule.check_type,
                effect=rule.effect,
                severity=rule.severity,
                scope=rule.scope,
                reason="该条为监管裁量/提示性条款，不构成相对人的无条件义务，仅作提示",
                clause=rule.clause,
                quote=rule.quote,
                source_id=rule.source_id,
            )
        )

    return Result(
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.version,
        city=ruleset.city,
        findings=obligations,
        conditional_triggers=triggers,
        card=card,
        disabled_rules=list(getattr(ruleset, "disabled_rules", [])),
    )


def check_contract(
    text: str, city: str, data_dir: Optional[str] = None
) -> Result:
    """别名：语义化的端到端入口。"""
    return compute_result(text, city, data_dir=data_dir, scope="calc")


def parameter_overview(city: str, data_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """参数来源块：每项参数挂发布机关/施行日期/文号/URL/抓取日期。

    让读者不开仓库也能核证"这个数字哪来的"。

    **必须覆盖门控后实际参与判定的全部规则**（含叠加进来的全国层规则与
    quota 引用条目）——否则"溯源表行数 == 判定行数"的硬约束会失败，
    或者更糟：报告漏掉一半判定所依据的参数来源。
    """
    try:
        rs = effective_ruleset(city, "calc", data_dir)
    except RulesetError as exc:
        raise PipelineError(str(exc))

    all_rules = list(rs.rules) + list(getattr(rs, "reference_rules", []) or [])
    out = []
    for rule in all_rules:
        src = rs.source_by_id(rule.source_id) or {}
        out.append(
            {
                "rule_id": rule.rule_id,
                "title": rule.title,
                "value": rule.value,
                "unit": rule.unit,
                "clause": rule.clause,
                "status": rule.status,
                "clause_status": rule.clause_status,
                "source_title": src.get("title"),
                "doc_no": src.get("doc_no"),
                "effective_date": src.get("effective_date"),
                "url": src.get("url"),
                "fetched_date": src.get("fetched_date"),
            }
        )
    return out


def ruleset_overview(city: str, data_dir: Optional[str] = None) -> Dict[str, Any]:
    """规则包总览：条目数、来源、门槛、覆盖登记。"""
    from .ruleset import load_ruleset

    try:
        rs = load_ruleset(city, data_dir)
    except RulesetError as exc:
        raise PipelineError(str(exc))
    return {
        "ruleset_id": rs.ruleset_id,
        "city": rs.city,
        "version": rs.version,
        "rule_count": len(rs.rules),
        "thresholds": rs.thresholds,
        "coverage": rs.manifest_coverage,
        "sources": [
            {
                "source_id": s.get("source_id"),
                "title": s.get("title"),
                "doc_no": s.get("doc_no"),
                "effective_date": s.get("effective_date"),
                "url": s.get("url"),
            }
            for s in rs.sources
        ],
    }


def diagnostics(city: str, data_dir: Optional[str] = None) -> Dict[str, Any]:
    """门控诊断：哪些条目被拦下、原因是什么（产物里显式可见）。"""
    try:
        rs = effective_ruleset(city, "calc", data_dir)
    except RulesetError as exc:
        raise PipelineError(str(exc))
    return {
        "ruleset_id": rs.ruleset_id,
        "enabled_count": len(rs.rules),
        "disabled": list(getattr(rs, "disabled_rules", [])),
    }


def has_noncompliant(result: Result) -> bool:
    return any(f.status == STATUS_NONCOMPLIANT for f in result.findings)
