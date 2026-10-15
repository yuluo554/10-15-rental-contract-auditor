# HANDOFF-M4 — 基准与评测（里程碑交接快照）

> 上一棒：M3 知识规则（2026-10-15 完成）
> 下一棒目标：**M4 基准**——合成合同样例与植入真值、三层基准（题面模块⑤）
> 本文件用法（新对话启动）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务`

---

## 1. 当前进度（M3 已完成，证据位置）

| 项 | 状态 | 证据 |
|---|---|---|
| 北京规则包 10 条（数值 7） | ✅ | `data/rules/ruleset-bj.json`（sha256 前 16 位 `18733c0829c27175`，M3 **未改动**） |
| 上海规则包 7 条（数值 6） | ✅ | `data/rules/ruleset-sh.json`（`61be112ac3bab0b9`，未改动） |
| 全国层 4 条 | ✅ | `data/rules/ruleset-cn.json`（`23a667bdd69ba94a`，未改动） |
| 合成样例 10 份（含 2 份保租房） | ✅ | `data/samples/samples.json`（`d835e8daee1c0246`，未改动）+ `demo-contract-bj.txt` |
| **M3 主体：模块②③纪律逐条证成** | ✅ | `tests/test_m3_knowledge_rules.py`（26 个测试函数 / **44 个参数化用例**，详见 §2） |
| 测试全绿 | ✅ | **207 项**（M2 为 163，M3 净增 44），双解释器（3.8.8 / 3.12.10） |
| 生成器冻结 | ✅ | `gen_rulesets.py --check` / `gen_samples.py --check` / `fetch_sources.py --check` 三者均 exit 0 |
| 守门 | ✅ | `check_literals.py`（+`--selftest`）/ `audit_desensitize.py selftest|tracked` 均 exit 0（HARD 0） |
| 基准三套件 | ✅ | `BENCH_OK`（B1 90/90、B2 17/17 误报 0、B3 14/14）——**M3 未动基准，指标原样** |
| 变异验证 | ✅ | `ALL_GUARDS_EFFECTIVE`（**10 项变异全部转红**，详见 §3） |
| CI workflow | ✅ 已写 | `.github/workflows/ci.yml`（**仍未接远端，CI 待首推验证**） |

### M3 本地等价校验记录（未接远端，CI 待首推验证）

| 通路 | 命令 | 结果 |
|---|---|---|
| 全量测试 ×2 解释器 | `py -3.12 -X utf8 -m pytest -q` / `py -3.8 -X utf8 -m pytest -q` | **207 项全绿**，exit 0 |
| 快照冻结 | `tools/fetch_sources.py --check` | `SOURCES_FROZEN_OK` |
| 规则包冻结 | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK`（**改版本推导后仍位级一致**） |
| 样例冻结 | `tools/gen_samples.py --check` | `SAMPLES_FROZEN_OK` |
| 零字面量门禁 + 自检 | `tools/check_literals.py` / `--selftest` | exit 0 / `LITERAL_GATE_SELFTEST_OK`（token 9 个） |
| 脱敏审计自检 + 已跟踪 | `audit_desensitize.py selftest` / `tracked` | exit 0（HARD 0；advisory 5 只报；放行 26） |
| 基准三套件 | `rca bench` | `BENCH_OK`（耗时 0.028s） |
| 报告双轨导出 | `rca report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep` | Markdown + XLSX 均生成；**两次导出逐字节一致**（md `09e6bd2c77185f80` / xlsx `bd9f8f9664d89557`）；溯源行数 == 判定行数；两格式都含"法条原文"列与五态计数 |
| 判定可复现（判定层） | 同输入连跑 5 次逐字段比对 | findings/triggers/counts/version 全部一致 |
| 变异验证 | `_scratch/m3_mutation.py`（不入仓） | `ALL_GUARDS_EFFECTIVE`（10/10 转红） |

