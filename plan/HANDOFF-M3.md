# HANDOFF-M3 — 知识规则（里程碑交接快照）

> 上一棒：M2 解析（2026-10-15 完成）
> 下一棒目标：**M3 知识规则**——城市差异包加载 + 数值规则判定引擎（题面模块②③）
> 本文件用法（新对话启动）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务`

---

## 1. 当前进度（M2 已完成，证据位置）

| 项 | 状态 | 证据 |
|---|---|---|
| 北京规则包 10 条（数值 7） | ✅ | `data/rules/ruleset-bj.json`（sha256 前 16 位 `18733c0829c27175`） |
| 上海规则包 7 条（数值 6） | ✅ | `data/rules/ruleset-sh.json`（`61be112ac3bab0b9`） |
| 全国层 4 条 | ✅ | `data/rules/ruleset-cn.json`（`23a667bdd69ba94a`） |
| 配套办法来源被真实引用 | ✅ | 京包 2 条规则挂 `SRC-BJ-DEPOSIT-ESCROW`（第九条 / 第十三条） |
| 合成样例 10 份（含 2 份保租房） | ✅ | `data/samples/samples.json`（`d835e8daee1c0246`）+ `demo-contract-bj.txt` |
| **解析层加固（M2 主体）** | ✅ | `src/rca/parser/clauses.py` + `parser/extract.py`（详见 §2） |
| 测试全绿 | ✅ | **163 项**，双解释器（3.8.8 / 3.12.10） |
| 生成器冻结 | ✅ | `gen_rulesets.py --check` / `gen_samples.py --check` / `fetch_sources.py --check` 三者均 exit 0 |
| 守门 | ✅ | `check_literals.py`（+`--selftest`）/ `audit_desensitize.py selftest|tracked` 均 exit 0（HARD 0） |
| 基准三套件 | ✅ | `BENCH_OK`（B1 90/90、B2 17/17 误报 0、B3 14/14） |
| CI workflow | ✅ 已写 | `.github/workflows/ci.yml`（**仍未接远端，CI 待首推验证**） |

### M2 本地等价校验记录（未接远端，CI 待首推验证）

| 通路 | 命令 | 结果 |
|---|---|---|
| 全量测试 ×2 解释器 | `py -3.12 -X utf8 -m pytest -q` / `py -3.8 -X utf8 -m pytest -q` | **163 项全绿**，exit 0 |
| 快照冻结 | `tools/fetch_sources.py --check` | `SOURCES_FROZEN_OK` |
| 规则包冻结 | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK` |
| 样例冻结 | `tools/gen_samples.py --check` | `SAMPLES_FROZEN_OK` |
| 零字面量门禁 + 自检 | `tools/check_literals.py` / `--selftest` | exit 0 / `LITERAL_GATE_SELFTEST_OK`（token 9 个） |
| 脱敏审计自检 + 已跟踪 | `audit_desensitize.py selftest` / `tracked` | exit 0（HARD 0；advisory 5 只报；放行 26） |
| 基准三套件 | `rca bench` | `BENCH_OK` |
| 报告双轨导出 | `rca report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep` | Markdown + XLSX 均生成，溯源行数 == 判定行数（导出前断言通过） |
| 规则包可读性 | `rca rules --city 北京/上海` | 条目数/来源/门槛/覆盖登记齐 |
| 解析层变异验证 | 逐项回退 8 处修复，对应回归测试逐个转红 | `ALL_GUARDS_EFFECTIVE`（**测试在缺陷存在时会失败**，非"碰巧绿"） |

**不可本机实跑的通路（显式标注"待首推验证"）**：CI 矩阵的环境差异
（cp1252 编码、ubuntu 缺 Qt 系统库、actions/checkout 行为）。**M2 未改变该状态。**

---

## 2. M2 修掉的真缺陷（均已加回归 + 变异验证）

题面模块①要求："切分条款号可回定位原文，无法定位项显式标注。"
M2 的缺陷全部由**实测**发现（非推测），逐条列在下方。**每条都做过变异验证**：
把修复回退后，对应回归测试确实转红——测试在缺陷存在时**会失败**，才有守门价值。

### 2.1 正文交叉引用被当成条款边界（严重，与 M1 条号劫持同源）

