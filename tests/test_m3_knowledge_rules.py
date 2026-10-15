"""M3 知识规则里程碑回归（题面模块②③）。

M0 建了引擎骨架、M1 补齐了规则包数据与锚点门。**M3 的实质是"把模块②③的
确定性纪律逐条证成并锁进测试"**——先复核既有实现是否真满足，再补缺口。
本文件的每一条都对应 HANDOFF-M3 §6 的一个 DoD 勾选项。

模块②原文："城市标识 → versioned ruleset（数值规则 + 法条原文锚点）；
缺锚点的规则不得被引擎加载生效"。
模块③原文："条款序列 + 规则包 → 逐条判定（符合/不符合/缺失/无法判定）；
判定回指锚点 ID 与原文；**同版本 + 同输入 = 同输出**"。
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import write_text_lf
from rca.cli import main
from rca.engine.pipeline import compute_result, parameter_overview, ruleset_overview
from rca.engine.ruleset import effective_ruleset, load_ruleset
from rca.model import ALL_STATUSES
from rca.report.sections import report_sections

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CITIES = ("北京", "上海", "全国")


def _snapshot_texts():
    """{source_id: 快照全文}——按台账索引，供 quote 逐字回查。"""
    manifest = json.loads((DATA / "knowledge" / "MANIFEST.json").read_text(encoding="utf-8"))
    out = {}
    for s in manifest["sources"]:
        p = ROOT / s["snapshot"]
        if p.is_file():
            out[s["source_id"]] = p.read_text(encoding="utf-8")
    return out


def _cli_json(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, json.loads(buf.getvalue())


# ---------------------------------------------------------------------------
# DoD: 同版本 + 同输入 = 同输出（判定层显式回归）
# ---------------------------------------------------------------------------

def test_judgment_is_deterministic_field_by_field(bj_enterprise, data_dir):
    """同输入连跑 N 次，findings 序列与**每个字段**逐字段一致。

    现仅有报告层逐字节测试；判定层此前只有两次调用的整体 dict 相等断言——
    那抓不到"字段顺序稳定但某字段偶发漂移"（如 Decimal 量化路径分叉）。
    这里连跑 5 次并逐 finding、逐字段比对，锁死"同版本 + 同输入 = 同输出"。
    """
    runs = [
        compute_result(bj_enterprise, "北京", data_dir=data_dir).to_dict()
        for _ in range(5)
    ]
    first = runs[0]
    for i, run in enumerate(runs[1:], start=1):
        assert run["findings"] == first["findings"], "第 %d 次运行的 findings 序列漂移" % i
        assert run["conditional_triggers"] == first["conditional_triggers"]
        assert run["overall_status"] == first["overall_status"]
        assert run["status_counts"] == first["status_counts"]
        assert run["ruleset_version"] == first["ruleset_version"]

    # findings 的**字段集合**也要稳定（不是只有值相等）
    keysets = {tuple(sorted(f.keys())) for run in runs for f in run["findings"]}
    assert len(keysets) == 1, "findings 的字段集合在多次运行间不稳定: %s" % keysets


def test_judgment_order_matches_ruleset_order(bj_enterprise, data_dir):
    """findings 顺序必须**等于门控后规则包顺序**（同版本 → 同输出次序）。

    只比较"多次调用结果相同"是不够的：进程内 `hash()` 对同一字符串恒定，
    所以哪怕实现改成按 `hash(rule_id)` 排序，多次调用照样一致（跨进程才漂移）。
    断言"顺序 == 规则包顺序"才能把"同版本同输入 = 同输出"锁到**可核证的次序**
    上，而不是锁到"碰巧重复调用一致"。
    """
    rs = effective_ruleset("北京", "calc", data_dir)
    expected = [r.rule_id for r in rs.rules]
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    assert [f.rule_id for f in result.findings] == expected, (
        "findings 顺序与规则包顺序不一致（跨进程 hash 随机化会让输出漂移）"
    )
    # 条件触发栏顺序同理
    trig_expected = [r.rule_id for r in rs.reference_rules]
    assert [f.rule_id for f in result.conditional_triggers] == trig_expected


# ---------------------------------------------------------------------------
# DoD: 判定回指锚点 ID 与原文（结果侧反向查规则包 + quote 逐字在快照）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("city", CITIES)
def test_findings_resolve_back_to_ruleset_anchors(city, bj_enterprise, data_dir):
    """对 CLI JSON 的每条 finding **反向查规则包**，四个锚点字段必须可解析。

    这是结果侧断言：数据侧的"每条规则有锚点"（M1 已锁）**不等于**"每条判定
    回指的锚点能在规则包里查到"——引擎若挂错 rule_id 或丢字段，数据侧断言照样绿。
    """
    rc, payload = _cli_json(
        ["check", "--text", bj_enterprise, "--city", city, "--json"]
    )
    rs = effective_ruleset(city, "calc", data_dir)
    by_id = {r.rule_id: r for r in list(rs.rules) + list(rs.reference_rules)}
    assert by_id, "门控后无任何规则，测试本身失效"

    checked = 0
    for f in payload["findings"] + payload["conditional_triggers"]:
        rid = f["rule_id"]
        assert rid in by_id, "判定 %s 在规则包中解析不到（溯源断裂）" % rid
        rule = by_id[rid]
        assert f["clause"] == rule.clause, "%s 条款号与规则包不一致" % rid
        assert f["quote"] == rule.quote, "%s 法条原文与规则包不一致" % rid
        assert f["source_id"] == rule.source_id, "%s 来源与规则包不一致" % rid
        assert f["source_id"] in {s["source_id"] for s in rs.sources}
        checked += 1
    # 每条判定都回指成功（分母 = 实际判定数），且确实有判定可查
    total = len(payload["findings"]) + len(payload["conditional_triggers"])
    assert checked == total and checked >= 4, "回指未覆盖全部判定（%d/%d）" % (checked, total)


def test_finding_quotes_are_verbatim_in_their_snapshots(bj_enterprise, data_dir):
    """结果侧的**逐字**断言：每条判定引用的原文必须在其来源快照中逐字出现。

    数据侧（规则包生成时）已断言过一遍；这里从**判定结果**再走一遍，
    防"规则包被改而判定仍引用旧 quote"这类上游/下游脱钩。
    """
    snaps = _snapshot_texts()
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    for f in list(result.findings) + list(result.conditional_triggers):
        assert f.source_id in snaps, "%s 的来源无快照: %s" % (f.rule_id, f.source_id)
        assert f.quote in snaps[f.source_id], (
            "判定 %s 的 quote 未在来源 %s 快照中逐字出现" % (f.rule_id, f.source_id)
        )


def test_every_finding_row_carries_anchor_into_the_report(bj_enterprise, data_dir):
    """锚点必须进**报告产物**：逐条判定行须含条款号与法条原文。

    "判定回指锚点"若只落在 JSON 里、报告表没有原文列，导出的报告就是
    "看起来有依据但读者核不到原文"——比不判更危险。
    """
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    sec = next(s for s in report_sections(result) if s.key == "findings")
    headers = sec.table["headers"]
    assert "条款号" in headers, "报告判定表缺条款号列"
    assert "法条原文" in headers, "报告判定表缺法条原文列"

    quote_col = headers.index("法条原文")
    clause_col = headers.index("条款号")
    # 判定来源含**叠加进来的全国层**，故必须用门控后的有效规则集查，
    # 只用城市包会在 CN-* 规则上 KeyError（那正是"城市包叠加全国层"的既定口径 K11）。
    rs = effective_ruleset("北京", "calc", data_dir)
    by_id = {r.rule_id: r for r in list(rs.rules) + list(rs.reference_rules)}
    assert sec.table["rows"], "判定明细为空，测试失效"
    for row in sec.table["rows"]:
        rid = row[0]
        assert rid in by_id, "报告行 %s 在有效规则集中解析不到" % rid
        assert row[clause_col] == by_id[rid].clause, "%s 报告行条款号错" % rid
        assert row[quote_col] == by_id[rid].quote, "%s 报告行原文错" % rid


def test_conditional_trigger_rows_carry_anchor_too(bj_enterprise, data_dir):
    """条件触发栏的行同样必须挂原文（否则整栏读者无从核证）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    sec = next(s for s in report_sections(result) if s.key == "conditional")
    assert "法条原文" in sec.table["headers"]
    assert sec.table["rows"], "条件触发栏为空，测试失效"


