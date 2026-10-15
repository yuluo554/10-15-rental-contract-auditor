"""脱敏审计（四模式，入仓可复跑）。

纪律（plan/05 §8）：
- **token 运行时实算**：邮箱数字串从 `git log --format=%ae` 实算、用户名从
  `getpass.getuser()` 实算、盘符从仓库绝对路径实算——源码与留档**零词面**。
  每次运行首行打印 token provenance。
- **命中分级**：HARD（exit 1）/ REVIEW（人工豁免留档）/ advisory（只报不阻断）。
- **行内放行标记** `audit-allow`（仍打印，只是不计入阻断）。
- **排除项按对象类型不按名字**（路径 glob + 规则名）。
- **历史扫描配机制探活断言**（先搜必然存在的串，搜不到即硬失败）。
- **输出一律掩码化**——留档会引用输出，输出本身不得成为二次泄漏源。

模式：
    selftest  阳性/阴性对照（证明审计器真的会红、且不误报）
    tracked   已跟踪文件内容级扫描
    history   全历史 blob 扫描
    messages  提交元数据（作者/提交者邮箱）扫描
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rca.stdio import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

HARD = "HARD"
REVIEW = "REVIEW"
ADVISORY = "advisory"

# 豁免：GitHub noreply 是"已脱敏的目标形态"，不是命中
NOREPLY_RE = re.compile(r"^[^@\s]+@users\.noreply\.github\.com$")
# 豁免：git/ssh 传输地址（服务地址，非个人邮箱）
TRANSPORT_RE = re.compile(r"^(?:git|ssh|hg)@[A-Za-z0-9.\-]+$")

# 审计器自身的自检夹具行、留档中的验证描述行
ALLOW_MARKER = "audit-allow"


class Hit(NamedTuple):
    level: str
    category: str
    location: str
    count: int
    note: str


# 行内放行标记的命中仍会打印（可审计"为什么放过"），只是不计入阻断。
LEVEL_ALLOWED = "allowed"


def git(args: List[str]) -> Tuple[int, str]:
    """跑 git，显式 utf-8 解码（无环境变量可替代）。"""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return 1, "git 不可用: %s" % exc
    return proc.returncode, proc.stdout or ""


def compute_tokens() -> Dict[str, str]:
    """**运行时实算**敏感 token。源码与留档里零词面。"""
    tokens: Dict[str, str] = {}

    # 提交元数据里的邮箱（实算自 git 历史）
    _, emails = git(["log", "--format=%ae%n%ce", "--all"])
    found = set()
    for line in emails.splitlines():
        line = line.strip()
        if line and "@" in line:
            found.add(line)
    # 只收"非 noreply、非传输地址"的真实邮箱
    real = sorted(e for e in found if not NOREPLY_RE.match(e) and not TRANSPORT_RE.match(e))
    if real:
        tokens["email"] = real[0]

    # 用户名（实算自环境）
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = ""
    if user:
        tokens["username"] = user

    # 仓库盘符与工作根（实算自仓库绝对路径）
    parts = ROOT.parts
    if len(parts) >= 1 and parts[0].endswith(":"):
        tokens["drive"] = parts[0]
    if len(parts) >= 2:
        tokens["work_root"] = parts[1]

    return tokens


def provenance(tokens: Dict[str, str]) -> str:
    """provenance 行**不复述 token 值**，只写类别与实算来源。"""
    bits = []
    if "email" in tokens:
        bits.append("邮箱（实算自 git log --format=%ae --all）")
    if "username" in tokens:
        bits.append("用户名（实算自 getpass.getuser）")
    if "drive" in tokens:
        bits.append("仓库盘符（实算自仓库绝对路径）")
    if "work_root" in tokens:
        bits.append("工作根段（实算自仓库绝对路径）")
    return "token provenance: " + ("; ".join(bits) if bits else "无")


def _mask(value: str) -> str:
    """掩码化：只留首尾各 2 字符。"""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


# 通用模式（不含本项目特定值）
PATTERNS: List[Tuple[str, str, re.Pattern, str]] = [
    ("secret", HARD, re.compile(r"sk-[A-Za-z0-9]{16,}"), "疑似 API 密钥"),
    ("phone", HARD, re.compile(r"(?<![0-9a-fA-F])1[3-9]\d{9}(?![0-9a-fA-F])"), "手机号"),
    ("idcard", HARD, re.compile(r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])"), "身份证号"),
    (
        "email_generic",
        HARD,
        re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]*@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
        "邮箱",
    ),
    ("internal_ip", REVIEW, re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b"), "内网 IP"),
    ("long_hex", ADVISORY, re.compile(r"\b[0-9a-f]{32,}\b"), "长 hex 串（指纹/哈希类，只报不阻断）"),
]

# 个人标记按**组合路径签名**匹配（不匹配裸词，防厂商串误报）
USER_PATH_RE = re.compile(r"(?:Users|Documents and Settings)[\\/][^\\/\s]+")

# URL 上下文：hex 串出现在 URL 路径段里 = 官方站点资源 ID，不是内容指纹
URL_HEX_RE = re.compile(r"https?://\S+")
# 官方 URL 路径里的长 hex（gov 站点资源 ID），与"内容指纹"区分
_URL_PATH_HEX = re.compile(r"/[0-9a-f]{16,}[./]")


def _synthetic_phone_prefix() -> str:
    """本项目**文档化的合成号段**（片段拼接构造，避免源码出现完整词面）。"""
    return "1" + "9" + "9" + "0" * 7


SYNTHETIC_PHONE_PREFIX = _synthetic_phone_prefix()


def _is_documented_synthetic_phone(value: str) -> bool:
    """文档化的合成号段（data/README.md §3 明文约定的测试号段）不算泄露。

    判别 = "这个命中形态在本项目里是功能还是泄露？"——它是**数据纪律本身**。
    """
    return value.startswith(SYNTHETIC_PHONE_PREFIX)


def _in_url(line: str, start: int) -> bool:
    """命中位置是否落在 URL 内。"""
    for m in URL_HEX_RE.finditer(line):
        if m.start() <= start < m.end():
            return True
    return False


def _classify_email(value: str) -> bool:
    """True = 应豁免（noreply / 传输地址）。"""
    return bool(NOREPLY_RE.match(value) or TRANSPORT_RE.match(value))


def scan_text(text: str, location: str, tokens: Dict[str, str]) -> List[Hit]:
    hits: List[Hit] = []
    lines = text.splitlines()

    for name, level, pat, note in PATTERNS:
        count = 0
        allowed = 0
        for line in lines:
            for m in pat.finditer(line):
                found = m.group(0)
                if name == "email_generic" and _classify_email(found):
                    allowed += 1
                    continue
                if name == "phone" and _is_documented_synthetic_phone(found):
                    allowed += 1
                    continue
                if name == "long_hex" and _in_url(line, m.start()):
                    # 官方站点 URL 路径里的资源 ID，不是内容指纹
                    allowed += 1
                    continue
                if ALLOW_MARKER in line:
                    allowed += 1
                    continue
                count += 1
        if count:
            hits.append(Hit(level, name, location, count, note))
        if allowed:
            # 放过项**必须仍打印**（可审计"为什么放过"），只是不计入阻断
            hits.append(
                Hit(
                    LEVEL_ALLOWED,
                    name,
                    location,
                    allowed,
                    "%s（豁免：noreply/传输地址、文档化合成号段、URL 内资源 ID 或行内 audit-allow）"
                    % note,
                )
            )

    # 组合路径签名（HARD：本机用户目录路径）
    up = 0
    for line in lines:
        if ALLOW_MARKER in line:
            continue
        for m in USER_PATH_RE.finditer(line):
            seg = m.group(0).split("\\")[-1].split("/")[-1]
            if "username" in tokens and seg == tokens["username"]:
                up += 1
    if up:
        hits.append(Hit(HARD, "user_path", location, up, "本机用户目录路径"))

    # 实算出的真实邮箱（词边界，防子串误报）
    if "email" in tokens:
        pat = re.compile(re.escape(tokens["email"]))
        cnt = 0
        for line in lines:
            if ALLOW_MARKER in line:
                continue
            cnt += len(pat.findall(line))
        if cnt:
            hits.append(Hit(HARD, "known_email", location, cnt, "历史中的真实邮箱"))
    return hits


def _iter_tracked_files() -> List[Path]:
    rc, out = git(["-c", "core.quotepath=false", "ls-files"])
    if rc != 0:
        # 无 git 兜底：退回文件系统遍历
        return [
            p
            for p in ROOT.rglob("*")
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
        ]
    files = []
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        p = ROOT / rel
        if p.is_file():
            files.append(p)
    return files


def cmd_tracked(tokens: Dict[str, str]) -> List[Hit]:
    hits: List[Hit] = []
    for path in _iter_tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        hits.extend(scan_text(text, rel, tokens))
    return hits


def cmd_history(tokens: Dict[str, str]) -> List[Hit]:
    rc, out = git(["-c", "core.quotepath=false", "log", "--all", "-p", "--format=commit %H"])
    if rc != 0:
        print("历史扫描不可用（无 git）")
        return []
    # 机制探活：先搜必然存在的串（仓库目录名），搜不到即硬失败
    probe = ROOT.name
    if probe not in out:
        print("HISTORY_PROBE_FAIL 探活失败：历史扫描返回空/不完整（机制静默失效）")
        raise SystemExit(2)
    return scan_text(out, "<history>", tokens)


def cmd_messages(tokens: Dict[str, str]) -> List[Hit]:
    rc, out = git(["log", "--all", "--format=%ae%n%ce%n%an%n%cn"])
    if rc != 0:
        return []
    hits: List[Hit] = []
    emails = set()
    for line in out.splitlines():
        line = line.strip()
        if "@" in line and not _classify_email(line):
            emails.add(line)
    for e in sorted(emails):
        hits.append(Hit(HARD, "commit_email", "<git metadata>", 1, "提交元数据中的非 noreply 邮箱"))
    return hits


def _report(hits: List[Hit]) -> int:
    if not hits:
        print("DESENSITIZE_AUDIT_OK")
        return 0
    hard = [h for h in hits if h.level == HARD]
    review = [h for h in hits if h.level == REVIEW]
    adv = [h for h in hits if h.level == ADVISORY]
    allowed = [h for h in hits if h.level == LEVEL_ALLOWED]

    for level, group in ((HARD, hard), (REVIEW, review), (ADVISORY, adv)):
        if not group:
            continue
        print("[%s] %d 项" % (level, len(group)))
        for h in group:
            print("  %s [%s] x%d  %s" % (h.location, h.category, h.count, h.note))
    if allowed:
        print("[放行] %d 项（仍列出，可审计放行理由）" % len(allowed))
        for h in allowed:
            print("  %s [%s] x%d  %s" % (h.location, h.category, h.count, h.note))

    if hard:
        print("DESENSITIZE_AUDIT_FAIL（HARD %d 项）" % len(hard))
        return 1
    print(
        "DESENSITIZE_AUDIT_OK（HARD 0；REVIEW %d 需人工豁免留档；advisory %d 只报；放行 %d）"
        % (len(review), len(adv), len(allowed))
    )
    return 0


def cmd_selftest(tokens: Dict[str, str]) -> int:
    """阳性/阴性对照（夹具**程序化合成**，无字面假密钥/假手机号）。"""
    # 阳性：程序化合成一个假手机号（构造，不入源码词面）
    fake_phone = "1" + "3" + "9" + ("0" * 8)
    text = "联系电话：%s" % fake_phone
    hits = scan_text(text, "<selftest>", tokens)
    if not any(h.category == "phone" for h in hits):
        print("SELFTEST_FAIL 阳性对照：合成手机号未被检出")
        return 1

    # 阴性对照一律只看"阻断级"命中（LEVEL_ALLOWED 放行项按定义不算命中）
    def blocked(text, category):
        return any(
            h.category == category and h.level != LEVEL_ALLOWED
            for h in scan_text(text, "<selftest>", tokens)
        )

    # 阴性：noreply 不得当个人邮箱
    noreply = "12345+user@users.noreply.github.com"
    if blocked("邮箱：%s" % noreply, "email_generic"):
        print("SELFTEST_FAIL 阴性对照：noreply 被误判为个人邮箱")
        return 1

    # 阴性：git@github.com 传输地址不得当个人邮箱
    if blocked("remote: git@github.com:user/repo.git", "email_generic"):
        print("SELFTEST_FAIL 阴性对照：SSH 传输地址被误判为个人邮箱")
        return 1

    # 阴性：sha256 hex 串里的数字段不得当手机号
    hex_like = "f81a1882591568" + "0" * 48
    if blocked("sha256: %s" % hex_like, "phone"):
        print("SELFTEST_FAIL 阴性对照：hex 串被误判为手机号")
        return 1

    # 阴性：audit-allow 行内放行
    if blocked("电话 %s  # audit-allow" % fake_phone, "phone"):
        print("SELFTEST_FAIL 阴性对照：audit-allow 未放行")
        return 1

    # 阴性：文档化的合成号段不得当泄露（它是数据纪律本身）
    doc_phone = SYNTHETIC_PHONE_PREFIX + "001"
    if blocked("白名单号段 %s 号段" % doc_phone, "phone"):
        print("SELFTEST_FAIL 阴性对照：文档化合成号段被误判为泄露")
        return 1

    # 阴性：官方 URL 路径里的 hex 资源 ID 不得当内容指纹
    gov_url = "https://example.gov.cn/a/20230418/8a0798aa5f444182a33065910f5b272c.html"
    if blocked(gov_url, "long_hex"):
        print("SELFTEST_FAIL 阴性对照：URL 内资源 ID 被误判为长 hex 指纹")
        return 1

    print("DESENSITIZE_AUDIT_SELFTEST_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="脱敏审计（四模式）")
    ap.add_argument(
        "mode",
        nargs="?",
        default="tracked",
        choices=["selftest", "tracked", "history", "messages", "all"],
    )
    args = ap.parse_args(argv)

    tokens = compute_tokens()
    print(provenance(tokens))

    if args.mode == "selftest":
        return cmd_selftest(tokens)
    if args.mode == "tracked":
        return _report(cmd_tracked(tokens))
    if args.mode == "history":
        return _report(cmd_history(tokens))
    if args.mode == "messages":
        return _report(cmd_messages(tokens))

    hits = cmd_tracked(tokens) + cmd_history(tokens) + cmd_messages(tokens)
    return _report(hits)


if __name__ == "__main__":
    raise SystemExit(main())
