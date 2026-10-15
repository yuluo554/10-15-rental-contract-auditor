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


# ---------------------------------------------------------------------------
# M2：正文交叉引用不得被当成条款边界（与 M1 的条号劫持同源，发生在解析层）
# ---------------------------------------------------------------------------


def test_inline_cross_reference_is_not_a_clause_boundary():
    """正文里的交叉引用同样是"第X条"形态，**不是**条款边界。

    实测原缺陷：`第一条 …应遵守第五条关于维修的约定。` 被劈成两条，
    并凭空造出一个"第五条"——报告随后把判定依据指向**不存在的条款**。
    正确切分：只有 第一条 / 第二条，且第一条正文完整含引用句。
    """
    text = (
        "第一条 甲方将房屋出租给乙方。乙方应遵守第五条关于维修的约定。\n"
        "第二条 租赁期限为 2 年。\n"
    )
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["第一条", "第二条"], (
        "交叉引用被当成了条款边界：%s" % [c.number for c in clauses]
    )
    assert "第五条关于维修的约定" in clauses[0].text, "第一条正文被引用从中间劈开"
    assert not pending, "行内交叉引用是**正确**用法，不应刷进待人工确认清单"


def test_wrapped_cross_reference_is_flagged_not_silent():
    """PDF 断行形态（"…应遵守" 换行 "第五条…"）条号落在行首，定义位判定放行。

    这一形态**必须显式进待人工确认清单**——它正是"看着成功、实则错位"
    （`located=True` 但正文被劈开）的最危险形态，静默即等于把错位当成功。
    """
    text = (
        "第一条 甲方将房屋出租给乙方。乙方应遵守\n"
        "第五条关于维修的约定。\n"
        "第二条 租赁期限为 2 年。\n"
    )
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["第一条", "第二条"]
    assert "第五条关于维修的约定" in clauses[0].text, "断行引用劈开了第一条正文"
    assert any("第五条" in p and "交叉引用" in p for p in pending), (
        "断行交叉引用未进待人工确认清单（静默错位）：%s" % pending
    )


def test_citation_with_exception_is_not_a_boundary():
    """合法引用后随形态（"第五条规定的除外"）不得被当成条款起始。

    只挡"引用触发词在前"，不管"引用在句末被后随限定"——这两种都是引用而非定义。
    """
    text = "第三条 维修责任由甲方承担，第五条规定的除外。\n第四条 押金退还。\n"
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["第三条", "第四条"], (
        "句末引用被当成了条款边界：%s" % [c.number for c in clauses]
    )
    assert "第五条规定的除外" in clauses[0].text
    assert not pending


def test_normal_sentence_ending_is_not_mistaken_for_citation():
    """负向守门：正常句尾（含"遵守"字样）之后的新条款必须照常切出。

    前导守门只认**紧贴条号**的触发词；句号隔开的正常句尾不得误伤，
    否则会把真实条款静默吞掉（比漏切更糟：整条义务凭空消失）。
    """
    text = (
        "第一条 乙方应遵守约定，按时支付租金。\n"
        "第二条 租赁期限为 2 年。\n"
    )
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["第一条", "第二条"], (
        "正常句尾被误判为引用，真实条款被吞掉：%s" % [c.number for c in clauses]
    )
    assert not pending


def test_noun_phrase_lead_does_not_eat_real_clause():
    """名词短语（"本合同/本条例"）收尾的句子之后，新条款**不得**被当引用吞掉。

    这类名词短语能合法结束一个正常句子（"…依据本合同" 换行 "第二条 …"），
    故前导守门只收"不能单独收尾成句"的动词/介词——否则真条款会凭空消失。
    """
    text = (
        "第一条 双方的权利义务依据本合同\n"
        "第二条 租赁期限为 2 年。\n"
    )
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["第一条", "第二条"], (
        "名词短语收尾被误判为引用，真条款被吞掉：%s" % [c.number for c in clauses]
    )
    assert not pending


# ---------------------------------------------------------------------------
# M2：第X条之一（修订条文）与重复条号
# ---------------------------------------------------------------------------


def test_article_with_zhiyi_suffix_is_one_clause():
    """`第一条之一` 是**一个**条号，不得被切回裸 `第一条` 而与之重复。

    实测原缺陷：`第一条之一` 被匹配成 `第一条`，产生两个"第一条"
    （located 均为 True，看着成功）——回定位随之互相错配。
    """
    text = "第一条 内容甲。\n第一条之一 内容乙。\n第二条 内容丙。\n"
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["第一条", "第一条之一", "第二条"], (
        "之一后缀形态切分错误：%s" % [c.number for c in clauses]
    )
    assert len(set(c.number for c in clauses)) == len(clauses), "产生了重复条号"
    assert not pending


def test_duplicate_clause_number_is_flagged_not_mismatched():
    """真重复条号（原文就写重了）必须显式标注，不得让回定位互相错配。"""
    text = "第一条 内容甲。\n第一条 内容乙。\n第二条 内容丙。\n"
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["第一条", "第二条"], (
        "重复条号未被去重：%s" % [c.number for c in clauses]
    )
    assert any("重复条号" in p for p in pending), (
        "重复条号未进待人工确认清单（回定位会互相错配）：%s" % pending
    )


