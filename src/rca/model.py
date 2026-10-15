"""统一中间表示：条款序列、合同卡片、判定结果。

设计：条款切分与要素抽取的产物都进这里定义的结构，"判定"就归约为
"卡片字段 vs 规则条目"的结构化对齐。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "Clause",
    "Evidence",
    "Field",
    "LeaseCard",
    "Finding",
    "Result",
    "STATUS_COMPLIANT",
    "STATUS_NONCOMPLIANT",
    "STATUS_SKIPPED",
    "STATUS_UNKNOWN",
    "STATUS_NOT_ASSESSED",
    "ALL_STATUSES",
]

# 判定状态五值（口径见 plan/03 §4.1）
STATUS_COMPLIANT = "compliant"
STATUS_NONCOMPLIANT = "noncompliant"
STATUS_SKIPPED = "skipped"
STATUS_UNKNOWN = "unknown"
STATUS_NOT_ASSESSED = "not_assessed"
ALL_STATUSES = (
    STATUS_COMPLIANT,
    STATUS_NONCOMPLIANT,
    STATUS_SKIPPED,
    STATUS_UNKNOWN,
    STATUS_NOT_ASSESSED,
)

# 非 pass 集合（用于基准对账）：fail ∪ unknown ∪ not_assessed
NON_PASS_STATUSES = (STATUS_NONCOMPLIANT, STATUS_UNKNOWN, STATUS_NOT_ASSESSED)


def _jsonable(value: Any) -> Any:
    """Decimal → str（JSON 无 Decimal 类型；字符串保留精度语义）。"""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


@dataclass(frozen=True)
class Clause:
    """切分出的一个条款。"""

    number: str
    text: str
    kind: str
    span: Tuple[int, int]
    located: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "text": self.text,
            "kind": self.kind,
            "span": list(self.span),
            "located": self.located,
        }

@dataclass(frozen=True)
class Evidence:
    """判定依据的证据锚点。clause_text 必须是原文子串（抽取层已断言）。"""

    clause_number: Optional[str] = None
    clause_text: Optional[str] = None
    char_span: Optional[Tuple[int, int]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clause_number": self.clause_number,
            "clause_text": self.clause_text,
            "char_span": list(self.char_span) if self.char_span else None,
        }


@dataclass(frozen=True)
class Field:
    """卡片上的一个要素。value=None 表示未观测。"""

    name: str
    value: Any = None
    unit: Optional[str] = None
    confidence: str = "absent"
    evidence: Optional[Evidence] = None

    @property
    def observed(self) -> bool:
        return self.value is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": _jsonable(self.value),
            "unit": self.unit,
            "confidence": self.confidence,
            "evidence": self.evidence.to_dict() if self.evidence else None,
        }


@dataclass
class LeaseCard:
    """合同卡片：判定引擎的唯一输入形态。"""

    city: Optional[str] = None
    party: str = "unknown"
    lease_kind: str = "ordinary"
    fields: Dict[str, Field] = field(default_factory=dict)
    clauses: List[Clause] = field(default_factory=list)
    pending_manual: List[str] = field(default_factory=list)
    encoding_fallback: Optional[str] = None

    def get(self, name: str) -> Field:
        return self.fields.get(name, Field(name=name))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "city": self.city,
            "party": self.party,
            "lease_kind": self.lease_kind,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "clauses": [c.to_dict() for c in self.clauses],
            "pending_manual": list(self.pending_manual),
            "encoding_fallback": self.encoding_fallback,
        }


@dataclass(frozen=True)
class Finding:
    """一条判定结果。rule_id 必须能在规则包中解析（溯源硬约束）。"""

    rule_id: str
    title: str
    status: str
    check_type: str
    effect: str
    severity: str
    scope: str
    reason: str
    param: Optional[str] = None
    observed: Any = None
    limit: Any = None
    op: Optional[str] = None
    unit: Optional[str] = None
    clause: Optional[str] = None
    quote: Optional[str] = None
    source_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "status": self.status,
            "check_type": self.check_type,
            "effect": self.effect,
            "severity": self.severity,
            "scope": self.scope,
            "reason": self.reason,
            "param": self.param,
            "observed": _jsonable(self.observed),
            "limit": _jsonable(self.limit),
            "op": self.op,
            "unit": self.unit,
            "clause": self.clause,
            "quote": self.quote,
            "source_id": self.source_id,
        }


@dataclass
class Result:
    """一次体检的完整结果。"""

    ruleset_id: str
    ruleset_version: str
    city: Optional[str]
    findings: List[Finding] = field(default_factory=list)
    card: Optional[LeaseCard] = None
    disabled_rules: List[Dict[str, Any]] = field(default_factory=list)
    conditional_triggers: List[Finding] = field(default_factory=list)

    @property
    def obligations(self) -> List[Finding]:
        """无条件义务栏（含 periodic/standing）——频次与期限只取此栏。"""
        return [f for f in self.findings if f.effect != "conditional_institution"]

    @property
    def overall_status(self) -> str:
        """整体等级。

        - 无任何有效判定（全 skipped）→ not_assessed（绝不输出 compliant）
        - 有 noncompliant → noncompliant
        - 有 unknown → not_assessed（结论不完整；**保守口径**：不声称合规）
        - 否则 compliant

        "没查出问题"与"没检查过"必须可区分：有 unknown 项时**绝不**报 compliant。
        报告层须同时给出"已判定 N 项 / 未判定 M 项"的计数，避免读者把
        "部分未判定"误读成"完全没检查"。
        """
        considered = list(self.findings)
        if not considered:
            return STATUS_NOT_ASSESSED
        effective = [f for f in considered if f.status != STATUS_SKIPPED]
        if not effective:
            return STATUS_NOT_ASSESSED
        if any(f.status == STATUS_NONCOMPLIANT for f in effective):
            return STATUS_NONCOMPLIANT
        if any(f.status in (STATUS_UNKNOWN, STATUS_NOT_ASSESSED) for f in effective):
            return STATUS_NOT_ASSESSED
        return STATUS_COMPLIANT

    @property
    def status_counts(self) -> Dict[str, int]:
        """各状态计数（报告层用于把"部分未判定"与"完全未检查"区分开）。"""
        out: Dict[str, int] = {}
        for f in self.findings:
            out[f.status] = out.get(f.status, 0) + 1
        return out

    def overall_summary(self) -> str:
        """整体判定的可读摘要（含计数，防误读）。"""
        counts = self.status_counts
        assessed = sum(v for k, v in counts.items() if k != STATUS_SKIPPED)
        undetermined = counts.get(STATUS_UNKNOWN, 0)
        parts = ["已判定 %d 项" % assessed]
        if undetermined:
            parts.append("其中未能判定 %d 项（需人工确认或补充合同信息）" % undetermined)
        skipped = counts.get(STATUS_SKIPPED, 0)
        if skipped:
            parts.append("不适用 %d 项" % skipped)
        return "%s（%s）" % (self.overall_status, "，".join(parts))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "city": self.city,
            "overall_status": self.overall_status,
            "findings": [f.to_dict() for f in self.findings],
            "conditional_triggers": [f.to_dict() for f in self.conditional_triggers],
            "disabled_rules": list(self.disabled_rules),
            "card": self.card.to_dict() if self.card else None,
        }