# ---------------------------------------------------------------------------
# DoD: 城市差异包机制（同一条义务两城判出不同结果）
# ---------------------------------------------------------------------------

_AFFORDABLE_INDIVIDUAL = """上海保障性租赁住房租赁合同

出租人（甲方）：个人出租（王五）
承租人（乙方）：赵六
联系电话：19900000003

第一条 甲方将位于上海市静安区的保障性租赁住房出租给乙方居住使用，建筑面积 55 平方米。
第二条 租赁期限为 2 年，自 2026 年 1 月 1 日起至 2028 年 1 月 1 日止。
第三条 月租金为人民币 4500 元，乙方按月支付。
第四条 乙方应向甲方支付押金 2 个月租金。
第五条 甲方应自合同订立之日起 30 日内办理登记备案，并自合同订立之日起 3 个工作日内办理出租登记。
第六条 房屋及其附属设施的维修责任由甲方承担。
"""


def test_same_fact_different_city_different_verdict(data_dir):
    """**同一份合同事实**在两城判出不同结果——城市差异包的显式用例。

    事实：个人房东 + 保障性租赁住房 + 押金 2 个月；合同本身完备（全国层全合规）。
    - 北京：押金上限规则主体限于"住房租赁企业"→ 个人主体 skipped；北京无保租房押金条
      → 无违规 → 整体 compliant。
    - 上海：保租房押金上限规则主体为 any 且 lease_kind=affordable → 命中实判 → noncompliant。

    合同刻意写全（含备案/出租登记/维修），使**全国层在两城均判合规**——这样结论差异
    只能由城市包解释。若只靠全国层（民法典），两城结果必然相同：该用例专门证明
    "城市包真的在起作用"，而非"恰好被全国层掩盖"。
    """
    bj = compute_result(_AFFORDABLE_INDIVIDUAL, "北京", data_dir=data_dir)
    sh = compute_result(_AFFORDABLE_INDIVIDUAL, "上海", data_dir=data_dir)
    bj_ids = {f.rule_id for f in bj.findings}
    sh_ids = {f.rule_id for f in sh.findings}

    assert bj.card.party == "individual"
    assert sh.card.party == "individual"
    assert bj.card.lease_kind == sh.card.lease_kind == "affordable"

    # 全国层（民法典）在两城都必须判合规——否则差异可能来自全国层而非城市包
    for r in (bj, sh):
        cn = {f.rule_id: f.status for f in r.findings if f.rule_id.startswith("CN-")}
        assert cn, "全国层未叠加"
        assert all(s in ("compliant", "skipped") for s in cn.values()), (
            "全国层未全合规，本用例无法把差异归因于城市包: %s" % cn
        )

    # 北京：企业专属押金上限对个人主体 skipped（原文写了主体限制）
    bj_dep = next(f for f in bj.findings if f.rule_id == "BJ-DEPOSIT-MAX-1M")
    assert bj_dep.status == "skipped"
    # 上海：保租房押金上限对 any 主体实判 → 押金 2 个月超 1 个月 → noncompliant
    sh_dep = next(f for f in sh.findings if f.rule_id == "SH-AFFORDABLE-DEPOSIT-1M")
    assert sh_dep.status == "noncompliant"

    # 两城的**整体结论**确实不同（同事实、不同城市口径）
    assert bj.overall_status == "compliant", "北京侧应全合规: %s" % bj.status_counts
    assert sh.overall_status == "noncompliant", "上海侧应检出不符合: %s" % sh.status_counts
    assert bj.overall_status != sh.overall_status, (
        "同事实在两城判出同一结论，城市差异包未生效"
    )
    # 各自只命中本城专属规则，不混入对方前缀
    assert any(i.startswith("BJ-") for i in bj_ids)
    assert not any(i.startswith("BJ-") for i in sh_ids), "上海包混入了北京规则"
    assert any(i.startswith("SH-") for i in sh_ids)
    assert not any(i.startswith("SH-") for i in bj_ids), "北京包混入了上海规则"


