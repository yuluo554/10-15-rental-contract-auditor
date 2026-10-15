"""发布工具测试：确定性打包、ASCII 附件名、中立目录验收的禁区检测。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tools_support import load_tool

ROOT = Path(__file__).resolve().parents[1]

build_release = load_tool("build_release")
verify_package = load_tool("verify_package")


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist" / "rca-cli"
    (dist / "sub").mkdir(parents=True)
    (dist / "rca-cli.exe").write_bytes(b"FAKE-EXE")
    (dist / "sub" / "data.json").write_bytes(b'{"a":1}')
    (dist / "_internal").mkdir()
    (dist / "_internal" / "x.txt").write_bytes(b"x")
    return dist


def test_release_zip_is_deterministic(tmp_path):
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    name = "rca-cli-win64.zip"
    build_release.build_zip(dist, out / name, "rca-cli")
    first = (out / name).read_bytes()
    build_release.build_zip(dist, out / name, "rca-cli")
    second = (out / name).read_bytes()
    assert first == second, "两次打包字节不一致（确定性被破坏）"


def test_release_zip_entries_frozen_metadata(tmp_path):
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    build_release.build_zip(dist, out / "a.zip", "a")
    with zipfile.ZipFile(out / "a.zip") as zf:
        for info in zf.infolist():
            assert info.create_system == 0
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED


def test_release_ledger_has_sha256(tmp_path):
    dist = _make_dist(tmp_path)
    out = tmp_path / "out"
    zp = build_release.build_zip(dist, out / "a.zip", "a")
    entry = build_release.ledger_entry(zp)
    assert len(entry["sha256"]) == 64
    assert entry["bytes"] > 0
    assert entry["entries"] > 0


def test_non_ascii_asset_name_rejected(tmp_path, capsys):
    dist = _make_dist(tmp_path)
    rc = build_release.main(
        ["--dist", str(dist), "--out", str(tmp_path / "o"), "--name", "中文.zip"]
    )
    assert rc == 2


def test_verify_detects_forbidden_top_level(tmp_path):
    dist = tmp_path / "dist"
    (dist / "plan").mkdir(parents=True)
    (dist / "rca-cli.exe").write_bytes(b"x")
    problems = verify_package.check_top_level(dist)
    assert any("plan" in p for p in problems)


def test_verify_allows_dependency_dirs_nested(tmp_path):
    """禁区成分只匹配 dist **顶层**——依赖包自带的同名子目录不算泄露。"""
    dist = tmp_path / "dist"
    (dist / "_internal" / "IPython" / "core" / "tests").mkdir(parents=True)
    (dist / "_internal" / "IPython" / "core" / "tests" / "a.py").write_bytes(b"x")
    assert verify_package.check_top_level(dist) == []
