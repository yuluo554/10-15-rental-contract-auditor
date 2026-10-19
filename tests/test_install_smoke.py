"""装态守门：**非 editable 安装**必须能跑（D1 的回归防线）。

缺陷背景（本轮实测）：数据原先在仓库根 `data/`（包外）且 `pyproject.toml` 无
`package-data`，wheel 里一个数据文件都没有。editable 安装下 `paths.py` 靠开发树
上溯命中仓库根，所以 CI 四个 job 全绿；但 `pip install <wheel>` 后：

    rca rules --city 北京  → exit 2「未找到 data/ 目录」
    rca bench             → exit 2

`test_spec_*` 那批守门全部只覆盖 exe（PyInstaller 白名单），**没有任何一条**覆盖
wheel 形态——这正是"测试全绿 ≠ 装完能用"。本文件补上这条通路：

    建 wheel → 建全新 venv → 装 wheel → 在中立目录跑 rules / bench / check

断言落在**规则条数**、`BENCH_OK` 与 `check` 退出码上（不是"命令能启动"）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_DATA = ROOT / "src" / "rca" / "data"
PACKAGE_DATA_TOML = ROOT / "pyproject.toml"


# --------------------------------------------------------------------------
# 轻量守门（秒级）：布局与声明同源，坏掉时在这里就红
# --------------------------------------------------------------------------

def test_package_data_declaration_matches_whitelist():
    """`pyproject.toml` 的 package-data 必须覆盖**wheel 应带**的全部数据。

    `build_datas()` 是 exe 的白名单单一事实源；wheel 走的是 setuptools 的
    `package-data` 声明——两者覆盖集合不一致时，exe 能跑而 wheel 不能（正是 D1）。

    wheel 的集合 = exe 白名单 + `WHEEL_EXTRA`（装态演示样例）。两个方向都要守：
    漏了白名单项 → 装态 `rules`/`bench` exit 2；漏了 WHEEL_EXTRA → README 命令当场 exit 2。
    """
    from rca.packaging import WHITELIST, WHEEL_EXTRA, package_data_dir, wheel_data_entries

    # 超集方向：WHEEL_EXTRA 只增不减（不得把白名单项挪出去）
    assert set(wheel_data_entries()) >= set(WHITELIST), "WHEEL_EXTRA 覆盖掉了白名单项"
    assert set(wheel_data_entries()) == set(WHITELIST) | set(WHEEL_EXTRA)

    declared = PACKAGE_DATA_TOML.read_text(encoding="utf-8")
    assert "[tool.setuptools.package-data]" in declared, "pyproject 未声明 package-data"

    for rel in wheel_data_entries():
        p = package_data_dir(ROOT) / rel
        assert p.is_file(), "wheel 数据在包内数据根缺失: %s" % rel

    # 逐条落到 glob 上：子目录必须被某个 pattern 覆盖
    patterns = []
    for line in declared.splitlines():
        line = line.strip()
        if line.startswith('"data/'):
            patterns.append(line.strip('",'))
    assert patterns, "package-data 里没有 data/ 条目"

    import fnmatch

    for rel in wheel_data_entries():
        target = "data/" + rel
        covered = any(fnmatch.fnmatch(target, pat) for pat in patterns)
        assert covered, "package-data 未覆盖 wheel 数据项: %s（patterns=%s）" % (target, patterns)


def test_paths_resolves_package_data_before_dev_tree():
    """`paths.py` 的包内分支必须存在，且排在开发树上溯之前。

    装态下没有开发树可上溯，包内分支是唯一通路；若它被删或被挪到兜底之后，
    装态就会退回"D1 的 exit 2"。
    """
    from rca import paths

    cands = paths._candidates()
    pkg = paths.package_data_dir().resolve()
    assert pkg in [c.resolve() for c in cands], "候选里没有包内数据目录"

    pkg_idx = [c.resolve() for c in cands].index(pkg)
    dev_idx = None
    for i, c in enumerate(cands):
        if "knowledge" in str(c) or c.name == "data":
            if i != pkg_idx and (c / "knowledge").is_dir() and c.resolve() != pkg:
                dev_idx = i
                break
    if dev_idx is not None:
        assert pkg_idx < dev_idx, "包内分支排在开发树上溯之后（装态会被开发树抢先）"

    # 包内数据确实可定位且带规则包
    d = paths.find_data_dir()
    assert (d / "rules" / "ruleset-bj.json").is_file(), "find_data_dir 未定位到带规则包的目录"


# --------------------------------------------------------------------------
# 重量守门（分钟级）：真建 wheel + 真建 venv + 真装 + 真跑
# --------------------------------------------------------------------------

def _run(cmd, cwd, env=None, timeout=600):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _clean_env():
    """中立环境：不带 PYTHONPATH（否则装态可能被源码树顶掉）。"""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _venv_python(venv_dir: Path) -> Path:
    """venv 解释器路径（Windows 是 `python.exe`，POSIX 是 `python`）。"""
    exe = "python.exe" if os.name == "nt" else "python"
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / exe


def _venv_exe(venv_dir: Path, name: str) -> Path:
    """venv 里的可执行文件（`rca` 入口；Windows 带 `.exe`）。"""
    suffix = ".exe" if os.name == "nt" else ""
    return venv_dir / ("Scripts" if os.name == "nt" else "bin") / (name + suffix)


@pytest.fixture(scope="module")
def installed_venv(tmp_path_factory):
    """建 wheel → 建全新 venv → 装 → 返回 (venv_python, venv_root)。

    **不复用开发 `.venv`**：开发环境有 editable 安装与仓库 CWD，验不出装态问题。

    构建前清掉 `src/rca.egg-info/` 与 `build/`：setuptools 的 `SOURCES.txt` 是
    增量文件，本地反复构建后它可能留着上一轮的 `data/` 条目——那样**即使删掉
    `package-data`，wheel 里照样有数据**（本轮负控实测踩到：先误判成"门禁无效"）。
    CI 是干净 clone 不受影响，但门禁必须在本地也可证伪。
    """
    for stale in (ROOT / "src" / "rca.egg-info", ROOT / "build"):
        if stale.exists():
            shutil.rmtree(stale, ignore_errors=True)

    work = tmp_path_factory.mktemp("install-smoke")
    wheel_dir = work / "wheel"
    wheel_dir.mkdir()

    env = _clean_env()
    proc = _run(
        [sys.executable, "-m", "pip", "wheel", ".", "-w", str(wheel_dir), "--no-deps"],
        cwd=ROOT,
        env=env,
    )
    assert proc.returncode == 0, "构建 wheel 失败：\n%s" % proc.stdout
    wheels = sorted(wheel_dir.glob("*.whl"))
    assert wheels, "未产出 wheel"

    venv_dir = work / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(str(venv_dir))
    venv_py = _venv_python(venv_dir)
    assert venv_py.is_file(), "venv 未生成 python: %s" % venv_py

    proc = _run(
        [str(venv_py), "-m", "pip", "install", "--no-index", str(wheels[0])],
        cwd=work,
        env=env,
    )
    assert proc.returncode == 0, "干净环境安装 wheel 失败：\n%s" % proc.stdout
    return venv_py, venv_dir


def _neutral_cwd(tmp_path):
    """中立目录：不带任何仓库痕迹（CWD 上溯是"装态看着能用"的主要假绿来源）。"""
    d = tmp_path / "neutral"
    d.mkdir()
    return d


def _installed_sample(venv_py: Path) -> Path:
    """装态里的演示样例（site-packages/rca/data/samples/…）。"""
    proc = _run(
        [str(venv_py), "-c", "import rca, os; print(os.path.dirname(rca.__file__))"],
        cwd=Path(os.environ.get("TEMP", ".")),
        env=_clean_env(),
    )
    assert proc.returncode == 0, proc.stdout
    pkg = Path(proc.stdout.strip().splitlines()[-1])
    return pkg / "data" / "samples" / "demo-contract-bj.txt"


def test_installed_package_finds_its_own_data(installed_venv, tmp_path):
    """装态 `find_data_dir()` 必须落在 site-packages 内（不是开发机仓库）。"""
    venv_py, venv_dir = installed_venv
    cwd = _neutral_cwd(tmp_path)
    proc = _run(
        [str(venv_py), "-c",
         "from rca.paths import find_data_dir; print(find_data_dir())"],
        cwd=cwd,
        env=_clean_env(),
    )
    assert proc.returncode == 0, "装态找不到 data/（D1 回归）：\n%s" % proc.stdout
    resolved = proc.stdout.strip().splitlines()[-1]
    assert "site-packages" in resolved.replace("\\", "/"), (
        "装态定位到的 data/ 不在 site-packages 内（疑似 CWD 上溯命中仓库树）: %s" % resolved
    )


def test_installed_rules_reports_frozen_rule_count(installed_venv, tmp_path):
    """`rca rules --city 北京` 退出码 0，且规则条数与冻结规则包一致（> 0）。"""
    venv_py, _ = installed_venv
    cwd = _neutral_cwd(tmp_path)
    proc = _run([str(venv_py), "-m", "rca.cli", "rules", "--city", "北京"],
                cwd=cwd, env=_clean_env())
    assert proc.returncode == 0, (
        "装态 `rules` 退出码 %d（期望 0）——D1 回归：\n%s" % (proc.returncode, proc.stdout)
    )
    expected = len(
        json.loads((SRC_DATA / "rules" / "ruleset-bj.json").read_text(encoding="utf-8"))["rules"]
    )
    assert expected > 0, "规则包为空（冻结件被改坏？）"
    assert "条目数：%d" % expected in proc.stdout, (
        "装态 `rules` 输出的规则条数与冻结规则包不一致（期望 %d 条）：\n%s"
        % (expected, proc.stdout[:800])
    )


def test_installed_bench_passes(installed_venv, tmp_path):
    """装态 `rca bench` 退出码 0 且输出 `BENCH_OK`（三套件在装态同样达标）。"""
    venv_py, _ = installed_venv
    cwd = _neutral_cwd(tmp_path)
    proc = _run([str(venv_py), "-m", "rca.cli", "bench"], cwd=cwd, env=_clean_env())
    assert proc.returncode == 0, (
        "装态 `bench` 退出码 %d（期望 0）——D1 回归：\n%s" % (proc.returncode, proc.stdout)
    )
    assert "BENCH_OK" in proc.stdout, "装态 bench 未输出 BENCH_OK：\n%s" % proc.stdout[-800:]


def test_installed_check_uses_packaged_sample(installed_venv, tmp_path):
    """装态 `check` 用**包内**样例，退出码 1（与源码态同语义）。"""
    venv_py, _ = installed_venv
    cwd = _neutral_cwd(tmp_path)
    sample = _installed_sample(venv_py)
    assert sample.is_file(), "装态未带演示样例: %s（README 的命令会当场 exit 2）" % sample

    proc = _run(
        [str(venv_py), "-m", "rca.cli", "check",
         "--input", str(sample), "--city", "北京"],
        cwd=cwd, env=_clean_env(),
    )
    assert proc.returncode == 1, (
        "装态 `check` 退出码 %d（期望 1 = 检出不符合）：\n%s"
        % (proc.returncode, proc.stdout[:800])
    )
    assert "整体判定：noncompliant" in proc.stdout, (
        "装态 check 未给出与源码态一致的判定：\n%s" % proc.stdout[:800]
    )


def test_installed_wheel_ships_knowledge_raw_outside(installed_venv):
    """官方全文快照**不随包**（版权红线）：装态里不得出现 `knowledge/raw/`。"""
    venv_py, _ = installed_venv
    proc = _run(
        [str(venv_py), "-c",
         "import rca, os; p=os.path.join(os.path.dirname(rca.__file__),'data','knowledge');"
         "print(os.path.isdir(os.path.join(p,'raw')))"],
        cwd=Path(os.environ.get("TEMP", ".")),
        env=_clean_env(),
    )
    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.strip().splitlines()[-1] == "False", (
        "官方全文快照进了发行包（版权红线）：data/knowledge/raw/ 不该随包"
    )