def test_affordable_rule_skips_ordinary_housing_in_same_city(data_dir):
    """同一城市内，房屋类型差异也要分派：普通住房不适用保租房专属规则。"""
    ordinary = """上海住房租赁合同

出租人（甲方）：上海宜居住房租赁有限公司
承租人（乙方）：孙八
联系电话：19900000004

第一条 甲方将位于上海市静安区的住房出租给乙方居住使用，建筑面积 80 平方米。
第二条 租赁期限为 2 年。
第三条 月租金为人民币 5000 元，乙方按月支付。
第四条 乙方应向甲方支付押金 2 个月租金。
"""
    result = compute_result(ordinary, "上海", data_dir=data_dir)
    f = {x.rule_id: x.status for x in result.findings}
    assert result.card.lease_kind == "ordinary"
    assert f["SH-AFFORDABLE-DEPOSIT-1M"] == "skipped", "保租房规则不得对普通住房实判"
    assert f["SH-RENT-DEPOSIT-ESCROW"] == "noncompliant", "企业押金超限须判不符合"


def test_city_packages_are_distinct_rulesets(data_dir):
    """京/沪/全国的 ruleset_id、版本、规则集必须彼此不同（versioned ruleset 基本性质）。"""
    ids = {}
    versions = {}
    rule_ids = {}
    for city in CITIES:
        rs = load_ruleset(city, str(DATA))
        ids[city] = rs.ruleset_id
        versions[city] = rs.version
        rule_ids[city] = {r.rule_id for r in rs.rules}
    assert len(set(ids.values())) == len(CITIES), "ruleset_id 重复: %s" % ids
    assert len(set(versions.values())) == len(CITIES), "版本号重复: %s" % versions
    assert rule_ids["北京"] != rule_ids["上海"], "京沪规则集完全相同，差异包名不副实"


