# HANDOFF-M5 — 交付与发布（里程碑交接快照）

> 上一棒：M4 基准（2026-10-15 完成）
> 下一棒目标：**M5 交付**——PySide6 桌面 exe 打包 + CLI 双入口离线可用（题面模块④⑥）
> 本文件用法（新对话启动）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务`

---

## 1. 当前进度（M4 已完成，证据位置）

| 项 | 状态 | 证据 |
|---|---|---|
| 北京规则包 10 条（数值 7） | ✅ | `data/rules/ruleset-bj.json`（sha256 前 16 位 `2feddd537ee32daa`，**M4 因 coverage 段扩充而变**） |
| 上海规则包 7 条（数值 6） | ✅ | `data/rules/ruleset-sh.json`（`e289ec2f371f56bf`） |
| 全国层 4 条 | ✅ | `data/rules/ruleset-cn.json`（`aa1bcdf25654d0c2`） |
| 合成样例 **12 份**（原 10 份 + 缺要素 + 非合同） | ✅ | `data/samples/samples.json`（`4033fcbc1d35b56c`）+ `demo-contract-bj.txt` |
| **M4 主体：模块⑤评测口径逐条证成** | ✅ | `tests/test_m4_benchmark.py`（**24 个测试函数 / 32 个参数化用例**，详见 §2） |
| 覆盖登记三件套 | ✅ | `src/rca/benchmark/coverage.py`（单一实现源）+ 三规则包 `coverage.truth_sampling` |
| 测试全绿 | ✅ | **239 项**（M3 为 207，M4 净增 32），双解释器（3.8.8 / 3.12.10） |
| 生成器冻结 | ✅ | `gen_rulesets.py --check` / `gen_samples.py --check` / `fetch_sources.py --check` 三者均 exit 0 |
| 守门 | ✅ | `check_literals.py`（+`--selftest`）/ `audit_desensitize.py selftest\|tracked` 均 exit 0（HARD 0） |
| 基准三套件 | ✅ | `BENCH_OK`（B1 F1=1.0000 90/90、B2 150/150 误报 0、B3 14/14） |
| 变异验证 | ✅ | `ALL_GUARDS_EFFECTIVE`（**12 项变异全部转红**，详见 §3） |
| CI workflow | ✅ 已写 | `.github/workflows/ci.yml`（**仍未接远端，CI 待首推验证**） |

### M4 本地等价校验记录（未接远端，CI 待首推验证）

| 通路 | 命令 | 结果 |
|---|---|---|
| 全量测试 ×2 解释器 | `py -3.12 -X utf8 -m pytest -q` / `py -3.8 -X utf8 -m pytest -q` | **239 项全绿**，exit 0 |
| 快照冻结 | `tools/fetch_sources.py --check` | `SOURCES_FROZEN_OK` |
| 规则包冻结 | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK`（coverage 段扩充后位级一致） |
| 样例冻结 | `tools/gen_samples.py --check` | `SAMPLES_FROZEN_OK` |
| 零字面量门禁 + 自检 | `tools/check_literals.py` / `--selftest` | exit 0 / `LITERAL_GATE_SELFTEST_OK`（token 9 个） |
| 脱敏审计自检 + 已跟踪 | `audit_desensitize.py selftest` / `tracked` | exit 0（HARD 0；advisory 5 只报；放行 26） |
| 基准三套件 | `rca bench` | `BENCH_OK`（耗时 0.018s） |
| 报告双轨导出 | `rca report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep1` | Markdown + XLSX 均生成；**两次导出逐字节一致**（md `65b90120b4852a7e` / xlsx `b3eec790ae5e61b9`）；新增「基准覆盖登记」章节进两格式 |
| CLI 覆盖登记 | `rca rules --city 北京/上海/全国` | 分母 + 分子 + 采样清单三件套齐；`check --json` 顶层新增 `coverage` 键 |
| 变异验证 | `_scratch/m4_mutation.py`（不入仓） | `ALL_GUARDS_EFFECTIVE`（12/12 转红） |