**不可本机实跑的通路（显式标注"待首推验证"）**：CI 矩阵的环境差异
（cp1252 编码、ubuntu 缺 Qt 系统库、actions/checkout 行为）。**M3 未改变该状态。**

---

## 2. M3 修掉的真缺口（均加回归 + 变异验证）

题面模块②要求："城市标识 → versioned ruleset（数值规则 + 法条原文锚点）；缺锚点的规则不得被引擎加载生效"。
模块③要求："条款序列 + 规则包 → 逐条判定；判定回指锚点 ID 与原文；**同版本 + 同输入 = 同输出**"。

M0 已建引擎骨架（五态、双重门控、作用域、全国层叠加、义务分栏），M1 补齐规则包数据与锚点门。
**M3 的实质是逐条证成这两条纪律**，而非从零实现。复核中实测出**五处产物层面的缺口**——
都不是"没写测试"，而是"承诺在产物里不成立"：

### 2.1 CLI JSON 出口无五态计数（`status_counts`）

```
实测：`rca check --json` 顶层键 = [card, city, conditional_triggers, disabled_rules,
      findings, overall_status, ruleset_id, ruleset_version, sources]  ← 无 status_counts
```
只有 `overall_status` 时，`not_assessed` 既可能是"全不适用"也可能是"有一半没能判定"——
**机读消费者又把五态退化成三态**，而这正是 D10 决策要防的假合规点。报告层早就有计数，
JSON 层没有，两条出口不对称。
**修复**：`Result.to_dict()` 下发 `status_counts` 与 `overall_summary`。
回归：`test_cli_json_carries_status_counts` / `test_unknown_and_not_assessed_are_distinguishable`。

### 2.2 报告判定表**没有法条原文列**（锚点只在 JSON 里）

```
实测：报告 findings 表头 = | 规则 ID | 规则 | 判定 | 风险级 | 约定值 | 规则限值 | 条款号 | 判定理由 |
      —— 只有条款号，**没有法条原文**；`res.findings[0].quote in md` → False
```
plan/03 §6.2 第 3 项明确要求"逐条判定（… + 条款号锚点 + **法条原文逐字引用**）"。
锚点只落在 JSON 里、报告表没有原文列，导出的报告就是"看起来有依据但读者核不到原文"——
**比不判定更危险**（题面模块②的原话即为此）。
**修复**：判定表加"法条原文"列；条件触发栏同样加（整栏若无可核证原文，读者无从复核）。
回归：`test_every_finding_row_carries_anchor_into_the_report` /
`test_conditional_trigger_rows_carry_anchor_too`（断言报告行 == 规则包对应字段，逐字）。

### 2.3 报告**不显示整体判定与五态计数**

导出文件常被单独转发给读者。只有明细表时，读者无法区分"全不适用"（`not_assessed`）
与"部分未判定"（`unknown`）——又一处把五态退化回三态。
**修复**：输入事实节输出整体结论 + **五态全列（含 0 项）**的计数。
**为什么必须"含 0 项"**：只列非零项会让"该状态检查过但为 0"与"该状态根本没纳入检查"
长得一样——正是五态要防的误读。
回归：`test_report_shows_counts_and_overall_status`（断言绑**实际取值**，不只绑标签字样）。

### 2.4 `version` 是 `SPECS` 里手写的字面量（可追溯性不成立）

DoD 要求"`ruleset_version` 进报告且**可从规则包 manifest 复算**"。实测：版本号是
`tools/gen_rulesets.py` 的 `SPECS` 里手写的 `"version": "2024.10"` 等三处字面量——
与数据脱钩的第二份真相。新增/替换一条规则所依据的来源后版本号还是旧的，
**报告标注的"依据版本"就指向了错的原文版本**，读者据此核证会核到错版本的法条。
**修复**：新增 `derive_version()`——取被本包规则引用的来源中**最晚 `effective_date`**，
形如 `YYYY.MM`；来源未登记或缺 `effective_date` 则**显式报错**（不静默回落）。
同时**删掉 SPECS 里三处手写 `version`**，使该口径无法被"抄回去"。
**注意**：推导值与原字面量完全一致（京 `2024.10` / 沪 `2023.02` / 全 `2021.01`），
故规则包**位级未变**（sha256 三者均与 M2 相同）。
回归：`test_ruleset_version_recomputable_from_manifest`（三个包各一遍）/
`test_version_reaches_both_outputs` / `test_derive_version_is_actually_computed_not_hardcoded`
（换施行日 → 推导值必须跟着变，证明真算）。

