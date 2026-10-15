"""GUI 分层与装配测试。

offscreen 常驻：`QT_QPA_PLATFORM=offscreen` 必须在**首次导入 PySide6 前**设置。
缺 PySide6 时整模块声明式跳过（`importorskip`）——GUI 是可选功能，
但核心层能力（引擎/报告/基准）不因缺 extra 而放过。
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]

pytest.importorskip("PySide6", reason="GUI 为可选功能，缺 [gui] extra 时跳过")


def test_gui_builds_window():
    from rca.gui.app import build_app

    app, window = build_app()
    assert window.windowTitle()
    assert window.centralWidget() is not None


def test_gui_has_expected_tabs():
    from rca.gui.app import build_app

    app, window = build_app()
    tabs = window.centralWidget()
    assert tabs.count() >= 2


def test_gui_does_no_arithmetic_in_source():
    """"零判定逻辑"的 AST 守门第二条：界面层不得做算术运算。

    字符串的 `*`/`+` 是排版，不算；`Path / "seg"` 是路径拼接，也不是算术。
    只抓两侧操作数**均非字符串字面量且非路径拼接**的
    `*` `/` `-` `//` `%` `**`。
    """
    banned = (ast.Mult, ast.Div, ast.Sub, ast.FloorDiv, ast.Mod, ast.Pow)

    def _is_str_const(node):
        return isinstance(node, ast.Constant) and isinstance(node.value, str)

    def _is_path_join(node):
        """`Path(...) / "seg"` 形态：任一侧是 Path 调用，或另一侧是字符串字面量。"""
        for side in (node.left, node.right):
            if isinstance(side, ast.Call):
                func = side.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name in ("Path", "joinpath"):
                    return True
        # 一侧为字符串字面量的 `/` 视为路径拼接（路径分隔语义）
        if isinstance(node.op, ast.Div) and (_is_str_const(node.left) or _is_str_const(node.right)):
            return True
        return False

    for py in (ROOT / "src" / "rca" / "gui").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, banned):
                if _is_str_const(node.left) and _is_str_const(node.right):
                    continue
                # `"fmt" % value` 左侧是字符串字面量 = 字符串格式化，恒非算术
                if isinstance(node.op, ast.Mod) and _is_str_const(node.left):
                    continue
                if isinstance(node.op, ast.Mod) and isinstance(node.right, ast.Tuple):
                    continue
                if _is_path_join(node):
                    continue
                raise AssertionError(
                    "%s:%d 界面层出现算术运算（应经 pipeline 取数）"
                    % (py.relative_to(ROOT).as_posix(), node.lineno)
                )


def test_gui_imports_only_pipeline_from_engine():
    """GUI 唯一入口是 engine.pipeline（不直接 import 引擎内部模块）。"""
    for py in (ROOT / "src" / "rca" / "gui").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                for inner in ("checker", "ruleset", "benchmark", "parser"):
                    assert not mod.endswith(inner), (
                        "%s import 了引擎内部模块 %s（唯一入口应为 pipeline）"
                        % (py.relative_to(ROOT).as_posix(), mod)
                    )


def test_gui_has_no_policy_literals():
    """界面层不得内联政策数值（与引擎侧同一份 token 面）。"""
    import json
    import re

    tokens = set()
    rules_dir = ROOT / "data" / "rules"
    for p in sorted(rules_dir.glob("ruleset-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        for r in data.get("rules", []):
            v = r.get("value")
            if isinstance(v, int) and not isinstance(v, bool) and v >= 10:
                tokens.add(str(v))
    pats = [(t, re.compile(r"(?<![\d.])" + re.escape(t) + r"(?![\d])")) for t in tokens]
    for py in (ROOT / "src" / "rca" / "gui").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token, pat in pats:
            assert not pat.search(text), "%s 含政策数值 %s" % (py.name, token)
