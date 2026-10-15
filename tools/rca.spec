# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：双 exe（GUI console=False + CLI console=True）。

纪律（plan/05 §6）：
- datas **只由** `rca.packaging.build_datas()` 产生（白名单单一事实源），
  本文件不得手写任何数据路径——由 `tests/test_repo_guardrails.py` 守门断言。
- 入口脚本用**绝对导入的冻结入口模块**（`rca.cli_entry` / `rca.gui_entry`）：
  PyInstaller 把它当顶层 `__main__` 执行，脚本内相对导入会直接
  `ImportError: attempted relative import with no known parent package`
  （M5 首次实构建实测：exe 一启动就崩）。
- PyInstaller 5.x/6.x 的 PYZ 签名差异用 getattr 兜底，同一份 spec 两版都能跑。
- **依赖按目标分档**：PySide6 只进 GUI 目标。CLI 目标若跟着带 Qt，
  会白背 87MB（`_internal/PySide6`）——发行包体积翻七倍。
- **CLI 目标排除出网栈**（`ssl`/`_ssl`/`_socket`/`_hashlib`）：CLI 判定通路
  零网络需求（`src/rca` 无任何出网调用，由守门测试断言）。排除后 CLI 产物
  **不含 TLS 运行库**，"纯本地零上传"就不再只是一句代码声明，
  而是**产物级可核验**（发行包里没有能发起 TLS 的东西）。
  与规划一致：此四项**只从 CLI 目标排除**，GUI 目标保留（Qt 自带依赖面更宽）。

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

# 纯可选、非承诺功能的重件可排除；被 README 文档化的功能依赖一律保留。
BASE_EXCLUDES = ["tkinter", "matplotlib", "numpy", "pandas", "PyQt5", "PyQt6"]

# 出网栈：只从 CLI 目标排除（CLI 判定通路零网络需求 → 产物里没有发起 TLS 的能力）
NETWORK_EXCLUDES = ["ssl", "_ssl", "_socket", "_hashlib"]


def _pyz(analysis):
    """PYZ 构造（5.x/6.x 签名差异兜底）。"""
    zipped = getattr(analysis, "zipped_data", None)
    if zipped is not None:
        return PYZ(analysis.pure, zipped)
    return PYZ(analysis.pure)


def _build(script, name, console, hiddenimports, excludes):
    """构建单个 onedir 目标。

    `hiddenimports` / `excludes` 按目标传入——**不共用一份**：
    共用会把 GUI 重件（PySide6）灌进 CLI 产物（M5 首次实构建实测）。
    """
    analysis = Analysis(
        [script],
        pathex=[SRC],
        binaries=[],
        datas=datas,
        hiddenimports=list(hiddenimports),
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=list(excludes),
        noarchive=False,
    )
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


cli_dist = _build(
    os.path.join(SRC, "rca", "cli_entry.py"),
    "rca-cli",
    True,
    hiddenimports=[],
    excludes=BASE_EXCLUDES + ["PySide6", "shiboken6"] + NETWORK_EXCLUDES,
)

gui_dist = _build(
    os.path.join(SRC, "rca", "gui_entry.py"),
    "rca-gui",
    False,
    hiddenimports=["rca.gui.app"],
    excludes=BASE_EXCLUDES,
)
