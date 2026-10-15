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

__all__ = [
    "Section", "DISCLAIMER", "report_sections", "assert_traceable",
    "TraceabilityError", "coverage_rows",
]

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


# 五态的中文标签（报告读者看的是中文，不是枚举值）。
# 只收五态：`status_counts` 只统计 findings（义务栏），条件触发栏的 `reference`
# 是栏位标记而非判定状态，不参与计数。
_STATUS_LABELS = {
    "compliant": "符合",
    "noncompliant": "不符合",
    "skipped": "不适用",
    "unknown": "无法判定",
    "not_assessed": "未评估",
}


def _counts_text(counts: Dict[str, int]) -> str:
    """五态计数的可读串。**全部状态都列出（含 0 项）**。

    只列非零项会让"该状态被检查过但为 0"与"该状态根本没被纳入检查"长得一样，
    又把五态语义退化回三态——正是它要防的误读。
    """
    parts = []
    for status in ("compliant", "noncompliant", "skipped", "unknown", "not_assessed"):
        parts.append("%s %d 项" % (_STATUS_LABELS[status], counts.get(status, 0)))
    return "，".join(parts)


def coverage_rows(coverage: Optional[Dict[str, Any]]) -> List[List[str]]:
    """覆盖登记 → 报告表行（分母 / 分子 / 采样清单）。

    与 CLI 的 `coverage_lines()` 同源于 `coverage.truth_sampling`——
    两处各写一套会让"报告说的采样数"与"CLI 说的采样数"成为两份真相。
    """
    from ..benchmark.coverage import CHECK_TYPE_FORMS

    sampling = (coverage or {}).get("truth_sampling") or {}
    rows: List[List[str]] = []
    for form in CHECK_TYPE_FORMS:
        item = sampling.get(form)
        if not item:
            continue
        rows.append(
            [
                form,
                str(item.get("rule_total", 0)),
                str(item.get("sampled_rules", 0)),
                "、".join(item.get("sampled_rule_ids") or []) or "—",
            ]
        )
    return rows


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
                # 整体判定与五态计数必须进**报告**出口（不止 CLI）：导出文件常被
                # 单独转发给读者，若只有明细表，读者无法区分"全不适用"（not_assessed）
                # 与"有一半没能判定"（unknown）——这正是五态语义要防的误读。
                "整体判定：%s" % result.overall_summary(),
                "判定状态计数：%s" % _counts_text(result.status_counts),
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
                _fmt(f.quote),
                f.reason,
            ]
        )
    sections.append(
        Section(
            key="findings",
            title="二、逐条判定（无条件义务）",
            paragraphs=["共 %d 条判定。" % len(result.findings)],
            table={
                "headers": [
                    "规则 ID", "规则", "判定", "风险级", "约定值", "规则限值",
                    "条款号", "法条原文", "判定理由",
                ],
                "rows": det_rows,
            },
        )
    )

    # §3 条件触发栏（独立小节，不合写）
    trig_rows = []
    for f in result.conditional_triggers:
        trig_rows.append([f.rule_id, f.title, _fmt(f.clause), _fmt(f.quote), f.reason])
    sections.append(
        Section(
            key="conditional",
            title="三、条件触发与监管裁量事项（非相对人无条件义务）",
            paragraphs=[
                "本节所列事项为**监管裁量权或提示性条款**，不构成相对人的无条件义务，"
                "亦不计入上节频次/期限统计。"
            ],
            table={"headers": ["规则 ID", "事项", "条款号", "法条原文", "说明"], "rows": trig_rows},
            enabled=bool(trig_rows),
            disabled_note="本次未涉及条件触发事项。" if not trig_rows else None,
        )
    )

    # §4 未启用清单（显式写出）
    disabled = result.disabled_rules or []
    dis_rows = [[d.get("rule_id"), d.get("title"), d.get("status"), d.get("reason")] for d in disabled]
    # 引导语必须**覆盖两种拦截原因**：数值 status 非 verified，**或**缺锚点
    # （M1 起锚点门也会往本清单塞条目）。只写"数值核对状态非 verified"时，
    # 缺锚点被拦下的规则会带着"缺锚点（法条原文）"的理由列在下面，读者却被告知
    # 是数值没核对——理由与清单自相矛盾（实测：北京包缺 quote 时即为此形态）。
    sections.append(
        Section(
            key="disabled",
            title="四、本次未启用的规则",
            paragraphs=[
                "以下规则因**数值核对状态非 `verified`** 或**缺锚点**（条款号 / 法条原文 / 来源）"
                "而**未参与本次判定**（这与「已判定且未发现问题」是两种截然不同的结论）；"
                "逐条原因见下表。"
            ],
            table={"headers": ["规则 ID", "规则", "状态", "原因"], "rows": dis_rows},
            enabled=True,
            disabled_note="本次未启用任何规则（全部规则均为已核对状态且锚点齐备）。" if not dis_rows else None,
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

    # §7 基准覆盖登记（分母 + 分子 + 采样清单）
    # 报告单独转发给读者时，只看到"逐条判定"无法判断**规则包覆盖了多少、真值库采样了几条**——
    # 覆盖声明必须进产物，否则"覆盖了哪些形态"只在规则包里可见（读者核不到）。
    sections.append(
        Section(
            key="coverage",
            title="七、基准覆盖登记",
            paragraphs=[
                "本规则包的判定基准覆盖情况（**分母 = 规则条数，分子 = 真值库采样条数**，"
                "并声明「抽样覆盖、非逐条穷举」）。只写分母就是假覆盖，故分子与采样清单"
                "一并列出，供读者判断「这个规则包被验到什么程度」。",
            ],
            table={
                "headers": ["规则形态", "规则条数（分母）", "真值库采样条数（分子）", "采样清单"],
                "rows": [],
            },
        )
    )

    # §8 依据清单 + 免责声明
    sections.append(
        Section(
            key="disclaimer",
            title="八、依据与免责声明",
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
