"""城市规则包生成器（冻结产物，禁手改）。

纪律（plan/02 §3，skill 阶段 1"标准类数据的转录必须脚本转写 + 原文逐字包含断言"）：
- **条款号由快照推导**，不手抄：定位 `quote` 在快照中的位置，回溯到最近的 `第X条`。
  手抄条款号必然引入不可复现的漂移（本项目实测：同一罚则短语人工定位到两个不同条号）。
- **每处抽取值断言原文逐字包含**：`assert quote in snapshot_text`，失败即生成失败。
- 产物无时间戳、字典序稳定 → 两次运行逐字节一致（`--check` 守门）。

用法：
    py -3.12 -X utf8 tools/gen_rulesets.py            # 生成 data/rules/ruleset-*.json
    py -3.12 -X utf8 tools/gen_rulesets.py --check     # 位级一致校验，输出 RULESETS_FROZEN_OK
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "knowledge" / "raw"
RULES_DIR = ROOT / "data" / "rules"
MANIFEST = ROOT / "data" / "knowledge" / "MANIFEST.json"

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

SPECS = {
    "cn": {
        "ruleset_id": "cn-2021.01",
        "city": "全国",
        "city_code": "cn",
        "version": "2021.01",
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
        ],
    },
    "bj": {
        "ruleset_id": "bj-2024.10",
        "city": "北京",
        "city_code": "bj",
        "version": "2024.10",
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
        ],
    },
    "sh": {
        "ruleset_id": "sh-2023.02",
        "city": "上海",
        "city_code": "sh",
        "version": "2023.02",
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

_CLAUSE = re.compile(r"第([一二三四五六七八九十百零〇]+)条")


def derive_clause(snapshot_text: str, anchor: str, source_id: str) -> str:
    """从快照推导条款号：定位 anchor，回溯到最近的 `第X条`。

    绝不手抄——手抄条款号不可复现（实测同一罚则短语人工定位出两个不同条号）。
    """
    pos = snapshot_text.find(anchor)
    if pos < 0:
        raise ValueError("anchor 未在快照中逐字出现: [%s] (%s)" % (anchor[:40], source_id))
    best = None
    for m in _CLAUSE.finditer(snapshot_text, 0, pos + 1):
        best = m
    if best is None:
        raise ValueError("anchor 之前无条款号: [%s]" % anchor[:40])
    return "第%s条" % best.group(1)


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def build_ruleset(key: str) -> dict:
    spec = SPECS[key]
    snap_path = RAW / spec["snapshot"]
    if not snap_path.is_file():
        raise FileNotFoundError("快照缺失，先跑 tools/fetch_sources.py: %s" % snap_path)
    text = snap_path.read_text(encoding="utf-8")
    manifest = load_manifest()
    rel_snap = "data/knowledge/raw/%s" % spec["snapshot"]
    snap_meta = next(
        (s for s in manifest["sources"] if s["snapshot"] == rel_snap), None
    )
    if snap_meta is None:
        raise ValueError("台账未登记快照: %s" % rel_snap)

    rules = []
    for r in spec["rules"]:
        quote = r["quote"]
        # 硬断言：法条原文逐字出现在官方快照中
        if quote not in text:
            raise ValueError(
                "规则 %s 的 quote 未在快照中逐字出现: %s" % (r["rule_id"], quote[:50])
            )
        clause = derive_clause(text, r["anchor"], r["source_id"])
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

    # 覆盖登记：总数 / 采样数（基准层填采样数，此处先登记总数）
    by_type: dict = {}
    for r in rules:
        by_type[r["check_type"]] = by_type.get(r["check_type"], 0) + 1

    return {
        "ruleset_id": spec["ruleset_id"],
        "city": spec["city"],
        "city_code": spec["city_code"],
        "version": spec["version"],
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
            "note": "规则包条目总数按 check_type 登记；真值库采样数由基准层填充（plan/04 §2.3）",
            "rule_totals_by_check_type": dict(sorted(by_type.items())),
            "rule_total": len(rules),
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
