"""真值对账语义的**单一实现源**（测试与基准共用）。

若两条通路各写一套对账逻辑，会出现"基准说达标、测试说不过"的双口径漂移。
"""

from __future__ import annotations

from typing import Dict, List

from ..model import NON_PASS_STATUSES

__all__ = ["observed_nonpass", "compare_nonpass", "compare_exact", "non_pass_set"]

# 非 pass = fail ∪ unknown ∪ not_assessed
# "skipped" 不计入——它表示"不适用"，不是"有问题"。
_SKIP = "skipped"
_REFERENCE = "reference"


def non_pass_set(findings: Dict[str, str]) -> Dict[str, str]:
    """从 {rule_id: status} 中取出非 pass 子集。"""
    return {
        rid: st
        for rid, st in findings.items()
        if st in NON_PASS_STATUSES
    }


def observed_nonpass(findings: Dict[str, str]) -> Dict[str, str]:
    """观测到的非 pass 集合（引擎输出侧）。"""
    return non_pass_set(findings)


def compare_nonpass(
    expected: Dict[str, str], observed: Dict[str, str]
) -> Dict[str, List[str]]:
    """对账：返回 命中 / 漏报 / 误报 / 状态不符 四类。

    - 漏报（missed）：期望非 pass 但观测为 pass/skipped
    - 误报（false_positive）：期望 pass/skipped 但观测为非 pass
    - 状态不符（status_mismatch）：都在非 pass 集合里但状态不同
    """
    exp = non_pass_set(expected)
    obs = non_pass_set(observed)
    hits, missed, fp, mismatch = [], [], [], []

    for rid, st in exp.items():
        if rid not in obs:
            missed.append(rid)
        elif obs[rid] == st:
            hits.append(rid)
        else:
            mismatch.append(rid)

    for rid in obs:
        if rid not in exp:
            fp.append(rid)

    return {
        "hits": sorted(hits),
        "missed": sorted(missed),
        "false_positive": sorted(fp),
        "status_mismatch": sorted(mismatch),
    }


def compare_exact(
    expected: Dict[str, str], observed: Dict[str, str]
) -> Dict[str, List[str]]:
    """全量精确对账：真值登记的**每条**规则，观测状态必须与登记状态一致。

    与 `compare_nonpass` 的分工：后者只比对非 pass 集合（用于误报/漏报判定），
    会漏掉一整类错误——真值登记 `compliant` / `skipped` / `reference`，观测却是
    别的状态：两侧都不落在非 pass 集合里，**恒不报**。

    本函数把 `expect ∪ also_expect` 全部纳入分母，因此 `also_expect`（同一注入
    隐含的其余结论，如 quota 条进条件触发栏的 `reference`）不再"登记了但从不校验"
    的死数据——真值库里出现一个永不参与对账的字段，本身就是一种假覆盖。

    返回四类：`hits`（登记且一致）、`mismatch`（登记且观测到，但状态不同）、
    `missed`（登记了却完全没观测到）、`unregistered`（观测到却未登记真值——
    真值库漏登记，与"假覆盖"同源，故计入分母的非命中侧）。
    """
    hits: List[str] = []
    mismatch: List[str] = []
    missed: List[str] = []
    for rid, st in expected.items():
        if rid not in observed:
            missed.append(rid)
        elif observed[rid] == st:
            hits.append(rid)
        else:
            mismatch.append(rid)
    unregistered = [rid for rid in observed if rid not in expected]
    return {
        "hits": sorted(hits),
        "mismatch": sorted(mismatch),
        "missed": sorted(missed),
        "unregistered": sorted(unregistered),
    }