### 2.5 报告"未启用清单"引导语与实际拦截原因矛盾

```
实测：把北京包一条规则的 quote 置空（缺锚点）后：
      disabled_rules = [BJ-DEPOSIT-MAX-1M | 缺锚点（法条原文），不参与判定]
      报告 §4 引导语 = "以下规则的数值核对状态非 `verified`，未参与本次判定"
```
M1 起锚点门会往同一清单塞条目，但引导语仍只说"数值核对状态非 verified"——
读者被告知是**数值没核对**，清单里却写着**缺锚点**，理由与清单自相矛盾。
**修复**：引导语改为"因**数值核对状态非 `verified`** 或**缺锚点**（条款号 / 法条原文 / 来源）"。
回归：`test_disabled_section_wording_covers_anchor_blocks`（变异验证：改回旧措辞即转红）。

### 2.6 复核项（非缺陷，已确认不回归）

- **K17 缺锚点规则不得加载生效**：M1 已闭环。M3 把它扩到**三个包 × 三个锚点字段**
  （此前只测北京一个包的三个字段），并加"status=verified 但缺锚点仍被拦"的独立性断言。
  回归：`test_anchor_gate_holds_for_every_city_and_field`（9 个参数化用例）/
  `test_gate_holds_even_when_status_is_verified`。
- **城市差异包机制**：此前只靠 B2 样本间接覆盖。M3 加**显式用例**——同一份合同事实
  （个人房东 + 保租房 + 押金 2 个月，合同其余部分写全）在两城判出**不同结论**：
  北京全合规（企业专属押金上限对个人主体 `skipped`，北京无保租房押金条），
  上海 `noncompliant`（保租房押金上限实判）。用例刻意让**全国层在两城均合规**，
  使差异只能归因于城市包——否则"差异"可能来自全国层而非城市包。
  回归：`test_same_fact_different_city_different_verdict` /
  `test_affordable_rule_skips_ordinary_housing_in_same_city` / `test_city_packages_are_distinct_rulesets`。
- **覆盖登记分子/分母**：`rules --city X` 的 `rule_total` 必须 == 规则包实际条目数，
  逐形态分子合计 == 总数，且逐形态分布与规则包一致（防"登记的数与真实的数是两份"）。
  回归：`test_rules_coverage_matches_manifest`（三个包各一遍）。
- **判定求值顺序**：`findings` 顺序必须**等于门控后规则包顺序**。
  只断言"多次调用一致"不够——进程内 `hash()` 对同一字符串恒定，按 `hash` 排序照样"一致"，
  跨进程（`PYTHONHASHSEED` 不同）才漂移。回归：`test_judgment_order_matches_ruleset_order`。

---

## 3. M3 变异验证结论（`ALL_GUARDS_EFFECTIVE`，10/10）

脚本在 `_scratch/m3_mutation.py`（**不入仓**）。逐项回退修复，对应回归必须转红；
生成器类变异**先重生成产物**再跑测试（否则产物没变、测试读到的仍是旧值 → 假绿）。

