"""按路径加载 tools/ 下的脚本为模块（供测试导入）。

tools/ 不是包（没有 __init__.py），但脚本本身是可导入的模块；
用 importlib 按文件路径加载即可。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def load_tool(name: str) -> ModuleType:
    path = TOOLS / ("%s.py" % name)
    if not path.is_file():
        raise FileNotFoundError("工具脚本不存在: %s" % path)
    mod_name = "tool_%s" % name
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("无法加载工具脚本: %s" % path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod
