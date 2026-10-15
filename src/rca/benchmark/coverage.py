"""覆盖登记语义的**单一实现源**（生成器与基准/CLI/报告共用）。

plan/04 §2.3 要求 manifest 逐形态登记 **"规则包条目总数 / 真值库采样数 / 采样清单"**
三件套，并声明"抽样覆盖、非逐条穷举"。判别口诀：**"分母（总数）和分子（采样数）
都写出来了吗？只写分子就是假覆盖。"**

本项目此前只登记了分母（`rule_totals_by_check_type`）——**连分子都没有**，
"覆盖声明"于是成了一句无法证伪的话。本模块把三件套实算出来：

- 分母 `rule_total`：该形态在**本包**的规则条数；
- 分子 `sampled_rules`：其中被真值库采样到的条数（`expect ∪ also_expect` 里出现过）；
- 采样清单 `sampled_rule_ids` / `sample_ids`：具体是哪几条规则、由哪几份样例提供真值。

两处共用一份实现，避免"生成器算一套、基准再算一套"的双口径漂移
（与 `cases.py` 同一条纪律）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

__all__ = [
    "CHECK_TYPE_FORMS",
    "truth_rule_ids",
    "sample_coverage",
    "coverage_gaps",
    "coverage_lines",
]

# 规则形态（check_type）全集。与规则包 manifest 的 `rule_totals_by_check_type`
# 键集一致；缺一即"该形态无任何规则"或"登记漏了一个形态"，两种都要报。
CHECK_TYPE_FORMS = (
    "numeric_limit",
    "deadline_obligation",
    "element_completeness",
    "text_prohibition",
)

SAMPLING_DECLARATION = "抽样覆盖、非逐条穷举"


def truth_rule_ids(sample: Dict[str, Any]) -> List[str]:
    """一份样例真值登记的全部 rule_id（主期望 + 隐含结论）。

    `also_expect` 必须一并纳入：它是"同一注入隐含的其余结论"（如 quota 条进
    条件触发栏的 `reference`）。若覆盖登记只数 `expect`，那些只出现在
    `also_expect` 里的规则会被记成"没采样"，而它们其实有真值。
    """
    ids = list(sample.get("expect") or {})
    ids += list(sample.get("also_expect") or {})
    return ids


def sample_coverage(
    rule_forms: Dict[str, str], samples: Sequence[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """逐形态实算覆盖三件套。

    `rule_forms`：{rule_id: check_type}——**本包**的规则（不含叠加进来的其他层），
    否则"分母"会混进别包的条目，登记的数与真实的数成了两份。

    返回 `{form: {"rule_total", "sampled_rules", "sampled_rule_ids", "sample_ids"}}`。
    """
    # 每个样例提供真值的 rule_id 集合（一次算好，避免逐形态重复遍历）
    per_sample_ids = [(s.get("sample_id"), set(truth_rule_ids(s))) for s in samples]

    out: Dict[str, Dict[str, Any]] = {}
    for form in CHECK_TYPE_FORMS:
        form_rules = sorted(rid for rid, ct in rule_forms.items() if ct == form)
        sampled_rules: List[str] = []
        sample_ids: List[str] = []
        for rid in form_rules:
            hit = [sid for sid, ids in per_sample_ids if rid in ids]
            if hit:
                sampled_rules.append(rid)
                sample_ids.extend(hit)
        out[form] = {
            "rule_total": len(form_rules),
            "sampled_rules": len(sampled_rules),
            "sampled_rule_ids": sampled_rules,
            # 采样清单按样例去重且保序（确定性产物不得依赖 set 迭代序）
            "sample_ids": sorted(set(sample_ids)),
        }
    return out


def coverage_gaps(rule_forms: Dict[str, str], samples: Sequence[Dict[str, Any]]) -> List[str]:
    """返回**未被任何样例采样**的规则形态清单（空列表 = 无缺口）。

    "每个形态至少有一份采样件"是覆盖声明的下限；一个形态有规则却零采样件，
    说明该形态在基准里等于没测（分子为 0），必须显式报出来而不是静默。
    """
    cov = sample_coverage(rule_forms, samples)
    return [form for form in CHECK_TYPE_FORMS if cov[form]["rule_total"] > 0 and cov[form]["sampled_rules"] == 0]


def coverage_lines(coverage: Dict[str, Any]) -> List[str]:
    """把覆盖登记渲染成人读行（CLI 与报告共用，避免两处各写一套措辞）。"""
    sampling = (coverage or {}).get("truth_sampling") or {}
    if not sampling:
        return []
    lines = []
    for form in CHECK_TYPE_FORMS:
        item = sampling.get(form)
        if not item:
            continue
        lines.append(
            "%s：规则 %d 条，真值库采样 %d 条（样例 %d 份）"
            % (
                form,
                item.get("rule_total", 0),
                item.get("sampled_rules", 0),
                len(item.get("sample_ids") or []),
            )
        )
    return lines
