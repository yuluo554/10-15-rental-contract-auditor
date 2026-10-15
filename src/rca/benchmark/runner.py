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
from .cases import compare_exact, compare_nonpass, observed_nonpass
from .coverage import CHECK_TYPE_FORMS, coverage_gaps, sample_coverage

__all__ = ["run_benchmarks", "SUITES", "sample_coverage", "CHECK_TYPE_FORMS"]

SUITES = ("B1", "B2", "B3")

# 规则形态（check_type）全集：覆盖登记与样例覆盖检查都以此为准。
# 与规则包 manifest 的 `rule_totals_by_check_type` 键集一致。
CHECK_TYPE_FORMS = ("numeric_limit", "deadline_obligation", "element_completeness", "text_prohibition")

EXIT_OK = 0
EXIT_NOT_MET = 1
EXIT_USAGE = 2


class BenchConfigError(Exception):
    """门槛缺失/套件名未知 → exit 2。"""


def _dd(data_dir: Optional[Path]) -> Optional[str]:
    """`compute_result` 的 data_dir 形参是 str；None 表示"走默认定位"。"""
    return str(data_dir) if data_dir is not None else None


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


def _run_b1(samples: List[Dict[str, Any]], data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """解析基准：要素抽取**字段级 P / R / F1**（plan/04 §1）。

    真值来源 = 样例的 `expect_fields`（应有值的字段 → 期望取值）与
    `expect_absent_fields`（应观测不到的字段）。**与引擎完全独立**：
    期望由生成器按"合同里写了什么"推出，不调用引擎的抽取函数——
    否则引擎抽错时期望跟着一起错，探活永远绿（plan/04 §5）。

    口径：
    - TP = 真值登记应有值、引擎也观测到**且取值一致**的字段
    - FP = 真值登记应 absent、引擎却观测到了值（"无中生有"）
      ＋ 真值登记应有值、引擎观测到但**取值不同**（抽错值，比抽不到更危险）
    - FN = 真值登记应有值、引擎却观测不到（漏抽）
    - 分母不含"两边都认为该字段不存在"的字段（那种一致不构成能力证明）

    首期以"字段取值一致"为判据（不细分字符级偏移），故是字段级而非字符级 P/R。
    """
    tp = fp = fn = 0
    details = []
    for s in samples:
        result = compute_result(s["contract_text"], s["city"], data_dir=_dd(data_dir))
        card = result.card
        expect_present = s.get("expect_fields") or {}
        expect_absent = list(s.get("expect_absent_fields") or [])

        s_tp = s_fp = s_fn = 0
        for name, want in expect_present.items():
            f = card.get(name)
            if not f.observed:
                fn += 1
                s_fn += 1
                details.append({"sample_id": s["sample_id"], "field": name, "kind": "fn"})
                continue
            # 取值一致才算命中；抽到值但与真值不符 = 抽错值（记 FP + FN 都不妥，
            # 统一记 FP：它污染了 precision，也确实不是真值登记的那一项）
            if str(f.value) == str(want):
                tp += 1
                s_tp += 1
            else:
                fp += 1
                s_fp += 1
                details.append(
                    {
                        "sample_id": s["sample_id"], "field": name, "kind": "wrong_value",
                        "expected": str(want), "observed": str(f.value),
                    }
                )
        for name in expect_absent:
            f = card.get(name)
            if f.observed:
                fp += 1
                s_fp += 1
                details.append(
                    {"sample_id": s["sample_id"], "field": name, "kind": "false_positive",
                     "observed": str(f.value)}
                )

        # 有值字段必须有证据条款（防幻觉锚点）——这是**附加**约束，不进 P/R 分母，
        # 但违反即整份样例记一次 FP（值对了、证据编造，同样不可信）。
        #
        # 口径限定在**承载取值**的字段（数值/文本）。布尔"存在性"标记
        # （`has_deposit_clause` / `rent_pay_period_declared`）取 False 时断言的是
        # "文本里没有这一项"——为"不存在"索要证据条款是不可满足的要求，
        # 且这类标记的真伪由同一份文本直接决定，无幻觉空间。
        for name, f in card.fields.items():
            if name == "contract_text":
                continue
            if isinstance(f.value, bool):
                continue
            if f.observed and not (f.evidence and f.evidence.clause_text):
                fp += 1
                s_fp += 1
                details.append(
                    {"sample_id": s["sample_id"], "field": name, "kind": "no_evidence"}
                )

        details.append(
            {"sample_id": s["sample_id"], "tp": s_tp, "fp": s_fp, "fn": s_fn}
        )

    precision = (tp / (tp + fp)) if (tp + fp) else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "suite": "B1",
        "name": "解析基准（要素抽取字段级）",
        "metric": "f1",
        "value": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        # 保留 numerator/denominator 供既有门槛/打印路径使用：F1 的"分子"取 TP，
        # 分母取 TP+FP+FN（P/R 共用的基数）。F1 恒在 [0,1]，与门槛同量纲。
        "numerator": tp,
        "denominator": tp + fp + fn,
        "details": details,
    }