```
输入：第一条 甲方将房屋出租给乙方。乙方应遵守第五条关于维修的约定。
     第二条 租赁期限为 2 年。
原实测：切出 3 条 → ['第一条', '第五条', '第二条']
```
第一条正文被"第五条"从中间**劈开**，并凭空造出一个"第五条"条款。
后果：条款序列错乱 → 要素抽取的证据条款号错挂 → 报告把判定依据指向**不存在的条款**。
与 M1 修掉的 `derive_clause()` 劫持是**同一类缺陷**（把"引用"当"定义"），
但发生在解析层，M1 的修复不覆盖它。

**修复**：条号只认**定义位**——行首，或同句内紧跟句末标点。
回归：`test_inline_cross_reference_is_not_a_clause_boundary`。

### 2.2 断行交叉引用（`located=True` 却错位，最危险的一种）

PDF 复制常见断行形态：`…乙方应遵守` 换行 `第五条关于维修的约定。`
条号确实落在**行首**，定义位判定会放行——它会**静默地**劈开上一条正文
（`located=True`，看着成功、实则错位）。这是本里程碑发现的最隐蔽形态。

**修复**：加**前导触发词门**（`遵守/依照/依据/根据/按照/参照/符合/违反/适用/参见`
紧贴条号 → 判为引用）。**这一条不静默**：进 `pending_manual`。
回归：`test_wrapped_cross_reference_is_flagged_not_silent`。

**守门必须收窄，否则会吞掉真条款**（M2 自查发现的第二层风险）：名词短语
（`本合同`/`本条例`/`本办法`）能合法结束一个正常句子，收进触发词表会把**真条款**
误判成引用并凭空吞掉。现只收"不能单独收尾成句"的动词/介词。
回归：`test_noun_phrase_lead_does_not_eat_real_clause`（变异验证确认：加回名词短语该测试即红）。

### 2.3 后随引用限定（合法用法，须静默跳过）

`第三条 …维修责任由甲方承担，第五条规定的除外。` 里的"第五条"是**正确**的引用。
**修复**：后随门（`规定的除外/所列/所述/所指`）拦下；这类**静默跳过**，
不写进清单——否则每份合同都刷一屏噪音，反而淹没真正的错位项。
回归：`test_citation_with_exception_is_not_a_boundary`。

### 2.4 `第X条之一`（修订条文）未支持 → 重复条号

实测 `第一条之一` 被切成**两个 `第一条`**（`located` 均 True，看着成功），
`_locate()` 的单调递增会让重复条号**互相错配**。

**修复**：`之一`/`之二` 后缀并进同一个条号正则（后缀不并进去会被先匹配成裸条号）。
另加真重复条号（原文就写重了）的显式拦截 + 清单登记。
回归：`test_article_with_zhiyi_suffix_is_one_clause` /
`test_duplicate_clause_number_is_flagged_not_mismatched` /
`test_zhiyi_suffix_locate_is_monotonic`（负向）。

### 2.5 `（一）` 括号中文序号未支持

实测切不出任何条款，整体进 `pending_manual`（"未切分出任何条款"）。
这是"显式标注"的**正确**行为，但覆盖面应补：括号序号在合同里常用于"一、"下的分项，
切不出会让这些分项的正文全部落进上一条（**要素证据挂错条款**）。
**修复**：新增 `paren_index` 形态（`^[（(][一二三四五六七八九十]+[）)]`）。
回归：`test_paren_chinese_index_supported` / `test_paren_index_alone_is_supported`。

### 2.6 中文租期表述抽不到（**漏报**，且"一年半"会静默取错值）

| 输入 | 原实测 | 后果 |
|---|---|---|
| `租赁期限为半年。` | `value=None` | 保租房租期下限规则判 `unknown` 而非 `noncompliant`（**漏报**） |
| `租赁期限为一年半。` | **`1.00`** | 被通用"X 年"式吃成 1.00，**丢掉"半"**——静默取错值，比抽不到更危险 |
| `租赁期限为两年半。` | `None` | `两` 不在中文数字表里 |

**修复**：把"X年半/半年"匹配**前置**于通用式；补 `两` 的中文数字；
新增 `_cn_half_years()` 走独立分支（unit 记"年（中文表述）"）。
回归：`test_chinese_half_year_term_extracted` / `test_half_year_term_does_not_lose_the_half` /
`test_half_year_term_triggers_affordable_lower_bound`（**端到端**锁死下限违规不被降级为 unknown）。

### 2.7 抽取字段互不污染（复核项，非缺陷）

