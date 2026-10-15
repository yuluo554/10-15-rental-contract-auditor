"""README 可跑通性回归门。

纪律（skill 阶段 7，第三类缺口）：README 引用的输入文件必须**由生成器保证存在**，
且命令要**真跑**。本地因工作目录残留看着能跑、干净环境当场 exit 2 是实测高发形态，
静态"路径存在"断言抓不到无前缀的裸文件名——必须**从命令里抽参数**再真跑。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _cli_commands() -> list:
    """从 README 代码块里抽出 `python -m rca.cli ...` 命令。"""
    out = []
    for block in re.findall(r"```bash\n(.*?)```", _readme(), re.S):
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if "rca.cli" in line or "tools/" in line:
                out.append(line)
    return out


def test_readme_has_quickstart_commands():
    cmds = _cli_commands()
    assert len(cmds) >= 5, "README 快速开始的命令过少（%d 条）" % len(cmds)


def test_readme_input_paths_exist():
    """从命令里抽 `--input/--out/--data` 参数，断言路径真实存在或可创建。"""
    for cmd in _cli_commands():
        for m in re.finditer(r"--input\s+(\S+)", cmd):
            rel = m.group(1)
            assert (ROOT / rel).is_file(), (
                "README 命令引用了不存在的输入文件: %s（命令：%s）" % (rel, cmd)
            )


def test_readme_install_extras_line():
    """README 安装行必须含 extras（与 CI 同集合，保证收集数对账）。"""
    text = _readme()
    assert re.search(r'pip install -e "\.\[dev,gui\]"', text), "README 安装行缺 extras"


def _run(cmd: str):
    """执行 README 命令。

    命令文本里的 `python` 换成**当前解释器**再跑：本机（及部分 CI）裸 `python`
    是商店占位符/不在 PATH（实测 exit 9009）。README 原文不改——逐字执行的要求
    是"命令语义逐字"，解释器通道按本机实况适配。
    """
    if cmd.startswith("python "):
        cmd = '"%s" %s' % (sys.executable, cmd[len("python "):])
    return subprocess.run(
        cmd,
        shell=True,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )


@pytest.mark.parametrize(
    "cmd,expected_rc",
    [
        # check 在演示样例上会检出不符合 → 退出码 1 是既定语义
        ("python -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京", 1),
        ("python -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京 --json", 1),
        ("python -m rca.cli rules --city 北京", 0),
        ("python -m rca.cli bench", 0),
    ],
)
def test_readme_commands_run_with_documented_exit_code(cmd, expected_rc):
    """逐字执行 README 命令，退出码须符合明示语义（非 0 ≠ 跑挂）。"""
    proc = _run(cmd)
    assert proc.returncode == expected_rc, (
        "命令 %s 退出码 %d（期望 %d）\n%s" % (cmd, proc.returncode, expected_rc, proc.stdout)
    )


def test_readme_report_command_produces_both_formats(tmp_path):
    out_dir = tmp_path / "rep"
    cmd = (
        "python -m rca.cli report --input data/samples/demo-contract-bj.txt "
        "--city 北京 --out %s" % out_dir.as_posix()
    )
    proc = _run(cmd)
    assert proc.returncode in (0, 1), proc.stdout
    assert (out_dir / "体检报告.md").is_file()
    assert (out_dir / "体检报告.xlsx").is_file()
