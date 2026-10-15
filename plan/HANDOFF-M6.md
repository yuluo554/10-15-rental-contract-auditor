# HANDOFF-M6 — 发布（里程碑交接快照）

> 上一棒：M5 交付（2026-10-15 完成）
> 下一棒目标：**M6 发布**——建仓 + CI 首跑 + tag/Release + 发布留档三件套（plan/05 §9/§10）
> 本文件用法（新对话启动）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务`

---

## 0. 本棒最重要的三句话

1. **M0–M5 全项目一次 CI 都没跑过**（无远端）。M6 首推 = **首次 CI**，
   必须预算"多轮诊断"——首跑红不等于方法论失败。
2. **发布前有一件不可逆的事必须先做完**：本机 git 全局 `user.email` 是真实
   邮箱，历史 11 个提交全部中招；**必须在"还没人看见"时**用
   `git filter-repo --email-callback` 改写（窗口期 = 首推前）。
3. **M5 已经真构建 + 真验收过产物**（这是 M0–M4 从未做过的）。产物侧的
   `PACKAGE_VERIFY_OK` 是本项目第一次拿到；M6 发布物须**再验一遍下载件**。

---

## 1. 当前进度（M5 已完成，证据位置）

| 项 | 状态 | 证据 |
|---|---|---|
| 北京规则包 10 条（数值 7） | ✅ | `data/rules/ruleset-bj.json` |
| 上海规则包 7 条（数值 6） | ✅ | `data/rules/ruleset-sh.json` |
| 全国层 4 条 | ✅ | `data/rules/ruleset-cn.json` |
| 合成样例 12 份 | ✅ | `data/samples/samples.json` + `demo-contract-bj.txt` |
| **M5 主体：打包与双入口离线可用逐条证成** | ✅ | `tests/test_m5_packaging.py` + `tests/test_m5_dual_entry.py`（详见 §2） |
| 双 exe **实构建** | ✅ | `py -3.12 -m PyInstaller --noconfirm --clean tools/rca.spec` → `dist/rca-cli`（12MB）、`dist/rca-gui`（112MB） |
| **产物级验收** | ✅ | `verify_package.py --dist ...` 两个 exe 均 `PACKAGE_VERIFY_OK`（**本项目首次**） |
| 冻结态判定与源码一致 | ✅ | 冻结 exe `check` 结论与退出码 == 源码运行（`check_frozen_check_matches_source`） |
| 冻结态报告无外链 + 逐字节可复现 | ✅ | 冻结 exe 导出的 md sha256 `65b90120b4852a7e…`（与 M4 记录的源码侧值**同值**）；md 无 `](http`、xlsx 无 External 关系 |
| 测试全绿 | ✅ | **283 项**（M4 为 239，M5 净增 44），双解释器（3.8.8 / 3.12.10） |
| 生成器冻结 | ✅ | `fetch_sources.py` / `gen_rulesets.py` / `gen_samples.py` 三者 `--check` 均 exit 0 |
| 守门 | ✅ | `check_literals.py`（+`--selftest`）/ `audit_desensitize.py selftest\|tracked` 均 exit 0（HARD 0） |
| 基准三套件 | ✅ | `BENCH_OK`（B1 F1=1.0000 90/90、B2 150/150 误报 0、B3 14/14） |
| 变异验证 | ✅ | `ALL_GUARDS_EFFECTIVE`（**17 项变异全部转红**，详见 §3） |
| 发布 zip 确定性 | ✅ | `RELEASE_ZIP_DETERMINISTIC_OK`（`_scratch/rel2`，11928127 bytes / sha256 `d858c904…`；**_scratch 不入仓**） |
| CI workflow | ✅ 已写 | `.github/workflows/ci.yml`（**新增 `package` job**：真构建 + 产物验收 + zip 确定性；**仍待首推验证**） |

### M5 本地等价校验记录（未接远端，CI 待首推验证）

| 通路 | 命令 | 结果 |
|---|---|---|
| 全量测试 ×2 解释器 | `py -3.12 -X utf8 -m pytest -q` / `py -3.8 …` | **283 项全绿**，exit 0 |
| 快照/规则包/样例冻结 | 三个 `--check` | `SOURCES_FROZEN_OK` / `RULESETS_FROZEN_OK` / `SAMPLES_FROZEN_OK` |
| 零字面量门禁 + 自检 | `tools/check_literals.py` / `--selftest` | exit 0 / `LITERAL_GATE_SELFTEST_OK`（token 9 个） |
| 脱敏审计自检 + 已跟踪 | `audit_desensitize.py selftest` / `tracked` | exit 0（HARD 0；advisory 5 只报；放行 26） |
| 基准三套件 | `rca bench` | `BENCH_OK`（耗时 0.024s） |
| **实构建** | `py -3.12 -m PyInstaller --noconfirm --clean tools/rca.spec` | exit 0，双 exe 产出 |
| **产物验收 CLI** | `tools/verify_package.py --dist dist/rca-cli` | `PACKAGE_VERIFY_OK` |
| **产物验收 GUI** | `tools/verify_package.py --dist dist/rca-gui --gui-selftest` | `PACKAGE_VERIFY_OK` |
| 发布 zip 确定性 | `build_release.py --check` | `RELEASE_ZIP_DETERMINISTIC_OK` |
| 变异验证 | `_scratch/m5_mutation.py`（不入仓） | `ALL_GUARDS_EFFECTIVE`（17/17 转红） |

**不可本机实跑的通路（显式标注"待首推验证"）**：CI 矩阵的环境差异
（cp1252 编码、ubuntu 缺 Qt 系统库、`package` job 在 runner 上的构建时长与
PyInstaller 行为、actions/checkout 行为）。**M5 未改变该状态。**

---

## 2. M5 修掉的真缺口（均加回归 + 变异验证）

题面模块④⑥要求：PySide6 桌面 exe 打包 + CLI 双入口；纯本地零上传验证通过。
plan/05 把口径定死为"依赖分层、CI 矩阵、打包白名单单一事实源、脱敏审计、发布流程与留档"。

M0–M4 把 GUI 骨架、spec、白名单、`build_release.py`、`verify_package.py`、
发布检查单都建好了，**但一次都没构建过**（R5）。**M5 的实质是"第一次真构建，
把产物级缺口逐个挖出来修掉"**——实测出**六处真缺口**：

### 2.1 spec 的 `datas` 源路径写相对 → 构建直接失败

```
实测（M5 前）：datas = [(rel, ...)] 其中 rel = "data/rules/ruleset-bj.json"
              → ERROR: Unable to find '<repo>\tools\data\rules\ruleset-bj.json'
```
PyInstaller 把 datas 的相对源路径解析到 **SPECPATH**（`tools/`），不是 CWD。
**修复**：`build_datas()` 返回**绝对的源路径**（`p.resolve()`）+ 相对的目标目录。
回归：`test_datas_sources_are_absolute_paths`；变异 M1。

### 2.2 冻结入口用包内模块 → exe "构建成功但一启动就崩"

```
实测（M5 前）：Analysis([os.path.join(SRC, "rca", "cli.py")])
              → exe 运行：ImportError: attempted relative import with no known parent package
                [PYI-…:ERROR] Failed to execute script 'cli'
```
PyInstaller 把入口脚本当**顶层 `__main__`** 执行，`cli.py` 里的
`from . import __version__` 必然 ImportError。**这类缺陷最阴**：构建 exit 0、
产物存在，只有真跑才暴露。
**修复**：新增**绝对导入的薄入口** `rca/cli_entry.py` / `rca/gui_entry.py`
（只做 argv 转发，判定逻辑仍在 `rca.cli`，不复制）。
回归：`test_spec_uses_absolute_frozen_entry_modules` /
`test_frozen_entry_has_no_relative_import_at_module_or_function_level`（AST 静态抓）；
变异 M2/M3。

### 2.3 GUI exe 指向没有 `__main__` 的模块 → 无入口、`--selftest` 无人接

```
实测（M5 前）：spec 的 GUI 入口 = src/rca/gui/app.py
              该文件**没有 `__main__` 块**（只有 build_app / run_gui 两个函数）
              → 打成 exe 后无入口；且 plan/05 §6 认定的脚本化验收通路
                `--selftest <文件>` 完全不存在
```
窗口版 stdout 不接终端，**`--selftest` 是验收窗口 exe 的唯一通路**——
这个通路不存在 = 窗口 exe 无法脚本化验收。
**修复**：`rca/gui_entry.py` 提供 `__main__`，并把 `--selftest` **路由到 CLI 的同一份
`selftest` 实现**（双入口结论同源，而非各写一份）。
回归：`test_spec_uses_absolute_frozen_entry_modules` / `test_gui_entry_has_main_guard` /
`test_gui_selftest_routes_to_cli_single_source`；变异 M4。

### 2.4 `--selftest <文件>` 通路未接（CLI 侧）

```
实测（M5 中）：修好入口后 exe 能跑了，但 `rca-cli.exe --selftest out.json` 报
              argparse: invalid choice: '…\out.json'（把文件当成子命令名）
```
plan/05 §6 与 `tools/verify_package.py` 都把 `--selftest <文件>` 当验收通路，
但 CLI 只接受 `selftest --out <文件>` 子命令形态——**文档与实现不同形**。
**修复**：`rca.cli.normalize_argv()` 做一次规范化（`--selftest <文件>` →
`selftest --out <文件>`），`main()` 入口调用；GUI 侧复用同一个函数。
回归：`test_cli_normalizes_selftest_flag` / `test_cli_selftest_flag_runs_end_to_end`
（断言**结论文件真被写出**，不只断言函数返回值）；变异 M5。

### 2.5 CLI 产物白背 87MB PySide6 + 出网栈

```
实测（M5 前）：hiddenimports=["rca.gui.app"] 被**两个目标共用**
              → dist/rca-cli/_internal/PySide6 = 87MB，CLI 发行包 112MB
              → 且带 libcrypto/_ssl/_socket，发行包里躺着 TLS 运行库
```
**修复**：spec 的 `hiddenimports`/`excludes` **按目标分档**：
- PySide6 只进 GUI 目标；
- CLI 目标再排除 `NETWORK_EXCLUDES = ["ssl","_ssl","_socket","_hashlib"]`
  （CLI 判定通路零网络需求，`src/rca` 无出网调用）。
**结果**：CLI 发行包 **112MB → 12MB**，且**不含能发起 TLS 的组件**——
"纯本地零上传"因此不再只是代码声明，而是**产物级可核验**。
回归：`test_spec_does_not_share_hiddenimports_across_targets` /
`test_spec_excludes_network_stack_from_cli_target` /
`test_runtime_package_has_no_network_imports`；变异 M7/M8/M15。

### 2.6 GUI exe 对未知参数**静默挂死**（验收器超时）

```
实测（M5 中）：`rca-gui.exe check --input x.txt --city 北京`
              → 不认识这些参数却照常起窗口，挂进 Qt 事件循环 **永不返回**
              → verify_package 超时 180s（症状从"失败"退化成"卡住"）
```
窗口版没有终端，静默忽略参数是最坏形态。
**修复**：`gui_entry.unknown_args()` 挑出无法识别的参数 → 打印用法 + **exit 2**。
回归：`test_gui_rejects_unknown_args_with_exit_2`（打桩 `run_gui` 为"被调用即失败"
——**不能用真 `app.exec()`**，否则变异验证时脚本再次卡死）；变异 M6。

### 2.7 产物级验收的广度缺口（plan/05 §6 的"构建后三断言"只落了三分之一）

```
实测（M5 前）：verify_package.py 只有三项断言（顶层禁区 / frozen / 规则数）
              —— **没有**内嵌数据 sha256 对账、"入包集合 == 白名单"、
                 冻结态判定与源码对账、冻结报告无外链、出网组件扫描
```
**修复**：`verify_package.py` 扩到七类断言（见 §1 表与文件 docstring）。
**注意**：`check_embedded_data_sha256` 同时核"**入包集合 == 白名单**"
（防多余东西悄悄进包，而不只是防漏拷）。
回归：`test_verify_end_to_end_*` 四条**真跑 `verify()`** 的端到端断言
（+ `_fake_dist` 正/负对照）；变异 M9/M10/M11/M16/M17。

### 2.8 GUI 降级提示未按 `is_frozen()` 分流

```
实测（M5 前）：提示固定写"源码态安装：pip install -e .[gui]"
              —— 冻结态读者拿不到 pip，这条指引无效
              （且 CLI 发行包**不含 PySide6**，"本包可能未内嵌"的含糊措辞也不对）
```
**修复**：`cmd_gui` 按 `is_frozen()` 分流——冻结态如实说"本发行包未内嵌桌面界面，
请改用 GUI 发行包"；源码态才给 pip 命令。
回归：`test_gui_degradation_message_branches_on_frozen` +
`test_gui_degradation_message_source_branch_keeps_pip`（两头都断言，防只改一边）；变异 M13。

### 2.9 双入口结论同源缺"行为等价"断言

```
实测（M5 前）：无任何断言把 GUI 显示的判定与 CLI `check` 的结论对起来
```
plan/05 §7 要求测试断言**行为等价**（三方对账），而非"都调了同一个函数"
（弱断言：接线断了照样绿）。
**修复**：`tests/test_m5_dual_entry.py` 驱动**真实 Qt 控件**（填文本 → 选城市 →
点按钮 → 读只读输出框），三方对账：GUI 显示 == pipeline 直调 == CLI stdout；
并断言逐条判定明细也一致。
**关键设计**：`test_gui_uses_same_data_dir_as_cli` 用**改过的规则包副本**
（哨兵标题）才可证伪——直接传仓库 data_dir 测不出问题（丢参数会回落到同一份）。
变异 M14。

---

## 3. M5 变异验证结论（`ALL_GUARDS_EFFECTIVE`，17/17）

脚本在 `_scratch/m5_mutation.py`（**不入仓**）。照 §4 的教训：
**守门测试走它真正要保护的产物通路**、**变异打在唯一证据通路上**、
**断言绑实际取值**、**改源码后清 `__pycache__`**。

| # | 注入的缺陷 | 结果 |
|---|---|---|
| M1 | datas 源路径退回相对路径 | 转红 ✅ |
| M2 | CLI 入口退回包内模块（相对导入） | 转红 ✅ |
| M3 | 冻结入口引入相对导入（函数体内也算） | 转红 ✅ |
| M4 | GUI 入口退回无 `__main__` 的 `app.py` | 转红 ✅ |
| M5 | `--selftest` 规范化被拆掉 | 转红 ✅ |
| M6 | GUI 不再拒绝未知参数 | 转红 ✅（**须打桩 `run_gui`**，见下） |
| M7 | `hiddenimports` 两目标共用 | 转红 ✅ |
| M8 | CLI 不再排除出网栈 | 转红 ✅ |
| M9 | 内嵌数据 sha256 校验被摘掉 | 转红 ✅ |
| M10 | 内嵌数据校验脱钩白名单（只查第一份） | 转红 ✅ |
| M11 | 冻结态判定对账被摘掉 | 转红 ✅ |
| M12 | 判定提取放宽成贪婪捕获 | 转红 ✅ |
| M13 | GUI 降级提示不再按 `is_frozen` 分流 | 转红 ✅ |
| M14 | GUI 少传 `data_dir` | 转红 ✅ |
| M15 | 运行期包植入出网 import | 转红 ✅ |
| M16 | 冻结态报告外链检查被摘掉 | 转红 ✅ |
| M17 | 白名单外数据文件不再被检出 | 转红 ✅ |

**首轮一条"卡死"的教训（M6 可直接复用）**：
- **变异后的守门测试可能"挂住"而不是"失败"**。首轮 M6（摘掉 GUI 参数检查）
  让测试真的跑进了 Qt 事件循环，整个变异脚本永久卡死（外部 kill 才停，
  且**留下了未回滚的源码改动**——`finally` 没执行到）。
  两处修复：①守门测试打桩 `run_gui`，让缺陷表现为断言失败而非事件循环；
  ②变异脚本的 `_run_tests` 加 **300s 超时**，超时按"转红"处理并明说
  "变异后的守门测试挂住（未拦住缺陷）"。
  **教训**：变异验证脚本必须假设"缺陷可能让测试挂住"，
  且**暴力 kill 会留脏源码**——恢复后必须自己 grep 核对关键锚点。

---

## 4. 既定口径清单（K 清单——动了会打挂基准/验收，改前先对照）

> M1–M4 的 K1–K32 原样保留（见 `plan/HANDOFF-M5.md` §5），以下只列 **M5 新增**的 K33–K37。

| # | 口径 | 位置 | 动了的连锁 |
|---|---|---|---|
| **K33** | **spec 的 datas 源路径必须绝对**（目标目录保持包内相对） | `rca/packaging.py` `build_datas()` | 退回相对路径 → PyInstaller 解析到 SPECPATH（`tools/`）→ 构建直接失败 |
| **K34** | **冻结入口是绝对导入的薄模块**（`rca.cli_entry` / `rca.gui_entry`），入口及其调用链**不得有相对导入** | `tools/rca.spec` + 两个 `*_entry.py` | 退回包内模块 → exe 构建成功但一启动 `ImportError`（顶层 `__main__` 无父包） |
| **K35** | **`hiddenimports`/`excludes` 按目标分档**：PySide6 只进 GUI；CLI 额外排除 `ssl`/`_ssl`/`_socket`/`_hashlib` | `tools/rca.spec` | 共用一份 → CLI 白背 87MB Qt + 产物里躺着 TLS 库（"零上传"无法在产物级自证） |
| **K36** | **`--selftest <文件>` 与 `selftest --out <文件>` 同义**，规范化只有一处实现（`rca.cli.normalize_argv`），GUI 侧复用 | `src/rca/cli.py` + `src/rca/gui_entry.py` | 拆成两处解析 → 双入口验收结论可能不是同一份实现产的；不通则验收器直接 exit 2 |
| **K37** | **冻结态降级提示按 `is_frozen()` 分流**：冻结态说"本发行包未内嵌"，源码态才给 pip | `src/rca/cli.py` `cmd_gui` | 不分支 → 冻结态读者拿到无效的 pip 指引（且"可能未内嵌"的含糊措辞掩盖了 CLI 包本就不含 GUI 这个事实） |

**M5 补充的产物验收口径**（不在 K 表内但同等刚性）：
`verify_package.py` 的**入包集合 == 白名单**（不只要防漏拷，还要防多余东西进包）；
冻结态 `report` 的 md 无 `](http`、xlsx 无 `External` 关系。

---

## 5. 本机环境坑（M5 新增，全部实测过）

> M0–M4 的坑见 `plan/HANDOFF-M5.md` §6（`python` 不在 PATH、`/tmp` 不互通、
> `-X utf8`、`write_text(newline=)` 是 3.10+、`_scratch/` 用法、清 `__pycache__`、
> 生成器类变异先重生成、`rca report` 在演示样例上 exit 1、探针别用裸 `\s`）——全部仍有效。

- **本机 PyInstaller 版本分档**：3.12 通道是 **6.22.3**、3.8 通道是 **5.13.2**。
  打 GUI **必须用 3.12 通道**（5.x 扫 PySide6 字节码确定性崩）。M5 实构建全部走 3.12。
- **PyInstaller 的 `datas` 相对源路径解析到 SPECPATH 而不是 CWD**（实测踩过）。
- **PyInstaller 把 spec 里的脚本当顶层 `__main__`**：该脚本（含函数体）里的相对
  导入必然 ImportError——**构建 exit 0 但产物不可用**，只有真跑才暴露。
- **`--noconfirm --clean` 之外还要换 `--distpath`/`--workpath`**：
  否则 `build/`、`dist/` 与你可能要检查的产物混在一起（`_scratch/` 已 gitignore）。
- **GUI exe 的 `app.exec()` 会挂死一切自动化**：任何"驱动 GUI"的测试都必须
  打桩 `run_gui`，或只用 `build_app()`（不 `exec()`）；`QT_QPA_PLATFORM=offscreen`
  必须在**首次导入 PySide6 前**设好（`test_gui_layering.py` 已有范式）。
- **offscreen 下 `QFontDatabase` 会报 "Cannot find font directory"**：是警告不是失败，
  中文会渲染成方块但**不影响逻辑断言**（M5 的双入口对账只读文本）。
- **变异脚本必须带超时**：缺陷可能让守门测试"挂住"而不是"失败"
  （M5 首轮实测：整个脚本卡死，外部 kill 后**留下脏源码**）。
  强制终止后**必须自己 grep 核对关键锚点**，不要相信 `finally` 跑过了。
- **`Path.relative_to("data")`** 用于把仓库相对路径转成包内相对路径
  （`data/rules/x.json` → `rules/x.json`），写死在 `verify_package.py` 里；改白名单结构时要同步。

---

## 6. DoD（M6 出口判据，逐项勾选）

题面提交材料 5/6/8 与"应用完整性"评分维度。plan/05 §9/§10 把口径定死为
"建仓 → CI 首跑 → CI 对账 → 收尾固化 → 发布物已验 → README 转正"。

**先做完不可逆的那件事**（顺序不能颠倒）：
- [ ] **邮箱改写**：`git filter-repo --email-callback` 把 11 个提交的
      author/committer 邮箱改成 GitHub noreply；改完 `audit_desensitize.py messages`
      **两个字段**（ae 与 ce）都须干净。**必须在建仓/首推前做**
      （窗口期 = 零消费者）
- [ ] **署名留档**：发布到 GitHub **公开**仓库，署名 `yuluo554`

**M5 已完成的产物侧判据（M6 只需复跑 + 留档）**：
- [x] 实构建双 exe（3.12 通道，PyInstaller 6.22.3）
- [x] `verify_package.py` 对两个 exe 均 `PACKAGE_VERIFY_OK`
- [x] 冻结态 `data_dir_in_dist: true` + 冻结态判定与源码一致
- [x] 冻结态报告无外链、逐字节可复现
- [x] CLI 产物无出网组件（12MB，无 TLS）
- [x] 打包白名单与产物一致（入包集合 == 白名单）
- [x] GUI 分层守门不回归（`test_gui_layering.py`）
- [x] 双入口退出码语义一致（GUI 显示 == CLI `check`）
- [x] `py -3.12`/`py -3.8` 双解释器全绿（283 项，计数已同步进 README）
- [x] `rca bench` 三套件达标（exit 0，B2 误报 0）
- [x] 生成器 `--check` 三连 / 字面量门禁 + selftest / 脱敏 selftest + tracked
- [x] 变异验证 17/17 转红
- [x] `plan/00` 里程碑表 M5 状态回写 ✅
- [x] **本对话内写完 `plan/HANDOFF-M6.md`**

**M6 要做的事**：
- [ ] `gh repo create yuluo554/10-15-rental-contract-auditor --public --source . --remote origin`
      （**不带 `--push`**）→ 验 SSH key → `git remote set-url origin git@github.com:...`
      → push
- [ ] **CI 首跑**：预算"诊断 + 修复 + 再推一轮"（首跑 = 全项目首次 CI）
- [ ] **CI 对账**：`gh run list` 与 push 事件逐条配对（**push 事件数 = run 数**，
      不是提交数；amend/force push 后旧 run 的 sha 已不可达要注明）
- [ ] **发布物本体已验**：真下载 release 附件 → 下载件 sha256 与留档一致 →
      解压中立目录跑 `--selftest` 通过
- [ ] `git tag -a v0.1.0` + push tag + `gh release create`（notes 用
      `--notes-file`；附件名**一律 ASCII**）
- [ ] README 状态行转正 + CI 徽章 + topics（`gh repo edit --add-topic`，
      加完 `gh api` 回读确认）
- [ ] **留档三件套**：`plan/RELEASE-M6.md` / `plan/HANDOFF-M7.md`（如有下一棒）/
      `plan/DIST-sha256-M6.txt`（由 `sha256sum`/`hashlib` 输出**直接重定向**生成，
      人只写注释行）

**诚实口径**：M0–M5 未接远端，一切 CI 类判据写"**本地等价校验**（未接远端，CI 待首推验证）"。
**未推送 = 未跑 CI**，M6 首推后据实补记真实 run id。
**确认类条目只能在用户实际确认后打勾，禁止预填"用户已确认"**；
tag/release/topics 需用户在对话中确认一次（多项收拢一次 AskUserQuestion）；
visibility/删仓/历史重写必须用户明确授权。

---

## 7. 关键命令速查

```bash
# 验证（M6 每改一处都跑）
py -3.12 -X utf8 -m pytest -q                         # 283 项（双解释器各跑一遍）
py -3.12 -X utf8 -m rca.cli bench                     # 三套件 → BENCH_OK
py -3.12 -X utf8 tools/check_literals.py --selftest   # 门禁自检
py -3.12 -X utf8 tools/audit_desensitize.py tracked   # 脱敏（HARD 0）

# 打包与产物验收（M5 首次真跑；发布物必须走这条）
py -3.12 -X utf8 -m PyInstaller --noconfirm --clean tools/rca.spec
py -3.12 -X utf8 tools/verify_package.py --dist dist/rca-cli
py -3.12 -X utf8 tools/verify_package.py --dist dist/rca-gui --gui-selftest
py -3.12 -X utf8 tools/build_release.py --dist dist/rca-cli --out _scratch/release --name rca-cli-win64.zip
py -3.12 -X utf8 tools/build_release.py --dist dist/rca-cli --out _scratch/release --name rca-cli-win64.zip --check

# 数据（改 SPECS / 样例后按序执行；规则包须**先于**样例生成，因 coverage 读样例）
py -3.12 -X utf8 tools/gen_samples.py
py -3.12 -X utf8 tools/gen_rulesets.py
py -3.12 -X utf8 tools/gen_rulesets.py --check        # → RULESETS_FROZEN_OK
py -3.12 -X utf8 tools/gen_samples.py --check         # → SAMPLES_FROZEN_OK
py -3.12 -X utf8 tools/fetch_sources.py --check       # 快照冻结校验

# 手工试用（引擎/报告改动后重点看这几条）
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京
py -3.12 -X utf8 -m rca.cli rules --city 上海
py -3.12 -X utf8 -m rca.cli report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep

# 发布（M6，plan/05 §9）
gh repo create yuluo554/10-15-rental-contract-auditor --public --source . --remote origin
git remote set-url origin git@github.com:yuluo554/10-15-rental-contract-auditor.git
gh run list
git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0
gh release create v0.1.0 --notes-file <notes> <ascii-named-assets>
```

**注意生成顺序**：规则包的 `coverage.truth_sampling`（分子）**读样例**，
故改样例后必须重跑 `gen_rulesets.py`，否则 `RULESETS_FROZEN_OK` 会因为
"登记的分子与实算不符"而失败（这正是设计意图——登记的数与真实的数不能是两份）。

**注意 `rca report` 退出码**：演示样例上会检出不符合 → exit 1（既定语义），
用 `&&` 串联命令会在此断链，脚本里请用 `;` 或显式判断。

---

## 8. 下一棒启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务
```

**注意**：入库的 HANDOFF 内一律写**相对路径**（`plan/HANDOFF-M6.md`），
绝对路径只出现在用户侧的 `/goal` 启动命令中（否则发布期脱敏扫描必中）。

---

## 9. 遗留与风险

> M0–M4 的 R1–R19 见 `plan/HANDOFF-M5.md` §10（R1 CI 从未真跑、R2 真实邮箱、
> R3 `_scratch/`、R6–R13 数据/解析类、R14 变异脚本不入仓、R18/R19 假绿教训）——
> **全部仍有效**，其中 R1/R2 **正是 M6 的主线**。以下只列 M5 新增/状态变更的。

| # | 事项 | 处置 |
|---|---|---|
| **R4（已闭环）** | GUI 只做了骨架 | **M5 已闭环**：真构建 + 冻结态验收通过；GUI 仍是两个页签的骨架，但"骨架"不再等于"没验过" |
| **R5（已闭环）** | spec 从未构建过 | **M5 已闭环**：首次实构建暴露 6 处产物级缺口（§2.1–2.6）并全部修掉 + 加回归 + 变异验证 |
| **R20** | **`package` job 从未在 CI 跑过** | `.github/workflows/ci.yml` 新增 `package` job（真构建 + 验收 + zip 确定性），但**只在 windows/3.12 跑一次**。首推后按实况修（构建时长、runner 上的 PyInstaller 行为均未知）。若超时/失败，优先降级为"手动 workflow_dispatch"而非删掉整条 |
| **R21** | **GUI 发行包 112MB**（内含 87MB PySide6） | 属"够用"；若发布体量是问题，可考虑 `--exclude-module` 裁掉 Qt 未用子模块（QtWebEngine 等）。**M5 未做**（未实测哪些子模块真用不到，贸然裁会出运行期缺库） |
| **R22** | **GUI 只有两个页签**（合同体检 / 规则包） | 报告导出、批量扫描在 GUI 侧未提供（CLI 有）。属扩展项，不影响双入口"结论同源"承诺（GUI 的判定通路已与 CLI 对齐并有回归） |
| **R23** | **冻结态 `report` 的 md sha256 与源码侧同值**（`65b90120…`） | 这是"内嵌数据 + 包内渲染器"与源码同源的**正面证据**，但**exe 构建本身不承诺跨机字节一致**（`build_release.py` docstring 已写明）。**可复跑的是"同 dist → 同 zip 字节"这步** |
| **R24** | **变异脚本的"卡死"风险已加固但未根治** | 已加 300s 超时 + GUI 测试打桩。但**暴力 kill 仍会留脏源码**（M5 实测）。M6 若要常态化变异验证（提进 `tools/`），须先解决"进程被杀时如何保证回滚" |
| **R25** | `plan/HANDOFF-M5.md` 的 DoD 表格仍留 ⬜ | 属**历史快照**，按约定不追改（每棒留自己的快照）。M5 的各项判据已在本文件 §1/§6 据实记录 |