| # | 注入的缺陷 | 结果 |
|---|---|---|
| M1 | 报告判定表去掉「法条原文」列 | 转红 ✅ |
| M2 | 条件触发栏去掉「法条原文」列 | 转红 ✅ |
| M3 | `Result.to_dict` 去掉 `status_counts` | 转红 ✅ |
| M4 | 报告整体判定改成占位串（**仍含标签字样**） | 转红 ✅（**首轮假绿**，见下） |
| M5 | `derive_version` 改成抄字面量（写死） | 转红 ✅（**须重生成产物**） |
| M6 | 加载侧锚点门被移除（quote 缺也不拦） | 转红 ✅ |
| M7 | 判定求值顺序改成按 `hash` 排序 | 转红 ✅（**首轮假绿**，见下） |
| M8 | 覆盖登记 `rule_total` 与实际条目数脱钩 | 转红 ✅（**须重生成产物**） |
| M9 | `unknown` 退化为 `skipped`（把没看到记成不用做） | 转红 ✅（由 M1 既有专项守门捕获） |
| M10 | 未启用清单引导语改回只说"数值核对状态非 verified" | 转红 ✅ |

**首轮两条假绿的教训（M4 可直接复用）**：
1. **M4 假绿**：断言只写"报告含'整体判定'字样"→ 把该行换成任意含同样字样的占位串仍绿。
   改为**绑定实际取值**（`"整体判定：%s" % result.overall_summary()`）后转红。
2. **M7 假绿**：断言只写"三次调用顺序相同"→ 进程内 `hash()` 恒定，按 `hash` 排序恒真。
   改为**绑定规则包顺序**后转红。
3. **M5/M8 假绿**：生成器类变异若不重生成产物，测试读到的仍是旧产物。
   变异脚本须**先跑生成器**再断言。

**结论**：变异验证要针对**断言的实际强度**，而非"断言的存在"。只写"含有某字样"
或"多次调用一致"这类弱断言，会在变异下暴露为假门。

---

## 4. 解析层形态支持矩阵（M2 收尾实测，M3 未改动，供 M4 复核）

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
| 非合同文本 | 一段说明文字 | ✅ 进 `pending_manual` | M0 |

**中文租期表述**（`extract.py`，M2 新增）：`半年`→0.50 / `一年半`→1.50 /
`两年半`→2.50 / `6 个月`→0.50（月→年换算，M0 已有）。

---

## 5. 既定口径清单（K 清单——动了会打挂基准，改前先对照）