**不可本机实跑的通路（显式标注"待首推验证"）**：CI 矩阵的环境差异
（cp1252 编码、ubuntu 缺 Qt 系统库、actions/checkout 行为）。**M4 未改变该状态。**

---

## 2. M4 修掉的真缺口（均加回归 + 变异验证）

题面模块⑤要求：合成合同样例与植入真值、三层基准。plan/04 把口径定死为
"样本驱动 + 规则驱动两层，每套件配可证伪探活，空分母不冒充通过"。

M0 已建基准骨架（三套件、门槛随规则包下发、探活、空分母分支），M1/M2 把样例扩到 10 份。
**M4 的实质是"把模块⑤的评测口径逐条证成并补覆盖缺口"**——复核中实测出**六处产物层面的缺口**：

### 2.1 真值库采样数（分子）从未登记，`coverage` 只有分母

```
实测（M4 前）：ruleset-bj.json 的 coverage = {note, rule_totals_by_check_type, rule_total}
              —— 只有分母，**没有任何 sample_count（分子）**
```
plan/04 §2.3 原话："只写分母就是假覆盖"。本项目此前**连分子都没有**——
"覆盖声明"是一句无法证伪的话。
**修复**：新增 `src/rca/benchmark/coverage.py`（单一实现源），逐形态实算
**分母（rule_total）+ 分子（sampled_rules）+ 采样清单（sampled_rule_ids / sample_ids）**
三件套，并声明"抽样覆盖、非逐条穷举"。生成器写入规则包，基准层核对"登记的数 == 实算的数"，
CLI 与报告都展示。
回归：`test_coverage_registers_numerator_not_only_denominator`（三包各一遍）/
`test_registered_numerator_matches_recomputed` / `test_coverage_reaches_report_and_cli` /
`test_report_markdown_contains_coverage_rows`。

### 2.2 B1 指标名实不符：plan/04 说 P/R/F1，实现只有布尔式 `field_accuracy`

```
实测（M4 前）：`_run_b1` 的 metric = "field_accuracy"，判据是
              "有值字段须有证据 / 无值字段须 absent"——**没有 precision / recall / F1**
```
**二选一**：① 实现真 P/R/F1；② 把文档改成与实现一致。**M4 选 ①**。
**修复**：真值侧逐样例登记 `expect_fields`（应有值的字段 → 期望取值）与
`expect_absent_fields`（应观测不到的字段），由生成器按合同入参**独立推导**
（不调用引擎抽取/量化函数——否则引擎抽错时期望跟着一起错，探活永远绿）。
B1 真算 TP/FP/FN → P/R/F1。
**注意**：布尔"存在性"标记（`has_deposit_clause` / `rent_pay_period_declared`）取 False 时
断言的是"文本里没有这一项"，为"不存在"索要证据条款不可满足——故"有值须有证据"这条附加
约束**限定在承载取值的字段**（非 bool）。
回归：`test_b1_reports_real_precision_recall_f1` /
`test_b1_denominator_comes_from_registered_field_truth` /
`test_b1_field_truth_is_independent_of_engine`。

### 2.3 `also_expect` 是"登记了但从不校验"的死数据

```
实测（M4 前）：`_run_b2` 只调 `compare_nonpass(s["expect"], observed)`
              —— **`also_expect` 完全没进对账**
```
`also_expect` 记"同一注入隐含的其余结论"（如 quota 条进条件触发栏的 `reference`）。
真值库里一个永不参与对账的字段，本身就是一种假覆盖。
更根本的问题：只算"非 pass 集合"会漏掉一整类错误——真值登记 `compliant`/`skipped`/`reference`、
观测却是别的 pass 侧状态时，两侧都不在非 pass 集合里，**恒不报**。
**修复**：新增 `compare_exact`（全量精确对账，`expect ∪ also_expect` 每条都核），
B2 分母改为真值登记**每条**规则（hits + missed + mismatch + unregistered）。
回归：`test_compare_exact_flags_status_on_pass_side` / `test_b2_reconciles_also_expect` /
`test_b2_catches_reference_status_mismatch`。

