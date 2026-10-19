"""城市规则包生成器（冻结产物，禁手改）。

纪律（plan/02 §3，skill 阶段 1"标准类数据的转录必须脚本转写 + 原文逐字包含断言"）：
- **条款号由快照推导**，不手抄：定位 `quote` 在快照中的位置，回溯到最近的 `第X条`。
  手抄条款号必然引入不可复现的漂移（本项目实测：同一罚则短语人工定位到两个不同条号）。
- **每处抽取值断言原文逐字包含**：`assert quote in snapshot_text`，失败即生成失败。
- 产物无时间戳、字典序稳定 → 两次运行逐字节一致（`--check` 守门）。

用法：
    py -3.12 -X utf8 tools/gen_rulesets.py            # 生成 src/rca/data/rules/ruleset-*.json
    py -3.12 -X utf8 tools/gen_rulesets.py --check     # 位级一致校验，输出 RULESETS_FROZEN_OK

数据布局：随包数据在 `src/rca/data/`（rules / samples / knowledge/MANIFEST.json）；
官方全文快照 `data/knowledge/raw/` 留在仓库根，**不随包**（版权红线）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.benchmark.coverage import SAMPLING_DECLARATION, sample_coverage  # noqa: E402
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "knowledge" / "raw"
DATA = ROOT / "src" / "rca" / "data"
RULES_DIR = DATA / "rules"
SAMPLES = DATA / "samples" / "samples.json"
MANIFEST = DATA / "knowledge" / "MANIFEST.json"

# ---------------------------------------------------------------------------
# 规则定义表：数值与适用条件在此**一处定义**（引擎/报告/文档多处引用）。
#
# 字段说明：
#   anchor  = 用于在快照中定位条款号的**逐字原文**（同时作为 quote 的定位键）
#   quote   = 法条原文逐字引用（必须逐字出现在快照中；可短于 anchor 的上下文）
#   value   = 判定阈值；None 表示"定性检查项，无数值阈值"
# ---------------------------------------------------------------------------

CN = "SRC-CN-CIVIL-CODE"
BJ = "SRC-BJ-HOUSING-RENTAL"
SH = "SRC-SH-HOUSING-RENTAL"
ESCROW = "SRC-BJ-DEPOSIT-ESCROW"

SPECS = {
    "cn": {
        "ruleset_id": "cn-2021.01",
        "city": "全国",
        "city_code": "cn",
        "snapshot": "cn-civil-code.txt",
        "rules": [
            {
                "rule_id": "CN-LEASE-TERM-MAX",
                "title": "租赁期限不得超过二十年",
                "check_type": "numeric_limit",
                "scope": "calc",
                "param": "lease_term_years",
                "op": "<=",
                "value": 20,
                "unit": "年",
                "applies_if": {"party": ["any"]},
                "effect": "standing_obligation",
                "severity": "high",
                "source_id": CN,
                "anchor": "租赁期限不得超过二十年",
                "quote": "租赁期限不得超过二十年。超过二十年的，超过部分无效。",
            },
            {
                "rule_id": "CN-ELEMENT-COMPLETENESS",
                "title": "租赁合同应包含法定要素",
                "check_type": "element_completeness",
                "scope": "check",
                "param": "has_elements",
                "op": None,
                "value": None,
                "unit": None,
                "applies_if": {"party": ["any"]},
                "effect": "standing_obligation",
                "severity": "low",
                "source_id": CN,
                "anchor": "租赁合同的内容一般包括",
                "quote": (
                    "租赁合同的内容一般包括租赁物的名称、数量、用途、租赁期限、"
                    "租金及其支付期限和方式、租赁物维修等条款。"
                ),
                # 要素别名表：合同可用不同措辞满足同一法定要素。
                # 逐字匹配法条措辞会把"已约定"误判成"缺失"（假 noncompliant 比 unknown 更糟）。
                "elements": [
                    {"name": "租赁物的名称", "aliases": ["房屋", "住房", "坐落", "位于", "地址", "房产"]},
                    {"name": "数量", "aliases": ["面积", "套", "间", "室", "平方米"]},
                    {"name": "用途", "aliases": ["用途", "居住", "使用"]},
                    {"name": "租赁期限", "aliases": ["租赁期限", "租期", "期限"]},
                    {"name": "租金及其支付期限和方式", "aliases": ["租金", "支付", "付款"]},
                    {"name": "租赁物维修", "aliases": ["维修", "修缮", "维护"]},
                ],
            },
            {
                "rule_id": "CN-RENT-PAY-PERIOD",
                "title": "租金支付期限未约定时的法定补充规则",
                "check_type": "deadline_obligation",
                "scope": "check",
                "param": "rent_pay_period_declared",
                "op": None,
                "value": None,
                "unit": None,
                "applies_if": {"party": ["any"]},
                "effect": "standing_obligation",
                "severity": "low",
                "source_id": CN,
                "anchor": "承租人应当按照约定的期限支付租金",
                "quote": (
                    "承租人应当按照约定的期限支付租金。对支付租金的期限没有约定或者约定不明确，"
                    "依据本法第五百一十条的规定仍不能确定，租赁期限不满一年的，"
                    "应当在租赁期限届满时支付；租赁期限一年以上的，应当在每届满一年时支付，"
                    "剩余期限不满一年的，应当在租赁期限届满时支付。"
                ),
            },
            {
                # M1 复核新增（HANDOFF-M1 §2.3）。
                # 形态选择：书面形式是"合同文本形态"义务，不是数值义务——用与 704 条同形的
                # 定性检查项承载（要素表即"书面合同应呈现的形态标记"），无需引擎新增判定分支。
                # 输入为可识别书面合同 → 要素齐备 → compliant；输入不可识别为合同 →
                # 引擎判 unknown（"没看到"而非"没采用书面形式"），方向保守不冤枉用户。
                "rule_id": "CN-WRITTEN-FORM-6M",
                "title": "租赁期限六个月以上的应采用书面形式",
                "check_type": "element_completeness",
                "scope": "check",
                "param": "has_elements",
                "op": None,
                "value": None,
                "unit": None,
                "applies_if": {"party": ["any"]},
                "effect": "standing_obligation",
                "severity": "low",
                "source_id": CN,
                "anchor": "租赁期限六个月以上的，应当采用书面形式",
                "quote": (
                    "租赁期限六个月以上的，应当采用书面形式。当事人未采用书面形式，"
                    "无法确定租赁期限的，视为不定期租赁。"
                ),
                "elements": [
                    {"name": "书面签署主体（出租人、承租人）", "aliases": ["出租人", "甲方", "出租方"]},
                    {"name": "书面约定的租赁期限", "aliases": ["租赁期限", "租期", "期限"]},
                ],
            },
        ],
    },
    "bj": {
        "ruleset_id": "bj-2024.10",
        "city": "北京",
        "city_code": "bj",
        "snapshot": "bj-housing-rental.txt",
        "rules": [
            {
                "rule_id": "BJ-DEPOSIT-MAX-1M",
                "title": "住房租赁企业收取的押金一般不得超过一个月租金",
                "check_type": "numeric_limit",
                "scope": "calc",
                "param": "deposit_months",
                "op": "<=",
                "value": 1,
                "unit": "月租金",
                "applies_if": {"party": ["enterprise"]},
                "effect": "standing_obligation",
                "severity": "high",
                "source_id": BJ,
                "anchor": "住房租赁企业向承租人收取的押金一般不得超过一个月租金",
                "quote": (
                    "住房租赁企业向承租人收取的押金一般不得超过一个月租金，"
                    "并按照规定通过第三方专用账户托管。"
                ),
            },
            {
                "rule_id": "BJ-RENT-PREPAY-MAX-3M",
                "title": "住房租赁企业单次收取租金一般不得超过三个月租金",
                "check_type": "numeric_limit",
                "scope": "calc",
                "param": "rent_prepay_months",
                "op": "<=",
                "value": 3,
                "unit": "月租金",
                "applies_if": {"party": ["enterprise"]},
                "effect": "standing_obligation",
                "severity": "high",
                "source_id": BJ,
                "anchor": "住房租赁企业向承租人单次收取租金的数额一般不得超过三个月租金",
                "quote": (
                    "住房租赁企业向承租人单次收取租金的数额一般不得超过三个月租金，"
                    "超收的租金应当纳入监管。"
                ),
            },
            {
                "rule_id": "BJ-FILING-30D",
                "title": "出租人应自合同订立之日起三十日内办理登记备案",
                "check_type": "deadline_obligation",
                "scope": "calc",
                "param": "filing_days",
                "op": "<=",
                "value": 30,
                "unit": "日",
                "applies_if": {"party": ["any"]},
                "effect": "periodic_obligation",
                "severity": "medium",
                "source_id": BJ,
                "anchor": "出租人应当自住房租赁合同订立之日起三十日内",
                "quote": (
                    "出租人应当自住房租赁合同订立之日起三十日内按照规定到租赁住房所在地的"
                    "区住房和城乡建设或者房屋主管部门办理住房租赁登记备案"
                ),
            },
            {
                "rule_id": "BJ-LODGING-REG-3WD",
                "title": "出租人应自合同订立之日起三个工作日内办理出租登记",
                "check_type": "deadline_obligation",
                "scope": "calc",
                "param": "lodging_reg_workdays",
                "op": "<=",
                "value": 3,
                "unit": "工作日",
                "applies_if": {"party": ["any"]},
                "effect": "periodic_obligation",
                "severity": "medium",
                "source_id": BJ,
                "anchor": "出租人应当自住房租赁合同订立之日起三个工作日内",
                "quote": (
                    "出租人应当自住房租赁合同订立之日起三个工作日内，到住房所在地的"
                    "流动人口基层管理服务机构或者通过公安机关指定的信息系统办理出租登记"
                ),
            },
            {
                "rule_id": "BJ-DEPOSIT-REFUND-3WD",
                "title": "应自承租人返还住房后三个工作日内退还剩余押金、租金",
                "check_type": "deadline_obligation",
                "scope": "calc",
                "param": "deposit_refund_workdays",
                "op": "<=",
                "value": 3,
                "unit": "工作日",
                "applies_if": {"party": ["enterprise"]},
                "effect": "periodic_obligation",
                "severity": "high",
                "source_id": BJ,
                "anchor": "住房租赁企业应当自承租人返还住房后三个工作日内向承租人退还剩余押金",
                "quote": (
                    "住房租赁企业应当自承租人返还住房后三个工作日内向承租人退还剩余押金、租金。"
                ),
            },
            {
                "rule_id": "BJ-CONTRACT-ELEMENT-DEPOSIT",
                "title": "住房租赁合同应载明押金数额（一般不超过一个月租金）",
                "check_type": "element_completeness",
                "scope": "check",
                "param": "has_deposit_clause",
                "op": None,
                "value": None,
                "unit": None,
                "applies_if": {"party": ["any"]},
                "effect": "standing_obligation",
                "severity": "medium",
                "source_id": BJ,
                "anchor": "押金数额一般不超过一个月租金",
                "quote": "租金和押金数额、支付期限和方式，押金数额一般不超过一个月租金",
                # M1 复核结论：**有意**只挂押金相关的两项，不铺开第十四条全 10 项。
                # 理由：第十四条的通盘要素完整性已由全国层 CN-ELEMENT-COMPLETENESS（704 条）
                # 承担；本条的价值在于北京特有的"押金数额一般不超过一个月租金"这半句，
                # 故要素清单与之对齐。铺开成全 10 项会与 704 条重复判定同一件事，
                # 同因双报（一个缺失被记两次）反而降低可读性。
                "elements": [
                    {"name": "押金数额", "aliases": ["押金", "保证金"]},
                    {"name": "支付期限和方式", "aliases": ["支付", "付款", "交付方式"]},
                ],
            },
            {
                "rule_id": "BJ-RENT-INTERVENTION",
                "title": "租金明显上涨时市人民政府可采取价格干预措施（监管裁量权）",
                "check_type": "text_prohibition",
                "scope": "quota",
                "param": None,
                "op": None,
                "value": None,
                "unit": None,
                "applies_if": {"party": ["any"]},
                "effect": "conditional_institution",
                "severity": "advisory",
                "source_id": BJ,
                "anchor": "市人民政府可以采取涨价申报、限定租金或者租金涨幅等价格干预措施",
                "quote": (
                    "住房租金明显上涨或者有可能明显上涨时，市人民政府可以采取涨价申报、"
                    "限定租金或者租金涨幅等价格干预措施，稳定租金水平"
                ),
            },
            {
                # 台账 data/README.md §1 #2 承诺的 6 条数值规则之一（此前缺失）。
                # 属企业外部监管义务（非合同条款），合同通常不载明 → 判 unknown，
                # 正是"没看到 ≠ 没问题"的形态。
                "rule_id": "BJ-ENTERPRISE-FILING-30D",
                "title": "住房租赁企业应自领取营业执照之日起三十日内备案",
                "check_type": "numeric_limit",
                "scope": "calc",
                "param": "enterprise_filing_days",
                "op": "<=",
                "value": 30,
                "unit": "日",
                "applies_if": {"party": ["enterprise"]},
                "effect": "periodic_obligation",
                "severity": "medium",
                "source_id": BJ,
                "anchor": "住房租赁企业应当自领取营业执照之日起三十日内向所在地的区住房和城乡建设或者房屋主管部门备案",
                "quote": (
                    "住房租赁企业应当自领取营业执照之日起三十日内向所在地的区住房和城乡建设"
                    "或者房屋主管部门备案。"
                ),
            },
            {
                # 配套办法（京建法〔2024〕8 号）第九条：押金支付与退还的**合同内容**义务。
                # 与第十四条（条例）的押金要素检查分属两份来源，故并存不重复。
                #
                # applies_if 取 enterprise：**配套办法第二条自带适用主体限制**——
                # "本市范围内承租他人住房从事转租业务的住房租赁企业，向承租人收取的押金、
                # 租金的托管、监管及监督管理，适用本办法"。不限定主体会把个人房东也判进去
                # （M1 实测：个人合同上误判成 noncompliant，等于拿不适用他的办法冤枉他）。
                "rule_id": "BJ-ESCROW-DEPOSIT-TERMS",
                "title": "押金应按合同约定的支付时间、金额存入托管账户并按约定时间方式退还",
                "check_type": "element_completeness",
                "scope": "check",
                "param": "has_deposit_clause",
                "op": None,
                "value": None,
                "unit": None,
                "applies_if": {"party": ["enterprise"]},
                "effect": "standing_obligation",
                "severity": "medium",
                "source_id": ESCROW,
                "anchor": "押金应当按住房租赁合同约定的押金支付时间、金额存入用于押金托管的账户",
                "quote": (
                    "押金应当按住房租赁合同约定的押金支付时间、金额存入用于押金托管的账户，"
                    "并按合同约定的时间和方式退还。"
                ),
                "elements": [
                    {"name": "押金支付时间与金额", "aliases": ["押金", "保证金"]},
                    {"name": "押金退还时间与方式", "aliases": ["退还", "返还", "退回"]},
                ],
            },
            {
                # 配套办法第十三条：预收租金超三个月的**条件触发**义务（须全额入监管账户）。
                # 归条件触发栏：原文并不禁止超收，而是"超了就要监管"——判成"违反上限"
                # 是把条件义务说成禁止性义务（失真）。
                "rule_id": "BJ-ESCROW-RENT-SUPERVISION",
                "title": "预收租金超过三个月租金的，全部租金应存入租金监管账户",
                "check_type": "numeric_limit",
                "scope": "quota",
                "param": "rent_prepay_months",
                "op": "<=",
                "value": 3,
                "unit": "月租金",
                "applies_if": {"party": ["enterprise"]},
                "effect": "conditional_institution",
                "severity": "medium",
                "source_id": ESCROW,
                "anchor": "全部租金应当按合同约定的租金支付时间、金额存入用于租金监管的账户",
                "quote": (
                    "住房租赁合同约定预收租金数额超过3个月租金的，全部租金应当按合同约定的"
                    "租金支付时间、金额存入用于租金监管的账户。"
                ),
            },
        ],
    },
    "sh": {
        "ruleset_id": "sh-2023.02",
        "city": "上海",
        "city_code": "sh",
        "snapshot": "sh-housing-rental.txt",
        "rules": [
            {
                "rule_id": "SH-FILING-30D",
                "title": "出租人应自合同订立后三十日内办理登记备案",
                "check_type": "deadline_obligation",
                "scope": "calc",
                "param": "filing_days",
                "op": "<=",
                "value": 30,
                "unit": "日",
                "applies_if": {"party": ["any"]},
                "effect": "periodic_obligation",
                "severity": "medium",
                "source_id": SH,
                "anchor": "出租人应当自住房租赁合同订立后三十日内",
                "quote": "出租人应当自住房租赁合同订立后三十日内，向区房屋管理部门办理登记备案。",
            },
            {
                "rule_id": "SH-RENT-DEPOSIT-ESCROW",
                "title": "超三个月租金部分与超一个月押金部分应存入资金监管专用账户",
                "check_type": "numeric_limit",
                "scope": "calc",
                "param": "deposit_months",
                "op": "<=",
                "value": 1,
                "unit": "月租金",
                "applies_if": {"party": ["enterprise"]},
                "effect": "standing_obligation",
                "severity": "high",
                "source_id": SH,
                "anchor": "住房租赁企业向承租人一次性收取租金超过三个月的部分",
                "quote": (
                    "住房租赁企业向承租人一次性收取租金超过三个月的部分，"
                    "以及收取押金超过一个月租金的部分，应当存入住房租赁交易资金监管专用账户。"
                ),
            },
            {
                "rule_id": "SH-AFFORDABLE-DEPOSIT-1M",
                "title": "保障性租赁住房收取的押金不得超过一个月租金",
                "check_type": "numeric_limit",
                "scope": "calc",
                "param": "deposit_months",
                "op": "<=",
                "value": 1,
                "unit": "月租金",
                "applies_if": {"party": ["any"], "lease_kind": ["affordable"]},
                "effect": "standing_obligation",
                "severity": "high",
                "source_id": SH,
                "anchor": "收取的押金不得超过一个月租金",
                "quote": (
                    "保障性租赁住房租金不得高于备案的租赁价格，并应当按月或者按季度收取；"
                    "收取的押金不得超过一个月租金。"
                ),
            },
            {
                "rule_id": "SH-ENTERPRISE-FILING-30D",
                "title": "住房租赁企业应自领取营业执照之日起三十日内备案",
                "check_type": "deadline_obligation",
                "scope": "calc",
                "param": "enterprise_filing_days",
                "op": "<=",
                "value": 30,
                "unit": "日",
                "applies_if": {"party": ["enterprise"]},
                "effect": "periodic_obligation",
                "severity": "medium",
                "source_id": SH,
                "anchor": "住房租赁企业、房地产经纪机构应当自领取营业执照之日起三十日内",
                "quote": (
                    "住房租赁企业、房地产经纪机构应当自领取营业执照之日起三十日内，"
                    "向区房屋管理部门备案。"
                ),
            },
            {
                # 台账 data/README.md §1 #3 承诺的保租房条款。
                # op 取 ">="：**下限**义务（租期不得少于一年），与上限类规则的边界
                # 断言方向相反——B3 已按 op 分派两个方向，此处正好覆盖"下限"形态。
                "rule_id": "SH-AFFORDABLE-TERM-MIN-1Y",
                "title": "保障性租赁住房租赁期限不得少于一年",
                "check_type": "numeric_limit",
                "scope": "calc",
                "param": "lease_term_years",
                "op": ">=",
                "value": 1,
                "unit": "年",
                "applies_if": {"party": ["any"], "lease_kind": ["affordable"]},
                "effect": "standing_obligation",
                "severity": "medium",
                "source_id": SH,
                "anchor": "保障性租赁住房租赁期限不得少于一年",
                "quote": "除承租人另有要求的，保障性租赁住房租赁期限不得少于一年。",
            },
            {
                # 台账 §1 #3 承诺的罚则（5 万–20 万）。罚则不针对租客合同判定 → quota 栏。
                # 取"下限"数值作 value（5 万），op 用 ">="，边界断言方向为下限。
                "rule_id": "SH-PENALTY-AFFORDABLE-RENT-DEPOSIT",
                "title": "收取租金或押金不符合保租房要求的，处五万元以上二十万元以下罚款",
                "check_type": "numeric_limit",
                "scope": "quota",
                "param": None,
                "op": ">=",
                "value": 50000,
                "unit": "元",
                "applies_if": {"party": ["any"]},
                "effect": "conditional_institution",
                "severity": "advisory",
                "source_id": SH,
                "anchor": "收取的租金或者押金不符合要求的",
                "quote": (
                    "违反本条例第三十七条第二款规定，收取的租金或者押金不符合要求的，"
                    "由区房屋管理部门责令限期改正，处五万元以上二十万元以下罚款。"
                ),
            },
            {
                # 台账 §1 #3 承诺的"骗保 5 年禁申请保障房"。
                # 这是**行政后果**而非合同义务 → effect=conditional_institution 走 quota 栏
                # （HANDOFF-M1 §2.2 明示口径）。
                "rule_id": "SH-BAN-5Y-AFFORDABLE-APPLY",
                "title": "转租、出借保障性租赁住房的，禁止五年内再次申请本市各类保障性住房",
                "check_type": "text_prohibition",
                "scope": "quota",
                "param": None,
                "op": None,
                "value": None,
                "unit": None,
                "applies_if": {"party": ["any"]},
                "effect": "conditional_institution",
                "severity": "advisory",
                "source_id": SH,
                "anchor": "并禁止五年内再次申请本市各类保障性住房",
                "quote": (
                    "违反本条例第三十五条第一款第三项规定，承租人转租、出借保障性租赁住房的，"
                    "由区房屋管理部门责令限期改正，处一万元以上五万元以下罚款，"
                    "并禁止五年内再次申请本市各类保障性住房。"
                ),
            },
        ],
    },
}

# 基准验收门槛：随规则包下发（数据非代码），基准层只读、缺失即报配置错误
THRESHOLDS = {
    "B1_parse_f1_min": 0.95,
    "B2_hit_rate_min": 0.95,
    "B2_false_positive_max": 0,
    "B3_boundary_pass_rate_min": 1.0,
    "max_runtime_seconds": 60,
}

# 条号只在**行首**成立：官方快照里条号一律起于行首（京/沪条例的条号独占一行，
# 民法典的条号后接正文但同样起于行首）。
_CLAUSE = re.compile(r"^[ \t\u3000]*第([一二三四五六七八九十百零〇]+)条", re.M)


def derive_clause(snapshot_text: str, anchor: str, source_id: str) -> str:
    """从快照推导条款号：定位 anchor，回溯到最近的**行首** `第X条`。

    绝不手抄——手抄条款号不可复现（实测同一罚则短语人工定位出两个不同条号）。

    为什么限定行首：正文里的**交叉引用**（"违反本条例第三十七条第二款规定…"）
    也是 `第X条` 形态，若按"任意位置回溯"会把罚则自身的条号错认成被引用的条号
    （M1 实测：上海第六十一条的罚则被推导成第三十七条、第五十九条的罚则被推导成
    第三十五条——条号错认会让报告把罚则挂到错误法条上，比漏报更危险）。
    """
    pos = snapshot_text.find(anchor)
    if pos < 0:
        raise ValueError("anchor 未在快照中逐字出现: [%s] (%s)" % (anchor[:40], source_id))
    best = None
    for m in _CLAUSE.finditer(snapshot_text):
        if m.start() >= pos:
            break
        best = m
    if best is None:
        raise ValueError("anchor 之前无行首条款号: [%s]" % anchor[:40])
    return "第%s条" % best.group(1)


def derive_version(spec: dict, snap_meta_by_id: dict) -> str:
    """从 manifest 推导规则包版本号：**被本包规则引用的来源中，最晚的施行日期**。

    绝不手抄：版本号是"这套规则依据哪一版法规"的唯一标识，写死会与数据脱钩——
    新增/替换一条规则所依据的来源后，版本号若还是旧的，报告会把"依据已更新"
    的判定标成旧版本（读者据此核证会核到错版本的原文）。
    取最晚施行日：包内任一规则引用的来源更新，整套口径即随之变化。

    形如 `YYYY.MM`（月粒度：法规修订以月为发布节奏，日粒度会引入无意义的差异）。
    """
    referenced = {r["source_id"] for r in spec["rules"]}
    dates = []
    for sid in sorted(referenced):
        meta = snap_meta_by_id.get(sid)
        if meta is None:
            raise ValueError("规则引用的来源未在台账登记: %s" % sid)
        eff = meta.get("effective_date")
        if not eff:
            raise ValueError("来源 %s 缺 effective_date，无法推导版本号" % sid)
        dates.append(eff)
    if not dates:
        raise ValueError("规则包未引用任何来源，无法推导版本号")
    latest = max(dates)
    return "%s.%s" % (latest[:4], latest[5:7])


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_samples() -> list:
    """真值库（覆盖登记的**分子**来源）。

    覆盖登记必须"分母 + 分子 + 采样清单"三件套（plan/04 §2.3）——只写分母
    就是假覆盖。分子由真值库的 `expect` / `also_expect` 实算，故生成器需要读样例。
    **缺样例即显式报错**，绝不静默写 0：静默写 0 会让"没采样"与"采样了 0 条"
    长得一样，正是本登记要防的误读。
    """
    if not SAMPLES.is_file():
        raise FileNotFoundError("真值库缺失，先跑 tools/gen_samples.py: %s" % SAMPLES)
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def build_ruleset(key: str) -> dict:
    spec = SPECS[key]
    snap_path = RAW / spec["snapshot"]
    if not snap_path.is_file():
        raise FileNotFoundError("快照缺失，先跑 tools/fetch_sources.py: %s" % snap_path)
    manifest = load_manifest()
    rel_snap = "data/knowledge/raw/%s" % spec["snapshot"]
    snap_meta = next(
        (s for s in manifest["sources"] if s["snapshot"] == rel_snap), None
    )
    if snap_meta is None:
        raise ValueError("台账未登记快照: %s" % rel_snap)

    # 快照正文按 source_id 索引：**一条规则的 quote 必须在它自己声明的来源快照里
    # 逐字出现**，而不是在规则包的主快照里。北京包同时引用《条例》与配套《暂行办法》
    # 两份来源，用主快照做断言会把配套办法的规则误判成"未挂原文"。
    snap_text = {}
    for s in manifest["sources"]:
        p = ROOT / s["snapshot"]
        if p.is_file():
            snap_text[s["source_id"]] = p.read_text(encoding="utf-8")

    rules = []
    for r in spec["rules"]:
        quote = r["quote"]
        sid = r["source_id"]
        own = snap_text.get(sid)
        if own is None:
            raise ValueError("规则 %s 声明的来源无快照: %s" % (r["rule_id"], sid))
        # 硬断言：法条原文逐字出现在**其声明的**官方快照中
        if quote not in own:
            raise ValueError(
                "规则 %s 的 quote 未在快照 %s 中逐字出现: %s"
                % (r["rule_id"], sid, quote[:50])
            )
        clause = derive_clause(own, r["anchor"], sid)
        entry = {
            "rule_id": r["rule_id"],
            "title": r["title"],
            "check_type": r["check_type"],
            "scope": r["scope"],
            "param": r["param"],
            "op": r["op"],
            "value": r["value"],
            "unit": r["unit"],
            "applies_if": r["applies_if"],
            "effect": r["effect"],
            "severity": r["severity"],
            "source_id": r["source_id"],
            "clause": clause,
            "quote": quote,
            "status": "verified",
            "clause_status": "verified",
        }
        if "elements" in r:
            entry["elements"] = r["elements"]
        rules.append(entry)

    # 覆盖登记：**分母 + 分子 + 采样清单** 三件套（plan/04 §2.3）。
    # 分母 = 本包逐形态规则条数；分子 = 真值库对该形态采样到的条数；清单 = 具体哪几条规则、
    # 由哪几份样例提供真值。并声明"抽样覆盖、非逐条穷举"——声明本身就是口径的一部分：
    # 缺了它，读者会把"逐形态登记"读成"逐条穷举过"。
    by_type: dict = {}
    for r in rules:
        by_type[r["check_type"]] = by_type.get(r["check_type"], 0) + 1
    rule_forms = {r["rule_id"]: r["check_type"] for r in rules}
    truth_sampling = sample_coverage(rule_forms, load_samples())

    return {
        "ruleset_id": spec["ruleset_id"],
        "city": spec["city"],
        "city_code": spec["city_code"],
        "version": derive_version(spec, {s["source_id"]: s for s in manifest["sources"]}),
        "generated_by": "tools/gen_rulesets.py",
        "sources": [
            {
                "source_id": s["source_id"],
                "title": s["title"],
                "doc_no": s["doc_no"],
                "effective_date": s["effective_date"],
                "url": s["url"],
                "snapshot": s["snapshot"],
                "snapshot_sha256": s["sha256"],
                "fetched_date": s["fetched_date"],
            }
            for s in manifest["sources"]
        ],
        "benchmark_thresholds": THRESHOLDS,
        "coverage": {
            "note": "规则包条目总数（分母）+ 真值库采样数（分子）+ 采样清单；"
            + SAMPLING_DECLARATION,
            "sampling_declaration": SAMPLING_DECLARATION,
            "rule_totals_by_check_type": dict(sorted(by_type.items())),
            "rule_total": len(rules),
            "truth_sampling": truth_sampling,
            "truth_sampled_total": sum(
                v["sampled_rules"] for v in truth_sampling.values()
            ),
        },
        "rules": rules,
    }


def _dump(obj: dict) -> bytes:
    """确定性序列化：无时间戳、键序稳定、LF 行尾。"""
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode(
        "utf-8"
    )


def cmd_generate() -> int:
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    for key in sorted(SPECS):
        obj = build_ruleset(key)
        out = RULES_DIR / ("ruleset-%s.json" % key)
        out.write_bytes(_dump(obj))
        print(
            "已生成 %s  规则数=%d  sha256=%s"
            % (
                out.relative_to(ROOT).as_posix(),
                len(obj["rules"]),
                hashlib.sha256(out.read_bytes()).hexdigest()[:16],
            )
        )
    return 0


def cmd_check() -> int:
    problems = []
    for key in sorted(SPECS):
        out = RULES_DIR / ("ruleset-%s.json" % key)
        if not out.is_file():
            problems.append("规则包缺失: %s" % out.name)
            continue
        want = _dump(build_ruleset(key))
        have = out.read_bytes()
        if want != have:
            problems.append("规则包与生成器输出不一致（可能被手改）: %s" % out.name)
    if problems:
        for p in problems:
            print("FAIL " + p)
        return 1
    print("RULESETS_FROZEN_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="城市规则包生成器（冻结产物）")
    ap.add_argument("--check", action="store_true", help="位级一致校验")
    args = ap.parse_args(argv)
    try:
        return cmd_check() if args.check else cmd_generate()
    except (ValueError, FileNotFoundError) as exc:
        print("生成失败: %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
