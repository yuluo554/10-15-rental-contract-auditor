"""基准层（模块⑤）。

三套件（plan/04）：
  B1 解析基准   —— 样本驱动：要素抽取**字段级 P/R/F1**（真值侧登记"应有字段"）
  B2 端到端判定 —— 样本驱动：判定状态命中率 / 误报率（全量真值对账，含 also_expect）
  B3 规则驱动边界 —— 不读真值库：从规则表推导端点做 ±精度邻域断言

退出码三语义：0 达标 / 1 未达标或门控拦截 / 2 用法错误。
验收门槛**随规则包下发**（数据非代码），缺失即配置错误（exit 2）。

覆盖登记（plan/04 §2.3）：`coverage.py` 是"分母 + 分子 + 采样清单"三件套的
单一实现源，供生成器、基准、CLI、报告共用。
"""

from .cases import compare_exact, compare_nonpass, observed_nonpass
from .coverage import CHECK_TYPE_FORMS, coverage_gaps, sample_coverage
from .runner import run_benchmarks

__all__ = [
    "run_benchmarks",
    "compare_nonpass",
    "compare_exact",
    "observed_nonpass",
    "sample_coverage",
    "coverage_gaps",
    "CHECK_TYPE_FORMS",
]
