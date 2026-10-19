"""冻结态验收：中立目录 + 剥离 PATH 跑 CLI 通路。

纪律（plan/05 §6）：**别在仓库树内跑**——CWD 上溯会命中仓库 data，
"内嵌数据"验了个寂寞（假结果陷阱）。

验的是**产物**而非源码（plan/05 §6 的"构建后三断言"）：
1. dist 全树禁区扫描（只匹配 dist 顶层）
2. 内嵌数据逐份 sha256 与仓库冻结件对账（防"打进包的是旧数据"）
3. 冻结态判定与源码运行同结论（防"内嵌数据验了个寂寞"）
4. 冻结态导出的报告无外链（断网可开，在产物上复跑一遍）
5. CLI 产物无出网栈（零上传是**产物级**可核验，不只是代码声明）

用法：
    py -3.12 -X utf8 tools/verify_package.py --dist dist/rca-cli
    py -3.12 -X utf8 tools/verify_package.py --dist dist/rca-gui --gui-selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.packaging import BUNDLE_DATA_DIR, build_datas, package_data_dir  # noqa: E402
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 禁区成分：只匹配 dist **顶层**（依赖包自带的同名子目录不算泄露）
FORBIDDEN_TOP_LEVEL = ("plan", "tests", "_private", ".git", "src", "tools")

# CLI 产物不得携带出网栈（spec 已排除；此处核验排除项**真生效**）。
# 只查 CLI：GUI 目标按 spec 保留（Qt 依赖面更宽，且非本次零上传承诺的验证对象）。
FORBIDDEN_NETWORK_MODULES = ("_ssl", "libssl", "libcrypto", "_socket", "_hashlib")

# 演示样例（README/验收共用的那份输入）——随包数据在 `src/rca/data/` 下
DEMO_SAMPLE = "samples/demo-contract-bj.txt"


def demo_sample_path() -> Path:
    """演示样例在仓库内的绝对路径（包内数据根之下）。"""
    return package_data_dir(ROOT) / DEMO_SAMPLE


def _exe_names() -> dict:
    return {"cli": "rca-cli.exe", "gui": "rca-gui.exe"}


def _find_exe(dist: Path, kind: str) -> Path:
    name = _exe_names()[kind]
    cand = dist / name
    if cand.is_file():
        return cand
    # onedir 布局：exe 在 dist/<name>/<name>.exe
    for p in dist.rglob(name):
        return p
    raise FileNotFoundError("未找到 exe %s（dist=%s）" % (name, dist))


def check_top_level(dist: Path) -> list:
    problems = []
    for child in sorted(dist.iterdir()):
        if child.name in FORBIDDEN_TOP_LEVEL:
            problems.append("dist 顶层出现禁区成分: %s" % child.name)
    return problems


def find_embedded_data(dist: Path) -> Path | None:
    """定位包内 data/（PyInstaller 6 onedir → `_internal/data`）。"""
    cands = [dist / "_internal" / "data", dist / "data"]
    cands += sorted(p for p in dist.rglob("data") if p.is_dir())
    for c in cands:
        if (c / "knowledge").is_dir():
            return c
    return None


def expected_packed_entries() -> dict:
    """{产物内相对 data/ 的路径: 仓库源文件}——白名单的单一投影。

    产物内布局由 `rca.packaging.build_datas()` 的目标目录决定
    （`data/<子目录>/<文件名>`）；仓库源文件在包内数据根 `src/rca/data/`。
    """
    out = {}
    for src, dest in build_datas(ROOT):
        rel = (Path(dest).relative_to(BUNDLE_DATA_DIR) / Path(src).name).as_posix()
        out[rel] = Path(src)
    return out


def check_embedded_data_sha256(dist: Path) -> list:
    """内嵌数据逐份 sha256 与仓库冻结件对账，且**入包集合 == 白名单**。

    防三种产物级问题：
    - 白名单漏拷（构建期残留旧产物被 COLLECT 复用）；
    - datas 目标目录写错 → sha 对得上但位置不对；
    - 包内混进白名单外的文件（"多余东西悄悄进包"）。
    """
    problems = []
    embedded = find_embedded_data(dist)
    if embedded is None:
        return ["包内未找到 data/（内嵌数据缺失）"]

    expected = set()
    for src_abs, dest in build_datas(ROOT):
        src = Path(src_abs)
        rel_in_data = (Path(dest).relative_to(BUNDLE_DATA_DIR) / src.name).as_posix()
        expected.add("data/" + rel_in_data)
        packed = embedded / rel_in_data
        if not packed.is_file():
            problems.append("内嵌数据缺失: data/%s" % rel_in_data)
            continue
        want = hashlib.sha256(src.read_bytes()).hexdigest()
        got = hashlib.sha256(packed.read_bytes()).hexdigest()
        if want != got:
            problems.append("内嵌数据 sha256 失配: data/%s（包内为旧数据）" % rel_in_data)

    actual = {
        "data/" + p.relative_to(embedded).as_posix()
        for p in embedded.rglob("*")
        if p.is_file()
    }
    for extra in sorted(actual - expected):
        problems.append("包内出现白名单外的数据文件: %s" % extra)
    return problems


def check_no_network_modules(dist: Path) -> list:
    """CLI 产物不得含出网栈——"零上传"在产物级可核验。"""
    problems = []
    for p in dist.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if any(tok in name for tok in FORBIDDEN_NETWORK_MODULES):
            problems.append("CLI 产物含出网组件: %s" % p.relative_to(dist).as_posix())
    return problems


def check_no_external_links(text: str, label: str) -> list:
    if re.search(r"\]\(https?://", text):
        return ["%s 含 Markdown 外链（断网不可开）" % label]
    return []


def _neutral_run(exe: Path, args: list) -> subprocess.CompletedProcess:
    """中立目录 + 剥离 PATH 下运行（防 CWD 上溯命中仓库 data）。"""
    with tempfile.TemporaryDirectory() as td:
        env = {"SystemRoot": os.environ.get("SystemRoot", ""), "TEMP": td, "TMP": td}
        return subprocess.run(
            [str(exe)] + args,
            cwd=td,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )


def _neutral_run_with_file(exe: Path, args: list, src: Path) -> subprocess.CompletedProcess:
    """同上，但先把 `src` 拷进中立目录（exe 读它，且不经仓库 CWD 上溯）。"""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / src.name
        work.write_bytes(src.read_bytes())
        env = {"SystemRoot": os.environ.get("SystemRoot", ""), "TEMP": td, "TMP": td}
        return subprocess.run(
            [str(exe)] + [a.replace("{file}", work.name) for a in args],
            cwd=td,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )


def parse_verdict(text: str) -> str | None:
    """从 CLI 输出里抽出整体判定状态。

    状态是 ASCII 标识（`noncompliant` / `compliant` / `not_assessed` / `unknown`），
    用 `[A-Za-z_]+` 收口——否则紧跟其后的全角括号会被一起吞掉，
    两个不同的输出可能被误判成"一致"（对账变假绿）。
    """
    m = re.search(r"整体判定：([A-Za-z_]+)", text)
    return m.group(1) if m else None


def check_frozen_check_matches_source(dist: Path, exe: Path) -> list:
    """冻结态判定结论与源码运行**必须一致**（同一输入同一结论）。

    这是"内嵌数据真的被用上了"的行为级证据：数据不对/没读到，结论就会分叉。
    """
    from rca.cli import EXIT_NONCOMPLIANT

    problems = []
    demo = demo_sample_path()
    if not demo.is_file():
        return ["演示样例缺失: %s" % DEMO_SAMPLE]

    proc = _neutral_run_with_file(
        exe, ["check", "--input", "{file}", "--city", "北京"], demo
    )
    frozen_out = proc.stdout

    # 源码运行取同一结论（从 stdout 抽整体判定；退出码语义另见 test_cli_contract）
    src_proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "rca.cli", "check",
         "--input", str(demo), "--city", "北京"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    src_out = src_proc.stdout

    fv, sv = parse_verdict(frozen_out), parse_verdict(src_out)
    if fv is None:
        problems.append("冻结态 check 未输出整体判定（结论不可读）")
    if sv is None:
        problems.append("源码态 check 未输出整体判定（结论文本形态变了）")
    if fv != sv:
        problems.append("冻结态判定(%s) 与源码判定(%s) 不一致" % (fv, sv))
    if proc.returncode != src_proc.returncode:
        problems.append(
            "冻结态退出码(%d) 与源码退出码(%d) 不一致"
            % (proc.returncode, src_proc.returncode)
        )
    if proc.returncode not in (0, EXIT_NONCOMPLIANT):
        problems.append("冻结态 check 退出码异常: %d" % proc.returncode)

    problems += check_no_external_links(frozen_out, "冻结态 check 输出")
    return problems


def check_gui_rejects_unknown_args(dist: Path, exe: Path) -> list:
    """GUI exe 必须**拒绝**不认识的参数并立刻退出（不得挂进事件循环）。

    窗口版没有终端：静默忽略参数会让验收器看起来在跑、实则超时挂死
    （M5 验收实测踩到——`rca-gui check --input x.txt` 180s 超时）。
    """
    proc = _neutral_run(exe, ["check", "--input", "nope.txt", "--city", "北京"])
    if proc.returncode == 2:
        return []
    return [
        "GUI exe 未拒绝未知参数（退出码 %d，期望 2）——窗口版会挂死验收器"
        % proc.returncode
    ]


def check_frozen_report_no_external(dist: Path, exe: Path) -> list:
    """冻结态导出的报告必须**无外链**（断网可开）。

    plan/05 DoD 明写："报告无 `](http` 外链（已有 `test_markdown_has_no_external_links`，
    须在**冻结产物**上复跑一遍）"。源码侧的同类断言证明不了包内渲染器与
    内嵌数据的组合产物也没有外链——故这里在真 exe 的真报告上复跑。
    """
    problems = []
    demo = demo_sample_path()
    if not demo.is_file():
        return ["演示样例缺失: %s" % DEMO_SAMPLE]

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        contract = work / demo.name
        contract.write_bytes(demo.read_bytes())
        env = {"SystemRoot": os.environ.get("SystemRoot", ""), "TEMP": td, "TMP": td}
        out_dir = work / "rep"
        proc = subprocess.run(
            [str(exe), "report", "--input", contract.name, "--city", "北京",
             "--out", str(out_dir)],
            cwd=td,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if proc.returncode not in (0, 1):
            return ["冻结态 report 退出码异常: %d（%s）" % (proc.returncode, proc.stdout[:200])]

        md = out_dir / "体检报告.md"
        xlsx = out_dir / "体检报告.xlsx"
        if not md.is_file():
            problems.append("冻结态 report 未产出 Markdown")
        else:
            problems += check_no_external_links(
                md.read_text(encoding="utf-8"), "冻结态报告 Markdown"
            )
        if not xlsx.is_file():
            problems.append("冻结态 report 未产出 XLSX")
        else:
            problems += check_xlsx_no_external_rels(xlsx)
    return problems


def check_xlsx_no_external_rels(xlsx: Path) -> list:
    """XLSX 不得含 External 关系（断网可开）。"""
    import zipfile

    problems = []
    with zipfile.ZipFile(xlsx) as zf:
        for name in zf.namelist():
            if name.endswith(".rels"):
                if b"External" in zf.read(name):
                    problems.append("冻结态报告 XLSX 含外部关系: %s" % name)
    return problems


def verify(dist: Path, gui_selftest: bool) -> int:
    problems = check_top_level(dist)
    if problems:
        for p in problems:
            print("FAIL " + p)
        return 1

    kind = "gui" if gui_selftest else "cli"
    try:
        exe = _find_exe(dist, kind)
    except FileNotFoundError as exc:
        print("FAIL %s" % exc)
        return 1
    print("待验 exe: %s" % exe)

    problems += check_embedded_data_sha256(dist)
    if kind == "cli":
        problems += check_no_network_modules(dist)

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "selftest.json"
        proc = _neutral_run(exe, ["--selftest", str(out)])
        print("selftest 退出码: %d" % proc.returncode)
        if proc.stdout.strip():
            print(proc.stdout.strip()[:800])
        if proc.returncode != 0:
            problems.append("冻结态自检非零退出")
        if not out.is_file():
            problems.append("自检未写出结论文件")
        else:
            payload = json.loads(out.read_text(encoding="utf-8"))
            if not payload.get("frozen"):
                problems.append("自检未报告 frozen=true（可能跑的不是冻结态）")
            if payload.get("data_dir_in_dist") is not True:
                problems.append(
                    "数据目录未落在 exe 目录内（内嵌数据失效，会回头读开发机仓库）"
                )
            if payload.get("bj_rule_count", 0) <= 0:
                problems.append("规则数为 0")

    # 判定通路：CLI exe 真跑 check/report 并与源码对账；GUI exe 走参数纪律检查
    # （窗口版无终端的脚本化通路就是 `--selftest`，计划口径如此）
    if kind == "cli":
        problems += check_frozen_check_matches_source(dist, exe)
        problems += check_frozen_report_no_external(dist, exe)
    else:
        problems += check_gui_rejects_unknown_args(dist, exe)

    if problems:
        print("\n验收未通过：")
        for p in problems:
            print("  - %s" % p)
        return 1
    print("PACKAGE_VERIFY_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="冻结态验收（中立目录 + 剥离 PATH）")
    ap.add_argument("--dist", required=True, help="dist 目录")
    ap.add_argument("--gui-selftest", action="store_true", help="验 GUI exe")
    args = ap.parse_args(argv)
    dist = Path(args.dist)
    if not dist.is_dir():
        print("FAIL dist 目录不存在: %s" % dist)
        return 1
    return verify(dist, args.gui_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
