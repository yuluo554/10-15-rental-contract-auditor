"""报告层。

单一渲染源：`report_sections()` 返回结构化章节，Markdown 与 XLSX 渲染器
各自读它——于是"两格式内容一致"是**结构性质**，不是人工比对。
"""

from .sections import report_sections, Section, DISCLAIMER

__all__ = ["report_sections", "Section", "DISCLAIMER"]