### 2.4 探活是"函数层"而非"端到端"（B1/B3 皆然）

```
实测（M4 前）：`test_probe_b1_detects_broken_expectation` 只断言
              `compare_nonpass()` 返回非空——**没有断言 `run_benchmarks()` 真的返回非 0**
```
对账函数对、但门槛判定通路没接上的话，旧断言照样绿。且 B1/B2 的 `_run_*` 此前
**忽略传入的 `data_dir`**（`compute_result` 不传 data_dir），导致"在另一个数据目录上跑完整通路"
根本做不到。
**修复**：`_run_b1`/`_run_b2` 接收并透传 `data_dir`；三个探活测试走**完整 `run_benchmarks(data_dir=tmp)`**
并断言 `== 1`。
**注意**：门槛是 0.95，只改一条样例的一处期望仍在容差内——此时基准判"达标"是**正确**的。
故 B1 探活**系统性**改错同一字段的全部样例（否则注入强度不足，证明不了门槛通路是活的）。
回归：`test_probe_b1_tampered_truth_makes_bench_fail_end_to_end` /
`test_probe_b3_boundary_mutation_makes_bench_fail_end_to_end`。

### 2.5 B2 的"坏引用注入"探活缺位

```
实测（M4 前）：plan/04 §5 表要求 B2 的注入缺陷是"注入一条必然误报的规则（坏引用）"，
              现测试只覆盖 B1/B3 的探活，**B2 的坏引用注入没有端到端探活**
```
**修复**：`test_probe_b2_bad_reference_injection_makes_bench_fail_end_to_end`——
在规则包里注入一条 `quote` **不逐字存在于快照**的规则（"坏引用"：看着有锚点、实则核不到原文），
引擎仍会加载并判定 → 产出真值库未登记的判定 → B2 未登记数 > 0 → 未达标。
回归：同上（端到端断言 `run_benchmarks == 1`）。

### 2.6 样例覆盖形态缺口：三处形态在基准里等于没测

```
实测（M4 前）：10 份样例全部是可识别合同 → **无一份能触发 not_assessed**；
              704 条要素完整性恒被 compliant 覆盖 → **缺失分支没测**；
              每个 check_type 形态是否有 ≥1 采样件，**没有任何登记**
```
plan/04 §7 明确要求覆盖三类易错形态，其中两类此前零采样件。
**修复**：样例扩到 12 份——
- `S-BJ-011`（剔除维修条）→ 704 条判 **noncompliant**（"无条件义务缺失 = noncompliant"）；
- `S-BJ-012`（非合同文本，刻意不含租赁关键词与条号）→ 整体 **not_assessed**（绝不输出 compliant）。
新增 `coverage_gaps()` 逐形态检查，**某形态有规则却零采样件 → 基准判未达标**
（分子为 0 的形态等于没测）。**无规则的形态（分母 0）不算缺口**——"没有这类规则"与
"有规则但没测"是两种情形。
回归：`test_missing_element_sample_yields_noncompliant` / `test_not_assessed_sample_exists` /
`test_every_check_type_form_has_a_sampled_case` /
`test_zero_sampled_form_makes_bench_fail_end_to_end`（**端到端**：`only="B3"` 隔离，
B3 自身必然通过，唯一未达标原因就是覆盖门）。

### 2.7 复核项（非缺陷，已确认不回归）

- **门槛五项齐备**：`B1_parse_f1_min` / `B2_hit_rate_min` / `B2_false_positive_max` /
  `B3_boundary_pass_rate_min` / `max_runtime_seconds` 三包各五项齐全（M0 已闭环）。
  回归：`test_thresholds_all_five_present`（三包各一遍）。
- **门槛真从 manifest 读**：把 manifest 门槛抬到 1.01（不可达）→ B1 必须报未达标。
  回归：`test_thresholds_come_from_manifest_not_code`。
