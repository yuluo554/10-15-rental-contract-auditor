"""桌面界面（PySide6）——只消费引擎 API，零判定逻辑。

分层纪律（plan/05 §7）：
- 本包**不得** import engine 内部模块（checker/ruleset/benchmark），
  唯一入口是 `rca.engine.pipeline` 的公开函数组。
- 界面层**不得**做算术运算、不得内联政策数值（AST 静态门禁三条齐上）。
- PySide6 只在**函数体内** import（模块顶层不 import 重件），
  故 `rca gui` 的惰性导入 try 必须包住"从 import 到调用完成"的整段。

首期骨架：装配窗口 + 页签，判定经 pipeline 取数。
"""

__all__ = ["main_window", "app"]
