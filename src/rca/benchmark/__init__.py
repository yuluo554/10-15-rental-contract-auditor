"""基准层（模块⑤）。

三套件（plan/04）：
  B1 解析基准   —— 样本驱动：要素抽取字段级 P/R/F1
  B2 端到端判定 —— 样本驱动：判定状态命中率 / 误报率
  B3 规则驱动边界 —— 不读真值库：从规则表推导端点做 ±精度邻域断言

退出码三语义：0 达标 / 1 未达标或门控拦截 / 2 用法错误。
验收门槛**随规则包下发**（数据非代码），缺失即配置错误（exit 2）。
"""

from .cases import compare_nonpass, observed_nonpass
from .runner import run_benchmarks

__all__ = ["run_benchmarks", "compare_nonpass", "observed_nonpass"]
