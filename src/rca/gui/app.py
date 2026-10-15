"""主窗口装配（PySide6 只在函数体内 import）。

编排层零 Qt：本模块只调 `rca.engine.pipeline` 的公开函数，
不复制任何判定逻辑、不做算术运算、不内联政策数值。
"""

from __future__ import annotations

import sys
from typing import List, Optional

__all__ = ["run_gui", "build_app", "DISCLAIMER_TEXT"]

DISCLAIMER_TEXT = "本工具输出为辅助参考的合同体检结果，不构成法律意见。"


def _qt():
    """函数体内取 Qt 符号（分层守门要求重件不进模块顶层）。"""
    from PySide6.QtWidgets import (  # noqa: F401
        QApplication,
        QComboBox,
        QLabel,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    return {
        "QApplication": QApplication,
        "QMainWindow": QMainWindow,
        "QWidget": QWidget,
        "QVBoxLayout": QVBoxLayout,
        "QLabel": QLabel,
        "QPlainTextEdit": QPlainTextEdit,
        "QPushButton": QPushButton,
        "QComboBox": QComboBox,
        "QTabWidget": QTabWidget,
    }


def _load_cjk_font(app) -> None:
    """offscreen 平台不扫描系统字体 → 中文渲染成方块。显式加载候选字体。

    字体路径由环境变量推导，**不写死绝对盘符**（换机失效且脱敏审计会命中）。
    """
    import os
    from pathlib import Path

    from PySide6.QtGui import QFont, QFontDatabase

    candidates: List[Path] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        candidates.append(Path(windir) / "Fonts" / "msyh.ttc")
    for posix in ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                  "/System/Library/Fonts/PingFang.ttc"):
        candidates.append(Path(posix))
    for c in candidates:
        if c.is_file():
            fid = QFontDatabase.addApplicationFont(str(c))
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    app.setFont(QFont(families[0]))
            return


def build_app(data_dir: Optional[str] = None):
    """装配 QApplication + 主窗口。返回 (app, window)。"""
    qt = _qt()
    app = qt["QApplication"].instance() or qt["QApplication"](sys.argv[:1])
    _load_cjk_font(app)
    window = _build_window(qt, data_dir)
    return app, window


def _build_window(qt, data_dir: Optional[str]):
    from ..engine.pipeline import compute_result, ruleset_overview

    window = qt["QMainWindow"]()
    window.setWindowTitle("房屋租赁合同审计器（租客视角）")
    tabs = qt["QTabWidget"]()
    window.setCentralWidget(tabs)

    # 页签一：合同体检
    page = qt["QWidget"]()
    layout = qt["QVBoxLayout"](page)
    layout.addWidget(qt["QLabel"]("城市："))
    city_box = qt["QComboBox"]()
    city_box.addItems(["北京", "上海"])
    layout.addWidget(city_box)
    layout.addWidget(qt["QLabel"]("粘贴合同文本："))
    editor = qt["QPlainTextEdit"]()
    layout.addWidget(editor)
    button = qt["QPushButton"]("开始体检")
    layout.addWidget(button)
    output = qt["QPlainTextEdit"]()
    output.setReadOnly(True)
    layout.addWidget(output)

    def _on_check():
        text = editor.toPlainText()
        if not text.strip():
            output.setPlainText("请输入合同文本。")
            return
        try:
            result = compute_result(text, city_box.currentText(), data_dir=data_dir)
        except Exception as exc:  # noqa: BLE001 - 界面层只转发，不判定
            output.setPlainText("体检失败：%s" % exc)
            return
        lines = ["整体判定：%s" % result.overall_status, ""]
        for f in result.findings:
            lines.append("[%s] %s" % (f.status, f.title))
            lines.append("    %s" % f.reason)
        lines.append("")
        lines.append(DISCLAIMER_TEXT)
        output.setPlainText("\n".join(lines))

    button.clicked.connect(_on_check)
    tabs.addTab(page, "合同体检")

    # 页签二：规则包信息
    info_page = qt["QWidget"]()
    info_layout = qt["QVBoxLayout"](info_page)
    info_label = qt["QLabel"]("")
    info_label.setWordWrap(True)
    info_layout.addWidget(info_label)
    try:
        overview = ruleset_overview("北京", data_dir)
        info_label.setText(
            "规则包：%s（%s）\n条目数：%d\n\n%s"
            % (
                overview["ruleset_id"],
                overview["city"],
                overview["rule_count"],
                DISCLAIMER_TEXT,
            )
        )
    except Exception as exc:  # noqa: BLE001
        info_label.setText("规则包信息不可用：%s" % exc)
    tabs.addTab(info_page, "规则包")

    return window


def run_gui(data_dir: Optional[str] = None) -> int:
    """启动 GUI 事件循环。缺依赖时由调用方（cmd_gui）兜底 exit 3。"""
    app, window = build_app(data_dir)
    window.show()
    return app.exec()
