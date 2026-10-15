# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：双 exe（GUI console=False + CLI console=True）。

纪律（plan/05 §6）：
- datas **只由** `rca.packaging.build_datas()` 产生（白名单单一事实源），
  本文件不得手写任何数据路径——由 `tests/test_repo_guardrails.py` 守门断言。
- 路径解析到 SPECPATH，不解析到 CWD（spec 内相对路径不解析 CWD）。
- PyInstaller 5.x/6.x 的 PYZ 签名差异用 getattr 兜底，同一份 spec 两版都能跑。

构建（发布构建固定用装了 PyInstaller ≥6 的 3.12 通道）：
    py -3.12 -m PyInstaller --noconfirm --clean tools/rca.spec
"""

import os
import sys

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(SPEC_DIR)
SRC = os.path.join(ROOT, "src")

sys.path.insert(0, SRC)
from rca.packaging import build_datas  # noqa: E402

datas = build_datas(ROOT)  # 唯一事实源：禁止在此手写数据路径
hiddenimports = ["rca.gui.app"]

COMMON = dict(
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 纯可选、非承诺功能的重件可排除；被 README 文档化的功能依赖一律保留
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PyQt5", "PyQt6"],
    noarchive=False,
)


def _pyz(analysis):
    """PYZ 构造（5.x/6.x 签名差异兜底）。"""
    zipped = getattr(analysis, "zipped_data", None)
    if zipped is not None:
        return PYZ(analysis.pure, zipped)
    return PYZ(analysis.pure)


def _build(script, name, console):
    analysis = Analysis([script], **COMMON)
    exe = EXE(
        _pyz(analysis),
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
    )
    return COLLECT(
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name=name,
    )


cli_dist = _build(os.path.join(SRC, "rca", "cli.py"), "rca-cli", True)
gui_dist = _build(os.path.join(SRC, "rca", "gui", "app.py"), "rca-gui", False)
