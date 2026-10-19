"""零政策字面量门禁。

纪律（plan/02 §4、skill 阶段 1）：全部规则包数值收编为禁用 token，
对**引擎/基准/前端/CLI 源码**做扫描，**连文档字符串与注释一起扫**。

两条关键设计：
1. **token 运行时实算**——从规则包 JSON 读出数值再构造 token，
   源码与留档**零词面**。门禁自己的输入也不许是代码字面量。
2. **豁免口径写死**——精度约定（两位小数）、日历常数等小值豁免，
   否则门禁刷屏被运维性忽略。

用法：
    py -3.12 -X utf8 tools/check_literals.py             # 扫描
    py -3.12 -X utf8 tools/check_literals.py --selftest   # 阳性/阴性对照
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [
    ROOT / "src" / "rca" / "engine",
    ROOT / "src" / "rca" / "benchmark",
    ROOT / "src" / "rca" / "report",
    ROOT / "src" / "rca" / "parser",
    ROOT / "src" / "rca" / "cli.py",
    ROOT / "src" / "rca" / "gui",
]

# 豁免口径（写死，防刷屏）——**这是本门禁的已知覆盖缺口，如实记录**：
# 本项目的政策数值多为个位数（押金 1 个月、收租 3 个月、退押金 3 个工作日），
# 把单/个位数当 token 会把 `range(1, n)`、`len(x) == 3` 这类结构性常数全打成命中，
# 门禁将被运维性忽略（"刷屏"比"漏报"更危险：它让门禁事实上失效）。
# 故只收编 **≥10** 的规则数值（本项目实际为 20 年、30 日）+ 全部年度数字。
# 缺口面由 selftest 阳性对照与"引擎源码零政策字面量"的代码审查共同兜底。
SMALL_VALUE_EXEMPT_BELOW = 10
# 年度数字也是禁用 token（政策随时间变，年份属政策元数据）
YEAR_MIN = 1900
YEAR_MAX = 2100


def compute_banned_tokens(data_dir: Path) -> Dict[str, Set[str]]:
    """从规则包**实算**禁用 token。源码里不出现任何政策数值字面量。"""
    import json

    tokens: Dict[str, Set[str]] = {"policy_numbers": set(), "years": set()}
    rules_dir = data_dir / "rules"
    if not rules_dir.is_dir():
        return tokens
    for path in sorted(rules_dir.glob("ruleset-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for rule in data.get("rules", []):
            value = rule.get("value")
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, int):
                if value >= SMALL_VALUE_EXEMPT_BELOW:
                    tokens["policy_numbers"].add(str(value))
                    # 对应小数形态
                    tokens["policy_numbers"].add("%d.0" % value)
                    tokens["policy_numbers"].add("%d.00" % value)
                if YEAR_MIN <= value <= YEAR_MAX:
                    tokens["years"].add(str(value))
            elif isinstance(value, float):
                text = ("%g" % value)
                tokens["policy_numbers"].add(text)
    return tokens


def _iter_scan_files() -> List[Path]:
    out: List[Path] = []
    for target in SCAN_DIRS:
        if target.is_file():
            out.append(target)
        elif target.is_dir():
            out.extend(sorted(p for p in target.rglob("*.py") if "__pycache__" not in p.parts))
    return out


def scan(data_dir: Path) -> List[Tuple[str, int, str, str]]:
    """返回 [(文件, 行号, token, 行内容)]。"""
    tokens = compute_banned_tokens(data_dir)
    all_tokens = set(tokens["policy_numbers"]) | set(tokens["years"])
    if not all_tokens:
        return []
    # 词边界匹配（数字形态需两侧非数字，防 300 命中 3000）
    patterns = [
        (t, re.compile(r"(?<![\d.])" + re.escape(t) + r"(?![\d])")) for t in sorted(all_tokens)
    ]
    hits: List[Tuple[str, int, str, str]] = []
    for path in _iter_scan_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if "literal-gate-allow" in line:
                continue
            for token, pat in patterns:
                if pat.search(line):
                    hits.append((str(path.relative_to(ROOT)), i, token, line.strip()[:100]))
    return hits


def provenance(data_dir: Path) -> str:
    tokens = compute_banned_tokens(data_dir)
    return "token provenance: 政策数值 %d 个 / 年度 %d 个（实算自 %s）" % (
        len(tokens["policy_numbers"]),
        len(tokens["years"]),
        (data_dir / "rules").relative_to(ROOT).as_posix(),
    )


def cmd_scan(data_dir: Path) -> int:
    print(provenance(data_dir))
    hits = scan(data_dir)
    if not hits:
        print("LITERAL_GATE_OK")
        return 0
    print("命中 %d 处：" % len(hits))
    for f, ln, token, line in hits:
        print("  %s:%d [%s] %s" % (f, ln, token, line))
    return 1


def cmd_selftest(data_dir: Path) -> int:
    """阳性/阴性对照：证明门禁真的会红，且不误报。"""
    tokens = compute_banned_tokens(data_dir)
    if not tokens["policy_numbers"] and not tokens["years"]:
        print("SELFTEST_FAIL 无 token 可对照（规则包缺失？）")
        return 1

    # 阳性对照：拿一个真实 token 构造一行"像源码"的文本，断言能命中
    sample_token = sorted(tokens["policy_numbers"] or tokens["years"])[0]
    probe = "LIMIT = %s  # 故意植入" % sample_token
    pat = re.compile(r"(?<![\d.])" + re.escape(sample_token) + r"(?![\d])")
    if not pat.search(probe):
        print("SELFTEST_FAIL 阳性对照未命中 token=%s" % sample_token)
        return 1

    # 阴性对照：词边界不得把 300 命中 3000
    if sample_token.isdigit():
        longer = sample_token + "0"
        if pat.search("VALUE = %s" % longer):
            print("SELFTEST_FAIL 阴性对照误报（词边界失效）token=%s" % sample_token)
            return 1

    print("LITERAL_GATE_SELFTEST_OK（token=%d 个，阳性/阴性对照通过）" % len(tokens["policy_numbers"]))
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="零政策字面量门禁")
    ap.add_argument("--selftest", action="store_true", help="阳性/阴性对照")
    ap.add_argument("--data", help="data/ 目录")
    args = ap.parse_args(argv)
    if args.data:
        data_dir = Path(args.data)
    else:
        data_dir = ROOT / "src" / "rca" / "data"
    return cmd_selftest(data_dir) if args.selftest else cmd_scan(data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