M1 遗留的复核项"`enterprise_filing_days` 会不会误抽到别的数字"——M2 实测：
`订立之日起 N 日内备案` / `订立之日起 N 个工作日内出租登记` / `营业执照之日起 N 日内`
三者的 evidence 各自独立，**无交叉污染**（四组探针全部确认）。

---

## 3. 解析层形态支持矩阵（M2 收尾实测，供 M3/M4 复核）

| 形态 | 输入 | 结果 | M2 新增？ |
|---|---|---|---|
| `第X条` 中文数字 | `第一条 …` | ✅ 切出 | M0 |
| `第X条` 阿拉伯数字 | `第1条 …` | ✅ 切出 | M0 |
| **`第X条之一/之二`** | `第一条之一 …` | ✅ 切出（单一不重复条号） | **M2** |
| 中文顿号索引 | `一、…` | ✅ 切出（`kind=cn_index`） | M0 |
| **括号中文序号** | `（一）…` | ✅ 切出（`kind=paren_index`） | **M2** |
| 阿拉伯点索引 | `1. …` | ✅ 切出（`kind=num_index`） | M0 |
| 逐字符空格（PDF 复制） | `第 一 条 …` | ✅ 折叠后切出 | M0 |
| CRLF | `\r\n` | ✅ 归一后切出 | M0 |
| **行内交叉引用** | `…遵守第五条…` | ✅ **不**切为边界，正文完整 | **M2** |
| **断行交叉引用** | `…遵守\n第五条…` | ✅ 跳过 + 进 `pending_manual` | **M2** |
| 后随引用限定 | `第五条规定的除外` | ✅ 跳过（静默，合法用法） | **M2** |
| **真重复条号** | 两个 `第一条` | ✅ 去重 + 进 `pending_manual` | **M2** |
| 非合同文本 | 一段说明文字 | ✅ 进 `pending_manual` | M0 |

**中文租期表述**（`extract.py`，M2 新增）：`半年`→0.50 / `一年半`→1.50 /
`两年半`→2.50 / `6 个月`→0.50（月→年换算，M0 已有）。

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
| K9 | **条款号由快照机器推导，禁手抄；只认行首条号** | `tools/gen_rulesets.py` `derive_clause()` | M1 补的"行首"限定：去掉会被交叉引用劫持（HANDOFF-M2 §2.1） |
| K10 | 零字面量门禁豁免阈值 = **≥10** 的规则数值 | `tools/check_literals.py` | 本项目政策数值多为个位数，阈值 100 会让 token 集为空 → **假绿**（M0 实测踩过） |
| K11 | 城市包**叠加**全国层（同名 rule_id 城市优先） | `engine/ruleset.py` | 去掉会让租期上限等全国规则漏判（M0 被 B2 抓出） |
| K12 | 主体未知 → `unknown`（**不是 skipped**） | `engine/checker.py` `_applicability()` | 改则等于把"没做"记成"不用做" |
| K13 | `quote` 断言按规则自己声明的 `source_id` 取快照（非规则包主快照） | `tools/gen_rulesets.py` `build_ruleset()` | 改回主快照会让配套办法的规则误判成"未挂原文" |
| K14 | `applies_if` 支持 `lease_kind` 维度（`affordable`/`ordinary`） | `engine/checker.py` `_applicability()` + 规则包 | 去掉则保租房专属规则会对普通租赁住房误判（应 skipped） |
| K15 | 数值规则的 `op` 含下限类（`>=`/`>`），措辞按方向分派 | `engine/checker.py` `_limit_words()` | 统一写"上限"会把下限义务说反 |
| K16 | 未观测时仍挂 `limit`（`unknown` 不等于规则无口径） | `engine/checker.py` `_check_numeric()` | 去掉则报告显示 `<= —`，读者误读为无口径 |
| K17 | 锚点门在加载侧二次拦截：`clause`/`quote`/`source_id` 缺一即不生效（题面模块②硬约束） | `engine/ruleset.py` `effective_ruleset()` | 去掉则"缺锚点的规则不得被引擎加载生效"只剩生成器单点保障 |
| K18 | `applies_if.party` 必须回读来源的适用范围条（不能只看被引条款） | 规则包各条 + `docs/技术报告.md` | 配套办法第二条限定"住房租赁企业"，误标 `any` 会让个人房东被判 noncompliant |
| **K19** | **条号只认"定义位"**（行首，或同句内紧跟句末标点）——解析层对应 K9 | `src/rca/parser/clauses.py` `_is_definition_position()` | 去掉则正文交叉引用被当边界，上一条被劈开并凭空造出不存在条款（M2 §2.1） |
| **K20** | **引用前导门只收"不能单独收尾成句"的动词/介词**（不收 `本合同`/`本条例` 等名词短语） | `src/rca/parser/clauses.py` `_CITATION_LEAD` | 收进名词短语会把**真条款**当引用吞掉（M2 §2.2 自查） |
| **K21** | **断行引用不静默**：进 `pending_manual`；后随引用限定则静默跳过 | `src/rca/parser/clauses.py` | 静默则"看着成功、实则错位"（`located=True`）被当成功；全不静默则清单刷屏淹没真错位 |
| **K22** | **`之一` 后缀并进条号正则**；重复条号去重并登记 | `src/rca/parser/clauses.py` `_PATTERNS` | 后缀不并进去会被先匹配成裸条号 → 重复条号 → `_locate` 互相错配（M2 §2.4） |
| **K23** | **中文租期表述前置匹配**（`X年半`/`半年` 先于通用 `X 年`）；中文数字表含 `两` | `src/rca/parser/extract.py` `_cn_half_years()` | 不前置则"一年半"被吃成 1.00（静默取错值）；漏抽让保租房下限规则漏报（M2 §2.6） |

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
- **基准/测试跑得快**（bench 0.03s、163 项测试约 4s）：每改一处都该跑全量。
- **`rca report` 在演示样例上退出码是 1**（检出不符合，既定语义）——用 `&&` 串联命令会在此断链，
  脚本里请用 `;` 或显式判断。
