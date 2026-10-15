"""真值对账语义的**单一实现源**（测试与基准共用）。

若两条通路各写一套对账逻辑，会出现"基准说达标、测试说不过"的双口径漂移。
"""

from __future__ import annotations

from typing import Dict, List

from ..model import NON_PASS_STATUSES

__all__ = ["observed_nonpass", "compare_nonpass", "non_pass_set"]

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
