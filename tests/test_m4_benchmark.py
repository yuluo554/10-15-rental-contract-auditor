"""M4 基准里程碑回归（题面模块⑤）。

题面模块⑤要求：合成合同样例与植入真值、三层基准。
plan/04 把口径定死为"样本驱动 + 规则驱动两层，每套件配可证伪探活，空分母不冒充通过"。

M0 建了基准骨架（三套件、门槛随规则包下发、探活、空分母分支），M1/M2 扩了样例。
**M4 的实质是"把模块⑤的评测口径逐条证成并补覆盖缺口"**——先复核既有实现是否真满足，
再补缺口。本文件每条对应 HANDOFF-M4 §7 的一个 DoD 勾选项。
"""

from __future__ import annotations

import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from conftest import write_text_lf
from rca.benchmark.cases import compare_exact
from rca.benchmark.coverage import CHECK_TYPE_FORMS, coverage_gaps, sample_coverage
from rca.benchmark.runner import _run_b1, _run_b2, run_benchmarks
from rca.engine.pipeline import compute_result, ruleset_overview
from rca.engine.ruleset import effective_ruleset, load_ruleset
from rca.report.markdown import render_markdown
from rca.report.sections import coverage_rows, report_sections

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "rca" / "data"
CITIES = ("北京", "上海", "全国")
SAMPLES = DATA / "samples" / "samples.json"
RULE_FILES = {
    "北京": "ruleset-bj.json", "上海": "ruleset-sh.json", "全国": "ruleset-cn.json"
}


def _samples() -> list:
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def _copy_data(tmp_path: Path) -> Path:
    """把整个 data/ 复制到 tmp（探活要在"另一个数据目录"上跑完整通路）。"""
    dst = tmp_path / "data"
    shutil.copytree(DATA, dst)
    return dst


def _bench(data_dir: Path) -> int:
    buf = io.StringIO()
    with redirect_stdout(buf):
        return run_benchmarks(data_dir=str(data_dir))


# ---------------------------------------------------------------------------
# DoD 1：真值库采样数（分子）必须登记——分母+分子+采样清单三件套
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("city", CITIES)
def test_coverage_registers_numerator_not_only_denominator(city, data_dir):
    """coverage 必须**三件套齐备**：分母（规则条数）+ 分子（采样条数）+ 采样清单。

    plan/04 §2.3 原话："只写分子就是假覆盖"——本项目此前连分子都没有，
    `coverage` 里只有 `rule_total`（分母），"覆盖声明"于是无法证伪。
    """
    info = ruleset_overview(city, data_dir)
    cov = info["coverage"]
    assert cov.get("sampling_declaration"), "覆盖声明缺「抽样覆盖、非逐条穷举」口径"
    truth = cov.get("truth_sampling")
    assert truth, "%s coverage 缺真值采样段（分子缺失=假覆盖）" % city
    assert set(truth) == set(CHECK_TYPE_FORMS), (
        "%s 逐形态采样登记缺形态：%s" % (city, sorted(set(CHECK_TYPE_FORMS) - set(truth)))
    )
    for form, item in truth.items():
        assert set(item) >= {"rule_total", "sampled_rules", "sampled_rule_ids", "sample_ids"}
        # 分子 ≤ 分母；有规则的形态分子必须 > 0（零采样 = 该形态等于没测）。
        # 无规则的形态（如上海包无 element_completeness 条）分母为 0，分子也必须为 0——
        # 那不是缺口（"没有这类规则"与"有规则但没测"是两种情形），由全局形态检查兜底。
        assert item["sampled_rules"] <= item["rule_total"]
        if item["rule_total"]:
            assert item["sampled_rules"] > 0, (
                "%s 形态 %s 有 %d 条规则却零采样件"
                % (city, form, item["rule_total"])
            )
        else:
            assert item["sampled_rules"] == 0
        assert len(item["sampled_rule_ids"]) == item["sampled_rules"]
        assert item["sample_ids"] or item["rule_total"] == 0


@pytest.mark.parametrize("city", CITIES)
def test_registered_numerator_matches_recomputed(city, data_dir):
    """规则包**登记的**采样数必须与从 samples.json 实算的一致（不是两份真相）。"""
    rs = load_ruleset(city, data_dir)
    actual = sample_coverage({r.rule_id: r.check_type for r in rs.rules}, _samples())
    assert rs.manifest_coverage["truth_sampling"] == actual, (
        "%s 覆盖登记的采样数与实算不符（假覆盖）" % city
    )
    # 逐形态分母也必须与规则包实际条目数一致
    for form, item in actual.items():
        assert item["rule_total"] == len(
            [r for r in rs.rules if r.check_type == form]
        ), "%s 形态 %s 的分母与实际条目数不符" % (city, form)