- **变异验证要清 `__pycache__`**：改源码后不清旧 `.pyc`，pytest 可能仍跑旧字节码，
  变异结果会假绿（M2 实测踩过，脚本里已加清理）。
- **探针脚本别用 `\s` 裸字符串**：`py -3.12` 对无效转义序列发 `SyntaxWarning`（M2 实测），
  写正则一律用 raw string。

---

## 6. DoD（M3 出口判据，逐项勾选）

题面模块②③的原文要求：模块②"城市标识 → versioned ruleset（数值规则 + 法条原文锚点）；
缺锚点的规则不得被引擎加载生效"；模块③"条款序列 + 规则包 → 逐条判定（符合/不符合/缺失/
无法判定）；判定回指锚点 ID 与原文；**同版本 + 同输入 = 同输出**"。

M0 已把引擎骨架建好（五态、双重门控、作用域、全国层叠加、义务分栏），
M1 补齐了规则包数据与锚点门。**M3 的实质是"把模块②③的确定性纪律逐条证成并锁进测试"**，
而非从零实现——先复核既有实现是否真满足，再补缺口。

- [ ] **同版本 + 同输入 = 同输出**有**显式回归**（现仅报告层有逐字节测试；判定层须加：
      同输入连跑 N 次，findings 序列与字段逐字段一致）
- [ ] **判定回指锚点 ID 与原文**：每条 finding 的 `rule_id`/`clause`/`quote`/`source_id`
      必须能在规则包中解析到，且 `quote` 逐字在对应快照中（现为数据侧断言，须加到**结果侧**：
      对 `rca check --json` 的每条 finding 反向查规则包）
- [ ] **城市差异包机制**：京/沪同一条义务的不同口径能各自命中（现 B2 已覆盖部分；
      须确认"同一条规则在两城判出不同结果"有显式用例，而非只靠全国层）
- [ ] **versioned ruleset 可追溯**：`ruleset_version` 进报告且可从规则包 manifest 复算
      （现报告已显示版本；须加断言"版本号 == manifest 推导值"）
- [ ] **缺锚点规则不得加载生效**：K17 已在加载侧拦截（M1 已闭环，M3 复核确认不回归）
- [ ] **判定五态语义**：`unknown`（没看到）与 `not_assessed`（没检查过）在 CLI/报告
      两条出口都可区分（现 `overall_status` + `status_counts` 已有；须确认 CLI JSON 也带计数）
- [ ] **规则包覆盖登记**：`rules --city X` 输出的覆盖分子/分母与规则包 manifest 一致
- [ ] `py -3.12 -X utf8 -m pytest -q` **双解释器**全绿（计数同步进 README）
- [ ] `rca bench` 三套件达标（exit 0），B2 误报 0
- [ ] `gen_rulesets.py --check` → `RULESETS_FROZEN_OK`（M3 若扩规则须重生成并同步 README 计数）
- [ ] `gen_samples.py --check` → `SAMPLES_FROZEN_OK`
- [ ] `check_literals.py` + `--selftest` 均 exit 0
- [ ] `audit_desensitize.py selftest` + `tracked` 均 exit 0（HARD 0）
- [ ] `plan/00` 里程碑表 M3 状态回写 ✅
- [ ] **本对话内写完 `plan/HANDOFF-M4.md`**（硬约束：不写不许结束对话）

