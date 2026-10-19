"""打包白名单（单一事实源）。

纪律（plan/05 §6）：spec 的 datas 只准由本函数产生；白名单外的数据目录
一律视为"新数据目录悄悄没进包"，构建期即报错。

**数据放在包内（`src/rca/data/`）而不是仓库根**：只有这样才能随 wheel 分发。
此前数据在仓库根 `data/`（包外），`pip install <wheel>` 后 `rca rules` 直接
exit 2「未找到 data/ 目录」——editable 安装因开发树上溯恰好能跑，故 CI 四个 job
全绿而装态不可用（回归门禁见 `tests/test_install_smoke.py`）。

**注意本模块放在包内（`rca/packaging.py`）而不是仓库顶层**——顶层
`packaging.py` 会遮蔽 PyPI 的 `packaging` 包，而 PyInstaller 自身依赖它
做版本判断，构建会崩且报错指向莫名其妙处。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

__all__ = [
    "build_datas",
    "WHITELIST",
    "WHEEL_EXTRA",
    "FORBIDDEN_TOP_LEVEL",
    "DATA_SUBDIR",
    "BUNDLE_DATA_DIR",
    "package_data_dir",
    "wheel_data_entries",
]

# 包内数据根（随 wheel 分发的那些数据都在这里）
DATA_SUBDIR = "src/rca/data"

# 产物（PyInstaller onedir）内的数据目录名：`_internal/data/`。
# `paths.py` 冻结态分支按这个名字定位，**不要跟着源码布局改**。
BUNDLE_DATA_DIR = "data"

# exe 白名单：**运行必需**的数据（版权红线数据不入包）。
# 路径相对包内数据根（`src/rca/data/`），与产物内布局一致。
# 这是"入包集合 == 白名单"断言的基准——**多一个文件都会被判红**，
# 所以演示样例不在这里（exe 的 `check` 读用户自己的合同，不需要样例）。
WHITELIST = (
    "rules/ruleset-bj.json",
    "rules/ruleset-sh.json",
    "rules/ruleset-cn.json",
    "samples/samples.json",
    "knowledge/MANIFEST.json",
)

# wheel 额外携带的"装完即跑"素材：README 快速开始与验收共用演示合同。
# 只在 wheel 里（`pip install` 后可直接跑 README 命令），exe 不需要——
# 故它不是 WHITELIST 的一部分，但**必须是 WHITELIST 的超集方向**：
# `WHEEL_EXTRA` 合入后不得移除任何 WHITELIST 项（由 `wheel_data_entries()` 保证）。
WHEEL_EXTRA = (
    "samples/demo-contract-bj.txt",
)

# 禁区：官方全文快照体积大且非运行必需（判定只需 quote 字段，已内嵌规则包）；
# 若未来要把 raw/ 打进包，须在此显式登记并同步版权说明。
FORBIDDEN_TOP_LEVEL = ("_private", ".git", "plan", "tests", "_scratch", "_backups")


def package_data_dir(root: Path) -> Path:
    """包内数据根目录（`<repo>/src/rca/data`）。"""
    return Path(root) / DATA_SUBDIR


def wheel_data_entries() -> Tuple[str, ...]:
    """wheel 应携带的数据文件（相对包内数据根）：exe 白名单 + 装态素材。"""
    return tuple(WHITELIST) + tuple(WHEEL_EXTRA)


def build_datas(root: Path) -> List[Tuple[str, str]]:
    """返回 PyInstaller `datas` 列表 [(源**绝对**路径, 目标目录)]。

    源路径必须是绝对的：PyInstaller 把 datas 的相对源路径解析到 **SPECPATH**
    （`tools/`），而不是 CWD——写相对路径会让构建报
    `Unable to find '<repo>/tools/data/rules/...'`（M5 首次实构建踩到）。
    目标目录保持相对（产物内布局，相对 bundle 根）：固定 `data/<子目录>`，
    与 `paths.py` 冻结态分支的约定一致。

    任一白名单项缺失即抛错——"照文档走"必然拿到可用构建环境。
    """
    root = Path(root)
    data_root = package_data_dir(root)
    datas: List[Tuple[str, str]] = []
    for rel in WHITELIST:
        p = data_root / rel
        if not p.is_file():
            raise FileNotFoundError(
                "打包白名单引用了不存在的文件: %s/%s" % (DATA_SUBDIR, rel)
            )
        dest = (Path(BUNDLE_DATA_DIR) / Path(rel).parent).as_posix()
        datas.append((str(p.resolve()), dest))

    # 未登记的数据目录检测（防"新数据目录悄悄没进包"）
    if data_root.is_dir():
        registered_dirs = {Path(rel).parent.as_posix() for rel in WHITELIST}
        for child in sorted(data_root.iterdir()):
            if child.is_dir():
                rel = child.relative_to(data_root).as_posix()
                if rel not in registered_dirs:
                    raise ValueError(
                        "包内数据目录出现未登记项: %s/%s（白名单与排除项互相矛盾，"
                        "请同步 rca/packaging.py 的 WHITELIST）" % (DATA_SUBDIR, rel)
                    )
    return datas
