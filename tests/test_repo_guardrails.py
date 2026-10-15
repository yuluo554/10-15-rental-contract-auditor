"""仓库守门测试：生成器冻结、EOL、零字面量门禁、脱敏审计、分层纪律。

这些守门随全量测试常驻——"本地全绿"与"CI 绿"从此是同一道闸门。
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _run(args, **kw):
    return subprocess.run(
        [sys.executable] + args,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        **kw,
    )


# --------------------------------------------------------------------------
# 生成器冻结：改数据必须走生成器整目录重生成
# --------------------------------------------------------------------------

def test_rulesets_frozen():
    proc = _run([str(ROOT / "tools" / "gen_rulesets.py"), "--check"])
    assert proc.returncode == 0, proc.stdout
    assert "RULESETS_FROZEN_OK" in proc.stdout


def test_samples_frozen():
    proc = _run([str(ROOT / "tools" / "gen_samples.py"), "--check"])
    assert proc.returncode == 0, proc.stdout
    assert "SAMPLES_FROZEN_OK" in proc.stdout


def test_sources_frozen():
    """官方快照 sha256 与台账一致（检出后重算，防 EOL 归一化）。"""
    import hashlib
    import json

    manifest = json.loads((DATA / "knowledge" / "MANIFEST.json").read_text(encoding="utf-8"))
    for s in manifest["sources"]:
        p = ROOT / s["snapshot"]
        assert p.is_file(), "快照缺失: %s" % s["snapshot"]
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == s["sha256"], "快照 sha256 失配: %s" % s["snapshot"]


# --------------------------------------------------------------------------
# EOL 门：冻结件出现 CR 即大声失败（字节冻结的前提）
# --------------------------------------------------------------------------

FROZEN_FILES = [
    "data/knowledge/raw/cn-civil-code.txt",
    "data/knowledge/raw/bj-housing-rental.txt",
    "data/knowledge/raw/sh-housing-rental.txt",
    "data/knowledge/raw/bj-deposit-escrow.txt",
    "data/rules/ruleset-bj.json",
    "data/rules/ruleset-sh.json",
    "data/rules/ruleset-cn.json",
    "data/samples/samples.json",
]


@pytest.mark.parametrize("rel", FROZEN_FILES)
def test_frozen_files_have_no_cr(rel):
    data = (ROOT / rel).read_bytes()
    assert b"\r" not in data, "冻结件含 CR（应为 LF）: %s" % rel


def test_gitattributes_marks_snapshots_as_binary_text():
    """官方快照必须标 -text（否则克隆时 EOL 归一化让 sha256 失配）。"""
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "data/knowledge/raw/*.txt -text" in text
    assert "eol=lf" in text


# --------------------------------------------------------------------------
# 零政策字面量门禁（扫描引擎/基准/报告/解析/CLI 源码）
# --------------------------------------------------------------------------

def test_literal_gate_passes():
    proc = _run([str(ROOT / "tools" / "check_literals.py")])
    assert proc.returncode == 0, proc.stdout
    assert "LITERAL_GATE_OK" in proc.stdout


def test_literal_gate_selftest():
    """门禁自身可证伪（阳性/阴性对照）——防"token 集为空"的假绿。"""
    proc = _run([str(ROOT / "tools" / "check_literals.py"), "--selftest"])
    assert proc.returncode == 0, proc.stdout
    assert "LITERAL_GATE_SELFTEST_OK" in proc.stdout


def test_literal_gate_detects_injected_literal(tmp_path):
    """变异验证：往扫描面植入一个真实政策数值，门禁必须变红。"""
    target = ROOT / "src" / "rca" / "engine" / "checker.py"
    original = target.read_text(encoding="utf-8")
    tokens = json_tokens()
    token = sorted(tokens)[0]
    try:
        target.write_bytes((original + "\n_INJECTED = %s\n" % token).encode("utf-8"))
        proc = _run([str(ROOT / "tools" / "check_literals.py")])
        assert proc.returncode == 1, "植入政策数值后门禁仍绿 → 假门"
    finally:
        target.write_bytes(original.encode("utf-8"))


def json_tokens():
    """实算 token（与门禁同源，但仅测试用）。"""
    sys.path.insert(0, str(ROOT / "tools"))
    import importlib

    mod = importlib.import_module("check_literals")
    toks = mod.compute_banned_tokens(DATA)
    return set(toks["policy_numbers"]) | set(toks["years"])


# --------------------------------------------------------------------------
# 脱敏审计（selftest 常驻；tracked 常驻）
# --------------------------------------------------------------------------

def test_desensitize_selftest():
    proc = _run([str(ROOT / "tools" / "audit_desensitize.py"), "selftest"])
    assert proc.returncode == 0, proc.stdout
    assert "DESENSITIZE_AUDIT_SELFTEST_OK" in proc.stdout


def test_desensitize_tracked_has_no_hard_hits():
    """已跟踪文件不得有 HARD 级命中。"""
    proc = _run([str(ROOT / "tools" / "audit_desensitize.py"), "tracked"])
    assert proc.returncode == 0, proc.stdout


def test_desensitize_tokens_are_runtime_computed():
    """扫描器源码不得出现 token 词面（运行时实算）。"""
    src = (ROOT / "tools" / "audit_desensitize.py").read_text(encoding="utf-8")
    # 源码里不得出现真实邮箱域名片段（本地 git 配置是最高频翻车源）
    assert "@qq.com" not in src
    assert "2824098035" not in src


# --------------------------------------------------------------------------
# 分层纪律：引擎/报告不得 import GUI
# --------------------------------------------------------------------------

LAYERED_DIRS = ["src/rca/engine", "src/rca/report", "src/rca/parser", "src/rca/benchmark"]


@pytest.mark.parametrize("rel", LAYERED_DIRS)
def test_core_layers_do_not_import_gui(rel):
    for py in (ROOT / rel).rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert "PySide6" not in src, "%s 顶层不得引用 GUI 重件" % py
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "gui" not in node.module.split("."), (
                    "%s import 了 GUI 模块（唯一入口应为 pipeline）" % py
                )


def test_cli_module_does_not_import_gui_at_top_level():
    """AST 静态守门：CLI 顶层不得 import GUI/PySide6（比 sys.modules 断言可靠）。"""
    src = (ROOT / "src" / "rca" / "cli.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:  # 只看模块顶层
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("PySide6")
                assert "gui" not in alias.name
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "gui" not in node.module.split(".")
            assert not node.module.startswith("PySide6")


def test_engine_has_no_policy_numbers_in_source():
    """引擎源码零政策字面量（与门禁同一份 token，此处做源码级复核）。"""
    tokens = json_tokens()
    pats = [(t, re.compile(r"(?<![\d.])" + re.escape(t) + r"(?![\d])")) for t in tokens]
    for py in (ROOT / "src" / "rca").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token, pat in pats:
            assert not pat.search(text), "%s 含政策数值字面量 %s" % (py.name, token)


# --------------------------------------------------------------------------
# 打包白名单单一事实源（plan/05 §6）
# --------------------------------------------------------------------------

def test_packaging_whitelist_is_single_source():
    from rca.packaging import build_datas

    datas = build_datas(ROOT)
    assert datas, "打包白名单为空"
    for src, _dest in datas:
        assert (ROOT / src).exists(), "白名单引用了不存在的路径: %s" % src


def test_packaging_module_is_inside_package_not_top_level():
    """`packaging.py` 放顶层会遮蔽 PyPI 的 packaging（PyInstaller 依赖它）。"""
    assert (ROOT / "src" / "rca" / "packaging.py").is_file()
    assert not (ROOT / "packaging.py").exists(), (
        "顶层 packaging.py 会遮蔽 PyPI packaging 包，必须放包内"
    )


def test_spec_has_no_handwritten_data_paths():
    """spec 的 datas 必须来自 build_datas()，不得手写数据路径。"""
    spec = (ROOT / "tools" / "rca.spec").read_text(encoding="utf-8")
    assert "build_datas(" in spec, "spec 未调用白名单单一事实源"
    assert "datas=[" not in spec.replace("datas=datas", ""), "spec 出现手写 datas 列表"
    for forbidden in ("data/rules", "data/knowledge", "data/samples"):
        assert forbidden not in spec, "spec 手写了数据路径: %s" % forbidden


def test_gitignore_keeps_spec_tracked():
    """`*.spec` 通配会吞掉我们的 spec，必须有例外。"""
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "!tools/rca.spec" in text, ".gitignore 缺 spec 例外（spec 会被吞掉）"

