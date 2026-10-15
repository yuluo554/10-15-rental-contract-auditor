# HANDOFF-M2 — 解析里程碑（交接快照）

> 上一棒：M1 数据先行（2026-10-15 完成）
> 下一棒目标：**M2 解析**——合同文本导入与条款切分（题面模块①）
> 本文件用法（新对话启动）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务`

---

## 1. 当前进度（M1 已完成，证据位置）

| 项 | 状态 | 证据 |
|---|---|---|
| 北京规则包 10 条（数值 7） | ✅ | `data/rules/ruleset-bj.json`（sha256 前 16 位 `b2a030855673ff21`） |
| 上海规则包 7 条（数值 6） | ✅ | `data/rules/ruleset-sh.json`（`61be112ac3bab0b9`） |
| 全国层 4 条 | ✅ | `data/rules/ruleset-cn.json`（`23a667bdd69ba94a`） |
| 配套办法来源被真实引用 | ✅ | 京包 2 条规则挂 `SRC-BJ-DEPOSIT-ESCROW`（第九条 / 第十三条） |
| 合成样例 10 份（含 2 份保租房） | ✅ | `data/samples/samples.json`（`58ab1ae13111efef`）+ `demo-contract-bj.txt` |
| 测试全绿 | ✅ | **148 项**，双解释器（3.8.8 / 3.12.10） |
| 生成器冻结 | ✅ | `gen_rulesets.py --check` / `gen_samples.py --check` / `fetch_sources.py --check` 三者均 exit 0 |
| 守门 | ✅ | `check_literals.py`（+`--selftest`）/ `audit_desensitize.py selftest|tracked` 均 exit 0（HARD 0） |
| 基准三套件 | ✅ | `BENCH_OK`（B1 90/90、B2 17/17 误报 0、B3 14/14） |
| CI workflow | ✅ 已写 | `.github/workflows/ci.yml`（**仍未接远端，CI 待首推验证**） |

### M1 本地等价校验记录（未接远端，CI 待首推验证）

| 通路 | 命令 | 结果 |
|---|---|---|
| 全量测试 ×2 解释器 | `py -3.12 -m pytest -q` / `py -3.8 -m pytest -q` | **148 项全绿**，exit 0 |
| 快照冻结 | `tools/fetch_sources.py --check` | `SOURCES_FROZEN_OK` |
| 规则包冻结 | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK` |
| 样例冻结 | `tools/gen_samples.py --check` | `SAMPLES_FROZEN_OK` |
| 零字面量门禁 + 自检 | `tools/check_literals.py` / `--selftest` | exit 0 / `LITERAL_GATE_SELFTEST_OK`（token 9 个） |
| 脱敏审计自检 + 已跟踪 | `audit_desensitize.py selftest` / `tracked` | exit 0（HARD 0；advisory 5 只报） |
| 基准三套件 | `rca bench` | `BENCH_OK` |
| 报告双轨导出 | `rca report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep` | Markdown + XLSX 均生成，溯源行数 == 判定行数（导出前断言通过） |
| 规则包可读性 | `rca rules --city 北京/上海` | 条目数/来源/门槛/覆盖登记齐 |

**不可本机实跑的通路（显式标注"待首推验证"）**：CI 矩阵的环境差异
（cp1252 编码、ubuntu 缺 Qt 系统库、actions/checkout 行为）。**M1 未改变该状态。**

### M1 规则清单（逐条，供 M2 起复核）