def _run_b2(samples: List[Dict[str, Any]], data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """端到端判定基准：植入真值**全量**对账（命中率 / 误报率）。

    分母 = `expect ∪ also_expect` 登记的**全部**规则（不是只算非 pass 集合）。
    只算非 pass 会漏掉一整类错误：真值登记 `compliant`/`skipped`/`reference`、
    观测却是别的状态时，两侧都不在非 pass 集合里，**恒不报**。
    """
    hits = missed = fp = mismatch = unregistered = 0
    per_sample = []
    for s in samples:
        result = compute_result(s["contract_text"], s["city"], data_dir=_dd(data_dir))
        observed = {f.rule_id: f.status for f in result.findings}
        for f in result.conditional_triggers:
            observed[f.rule_id] = f.status

        # 全量精确对账：expect ∪ also_expect 每条都要核（also_expect 不再是不校验的死数据）
        expected = dict(s.get("expect") or {})
        expected.update(s.get("also_expect") or {})
        exact = compare_exact(expected, observed)
        hits += len(exact["hits"])
        missed += len(exact["missed"])
        mismatch += len(exact["mismatch"])
        unregistered += len(exact["unregistered"])

        # 误报率仍按非 pass 集合口径：真值说 pass/skipped，观测却报 noncompliant/unknown
        cmp = compare_nonpass(expected, observed)
        fp += len(cmp["false_positive"])

        per_sample.append(
            {
                "sample_id": s["sample_id"],
                "hits": len(exact["hits"]),
                "missed": len(exact["missed"]),
                "mismatch": len(exact["mismatch"]),
                "unregistered": len(exact["unregistered"]),
                "false_positive": len(cmp["false_positive"]),
            }
        )

    denom = hits + missed + mismatch + unregistered
    hit_rate = (hits / denom) if denom else 0.0
    return {
        "suite": "B2",
        "name": "端到端判定基准（植入真值全量对账）",
        "metric": "hit_rate",
        "value": round(hit_rate, 4),
        "numerator": hits,
        "denominator": denom,
        "false_positive": fp,
        "status_mismatch": mismatch,
        "unregistered": unregistered,
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


def _coverage_problems(root: Path, samples: List[Dict[str, Any]]) -> List[str]:
    """样例覆盖形态检查（plan/04 §2.3 + HANDOFF-M4 DoD 第 6 条）。

    "每个 check_type 形态都有 ≥1 份采样件"是覆盖声明的**下限**：一个形态有规则
    却零采样件，说明该形态在基准里等于没测（分子为 0）——这种"达标"是假门。
    规则包 manifest 里的 `truth_sampling` 也必须与该实算一致（登记的数与真实的数
    不能是两份）。
    """
    problems: List[str] = []
    forms: Dict[str, str] = {}
    for city in ("北京", "上海", "全国"):
        try:
            rs = load_ruleset(city, str(root))
        except RulesetError:
            continue
        for r in rs.rules:
            forms[r.rule_id] = r.check_type

    gaps = coverage_gaps(forms, samples)
    if gaps:
        problems.append("样例覆盖缺口：形态 %s 有规则却零采样件（等于没测）" % ",".join(gaps))

    # 逐包核对 manifest 登记的采样数与实算一致
    for city in ("北京", "上海", "全国"):
        try:
            rs = load_ruleset(city, str(root))
        except RulesetError:
            continue
        manifest = rs.manifest_coverage or {}
        registered = manifest.get("truth_sampling")
        if not registered:
            problems.append("%s 规则包 coverage 未登记真值采样数（分子缺失=假覆盖）" % city)
            continue
        actual = sample_coverage({r.rule_id: r.check_type for r in rs.rules}, samples)
        if registered != actual:
            problems.append("%s 规则包登记的采样数与实算不一致（假覆盖）" % city)
        for form, item in actual.items():
            if item["rule_total"] and not item["sampled_rules"]:
                problems.append("%s 形态 %s 有 %d 条规则但零采样件" % (city, form, item["rule_total"]))
    return problems


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
                problems.append(
                    "B1 F1 %.4f < 门槛 %.4f（P=%.4f R=%.4f）"
                    % (r["value"], th["B1_parse_f1_min"], r["precision"], r["recall"])
                )
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
            results.append(_run_b1(samples, root) if samples else _not_enabled("B1", "无样例"))
        elif name == "B2":
            results.append(_run_b2(samples, root) if samples else _not_enabled("B2", "无样例"))
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
            if r["suite"] == "B1":
                print(
                    "      精确率=%.4f 召回率=%.4f（TP=%d FP=%d FN=%d）"
                    % (r["precision"], r["recall"], r["true_positive"],
                       r["false_positive"], r["false_negative"])
                )
            if r["suite"] == "B2":
                print(
                    "      误报=%d 状态不符=%d 未登记=%d"
                    % (r["false_positive"], r["status_mismatch"], r.get("unregistered", 0))
                )
    print("耗时 %.3fs" % elapsed)

    # 部分运行时不判定未测指标（避免把"没测"误报成"未达标"）
    partial = set(requested) != set(SUITES)
    ok, problems = _evaluate(results, th)
    # 样例覆盖形态检查**总是**参与判定（它是覆盖声明的前提，与"跑了哪几个套件"无关）：
    # 分母为 0 的"达标"是假门，分子为 0 的形态同样是假门。
    if samples:
        problems.extend(_coverage_problems(root, samples))
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
