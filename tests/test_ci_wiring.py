"""CI 接线守门：workflow 可解析、fetch-depth 全量历史、extras 覆盖测试期依赖。

三条都是"看起来配了其实没生效"的高发面：
- workflow 非法 YAML → GitHub 不建任何 job（run 0 秒失败），而 state 仍显示 active
- 浅克隆 → 历史扫描静默空验
- extras 缺测试期依赖 → 测试硬失败或静默少跑
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

yaml = pytest.importorskip("yaml", reason="dev extra 需含 PyYAML 以守门 workflow 可解析性")


def test_workflows_exist():
    assert WORKFLOWS, "未找到任何 CI workflow"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_valid_yaml(path):
    """非法 YAML 会让 GitHub 不建任何 job（且 state 仍显示 active）。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "%s 顶层不是映射" % path.name
    assert "jobs" in data, "%s 无 jobs" % path.name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_has_runs_on_and_steps(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for job_name, job in data["jobs"].items():
        assert "runs-on" in job, "job %s 缺 runs-on" % job_name
        assert job.get("steps"), "job %s 缺 steps" % job_name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_checkout_uses_full_history(path):
    """历史扫描类守门依赖全量历史；浅克隆会静默削弱成空验。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for job_name, job in data["jobs"].items():
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            if uses.startswith("actions/checkout"):
                with_block = step.get("with") or {}
                assert with_block.get("fetch-depth") == 0, (
                    "job %s 的 checkout 未配 fetch-depth: 0（历史扫描会空验）" % job_name
                )


def test_ci_env_sets_utf8():
    """编码三层加固的第一层：CI 全局 env 必须设 PYTHONUTF8。"""
    data = yaml.safe_load(WORKFLOWS[0].read_text(encoding="utf-8"))
    for job_name, job in data["jobs"].items():
        env = job.get("env") or {}
        assert str(env.get("PYTHONUTF8")) == "1", "job %s 未设 PYTHONUTF8" % job_name


def test_ci_installs_extras_covering_test_imports():
    """测试面 = 安装面：CI 安装行必须覆盖测试真 import 的库。"""
    text = WORKFLOWS[0].read_text(encoding="utf-8")
    assert ".[dev,gui]" in text, "CI 未安装覆盖测试期依赖的 extras"
    # PySide6（GUI 测试）、pyyaml（workflow 守门）、pytest 都须在安装面
    assert "gui" in text
    assert "dev" in text


def test_readme_install_line_matches_ci_extras():
    """README 快速开始的安装行必须与 CI 同 extras（否则干净环境对不上账）。"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '.[dev,gui]' in readme or "[dev,gui]" in readme, (
        "README 安装行与 CI extras 不一致（收集数对账会失败）"
    )


def test_step_names_with_colon_are_quoted():
    """step 名含「冒号+空格」时必须加引号，否则整份 workflow 非法 YAML。"""
    for path in WORKFLOWS:
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(\s*-?\s*name):\s+(.*)$", line)
            if not m:
                continue
            value = m.group(2).strip()
            if ": " in value and not (value.startswith('"') or value.startswith("'")):
                raise AssertionError(
                    "%s: name 值含「冒号+空格」但未加引号 → 整份 workflow 非法: %s"
                    % (path.name, line.strip())
                )


# --------------------------------------------------------------------------
# 装态门禁的 CI 接线（D1 回归防线）
# --------------------------------------------------------------------------

def test_ci_has_install_smoke_job():
    """必须有**非 editable** 安装的 CI job。

    D1 的成因就是"四个 job 全部 `pip install -e`"：数据在包外也看不出问题。
    这条断言锁死"至少有一个 job 走 wheel 通路"。
    """
    data = yaml.safe_load(WORKFLOWS[0].read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert "install-smoke" in jobs, (
        "CI 缺少 install-smoke job（非 editable 安装没有任何 CI 覆盖 → D1 会复发）"
    )

    text = WORKFLOWS[0].read_text(encoding="utf-8")
    job_block = text[text.index("install-smoke:"):]
    # 截到下一个 job（同缩进的 `  <name>:`）
    for marker in ("\n  package:", "\n  test:"):
        if marker in job_block:
            job_block = job_block[: job_block.index(marker)]

    assert "pip wheel" in job_block, "install-smoke job 未真建 wheel"
    assert "venv" in job_block, "install-smoke job 未建独立 venv"

    # 只查**执行行**：注释里解说缺陷成因时会写到 `pip install -e`，按字面 grep 会误红
    commands = [
        ln.strip()
        for ln in job_block.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    editable = [ln for ln in commands if "pip install -e" in ln or '-e ".[' in ln]
    assert not editable, (
        "install-smoke job 仍在用 editable 安装（验不出装态）: %s" % editable
    )
    # 断言落在业务输出上，不是"命令能启动"
    assert "BENCH_OK" in job_block, "install-smoke 未断言 BENCH_OK"
    assert "rules --city" in job_block, "install-smoke 未跑 rules"
