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
DATA = ROOT / "src" / "rca" / "data"


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


def test_derive_clause_ignores_inline_cross_references():
    """条号推导只看**行首**条号，不被正文里的交叉引用劫持（实测缺陷的回归）。

    上海第六十一条的罚则正文以"违反本条例第三十七条第二款规定…"开头；
    按"任意位置回溯最近的第X条"会把该罚则错认成第三十七条——报告会把罚则挂到
    错误法条上，比漏报更危险（读者按错条号去核证会核不到）。
    """
    from tools_support import load_tool

    mod = load_tool("gen_rulesets")
    sh = (ROOT / "data" / "knowledge" / "raw" / "sh-housing-rental.txt").read_text(
        encoding="utf-8"
    )
    clause = mod.derive_clause(sh, "收取的租金或者押金不符合要求的", "SRC-SH-HOUSING-RENTAL")
    assert clause == "第六十一条", "交叉引用劫持了条号推导（得到 %s）" % clause


def test_penalty_rule_clause_is_its_own_article():
    """罚则类规则的条号必须是罚则自身所在条，而非被引用条（端到端锁死）。"""
    rs = load_ruleset("上海", str(DATA))
    assert rs.rule_by_id("SH-PENALTY-AFFORDABLE-RENT-DEPOSIT").clause == "第六十一条"
    assert rs.rule_by_id("SH-BAN-5Y-AFFORDABLE-APPLY").clause == "第五十九条"


def test_quote_asserted_against_its_own_source_snapshot():
    """每条规则的 quote 必须在其**声明的来源**快照中逐字出现。

    北京包同时引用《条例》与配套《暂行办法》两份来源；若拿规则包主快照做断言，
    配套办法的规则会被误判成"未挂原文"。本测试锁死"按 source_id 取快照"。
    """
    escrow = load_ruleset("北京", str(DATA))
    esc = (ROOT / "data" / "knowledge" / "raw" / "bj-deposit-escrow.txt").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "data" / "knowledge" / "raw" / "bj-housing-rental.txt").read_text(
        encoding="utf-8"
    )
    referenced = [r for r in escrow.rules if r.source_id == "SRC-BJ-DEPOSIT-ESCROW"]
    assert referenced, "配套办法来源必须至少被 1 条规则引用（否则台账来源是摆设）"
    for r in referenced:
        assert r.quote in esc, "%s 的 quote 不在配套办法快照中" % r.rule_id
        assert r.quote not in main, "%s 的 quote 竟然出现在《条例》快照里（来源标错）" % r.rule_id


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


@pytest.mark.parametrize("field", ["quote", "clause", "source_id"])
def test_rule_missing_anchor_is_gated_out(tmp_path, field):
    """题面模块②硬约束：**缺锚点的规则不得被引擎加载生效**。

    锚点 = 条款号 + 法条原文逐字引用 + 来源。生成器已对出厂规则做逐字断言，
    但门控不能只依赖上游（规则包可被手工替换、或由第三方扩展包提供），
    引擎必须在**加载侧**再拦一次——否则报告会给出"看起来有依据"的判定，
    读者却找不到原文核对（比不判定更危险）。
    """
    src = json.loads((DATA / "rules" / "ruleset-bj.json").read_text(encoding="utf-8"))
    rid = src["rules"][0]["rule_id"]
    src["rules"][0][field] = None if field != "source_id" else ""
    (tmp_path / "rules").mkdir(parents=True)
    (tmp_path / "rules" / "ruleset-bj.json").write_text(
        json.dumps(src, ensure_ascii=False), encoding="utf-8"
    )
    rs = effective_ruleset("北京", "calc", str(tmp_path))
    assert rid not in [r.rule_id for r in rs.rules], "缺 %s 的规则不得进判定路径" % field
    hit = [d for d in rs.disabled_rules if d["rule_id"] == rid]
    assert hit, "被拦下的缺锚点规则必须进未启用清单（显式可见，不静默丢弃）"
    assert "缺锚点" in hit[0]["reason"]


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


def test_m1_coverage_floors():
    """M1 出口判据：各包条数下限 + 配套来源被真实引用。

    下限写进测试而非只写进交接文档——否则"扩到几条"会随重构静默回退。

    口径按 DoD 原文区分：
    - 京/沪要求的是**数值规则**条数（value 非空）；
    - 全国层要求的是**规则**条数（704 要素完整性 / 721 法定补充规则本就没有
      数值阈值，按"数值规则"计数会把已就位的条款排除在外，口径写错）。
    """
    numeric_floors = {"北京": 6, "上海": 5}
    for city, floor in numeric_floors.items():
        rs = load_ruleset(city, str(DATA))
        numeric = [r for r in rs.rules if r.value is not None]
        assert len(numeric) >= floor, (
            "%s 数值规则 %d 条 < 下限 %d 条" % (city, len(numeric), floor)
        )

    cn = load_ruleset("全国", str(DATA))
    assert len(cn.rules) >= 3, "全国层规则 %d 条 < 下限 3 条" % len(cn.rules)
    # 704/705/721 是 M0 已就位的三条，M1 复核须仍在（防被误删）
    for rid in ("CN-ELEMENT-COMPLETENESS", "CN-LEASE-TERM-MAX", "CN-RENT-PAY-PERIOD"):
        assert cn.rule_by_id(rid) is not None, "全国层既有规则 %s 缺失" % rid

    # 台账登记但从未被引用的来源 = 摆设；M1 要求它至少挂 1 条规则
    bj = load_ruleset("北京", str(DATA))
    assert any(r.source_id == "SRC-BJ-DEPOSIT-ESCROW" for r in bj.rules), (
        "SRC-BJ-DEPOSIT-ESCROW 未被任何规则引用"
    )


def test_every_rule_carries_verification_status():
    """题面模块②：每条数值规则须携带查证状态（✅/⬜）。

    缺锚点（无 clause/quote）或状态非 verified 的规则**不得被引擎加载生效**——
    此处断言规则包里每条都齐备且为 verified（门控层另有 pending 拦截测试）。
    """
    for city in ("北京", "上海", "全国"):
        rs = load_ruleset(city, str(DATA))
        for r in rs.rules:
            assert r.status == "verified", "%s 数值核对状态非 verified" % r.rule_id
            assert r.clause_status == "verified", "%s 条款核对状态非 verified" % r.rule_id


def test_data_dir_locatable():
    d = find_data_dir()
    assert (d / "rules").is_dir()