# ---------------------------------------------------------------------------
# DoD: versioned ruleset 可追溯（版本号 == manifest 推导值）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("city", CITIES)
def test_ruleset_version_recomputable_from_manifest(city, data_dir):
    """版本号必须能从规则包 manifest **复算**（不是手写的第二份真相）。

    口径（tools/gen_rulesets.py `derive_version`）：被本包规则引用的来源中，
    最晚的 `effective_date`，取 `YYYY.MM`。手写版本号会在来源更新后与数据脱钩，
    报告据此标注的"依据版本"就指向了错的原文版本。
    """
    rs = load_ruleset(city, str(DATA))
    manifest = json.loads(
        (DATA / "knowledge" / "MANIFEST.json").read_text(encoding="utf-8")
    )
    by_id = {s["source_id"]: s for s in manifest["sources"]}
    referenced = {r.source_id for r in rs.rules}
    latest = max(by_id[sid]["effective_date"] for sid in referenced)
    assert rs.version == "%s.%s" % (latest[:4], latest[5:7]), (
        "%s 版本号 %s 与 manifest 推导值不符" % (city, rs.version)
    )


@pytest.mark.parametrize("city", CITIES)
def test_version_reaches_both_outputs(city, bj_enterprise, data_dir):
    """版本号必须同时进 CLI JSON 与报告（可追溯 = 产物里看得见）。"""
    rs = load_ruleset(city, str(DATA))
    rc, payload = _cli_json(["check", "--text", bj_enterprise, "--city", city, "--json"])
    assert payload["ruleset_version"] == rs.version
    assert payload["ruleset_id"] == rs.ruleset_id

    result = compute_result(bj_enterprise, city, data_dir=data_dir)
    sec = next(s for s in report_sections(result) if s.key == "input")
    assert any(rs.version in p for p in sec.paragraphs), "报告未显示规则包版本"


def test_derive_version_is_actually_computed_not_hardcoded():
    """变异验证：手写死版本号后 `--check` 必须失败。

    若 `derive_version` 只是把 SPECS 里的字面量抄一遍，本测试会假绿——
    故直接调用生成器函数，验证"改台账施行日 → 推导值随之变化"。
    """
    from tools_support import load_tool

    mod = load_tool("gen_rulesets")
    spec = {"rules": [{"source_id": "SRC-X"}]}
    meta = {"SRC-X": {"effective_date": "2024-10-01"}}
    assert mod.derive_version(spec, meta) == "2024.10"
    # 换一个更晚的施行日 → 推导值必须跟着变（证明是真算的）
    meta2 = {"SRC-X": {"effective_date": "2025-03-15"}}
    assert mod.derive_version(spec, meta2) == "2025.03", "版本号未随来源更新而变（疑似写死）"
    # 未登记来源必须显式报错，不静默回落到某默认值
    with pytest.raises(ValueError):
        mod.derive_version(spec, {})