| # | 口径 | 位置 | 动了的连锁 |
|---|---|---|---|
| K1 | 真值语义：`expect` 主期望 + `also_expect` 隐含结论；对账按"全部非 pass 集合" | `src/rca/benchmark/cases.py` | 改则须同步改 `tools/gen_samples.py` 与全部基准断言 |
| K2 | 判定五值 + `effect` 枚举取值集合 | `src/rca/model.py` | 改则须同步报告分栏、CLI 测试、基准 |
| K3 | 门槛来源 = 规则包 manifest（**非代码**） | `ruleset-*.json` 的 `benchmark_thresholds` | 基准层只读，缺失即 exit 2 |
| K4 | `effective_ruleset(city, scope)` 签名 + 作用域 `{calc, check, quota}` | `src/rca/engine/ruleset.py` | 改则须同步全部退出码断言 |
| K5 | 精度约定：金额/月数两位小数 `ROUND_HALF_UP`；月→年换算两位小数 | `parser/extract.py` `q2()` | 精度约定**非政策数值**，可豁免零字面量门禁 |
| K6 | 测试全离线、零 API 依赖（D5：首期不用 LLM） | 全项目 | — |
| K7 | CLI 退出码四语义 0/1/2/3 | `src/rca/cli.py` | 锁进 `tests/test_cli_contract.py` |
| K8 | 合成数据假名/假号段（`19900000000` 号段） | `data/README.md` §3 | 审计器已把该号段登记为**豁免项** |
| K9 | **条款号由快照机器推导，禁手抄；只认行首条号** | `tools/gen_rulesets.py` `derive_clause()` | 去掉会被交叉引用劫持（HANDOFF-M2 §2.1） |
| K10 | 零字面量门禁豁免阈值 = **≥10** 的规则数值 | `tools/check_literals.py` | 阈值 100 会让 token 集为空 → **假绿**（M0 实测踩过） |
| K11 | 城市包**叠加**全国层（同名 rule_id 城市优先） | `engine/ruleset.py` | 去掉会让租期上限等全国规则漏判（M0 被 B2 抓出） |
| K12 | 主体未知 → `unknown`（**不是 skipped**） | `engine/checker.py` `_applicability()` | 改则等于把"没做"记成"不用做" |
| K13 | `quote` 断言按规则自己声明的 `source_id` 取快照（非规则包主快照） | `tools/gen_rulesets.py` `build_ruleset()` | 改回主快照会让配套办法的规则误判成"未挂原文" |
| K14 | `applies_if` 支持 `lease_kind` 维度（`affordable`/`ordinary`） | `engine/checker.py` `_applicability()` + 规则包 | 去掉则保租房专属规则会对普通租赁住房误判（应 skipped） |
| K15 | 数值规则的 `op` 含下限类（`>=`/`>`），措辞按方向分派 | `engine/checker.py` `_limit_words()` | 统一写"上限"会把下限义务说反 |
| K16 | 未观测时仍挂 `limit`（`unknown` 不等于规则无口径） | `engine/checker.py` `_check_numeric()` | 去掉则报告显示 `<= —`，读者误读为无口径 |
| K17 | 锚点门在加载侧二次拦截：`clause`/`quote`/`source_id` 缺一即不生效（题面模块②硬约束） | `engine/ruleset.py` `effective_ruleset()` | 去掉则"缺锚点的规则不得被引擎加载生效"只剩生成器单点保障 |
| K18 | `applies_if.party` 必须回读来源的适用范围条（不能只看被引条款） | 规则包各条 + `docs/技术报告.md` | 配套办法第二条限定"住房租赁企业"，误标 `any` 会让个人房东被判 noncompliant |
| K19 | 条号只认"定义位"（行首，或同句内紧跟句末标点）——解析层对应 K9 | `src/rca/parser/clauses.py` `_is_definition_position()` | 去掉则正文交叉引用被当边界，上一条被劈开并凭空造出不存在条款（M2 §2.1） |
| K20 | 引用前导门只收"不能单独收尾成句"的动词/介词（不收名词短语） | `src/rca/parser/clauses.py` `_CITATION_LEAD` | 收进名词短语会把**真条款**当引用吞掉（M2 §2.2 自查） |
| K21 | 断行引用不静默：进 `pending_manual`；后随引用限定则静默跳过 | `src/rca/parser/clauses.py` | 静默则"看着成功、实则错位"（`located=True`）被当成功；全不静默则清单刷屏淹没真错位 |
| K22 | `之一` 后缀并进条号正则；重复条号去重并登记 | `src/rca/parser/clauses.py` `_PATTERNS` | 后缀不并进去会被先匹配成裸条号 → 重复条号 → `_locate` 互相错配（M2 §2.4） |
| K23 | 中文租期表述前置匹配（`X年半`/`半年` 先于通用 `X 年`）；中文数字表含 `两` | `src/rca/parser/extract.py` `_cn_half_years()` | 不前置则"一年半"被吃成 1.00（静默取错值）；漏抽让保租房下限规则漏报（M2 §2.6） |
| **K24** | **五态计数必须在 CLI JSON 与报告两条出口都可区分**（`unknown` = 没看到 vs `not_assessed` = 没检查过），且计数**五态全列含 0 项** | `model.py` `to_dict()` / `report/sections.py` `_counts_text()` | 去掉则机读/转发报告的读者把五态退化成三态（D10 的假合规点复活）（M3 §2.1/§2.3） |
| **K25** | **判定表与条件触发栏必须各带"法条原文"列**（锚点不能只落在 JSON 里） | `report/sections.py` `report_sections()` | 去掉则导出报告"看起来有依据但读者核不到原文"，比不判定更危险（M3 §2.2） |
| **K26** | **`version` 由台账机器推导**（引用来源中最晚 `effective_date` → `YYYY.MM`），SPECS 里**不得**出现手写 `version` | `tools/gen_rulesets.py` `derive_version()` | 手写会与数据脱钩，报告标注的"依据版本"指向错原文版本（M3 §2.4） |
| **K27** | **`findings` 顺序 == 门控后规则包顺序** | `engine/checker.py` `check_card()` | 按 `hash` 等不稳定键排序会在跨进程（`PYTHONHASHSEED` 不同）漂移，破坏"同版本同输入 = 同输出"（M3 §2.5） |

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
- **基准/测试跑得快**（bench 0.028s、207 项测试约 4s）：每改一处都该跑全量。
- **`rca report` 在演示样例上退出码是 1**（检出不符合，既定语义）——用 `&&` 串联命令会在此断链，
  脚本里请用 `;` 或显式判断。