- **空分母不冒充通过**：复核 M0 分支不回归。回归：`test_empty_denominator_never_passes`。
- **README 指标与实际一致**：评测表的三个分子/分母必须与基准实跑一致（防文档漂移）。
  回归：`test_readme_metrics_match_bench_output`（绑**实际取值**）。
- **真值库为每条生效规则登记期望**：生效规则（门控后 + 全国层叠加 + 条件触发栏）
  必须在每份同城样例的 `expect ∪ also_expect` 里有登记，否则 B2 分母缺项（假覆盖）。
  回归：`test_truth_registers_every_enabled_rule`。

---

## 3. M4 变异验证结论（`ALL_GUARDS_EFFECTIVE`，12/12）

脚本在 `_scratch/m4_mutation.py`（**不入仓**）。逐项回退修复，对应回归必须转红；
生成器类变异**先重生成产物**再跑测试；改源码后**清 `__pycache__`**。

| # | 注入的缺陷 | 结果 |
|---|---|---|
| M1 | B1 退回布尔式准确率（去掉真值侧字段分母） | 转红 ✅ |
| M2 | B2 退回只算非 pass 集合（`also_expect` 重新成死数据） | 转红 ✅ |
| M3 | 覆盖登记去掉分子（只留分母） | 转红 ✅（**须重生成产物**） |
| M4 | 报告覆盖表返回空行（读者看不到采样数） | 转红 ✅ |
| M5 | 覆盖登记脱钩：登记采样数写成全 0（与实际不符） | 转红 ✅（**须重生成产物**） |
| M6 | 覆盖门整体失效（零采样件不再判未达标） | 转红 ✅（**首轮假绿**，见下） |
| M7 | B2 吞掉坏引用注入的证据（未登记与误报都不计） | 转红 ✅（**首轮假绿**，见下） |
| M8 | 探活只断言对账函数（不回退门槛通路） | 转红 ✅ |
| M9 | 缺要素样例不再判 noncompliant（无条件义务缺失被降级） | 转红 ✅（**须重生成产物**） |
| M10 | 非合同样例改写成可识别合同（不再触发 not_assessed） | 转红 ✅（**须重生成产物**） |
| M11 | README 指标与实际脱钩（评测表写死旧数字） | 转红 ✅ |
| M12 | 门槛不再从 manifest 读（回落代码默认值） | 转红 ✅ |

**首轮两条假绿的教训（M5 可直接复用）**：
1. **M6 假绿**：变异只改了 `coverage_gaps` 的**调用结果**（`gaps = []`），
   而回归测试只断言 `coverage_gaps()` **纯函数**返回空 → 纯函数没被改，测试仍绿。
   教训：**守门测试必须走它真正要保护的产物通路**（这里是 `run_benchmarks` 的门槛判定），
   只测被回退的那个函数本身会漏掉"函数对但没接上"的形态。改为端到端断言后转红。
2. **M7 假绿**：变异只吞掉 `unregistered`，而坏引用注入的误报同时会走
   `false_positive` 通路 → 指标仍掉、测试仍绿。教训：**变异要打在"唯一证据通路"上**，
   打在有冗余通路的地方测不出门是否有效。改为同时吞掉两条通路后转红。

**结论**：变异验证要针对**断言的实际强度与通路的唯一性**，而非"断言的存在"。
"函数返回非空"、"纯函数返回空"这类**函数层断言**，在"函数对但接线断"的缺陷下恒绿。

---

## 4. 解析层形态支持矩阵（M2 收尾实测，M3/M4 未改动，供 M5 复核）

