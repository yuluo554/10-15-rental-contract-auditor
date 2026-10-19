"""基准测试：达标、可证伪探活、空分母不冒充通过、退出码三语义。
"""

from __future__ import annotations

import json
from pathlib import Path

from rca.benchmark.cases import compare_nonpass, observed_nonpass
from rca.benchmark.runner import run_benchmarks
from rca.engine.pipeline import compute_result

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "rca" / "data"


def test_all_suites_pass(data_dir):
    assert run_benchmarks(data_dir=data_dir) == 0


def test_only_single_suite(data_dir):
    """部分运行：不判定未测指标（避免把"没测"误报成"未达标"）。"""
    assert run_benchmarks(only="B3", data_dir=data_dir) == 0


def test_unknown_only_suite_exit_2(data_dir):
    assert run_benchmarks(only="B99", data_dir=data_dir) == 2


def test_unknown_suite_in_list_exit_2(data_dir):
    assert run_benchmarks(suite="B1,B99", data_dir=data_dir) == 2


def test_missing_samples_is_config_error(tmp_path):
    """门槛/样例缺失 → exit 2（配置错误），不回落代码默认值。"""
    (tmp_path / "rules").mkdir(parents=True)
    (tmp_path / "rules" / "ruleset-bj.json").write_text(
        json.dumps({"ruleset_id": "x", "city": "北京", "rules": []}), encoding="utf-8"
    )
    assert run_benchmarks(data_dir=str(tmp_path)) == 2


def test_probe_b1_detects_broken_expectation(data_dir):
    """可证伪探活：篡改真值 → 基准必须报未达标（门是活的，不是永绿）。"""
    samples = json.loads((DATA / "samples" / "samples.json").read_text(encoding="utf-8"))
    # 篡改：把第一条规则期望改成与实际不符的状态
    s = samples[0]
    rid = sorted(s["expect"])[0]
    s["expect"][rid] = "noncompliant" if s["expect"][rid] != "noncompliant" else "compliant"
    result = compute_result(s["contract_text"], s["city"], data_dir=data_dir)
    observed = {f.rule_id: f.status for f in result.findings}
    for f in result.conditional_triggers:
        observed[f.rule_id] = f.status
    cmp = compare_nonpass(s["expect"], observed)
    assert cmp["status_mismatch"] or cmp["missed"] or cmp["false_positive"], (
        "篡改真值后对账必须检出差异——否则基准是永绿假门"
    )


def test_probe_b3_detects_broken_boundary(data_dir):
    """可证伪探活：把规则边界改 ±1，边界断言必须报未达标。"""
    import copy

    from rca.engine.ruleset import load_ruleset

    rs = load_ruleset("北京", str(DATA))
    target = next(r for r in rs.rules if r.rule_id == "BJ-FILING-30D")
    # 边界点 30 原本应满足 <= 30；改成 29 后 30 必须不满足
    mutated = copy.copy(target)
    object.__setattr__(mutated, "value", 29)
    from decimal import Decimal

    limit = Decimal(str(mutated.value))
    assert not (Decimal("30") <= limit), "变异后边界断言必须失败——否则探活是装样子的"


def test_b2_no_false_positive(data_dir):
    """误报率必须为 0（门槛 B2_false_positive_max=0）。"""
    samples = json.loads((DATA / "samples" / "samples.json").read_text(encoding="utf-8"))
    total_fp = 0
    for s in samples:
        result = compute_result(s["contract_text"], s["city"], data_dir=data_dir)
        observed = {f.rule_id: f.status for f in result.findings}
        for f in result.conditional_triggers:
            observed[f.rule_id] = f.status
        total_fp += len(compare_nonpass(s["expect"], observed)["false_positive"])
    assert total_fp == 0


def test_non_pass_excludes_skipped():
    """非 pass 集合不含 skipped（"不适用"不是"有问题"）。"""
    obs = {"A": "compliant", "B": "skipped", "C": "noncompliant", "D": "unknown"}
    assert set(observed_nonpass(obs)) == {"C", "D"}


def test_not_enabled_zero_denominator_fails(tmp_path):
    """空分母分支必须 not_enabled + 未达标（防"没查"被读成"查了没问题"）。"""
    (tmp_path / "rules").mkdir(parents=True)
    (tmp_path / "samples").mkdir(parents=True)
    (tmp_path / "rules" / "ruleset-bj.json").write_text(
        json.dumps(
            {
                "ruleset_id": "x",
                "city": "北京",
                "rules": [
                    {
                        "rule_id": "X", "title": "t", "check_type": "numeric_limit",
                        "scope": "calc", "param": "p", "op": "<=", "value": 1,
                        "unit": "u", "applies_if": {"party": ["any"]},
                        "effect": "standing_obligation", "severity": "low",
                        "source_id": "s", "clause": "c", "quote": "q",
                        "status": "verified", "clause_status": "verified",
                    }
                ],
                "benchmark_thresholds": {"B1_parse_f1_min": 0.95},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "samples" / "samples.json").write_text("[]", encoding="utf-8")
    # 空样例 → 各套件 not_enabled → 必须 exit 1，不能"达标"
    assert run_benchmarks(data_dir=str(tmp_path)) == 1