@pytest.mark.parametrize("city", CITIES)
def test_coverage_reaches_report_and_cli(city, data_dir):
    """覆盖清单必须进**产物**：CLI `rules` 与导出报告都要能看出"该形态采样了几条"。"""
    info = ruleset_overview(city, data_dir)
    rows = coverage_rows(info["coverage"])
    assert rows, "报告覆盖表为空（读者无法判断该形态采样了几条）"
    assert [r[0] for r in rows] == list(CHECK_TYPE_FORMS), "覆盖表形态顺序不稳定"
    for row in rows:
        # 断言绑**实际取值**（分母/分子），不只绑标签字样
        item = info["coverage"]["truth_sampling"][row[0]]
        assert row[1] == str(item["rule_total"])
        assert row[2] == str(item["sampled_rules"])
        assert row[3] == ("、".join(item["sampled_rule_ids"]) or "—")

    # CLI 人类可读输出同样要带分子（只显示分母就是假覆盖）
    from rca.cli import main

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["rules", "--city", city])
    out = buf.getvalue()
    assert rc == 0
    assert "真值库采样" in out, "%s 的 rules 输出未展示采样分子" % city


def test_report_markdown_contains_coverage_rows(bj_enterprise, data_dir):
    """导出的 Markdown 报告必须实际含覆盖表行（而非只有表头）。"""
    info = ruleset_overview("北京", data_dir)
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    md = render_markdown(result, [], info["coverage"])
    for row in coverage_rows(info["coverage"]):
        assert row[0] in md, "报告缺形态行 %s" % row[0]
        assert row[2] in md, "报告缺该形态的采样分子 %s" % row[2]


# ---------------------------------------------------------------------------
# DoD 2：B1 指标与实现对齐——真 P/R/F1（消灭"文档说 P/R/F1、实现只有准确率"）
# ---------------------------------------------------------------------------

def test_b1_reports_real_precision_recall_f1(data_dir):
    """B1 必须真算 P/R/F1（不是布尔式准确率换名）。"""
    r = _run_b1(_samples(), DATA)
    assert r["metric"] == "f1"
    assert {"precision", "recall", "true_positive", "false_positive", "false_negative"} <= set(r)
    # F1 必须是 P/R 的调和平均（绑实际取值，防"字段填了但没算"）
    p, rec = r["precision"], r["recall"]
    expected_f1 = (2 * p * rec / (p + rec)) if (p + rec) else 0.0
    assert r["value"] == round(expected_f1, 4)
    # P/R 必须由 TP/FP/FN 实际算出
    tp, fp, fn = r["true_positive"], r["false_positive"], r["false_negative"]
    assert r["precision"] == round(tp / (tp + fp), 4) if (tp + fp) else True
    assert r["recall"] == round(tp / (tp + fn), 4) if (tp + fn) else True
    assert r["denominator"] == tp + fp + fn


def test_b1_denominator_comes_from_registered_field_truth(data_dir):
    """B1 的分母必须来自真值侧登记的"应有字段"，不是引擎自己数出来的字段。

    只数引擎的字段 = 拿引擎给自己出题（引擎漏抽一个字段，分母也跟着少一个，
    召回率永远 100%）——那正是"文档说 P/R、实现只有准确率"的根因。
    """
    samples = _samples()
    registered = sum(
        len(s.get("expect_fields") or {}) + len(s.get("expect_absent_fields") or [])
        for s in samples
    )
    assert registered > 0, "真值侧未登记应有字段（B1 无法算 P/R）"
    # 真值登记的字段总数必须 ≥ B1 的分母基数（TP+FN 是"应有值"侧）
    r = _run_b1(samples, DATA)
    assert r["true_positive"] + r["false_negative"] == sum(
        len(s.get("expect_fields") or {}) for s in samples
    ), "B1 的 TP+FN 与真值登记的应有字段数不符（分母不是真值侧）"