| 形态 | 输入 | 结果 | M2 新增？ |
|---|---|---|---|
| `第X条` 中文数字 | `第一条 …` | ✅ 切出 | M0 |
| `第X条` 阿拉伯数字 | `第1条 …` | ✅ 切出 | M0 |
| `第X条之一/之二` | `第一条之一 …` | ✅ 切出（单一不重复条号） | M2 |
| 中文顿号索引 | `一、…` | ✅ 切出（`kind=cn_index`） | M0 |
| 括号中文序号 | `（一）…` | ✅ 切出（`kind=paren_index`） | M2 |
| 阿拉伯点索引 | `1. …` | ✅ 切出（`kind=num_index`） | M0 |
| 逐字符空格（PDF 复制） | `第 一 条 …` | ✅ 折叠后切出 | M0 |
| CRLF | `\r\n` | ✅ 归一后切出 | M0 |
| 行内交叉引用 | `…遵守第五条…` | ✅ **不**切为边界，正文完整 | M2 |
| 断行交叉引用 | `…遵守\n第五条…` | ✅ 跳过 + 进 `pending_manual` | M2 |
| 后随引用限定 | `第五条规定的除外` | ✅ 跳过（静默，合法用法） | M2 |
| 真重复条号 | 两个 `第一条` | ✅ 去重 + 进 `pending_manual` | M2 |
| 非合同文本 | 一段说明文字 | ✅ 进 `pending_manual`（M4 新增样例 S-BJ-012 覆盖其判定侧） | M0 |

**中文租期表述**（`extract.py`，M2 新增）：`半年`→0.50 / `一年半`→1.50 /
`两年半`→2.50 / `6 个月`→0.50（月→年换算，M0 已有）。

---

## 5. 既定口径清单（K 清单——动了会打挂基准，改前先对照）

> M1–M3 的 K1–K27 原样保留（见 `plan/HANDOFF-M4.md` §5），以下只列 **M4 新增**的 K28–K30。

| # | 口径 | 位置 | 动了的连锁 |
|---|---|---|---|
| **K28** | **覆盖登记三件套**：分母（`rule_totals_by_check_type`/`rule_total`）+ 分子（`truth_sampling.<form>.sampled_rules`）+ 采样清单（`sampled_rule_ids`/`sample_ids`）+ 声明（`sampling_declaration`） | `src/rca/benchmark/coverage.py`（单一实现源） | 改则须同步生成器（写规则包）、基准核对、CLI 输出、报告覆盖章节；退回"只有分母"即假覆盖 |
| **K29** | **B1 真值侧字段登记**：`expect_fields`（应有值字段 → 期望取值）+ `expect_absent_fields`；期望由生成器按合同入参独立推导，**不得调用引擎抽取/量化函数** | `tools/gen_samples.py` `_expected_fields()` | 借引擎函数会让期望与引擎同源 → 引擎抽错时期望一起错 → 探活假绿（plan/04 §5） |
| **K30** | **B2 分母 = 真值登记每条规则**（`expect ∪ also_expect`），四类结果 hits/missed/mismatch/unregistered 全计入 | `src/rca/benchmark/runner.py` `_run_b2` + `cases.py` `compare_exact` | 退回"只算非 pass 集合"会让 `also_expect` 重新成死数据（pass 侧状态不符恒不报） |
| **K31** | **零采样件的形态 → 基准判未达标**；无规则的形态（分母 0）不算缺口 | `runner.py` `_coverage_problems()` | 去掉则"分子为 0 的假门"复活（形态有规则却没测，仍报达标） |
| **K32** | **布尔"存在性"标记不适用"有值须有证据"约束** | `runner.py` `_run_b1` | 收回该限定会让非合同样例（两个标记取 False）永远记 FP，B1 精度被"不可满足的要求"拉低 |

---

## 6. 本机环境坑（全部实测过）

- **`python` 不在 PATH**（商店占位符）：一律用 `py -3.12` / `py -3.8`。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：临时文件用工作区相对路径 `_scratch/`（已 gitignore）。
- **跑命令带 `-X utf8`**（中文控制台编码）；但**代码里的编码缺口会被它掩盖**——
  故入口有 `_ensure_utf8_stdio()`，且 CI 设 `PYTHONUTF8=1`。
- **`Path.write_text(newline=)` 是 Python 3.10+ 参数**：3.8 通道直接 TypeError（实测踩过）。
  生成器一律 `write_bytes`。
