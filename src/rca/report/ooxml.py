"""自写最小 OOXML（XLSX）writer。

为什么不引 openpyxl（决策 D6）：第三方库的 ZIP 元数据（宿主系统标识、
时间戳）会让字节漂移，破坏"同输入逐字节一致"的承诺。

三条字节确定性手段：
- `ZIP_STORED`（不压缩，避开 zlib 版本漂移）
- `create_system=0`（避开平台标识漂移）
- 固定 `date_time=(1980,1,1,0,0,0)`（避开时间戳漂移）
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, List, Sequence

from .sections import Section

__all__ = ["render_xlsx_bytes"]

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def _xml_escape(text: Any) -> str:
    s = "" if text is None else str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _col_name(idx: int) -> str:
    """0 → A, 25 → Z, 26 → AA"""
    name = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def _inline_cell(col: int, row: int, value: Any) -> str:
    ref = "%s%d" % (_col_name(col), row)
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return '<c r="%s"><v>%s</v></c>' % (ref, value)
    return (
        '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
        % (ref, _xml_escape(value))
    )


def _sheet_xml(rows: Sequence[Sequence[Any]]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r_idx, row in enumerate(rows, start=1):
        parts.append('<row r="%d">' % r_idx)
        for c_idx, value in enumerate(row):
            parts.append(_inline_cell(c_idx, r_idx, value))
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="xl/workbook.xml"/>'
    "</Relationships>"
)

_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="体检报告" sheetId="1" r:id="rId1"/></sheets></workbook>'
)

_WB_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
    'Target="worksheets/sheet1.xml"/>'
    "</Relationships>"
)


def _rows_from_sections(sections: List[Section]) -> List[List[Any]]:
    rows: List[List[Any]] = []
    for sec in sections:
        rows.append([sec.title])
        for p in sec.paragraphs:
            rows.append([p])
        if sec.table is not None:
            table: Dict[str, Any] = sec.table
            headers = table.get("headers", [])
            body = table.get("rows", [])
            if headers:
                rows.append(list(headers))
            if body:
                for r in body:
                    rows.append(list(r))
            elif sec.disabled_note:
                rows.append([sec.disabled_note])
        elif sec.disabled_note:
            rows.append([sec.disabled_note])
        rows.append([])
    return rows


def render_xlsx_bytes(sections: List[Section]) -> bytes:
    """确定性 XLSX 字节。同输入两次调用逐字节一致。"""
    rows = _rows_from_sections(sections)
    entries = [
        ("[Content_Types].xml", _CONTENT_TYPES),
        ("_rels/.rels", _ROOT_RELS),
        ("xl/workbook.xml", _WORKBOOK),
        ("xl/_rels/workbook.xml.rels", _WB_RELS),
        ("xl/worksheets/sheet1.xml", _sheet_xml(rows)),
    ]
    entries.sort(key=lambda kv: kv[0])  # 条目显式排序（os.walk 类顺序不稳定）
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, content in entries:
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            zf.writestr(info, content.encode("utf-8"))
    return buf.getvalue()
