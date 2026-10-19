"""M5 交付层守门：冻结入口、打包依赖分档、argv 规范化、零出网。

**为什么这些守门必须存在**（M5 首次实构建实测出的四处产物级缺口）：
1. spec 的 `datas` 源路径写成相对路径 → PyInstaller 解析到 SPECPATH（`tools/`），
   构建直接 `Unable to find .../tools/data/...` 失败。
2. spec 以 `src/rca/cli.py` 为入口 → PyInstaller 当顶层 `__main__` 跑，
   包内相对导入抛 `attempted relative import with no known parent package`，
   exe 一启动就崩（**构建能"成功"，产物完全不可用**）。
3. GUI exe 指向 `src/rca/gui/app.py`，该文件**没有 `__main__`**：
   被打成 exe 后没有任何入口、不处理 `--selftest`（脚本化验收的唯一通路）。
4. spec 把 `hiddenimports=["rca.gui.app"]` **两个目标共用** → CLI 产物白背
   87MB PySide6；再叠加 `ssl`/`libcrypto` 等出网栈，"纯本地零上传"在产物级无法自证。

这四条都属于"**看起来配了、构建也过了，但产物不可用**"——只在真跑一次
构建 + 冻结态验收时才暴露。故守门分两层：
- 本文件的**静态**守门（秒级，进 CI 全量测试）；
- `tools/verify_package.py` 的**产物级**验收（需先构建，见 DoD 命令）。
本文件断言的都是"产物级验收会依赖的前提"，前提被改坏时在这里就红。
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
from pathlib import Path

import pytest

from tools_support import load_tool

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tools" / "rca.spec"

sys.path.insert(0, str(ROOT / "src"))

verify_package = load_tool("verify_package")

SPEC_TEXT = SPEC.read_text(encoding="utf-8")


def _build_call_args(target: str) -> str:
    """取出 `cli_dist = _build(...)` / `gui_dist = _build(...)` 的实参文本。

    按**括号配平**切（`str.split(")")` 会被 `os.path.join(...)` 的括号带偏，
    M5 实测踩到：切出来的实参只剩第一个参数）。
    """
    marker = "%s = _build(" % target
    start = SPEC_TEXT.index(marker) + len(marker)
    depth = 1
    i = start
    while i < len(SPEC_TEXT) and depth:
        if SPEC_TEXT[i] == "(":
            depth += 1
        elif SPEC_TEXT[i] == ")":
            depth -= 1
        i += 1
    assert depth == 0, "spec 的 _build 调用括号不配平: %s" % target
    return SPEC_TEXT[start:i - 1]


# --------------------------------------------------------------------------
# 冻结入口：入口脚本必须是绝对导入的薄入口（相对导入 → exe 一启动就崩）
# --------------------------------------------------------------------------

def test_spec_uses_absolute_frozen_entry_modules():
    """入口必须是 `rca.cli_entry` / `rca.gui_entry`，不能是包内模块本身。"""
    assert "cli_entry.py" in SPEC_TEXT, "CLI 入口未指向 rca.cli_entry"
    assert "gui_entry.py" in SPEC_TEXT, "GUI 入口未指向 rca.gui_entry"


@pytest.mark.parametrize("mod", ["rca.cli_entry", "rca.gui_entry"])
def test_frozen_entry_has_no_relative_import_at_module_or_function_level(mod):
    """入口及其调用链上的 import 必须是绝对的（冻结态没有父包）。

    PyInstaller 把 spec 脚本当顶层 `__main__` 执行：该脚本内（含函数体内）
    的**相对导入**必然 `ImportError`。这里用 AST 静态抓，比真构建快 3 个数量级。
    """
    path = ROOT / "src" / ("%s.py" % mod.replace(".", "/"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, (
                "%s:%d 冻结入口出现相对导入（level=%d）→ exe 启动即崩"
                % (path.name, node.lineno, node.level)
            )


@pytest.mark.parametrize("mod", ["rca.cli_entry", "rca.gui_entry"])
def test_frozen_entry_is_importable_by_absolute_name(mod):
    """绝对名可导入 = 冻结态能跑的前提（同一断言在源码态即可证伪）。"""
    import importlib

    assert importlib.import_module(mod) is not None


def test_gui_entry_has_main_guard():
    """GUI exe 的入口文件必须有 `__main__` 守卫（原 app.py 没有 → exe 无入口）。"""
    src = (ROOT / "src" / "rca" / "gui_entry.py").read_text(encoding="utf-8")
    assert '__name__ == "__main__"' in src


# --------------------------------------------------------------------------
# CLI 的 `--selftest <文件>`：plan/05 §6 认定的脚本化验收唯一通路
# --------------------------------------------------------------------------

def test_cli_normalizes_selftest_flag():
    from rca.cli import normalize_argv

    assert normalize_argv(["--selftest", "out.json"]) == ["selftest", "--out", "out.json"]


def test_cli_selftest_flag_runs_end_to_end(tmp_path):
    """`--selftest <文件>`（不带子命令）必须真能跑出结论文件。

    只会规范化、但 `main` 没接上这条通路的话，验收器仍会拿到 exit 2
    ——故这里断言**结论文件真被写出**，而非只断言函数返回值。
    """
    import json

    from rca.cli import main

    out = tmp_path / "st.json"
    rc = main(["--selftest", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["bj_rule_count"] > 0
    assert payload["frozen"] is False


def test_cli_normalize_leaves_other_commands_untouched():
    from rca.cli import normalize_argv

    assert normalize_argv(["check", "--city", "北京"]) == ["check", "--city", "北京"]
    assert normalize_argv(["selftest", "--out", "x"]) == ["selftest", "--out", "x"]


def test_gui_selftest_routes_to_cli_single_source(tmp_path):
    """GUI 的 `--selftest` 必须复用 CLI 的规范化（单一实现源）。

    断言的是**路由结果**（等于 CLI 规范化输出），不是"都调了某函数"。
    """
    from rca.cli import normalize_argv
    from rca.gui_entry import selftest_argv

    got = selftest_argv(["--selftest", "o.json"])
    assert got == normalize_argv(["--selftest", "o.json"])


def test_gui_rejects_unknown_args_with_exit_2(monkeypatch, capsys):
    """GUI exe 必须拒绝未知参数（否则静默挂进事件循环，验收器超时）。

    打桩 `run_gui` 为"被调用即失败"——**不能用真 `app.exec()` 做这个断言**：
    参数检查一旦被摘掉，真跑会挂进 Qt 事件循环永不返回（M5 变异验证实测：
    整个变异脚本卡死），症状从"测试转红"退化成"测试卡住"。
    """
    import rca.gui.app as gui_app
    from rca.gui_entry import main

    def _boom(*a, **k):
        raise AssertionError("未知参数未被拦下：run_gui 被调用了（会挂死窗口版）")

    monkeypatch.setattr(gui_app, "run_gui", _boom)

    rc = main(["check", "--input", "x.txt", "--city", "北京"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "无法识别" in err


def test_gui_unknown_args_helper_consumes_data_value():
    from rca.gui_entry import unknown_args

    assert unknown_args(["--data", "foo"]) == []
    assert unknown_args(["--data", "foo", "junk"]) == ["junk"]


# --------------------------------------------------------------------------
# 打包依赖分档：CLI 产物不得背 GUI 重件与出网栈
# --------------------------------------------------------------------------

def test_spec_does_not_share_hiddenimports_across_targets():
    """`hiddenimports` 不得两目标共用——共用会把 PySide6 灌进 CLI 产物。"""
    cli_args = _build_call_args("cli_dist")
    assert "hiddenimports=[]" in cli_args, "CLI 目标的 hiddenimports 未显式置空"

    gui_args = _build_call_args("gui_dist")
    assert "hiddenimports=" in gui_args, "GUI 目标未显式声明 hiddenimports"
    assert "rca.gui.app" in gui_args


def test_spec_excludes_network_stack_from_cli_target():
    """CLI 目标必须排除出网栈（产物级"零上传"可核验的前提）。"""
    assert "NETWORK_EXCLUDES" in SPEC_TEXT
    for mod in ("ssl", "_ssl", "_socket", "_hashlib"):
        assert '"%s"' % mod in SPEC_TEXT, "spec 未排除出网栈: %s" % mod
    cli_args = _build_call_args("cli_dist")
    assert "NETWORK_EXCLUDES" in cli_args, "出网栈排除项未接到 CLI 目标上"


def test_spec_excludes_gui_stack_from_cli_target():
    cli_args = _build_call_args("cli_dist")
    assert "PySide6" in cli_args


def test_datas_sources_are_absolute_paths():
    """datas 的**源**路径必须是绝对路径。

    相对路径会被 PyInstaller 解析到 SPECPATH（`tools/`），构建直接失败
    （M5 实测：`Unable to find '<repo>/tools/data/rules/ruleset-bj.json'`）。
    """
    from rca.packaging import build_datas

    datas = build_datas(ROOT)
    assert datas, "打包白名单为空"
    for src, dest in datas:
        assert Path(src).is_absolute(), "datas 源路径非绝对: %s（会解析到 SPECPATH）" % src
        assert Path(src).is_file(), "datas 源文件不存在: %s" % src
        assert not Path(dest).is_absolute(), "datas 目标应为包内相对目录: %s" % dest


# --------------------------------------------------------------------------
# 零出网：源码级（产物级由 verify_package 的 check_no_network_modules 兜）
# --------------------------------------------------------------------------

NETWORK_MODULES = ("urllib.request", "urllib.error", "socket", "http.client",
                   "requests", "httpx", "ssl", "ftplib", "smtplib", "telnetlib")
NETWORK_CALLS = ("urlopen", "urlretrieve", "socket(")

# 运行期包内**不得**出现的出网 import（tools/ 下的抓取脚本是开发期工具，
# 不入发行包、不在此扫描面内）
SCAN_ROOTS = ("src/rca",)


def _iter_py():
    for rel in SCAN_ROOTS:
        for p in (ROOT / rel).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p


def test_runtime_package_has_no_network_imports():
    """运行期包零出网 import —— "纯本地零上传"的源码级证据。"""
    for py in _iter_py():
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                for banned in NETWORK_MODULES:
                    assert not (name == banned or name.startswith(banned + ".")), (
                        "%s 出现出网 import: %s" % (py.relative_to(ROOT).as_posix(), name)
                    )


def test_runtime_package_has_no_network_calls():
    """源码文本级复核：不得出现出网调用名面。"""
    for py in _iter_py():
        text = py.read_text(encoding="utf-8")
        for call in NETWORK_CALLS:
            assert call not in text, (
                "%s 出现出网调用 %s" % (py.relative_to(ROOT).as_posix(), call)
            )


def test_gui_entry_does_not_import_pyside6_at_top_level():
    """GUI 入口不得在模块顶层 import PySide6（分层守门同口径）。"""
    tree = ast.parse((ROOT / "src" / "rca" / "gui_entry.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.startswith("PySide6")
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("PySide6")


# --------------------------------------------------------------------------
# 降级提示按 is_frozen() 分流（plan/05 §6）
# --------------------------------------------------------------------------

def test_gui_degradation_message_branches_on_frozen(monkeypatch, capsys):
    """冻结态读者拿不到 pip：提示不该叫他去 pip install。

    CLI 发行包**不含 PySide6**（spec 分档），冻结态 `rca gui` 必须
    如实说"本发行包未内嵌"，而不是给一条无效的源码安装指引。
    """
    import builtins

    from rca.cli import main
    from rca import cli as cli_mod

    monkeypatch.setattr(cli_mod, "is_frozen", lambda: True)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6") or name == "rca.gui.app":
            raise ImportError("simulated missing PySide6")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rc = main(["gui"])
    err = capsys.readouterr().err
    assert rc == 3
    assert "未内嵌" in err and "pip install" not in err, (
        "冻结态降级提示未分流（仍给源码安装指引）: %s" % err
    )


def test_gui_degradation_message_source_branch_keeps_pip(monkeypatch, capsys):
    """源码态保留 pip 安装指引（分组断言两头都要动）。"""
    import builtins

    from rca.cli import main
    from rca import cli as cli_mod

    monkeypatch.setattr(cli_mod, "is_frozen", lambda: False)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6") or name == "rca.gui.app":
            raise ImportError("simulated missing PySide6")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rc = main(["gui"])
    err = capsys.readouterr().err
    assert rc == 3
    assert "pip install" in err, "源码态降级提示丢了安装指引: %s" % err


# --------------------------------------------------------------------------
# verify_package 自身的静态守门（产物级断言的前提）
# --------------------------------------------------------------------------

def test_verify_package_checks_embedded_data_sha256():
    assert hasattr(verify_package, "check_embedded_data_sha256")
    src = inspect.getsource(verify_package.check_embedded_data_sha256)
    assert "sha256" in src and "build_datas" in src, (
        "内嵌数据校验未与白名单同源（漏拷的项不会被发现）"
    )


def test_verify_package_detects_forbidden_network_module(tmp_path):
    """负向对照：产物里塞进 TLS 运行库，校验必须报出来。"""
    dist = tmp_path / "dist"
    (dist / "_internal").mkdir(parents=True)
    (dist / "rca-cli.exe").write_bytes(b"x")
    (dist / "_internal" / "libssl-3.dll").write_bytes(b"x")
    problems = verify_package.check_no_network_modules(dist)
    assert any("libssl" in p for p in problems), "出网组件混入产物未被发现"

    (dist / "_internal" / "libssl-3.dll").unlink()
    assert verify_package.check_no_network_modules(dist) == []


def _lay_embedded_data(dist: Path) -> Path:
    """按白名单在 dist 内部署一份"与仓库一致"的内嵌数据（产物内布局）。"""
    embedded = dist / "_internal" / "data"
    for rel_in_data, src in verify_package.expected_packed_entries().items():
        target = embedded / rel_in_data
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
    return embedded


def test_verify_package_detects_embedded_data_mismatch(tmp_path, monkeypatch):
    """负向对照：包内数据与仓库冻结件不一致，校验必须报出来。"""
    dist = tmp_path / "dist"
    embedded = _lay_embedded_data(dist)
    assert verify_package.check_embedded_data_sha256(dist) == []

    victim = embedded / "rules" / "ruleset-bj.json"
    victim.write_bytes(victim.read_bytes().replace(b'"city"', b'"cty"', 1))
    problems = verify_package.check_embedded_data_sha256(dist)
    assert any("sha256 失配" in p for p in problems), "包内旧数据未被发现"


def test_verify_package_detects_unlisted_extra_data_file(tmp_path):
    """负向对照：包内混入白名单外的数据文件 → 必须报出来（防多余东西进包）。"""
    dist = tmp_path / "dist"
    embedded = _lay_embedded_data(dist)
    assert verify_package.check_embedded_data_sha256(dist) == []

    (embedded / "rules" / "ruleset-secret.json").write_bytes(b"{}")
    problems = verify_package.check_embedded_data_sha256(dist)
    assert any("白名单外" in p for p in problems), "白名单外数据文件未被发现"


def test_verify_package_has_gui_arg_discipline_check():
    assert hasattr(verify_package, "check_gui_rejects_unknown_args")


def test_verify_package_frozen_check_is_wired_into_verify():
    """冻结态判定对账必须真的接进 `verify`（不能只在模块里躺着）。"""
    src = inspect.getsource(verify_package.verify)
    assert "check_frozen_check_matches_source" in src, (
        "冻结态判定对账未接进 verify（模块里有、流程没走 = 假门）"
    )


def test_verdict_parser_rejects_greedy_capture():
    """判定提取必须只吃 ASCII 状态名——贪婪捕获会把两种不同输出判成一致。"""
    assert verify_package.parse_verdict("整体判定：noncompliant（已判定 12 项）") == "noncompliant"
    assert verify_package.parse_verdict("整体判定：compliant") == "compliant"
    got = verify_package.parse_verdict("整体判定：compliant（已判定 3 项）")
    assert got == "compliant", "贪婪捕获把说明文字吞进了状态：%r" % got
    assert verify_package.parse_verdict("没有这一行") is None


# --------------------------------------------------------------------------
# 产物级验收的**端到端**通路（不是只测被调用的那个函数）
#
# 照 M4 的假绿教训：只断言"某函数存在/某纯函数返回预期"时，
# "函数对但接线断了"照样绿。故这里构造一个假 dist，**真跑 `verify()`**，
# 断言问题被汇总上报。M9/M10/M11 三类"摘掉接线"的变异只有这样才能抓住。
# --------------------------------------------------------------------------

def _fake_dist(tmp_path: Path, corrupt_rel: str | None = None) -> Path:
    """搭一个结构完整（内嵌数据与仓库一致）的假 dist。"""
    dist = tmp_path / "dist" / "rca-cli"
    (dist / "_internal").mkdir(parents=True)
    (dist / "rca-cli.exe").write_bytes(b"fake")
    embedded = _lay_embedded_data(dist)
    if corrupt_rel:
        victim = embedded / corrupt_rel
        victim.write_bytes(victim.read_bytes().replace(b'"city"', b'"cty"', 1))
    return dist


def _patch_exe_calls(monkeypatch):
    """让 `verify()` 不必真跑 exe：假 exe 调用 + 假自检结论 + 假报告通路。"""
    import subprocess

    monkeypatch.setattr(
        verify_package, "_find_exe",
        lambda dist, kind: dist / ("rca-gui.exe" if kind == "gui" else "rca-cli.exe"),
    )

    def fake_neutral_run(exe, args):
        import json as _json
        if "--selftest" in args:
            out = Path(args[args.index("--selftest") + 1])
            out.write_bytes(_json.dumps(
                {"frozen": True, "data_dir_in_dist": True, "bj_rule_count": 10}
            ).encode("utf-8"))
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="")

    monkeypatch.setattr(verify_package, "_neutral_run", fake_neutral_run)
    # 假 exe 产不出真报告 → 报告通路另行打桩（它有独立的负向对照测试）
    monkeypatch.setattr(verify_package, "check_frozen_report_no_external",
                        lambda d, e: [])


def test_verify_end_to_end_reports_embedded_data_mismatch(tmp_path, monkeypatch, capsys):
    """真跑 `verify()`：包内数据被改过 → 必须判未通过并点名 sha256 失配。

    变异 M10（校验脱钩白名单，只查第一份）与 M9（摘掉校验调用）在这里转红。
    """
    dist = _fake_dist(tmp_path, corrupt_rel="rules/ruleset-sh.json")
    _patch_exe_calls(monkeypatch)
    monkeypatch.setattr(verify_package, "check_frozen_check_matches_source",
                        lambda d, e: [])

    rc = verify_package.verify(dist, gui_selftest=False)
    out = capsys.readouterr().out
    assert rc == 1, "包内数据失配却仍然通过验收"
    assert "sha256 失配" in out, "未点名 sha256 失配：%s" % out


def test_verify_end_to_end_clean_dist_passes(tmp_path, monkeypatch, capsys):
    """对照组：数据一致 + 判定对账空 + 自检正常 → 必须 PACKAGE_VERIFY_OK。

    没有这一条，"永远返回 1 的验收器"也能让上面的负向断言过。
    """
    dist = _fake_dist(tmp_path)
    _patch_exe_calls(monkeypatch)
    monkeypatch.setattr(verify_package, "check_frozen_check_matches_source",
                        lambda d, e: [])

    rc = verify_package.verify(dist, gui_selftest=False)
    out = capsys.readouterr().out
    assert rc == 0, "干净产物被判未通过：%s" % out
    assert "PACKAGE_VERIFY_OK" in out


def test_verify_end_to_end_wires_frozen_check(tmp_path, monkeypatch, capsys):
    """真跑 `verify()`：冻结态判定对账的结论必须被汇总进去。

    变异 M11（把 `check_frozen_check_matches_source` 的调用点摘掉）在这里转红
    ——只断言函数存在的弱测试抓不到这种"接线断了"。
    """
    dist = _fake_dist(tmp_path)
    _patch_exe_calls(monkeypatch)
    monkeypatch.setattr(verify_package, "check_frozen_check_matches_source",
                        lambda d, e: ["SENTINEL-FROZEN-CHECK-NOT-WIRED"])

    rc = verify_package.verify(dist, gui_selftest=False)
    out = capsys.readouterr().out
    assert rc == 1, "判定对账报了问题却仍然通过验收"
    assert "SENTINEL-FROZEN-CHECK-NOT-WIRED" in out, "判定对账结论未被汇总：%s" % out


def test_verify_end_to_end_reports_network_module(tmp_path, monkeypatch, capsys):
    """真跑 `verify()`：产物里混入 TLS 运行库 → 必须判未通过。"""
    dist = _fake_dist(tmp_path)
    (dist / "_internal" / "libssl-3.dll").write_bytes(b"x")
    _patch_exe_calls(monkeypatch)
    monkeypatch.setattr(verify_package, "check_frozen_check_matches_source",
                        lambda d, e: [])

    rc = verify_package.verify(dist, gui_selftest=False)
    out = capsys.readouterr().out
    assert rc == 1
    assert "出网组件" in out


# --------------------------------------------------------------------------
# 冻结态报告无外链（plan/05 DoD：源码侧断言须在冻结产物上复跑）
# --------------------------------------------------------------------------

def test_verify_package_has_frozen_report_check():
    assert hasattr(verify_package, "check_frozen_report_no_external")


def test_verify_package_wires_frozen_report_check():
    src = inspect.getsource(verify_package.verify)
    assert "check_frozen_report_no_external" in src, "冻结态报告外链检查未接进 verify"


def test_xlsx_external_rels_detected(tmp_path):
    """负向对照：XLSX 里塞进 External 关系，检查必须报出来。"""
    import zipfile

    xlsx = tmp_path / "a.xlsx"
    with zipfile.ZipFile(xlsx, "w") as zf:
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships>'
                                   '<Relationship Target="http://x" TargetMode="External"/>'
                                   "</Relationships>")
    problems = verify_package.check_xlsx_no_external_rels(xlsx)
    assert any("外部关系" in p for p in problems), "XLSX 外链未被发现"

    clean = tmp_path / "b.xlsx"
    with zipfile.ZipFile(clean, "w") as zf:
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships/>')
    assert verify_package.check_xlsx_no_external_rels(clean) == []


def test_end_to_end_reports_external_links_in_frozen_report(tmp_path, monkeypatch, capsys):
    """真跑 `verify()`：冻结态报告含外链 → 必须判未通过。"""
    dist = _fake_dist(tmp_path)
    _patch_exe_calls(monkeypatch)
    monkeypatch.setattr(verify_package, "check_frozen_check_matches_source",
                        lambda d, e: [])
    monkeypatch.setattr(verify_package, "check_frozen_report_no_external",
                        lambda d, e: ["SENTINEL-EXTERNAL-LINK"])

    rc = verify_package.verify(dist, gui_selftest=False)
    out = capsys.readouterr().out
    assert rc == 1
    assert "SENTINEL-EXTERNAL-LINK" in out


def test_verify_package_still_guards_forbidden_top_level(tmp_path):
    """M0 既有断言不回归（顶层禁区扫描）。"""
    dist = tmp_path / "dist"
    (dist / "tools").mkdir(parents=True)
    (dist / "rca-cli.exe").write_bytes(b"x")
    assert verify_package.check_top_level(dist)