- **变异验证要清 `__pycache__`**：改源码后不清旧 `.pyc`，pytest 可能仍跑旧字节码，
  变异结果会假绿（M2 实测踩过，脚本里已加清理）。
- **生成器类变异必须先重生成产物**（M3 实测）：改 `gen_rulesets.py` 但不跑生成器时，
  测试读到的规则包还是旧的 → 变异假绿。变异脚本须"改源码 → 跑生成器 → 跑测试"。
- **探针脚本别用 `\s` 裸字符串**：`py -3.12` 对无效转义序列发 `SyntaxWarning`（M2 实测），
  写正则一律用 raw string。

---

## 7. DoD（M4 出口判据，逐项勾选）

题面模块⑤要求：合成合同样例与植入真值、三层基准。plan/04 把口径定死为
"样本驱动 + 规则驱动两层，每套件配可证伪探活，空分母不冒充通过"。

M0 已把基准骨架建好（三套件、门槛随规则包下发、探活、空分母分支），
M1/M2 把样例扩到 10 份并把分母抬到 90/17/14。**M4 的实质是"把模块⑤的评测口径
逐条证成并补覆盖缺口"**，而非从零实现——先复核既有实现是否真满足，再补缺口。

- [ ] **真值库采样数（分子）必须登记**：plan/04 §2.3 要求 manifest 逐形态登记
      **"规则包条目总数 / 真值库采样数 / 采样清单"**三件套，并声明"抽样覆盖、非逐条穷举"。
      **现实测：`coverage` 里只有 `rule_total` 与 `rule_totals_by_check_type`（分母），
      没有任何 `sample_count`（分子）**——即"只写分母就是假覆盖"（plan/04 原话）。
      须补：从 `samples.json` 的 `expect`/`also_expect` 实算各形态采样数 + 采样清单（sample_id 列表），
      并加断言"分子 ≤ 分母 且 分子 > 0"。
- [ ] **B1 指标口径与实现对齐**：plan/04 §1 写 B1 = "要素抽取字段级 **P/R/F1**"，
      README 评测表写 "要素抽取字段准确率"；**现实现只算一个布尔式的 `field_accuracy`**
      （"有值字段须有证据 / 无值字段须 absent"），**没有 precision / recall / F1**。
      二选一：① 实现真 P/R/F1（需真值侧登记"应有字段"）；② 把 plan/04 与 README 的措辞
      改为与实现一致。**不得留"文档说 P/R/F1、实现只有准确率"的双口径**。
- [ ] **B2 探活须端到端**：现 `test_probe_b1_detects_broken_expectation` 只断言
      `compare_nonpass()` 返回非空（对账函数层），**没有断言 `run_benchmarks()` 真的返回非 0**。
      须加：篡改真值/样例后，`run_benchmarks(data_dir=tmp)` 必须 exit 1（走完整门槛判定通路）。
- [ ] **B2 误报探活缺位**：plan/04 §5 表要求 B2 的注入缺陷是"注入一条必然误报的规则（坏引用）"，
      现测试只覆盖了 B1/B3 的探活，**B2 的"坏引用注入"没有端到端探活**。
- [ ] **覆盖清单进产物**：`rules --city X` 与报告应能看出"该形态采样了几条"，
      而非只有总数（现 `coverage` 只有分母）。