| 包 | 规则 ID | 条号 | scope | 值 | M1 新增？ |
|---|---|---|---|---|---|
| 全国 | `CN-LEASE-TERM-MAX` | 705 | calc | 20 年 | M0 |
| 全国 | `CN-ELEMENT-COMPLETENESS` | 704 | check | 定性 | M0 |
| 全国 | `CN-RENT-PAY-PERIOD` | 721 | check | 定性 | M0 |
| 全国 | `CN-WRITTEN-FORM-6M` | **707** | check | 定性 | **M1** |
| 北京 | `BJ-DEPOSIT-MAX-1M` | 36 | calc | 1 月 | M0 |
| 北京 | `BJ-RENT-PREPAY-MAX-3M` | 36 | calc | 3 月 | M0 |
| 北京 | `BJ-FILING-30D` | 15 | calc | 30 日 | M0 |
| 北京 | `BJ-LODGING-REG-3WD` | 15 | calc | 3 工作日 | M0 |
| 北京 | `BJ-DEPOSIT-REFUND-3WD` | 36 | calc | 3 工作日 | M0 |
| 北京 | `BJ-CONTRACT-ELEMENT-DEPOSIT` | 14 | check | 定性 | M0 |
| 北京 | `BJ-RENT-INTERVENTION` | 60 | quota | — | M0 |
| 北京 | `BJ-ENTERPRISE-FILING-30D` | **27** | calc | 30 日 | **M1** |
| 北京 | `BJ-ESCROW-DEPOSIT-TERMS` | **9**（配套办法） | check | 定性 | **M1** |
| 北京 | `BJ-ESCROW-RENT-SUPERVISION` | **13**（配套办法） | quota | 3 月 | **M1** |
| 上海 | `SH-FILING-30D` | 17 | calc | 30 日 | M0 |
| 上海 | `SH-RENT-DEPOSIT-ESCROW` | 29 | calc | 1 月 | M0 |
| 上海 | `SH-AFFORDABLE-DEPOSIT-1M` | 37 | calc | 1 月 | M0 |
| 上海 | `SH-ENTERPRISE-FILING-30D` | 22 | calc | 30 日 | M0 |
| 上海 | `SH-AFFORDABLE-TERM-MIN-1Y` | **37** | calc | 1 年（**下限**） | **M1** |
| 上海 | `SH-PENALTY-AFFORDABLE-RENT-DEPOSIT` | **61** | quota | 50000 元 | **M1** |
| 上海 | `SH-BAN-5Y-AFFORDABLE-APPLY` | **59** | quota | — | **M1** |

---

## 2. M1 修掉的两个真缺陷（都加了回归）

### 2.1 条号推导被正文交叉引用劫持（严重）

`derive_clause()` 原实现是"定位 anchor → 回溯到任意位置最近的 `第X条`"。正文里的
**交叉引用**也是 `第X条` 形态，于是：

- 上海第六十一条的罚则（正文以"违反本条例**第三十七条**第二款规定…"开头）
  → 被推导成 **第三十七条**（错）
- 上海第五十九条的骗保罚则（正文以"违反本条例**第三十五条**第一款第三项规定…"开头）
  → 被推导成 **第三十五条**（错）

**后果**：报告把罚则挂到错误法条上，读者按该条号去官方原文核证会核不到——
比漏报更危险（漏报是"没查"，错挂是"查错了还给了错误的核对指引"）。

**修复**：条号只认**行首**匹配（官方快照里条号一律起于行首）。回归：
`test_derive_clause_ignores_inline_cross_references`、`test_penalty_rule_clause_is_its_own_article`。

### 2.2 跨来源规则的 `quote` 断言取错快照

北京包同时引用《条例》与配套《暂行办法》。原断言拿规则包**主快照**做逐字比对，
配套办法的规则会被误判成"未挂原文"（实际它在自己的来源里逐字存在）。
**修复**：按规则自己声明的 `source_id` 取快照。回归：`test_quote_asserted_against_its_own_source_snapshot`。

### 2.3 顺带修掉的展示缺陷

- **下限类规则的方向措辞**：`op` 为 `>=`/`>` 时，原实现一律写"未超过规则上限"——
  把"保租房租期不得少于一年"说成"不得超过一年"，**方向说反**。现按 `op` 分派措辞
  （下限类写"低于规则下限"）。回归：`test_lower_bound_rule_reason_uses_lower_bound_wording`。
- **未观测时丢掉限值**：合同没写某要素时，报告"规则限值"列显示 `<= —`，读者会误以为
  该条没有数值口径。现照挂 `limit`（`<= 30`）。回归：`test_unobserved_numeric_rule_still_reports_its_limit`。
- **缺锚点规则会被引擎放行（题面硬约束未在加载侧落实）**：题面模块②要求"缺锚点的规则
  不得被引擎加载生效"，但原门控**只查 `status`**——一条 `status=verified` 却缺 `quote`/`clause`
  的规则照样进判定路径（实测确认）。生成器对出厂规则有逐字断言，但门控不能只依赖上游：
  规则包可被手工替换、也可由第三方扩展包提供。现于 `effective_ruleset()` 加**锚点门**
  （`clause`/`quote`/`source_id` 缺一即拦下并进"未启用清单"）。
  回归：`test_rule_missing_anchor_is_gated_out`（参数化三字段）。

### 2.4 HANDOFF-M1 §2 的两个"复核项"——M1 已闭环（结论已锁进测试）