def test_b1_field_truth_is_independent_of_engine(data_dir):
    """真值侧字段期望必须**独立于引擎**：期望值由生成器入参推导，不调引擎抽取函数。

    若期望借用引擎的抽取/量化函数，引擎抽错时期望一起错，探活永远绿（plan/04 §5）。
    本测试直接核对真值取值与"合同文本里写的数"一致，绕开引擎。
    """
    s = next(x for x in _samples() if x["sample_id"] == "S-BJ-001")
    text = s["contract_text"]
    # 文本写"押金 1 个月租金"→ 真值必须记 1.00，且该值在正文中逐字可核
    assert s["expect_fields"]["deposit_months"] == "1.00"
    assert "押金 1 个月租金" in text
    # 租期 3 年 → 真值 3.00（不是引擎返回什么就记什么）
    assert s["expect_fields"]["lease_term_years"] == "3.00"
    assert "租赁期限为 3 年" in text


# ---------------------------------------------------------------------------
# DoD：also_expect 不得是"登记了但从不校验"的死数据（B2 全量对账）
# ---------------------------------------------------------------------------

def test_compare_exact_flags_status_on_pass_side():
    """全量对账必须抓到"两侧都不在非 pass 集合所以恒不报"的错误。

    真值登记 compliant、观测却是 skipped（两者都算 pass）时，`compare_nonpass`
    两侧的非 pass 集合都为空 → 恒不报；`compare_exact` 必须报出来。
    这正是 `also_expect`（`reference` 等 pass 侧结论）此前是死数据的根因。
    """
    from rca.benchmark.cases import compare_nonpass

    expected = {"R1": "compliant", "R2": "reference"}
    observed = {"R1": "skipped", "R2": "skipped"}
    old = compare_nonpass(expected, observed)
    assert not (old["missed"] or old["false_positive"] or old["status_mismatch"]), (
        "非 pass 口径本应漏掉这一类（这正是全量对账存在的理由）"
    )
    new = compare_exact(expected, observed)
    assert new["mismatch"] == ["R1", "R2"]


def test_b2_reconciles_also_expect(data_dir):
    """B2 的分母必须覆盖 `expect ∪ also_expect` 登记的**每条**规则。

    `also_expect`（同一注入隐含的其余结论，如 quota 条进条件触发栏的 `reference`）
    此前被 B2 完全忽略——真值库里一个永不参与对账的字段，本身就是一种假覆盖。
    """
    samples = _samples()
    total_truth = sum(
        len(s.get("expect") or {}) + len(s.get("also_expect") or {}) for s in samples
    )
    r = _run_b2(samples, DATA)
    assert r["denominator"] == total_truth, (
        "B2 分母 %d != 真值登记总数 %d（also_expect 未纳入对账）"
        % (r["denominator"], total_truth)
    )
    assert r["hit_rate"] if False else r["value"] == 1.0
    assert r["false_positive"] == 0 and r["unregistered"] == 0


def test_b2_catches_reference_status_mismatch(tmp_path):
    """also_expect 里的 `reference` 若被判成别的状态，B2 必须报差异。

    这是"also_expect 真被校验了"的反证：若它仍是死数据，改这个值不会影响任何指标。
    """
    d = _copy_data(tmp_path)
    samples = json.loads((d / "samples" / "samples.json").read_text(encoding="utf-8"))
    # 把某份样例的 also_expect 值改错（引擎实际返回 reference，这里改成 pass 侧的另一状态）
    target = next(s for s in samples if s["sample_id"] == "S-BJ-001")
    rid = sorted(target["also_expect"])[0]
    target["also_expect"][rid] = "compliant"
    write_text_lf(d / "samples" / "samples.json", json.dumps(samples, ensure_ascii=False))

    r = _run_b2(samples, d)
    assert r["status_mismatch"] >= 1, "also_expect 被改错却未被对账检出（死数据）"


# ---------------------------------------------------------------------------
# DoD 3：B2（误报）探活须端到端——run_benchmarks 真的返回非 0
# ---------------------------------------------------------------------------

