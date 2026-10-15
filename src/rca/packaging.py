"""打包白名单（单一事实源）。

纪律（plan/05 §6）：spec 的 datas 只准由本函数产生；白名单外的数据目录
一律视为"新数据目录悄悄没进包"，构建期即报错。

**注意本模块放在包内（`rca/packaging.py`）而不是仓库顶层**——顶层
`packaging.py` 会遮蔽 PyPI 的 `packaging` 包，而 PyInstaller 自身依赖它
做版本判断，构建会崩且报错指向莫名其妙处。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

__all__ = ["build_datas", "WHITELIST", "FORBIDDEN_TOP_LEVEL"]

# 白名单：只收运行必需的数据（版权红线数据不入包）
WHITELIST = (
    "data/rules/ruleset-bj.json",
    "data/rules/ruleset-sh.json",
    "data/rules/ruleset-cn.json",
    "data/samples/samples.json",
    "data/knowledge/MANIFEST.json",
)

# 禁区：官方全文快照体积大且非运行必需（判定只需 quote 字段，已内嵌规则包）；
# 若未来要把 raw/ 打进包，须在此显式登记并同步版权说明。
FORBIDDEN_TOP_LEVEL = ("_private", ".git", "plan", "tests", "_scratch", "_backups")


def build_datas(root: Path) -> List[Tuple[str, str]]:
    """返回 PyInstaller `datas` 列表 [(源相对路径, 目标目录)]。

    任一白名单项缺失即抛错——"照文档走"必然拿到可用构建环境。
    """
    root = Path(root)
    datas: List[Tuple[str, str]] = []
    for rel in WHITELIST:
        p = root / rel
        if not p.is_file():
            raise FileNotFoundError("打包白名单引用了不存在的文件: %s" % rel)
        datas.append((rel, str(Path(rel).parent.as_posix())))

    # 未登记的数据目录检测（防"新数据目录悄悄没进包"）
    data_root = root / "data"
    if data_root.is_dir():
        registered_dirs = {Path(rel).parent.as_posix() for rel in WHITELIST}
        for child in sorted(data_root.iterdir()):
            if child.is_dir():
                rel = child.relative_to(root).as_posix()
                if rel not in registered_dirs:
                    raise ValueError(
                        "data/ 下出现未登记目录: %s（白名单与排除项互相矛盾，"
                        "请同步 rca/packaging.py 的 WHITELIST）" % rel
                    )
    return datas