- **本机双解释器都可用**：`py -0` 列出 3.8.8-64 与 3.12-64，两者都装了 pytest + PySide6 + rca（editable）。
- **`py -3.12 -m pip install -e .` 会写 `src/rca.egg-info/`**：已被 .gitignore 覆盖。
- **基准/测试跑得快**（bench 0.018s、239 项测试约 5s）：每改一处都该跑全量。
- **`rca report` 在演示样例上退出码是 1**（检出不符合，既定语义）——用 `&&` 串联命令会在此断链，
  脚本里请用 `;` 或显式判断。
- **变异验证要清 `__pycache__`**：改源码后不清旧 `.pyc`，pytest 可能仍跑旧字节码，
  变异结果会假绿（M2 实测踩过，脚本里已加清理）。
- **生成器类变异必须先重生成产物**（M3 实测）：改 `gen_*.py` 但不跑生成器时，
  测试读到的还是旧产物 → 变异假绿。变异脚本须"改源码 → 跑生成器 → 跑测试"。
- **`_scratch/` 下的脚本 `_copy_data()` 复制整个 `data/`**：探活要在"另一个数据目录"上
  跑完整通路（改 `data/` 本体会污染冻结件，且被 `--check` 抓到）。
- **探针脚本别用 `\s` 裸字符串**：`py -3.12` 对无效转义序列发 `SyntaxWarning`（M2 实测），
  写正则一律用 raw string。

---

## 7. DoD（M5 出口判据，逐项勾选）

题面模块④⑥要求：PySide6 桌面 exe 打包 + CLI 双入口；纯本地零上传验证通过。
plan/05 把口径定死为"依赖分层、CI 矩阵、打包白名单单一事实源、脱敏审计、发布流程与留档"。

M0 已把 GUI 骨架（两个页签）、打包 spec、`packaging.py` 白名单、`build_release.py`、
`verify_package.py`、发布检查单建好。**M5 的实质是"把打包与双入口离线可用逐条证成"**，
而非从零实现——先复核既有实现是否真满足，再补缺口。

- [ ] **实构建**：`PyInstaller >= 6`（5.x 扫 PySide6 字节码确定性崩溃）在 3.12 通道真构建一次，
      产出 `dist/` 下的桌面 exe；**M0–M4 从未构建过**（R5），届时会暴露 spec 问题（按实况修）
- [ ] **打包白名单与产物一致**：`rca/packaging.py` `build_datas()` 的 datas 列表 == 实际入包内容；
      `data/` 下无未登记目录（否则白名单与排除项互相矛盾）
- [ ] **冻结态数据目录在 exe 内**：`rca selftest --out <file>` 在冻结态必须报
      `data_dir_in_dist: true`（否则 exe 回头读开发机仓库 `data/`，"内嵌数据验了个寂寞"）
- [ ] **冻结态判定可跑**：冻结 exe 上真跑一次 `check`（用内嵌样例）→ 结论与源码运行一致
- [ ] **纯本地零上传验证**：`verify_package.py` 的断网/无外链断言通过；报告无 `](http` 外链
      （已有 `test_markdown_has_no_external_links`，须在**冻结产物**上复跑一遍）
- [ ] **GUI 分层守门不回归**：GUI 只消费引擎 API、零判定逻辑（`test_gui_layering.py`）
- [ ] **双入口退出码语义一致**：CLI 与 GUI 的结论必须同源（都经 `engine/pipeline.py`），
      GUI 显示的整体判定 == CLI `check` 的输出
- [ ] `py -3.12 -X utf8 -m pytest -q` **双解释器**全绿（计数同步进 README）
- [ ] `rca bench` 三套件达标（exit 0），B2 误报 0
- [ ] `gen_rulesets.py --check` → `RULESETS_FROZEN_OK`
- [ ] `gen_samples.py --check` → `SAMPLES_FROZEN_OK`
- [ ] `check_literals.py` + `--selftest` 均 exit 0
- [ ] `audit_desensitize.py selftest` + `tracked` 均 exit 0（HARD 0）
- [ ] **变异验证**：M5 新增的每条守门逐项回退后必须转红（照 §3 的教训：
      断言绑实际取值、生成器类变异先重生成、**守门测试走它真正要保护的通路**）