| HANDOFF-M1 原任务 | 复核结论 | 锁定测试 |
|---|---|---|
| §2.1 复核 `BJ-CONTRACT-ELEMENT-DEPOSIT`（第十四条）要素清单是否该扩 | **不扩，有意保持"押金数额 + 支付期限和方式"两项**。第十四条的通盘要素完整性已由全国层 704 条（`CN-ELEMENT-COMPLETENESS`，6 项）承担；本条的价值在北京特有的"押金数额一般不超过一个月租金"半句。铺开成全 10 项会与 704 条**重复判定同一件事**（同一缺失被记两次），可读性反而下降 | `test_bj_article14_elements_scope_is_deliberate` |
| §2.3 复核 721 条法定补充规则的判定形态（现为 `rent_pay_period_declared` 定性） | **保持 `unknown`**。721 条是**法定补充规则**——未约定时由法律补充，不是当事人的违法行为。判 `noncompliant` 会把"法律已经替你规定了"说成"你违规了"（假 noncompliant，冤枉用户）。`unknown` + 理由写明"非法定违反，仅提示"，方向保守且如实 | `test_rent_pay_period_missing_is_unknown_not_noncompliant` |

---

## 3. M2 待办（按优先级）

题面模块①要求："合同文本导入与条款切分——切分条款号可回定位原文，无法定位项显式标注。"

M0 已把解析层的**骨架**建好（`parser/clauses.py` 切分 + `parser/extract.py` 抽取 + 证据逐字校验）。
**M1 收尾时对切分形态做了实测盘点**（下列结论均已实跑，非推测），据此定 M2 范围：

**已支持的形态**（实测通过，无需再做）：

| 形态 | 输入 | 结果 |
|---|---|---|
| `第X条` 中文数字 | `第一条 …` | ✅ 切出 |
| `第X条` 阿拉伯数字 | `第1条 …` | ✅ 切出 |
| 中文顿号索引 | `一、…` | ✅ 切出（kind=`cn_index`） |
| 阿拉伯点索引 | `1. …` | ✅ 切出（kind=`num_index`） |
| 逐字符空格（PDF 复制） | `第 一 条 …` | ✅ 折叠后切出 |
| CRLF | `\r\n` | ✅ 归一后切出 |

**实测发现的真缺陷（M2 必修）**：

1. **正文交叉引用被当成条款边界（严重，与 M1 的条号劫持同源）**：
   ```
   输入：第一条 甲方将房屋出租给乙方。乙方应遵守第五条关于维修的约定。
        第二条 租赁期限为 2 年。
   实测：切出 3 条 → ['第一条', '第五条', '第二条']
   ```
   第一条的正文被"第五条"从中间**劈开**，并凭空造出一个"第五条"条款。
   后果：条款序列错乱 → 要素抽取的证据条款号错挂 → 报告把判定依据指向不存在的条款。
   **与 M1 修掉的 `derive_clause` 劫持是同一类缺陷**（把引用当定义），
   但发生在解析层，M1 的修复不覆盖它。
2. **"第X条之一"（修订条文）未支持**：实测 `第一条之一` 被切成**两个 `第一条`**
   （重复条号，`located` 均 True）。须支持 `之一`/`之二` 后缀形态。
3. **`（一）` 括号中文序号未支持**：实测切不出任何条款，整体进 `pending_manual`
   （"未切分出任何条款"）。这是"显式标注"的正确行为，但覆盖面应补。
4. **重复条号的回定位**：`_locate()` 已用 cursor 保证单调递增，但缺陷 2 造成的
   重复条号会互相错配；修缺陷 2 时须一并加负向测试。

**M2 其余待办**：

5. **要素抽取覆盖面**（`parser/extract.py`）：现覆盖押金/租期/备案/出租登记/退押金/企业备案/
   单次收租 7 类。M1 新增规则带出新输入面，须确认：
   - `lease_term_years` 月→年换算已有（实测 `6 个月` → `0.50` 年 ✓），
     但 **`半年` 这类中文表述抽不到**（实测 `value=None`）——保租房租期下限依赖该字段，
     漏抽会让下限规则判 `unknown` 而非 `noncompliant`（**漏报**）。
   - `enterprise_filing_days`（营业执照领取日）：合同一般没有，判 `unknown` 是**预期行为**
     （见 `plan/02` §5.2 的"第三个陷阱"），但须确认不会误抽到别的数字。
6. **无法定位项显式标注**（`pending_manual`）：现仅"整段无条款号"与"条号回定位失败"进清单。
   待补：缺陷 1 那类"边界错但 located=True"的形态——**它现在是静默的**，
   这是最危险的一种（看着成功、实则错位）。

