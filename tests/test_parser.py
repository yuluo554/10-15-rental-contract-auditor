"""解析层测试：条款切分回定位、要素抽取证据链、陷阱处理。"""

from __future__ import annotations

from rca.parser.clauses import collapse_spaced_chars, normalize_newlines, split_clauses
from rca.parser.extract import build_card


def test_split_finds_articles(bj_compliant):
    clauses, text, pending = split_clauses(bj_compliant)
    numbers = [c.number for c in clauses]
    assert "第一条" in numbers
    assert "第八条" in numbers
    assert len(clauses) == 8
    assert not pending, "正常合同不应有待人工确认项"


def test_every_clause_number_located_verbatim(bj_compliant):
    """确定性纪律：切分出的条款号必须能在原文中定位到逐字原文。"""
    clauses, text, _ = split_clauses(bj_compliant)
    cursor = 0
    for c in clauses:
        assert c.located, "条款 %s 未定位" % c.number
        pos = text.find(c.number, cursor)
        assert pos >= 0, "条款号 %s 无法在原文定位" % c.number
        cursor = pos


def test_unlocatable_text_is_flagged():
    """无法定位的切分必须显式标注（不静默吞掉）。"""
    clauses, _, pending = split_clauses("这不是合同，只是一段说明文字。")
    assert pending, "非合同文本必须进待人工确认清单"


def test_crlf_is_normalized():
    text = "第一条 内容。\r\n第二条 内容。\r\n"
    clauses, normalized, _ = split_clauses(text)
    assert "\r" not in normalized
    assert len(clauses) == 2


def test_spaced_chars_collapsed():
    """PDF 复制产生的逐字符空格要能折叠。"""
    spaced = "第 一 条 甲 方 将 房 屋 出 租 给 乙 方 使 用 居 住"
    collapsed = collapse_spaced_chars(spaced)
    assert "第一条" in collapsed


def test_arabic_article_numbers():
    clauses, _, _ = split_clauses("第1条 内容A\n第2条 内容B\n")
    assert [c.number for c in clauses] == ["第1条", "第2条"]


def test_extract_evidence_is_verbatim_substring(bj_enterprise):
    clauses, text, pending = split_clauses(bj_enterprise)
    card = build_card(text, clauses, pending)
    for name, f in card.fields.items():
        if f.evidence and f.evidence.clause_text:
            assert f.evidence.clause_text in text, (
                "%s 的证据不是原文子串（防幻觉硬约束）" % name
            )


def test_extract_numeric_fields(bj_enterprise):
    clauses, text, pending = split_clauses(bj_enterprise)
    card = build_card(text, clauses, pending)
    assert card.get("deposit_months").value == 2
    assert card.get("rent_prepay_months").value == 6
    assert card.get("lease_term_years").value == 3
    assert card.get("filing_days").value == 30
    assert card.get("deposit_refund_workdays").value == 5


def test_extract_month_to_year_conversion():
    """月→年换算（精度约定：两位小数）。"""
    text = "第一条 房屋位于朝阳区，建筑面积 60 平方米。\n第二条 租赁期限为 18 个月。\n"
    clauses, normalized, pending = split_clauses(text)
    card = build_card(normalized, clauses, pending)
    assert str(card.get("lease_term_years").value) == "1.50"


def test_party_detection_enterprise(bj_enterprise):
    clauses, text, pending = split_clauses(bj_enterprise)
    card = build_card(text, clauses, pending)
    assert card.party == "enterprise"


def test_party_detection_individual(individual):
    clauses, text, pending = split_clauses(individual)
    card = build_card(text, clauses, pending)
    assert card.party == "individual"


def test_party_detection_unknown():
    text = "住房租赁合同\n第一条 甲方将房屋出租给乙方。\n"
    clauses, normalized, pending = split_clauses(text)
    card = build_card(normalized, clauses, pending)
    assert card.party == "unknown"


def test_city_detection(bj_compliant):
    clauses, text, pending = split_clauses(bj_compliant)
    card = build_card(text, clauses, pending)
    assert card.city == "北京"


def test_missing_field_is_absent_not_zero(bj_compliant):
    """未观测字段必须是 absent，**绝不静默取 0**。"""
    clauses, text, pending = split_clauses(bj_compliant)
    card = build_card(text, clauses, pending)
    f = card.get("lodging_reg_workdays")
    assert f.value is None
    assert f.confidence == "absent"
    assert not f.observed