def test_zhiyi_suffix_locate_is_monotonic():
    """之一形态下 `_locate` 的单调递增仍成立（防重复条号错配的负向测试）。"""
    text = "第一条 内容甲。\n第一条之一 内容乙。\n第一条之二 内容丙。\n第二条 内容丁。\n"
    clauses, normalized, _ = split_clauses(text)
    cursor = 0
    for c in clauses:
        pos = normalized.find(c.number, cursor)
        assert pos >= 0, "条号 %s 无法单调定位" % c.number
        cursor = pos
    assert [c.number for c in clauses] == [
        "第一条", "第一条之一", "第一条之二", "第二条",
    ]


# ---------------------------------------------------------------------------
# M2：`（一）` 括号中文序号
# ---------------------------------------------------------------------------


def test_paren_chinese_index_supported():
    """`（一）` 括号中文序号须能切出（原实现整体进 pending_manual）。

    实测原缺陷：整段切不出任何条款。括号序号在合同里常用于"一、"下的分项，
    切不出会让这些分项的正文全部落进上一条（要素证据挂错条款）。
    """
    text = "一、房屋基本情况\n（一）坐落：某小区 1 号楼\n（二）面积：60 平方米\n二、租赁期限\n"
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["一、", "（一）", "（二）", "二、"], (
        "括号中文序号未切出：%s" % [c.number for c in clauses]
    )
    assert all(c.kind == "paren_index" for c in clauses if c.number.startswith("（")), (
        "括号序号的 kind 未登记为 paren_index"
    )
    assert not pending


def test_paren_index_alone_is_supported():
    """纯括号序号文本也要能切出（不依赖"一、"父级序号存在）。"""
    text = "（一）坐落：某小区 1 号楼\n（二）面积：60 平方米\n"
    clauses, _, pending = split_clauses(text)
    assert [c.number for c in clauses] == ["（一）", "（二）"]
    assert not pending


# ---------------------------------------------------------------------------
# M2：中文租期表述（保租房租期下限规则的输入面）
# ---------------------------------------------------------------------------


def test_chinese_half_year_term_extracted():
    """`半年` / `X年半` 必须抽到并换算——否则保租房租期下限规则判 unknown（漏报）。"""
    cases = {
        "租赁期限为半年。": "0.50",
        "租赁期限为一年半。": "1.50",
        "租赁期限为两年半。": "2.50",
        "租期半年。": "0.50",
    }
    for sentence, want in cases.items():
        text = "第一条 甲方出租房屋。\n第二条 %s\n" % sentence
        clauses, normalized, pending = split_clauses(text)
        card = build_card(normalized, clauses, pending)
        got = card.get("lease_term_years").value
        assert got is not None, "中文租期表述未抽到：%r" % sentence
        assert str(got) == want, "%r 抽成 %s，期望 %s" % (sentence, got, want)


def test_half_year_term_does_not_lose_the_half():
    """`一年半` 不得被通用"X 年"式吃成 1.00（**静默取错值**比抽不到更危险）。"""
    text = "第一条 甲方出租房屋。\n第二条 租赁期限为一年半。\n"
    clauses, normalized, pending = split_clauses(text)
    card = build_card(normalized, clauses, pending)
    assert str(card.get("lease_term_years").value) == "1.50", (
        "'半'被丢掉了：%s" % card.get("lease_term_years").value
    )


def test_half_year_term_triggers_affordable_lower_bound():
    """端到端：`半年` 的保租房租期必须判 noncompliant，不得因漏抽而降级为 unknown。

    这是"漏报"的回归锁：抽不到 → 字段 absent → 下限规则判 unknown
    （"没看到"），把真实的**下限违规**说成"无法判定"。
    """
    from rca.engine.pipeline import compute_result

    text = (
        "上海保障性租赁住房租赁合同\n\n"
        "出租人（甲方）：上海宜居住房租赁有限公司\n"
        "承租人（乙方）：张三\n"
        "联系电话：19900000001\n\n"
        "第一条 甲方将位于上海市浦东新区的保障性租赁住房出租给乙方居住使用，建筑面积 60 平方米。\n"
        "第二条 租赁期限为半年。\n"
        "第三条 月租金为人民币 5000 元，乙方按月支付。\n"
        "第四条 乙方应向甲方支付押金 1 个月租金。\n"
        "第五条 甲方应自合同订立之日起 30 日内办理登记备案。\n"
    )
    result = compute_result(text, "上海")
    finding = next(f for f in result.findings if f.rule_id == "SH-AFFORDABLE-TERM-MIN-1Y")
    assert finding.status == "noncompliant", (
        "中文租期表述漏抽导致下限违规被降级：%s（%s）" % (finding.status, finding.reason)
    )


def test_natural_fixtures_still_split_cleanly(bj_enterprise, bj_compliant, individual):
    """解析层加固后，既有夹具的切分与抽取**不得回退**（防误伤守门）。"""
    for raw in (bj_enterprise, bj_compliant, individual):
        clauses, text, pending = split_clauses(raw)
        assert not pending, "正常合同出现了待人工确认项：%s" % pending
        assert all(c.located for c in clauses), "正常合同出现未定位条款"
        card = build_card(text, clauses, pending)
        assert card.get("contract_text").value == text
    # 两份 8 条合同（企业/合规）不得因新增守门而丢条
    for raw in (bj_enterprise, bj_compliant):
        clauses, _, _ = split_clauses(raw)
        assert len(clauses) == 8, "夹具条数回退：%d" % len(clauses)

