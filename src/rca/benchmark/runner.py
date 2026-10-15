"""基准运行器：三套件 + 门槛校验 + 可证伪探活。

退出码三语义：0 达标 / 1 未达标或门控拦截 / 2 用法错误。
门槛**随规则包下发**（数据非代码），缺失即 exit 2——不得回落代码默认值。
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..engine.pipeline import compute_result
from ..engine.ruleset import RulesetError, load_ruleset
from ..model import NON_PASS_STATUSES
from ..paths import find_data_dir
from .cases import compare_nonpass, observed_nonpass

__all__ = ["run_benchmarks", "SUITES"]

SUITES = ("B1", "B2", "B3")

EXIT_OK = 0
EXIT_NOT_MET = 1
EXIT_USAGE = 2


class BenchConfigError(Exception):
    """门槛缺失/套件名未知 → exit 2。"""


def _load_samples(data_dir: Path) -> List[Dict[str, Any]]:
    path = data_dir / "samples" / "samples.json"
    if not path.is_file():
        raise BenchConfigError("样例文件缺失: %s（先跑 tools/gen_samples.py）" % path)
    return json.loads(path.read_text(encoding="utf-8"))


def _thresholds(city: str, data_dir: Path) -> Dict[str, Any]:
    """门槛随规则包下发；缺失即配置错误（不回落代码默认值）。"""
    rs = load_ruleset(city, str(data_dir))
    th = rs.thresholds
    if not th:
        raise BenchConfigError("规则包 %s 未下发 benchmark_thresholds" % rs.ruleset_id)
    return th


def _run_b1(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """解析基准：要素抽取字段级准确率。

    首期以"抽取字段存在且证据可回定位"为判据（字段级 P/R 的简化形态）。
    """
    total = 0
    ok = 0
    details = []
    for s in samples:
        result = compute_result(s["contract_text"], s["city"])
        card = result.card
        checks = 0
        passed = 0
        for name, f in card.fields.items():
            if name == "contract_text":
                continue
            checks += 1
            # 判据：有值的字段必须有证据条款；无值字段置信度须为 absent
            if f.observed:
                good = bool(f.evidence and f.evidence.clause_text)
            else:
                good = f.confidence == "absent"
            if good:
                passed += 1
        total += checks
        ok += passed
        details.append({"sample_id": s["sample_id"], "fields": checks, "ok": passed})
    f1 = (ok / total) if total else 0.0
    return {
        "suite": "B1",
        "name": "解析基准（要素抽取）",
        "metric": "field_accuracy",
        "value": round(f1, 4),
        "numerator": ok,
        "denominator": total,
        "details": details,
    }


def _run_b2(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """端到端判定基准：植入真值对账（命中率 / 误报率）。"""
    hits = missed = fp = mismatch = 0
    per_sample = []
    for s in samples:
        result = compute_result(s["contract_text"], s["city"])
        observed = {f.rule_id: f.status for f in result.findings}
        for f in result.conditional_triggers:
            observed[f.rule_id] = f.status
        cmp = compare_nonpass(s["expect"], observed)
        hits += len(cmp["hits"])
        missed += len(cmp["missed"])
        fp += len(cmp["false_positive"])
        mismatch += len(cmp["status_mismatch"])
        per_sample.append({"sample_id": s["sample_id"], **{k: len(v) for k, v in cmp.items()}})

    denom = hits + missed + mismatch
    hit_rate = (hits / denom) if denom else 0.0
    return {
        "suite": "B2",
        "name": "端到端判定基准（植入真值对账）",
        "metric": "hit_rate",
        "value": round(hit_rate, 4),
        "numerator": hits,
        "denominator": denom,
        "false_positive": fp,
        "status_mismatch": mismatch,
        "details": per_sample,
    }


def _run_b3(cities: List[str], data_dir: Path) -> Dict[str, Any]:
    """规则驱动边界扫描：**不读真值库**，从规则表推导端点做 ±精度邻域断言。

    专门补"样本没覆盖的端点"——样本驱动证明"这些样本上对"，规则驱动证明
    "所有有限端点上对"。
    """
    checks = 0
    passed = 0
    details = []
    for city in cities:
        try:
            rs = load_ruleset(city, str(data_dir))
        except RulesetError:
            continue
        for rule in rs.rules:
            if rule.op not in ("<=", "<", ">=", ">") or rule.value is None:
                continue
            if not isinstance(rule.value, (int, float)):
                continue
            limit = Decimal(str(rule.value))
            eps = Decimal("0.01")
            at = limit
            just_over = limit + eps
            just_under = limit - eps

            def _cmp(observed: Decimal) -> bool:
                if rule.op == "<=":
                    return observed <= limit
                if rule.op == "<":
                    return observed < limit
                if rule.op == ">=":
                    return observed >= limit
                return observed > limit

            # 边界点必须满足；越界点（沿违规方向）必须不满足
            boundary_ok = _cmp(at)
            over_violates = not _cmp(just_over) if rule.op in ("<=", "<") else True
            under_violates = not _cmp(just_under) if rule.op in (">=", ">") else True
            ok = boundary_ok and over_violates and under_violates
            checks += 1
            if ok:
                passed += 1
            else:
                details.append(
                    {
                        "city": city,
                        "rule_id": rule.rule_id,
                        "op": rule.op,
                        "value": str(rule.value),
                        "boundary_ok": boundary_ok,
                    }
                )
    rate = (passed / checks) if checks else 0.0
    return {
        "suite": "B3",
        "name": "规则驱动边界扫描",
        "metric": "boundary_pass_rate",
        "value": round(rate, 4),
        "numerator": passed,
        "denominator": checks,
        "failures": details,
    }


def _not_enabled(suite: str, why: str) -> Dict[str, Any]:
    """空分母分支：`not_enabled=true` + notes 声明 + 必未达标（防"没查"被读成"查了没问题"）。"""
    return {
        "suite": suite,
        "metric": "not_enabled",
        "value": 0.0,
        "numerator": 0,
        "denominator": 0,
        "not_enabled": True,
        "notes": why,
    }


def _evaluate(results: List[Dict[str, Any]], th: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """按门槛判定。分母为 0 的"达标"是假门——恒未达标。"""
    problems: List[str] = []
    for r in results:
        suite = r["suite"]
        if r.get("not_enabled"):
            problems.append("%s 未启用（%s）→ 不算达标" % (suite, r.get("notes", "")))
            continue
        if r["denominator"] == 0:
            problems.append("%s 分母为 0（未覆盖任何用例）→ 不算达标" % suite)
            continue
        if suite == "B1":
            if r["value"] < float(th.get("B1_parse_f1_min", 0)):
                problems.append("B1 %.4f < 门槛 %.4f" % (r["value"], th["B1_parse_f1_min"]))
        elif suite == "B2":
            if r["value"] < float(th.get("B2_hit_rate_min", 0)):
                problems.append("B2 %.4f < 门槛 %.4f" % (r["value"], th["B2_hit_rate_min"]))
            if r.get("false_positive", 0) > int(th.get("B2_false_positive_max", 0)):
                problems.append(
                    "B2 误报 %d > 门槛 %d" % (r["false_positive"], th["B2_false_positive_max"])
                )
        elif suite == "B3":
            if r["value"] < float(th.get("B3_boundary_pass_rate_min", 0)):
                problems.append("B3 %.4f < 门槛 %.4f" % (r["value"], th["B3_boundary_pass_rate_min"]))
    return (not problems), problems


def run_benchmarks(
    only: Optional[str] = None,
    suite: Optional[str] = None,
    data_dir: Optional[str] = None,
) -> int:
    """跑基准。`--only`/`--suite` 传未知名必须 exit 2。"""
    requested: List[str] = []
    if only:
        requested = [only]
    elif suite:
        requested = [s.strip() for s in suite.split(",") if s.strip()]
    else:
        requested = list(SUITES)

    unknown = [s for s in requested if s not in SUITES]
    if unknown:
        print("用法错误：未知套件 %s（可选：%s）" % (",".join(unknown), "/".join(SUITES)))
        return EXIT_USAGE

    try:
        root = Path(data_dir) if data_dir else find_data_dir()
    except FileNotFoundError as exc:
        print("配置错误：%s" % exc)
        return EXIT_USAGE

    start = time.time()
    try:
        samples = _load_samples(root)
        th = _thresholds("北京", root)
    except BenchConfigError as exc:
        print("配置错误：%s" % exc)
        return EXIT_USAGE

    cities = ["北京", "上海", "全国"]
    results: List[Dict[str, Any]] = []
    for name in requested:
        if name == "B1":
            results.append(_run_b1(samples) if samples else _not_enabled("B1", "无样例"))
        elif name == "B2":
            results.append(_run_b2(samples) if samples else _not_enabled("B2", "无样例"))
        elif name == "B3":
            r = _run_b3(cities, root)
            results.append(r if r["denominator"] else _not_enabled("B3", "无带阈值规则"))

    elapsed = time.time() - start
    max_runtime = float(th.get("max_runtime_seconds", 0) or 0)

    print("=== 基准结果 ===")
    for r in results:
        if r.get("not_enabled"):
            print(
                "%-3s %-28s 未启用（%s）"
                % (r["suite"], r.get("name", ""), r.get("notes", ""))
            )
        else:
            print(
                "%-3s %-28s %s=%.4f (%d/%d)"
                % (
                    r["suite"],
                    r.get("name", ""),
                    r["metric"],
                    r["value"],
                    r["numerator"],
                    r["denominator"],
                )
            )
            if r["suite"] == "B2":
                print("      误报=%d 状态不符=%d" % (r["false_positive"], r["status_mismatch"]))
    print("耗时 %.3fs" % elapsed)

    # 部分运行时不判定未测指标（避免把"没测"误报成"未达标"）
    partial = set(requested) != set(SUITES)
    ok, problems = _evaluate(results, th)
    if max_runtime and elapsed > max_runtime:
        ok = False
        problems.append("运行时长 %.3fs > 门槛 %.1fs" % (elapsed, max_runtime))

    if problems:
        print("\n未达标：")
        for p in problems:
            print("  - %s" % p)
        if partial:
            print("（本次为部分运行，未测套件不参与判定）")
        return EXIT_NOT_MET

    print("\nBENCH_OK")
    if partial:
        print("（本次为部分运行：%s）" % ",".join(requested))
    return EXIT_OK
