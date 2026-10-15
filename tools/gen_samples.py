"""合成合同样例生成器（冻结产物，禁手改）。

纪律（plan/04 §2.1）：
- **禁 stdlib random**：自研确定性 RNG（splitmix64），stdlib random 不承诺跨版本序列一致。
- **禁 set 迭代序、禁系统时钟**：落盘产物无时间戳，两次运行逐字节一致。
- 合成数据纪律：假姓名、假手机号（19900000000 号段），见 data/README.md §3。
- 每个样例的植入真值显式登记在 `expect` / `also_expect`（规则级判定真值），
  以及 `expect_fields` / `expect_absent_fields`（要素抽取真值）——后者是 B1 算
  **字段级 P/R/F1** 的独立来源；缺了它，B1 只能退化成一个布尔式准确率。

用法：
    py -3.12 -X utf8 tools/gen_samples.py           # 生成 data/samples/*.json
    py -3.12 -X utf8 tools/gen_samples.py --check    # 位级一致校验 → SAMPLES_FROZEN_OK
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = ROOT / "data" / "samples"

_MASK = (1 << 64) - 1


class SplitMix64:
    """确定性 RNG（跨版本序列一致，stdlib random 不承诺这点）。"""

    def __init__(self, seed: int) -> None:
        self.state = seed & _MASK

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        return z ^ (z >> 31)

    def choice(self, seq):
        return seq[self.next_u64() % len(seq)]


# 合成数据：假姓名、假手机号（19900000000 号段）
FAKE_NAMES = ["张三", "李四", "王五", "赵六", "钱七", "孙八"]
FAKE_PHONES = ["19900000001", "19900000002", "19900000003", "19900000004"]
COMPANIES = ["北京安心住房租赁有限公司", "上海宜居住房租赁有限公司"]

CONTRACT_TMPL = """{title}

出租人（甲方）：{lessor}
承租人（乙方）：{tenant}
联系电话：{phone}

第一条 甲方将位于{city}{district}的{subject}出租给乙方居住使用，建筑面积 {area} 平方米。
第二条 租赁期限为 {term_text}，自 2026 年 1 月 1 日起至 {end_year} 年 {end_month} 月 1 日止。
第三条 月租金为人民币 {rent} 元，乙方{pay_mode}支付。
第四条 乙方应向甲方支付押金 {deposit} 个月租金，即人民币 {deposit_amount} 元。
第五条 甲方{prepay_text}
第六条 甲方应自合同订立之日起 {filing} 日内办理登记备案，并自合同订立之日起 {lodging} 个工作日内办理出租登记。
第七条 租赁期满，甲方应在乙方返还住房后 {refund} 个工作日内退还押金。
{maintenance}"""

# 维修条款可整条剔除，用于制造"无条件义务缺失 = noncompliant"形态（plan/04 §7 第 2 条）——
# 缺了它，704 条要素完整性只被 compliant 覆盖，缺失分支等于没测。
_MAINTENANCE_CLAUSE = "第八条 房屋及其附属设施的维修责任由甲方承担。\n"

# 非合同文本样例的正文：一段名词释义。**刻意不含**任何租赁关键词
# （租赁/出租/承租/租金/押金）与条号，故引擎判定为"不可识别的合同"：
# 主体 unknown、房屋类型 ordinary，要素类规则判 unknown（"没看到"而非"缺失"）。
# 用于覆盖"一条规则都不适用 → not_assessed，不输出 compliant"（plan/04 §7 第 3 条）。
NON_CONTRACT_TEXT = """住房名词说明

