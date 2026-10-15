"""CLI 契约测试：退出码四语义（K7）锁进测试，后续重构不漂移。

注意：退出码必须从**函数返回值**取，绝不从管道取（`cmd | tail` 的 `$?`
是 tail 的——这是"假绿"的经典来源）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import write_text_lf
from rca.cli import main

EXIT_OK = 0
EXIT_NONCOMPLIANT = 1
EXIT_USAGE = 2
EXIT_MISSING_DEP = 3


def _write(tmp_path: Path, name: str, text: str) -> str:
    p = tmp_path / name
    write_text_lf(p, text)
    return str(p)


def test_check_compliant_exit_0(tmp_path, bj_compliant):
    path = _write(tmp_path, "c.txt", bj_compliant)
    rc = main(["check", "--input", path, "--city", "北京"])
    assert rc == EXIT_OK


def test_check_noncompliant_exit_1(tmp_path, bj_enterprise):
    """退出码 1 = 检出不符合（既定语义，**不是失败**）。"""
    path = _write(tmp_path, "c.txt", bj_enterprise)
    rc = main(["check", "--input", path, "--city", "北京"])
    assert rc == EXIT_NONCOMPLIANT


def test_missing_input_file_exit_2(tmp_path):
    rc = main(["check", "--input", str(tmp_path / "nope.txt"), "--city", "北京"])
    assert rc == EXIT_USAGE


def test_unsupported_city_exit_2(tmp_path, bj_compliant):
    path = _write(tmp_path, "c.txt", bj_compliant)
    rc = main(["check", "--input", path, "--city", "广州"])
    assert rc == EXIT_USAGE


def test_no_subcommand_exit_2():
    assert main([]) == EXIT_USAGE


def test_bench_unknown_suite_exit_2():
    """--only 传未知名必须 exit 2（否则"跑了个不存在的基准"会被读成成功）。"""
    assert main(["bench", "--only", "B99"]) == EXIT_USAGE


def test_bench_suite_alias_exit_2():
    assert main(["bench", "--suite", "B1,NOPE"]) == EXIT_USAGE


def test_gui_without_dependency_exit_3(monkeypatch):
    """缺 PySide6 必须 exit 3 而非裸异常。

    用 `builtins.__import__` 打桩——本机装了 extra 时真 import 会成功，
    只有打桩才能在本机复现缺依赖路径。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6") or name == "rca.gui.app":
            raise ImportError("simulated missing PySide6")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert main(["gui"]) == EXIT_MISSING_DEP


def test_check_json_is_valid(tmp_path, bj_enterprise, capsys):
    path = _write(tmp_path, "c.txt", bj_enterprise)
    rc = main(["check", "--input", path, "--city", "北京", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["city"] == "北京"
    assert payload["overall_status"] == "noncompliant"
    assert rc == EXIT_NONCOMPLIANT


def test_rules_subcommand_lists_sources(capsys):
    rc = main(["rules", "--city", "北京"])
    captured = capsys.readouterr()
    assert rc == EXIT_OK
    assert "北京市住房租赁条例" in captured.out


def test_rules_json_has_thresholds(capsys):
    rc = main(["rules", "--city", "北京", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == EXIT_OK
    assert payload["overview"]["thresholds"], "门槛必须随规则包下发"


def test_scan_isolates_failures(tmp_path, bj_compliant, capsys):
    """批量：坏文件不中断整批，且单列（"未判定 ≠ 违规"）。"""
    _write(tmp_path, "good.txt", bj_compliant)
    (tmp_path / "bad.txt").write_text("", encoding="utf-8")
    rc = main(["scan", "--dir", str(tmp_path), "--city", "北京"])
    captured = capsys.readouterr()
    assert "good.txt" in captured.out
    # 空文件属"未判定"，不改变退出码（good.txt 无不符合 → 0）
    assert rc == EXIT_OK


def test_scan_missing_dir_exit_2(tmp_path):
    assert main(["scan", "--dir", str(tmp_path / "nope"), "--city", "北京"]) == EXIT_USAGE


def test_selftest_writes_file(tmp_path, capsys):
    out = tmp_path / "selftest.json"
    rc = main(["selftest", "--out", str(out)])
    assert rc == EXIT_OK
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["bj_rule_count"] > 0
    assert payload["frozen"] is False
    # 非冻结态该项必须是 None（不让源码运行被误判为 FAIL）
    assert payload["data_dir_in_dist"] is None
