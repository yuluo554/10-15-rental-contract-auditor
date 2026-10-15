"""数据目录定位（含 PyInstaller 冻结态分支）。

优先级：显式参数 > 环境变量 RCA_DATA_DIR > 冻结态内嵌 > 开发树上溯。
冻结分支必须显式处理，否则 exe 会回头读开发机的仓库 data/（"内嵌数据验了个寂寞"）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["is_frozen", "find_data_dir", "exe_dir"]

ENV_VAR = "RCA_DATA_DIR"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 冻结态。"""
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path | None:
    """冻结态的 exe 所在目录；非冻结态返回 None。"""
    if not is_frozen():
        return None
    return Path(sys.executable).resolve().parent


def _candidates() -> list[Path]:
    out: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        # PyInstaller 6：数据在 _MEIPASS/data
        out.append(Path(meipass) / "data")
    ed = exe_dir()
    if ed is not None:
        # PyInstaller 6 onedir：exe目录/_internal/data；5.x 平铺：exe目录/data
        out.append(ed / "_internal" / "data")
        out.append(ed / "data")
    # 开发树：从本文件上溯找含 data/knowledge 的目录
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "data"
        if (cand / "knowledge").is_dir():
            out.append(cand)
            break
    return out


def find_data_dir(explicit: str | os.PathLike | None = None) -> Path:
    """返回 data/ 目录。找不到抛 FileNotFoundError。"""
    if explicit:
        p = Path(explicit)
        if p.is_dir():
            return p
        raise FileNotFoundError("指定的数据目录不存在: %s" % p)

    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env)
        if p.is_dir():
            return p
        raise FileNotFoundError("%s 指向的目录不存在: %s" % (ENV_VAR, p))

    for cand in _candidates():
        if cand.is_dir():
            return cand
    raise FileNotFoundError("未找到 data/ 目录；可用 --data 或 %s 指定" % ENV_VAR)


def data_path_in_dist(data_dir: Path) -> bool | None:
    """冻结态自检：数据目录是否落在 exe 目录之内。

    非冻结态返回 None（不是 FAIL）——不让源码运行被误判。
    """
    ed = exe_dir()
    if ed is None:
        return None
    try:
        return os.path.commonpath([str(ed), str(Path(data_dir).resolve())]) == str(ed)
    except ValueError:
        # 跨盘符
        return False