**诚实口径**：M0–M5 未接远端，一切 CI 类判据写"**本地等价校验**（未接远端，CI 待首推验证）"。
**未推送 = 未跑 CI**，M6 首推后据实补记真实 run id。

---

## 7. 关键命令速查

```bash
# 验证（M3 每改一处都跑）
py -3.12 -X utf8 -m pytest -q                         # 163 项（双解释器各跑一遍）
py -3.12 -X utf8 -m rca.cli bench                     # 三套件 → BENCH_OK
py -3.12 -X utf8 tools/check_literals.py --selftest   # 门禁自检
py -3.12 -X utf8 tools/audit_desensitize.py tracked   # 脱敏（HARD 0）

# 数据（改 SPECS / 样例后按序执行）
py -3.12 -X utf8 tools/gen_rulesets.py                # 生成规则包
py -3.12 -X utf8 tools/gen_rulesets.py --check        # → RULESETS_FROZEN_OK
py -3.12 -X utf8 tools/gen_samples.py                 # 生成样例
py -3.12 -X utf8 tools/gen_samples.py --check         # → SAMPLES_FROZEN_OK
py -3.12 -X utf8 tools/fetch_sources.py --check       # 快照冻结校验

# 手工试用（引擎改动后重点看这几条）
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京 --json
py -3.12 -X utf8 -m rca.cli rules --city 上海 --json
py -3.12 -X utf8 -m rca.cli scan --dir data/samples --city 北京
py -3.12 -X utf8 -m rca.cli report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep
```

---

## 8. 下一棒启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务
```

**注意**：入库的 HANDOFF 内一律写**相对路径**（`plan/HANDOFF-M3.md`），
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
| R7 | 样例增至 10 份后，B1 分母 90、B2 分母 17、B3 分母 14 | 后续改动须同步 README 的评测表与 `tests/` 里任何写死计数的断言 |
| R8 | 配套办法来源目前只被 2 条规则引用 | 属"够用"而非"穷尽"；办法里还有押金退还 3 工作日、账户公示等可抽条目，M3/M4 视需要扩 |
| R9 | 全国层只有 1 条数值规则（705） | 707/704/721 本质是定性/补充规则，无阈值——**不是遗漏**，`test_m1_coverage_floors` 已按此口径写死 |
| R10 | 配套办法的主体限定取"enterprise"而非"转租业务企业" | 原文限定的是"承租他人住房从事**转租业务**的住房租赁企业"；本项目主体识别只分 enterprise/individual（不判是否转租），故 escrow 两条对**所有**企业主体生效，比原文宽一档。属**已知保守偏差**：宁可对企业多提示，不可对个人误判。若 M3/M4 引入"是否转租"维度，须回来收紧 |
| **R11** | **解析层新增守门有"吞真条款"风险**（前导门收词过宽会把真条款当引用） | M2 已收窄到"不能单独收尾成句"的动词/介词（K20），并加负向测试。**后续若扩触发词表，必须同步加负向测试**（`test_noun_phrase_lead_does_not_eat_real_clause` 是模板） |
| **R12** | **`（一）` 括号序号与 `一、` 父级序号并列切出，层级关系未表达** | 现只切平铺序列（`kind` 区分形态），不建树。要素证据按 span 归属，平铺不影响归属正确性；若 M3/M4 需要"某分项属于哪一条"的层级语义，须扩 `Clause` 结构（**动模型前先看 K2 连锁**） |
| **R13** | **中文租期只覆盖"年/月/年半/半年"，未覆盖"X个月零Y天"等复合表述** | 合同里极罕见；若实测遇到，按 K23 的形态补进 `_cn_half_years()` 同层（前置匹配），并加端到端测试 |
| **R14** | **解析层变异验证脚本在 `_scratch/`（不入仓）** | 变异验证结论（`ALL_GUARDS_EFFECTIVE`）已写进本文件；若要把变异验证常态化，M4 可考虑把它提成 `tools/` 下的守门（须先评估运行时长与跨解释器稳定性） |
