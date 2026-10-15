"""规则包加载与门控。

门控纪律（plan/02 §4）：
- `status`（数值核对状态）是**唯一判定门控**：pending 条目绝不进判定路径。
- `clause_status`（条款号核对状态）只做可证性展示，不阻断判定。
- 门控**按作用域**取条目：calc 路径只校验 scope ∈ {calc, check}。
- 第三态 `input_required` 标在字段层，不阻断门控但运行时必索。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..paths import find_data_dir

__all__ = ["Rule", "Ruleset", "RulesetError", "load_ruleset", "available_cities"]

SCOPES = ("calc", "check", "quota")
CITY_FILES = {
    "北京": "ruleset-bj.json",
    "上海": "ruleset-sh.json",
    "全国": "ruleset-cn.json",
}


class RulesetError(Exception):
    """规则包缺失/结构错误/门控拦截。CLI 映射为退出码 2。"""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    check_type: str
    scope: str
    param: Optional[str]
    op: Optional[str]
    value: Any
    unit: Optional[str]
    applies_if: Dict[str, Any]
    effect: str
    severity: str
    source_id: str
    clause: Optional[str]
    quote: Optional[str]
    status: str
    clause_status: str
    elements: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Rule":
        return cls(
            rule_id=d["rule_id"],
            title=d["title"],
            check_type=d["check_type"],
            scope=d["scope"],
            param=d.get("param"),
            op=d.get("op"),
            value=d.get("value"),
            unit=d.get("unit"),
            applies_if=d.get("applies_if") or {},
            effect=d["effect"],
            severity=d.get("severity", "medium"),
            source_id=d["source_id"],
            clause=d.get("clause"),
            quote=d.get("quote"),
            status=d["status"],
            clause_status=d.get("clause_status", "pending"),
            elements=d.get("elements"),
        )


@dataclass
class Ruleset:
    ruleset_id: str
    city: str
    city_code: str
    version: str
    sources: List[Dict[str, Any]]
    rules: List[Rule]
    thresholds: Dict[str, Any]
    manifest_coverage: Dict[str, Any]
    # 门控产物（effective_ruleset 填充）
    disabled_rules: List[Dict[str, Any]] = field(default_factory=list)
    reference_rules: List[Rule] = field(default_factory=list)

    def source_by_id(self, source_id: str) -> Optional[Dict[str, Any]]:
        for s in self.sources:
            if s["source_id"] == source_id:
                return s
        return None

    def rule_by_id(self, rule_id: str) -> Optional[Rule]:
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RulesetError("规则包不存在: %s" % path)
    except OSError as exc:
        raise RulesetError("规则包读取失败 %s: %s" % (path, exc))
    try:
        return json.loads(text)
    except ValueError as exc:
        raise RulesetError("规则包 JSON 非法 %s: %s" % (path, exc))


def load_ruleset(city: str, data_dir: Optional[str] = None) -> Ruleset:
    """按城市加载规则包（含全部条目，不门控）。"""
    if city not in CITY_FILES:
        raise RulesetError(
            "不支持的城市: %s（可选：%s）" % (city, "、".join(CITY_FILES))
        )
    root = Path(data_dir) if data_dir else find_data_dir()
    path = root / "rules" / CITY_FILES[city]
    raw = _load_json(path)
    rules = [Rule.from_dict(r) for r in raw.get("rules", [])]
    if not rules:
        raise RulesetError("规则包无条目: %s" % path)
    return Ruleset(
        ruleset_id=raw["ruleset_id"],
        city=raw.get("city", city),
        city_code=raw.get("city_code", ""),
        version=raw.get("version", ""),
        sources=raw.get("sources", []),
        rules=rules,
        thresholds=raw.get("benchmark_thresholds", {}),
        manifest_coverage=raw.get("coverage", {}),
    )


def available_cities(data_dir: Optional[str] = None) -> List[str]:
    root = Path(data_dir) if data_dir else find_data_dir()
    out = []
    for city, fname in CITY_FILES.items():
        if (root / "rules" / fname).is_file():
            out.append(city)
    return out


def effective_ruleset(
    city: str, scope: str, data_dir: Optional[str] = None
) -> Ruleset:
    """门控后的规则包。

    作用域语义（plan/02 §4.1）：
      - "calc"  → 判定路径：取 scope ∈ {calc, check} 的 verified 条目
      - "check" → 只取 scope == "check"
      - "quota" → 只取 scope == "quota"

    关键：**scope 决定"是否参与判定"，不决定"是否呈现"**。
    quota 类（监管裁量/提示性条款）在 calc 路径下仍以 `reference_rules` 呈现
    （进"条件触发栏"），否则报告会漏掉整类事项——"没查"与"查了没问题"
    是两种截然不同的结论。

    分层：城市包（京/沪）**叠加在全国层（民法典）之上**——全国层的规则
    对任何城市都适用，城市包只补充/覆盖地方特有规则。
    同名 rule_id 以城市包为准（地方规定优先）。

    被拦下的条目记入 `disabled_rules`，调用方负责在产物里显式呈现。
    """
    if scope not in SCOPES:
        raise RulesetError("未知作用域: %s（可选：%s）" % (scope, "/".join(SCOPES)))

    rs = load_ruleset(city, data_dir)
    # 叠加全国层（城市包本身不重复叠加）
    merged = list(rs.rules)
    if city != "全国":
        try:
            national = load_ruleset("全国", data_dir)
        except RulesetError:
            national = None
        if national is not None:
            city_ids = {r.rule_id for r in rs.rules}
            for r in national.rules:
                if r.rule_id not in city_ids:
                    merged.append(r)
            # 来源台账合并：否则全国层规则在"参数来源块"里查不到出处
            known = {s.get("source_id") for s in rs.sources}
            for s in national.sources:
                if s.get("source_id") not in known:
                    rs.sources.append(s)

    if scope == "calc":
        wanted = {"calc", "check"}
    else:
        wanted = {scope}

    kept: List[Rule] = []
    reference: List[Rule] = []
    disabled: List[Dict[str, Any]] = []
    for r in merged:
        if r.status != "verified":
            if r.scope in wanted or r.scope == "quota":
                disabled.append(
                    {
                        "rule_id": r.rule_id,
                        "title": r.title,
                        "status": r.status,
                        "clause_status": r.clause_status,
                        "reason": "数值核对状态非 verified，不参与判定",
                    }
                )
            continue
        # 锚点门（题面模块②硬约束）：**缺锚点的规则不得被引擎加载生效**。
        # 锚点 = 条款号 + 法条原文逐字引用；两者缺一，判定结论就无从核证——
        # 报告会给出一条"看起来有依据"的判定，读者却找不到原文核对（比不判更危险）。
        # 生成器已对出厂规则做逐字断言，但门控不能只依赖上游：规则包可被手工替换、
        # 也可由第三方扩展包提供，引擎必须在**加载侧**再拦一次。
        missing = []
        if not r.clause:
            missing.append("条款号")
        if not r.quote:
            missing.append("法条原文")
        if not r.source_id:
            missing.append("来源")
        if missing:
            if r.scope in wanted or r.scope == "quota":
                disabled.append(
                    {
                        "rule_id": r.rule_id,
                        "title": r.title,
                        "status": r.status,
                        "clause_status": r.clause_status,
                        "reason": "缺锚点（%s），不参与判定" % "、".join(missing),
                    }
                )
            continue
        if r.scope == "quota":
            # 条件触发/监管裁量：不作为相对人义务判定，但必须在报告里显式呈现
            if scope == "calc":
                reference.append(r)
            continue
        if r.scope in wanted:
            kept.append(r)

    rs.rules = kept
    rs.reference_rules = reference
    rs.disabled_rules = disabled
    return rs
