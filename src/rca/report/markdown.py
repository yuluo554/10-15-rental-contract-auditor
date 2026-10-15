"""人读渲染（Markdown）。消费 report_sections()，不自己组装内容。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..model import Result
from .sections import Section, coverage_rows, report_sections

__all__ = ["render_markdown"]


def _table_md(table: Dict[str, Any]) -> List[str]:
    headers: List[str] = table.get("headers", [])
    rows: List[List[Any]] = table.get("rows", [])
    if not headers:
        return []
    out = ["| " + " | ".join(str(h) for h in headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        out.append("| " + " | ".join(cells) + " |")
    return out


def render_sections(sections: List[Section]) -> str:
    lines: List[str] = []
    for sec in sections:
        lines.append("## %s" % sec.title)
        lines.append("")
        for p in sec.paragraphs:
            lines.append(p)
            lines.append("")
        if sec.table is not None:
            rows = sec.table.get("rows", [])
            if rows:
                lines.extend(_table_md(sec.table))
                lines.append("")
            elif sec.disabled_note:
                lines.append(sec.disabled_note)
                lines.append("")
        elif sec.disabled_note:
            lines.append(sec.disabled_note)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(
    result: Result,
    sources_rows: List[List[str]] | None = None,
    coverage: Optional[Dict[str, Any]] = None,
) -> str:
    """渲染完整报告。sources_rows 由调用方从 parameter_overview 构造，
    coverage 由调用方从规则包 manifest 的 `coverage` 段取（分母+分子+采样清单）。"""
    sections = report_sections(result)
    if sources_rows is not None:
        for sec in sections:
            if sec.key == "sources":
                sec.table = {
                    "headers": ["规则 ID", "条款号", "来源文件", "文号", "施行日期", "URL"],
                    "rows": sources_rows,
                }
    if coverage is not None:
        rows = coverage_rows(coverage)
        for sec in sections:
            if sec.key == "coverage":
                sec.table = {
                    "headers": ["规则形态", "规则条数（分母）", "真值库采样条数（分子）", "采样清单"],
                    "rows": rows,
                }
                sec.enabled = bool(rows)
                sec.disabled_note = None if rows else "规则包未登记覆盖采样信息。"
    body = render_sections(sections)
    return body