**每改一处解析层的固定动作**：
1. `py -3.12 -X utf8 -m pytest -q`（**148 项必须仍全绿**；双解释器各跑一遍）
2. `py -3.12 -X utf8 -m rca.cli bench`（三套件必须仍达标；B1 分母会随字段增减变化）
3. **若改了抽取字段或样例正文** → 须同步 `tools/gen_samples.py` 的 `expect` 推导并重跑生成器
   （`gen_samples.py --check` → `SAMPLES_FROZEN_OK`）
4. `py -3.12 -X utf8 tools/check_literals.py`（解析层在扫描面内，**不得引入政策数值字面量**）

**扩展项（非门槛）**：图片型 PDF / 扫描件不在首期范围（题面已声明），OCR 通路属扩展项。

---

## 4. 既定口径清单（K 清单——动了会打挂基准，改前先对照）

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
| K9 | **条款号由快照机器推导，禁手抄；只认行首条号** | `tools/gen_rulesets.py` `derive_clause()` | M1 补的"行首"限定：去掉会被交叉引用劫持（§2.1） |
| K10 | 零字面量门禁豁免阈值 = **≥10** 的规则数值 | `tools/check_literals.py` | 本项目政策数值多为个位数，阈值 100 会让 token 集为空 → **假绿**（M0 实测踩过） |
| K11 | 城市包**叠加**全国层（同名 rule_id 城市优先） | `engine/ruleset.py` | 去掉会让租期上限等全国规则漏判（M0 被 B2 抓出） |
| K12 | 主体未知 → `unknown`（**不是 skipped**） | `engine/checker.py` `_applicability()` | 改则等于把"没做"记成"不用做" |
| **K13** | **`quote` 断言按规则自己声明的 `source_id` 取快照**（非规则包主快照） | `tools/gen_rulesets.py` `build_ruleset()` | 改回主快照会让配套办法的规则误判成"未挂原文"（§2.2） |
| **K14** | **`applies_if` 支持 `lease_kind` 维度**（`affordable`/`ordinary`） | `engine/checker.py` `_applicability()` + 规则包 | 去掉则保租房专属规则会对普通租赁住房误判（应 skipped） |
| **K15** | **数值规则的 `op` 含下限类（`>=`/`>`），措辞按方向分派** | `engine/checker.py` `_limit_words()` | 统一写"上限"会把下限义务说反（§2.3） |
| **K16** | **未观测时仍挂 `limit`**（`unknown` 不等于规则无口径） | `engine/checker.py` `_check_numeric()` | 去掉则报告显示 `<= —`，读者误读为无口径 |
| **K17** | **锚点门在加载侧二次拦截**：`clause`/`quote`/`source_id` 缺一即不生效（题面模块②硬约束） | `engine/ruleset.py` `effective_ruleset()` | 去掉则"缺锚点的规则不得被引擎加载生效"只剩生成器单点保障；规则包被手工替换或第三方扩展包提供时会被放行（M1 实测：原实现只查 status，缺锚点仍进判定路径） |

---

## 5. 本机环境坑（全部实测过）

- **`python` 不在 PATH**（商店占位符）：一律用 `py -3.12` / `py -3.8`。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：临时文件用工作区相对路径 `_scratch/`（已 gitignore）。
- **跑命令带 `-X utf8`**（中文控制台编码）；但**代码里的编码缺口会被它掩盖**——
  故入口有 `_ensure_utf8_stdio()`，且 CI 设 `PYTHONUTF8=1`。
- **`Path.write_text(newline=)` 是 Python 3.10+ 参数**：3.8 通道直接 TypeError（实测踩过）。
  生成器一律 `write_bytes`。
- **本机双解释器都可用**：`py -0` 列出 3.8.8-64 与 3.12-64，两者都装了 pytest + PySide6 + rca（editable）。
- **`py -3.12 -m pip install -e .` 会写 `src/rca.egg-info/`**：已被 .gitignore 覆盖。
- **基准/测试跑得快**（bench 0.03s、148 项测试约 4s）：每改一处都该跑全量。
- **`rca report` 在演示样例上退出码是 1**（检出不符合，既定语义）——用 `&&` 串联命令会在此断链，
  脚本里请用 `;` 或显式判断。

---

## 6. DoD（M2 出口判据，逐项勾选）

