"""解析层：合同文本 → 条款序列 → 合同卡片。

规则优先：正则 + 槽位 + 合法性校验；失败降级到显式第三态（pending_manual）。
"""

from .clauses import split_clauses
from .extract import build_card

__all__ = ["split_clauses", "build_card"]
