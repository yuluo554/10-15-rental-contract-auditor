"""CLI：合同体检入口（唯一对外命令入口）。

退出码语义（plan/03 §9，定稿后锁进测试）：
  0 = 完成（无论是否检出不符合）
  1 = 检出 noncompliant（判定类工具的既定语义）
  2 = 输入不可用 / 用法错误 / 参数错误 / input_required 缺失
  3 = 缺可选依赖（如 GUI 的 PySide6）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .engine.pipeline import (
    PipelineError,
    compute_result,
    diagnostics,
    has_noncompliant,
    parameter_overview,
    ruleset_overview,
)
from .model import Result, STATUS_NONCOMPLIANT
from .paths import data_path_in_dist, find_data_dir, is_frozen
from .report.markdown import render_markdown
from .report.ooxml import render_xlsx_bytes
from .report.sections import report_sections
from .stdio import ensure_utf8_stdio

__all__ = ["main"]

EXIT_OK = 0
EXIT_NONCOMPLIANT = 1
EXIT_USAGE = 2
EXIT_MISSING_DEP = 3


def _read_text(path: Path) -> str:
    """读合同文本；UTF-8 优先，回落 GB18030（并如实记录）。"""
    raw = path.read_bytes()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _load_contract(args) -> str:
    if args.text is not None:
        return args.text
    if args.input is not None:
        p = Path(args.input)
        if not p.is_file():
            raise PipelineError("输入文件不存在: %s" % p)
        return _read_text(p)
    raise PipelineError("请提供 --input <合同文件> 或 --text <合同文本>")


def _sources_rows(city: str, data_dir: Optional[str]) -> List[List[str]]:
    out = []
    for p in parameter_overview(city, data_dir):
        out.append(
            [
                p["rule_id"],
                p["clause"] or "—",
                p["source_title"] or "—",
                p["doc_no"] or "—",
                p["effective_date"] or "—",
                p["url"] or "—",
            ]
        )
    return out


def cmd_check(args) -> int:
    text = _load_contract(args)
    city = args.city
    result = compute_result(text, city, data_dir=args.data)

    if args.json:
        payload = result.to_dict()
        payload["sources"] = parameter_overview(city, args.data)
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        rows = _sources_rows(city, args.data)
        md = render_markdown(result, rows)
        sys.stdout.write(md)
        sys.stdout.write("\n整体判定：%s\n" % result.overall_summary())

    if args.report:
        _write_reports(result, city, args)

    return EXIT_NONCOMPLIANT if has_noncompliant(result) else EXIT_OK


def _write_reports(result: Result, city: str, args) -> None:
    from .report.sections import assert_traceable

    rows = _sources_rows(city, args.data)
    assert_traceable(result, rows)
    out = Path(args.report)
    out.mkdir(parents=True, exist_ok=True)
    sections = report_sections(result)
    for sec in sections:
        if sec.key == "sources":
            sec.table = {
                "headers": ["规则 ID", "条款号", "来源文件", "文号", "施行日期", "URL"],
                "rows": rows,
            }
    md_path = out / "体检报告.md"
    md_path.write_bytes(render_markdown(result, rows).encode("utf-8"))
    xlsx_path = out / "体检报告.xlsx"
    xlsx_path.write_bytes(render_xlsx_bytes(sections))
    sys.stdout.write("已导出报告: %s / %s\n" % (md_path, xlsx_path))


def cmd_scan(args) -> int:
    """批量：失败隔离（单件异常不中断整批），失败件单列不吞掉。"""
    root = Path(args.dir)
    if not root.is_dir():
        print("目录不存在: %s" % root, file=sys.stderr)
        return EXIT_USAGE
    files = sorted(p for p in root.glob("*.txt"))
    if not files:
        print("目录下无 .txt 合同文件: %s" % root, file=sys.stderr)
        return EXIT_USAGE

    any_noncompliant = False
    failed = []
    for f in files:
        try:
            text = _read_text(f)
            result = compute_result(text, args.city, data_dir=args.data)
        except PipelineError as exc:
            failed.append((f.name, str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 - 失败隔离：单件异常不中断整批
            failed.append((f.name, "%s: %s" % (type(exc).__name__, exc)))
            continue
        flag = "不符合" if has_noncompliant(result) else result.overall_status
        print("%-40s %s" % (f.name, flag))
        if has_noncompliant(result):
            any_noncompliant = True

    if failed:
        print("\n以下文件未能判定（未判定 ≠ 违规）：")
        for name, why in failed:
            print("  %-40s %s" % (name, why))

    return EXIT_NONCOMPLIANT if any_noncompliant else EXIT_OK


def cmd_rules(args) -> int:
    info = ruleset_overview(args.city, args.data)
    diag = diagnostics(args.city, args.data)
    payload = {"overview": info, "diagnostics": diag}
    if args.json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return EXIT_OK
    print("规则包：%s（%s，v%s）" % (info["ruleset_id"], info["city"], info["version"]))
    print("条目数：%d（本次生效 %d）" % (info["rule_count"], diag["enabled_count"]))
    print("\n来源：")
    for s in info["sources"]:
        print("  - %s（%s，%s 施行）" % (s["title"], s["doc_no"], s["effective_date"]))
    print("\n基准验收门槛（随规则包下发）：")
    for k, v in sorted(info["thresholds"].items()):
        print("  %s = %s" % (k, v))
    print("\n覆盖登记：")
    cov = info["coverage"]
    print("  规则总数：%s" % cov.get("rule_total"))
    for k, v in sorted((cov.get("rule_totals_by_check_type") or {}).items()):
        print("  %-24s %s" % (k, v))
    if diag["disabled"]:
        print("\n未启用（数值核对状态非 verified）：")
        for d in diag["disabled"]:
            print("  - %s：%s" % (d["rule_id"], d["reason"]))
    return EXIT_OK


def cmd_report(args) -> int:
    text = _load_contract(args)
    result = compute_result(text, args.city, data_dir=args.data)
    _write_reports(result, args.city, args)
    return EXIT_NONCOMPLIANT if has_noncompliant(result) else EXIT_OK


def cmd_bench(args) -> int:
    """基准：惰性导入 benchmark 包（首期骨架为占位实现）。"""
    try:
        from .benchmark.runner import run_benchmarks
    except ImportError as exc:
        print("基准模块不可用: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    return run_benchmarks(
        only=args.only, data_dir=args.data, suite=args.suite
    )


def cmd_selftest(args) -> int:
    """冻结态自检：数据目录定位 + 规则数 + GUI 装配（如可用）。

    窗口版 stdout 不接终端，故结论写文件回传、退出码携带成败。
    """
    report = {"version": __version__, "frozen": is_frozen()}
    rc = EXIT_OK
    try:
        data_dir = find_data_dir(args.data)
        report["data_dir"] = str(data_dir)
        report["data_dir_in_dist"] = data_path_in_dist(data_dir)
        if is_frozen() and report["data_dir_in_dist"] is not True:
            report["error"] = "冻结态数据目录未落在 exe 目录内"
            rc = EXIT_USAGE
        info = ruleset_overview("北京", str(data_dir))
        report["bj_rule_count"] = info["rule_count"]
        if info["rule_count"] <= 0:
            report["error"] = "规则数为 0"
            rc = EXIT_USAGE
    except Exception as exc:  # noqa: BLE001
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
        rc = EXIT_USAGE

    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_bytes(payload.encode("utf-8"))
        print("自检结论已写入: %s" % args.out)
    else:
        sys.stdout.write(payload)
    return rc


def cmd_gui(args) -> int:
    """GUI 惰性导入：try 包住**从 import 到调用完成**的整段。

    分层守门要求重件只在函数体内 import → 真正的缺依赖异常在后面的调用
    阶段才抛，"只包 import 行"会漏（抛裸异常而非 exit 3）。
    """
    try:
        from .gui.app import run_gui

        return run_gui(data_dir=args.data)
    except ImportError as exc:
        print(
            "GUI 需要可选依赖 PySide6。源码态安装：pip install -e \".[gui]\"\n"
            "（若为发行包，本包可能未内嵌该功能）\n原因：%s" % exc,
            file=sys.stderr,
        )
        return EXIT_MISSING_DEP


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rca",
        description="房屋租赁合同审计器（租客视角）——辅助参考的合同体检，不构成法律意见。",
    )
    ap.add_argument("--version", action="version", version="rca %s" % __version__)
    sub = ap.add_subparsers(dest="command")

    common_data = dict(help="data/ 目录路径（默认自动定位）")

    p = sub.add_parser("check", help="单件合同体检")
    p.add_argument("--input", help="合同文本文件路径")
    p.add_argument("--text", help="直接传入合同文本")
    p.add_argument("--city", required=True, help="城市（北京/上海/全国）")
    p.add_argument("--data", **common_data)
    p.add_argument("--json", action="store_true", help="输出 JSON（机读）")
    p.add_argument("--report", help="同时导出报告到该目录")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("scan", help="批量合同体检（失败隔离）")
    p.add_argument("--dir", required=True, help="含 .txt 合同的目录")
    p.add_argument("--city", required=True, help="城市（北京/上海/全国）")
    p.add_argument("--data", **common_data)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("report", help="导出体检报告（Markdown + XLSX）")
    p.add_argument("--input", help="合同文本文件路径")
    p.add_argument("--text", help="直接传入合同文本")
    p.add_argument("--city", required=True, help="城市（北京/上海/全国）")
    p.add_argument("--out", dest="report", required=True, help="报告输出目录")
    p.add_argument("--data", **common_data)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("rules", help="查看规则包与门控状态")
    p.add_argument("--city", required=True, help="城市（北京/上海/全国）")
    p.add_argument("--data", **common_data)
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("bench", help="内置基准（一键复跑）")
    p.add_argument("--only", help="只跑指定套件")
    p.add_argument("--suite", help="套件集合（逗号分隔）")
    p.add_argument("--data", **common_data)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("selftest", help="冻结态自检（结论写文件回传）")
    p.add_argument("--out", help="自检结论输出文件")
    p.add_argument("--data", **common_data)
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("gui", help="启动桌面界面（需 [gui] 可选依赖）")
    p.add_argument("--data", **common_data)
    p.set_defaults(func=cmd_gui)

    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_stdio()
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except PipelineError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return EXIT_USAGE
    except FileNotFoundError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