- [ ] `plan/00` 里程碑表 M5 状态回写 ✅
- [ ] **本对话内写完 `plan/HANDOFF-M6.md`**（硬约束：不写不许结束对话）

**诚实口径**：M0–M5 未接远端，一切 CI 类判据写"**本地等价校验**（未接远端，CI 待首推验证）"。
**未推送 = 未跑 CI**，M6 首推后据实补记真实 run id。

---

## 8. 关键命令速查

```bash
# 验证（M5 每改一处都跑）
py -3.12 -X utf8 -m pytest -q                         # 239 项（双解释器各跑一遍）
py -3.12 -X utf8 -m rca.cli bench                     # 三套件 → BENCH_OK
py -3.12 -X utf8 tools/check_literals.py --selftest   # 门禁自检
py -3.12 -X utf8 tools/audit_desensitize.py tracked   # 脱敏（HARD 0）

# 数据（改 SPECS / 样例后按序执行；注意规则包须**先于**样例生成，因 coverage 读样例）
py -3.12 -X utf8 tools/gen_samples.py                 # 生成样例（coverage 的分子来源）
py -3.12 -X utf8 tools/gen_rulesets.py                # 生成规则包（读样例算 coverage）
py -3.12 -X utf8 tools/gen_rulesets.py --check        # → RULESETS_FROZEN_OK
py -3.12 -X utf8 tools/gen_samples.py --check         # → SAMPLES_FROZEN_OK
py -3.12 -X utf8 tools/fetch_sources.py --check       # 快照冻结校验

# 手工试用（引擎/报告改动后重点看这几条）
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京 --json
py -3.12 -X utf8 -m rca.cli rules --city 上海
py -3.12 -X utf8 -m rca.cli scan --dir data/samples --city 北京
py -3.12 -X utf8 -m rca.cli report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep

# 打包（M5 首次实跑，按实况修 spec）
py -3.12 -X utf8 tools/build_release.py               # 见 tools/rca.spec
py -3.12 -X utf8 tools/verify_package.py              # 产物校验
```

**注意生成顺序**：规则包的 `coverage.truth_sampling`（分子）**读样例**，
故改样例后必须重跑 `gen_rulesets.py`，否则 `RULESETS_FROZEN_OK` 会因为
"登记的分子与实算不符"而失败（这正是设计意图——登记的数与真实的数不能是两份）。

---

