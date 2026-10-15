"""报告层测试：单一渲染源、溯源硬约束、字节确定性、无外链、免责声明。
"""

from __future__ import annotations

import hashlib
import io
import re
import time
import zipfile
from pathlib import Path

import pytest

from rca.engine.pipeline import compute_result, parameter_overview
from rca.report.markdown import render_markdown
from rca.report.ooxml import render_xlsx_bytes
from rca.report.sections import (
    DISCLAIMER,
    FORBIDDEN_PHRASES,
    TraceabilityError,
    assert_traceable,
    report_sections,
)


def _sources_rows(city, data_dir):
    return [
        [p["rule_id"], p["clause"] or "—", p["source_title"] or "—",
         p["doc_no"] or "—", p["effective_date"] or "—", p["url"] or "—"]
        for p in parameter_overview(city, data_dir)
    ]


def test_sections_include_required_blocks(bj_enterprise, data_dir):
    """报告必含四块：输入事实 / 判定明细 / 参数来源 / 免责声明。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    keys = {s.key for s in report_sections(result)}
    assert {"input", "findings", "sources", "disclaimer"} <= keys


def test_disclaimer_present_in_markdown(bj_enterprise, data_dir):
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    md = render_markdown(result, _sources_rows("北京", data_dir))
    assert DISCLAIMER in md


def test_no_forbidden_phrases(bj_enterprise, data_dir):
    """法律红线：不得出现"律师审查""法律效力"等表述。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    md = render_markdown(result, _sources_rows("北京", data_dir))
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in md, "报告出现禁用表述：%s" % phrase


def test_markdown_has_no_external_links(bj_enterprise, data_dir):
    """无外链：Markdown 里不得有 ](http 形式的外链（URL 以文本形式呈现是允许的）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    md = render_markdown(result, _sources_rows("北京", data_dir))
    assert not re.search(r"\]\(https?://", md), "报告含 Markdown 外链"


def test_xlsx_has_no_external_relationships(bj_enterprise, data_dir):
    """XLSX 无 External 关系（断网可开）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    sections = report_sections(result)
    for s in sections:
        if s.key == "sources":
            s.table = {"headers": ["a", "b", "c", "d", "e", "f"],
                       "rows": _sources_rows("北京", data_dir)}
    blob = render_xlsx_bytes(sections)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for name in zf.namelist():
            if name.endswith(".rels"):
                content = zf.read(name).decode("utf-8")
                assert "External" not in content, "%s 含外部关系" % name


def test_xlsx_is_byte_deterministic(bj_enterprise, data_dir):
    """XLSX 同输入逐字节一致（跨秒也要一致——时间戳必须钉死）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    a = render_xlsx_bytes(report_sections(result))
    time.sleep(1.1)
    b = render_xlsx_bytes(report_sections(result))
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_markdown_is_byte_deterministic(bj_enterprise, data_dir):
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    a = render_markdown(result, _sources_rows("北京", data_dir))
    time.sleep(1.1)
    b = render_markdown(result, _sources_rows("北京", data_dir))
    assert a.encode("utf-8") == b.encode("utf-8")


def test_xlsx_zip_entries_frozen_metadata(bj_enterprise, data_dir):
    """zip 容器层：create_system=0 + 固定 date_time（跨平台重生成位级一致）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    blob = render_xlsx_bytes(report_sections(result))
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in zf.infolist():
            assert info.create_system == 0, "%s create_system != 0" % info.filename
            assert info.date_time == (1980, 1, 1, 0, 0, 0), "%s 时间戳未钉死" % info.filename


def test_two_formats_share_single_render_source(bj_enterprise, data_dir):
    """两格式"内容一致"是结构性质：从两种产物抽内容做逐项对等断言。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    sections = report_sections(result)
    md = render_markdown(result, _sources_rows("北京", data_dir))

    blob = render_xlsx_bytes(sections)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")

    # 章节标题与规则 ID 必须在两种产物里都出现
    for sec in sections:
        assert sec.title in md
        assert sec.title in sheet
    for f in result.findings:
        assert f.rule_id in md
        assert f.rule_id in sheet


def test_traceability_assertion_rejects_incomplete(bj_enterprise, data_dir):
    """溯源硬约束：行数不匹配即拒绝导出（不留半溯源报告）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    with pytest.raises(TraceabilityError):
        assert_traceable(result, [["ONLY-ONE-ROW", "—", "—", "—", "—", "—"]])


def test_traceability_assertion_accepts_complete(bj_enterprise, data_dir):
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    assert_traceable(result, _sources_rows("北京", data_dir))


def test_disabled_section_states_not_checked(bj_enterprise, data_dir):
    """"未启用"章节必须显式写出（"没查"与"查了没问题"是两种结论）。"""
    result = compute_result(bj_enterprise, "北京", data_dir=data_dir)
    md = render_markdown(result, _sources_rows("北京", data_dir))
    assert "未参与本次判定" in md or "未启用" in md
