"""报告章节结构（单一渲染源）。

纪律：
- 溯源完整性硬约束：`assert_traceable()` 在导出前断言"溯源行数 == 明细行数"
  且每条引用 rule_id 可解析——不留"半溯源"报告。
- "未启用"章节显式写出（"本次未启用 X"），不留空——"没查"与"查了没问题"
  是两种截然不同的结论，留空会被误读成后者。
- 免责声明必须出现在所有产物（题面 §6.1 法律红线）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..model import Result, STATUS_SKIPPED

__all__ = ["Section", "DISCLAIMER", "report_sections", "assert_traceable", "TraceabilityError"]

DISCLAIMER = "本报告为辅助参考的合同体检结果，不构成法律意见。"

# 免责红线：不得出现的表述（守门测试断言）
FORBIDDEN_PHRASES = ("律师审查", "法律效力", "具有法律效力", "律师意见")


class TraceabilityError(Exception):
    """溯源不完整——拒绝导出（不留半溯源报告）。"""


@dataclass
class Section:
    key: str
    title: str
    paragraphs: List[str] = field(default_factory=list)
    table: Optional[Dict[str, Any]] = None   # {"headers": [...], "rows": [[...]]}
    enabled: bool = True
    disabled_note: Optional[str] = None


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    return str(value)


def report_sections(result: Result) -> List[Section]:
    """把判定结果转成结构化章节。Markdown 与 XLSX 都消费它。"""
    sections: List[Section] = []

    # §1 输入事实
    card = result.card
    rows = []
    if card is not None:
        for name, f in sorted(card.fields.items()):
            if name == "contract_text":
                continue
            rows.append(
                [
                    name,
                    _fmt(f.value),
                    _fmt(f.unit),
                    f.confidence,
                    (f.evidence.clause_number if f.evidence and f.evidence.clause_number else "—"),
                ]
            )
    sections.append(
        Section(
            key="input",
            title="一、输入事实",
            paragraphs=[
                "城市：%s" % _fmt(result.city),
                "合同主体：%s" % _fmt(card.party if card else None),
                "租赁类型：%s" % _fmt(card.lease_kind if card else None),
                "规则包版本：%s（%s）" % (result.ruleset_version, result.ruleset_id),
            ],
            table={"headers": ["要素", "取值", "单位", "置信度", "证据条款"], "rows": rows},
        )
    )

    # §2 判定明细
    det_rows = []
    for f in result.findings:
        det_rows.append(
            [
                f.rule_id,
                f.title,
                f.status,
                f.severity,
                _fmt(f.observed),
                ("%s %s" % (f.op, _fmt(f.limit))) if f.op else "—",
                _fmt(f.clause),
                f.reason,
            ]
        )
    sections.append(
        Section(
            key="findings",
            title="二、逐条判定（无条件义务）",
            paragraphs=["共 %d 条判定。" % len(result.findings)],
            table={
                "headers": ["规则 ID", "规则", "判定", "风险级", "约定值", "规则限值", "条款号", "判定理由"],
                "rows": det_rows,
            },
        )
    )

    # §3 条件触发栏（独立小节，不合写）
    trig_rows = []
    for f in result.conditional_triggers:
        trig_rows.append([f.rule_id, f.title, _fmt(f.clause), f.reason])
    sections.append(
        Section(
            key="conditional",
            title="三、条件触发与监管裁量事项（非相对人无条件义务）",
            paragraphs=[
                "本节所列事项为**监管裁量权或提示性条款**，不构成相对人的无条件义务，"
                "亦不计入上节频次/期限统计。"
            ],
            table={"headers": ["规则 ID", "事项", "条款号", "说明"], "rows": trig_rows},
            enabled=bool(trig_rows),
            disabled_note="本次未涉及条件触发事项。" if not trig_rows else None,
        )
    )

    # §4 未启用清单（显式写出）
    disabled = result.disabled_rules or []
    dis_rows = [[d.get("rule_id"), d.get("title"), d.get("status"), d.get("reason")] for d in disabled]
    sections.append(
        Section(
            key="disabled",
            title="四、本次未启用的规则",
            paragraphs=[
                "以下规则的数值核对状态非 `verified`，**未参与本次判定**"
                "（这与「已判定且未发现问题」是两种截然不同的结论）："
            ],
            table={"headers": ["规则 ID", "规则", "状态", "原因"], "rows": dis_rows},
            enabled=True,
            disabled_note="本次未启用任何规则（全部规则均为已核对状态）。" if not dis_rows else None,
        )
    )

    # §5 待人工确认
    pending = list(card.pending_manual) if card else []
    sections.append(
        Section(
            key="pending",
            title="五、待人工确认",
            paragraphs=["以下项目机器无法定位到逐字原文，需人工核对（不静默吞掉）："],
            table={"headers": ["项目"], "rows": [[p] for p in pending]},
            enabled=True,
            disabled_note="无待人工确认项。" if not pending else None,
        )
    )

    # §6 参数来源块
    sections.append(
        Section(
            key="sources",
            title="六、参数来源",
            paragraphs=["本节参数来源由规则包 manifest 生成，供读者独立核证。"],
            table={"headers": ["规则 ID", "条款号", "来源文件", "文号", "施行日期", "URL"], "rows": []},
        )
    )

    # §7 依据清单 + 免责声明
    sections.append(
        Section(
            key="disclaimer",
            title="七、依据与免责声明",
            paragraphs=[
                "本报告的判定依据为规则包内已核对的法条原文（见各条 `quote` 字段）。",
                DISCLAIMER,
                "如对判定结果有异议，请以官方发布的法规原文为准。",
            ],
        )
    )
    return sections


def assert_traceable(result: Result, sources_rows: List[List[str]]) -> None:
    """导出前断言：溯源行数 == 明细行数 + 条件触发行数，且 rule_id 可解析。"""
    detail_count = len(result.findings) + len(result.conditional_triggers)
    if len(sources_rows) != detail_count:
        raise TraceabilityError(
            "溯源不完整：溯源行 %d != 判定行 %d（拒绝导出）"
            % (len(sources_rows), detail_count)
        )
    ids = [r[0] for r in sources_rows]
    if len(set(ids)) != len(ids):
        raise TraceabilityError("溯源存在重复 rule_id（拒绝导出）")
    for f in list(result.findings) + list(result.conditional_triggers):
        if f.rule_id not in ids:
            raise TraceabilityError("判定 %s 无对应溯源行（拒绝导出）" % f.rule_id)