def test_probe_b1_tampered_truth_makes_bench_fail_end_to_end(tmp_path):
    """B1 探活端到端：篡改真值后 `run_benchmarks(data_dir=tmp)` 必须 exit 1。

    旧测试只断言 `compare_nonpass()` 返回非空（对账函数层），**没有**断言
    `run_benchmarks()` 真的返回非 0——对账函数对、但门槛判定通路没接上的话，
    旧断言照样绿。

    注意门槛是 0.95：注入的缺陷必须**系统性地**越过门槛才会让基准报未达标
    （把整份真值库里同一字段的期望改错，而不是只改一处——只改一处仍在容差内，
    基准判"达标"本身是正确的，那种注入证明不了门槛通路是活的）。
    """
    d = _copy_data(tmp_path)
    samples = json.loads((d / "samples" / "samples.json").read_text(encoding="utf-8"))
    # 系统性篡改：把所有样例的 `deposit_months` 期望取值改成与合同不符
    for s in samples:
        if "deposit_months" in (s.get("expect_fields") or {}):
            s["expect_fields"]["deposit_months"] = "9.00"
    write_text_lf(d / "samples" / "samples.json", json.dumps(samples, ensure_ascii=False))

    r = _run_b1(samples, d)
    assert r["false_positive"] >= 5, "系统性篡改字段真值未被 B1 检出"
    assert r["value"] < 0.95, "篡改后的 F1 %.4f 未跌破门槛（注入强度不足）" % r["value"]
    assert _bench(d) == 1, "篡改真值后基准必须报未达标（走完整门槛判定通路）"


def test_probe_b2_bad_reference_injection_makes_bench_fail_end_to_end(tmp_path):
    """B2 探活端到端：注入一条**必然误报**的规则（坏引用）→ 基准必须 exit 1。

    plan/04 §5 表要求 B2 的注入缺陷是"注入一条必然误报的规则（坏引用）"。
    此前测试只覆盖 B1/B3 的探活，**B2 的坏引用注入没有端到端探活**。

    注入形态：在规则包里加一条 quote **不逐字存在于快照**的规则（"坏引用"——
    看着有锚点、实则核不到原文）。引擎仍会加载并判定 → 产出一条真值库未登记的
    判定 → B2 的未登记数 > 0 → 命中率 < 1 → 未达标。
    """
    d = _copy_data(tmp_path)
    rs_path = d / "rules" / "ruleset-bj.json"
    raw = json.loads(rs_path.read_text(encoding="utf-8"))
    injected = {
        "rule_id": "BJ-INJECTED-BAD-REF",
        "title": "注入的坏引用规则（探活用）",
        "check_type": "numeric_limit",
        "scope": "calc",
        "param": "deposit_months",
        "op": "<=",
        "value": 0,
        "unit": "月租金",
        "applies_if": {"party": ["any"]},
        "effect": "standing_obligation",
        "severity": "high",
        "source_id": "SRC-BJ-HOUSING-RENTAL",
        "clause": "第三十六条",
        "quote": "这是一句在官方快照里并不存在的伪造法条原文，用于探活。",
        "status": "verified",
        "clause_status": "verified",
    }
    raw["rules"].append(injected)
    write_text_lf(rs_path, json.dumps(raw, ensure_ascii=False))

    # 先确认注入的规则真的产生了"必然误报"的判定（押金 1 个月 > 上限 0）
    samples = json.loads((d / "samples" / "samples.json").read_text(encoding="utf-8"))
    s = next(x for x in samples if x["sample_id"] == "S-BJ-001")
    result = compute_result(s["contract_text"], s["city"], data_dir=str(d))
    injected_finding = next(
        (f for f in result.findings if f.rule_id == "BJ-INJECTED-BAD-REF"), None
    )
    assert injected_finding is not None, "注入的规则未被引擎加载（探活前提不成立）"
    assert injected_finding.status == "noncompliant"

    r = _run_b2(samples, d)
    assert r["unregistered"] >= 1 or r["false_positive"] >= 1, (
        "坏引用注入产生的误报未被 B2 检出"
    )
    assert r["value"] < 1.0
    assert _bench(d) == 1, "注入坏引用规则后基准必须报未达标"


def test_probe_b3_boundary_mutation_makes_bench_fail_end_to_end(tmp_path):
    """B3 探活端到端：把规则表某边界值改 ±1 → `run_benchmarks` 必须 exit 1。"""
    d = _copy_data(tmp_path)
    rs_path = d / "rules" / "ruleset-bj.json"
    raw = json.loads(rs_path.read_text(encoding="utf-8"))
    target = next(r for r in raw["rules"] if r["rule_id"] == "BJ-FILING-30D")
    # B3 从规则表推导端点：把值改成 31 后，B3 自身仍会通过（它按新值推导）——
    # 故真正能抓"边界被改"的是**独立来源**的期望（B2 的样例真值：备案 30 日应 compliant）。
    target["value"] = 29
    write_text_lf(rs_path, json.dumps(raw, ensure_ascii=False))
    assert _bench(d) == 1, "规则边界被改后基准必须报未达标（独立真值来源必须抓到）"


# ---------------------------------------------------------------------------
# DoD：空分母不冒充通过（复核既有实现，确认不回归）
# ---------------------------------------------------------------------------

