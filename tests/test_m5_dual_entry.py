"""M5 双入口一致性：GUI 展示的判定必须与 CLI `check` 同源同值。

题面模块④⑥要求"桌面 exe + CLI 双入口"。**双入口的真正风险不是"都能启动"，
而是两条通路各自演化出两套结论**——GUI 里显示"符合"、CLI 报"不符合"，
比只有一个入口更糟（用户不知道该信哪个）。

守门方式（plan/05 §7 "编排上收"）：**行为等价**断言，不是"都调了同一个函数"
这种字面声明。三方对账：
    GUI 界面显示的整体判定  ==  pipeline 直调  ==  CLI `check` 的 stdout 输出
三方都必须来自同一份输入与同一份规则包。

"都 import 了 pipeline" 是**弱断言**——接线断了（GUI 少传 data_dir、
CLI 换了 scope）它照样绿。故这里驱动真实控件、读真实输出文本。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI 为可选功能，缺 [gui] extra 时跳过")

ROOT = Path(__file__).resolve().parents[1]

from conftest import (  # noqa: E402
    BJ_COMPLIANT_CONTRACT,
    BJ_ENTERPRISE_CONTRACT,
    INDIVIDUAL_CONTRACT,
)


def _click_check(contract: str, city: str) -> str:
    """驱动真实控件：填文本 → 选城市 → 点按钮 → 读只读输出框。"""
    from PySide6.QtWidgets import QComboBox, QPlainTextEdit, QPushButton

    from rca.gui.app import build_app

    app, window = build_app()
    page = window.centralWidget().widget(0)
    combo = page.findChildren(QComboBox)[0]
    combo.setCurrentText(city)
    edits = page.findChildren(QPlainTextEdit)
    edits[0].setPlainText(contract)
    page.findChildren(QPushButton)[0].click()
    outputs = [e for e in edits if e.isReadOnly()]
    assert outputs, "未找到 GUI 输出控件"
    return outputs[0].toPlainText()


def _verdict(text: str) -> str:
    m = re.search(r"整体判定：([A-Za-z_]+)", text)
    assert m, "输出未含整体判定：%r" % text[:200]
    return m.group(1)


@pytest.mark.parametrize(
    "contract,label",
    [
        (BJ_ENTERPRISE_CONTRACT, "enterprise-noncompliant"),
        (BJ_COMPLIANT_CONTRACT, "compliant"),
        (INDIVIDUAL_CONTRACT, "individual"),
    ],
    ids=["noncompliant", "compliant", "individual"],
)
def test_gui_verdict_matches_pipeline_direct_call(contract, label):
    """GUI 显示的整体判定 == pipeline 直调结果（同输入）。"""
    from rca.engine.pipeline import compute_result

    shown = _verdict(_click_check(contract, "北京"))
    direct = compute_result(contract, "北京").overall_status
    assert shown == direct, "%s: GUI 显示 %s，pipeline 直调 %s" % (label, shown, direct)


@pytest.mark.parametrize(
    "contract",
    [BJ_ENTERPRISE_CONTRACT, BJ_COMPLIANT_CONTRACT],
    ids=["noncompliant", "compliant"],
)
def test_gui_verdict_matches_cli_check_stdout(contract, capsys):
    """GUI 显示的整体判定 == CLI `check` 的 stdout 结论（题面双入口的核心承诺）。"""
    from rca.cli import main

    rc = main(["check", "--input", _write_tmp(contract), "--city", "北京"])
    cli_verdict = _verdict(capsys.readouterr().out)
    gui_verdict = _verdict(_click_check(contract, "北京"))

    assert gui_verdict == cli_verdict, (
        "双入口结论分叉：GUI=%s CLI=%s（用户不知道该信哪个）" % (gui_verdict, cli_verdict)
    )
    # 退出码语义与结论一致（1 = 检出不符合，0 = 未检出）
    assert (rc == 1) == (cli_verdict == "noncompliant")


def _write_tmp(contract: str) -> str:
    """写临时合同文件（LF 行尾，与 conftest.write_text_lf 同口径）。"""
    import tempfile
    from pathlib import Path

    td = Path(tempfile.mkdtemp(prefix="rca-m5-"))
    p = td / "c.txt"
    p.write_bytes(contract.encode("utf-8"))
    return str(p)


def test_gui_findings_count_matches_pipeline():
    """不只对账整体判定：逐条判定的条数与状态也要一致（防"总数对、明细错"）。"""
    from rca.engine.pipeline import compute_result

    shown = _click_check(BJ_ENTERPRISE_CONTRACT, "北京")
    result = compute_result(BJ_ENTERPRISE_CONTRACT, "北京")

    for f in result.findings:
        assert "[%s] %s" % (f.status, f.title) in shown, (
            "pipeline 的判定 %s(%s) 未出现在 GUI 输出里" % (f.rule_id, f.status)
        )
    # GUI 逐条列出后，明细行数不应少于 findings 条数
    listed = [ln for ln in shown.splitlines() if ln.startswith("[")]
    assert len(listed) >= len(result.findings)


def test_gui_uses_same_data_dir_as_cli(tmp_path):
    """GUI 显式传 data_dir 时必须**真的用**它（防"接了参数没往下传"）。

    用**改过的规则包副本**才可证伪：给一条必然出现在判定里的规则改名成哨兵串，
    GUI 若丢掉 data_dir（回落到自动定位 = 仓库规则包），哨兵就不会出现在输出里。
    （直接传仓库 data_dir 测不出问题：丢参数会回落到同一份，结论恰好一样。）
    """
    import shutil

    from PySide6.QtWidgets import QComboBox, QPlainTextEdit, QPushButton

    from rca.gui.app import build_app

    SENTINEL = "SENTINEL-DATA-DIR-M5"
    alt = tmp_path / "data"
    for sub in ("rules", "knowledge", "samples"):
        shutil.copytree(ROOT / "data" / sub, alt / sub)
    rs_path = alt / "rules" / "ruleset-bj.json"
    rs = json.loads(rs_path.read_text(encoding="utf-8"))
    hit = [r for r in rs["rules"] if r["rule_id"] == "BJ-FILING-30D"]
    assert hit, "BJ-FILING-30D 不在规则包里，本用例不可证伪"
    hit[0]["title"] = SENTINEL
    rs_path.write_bytes(json.dumps(rs, ensure_ascii=False, indent=2).encode("utf-8"))

    # 前提自检：哨兵在仓库规则包里不存在（否则"出现"证明不了用的是副本）
    assert SENTINEL not in (ROOT / "data" / "rules" / "ruleset-bj.json").read_text(
        encoding="utf-8"
    )

    app, window = build_app(data_dir=str(alt))
    page = window.centralWidget().widget(0)
    page.findChildren(QComboBox)[0].setCurrentText("北京")
    edits = page.findChildren(QPlainTextEdit)
    edits[0].setPlainText(BJ_ENTERPRISE_CONTRACT)
    page.findChildren(QPushButton)[0].click()
    shown = [e for e in edits if e.isReadOnly()][0].toPlainText()

    assert SENTINEL in shown, (
        "GUI 未使用传入的 data_dir（疑似回落默认数据目录）：输出里没有副本规则包的哨兵标题"
    )