本节说明用于解释若干名词，不构成任何合同条款。
"定金"指为担保履约而预先支付的一笔款项，具体数额由当事人约定。
"保证金"指用于担保履约的款项。
本节既非合同亦非法律意见，仅作名词释义之用。
"""



def _q2(value: Decimal) -> Decimal:
    """两位小数 ROUND_HALF_UP。

    这里**刻意自写**而不 import `rca.parser.extract.q2`：真值必须与引擎**独立同源**
    （plan/04 §5）——若真值借引擎的量化函数算，引擎量化路径改错时真值跟着一起错，
    探活永远绿。
    """
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



def _build_sample(
    rng: SplitMix64,
    idx: int,
    city: str,
    affordable: bool = False,
    term_months: int = None,
    omit_maintenance: bool = False,
    force_enterprise: bool = None,
    non_contract: bool = False,
) -> dict:
    is_bj = city == "北京"
    district = rng.choice(["朝阳区", "海淀区", "西城区"]) if is_bj else rng.choice(["浦东新区", "徐汇区", "静安区"])
    tenant = rng.choice(FAKE_NAMES)
    phone = rng.choice(FAKE_PHONES)
    area = rng.choice(["68", "89", "102", "115"])
    rent = rng.choice(["4500", "5000", "6200", "7800"])
    # term_months 非空时租期按月写（用于触发"保租房租期不得少于一年"的下限违规），
    # 此时不消耗 RNG 的年租期抽签——该样例恒排在末尾，前序样例的序列不受影响。
    if term_months is None:
        term = rng.choice(["1", "2", "3", "21"])
        term_years = int(term)
    else:
        term = None
        term_years = term_months // 12
    deposit = rng.choice(["1", "1", "2", "3"])
    filing = rng.choice(["30", "30", "15", "45"])
    lodging = rng.choice(["3", "3", "5"])
    refund = rng.choice(["3", "3", "5", "7"])
    enterprise = idx % 3 != 2 if force_enterprise is None else force_enterprise

    lessor = COMPANIES[0 if is_bj else 1] if enterprise else "个人出租（%s）" % tenant
    prepay = rng.choice(["3", "3", "6"])
    prepay_text = "单次收取租金 %s 个月，乙方应在签约时一次性支付。" % prepay
    pay_mode = "按月" if prepay == "3" else "按季"

    if term_months is None:
        term_text = "%s 年" % term
        end_year = 2026 + int(term)
        end_month = 1
    else:
        # 单位必须写出来：解析层按「租赁期限…N 个月」形态抽取并做月→年换算，
        # 写成裸数字会抽不到租期（实测：整份样例的租期字段变 absent）。
        term_text = "%d 个月" % term_months
        end_year = 2026 + term_months // 12
        end_month = 1 + term_months % 12

    # 保障性租赁住房样例：合同正文必须出现该字样（解析层据此判定 lease_kind=affordable），
    # 否则保租房专属规则（押金上限、租期下限）永远只走 skipped 分支，等于没测。
    subject = "保障性租赁住房" if affordable else "住房"
    title = "%s%s租赁合同" % (city, "保障性租赁住房" if affordable else "住房")

    text = CONTRACT_TMPL.format(
        title=title,
        city=city,
        lessor=lessor,
        tenant=tenant,
        phone=phone,
        district=district,
        area=area,
        subject=subject,
        term_text=term_text,
        end_year=end_year,
        end_month=end_month,
        rent=rent,
        pay_mode=pay_mode,
        deposit=deposit,
        deposit_amount=str(int(rent) * int(deposit)),
        prepay_text=prepay_text,
        filing=filing,
        lodging=lodging,
        refund=refund,
        maintenance="" if omit_maintenance else _MAINTENANCE_CLAUSE,
    )

    # 非合同文本样例：覆盖 plan/04 §7 第 3 条形态（"一条规则都不适用 → not_assessed，
    # 不输出 compliant"）。现 10 份样例全部是可识别的合同，**没有一份能触发 not_assessed**，
    # 该形态在基准里等于没测。
    if non_contract:
        text = NON_CONTRACT_TEXT

    # 植入真值（主期望）：按规则数值与合同事实逐条推导
    expect = {}
    also = {}
    party = "enterprise" if enterprise else "individual"
    lease_kind = "affordable" if affordable else "ordinary"

    if non_contract:
        # 推导（不读引擎）：文本不可识别为合同 → 无条款、无要素；
        # 主体/房屋类型未知（lease_kind 落到 ordinary）：
        #   - 主体限定类（party=enterprise）→ 无法确定是否适用 → unknown（不是 skipped）
        #   - 保租房专属（lease_kind=affordable）→ 房屋类型明确不满足 → skipped
        #   - 其余（party=any）→ 适用，但要素/数值一律未观测 → unknown
        # 故整体 not_assessed（有 unknown、无 compliant）。
        expect["CN-LEASE-TERM-MAX"] = "unknown"
        expect["CN-ELEMENT-COMPLETENESS"] = "unknown"
        expect["CN-RENT-PAY-PERIOD"] = "unknown"
        expect["CN-WRITTEN-FORM-6M"] = "unknown"
        if is_bj:
            expect["BJ-DEPOSIT-MAX-1M"] = "unknown"
            expect["BJ-RENT-PREPAY-MAX-3M"] = "unknown"
            expect["BJ-DEPOSIT-REFUND-3WD"] = "unknown"
            expect["BJ-ENTERPRISE-FILING-30D"] = "unknown"
            expect["BJ-ESCROW-DEPOSIT-TERMS"] = "unknown"
            expect["BJ-FILING-30D"] = "unknown"
            expect["BJ-LODGING-REG-3WD"] = "unknown"
            expect["BJ-CONTRACT-ELEMENT-DEPOSIT"] = "unknown"
            also["BJ-RENT-INTERVENTION"] = "reference"
            also["BJ-ESCROW-RENT-SUPERVISION"] = "reference"
        else:
            expect["SH-FILING-30D"] = "unknown"
            expect["SH-RENT-DEPOSIT-ESCROW"] = "unknown"
            expect["SH-ENTERPRISE-FILING-30D"] = "unknown"
            expect["SH-AFFORDABLE-DEPOSIT-1M"] = "skipped"
            expect["SH-AFFORDABLE-TERM-MIN-1Y"] = "skipped"
            also["SH-PENALTY-AFFORDABLE-RENT-DEPOSIT"] = "reference"
            also["SH-BAN-5Y-AFFORDABLE-APPLY"] = "reference"
        fields = {"has_deposit_clause": False, "rent_pay_period_declared": False}
        absent = [
            "lease_term_years", "deposit_months", "rent_prepay_months", "filing_days",
            "lodging_reg_workdays", "deposit_refund_workdays", "enterprise_filing_days",
        ]
        return _finish(
            is_bj, idx, city, party, lease_kind, text, expect, also, fields, absent,
            "非合同文本（术语说明）：覆盖「一条规则都不适用 → not_assessed」形态",
        )

    # 全国层：租期 20 年上限 + 704 要素完整性 + 721 法定补充 + 707 书面形式。
    # **每条生效规则都必须登记真值**——否则 B2 的全量对账会把它记成误报，
    # 或者更糟：它从未被任何真值核过（"登记了但没验"）。
    expect["CN-LEASE-TERM-MAX"] = "compliant" if term_years <= 20 else "noncompliant"
    # 704 条要素完整性：剔除维修条 → 缺失法定要素 → **无条件义务缺失 = noncompliant**
    # （plan/04 §7 第 2 条；绝不能记成 skipped）。
    expect["CN-ELEMENT-COMPLETENESS"] = "noncompliant" if omit_maintenance else "compliant"
    # 721 条：合同载明"按月/按季支付" → 已约定 → compliant。
    expect["CN-RENT-PAY-PERIOD"] = "compliant"
    # 707 条：可识别的书面合同 → 要素（签署主体 + 期限）齐备 → compliant。
    expect["CN-WRITTEN-FORM-6M"] = "compliant"

    if is_bj:
        if party == "enterprise":
            expect["BJ-DEPOSIT-MAX-1M"] = "compliant" if int(deposit) <= 1 else "noncompliant"
            expect["BJ-RENT-PREPAY-MAX-3M"] = "compliant" if int(prepay) <= 3 else "noncompliant"
            expect["BJ-DEPOSIT-REFUND-3WD"] = "compliant" if int(refund) <= 3 else "noncompliant"
        else:
            expect["BJ-DEPOSIT-MAX-1M"] = "skipped"
            expect["BJ-RENT-PREPAY-MAX-3M"] = "skipped"
            expect["BJ-DEPOSIT-REFUND-3WD"] = "skipped"
        expect["BJ-FILING-30D"] = "compliant" if int(filing) <= 30 else "noncompliant"
        expect["BJ-LODGING-REG-3WD"] = "compliant" if int(lodging) <= 3 else "noncompliant"
        expect["BJ-CONTRACT-ELEMENT-DEPOSIT"] = "compliant"
        # 企业备案期限是**外部监管义务**：合同不会载明营业执照领取日 → 企业主体判 unknown
        # （"没看到"而非"没问题"）；自然人主体原文写了适用限制 → skipped。
        expect["BJ-ENTERPRISE-FILING-30D"] = "unknown" if party == "enterprise" else "skipped"
        # 配套办法（京建法〔2024〕8 号）第九条：押金支付/退还条款须载明。
        # 该办法第二条自带主体限制（"承租他人住房从事转租业务的住房租赁企业"），
        # 故自然人主体判 skipped——拿不适用于他的办法判 noncompliant 是冤枉用户。
        expect["BJ-ESCROW-DEPOSIT-TERMS"] = "compliant" if party == "enterprise" else "skipped"
        also["BJ-RENT-INTERVENTION"] = "reference"
        also["BJ-ESCROW-RENT-SUPERVISION"] = "reference"
    else:
        expect["SH-FILING-30D"] = "compliant" if int(filing) <= 30 else "noncompliant"
        if affordable:
            # 保租房专属：押金上限 1 个月、租期下限 1 年（applies_if 命中，走实判）
            expect["SH-AFFORDABLE-DEPOSIT-1M"] = (
                "compliant" if int(deposit) <= 1 else "noncompliant"
            )
            expect["SH-AFFORDABLE-TERM-MIN-1Y"] = (
                "compliant" if term_years >= 1 else "noncompliant"
            )
        else:
            expect["SH-AFFORDABLE-DEPOSIT-1M"] = "skipped"  # 非保障性租赁住房
            expect["SH-AFFORDABLE-TERM-MIN-1Y"] = "skipped"
        if party == "enterprise":
            expect["SH-RENT-DEPOSIT-ESCROW"] = "compliant" if int(deposit) <= 1 else "noncompliant"
            expect["SH-ENTERPRISE-FILING-30D"] = "unknown"
        else:
            expect["SH-RENT-DEPOSIT-ESCROW"] = "skipped"
            expect["SH-ENTERPRISE-FILING-30D"] = "skipped"
        also["SH-PENALTY-AFFORDABLE-RENT-DEPOSIT"] = "reference"
        also["SH-BAN-5Y-AFFORDABLE-APPLY"] = "reference"

    term_desc = ("%d 个月" % term_months) if term_months is not None else ("%s 年" % term)
    return _finish(
        is_bj, idx, city, party, lease_kind, text, expect, also,
        fields=_expected_fields(
            term_months, term_years, deposit, prepay, filing, lodging, refund
        ),
        absent=["enterprise_filing_days"],
        notes="合成样例：假姓名/假手机号；%s；租期%s、押金%s个月、单次收租%s个月、备案%s日、出租登记%s工作日、退押金%s工作日"
        % (
            "保障性租赁住房" if affordable else "普通租赁住房",
            term_desc,
            deposit,
            prepay,
            filing,
            lodging,
            refund,
        ),
    )


def _expected_fields(term_months, term_years, deposit, prepay, filing, lodging, refund):
    """真值侧的**要素抽取期望值**（B1 字段级 P/R/F1 的独立来源）。

    与引擎完全独立：这里直接由生成器的入参（合同里写了什么）推期望值，
    不调用引擎的抽取函数。引擎抽错时，这份期望不会跟着错——这是探活的前提
    （plan/04 §5"期望必须有独立来源"）。
    """
    if term_months is None:
        term_value = str(_q2(Decimal(term_years)))
    else:
        term_value = str(_q2(Decimal(term_months) / Decimal(12)))
    return {
        "lease_term_years": term_value,
        "deposit_months": str(_q2(Decimal(deposit))),
        "rent_prepay_months": str(_q2(Decimal(prepay))),
        "filing_days": str(_q2(Decimal(filing))),
        "lodging_reg_workdays": str(_q2(Decimal(lodging))),
        "deposit_refund_workdays": str(_q2(Decimal(refund))),
        "has_deposit_clause": True,
        "rent_pay_period_declared": True,
    }


def _finish(is_bj, idx, city, party, lease_kind, text, expect, also, fields, absent, notes):
    return {
        "sample_id": "S-%s-%03d" % ("BJ" if is_bj else "SH", idx),
        "city": city,
        "party": party,
        "lease_kind": lease_kind,
        "contract_text": text,
        "expect": dict(sorted(expect.items())),
        "also_expect": dict(sorted(also.items())),
        # 要素抽取真值：`expect_fields` 登记"应有值的字段 → 期望取值"，
        # `expect_absent_fields` 登记"应观测不到（absent）的字段"。
        # 二者是 B1 算 P/R/F1 的**独立来源**；缺了它 B1 只能退化成布尔式准确率
        # （"有值就有证据"），precision / recall 无从谈起（plan/04 §1）。
        "expect_fields": dict(sorted(fields.items())),
        "expect_absent_fields": sorted(absent),
        "notes": notes,
    }


def build_samples() -> list:
    rng = SplitMix64(20261015)
    out = []
    for i in range(1, 9):
        city = "北京" if i <= 4 else "上海"
        out.append(_build_sample(rng, i, city))
    # 第 9–10 份：保障性租赁住房（上海）。新增在**末尾**——前 8 份的 RNG 消耗序列不变，
    # 故 S-BJ-001（README 演示合同）与其余样例逐字节不动。
    # S-SH-009 租期 3 年（满足下限）；S-SH-010 租期 9 个月（**违反**"不得少于一年"下限）——
    # 下限类规则必须有违规样例，否则该分支永远只被 compliant 覆盖（等于没测）。
    out.append(_build_sample(rng, 9, "上海", affordable=True))
    out.append(_build_sample(rng, 10, "上海", affordable=True, term_months=9))
    # 第 11 份：剔除维修条 → 704 条要素完整性判 **noncompliant**。
    # 覆盖 plan/04 §7 第 2 条"无条件义务缺失 = noncompliant（不是 skipped）"——
    # 此前 10 份样例的 704 条恒为 compliant，该形态在基准里等于没测。
    out.append(_build_sample(rng, 11, "北京", omit_maintenance=True, force_enterprise=True))
    # 第 12 份：非合同文本 → 无任何可判定项 → 整体 **not_assessed**（绝不输出 compliant）。
    # 覆盖 plan/04 §7 第 3 条。此前无一份样例能触发 not_assessed。
    out.append(_build_sample(rng, 12, "北京", non_contract=True))
    return out


def _dump(samples: list) -> bytes:
    return (
        json.dumps(samples, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


# README 快速开始引用的**可直接喂给 CLI** 的演示合同。
# 纪律（skill 阶段 7）：README 里那条命令的输入必须由生成器保证存在——
# 否则本地因工作目录残留看着能跑，干净环境当场 exit 2。
DEMO_SAMPLE_ID = "S-BJ-001"
DEMO_FILENAME = "demo-contract-bj.txt"


def _demo_text(samples: list) -> bytes:
    target = next(s for s in samples if s["sample_id"] == DEMO_SAMPLE_ID)
    return target["contract_text"].encode("utf-8")


def cmd_generate() -> int:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    samples = build_samples()
    out = SAMPLES_DIR / "samples.json"
    out.write_bytes(_dump(samples))
    demo = SAMPLES_DIR / DEMO_FILENAME
    demo.write_bytes(_demo_text(samples))
    print(
        "已生成 %s  样例数=%d  sha256=%s"
        % (
            out.relative_to(ROOT).as_posix(),
            len(samples),
            hashlib.sha256(out.read_bytes()).hexdigest()[:16],
        )
    )
    print("已生成演示合同 %s（README 快速开始直接引用）" % demo.relative_to(ROOT).as_posix())
    return 0


def cmd_check() -> int:
    out = SAMPLES_DIR / "samples.json"
    if not out.is_file():
        print("FAIL 样例文件缺失: %s" % out.name)
        return 1
    if _dump(build_samples()) != out.read_bytes():
        print("FAIL 样例与生成器输出不一致（可能被手改）")
        return 1
    demo = SAMPLES_DIR / DEMO_FILENAME
    if not demo.is_file():
        print("FAIL 演示合同缺失: %s（README 引用它）" % DEMO_FILENAME)
        return 1
    if _demo_text(build_samples()) != demo.read_bytes():
        print("FAIL 演示合同与生成器输出不一致")
        return 1
    print("SAMPLES_FROZEN_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="合成合同样例生成器（冻结产物）")
    ap.add_argument("--check", action="store_true", help="位级一致校验")
    args = ap.parse_args(argv)
    return cmd_check() if args.check else cmd_generate()


if __name__ == "__main__":
    raise SystemExit(main())