def test_empty_denominator_never_passes(tmp_path):
    """分母为 0 的"达标"是假门——恒未达标（复核 M0 分支不回归）。"""
    (tmp_path / "rules").mkdir(parents=True)
    (tmp_path / "samples").mkdir(parents=True)
    (tmp_path / "rules" / "ruleset-bj.json").write_text(
        json.dumps(
            {
                "ruleset_id": "x", "city": "北京",
                "rules": [{
                    "rule_id": "X", "title": "t", "check_type": "numeric_limit",
                    "scope": "calc", "param": "p", "op": "<=", "value": 1, "unit": "u",
                    "applies_if": {"party": ["any"]}, "effect": "standing_obligation",
                    "severity": "low", "source_id": "s", "clause": "c", "quote": "q",
                    "status": "verified", "clause_status": "verified",
                }],
                "benchmark_thresholds": {"B1_parse_f1_min": 0.95},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "samples" / "samples.json").write_text("[]", encoding="utf-8")
    assert _bench(tmp_path) == 1


# ---------------------------------------------------------------------------
# DoD 5/6：样例覆盖形态检查 + 每个形态 ≥1 采样件
# ---------------------------------------------------------------------------

def test_every_check_type_form_has_a_sampled_case(data_dir):
    """每个 check_type 形态都必须有 ≥1 份采样件（否则该形态在基准里等于没测）。"""
    forms = {}
    for city in CITIES:
        for r in load_ruleset(city, data_dir).rules:
            forms[r.rule_id] = r.check_type
    assert coverage_gaps(forms, _samples()) == [], (
        "存在零采样件的形态：%s" % coverage_gaps(forms, _samples())
    )


def test_zero_sampled_form_makes_bench_fail_end_to_end(tmp_path):
    """零采样件的形态必须让**基准**判未达标（分子为 0 的"达标"是假门）。

    只测 `coverage_gaps()` 纯函数是不够的：函数对、但基准层的门槛判定没接上，
    零采样照样"达标"。故本测试走完整通路，并用 `only="B3"` **隔离**——
    B3 自身按规则表推导端点必然通过，唯一可能的未达标原因就是覆盖门。
    """
    d = _copy_data(tmp_path)
    samples = json.loads((d / "samples" / "samples.json").read_text(encoding="utf-8"))
    # 抹掉所有样例对 element_completeness 形态规则的采样（expect 与 also_expect 都抹）
    for s in samples:
        for bucket in ("expect", "also_expect"):
            for rid in list(s.get(bucket) or {}):
                if rid.startswith(("CN-ELEMENT-COMPLETENESS", "CN-WRITTEN-FORM",
                                   "BJ-CONTRACT-ELEMENT", "BJ-ESCROW-DEPOSIT")):
                    del s[bucket][rid]
    write_text_lf(d / "samples" / "samples.json", json.dumps(samples, ensure_ascii=False))

    forms = {}
    for city in CITIES:
        for r in load_ruleset(city, str(d)).rules:
            forms[r.rule_id] = r.check_type
    assert "element_completeness" in coverage_gaps(forms, samples), "测试未造出零采样形态"

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_benchmarks(only="B3", data_dir=str(d))
    assert rc == 1, "零采样形态未让基准判未达标（分子为 0 的假门复活）"
    assert "覆盖缺口" in buf.getvalue() or "零采样" in buf.getvalue()


def test_samples_cover_both_cities_and_both_lease_kinds(data_dir):
    """样例必须覆盖京/沪两市与普通/保租房两种房屋类型（城市差异包要有采样件）。"""
    samples = _samples()
    assert {s["city"] for s in samples} >= {"北京", "上海"}
    assert {s["lease_kind"] for s in samples} == {"ordinary", "affordable"}


def test_missing_element_sample_yields_noncompliant(data_dir):
    """无条件义务缺失 = noncompliant（不是 skipped）——必须有样例实触达该形态。

    plan/04 §7 第 2 条：合同缺民法典 704 条某要素 → 期望 noncompliant。
    此前 704 条恒被 compliant 覆盖，该分支等于没测。
    """
    s = next(x for x in _samples() if x["sample_id"] == "S-BJ-011")
    assert s["expect"]["CN-ELEMENT-COMPLETENESS"] == "noncompliant"
    result = compute_result(s["contract_text"], s["city"], data_dir=data_dir)
    f = {x.rule_id: x for x in result.findings}["CN-ELEMENT-COMPLETENESS"]
    assert f.status == "noncompliant", "缺要素样例未判 noncompliant: %s" % f.reason
    assert "维修" in f.reason


def test_not_assessed_sample_exists(data_dir):
    """必须有一份样例能触达"整体 not_assessed"（绝不输出 compliant）。

    plan/04 §7 第 3 条：一条规则都不适用的样例 → 整体 not_assessed。
    此前 12 份样例全部可识别为合同，无一份能触发 not_assessed。
    """
    s = next(x for x in _samples() if x["sample_id"] == "S-BJ-012")
    result = compute_result(s["contract_text"], s["city"], data_dir=data_dir)
    assert result.overall_status == "not_assessed", (
        "非合同样例未判 not_assessed（实测 %s）" % result.overall_status
    )
    assert result.overall_status != "compliant"
    assert result.status_counts.get("unknown", 0) > 0


def test_truth_registers_every_enabled_rule(bj_enterprise, data_dir):
    """真值库必须为**每条生效规则**登记期望——否则 B2 分母缺项（假覆盖）。

    生效规则 = 门控后 + 叠加全国层 + 条件触发栏。逐包逐样例核。
    """
    for city in CITIES:
        rs = effective_ruleset(city, "calc", data_dir)
        enabled = {r.rule_id for r in list(rs.rules) + list(rs.reference_rules)}
        for s in _samples():
            if s["city"] != city:
                continue
            truth = set(s.get("expect") or {}) | set(s.get("also_expect") or {})
            missing = enabled - truth
            assert not missing, "%s 样例 %s 未登记生效规则 %s" % (city, s["sample_id"], missing)


# ---------------------------------------------------------------------------
# DoD 7：门槛三件套（五项）齐备
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("city", CITIES)
def test_thresholds_all_five_present(city, data_dir):
    """门槛五项须都在规则包 manifest 里（数据非代码，基准层只读）。"""
    rs = load_ruleset(city, data_dir)
    for key in (
        "B1_parse_f1_min", "B2_hit_rate_min", "B2_false_positive_max",
        "B3_boundary_pass_rate_min", "max_runtime_seconds",
    ):
        assert key in rs.thresholds, "%s 规则包缺门槛 %s" % (city, key)


def test_thresholds_come_from_manifest_not_code(data_dir):
    """改规则包 manifest 的门槛必须改变判定结果（证明基准层真读数据）。"""
    assert run_benchmarks(only="B1", data_dir=data_dir) == 0
    # 抬高门槛到 1.01（不可达）→ B1 必须报未达标
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "data"
        shutil.copytree(DATA, d)
        p = d / "rules" / "ruleset-bj.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["benchmark_thresholds"]["B1_parse_f1_min"] = 1.01
        write_text_lf(p, json.dumps(raw, ensure_ascii=False))
        assert _bench(d) == 1, "抬高门槛后基准仍达标（门槛未真从 manifest 读取）"


# ---------------------------------------------------------------------------
# 三套件一键复跑 + 指标写入 README（DoD）
# ---------------------------------------------------------------------------

def test_all_suites_pass_and_metrics_are_real(data_dir):
    assert _bench(DATA) == 0
    b1, b2 = _run_b1(_samples(), DATA), _run_b2(_samples(), DATA)
    assert b1["value"] == 1.0 and b1["denominator"] > 0
    assert b2["value"] == 1.0 and b2["denominator"] > 0 and b2["false_positive"] == 0


def test_readme_metrics_match_bench_output(data_dir):
    """README 评测表的三个分子/分母必须与基准实跑一致（防文档漂移）。

    断言绑**实际取值**：只断言"README 里有 B1 字样"的话，把数字改成任何值都照样绿。
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    b1 = _run_b1(_samples(), DATA)
    b2 = _run_b2(_samples(), DATA)
    b3 = None
    from rca.benchmark.runner import _run_b3

    b3 = _run_b3(["北京", "上海", "全国"], DATA)
    assert "%d/%d" % (b1["true_positive"], b1["denominator"]) in readme, (
        "README 的 B1 计数 %d/%d 未出现" % (b1["true_positive"], b1["denominator"])
    )
    assert "%d/%d" % (b2["numerator"], b2["denominator"]) in readme, (
        "README 的 B2 计数 %d/%d 未出现" % (b2["numerator"], b2["denominator"])
    )
    assert "%d/%d" % (b3["numerator"], b3["denominator"]) in readme, (
        "README 的 B3 计数 %d/%d 未出现" % (b3["numerator"], b3["denominator"])
    )