## 9. 下一棒启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务
```

**注意**：入库的 HANDOFF 内一律写**相对路径**（`plan/HANDOFF-M5.md`），
绝对路径只出现在用户侧的 `/goal` 启动命令中（否则发布期脱敏扫描必中）。

---

## 10. 遗留与风险

| # | 事项 | 处置 |
|---|---|---|
| R1 | **CI 从未真跑过**（无远端） | M6 首推 = 全项目首次 CI，须预算"多轮诊断"；M0 已前置 eol=lf / fetch-depth / extras / 编码三层，但**不能保证首跑全绿** |
| R2 | 提交邮箱是**真实 QQ 邮箱**（本机 git 全局配置） | M6 发布前必须改写为 GitHub noreply（首推前是零消费者窗口，`git filter-repo --email-callback`）。`audit_desensitize.py messages` 会如实报 HARD |
| R3 | `_scratch/` 是验证期草稿目录 | 已 gitignore；**绝不入仓**。M4 的变异脚本 `_scratch/m4_mutation.py` 在此 |
| R4 | **GUI 只做了骨架（两个页签）** | **M5 主体**：须实构建 + 冻结态验证；分层守门已就位 |
| R5 | **打包 spec 已写但从未构建过** | **M5 主体**：实构建时会暴露 spec 问题（PyInstaller 版本差异等），届时按实况修 |
| R6 | 规则包数值覆盖已补齐（京 10 / 沪 7 / 全国 4） | M1 已闭环；扩展其他城市须先走 `plan/02` §1 的原文直连预检 |
| R7 | 样例 **12 份** → B1 分母 90、B2 分母 150、B3 分母 14 | 后续改动须同步 README 评测表与 `tests/` 里任何写死计数的断言（`test_readme_metrics_match_bench_output` 已锁） |
| R8 | 配套办法来源目前只被 2 条规则引用 | 属"够用"而非"穷尽"；办法里还有押金退还 3 工作日、账户公示等可抽条目，M5 视需要扩 |
| R9 | 全国层只有 1 条数值规则（705） | 707/704/721 本质是定性/补充规则，无阈值——**不是遗漏**，`test_m1_coverage_floors` 已按此口径写死 |
| R10 | 配套办法的主体限定取"enterprise"而非"转租业务企业" | 原文限定的是"承租他人住房从事**转租业务**的住房租赁企业"；本项目主体识别只分 enterprise/individual（不判是否转租），故 escrow 两条对**所有**企业主体生效，比原文宽一档。属**已知保守偏差**：宁可对企业多提示，不可对个人误判。若 M5/M6 引入"是否转租"维度，须回来收紧 |
| R11 | 解析层新增守门有"吞真条款"风险（前导门收词过宽会把真条款当引用） | M2 已收窄到"不能单独收尾成句"的动词/介词（K20），并加负向测试。**后续若扩触发词表，必须同步加负向测试**（`test_noun_phrase_lead_does_not_eat_real_clause` 是模板） |
| R12 | `（一）` 括号序号与 `一、` 父级序号并列切出，层级关系未表达 | 现只切平铺序列（`kind` 区分形态），不建树。要素证据按 span 归属，平铺不影响归属正确性；若 M5/M6 需要"某分项属于哪一条"的层级语义，须扩 `Clause` 结构（**动模型前先看 K2 连锁**） |
| R13 | 中文租期只覆盖"年/月/年半/半年"，未覆盖"X个月零Y天"等复合表述 | 合同里极罕见；若实测遇到，按 K23 的形态补进 `_cn_half_years()` 同层（前置匹配），并加端到端测试 |
| R14 | 变异验证脚本在 `_scratch/`（不入仓） | 结论（`ALL_GUARDS_EFFECTIVE`）已写进本文件；M4 脚本 `_scratch/m4_mutation.py`（12 项）。若要常态化，M5/M6 可提成 `tools/` 下守门（须先评估运行时长与跨解释器稳定性；注意"生成器类变异须先重生成"与"清 `__pycache__`"两个前提） |
| R15 | **B1 指标名实不符已修**（plan/04 说 P/R/F1，实现只有 `field_accuracy`） | **M4 已闭环**：真值侧登记 `expect_fields`/`expect_absent_fields`，B1 真算 P/R/F1；plan/04 §1、README 评测表、`docs/技术报告.md` §3.3 三处措辞已对齐实现 |
| R16 | **真值库采样数（分子）从未登记** | **M4 已闭环**：`coverage.truth_sampling` 三件套（分母/分子/采样清单/声明），进 CLI 与报告；基准核对"登记 == 实算" |
| R17 | **`also_expect` 是死数据** | **M4 已闭环**：`compare_exact` 全量对账，B2 分母含 `also_expect` 每条 |
| **R18** | **覆盖门与探活的"函数层断言"陷阱**（首轮 M6/M7 假绿） | 守门测试必须走**它真正要保护的产物通路**（`run_benchmarks`），不能只测被回退的函数本身；变异要打在**唯一证据通路**上。M4 已在 `_scratch/m4_mutation.py` 固化这两条教训 |
| **R19** | **无规则的形态与"有规则却零采样"须区分** | `coverage_gaps()` 只把"分母 > 0 且分子 == 0"记为缺口；分母为 0（该包本无此形态）不算。改错会把正常的形态差异判成缺口（上海包无 `element_completeness` 条） |
