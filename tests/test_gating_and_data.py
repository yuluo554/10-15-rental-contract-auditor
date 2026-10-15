"""门控与数据纪律测试（plan/02 §4，K1–K8）。

覆盖：
- 双重门控：数值 status 拦门、clause_status 不拦门
- 门控按作用域
- 规则包/样例的"未挂原文不得落库"（quote 逐字出现在快照）
- 门槛随规则包下发（数据非代码）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rca.engine.ruleset import (
    RulesetError,
    effective_ruleset,
    load_ruleset,
)
from rca.paths import find_data_dir

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_all_rules_have_clause_and_quote():
    """"未挂原文核对不得落库"——规则包每条必须有条款号与法条原文。"""
    for city in ("北京", "上海", "全国"):
        rs = load_ruleset(city, str(DATA))
        for r in rs.rules:
            assert r.clause, "%s 缺条款号" % r.rule_id
            assert r.quote, "%s 缺法条原文" % r.rule_id
            assert r.source_id, "%s 缺来源" % r.rule_id


def test_quotes_appear_verbatim_in_snapshots():
    """**机器化逐字比对**：每条 quote 必须逐字出现在对应官方快照中。"""
    manifest = json.loads((DATA / "knowledge" / "MANIFEST.json").read_text(encoding="utf-8"))
    snap_by_id = {s["source_id"]: s["snapshot"] for s in manifest["sources"]}
    texts = {}
    for sid, rel in snap_by_id.items():
        texts[sid] = (ROOT / rel).read_text(encoding="utf-8")

    checked = 0
    for city in ("北京", "上海", "全国"):
        rs = load_ruleset(city, str(DATA))
        for r in rs.rules:
            snap_text = texts[r.source_id]
            assert r.quote in snap_text, (
                "规则 %s 的 quote 未在快照 %s 中逐字出现" % (r.rule_id, snap_by_id[r.source_id])
            )
            checked += 1
    assert checked >= 10, "逐字比对覆盖面过小（%d 条）" % checked


def test_clause_numbers_derived_from_snapshot():
    """条款号必须能在快照中定位（不是手抄）。"""
    manifest = json.loads((DATA / "knowledge" / "MANIFEST.json").read_text(encoding="utf-8"))
    snap_by_id = {s["source_id"]: s["snapshot"] for s in manifest["sources"]}
    for city in ("北京", "上海", "全国"):
        rs = load_ruleset(city, str(DATA))
        for r in rs.rules:
            text = (ROOT / snap_by_id[r.source_id]).read_text(encoding="utf-8")
            assert r.clause in text, "%s 的条款号 %s 不在快照中" % (r.rule_id, r.clause)


def test_pending_rule_is_gated_out(tmp_path):
    """数值 status != verified 的条目必须被门控拦下（绝不进判定路径）。"""
    src = json.loads((DATA / "rules" / "ruleset-bj.json").read_text(encoding="utf-8"))
    src["rules"][0]["status"] = "pending"
    (tmp_path / "rules").mkdir(parents=True)
    (tmp_path / "rules" / "ruleset-bj.json").write_text(
        json.dumps(src, ensure_ascii=False), encoding="utf-8"
    )
    rs = effective_ruleset("北京", "calc", str(tmp_path))
    ids = [r.rule_id for r in rs.rules]
    assert src["rules"][0]["rule_id"] not in ids, "pending 条目不得进判定路径"
    assert any(d["rule_id"] == src["rules"][0]["rule_id"] for d in rs.disabled_rules)


def test_clause_status_does_not_gate(tmp_path):
    """条款号核对状态 pending **不阻断**判定（双重门控拆分）。"""
    src = json.loads((DATA / "rules" / "ruleset-bj.json").read_text(encoding="utf-8"))
    rid = src["rules"][0]["rule_id"]
    src["rules"][0]["clause_status"] = "pending"
    (tmp_path / "rules").mkdir(parents=True)
    (tmp_path / "rules" / "ruleset-bj.json").write_text(
        json.dumps(src, ensure_ascii=False), encoding="utf-8"
    )
    rs = effective_ruleset("北京", "calc", str(tmp_path))
    assert rid in [r.rule_id for r in rs.rules], "条款号 pending 不得阻断判定"


def test_scope_filters_judgment_path():
    """quota 类不进判定路径，但以 reference_rules 呈现。"""
    rs = effective_ruleset("北京", "calc", str(DATA))
    assert all(r.scope in ("calc", "check") for r in rs.rules)
    assert any(r.scope == "quota" for r in rs.reference_rules)


def test_unknown_scope_raises():
    with pytest.raises(RulesetError):
        effective_ruleset("北京", "nope", str(DATA))


def test_unknown_city_raises():
    with pytest.raises(RulesetError):
        load_ruleset("广州", str(DATA))


def test_thresholds_come_from_ruleset():
    """门槛是数据不是代码：必须能在规则包里读到。"""
    rs = load_ruleset("北京", str(DATA))
    assert rs.thresholds
    for key in ("B1_parse_f1_min", "B2_hit_rate_min", "B3_boundary_pass_rate_min"):
        assert key in rs.thresholds, "门槛缺 %s" % key


def test_national_layer_merged_into_city():
    """城市包叠加全国层（民法典规则对任何城市都适用）。"""
    rs = effective_ruleset("北京", "calc", str(DATA))
    ids = {r.rule_id for r in rs.rules}
    assert any(i.startswith("CN-") for i in ids), "全国层规则未叠加"
    assert any(i.startswith("BJ-") for i in ids), "城市层规则缺失"


def test_coverage_registered_with_totals():
    """覆盖声明必须登记**总数**（分子/分母双登记，防假覆盖）。"""
    rs = load_ruleset("北京", str(DATA))
    cov = rs.manifest_coverage
    assert cov.get("rule_total", 0) > 0
    assert cov.get("rule_totals_by_check_type"), "逐形态总数必须登记"


def test_available_cities(data_dir):
    from rca.engine.ruleset import available_cities

    cities = available_cities(data_dir)
    assert set(cities) >= {"北京", "上海", "全国"}


def test_data_dir_locatable():
    d = find_data_dir()
    assert (d / "rules").is_dir()