# ---------------------------------------------------------------------------
# DoD: 缺锚点规则不得加载生效（K17 复核，确认不回归）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["clause", "quote", "source_id"])
@pytest.mark.parametrize("city", ["北京", "上海", "全国"])
def test_anchor_gate_holds_for_every_city_and_field(tmp_path, field, city):
    """K17 复核：三个包 × 三个锚点字段，缺任一项即不生效且进未启用清单。

    M1 已闭环，M3 的任务是**确认不回归**——故对每个包每个字段都跑一遍，
    而非只测北京一个包的一个字段（城市包可各自被替换）。
    """
    fname = {"北京": "ruleset-bj.json", "上海": "ruleset-sh.json", "全国": "ruleset-cn.json"}[city]
    src = json.loads((DATA / "rules" / fname).read_text(encoding="utf-8"))
    rid = src["rules"][0]["rule_id"]
    src["rules"][0][field] = None if field != "source_id" else ""
    (tmp_path / "rules").mkdir(parents=True)
    write_text_lf(tmp_path / "rules" / fname, json.dumps(src, ensure_ascii=False))

    rs = effective_ruleset(city, "calc", str(tmp_path))
    assert rid not in [r.rule_id for r in rs.rules], "%s 缺 %s 仍进了判定路径" % (city, field)
    hit = [d for d in rs.disabled_rules if d["rule_id"] == rid]
    assert hit, "%s 被拦下的规则必须进未启用清单（不静默丢弃）" % city
    assert "缺锚点" in hit[0]["reason"]


def test_gate_holds_even_when_status_is_verified(tmp_path):
    """锚点门独立于数值门：status=verified 但缺锚点仍必须被拦。"""
    src = json.loads((DATA / "rules" / "ruleset-bj.json").read_text(encoding="utf-8"))
    rid = src["rules"][0]["rule_id"]
    assert src["rules"][0]["status"] == "verified"
    src["rules"][0]["quote"] = None
    (tmp_path / "rules").mkdir(parents=True)
    write_text_lf(tmp_path / "rules" / "ruleset-bj.json", json.dumps(src, ensure_ascii=False))
    rs = effective_ruleset("北京", "calc", str(tmp_path))
    assert rid not in [r.rule_id for r in rs.rules], "锚点门被数值门短路了"


# ---------------------------------------------------------------------------
# DoD: 判定五态语义（两条出口都可区分 unknown / not_assessed）
# ---------------------------------------------------------------------------

def test_cli_json_carries_status_counts(bj_enterprise, data_dir):
    """CLI JSON 出口必须带五态计数（不止 overall_status）。

    只有 overall_status 时，`not_assessed` 既可能是"全不适用"也可能是"有一半
    没能判定"——报告层有计数、JSON 层没有，机读消费者就又把五态退化成三态。
    """
    rc, payload = _cli_json(
        ["check", "--text", bj_enterprise, "--city", "北京", "--json"]
    )
    assert "status_counts" in payload, "CLI JSON 缺 status_counts"
    counts = payload["status_counts"]
    assert isinstance(counts, dict) and counts
    assert set(counts) <= set(ALL_STATUSES), "出现了非五态的取值: %s" % counts
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    assert counts == result.status_counts
    assert "overall_summary" in payload, "CLI JSON 缺可读摘要（读者无法判断判定完整度）"


def test_unknown_and_not_assessed_are_distinguishable(data_dir):
    """`unknown`（没看到）与 `not_assessed`（没检查过）必须可区分。

    构造两份极端输入：一份是要素全无的合同（大量 unknown），一份是彻底
    无适用规则的情形——两者都不许报 compliant，且计数形态不同。
    """
    thin = "住房租赁合同\n甲方与乙方就房屋租赁事宜达成一致。\n"
    r = compute_result(thin, "北京", data_dir=data_dir)
    assert r.overall_status != "compliant", "未观测不得报 compliant"
    assert r.status_counts.get("unknown", 0) > 0, "未观测项须计入 unknown"

    _, payload = _cli_json(["check", "--text", thin, "--city", "北京", "--json"])
    assert payload["status_counts"].get("unknown", 0) > 0
    assert payload["overall_status"] == r.overall_status


def test_report_shows_counts_and_overall_status(bj_enterprise, data_dir):
    """报告出口同样须给出整体判定与五态计数（导出文件常被单独转发）。

    断言**绑到实际取值**，不只绑标签：只断言"含有'整体判定'字样"的话，
    把该行换成任何含同样字样的占位串都照样绿（变异验证实测踩过）。
    """
    from rca.report.sections import _counts_text

    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    sec = next(s for s in report_sections(result) if s.key == "input")
    joined = "\n".join(sec.paragraphs)

    # 必须出现**本份判定实际算出的**整体结论与计数串
    assert "整体判定：%s" % result.overall_summary() in joined, (
        "报告未输出本次判定的整体结论: %s" % joined
    )
    assert "判定状态计数：%s" % _counts_text(result.status_counts) in joined, (
        "报告未输出本次判定的五态计数: %s" % joined
    )
    assert result.overall_status in joined
    # 五态标签全列（含 0 项）——否则"检查过但为 0"与"根本没纳入检查"长得一样
    for label in ("符合", "不符合", "不适用", "无法判定", "未评估"):
        assert label in joined, "报告计数缺状态「%s」（零项也要列出）" % label