- [ ] **样例覆盖形态检查**：现 10 份样例只覆盖京/沪两市，`lease_kind=affordable` 仅 2 份
      （上海）。须确认每个 `check_type` 形态都有 ≥1 份采样件，并登记清单。
- [ ] **门槛三件套齐备**：`B1_parse_f1_min` / `B2_hit_rate_min` / `B2_false_positive_max` /
      `B3_boundary_pass_rate_min` / `max_runtime_seconds` 五项须都在规则包 manifest 里
      （现 5 项齐备，复核确认不回归）。
- [ ] `py -3.12 -X utf8 -m pytest -q` **双解释器**全绿（计数同步进 README）
- [ ] `rca bench` 三套件达标（exit 0），B2 误报 0
- [ ] `gen_rulesets.py --check` → `RULESETS_FROZEN_OK`（若扩 coverage 段须重生成并同步 README 计数）
- [ ] `gen_samples.py --check` → `SAMPLES_FROZEN_OK`
- [ ] `check_literals.py` + `--selftest` 均 exit 0
- [ ] `audit_desensitize.py selftest` + `tracked` 均 exit 0（HARD 0）
- [ ] **变异验证**：M4 新增的每条守门逐项回退后必须转红（照 §3 的教训：
      断言绑实际取值、生成器类变异先重生成）
- [ ] `plan/00` 里程碑表 M4 状态回写 ✅
- [ ] **本对话内写完 `plan/HANDOFF-M5.md`**（硬约束：不写不许结束对话）

**诚实口径**：M0–M5 未接远端，一切 CI 类判据写"**本地等价校验**（未接远端，CI 待首推验证）"。
**未推送 = 未跑 CI**，M6 首推后据实补记真实 run id。

---

## 8. 关键命令速查

```bash
# 验证（M4 每改一处都跑）
py -3.12 -X utf8 -m pytest -q                         # 207 项（双解释器各跑一遍）
py -3.12 -X utf8 -m rca.cli bench                     # 三套件 → BENCH_OK
py -3.12 -X utf8 tools/check_literals.py --selftest   # 门禁自检
py -3.12 -X utf8 tools/audit_desensitize.py tracked   # 脱敏（HARD 0）

# 数据（改 SPECS / 样例后按序执行）
py -3.12 -X utf8 tools/gen_rulesets.py                # 生成规则包
py -3.12 -X utf8 tools/gen_rulesets.py --check        # → RULESETS_FROZEN_OK
py -3.12 -X utf8 tools/gen_samples.py                 # 生成样例
py -3.12 -X utf8 tools/gen_samples.py --check         # → SAMPLES_FROZEN_OK
py -3.12 -X utf8 tools/fetch_sources.py --check       # 快照冻结校验

# 手工试用（引擎/报告改动后重点看这几条）
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京 --json
py -3.12 -X utf8 -m rca.cli rules --city 上海 --json
py -3.12 -X utf8 -m rca.cli scan --dir data/samples --city 北京
py -3.12 -X utf8 -m rca.cli report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep
```

---

