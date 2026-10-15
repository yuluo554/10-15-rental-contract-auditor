"""判定语义测试（plan/03 §4）——本项目的核心正确性面。

覆盖三类易错形态：
1. `skipped` 不冤枉用户（已知主体不满足适用条件）
2. **主体未知 → unknown，不是 skipped**（防"把没做记成不用做"）
3. 无条件义务缺失 = noncompliant
4. 无适用项 → not_assessed，绝不输出 compliant
"""

from __future__ import annotations

from rca.engine.pipeline import compute_result
from rca.model import (
    STATUS_COMPLIANT,
    STATUS_NONCOMPLIANT,
    STATUS_NOT_ASSESSED,
    STATUS_SKIPPED,
    STATUS_UNKNOWN,
)


def _by_id(result):
    return {f.rule_id: f for f in result.findings}


def test_enterprise_over_limit_is_noncompliant(bj_enterprise, data_dir):
    """押金 2 个月 > 北京上限 1 个月 → noncompliant。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    f = _by_id(result)["BJ-DEPOSIT-MAX-1M"]
    assert f.status == STATUS_NONCOMPLIANT
    assert "超过" in f.reason
    assert f.clause == "第三十六条"
    assert f.quote  # 判定必须挂法条原文


def test_rent_prepay_over_limit_is_noncompliant(bj_enterprise, data_dir):
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    f = _by_id(result)["BJ-RENT-PREPAY-MAX-3M"]
    assert f.status == STATUS_NONCOMPLIANT


def test_deposit_refund_over_limit_is_noncompliant(bj_enterprise, data_dir):
    """退还押金 5 个工作日 > 3 个工作日 → noncompliant。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    f = _by_id(result)["BJ-DEPOSIT-REFUND-3WD"]
    assert f.status == STATUS_NONCOMPLIANT


def test_compliant_contract_is_compliant(bj_compliant, data_dir):
    result = compute_result(bj_compliant, "北京", data_dir=data_dir)
    f = _by_id(result)
    assert f["BJ-DEPOSIT-MAX-1M"].status == STATUS_COMPLIANT
    assert f["BJ-RENT-PREPAY-MAX-3M"].status == STATUS_COMPLIANT
    assert f["BJ-DEPOSIT-REFUND-3WD"].status == STATUS_COMPLIANT
    assert f["BJ-FILING-30D"].status == STATUS_COMPLIANT


def test_known_individual_gets_skipped(individual, data_dir):
    """已知主体是自然人 → 企业专属规则判 skipped（原文写了适用主体限制）。

    这是"不适用要原文说了不适用"的正向形态。
    """
    result = compute_result(individual, "北京", data_dir=data_dir)
    f = _by_id(result)
    assert f["BJ-DEPOSIT-MAX-1M"].status == STATUS_SKIPPED
    assert "主体" in f["BJ-DEPOSIT-MAX-1M"].reason


def test_unknown_party_is_unknown_not_skipped(data_dir):
    """主体未知 → unknown（**不是 skipped**）。

    防"把没做记成不用做"的反向陷阱：若判 skipped，等于替用户断言
    "这条不适用"，合规结论虚高。
    """
    text = """住房租赁合同

第一条 甲方将位于朝阳区的住房出租给乙方居住使用，建筑面积 80 平方米。
第二条 租赁期限为 2 年。
第三条 月租金为人民币 5000 元，乙方按月支付。
第四条 乙方应向甲方支付押金 1 个月租金。
第五条 甲方应自合同订立之日起 30 日内办理登记备案。
第六条 房屋及其附属设施的维修责任由甲方承担。
"""
    result = compute_result(text, "北京", data_dir=data_dir)
    f = _by_id(result)["BJ-DEPOSIT-MAX-1M"]
    assert f.status == STATUS_UNKNOWN, "主体未知必须判 unknown，绝不替用户断言不适用"
    assert "无法确定合同主体" in f.reason


def test_overlong_lease_term_is_noncompliant(overlong_term, data_dir):
    """租期 25 年 > 民法典 20 年上限 → noncompliant（全国层规则叠加城市包）。"""
    result = compute_result(overlong_term, "北京", data_dir=data_dir)
    f = _by_id(result)
    assert "CN-LEASE-TERM-MAX" in f, "全国层规则必须叠加进城市包"
    assert f["CN-LEASE-TERM-MAX"].status == STATUS_NONCOMPLIANT
    assert f["CN-LEASE-TERM-MAX"].clause == "第七百零五条"


def test_no_applicable_rule_yields_not_assessed(data_dir):
    """一条规则都不适用 → not_assessed，绝不输出 compliant。

    "没查出问题"与"没检查过"必须可区分。
    """
    # 极简文本：无押金、无租期、无备案 —— 且主体未知
    text = "住房租赁合同\n甲方与乙方就房屋租赁事宜达成一致。\n"
    result = compute_result(text, "北京", data_dir=data_dir)
    assert result.overall_status == STATUS_NOT_ASSESSED
    assert result.overall_status != STATUS_COMPLIANT


def test_overall_status_noncompliant_wins(bj_enterprise, data_dir):
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    assert result.overall_status == STATUS_NONCOMPLIANT


def test_every_finding_has_clause_and_quote(bj_enterprise, data_dir):
    """溯源硬约束：每条判定必须挂条款号与法条原文。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    for f in result.findings:
        assert f.clause, "判定 %s 缺条款号" % f.rule_id
        assert f.quote, "判定 %s 缺法条原文" % f.rule_id
        assert f.source_id, "判定 %s 缺来源" % f.rule_id


def test_conditional_institution_not_in_obligations(bj_enterprise, data_dir):
    """监管裁量条款必须进"条件触发栏"，不进无条件义务栏（义务类型分栏）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    assert all(f.effect != "conditional_institution" for f in result.findings)
    ids = [f.rule_id for f in result.conditional_triggers]
    assert "BJ-RENT-INTERVENTION" in ids


def test_judgment_is_reproducible(bj_enterprise, data_dir):
    """同版本 + 同输入 = 同输出（可复现判定）。"""
    a = compute_result(bj_enterprise, "北京", data_dir=data_dir).to_dict()
    b = compute_result(bj_enterprise, "北京", data_dir=data_dir).to_dict()
    assert a == b


def test_element_completeness_uses_aliases(bj_compliant, data_dir):
    """要素完整性用别名表匹配——措辞不同不应误判为缺失。"""
    result = compute_result(bj_compliant, "全国", data_dir=data_dir)
    f = _by_id(result)
    assert f["CN-ELEMENT-COMPLETENESS"].status == STATUS_COMPLIANT