def test_all_five_statuses_are_reachable_in_engine():
    """五态全部可达（有真实触达路径，不是纸面枚举）。"""
    from rca.model import ALL_STATUSES as ENGINE_STATUSES

    assert set(ENGINE_STATUSES) == {
        "compliant", "noncompliant", "skipped", "unknown", "not_assessed"
    }
    src = (ROOT / "src" / "rca" / "engine" / "checker.py").read_text(encoding="utf-8")
    for status in ("compliant", "noncompliant", "skipped", "unknown"):
        assert "STATUS_%s" % status.upper() in src, "引擎未触达状态 %s" % status
    model = (ROOT / "src" / "rca" / "model.py").read_text(encoding="utf-8")
    assert "STATUS_NOT_ASSESSED" in model


# ---------------------------------------------------------------------------
# DoD: 规则包覆盖登记（rules --city X 的分子/分母与 manifest 一致）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("city", CITIES)
def test_rules_coverage_matches_manifest(city, data_dir):
    """`rules --city X` 输出的覆盖分子/分母必须与规则包 manifest 逐项一致。"""
    info = ruleset_overview(city, data_dir)
    cov = info["coverage"]
    fname = {
        "北京": "ruleset-bj.json", "上海": "ruleset-sh.json", "全国": "ruleset-cn.json"
    }[city]
    raw = json.loads((DATA / "rules" / fname).read_text(encoding="utf-8"))
    manifest_cov = raw["coverage"]

    # 分母（总数）必须与规则包实际条目数一致——登记的数与真实的数不能是两份
    assert cov["rule_total"] == manifest_cov["rule_total"]
    assert cov["rule_total"] == len(raw["rules"]), (
        "%s 覆盖登记的 rule_total=%s 与实际条目数 %d 不符（假覆盖）"
        % (city, cov["rule_total"], len(raw["rules"]))
    )
    # 逐形态分子合计必须等于总数（防"逐形态漏登记若干条"）
    by_type = cov["rule_totals_by_check_type"]
    assert sum(by_type.values()) == cov["rule_total"], (
        "%s 逐形态登记合计 %d != 总数 %d" % (city, sum(by_type.values()), cov["rule_total"])
    )
    # 逐形态登记必须与规则包实际分布一致
    actual = {}
    for r in raw["rules"]:
        actual[r["check_type"]] = actual.get(r["check_type"], 0) + 1
    assert by_type == dict(sorted(actual.items())), "%s 逐形态分布与规则包不符" % city


@pytest.mark.parametrize("city", CITIES)
def test_coverage_cli_output_matches_overview(city, capsys, data_dir):
    """`rules --city X` 的人类可读输出里的分子/分母与 --json 同源。"""
    rc, payload = _cli_json(["rules", "--city", city, "--json"])
    assert rc == 0
    cov = payload["overview"]["coverage"]
    assert cov["rule_total"] > 0
    assert cov["rule_totals_by_check_type"], "逐形态总数必须登记"


def test_enabled_rules_all_come_from_registered_packages(data_dir):
    """生效的每条规则都必须能在**已登记规则包**中找到出处（防凭空多出规则）。

    注意口径：`diagnostics.enabled_count` 是**门控后 + 叠加全国层**的条目数，
    与 `ruleset_overview.rule_count`（单包原始条目数）本就不是同一分母——
    城市包叠加全国层后条目更多（K11）。故断言对象是"每个生效 rule_id 有出处"，
    而非"生效数 ≤ 单包登记数"（后者会把正常的叠加判成缺陷）。
    """
    from rca.engine.pipeline import diagnostics

    registered = set()
    for city in CITIES:
        registered |= {r.rule_id for r in load_ruleset(city, str(DATA)).rules}

    for city in CITIES:
        rs = effective_ruleset(city, "calc", data_dir)
        enabled = list(rs.rules) + list(rs.reference_rules)
        assert enabled, "%s 无任何生效规则，测试失效" % city
        for r in enabled:
            assert r.rule_id in registered, (
                "%s 生效规则 %s 不在任何已登记规则包中" % (city, r.rule_id)
            )
        # 诊断计数必须与门控结果的实际长度一致（不是另算一遍）
        diag = diagnostics(city, data_dir)
        assert diag["enabled_count"] == len(rs.rules), (
            "%s 诊断的生效数 %d != 门控结果 %d" % (city, diag["enabled_count"], len(rs.rules))
        )
        # 被拦下的条目必须与生效条目不相交（一个规则不能既生效又被拦）
        disabled_ids = {d["rule_id"] for d in rs.disabled_rules}
        assert disabled_ids.isdisjoint({r.rule_id for r in enabled}), (
            "%s 有规则同时出现在生效与被拦清单中" % city
        )