## 9. 下一棒启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务
```

**注意**：入库的 HANDOFF 内一律写**相对路径**（`plan/HANDOFF-M4.md`），
绝对路径只出现在用户侧的 `/goal` 启动命令中（否则发布期脱敏扫描必中）。

---

## 10. 遗留与风险

| # | 事项 | 处置 |
|---|---|---|
| R1 | **CI 从未真跑过**（无远端） | M6 首推 = 全项目首次 CI，须预算"多轮诊断"；M0 已前置 eol=lf / fetch-depth / extras / 编码三层，但**不能保证首跑全绿** |
| R2 | 提交邮箱是**真实 QQ 邮箱**（本机 git 全局配置） | M6 发布前必须改写为 GitHub noreply（首推前是零消费者窗口，`git filter-repo --email-callback`）。`audit_desensitize.py messages` 会如实报 HARD |
| R3 | `_scratch/` 是验证期草稿目录 | 已 gitignore；**绝不入仓**。M3 的变异脚本与探针均在此 |
| R4 | GUI 只做了骨架（两个页签） | M5 交付里程碑再扩；分层守门已就位 |
| R5 | 打包 spec 已写但**从未构建过** | M5 实构建时会暴露 spec 问题（PyInstaller 版本差异等），届时按实况修 |
| R6 | 规则包数值覆盖已补齐（京 10 / 沪 7 / 全国 4） | M1 已闭环；扩展其他城市须先走 `plan/02` §1 的原文直连预检 |
| R7 | 样例 10 份 → B1 分母 90、B2 分母 17、B3 分母 14 | 后续改动须同步 README 评测表与 `tests/` 里任何写死计数的断言 |
| R8 | 配套办法来源目前只被 2 条规则引用 | 属"够用"而非"穷尽"；办法里还有押金退还 3 工作日、账户公示等可抽条目，M4 视需要扩 |
| R9 | 全国层只有 1 条数值规则（705） | 707/704/721 本质是定性/补充规则，无阈值——**不是遗漏**，`test_m1_coverage_floors` 已按此口径写死 |
| R10 | 配套办法的主体限定取"enterprise"而非"转租业务企业" | 原文限定的是"承租他人住房从事**转租业务**的住房租赁企业"；本项目主体识别只分 enterprise/individual（不判是否转租），故 escrow 两条对**所有**企业主体生效，比原文宽一档。属**已知保守偏差**：宁可对企业多提示，不可对个人误判。若 M4/M5 引入"是否转租"维度，须回来收紧 |
| R11 | 解析层新增守门有"吞真条款"风险（前导门收词过宽会把真条款当引用） | M2 已收窄到"不能单独收尾成句"的动词/介词（K20），并加负向测试。**后续若扩触发词表，必须同步加负向测试**（`test_noun_phrase_lead_does_not_eat_real_clause` 是模板） |
| R12 | `（一）` 括号序号与 `一、` 父级序号并列切出，层级关系未表达 | 现只切平铺序列（`kind` 区分形态），不建树。要素证据按 span 归属，平铺不影响归属正确性；若 M4/M5 需要"某分项属于哪一条"的层级语义，须扩 `Clause` 结构（**动模型前先看 K2 连锁**） |
| R13 | 中文租期只覆盖"年/月/年半/半年"，未覆盖"X个月零Y天"等复合表述 | 合同里极罕见；若实测遇到，按 K23 的形态补进 `_cn_half_years()` 同层（前置匹配），并加端到端测试 |
| R14 | 解析层变异验证脚本在 `_scratch/`（不入仓） | 变异验证结论（`ALL_GUARDS_EFFECTIVE`）已写进本文件；M3 新增脚本 `_scratch/m3_mutation.py`。若要把变异验证常态化，M4/M5 可考虑把它提成 `tools/` 下的守门（须先评估运行时长与跨解释器稳定性；注意"生成器类变异须先重生成"这一前提） |
| **R15** | **B1 指标名实不符**（plan/04 说 P/R/F1，实现只有 `field_accuracy`） | **M4 首要处理项**，见 §7 DoD 第 2 条。留双口径会被评审判为"文档与实现不一致" |
| **R16** | **真值库采样数（分子）从未登记**，`coverage` 只有分母 | **M4 首要处理项**，见 §7 DoD 第 1 条。plan/04 §2.3 原话："只写分子就是假覆盖"——本项目目前**连分子都没有** |
| **R17** | **报告"未启用清单"章节措辞曾只提 `status`**，但 M1 起锚点门也会往该清单塞条目 | **M3 已修**：引导语改为"因数值核对状态非 `verified` **或**缺锚点（条款号 / 法条原文 / 来源）"，与逐条原因不再矛盾。回归 `test_disabled_section_wording_covers_anchor_blocks`（变异验证：改回旧措辞即转红） |
