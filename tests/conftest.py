"""测试套件共享夹具。

纪律：测试全离线、零 API 依赖（K6）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DATA_DIR = SRC / "rca" / "data"


def write_text_lf(path, text: str) -> None:
    """确定性写文本（LF 行尾）。

    **不要用 `Path.write_text(newline=)`**——那是 Python 3.10+ 参数，
    3.8 通道上会 `TypeError`。走 `write_bytes` 才是全版本一致的做法
    （也正是 EOL 门要求生成器采用的形态）。
    """
    Path(path).write_bytes(text.encode("utf-8"))

# 合成合同（假姓名/假手机号 19900000000 号段，见 data/README.md §3）
BJ_ENTERPRISE_CONTRACT = """北京市住房租赁合同

出租人（甲方）：北京安心住房租赁有限公司
承租人（乙方）：张三
联系电话：19900000001

第一条 甲方将位于北京市朝阳区的住房出租给乙方居住使用，建筑面积 89 平方米。
第二条 租赁期限为 3 年，自 2026 年 1 月 1 日起至 2029 年 1 月 1 日止。
第三条 月租金为人民币 5000 元，乙方按季支付。
第四条 乙方应向甲方支付押金 2 个月租金，即人民币 10000 元。
第五条 甲方单次收取租金 6 个月，乙方应在签约时一次性支付。
第六条 甲方应自合同订立之日起 30 日内办理登记备案。
第七条 租赁期满，甲方应在乙方返还住房后 5 个工作日内退还押金。
第八条 房屋及其附属设施的维修责任由甲方承担。
"""

BJ_COMPLIANT_CONTRACT = """北京市住房租赁合同

出租人（甲方）：北京安心住房租赁有限公司
承租人（乙方）：李四
联系电话：19900000002

第一条 甲方将位于北京市海淀区的住房出租给乙方居住使用，建筑面积 68 平方米。
第二条 租赁期限为 2 年。
第三条 月租金为人民币 5000 元，乙方按月支付。
第四条 乙方应向甲方支付押金 1 个月租金。
第五条 甲方单次收取租金 3 个月。
第六条 甲方应自合同订立之日起 30 日内办理登记备案。
第七条 租赁期满，甲方应在乙方返还住房后 3 个工作日内退还押金。
第八条 房屋及其附属设施的维修责任由甲方承担。
"""

INDIVIDUAL_CONTRACT = """北京市住房租赁合同

出租人（甲方）：个人出租（王五）
承租人（乙方）：赵六
联系电话：19900000003

第一条 甲方将位于北京市西城区的住房出租给乙方居住使用，建筑面积 55 平方米。
第二条 租赁期限为 1 年。
第三条 月租金为人民币 4500 元，乙方按月支付。
第四条 乙方应向甲方支付押金 2 个月租金。
第五条 甲方应自合同订立之日起 30 日内办理登记备案。
第六条 房屋及其附属设施的维修责任由甲方承担。
"""

OVERLONG_TERM_CONTRACT = """北京市住房租赁合同

出租人（甲方）：北京安心住房租赁有限公司
承租人（乙方）：张三
联系电话：19900000004

第一条 甲方将位于北京市朝阳区的住房出租给乙方居住使用，建筑面积 89 平方米。
第二条 租赁期限为 25 年。
第三条 月租金为人民币 5000 元，乙方按月支付。
第四条 乙方应向甲方支付押金 1 个月租金。
第五条 甲方单次收取租金 3 个月。
第六条 甲方应自合同订立之日起 30 日内办理登记备案。
第七条 租赁期满，甲方应在乙方返还住房后 3 个工作日内退还押金。
第八条 房屋及其附属设施的维修责任由甲方承担。
"""


@pytest.fixture
def data_dir() -> str:
    return str(DATA_DIR)


@pytest.fixture
def bj_enterprise() -> str:
    return BJ_ENTERPRISE_CONTRACT


@pytest.fixture
def bj_compliant() -> str:
    return BJ_COMPLIANT_CONTRACT


@pytest.fixture
def individual() -> str:
    return INDIVIDUAL_CONTRACT


@pytest.fixture
def overlong_term() -> str:
    return OVERLONG_TERM_CONTRACT