- [ ] **正文交叉引用不再被当成条款边界**（`第一条 …应遵守第五条…` 必须只切出"第一条"），加负向测试
- [ ] **`第X条之一` 修订条文形态**支持（不产生重复条号），加测试
- [ ] **`（一）` 括号中文序号**支持，或明确留档为"不支持且进 `pending_manual`"
- [ ] **边界错位不静默**：`located=True` 但正文被劈开的形态能进 `pending_manual`（或有等价守门）
- [ ] 中文租期表述（`半年`）能抽取并换算，否则保租房下限规则会漏报
- [ ] `py -3.12 -X utf8 -m pytest -q` **双解释器**全绿（计数同步进 README）
- [ ] `rca bench` 三套件达标（exit 0），B2 误报 0
- [ ] `gen_samples.py --check` → `SAMPLES_FROZEN_OK`（若改了 expect 须重生成）
- [ ] `gen_rulesets.py --check` → `RULESETS_FROZEN_OK`（M2 不应改规则包；若改了须重生成）
- [ ] `check_literals.py` + `--selftest` 均 exit 0
- [ ] `audit_desensitize.py selftest` + `tracked` 均 exit 0（HARD 0）
- [ ] `plan/00` 里程碑表 M2 状态回写 ✅
- [ ] **本对话内写完 `plan/HANDOFF-M3.md`**（硬约束：不写不许结束对话）

**诚实口径**：M0–M5 未接远端，一切 CI 类判据写"**本地等价校验**（未接远端，CI 待首推验证）"。
**未推送 = 未跑 CI**，M6 首推后据实补记真实 run id。

---

## 7. 关键命令速查

```bash
# 验证（M2 每改一处都跑）
py -3.12 -X utf8 -m pytest -q                         # 148 项（双解释器各跑一遍）
py -3.12 -X utf8 -m rca.cli bench                     # 三套件 → BENCH_OK
py -3.12 -X utf8 tools/check_literals.py --selftest   # 门禁自检
py -3.12 -X utf8 tools/audit_desensitize.py tracked   # 脱敏（HARD 0）

# 数据（改 SPECS / 样例后按序执行）
py -3.12 -X utf8 tools/gen_rulesets.py                # 生成规则包
py -3.12 -X utf8 tools/gen_rulesets.py --check        # → RULESETS_FROZEN_OK
py -3.12 -X utf8 tools/gen_samples.py                 # 生成样例
py -3.12 -X utf8 tools/gen_samples.py --check         # → SAMPLES_FROZEN_OK
py -3.12 -X utf8 tools/fetch_sources.py --check       # 快照冻结校验

# 手工试用（解析层改动后重点看这几条）
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京 --json
py -3.12 -X utf8 -m rca.cli rules --city 上海 --json
py -3.12 -X utf8 -m rca.cli report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep
```

---

## 8. 下一棒启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务
```

**注意**：入库的 HANDOFF 内一律写**相对路径**（`plan/HANDOFF-M2.md`），
绝对路径只出现在用户侧的 `/goal` 启动命令里（否则发布期脱敏扫描必中）。

---

## 9. 遗留与风险

| # | 事项 | 处置 |
|---|---|---|
| R1 | **CI 从未真跑过**（无远端） | M6 首推 = 全项目首次 CI，须预算"多轮诊断"；M0 已在开发期前置了 eol=lf / fetch-depth / extras / 编码三层，但**不能保证首跑全绿** |
| R2 | 提交邮箱是**真实 QQ 邮箱**（本机 git 全局配置） | M6 发布前必须改写为 GitHub noreply（首推前是零消费者窗口，`git filter-repo --email-callback`）。`audit_desensitize.py messages` 会如实报 HARD |
| R3 | `_scratch/` 是验证期草稿目录 | 已 gitignore；**绝不入仓** |
| R4 | GUI 只做了骨架（两个页签） | M5 交付里程碑再扩；分层守门已就位 |
| R5 | 打包 spec 已写但**从未构建过** | M5 实构建时会暴露 spec 问题（PyInstaller 版本差异等），届时按实况修 |
| R6 | 规则包数值覆盖已补齐（京 10 / 沪 7 / 全国 4） | M1 已闭环；扩展其他城市须先走 `plan/02` §1 的原文直连预检 |
| **R7** | **样例增至 10 份后，B1 分母 90、B2 分母 17、B3 分母 14** | 后续改动须同步 README 的评测表与 `tests/` 里任何写死计数的断言 |
| **R8** | **配套办法来源目前只被 2 条规则引用** | 属"够用"而非"穷尽"；办法里还有押金退还 3 工作日、账户公示等可抽条目，M2/M3 视需要扩 |
| **R9** | 全国层只有 1 条数值规则（705） | 707/704/721 本质是定性/补充规则，无阈值——**不是遗漏**，`test_m1_coverage_floors` 已按此口径写死 |