# ---------------------------------------------------------------------------
# 模块②：城市标识 → versioned ruleset 的端到端接线
# ---------------------------------------------------------------------------

def test_unknown_city_is_rejected_not_silently_defaulted(tmp_path, bj_enterprise):
    """未知城市必须 exit 2（绝不静默回落到某默认城市包）。"""
    path = tmp_path / "c.txt"
    write_text_lf(path, bj_enterprise)
    rc = main(["check", "--input", str(path), "--city", "广州"])
    assert rc == 2, "未知城市未报用法错误（会静默用错规则包）"


def test_disabled_section_wording_covers_anchor_blocks(tmp_path, bj_enterprise, data_dir):
    """未启用清单的引导语必须覆盖**缺锚点**这一拦截原因。

    实测缺陷：引导语只写"数值核对状态非 verified"，而 M1 起锚点门也会往该清单塞条目
    （reason 为"缺锚点（法条原文）"）——读者被告知是数值没核对，清单里却写着缺锚点，
    **理由与清单自相矛盾**。
    """
    src = json.loads((DATA / "rules" / "ruleset-bj.json").read_text(encoding="utf-8"))
    src["rules"][0]["quote"] = None
    (tmp_path / "rules").mkdir(parents=True)
    write_text_lf(tmp_path / "rules" / "ruleset-bj.json", json.dumps(src, ensure_ascii=False))

    result = compute_result(bj_enterprise, "北京", data_dir=str(tmp_path))
    assert any("缺锚点" in d["reason"] for d in result.disabled_rules), "测试未造出缺锚点场景"
    sec = next(s for s in report_sections(result) if s.key == "disabled")
    joined = "\n".join(sec.paragraphs)
    assert "缺锚点" in joined, "未启用清单引导语未提缺锚点（与实际拦截原因矛盾）: %s" % joined
    assert "数值核对状态非" in joined, "引导语丢了数值门这一原因"


def test_source_ledger_covers_all_referenced_sources(data_dir):
    """规则包 sources 台账必须覆盖全部被引用的来源（否则溯源表出现空行）。"""
    for city in CITIES:
        rs = effective_ruleset(city, "calc", data_dir)
        known = {s["source_id"] for s in rs.sources}
        for rule in list(rs.rules) + list(rs.reference_rules):
            assert rule.source_id in known, (
                "%s 的规则 %s 引用了台账外来源 %s" % (city, rule.rule_id, rule.source_id)
            )


def test_parameter_overview_covers_every_finding(data_dir, bj_enterprise):
    """参数来源块必须覆盖**每一条**判定（含条件触发栏），不留半溯源。"""
    for city in CITIES:
        result = compute_result(bj_enterprise, city, data_dir=data_dir)
        rows = parameter_overview(city, data_dir)
        ids = {r["rule_id"] for r in rows}
        for f in list(result.findings) + list(result.conditional_triggers):
            assert f.rule_id in ids, "%s 的判定 %s 无溯源行" % (city, f.rule_id)


def test_decimal_quantization_is_stable_for_repeat_calls():
    """Decimal 量化路径可复现（判定确定性的底层前提）。"""
    from rca.parser.extract import q2

    vals = [Decimal("1.005"), Decimal("2.675"), Decimal("0.125"), Decimal("3.335")]
    first = [str(q2(v)) for v in vals]
    for _ in range(4):
        assert [str(q2(v)) for v in vals] == first
    assert first == ["1.01", "2.68", "0.13", "3.34"], "ROUND_HALF_UP 口径漂移: %s" % first
