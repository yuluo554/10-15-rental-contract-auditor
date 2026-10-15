# HANDOFF-M1 — 数据先行（里程碑交接快照）

> 上一棒：M0 计划与骨架（2026-10-15 完成，commit `2856c44`）
> 下一棒目标：**M1 数据先行**——京/沪条例全文逐条抽取出数值规则+原文锚点（题面模块②）
> 本文件用法（新对话启动）：`/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务`

---

## 1. 当前进度（M0 已完成，证据位置）

| 项 | 状态 | 证据 |
|---|---|---|
| plan/00–06 定稿 | ✅ | `plan/00`–`plan/06` |
| 可运行骨架 | ✅ | `src/rca/`（解析/引擎/报告/基准/CLI/GUI/packaging） |
| 数据底座入仓 | ✅ | `data/knowledge/raw/` 四份官方快照 + `data/knowledge/MANIFEST.json` |
| 规则包（三份） | ✅ | `data/rules/ruleset-{cn,bj,sh}.json`（生成器冻结产物） |
| 合成样例 | ✅ | `data/samples/samples.json`（8 份）+ `demo-contract-bj.txt` |
| 守门（零字面量/脱敏/EOL/冻结/CI/README） | ✅ | `tools/` + `tests/` |
| 测试全绿 | ✅ | 132 项，双解释器（3.8.8 / 3.12.10） |
| CI workflow | ✅ 已写 | `.github/workflows/ci.yml`（**未接远端，CI 待首推验证**） |

**M0 已实现的核心能力**（M1 在其上扩数据）：

- 判定五态：`compliant` / `noncompliant` / `skipped` / `unknown` / `not_assessed`
- 双重门控：`status`（数值，唯一门控）+ `clause_status`（条款号，只做可证性）
- 作用域门控：`calc` / `check` / `quota`；quota 类进"条件触发栏"不参与判定
- 全国层叠加：城市包自动叠加民法典规则（同名 rule_id 城市优先）
- 义务类型分栏：`standing_obligation` / `periodic_obligation` / `conditional_institution`
- 报告双轨：Markdown + XLSX，同输入逐字节一致；溯源完整性导出前断言

### M0 本地等价校验记录（未接远端，CI 待首推验证）

**可本机实跑的通路（逐条实测，取真退出码）**：

| 通路 | 命令 | 结果 |
|---|---|---|
| 全量测试 ×2 解释器 | `py -3.12 -m pytest -q` / `py -3.8 -m pytest -q` | 132 项全绿，exit 0 |
| 快照冻结 | `tools/fetch_sources.py --check` | exit 0 |
| 规则包冻结 | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK` |
| 样例冻结 | `tools/gen_samples.py --check` | `SAMPLES_FROZEN_OK` |
| 零字面量门禁 + 自检 | `tools/check_literals.py` / `--selftest` | exit 0 / `LITERAL_GATE_SELFTEST_OK` |
| 脱敏审计自检 + 已跟踪 + 历史 | `audit_desensitize.py selftest` / `tracked` / `history` | exit 0（HARD 0，历史探活通过） |
| 基准三套件 | `rca bench` | `BENCH_OK`（B1 72/72、B2 8/8 误报 0、B3 10/10） |
| CLI 退出码契约 | `check`(1) / `rules`(0) / 缺文件(2) / 未知城市(2) / `bench --only NOPE`(2) | 逐条符合明示语义 |
| 冻结态自检（源码态） | `rca selftest --out` | exit 0；`frozen=false`、`data_dir_in_dist=null`（非冻结态不误判） |
| **干净环境**（`git archive` 树 + 全新 venv 照 README 装 `.[dev,gui]`） | `pytest -q` + 上述工具链 | **132 项全绿，收集数与 dev 完全一致** |

**不可本机实跑的通路（显式标注"待首推验证"）**：CI 矩阵的环境差异
（cp1252 编码、ubuntu 缺 Qt 系统库、actions/checkout 行为）。
M0 已在开发期前置 `eol=lf` / `fetch-depth: 0` / extras 齐 / 编码三层加固，
但**不保证首跑全绿**——M6 须预算"多轮诊断"。

**干净环境实测抓到的缺陷（已修 + 已加回归）**：`git archive` 导出的树没有 `.git`，
脱敏审计退回文件系统遍历后扫到就地建的 `.venv/Lib/site-packages/**`，
第三方包自带邮箱成片误报（48 项假 HARD）。修复 = 按**特征**（`pyvenv.cfg` /
`Scripts/activate`）剪枝，不按名字；回归测试故意用非 `.venv` 名验证按特征判定。

---

## 2. M1 待办（按优先级）

题面模块②要求："规则包中每条数值规则必须携带来源文件、条款号、法条原文逐字引用与查证状态（✅/⬜）；缺锚点的规则不得被引擎加载生效。"

M0 已把**机制**建好（生成器 + 逐字断言 + 门控），M1 要把它**填满**：

1. **扩充北京规则包**（`tools/gen_rulesets.py` 的 `SPECS["bj"]["rules"]`）：
   - 补齐 `data/README.md` 承诺的 6 条数值规则（现已有 5 条 + 1 条 quota）
   - 复核 `BJ-CONTRACT-ELEMENT-DEPOSIT`（第十四条）的要素清单是否该扩
2. **扩充上海规则包**：
   - 补齐罚则（5 万–20 万）、骗保 5 年禁申请保障房（`effect=conditional_institution`，走 quota 栏）
   - 保租房租赁期限不得少于一年（第三十七条）
3. **扩充全国层**：
   - 民法典第七百零七条（租期六个月以上应采书面形式）
   - 复核 721 条法定补充规则的判定形态（现为 `rent_pay_period_declared` 定性）
4. **新增北京配套办法来源**：`SRC-BJ-DEPOSIT-ESCROW`（京建法〔2024〕8 号）已在台账与规则包 `sources` 里，
   但**尚无规则条目引用它**——M1 补 1–2 条托管/监管规则，让该来源真正被用上
5. **扩展项（非门槛）**：其他城市条例包（须先走 `plan/02` §1 的原文直连预检流程）

**每加一条规则的固定动作**（缺一即打挂基准）：
1. 在 `SPECS` 里加条目：`anchor`（纯文本短语，**不带条款号前缀**）+ `quote`（逐字原文）+ `applies_if` + `effect`
2. `py -3.12 -X utf8 tools/gen_rulesets.py`（生成；`quote` 不在快照中即报错）
3. `py -3.12 -X utf8 tools/gen_rulesets.py --check`（`RULESETS_FROZEN_OK`）
4. **若新规则会被样例命中** → 同步改 `tools/gen_samples.py` 的 `expect` 推导，重跑 `gen_samples.py`
5. `py -3.12 -X utf8 -m rca.cli bench`（三套件必须仍达标）
6. `py -3.12 -X utf8 -m pytest -q`（132 项必须仍全绿）

---

## 3. 既定口径清单（K 清单——动了会打挂基准，改前先对照）

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
| K9 | **条款号由快照机器推导，禁手抄** | `tools/gen_rulesets.py` `derive_clause()` | 手抄会引入不可复现漂移（M0 实测过） |
| K10 | 零字面量门禁豁免阈值 = **≥10** 的规则数值 | `tools/check_literals.py` | 本项目政策数值多为个位数，阈值 100 会让 token 集为空 → **假绿**（M0 实测踩过） |
| K11 | 城市包**叠加**全国层（同名 rule_id 城市优先） | `engine/ruleset.py` | 去掉会让租期上限等全国规则漏判（M0 被 B2 抓出） |
| K12 | 主体未知 → `unknown`（**不是 skipped**） | `engine/checker.py` `_applicability()` | 改则等于把"没做"记成"不用做" |

---

## 4. 本机环境坑（全部实测过）

- **`python` 不在 PATH**（商店占位符）：一律用 `py -3.12` / `py -3.8`。
- **Git Bash 的 `/tmp` 与 Windows Python 不互通**：临时文件用工作区相对路径 `_scratch/`（已 gitignore）。
- **跑命令带 `-X utf8`**（中文控制台编码）；但**代码里的编码缺口会被它掩盖**——
  故入口有 `_ensure_utf8_stdio()`，且 CI 设 `PYTHONUTF8=1`。
- **`Path.write_text(newline=)` 是 Python 3.10+ 参数**：3.8 通道直接 TypeError（实测踩过）。
  生成器一律 `write_bytes`。
- **本机双解释器都可用**：`py -0` 列出 3.8.8-64 与 3.12-64，两者都装了 pytest + PySide6 + rca（editable）。
- **`py -3.12 -m pip install -e .` 会写 `src/rca.egg-info/`**：已被 .gitignore 覆盖。
- **基准/测试跑得快**（bench 0.02s、132 项测试约 10s）：每改一处都该跑全量。

---

## 5. DoD（M1 出口判据，逐项勾选）

- [ ] 北京规则包 ≥6 条数值规则，每条挂 `quote` 且**逐字出现在官方快照中**
- [ ] 上海规则包 ≥5 条数值规则（含罚则/保租房条款），同样逐字断言通过
- [ ] 全国层 ≥3 条规则（704/705/721 已就位，M1 复核 + 补 707 条可选）
- [ ] `SRC-BJ-DEPOSIT-ESCROW`（京建法〔2024〕8 号）至少被 1 条规则引用
- [ ] `gen_rulesets.py --check` → `RULESETS_FROZEN_OK`
- [ ] `gen_samples.py --check` → `SAMPLES_FROZEN_OK`（若改了 expect 须重生成）
- [ ] `rca bench` 三套件达标（exit 0）
- [ ] `pytest -q` 全绿（**双解释器**：`py -3.12` 与 `py -3.8`）
- [ ] `check_literals.py` + `--selftest` 均 exit 0
- [ ] `audit_desensitize.py selftest` + `tracked` 均 exit 0（HARD 0）
- [ ] `plan/00` 里程碑表 M1 状态回写 ✅
- [ ] **本对话内写完 `plan/HANDOFF-M2.md`**（硬约束：不写不许结束对话）

**诚实口径**：M0–M5 未接远端，一切 CI 类判据写"**本地等价校验**（未接远端，CI 待首推验证）"。
**未推送 = 未跑 CI**，M6 首推后据实补记真实 run id。

---

## 6. 关键命令速查

```bash
# 数据（改 SPECS 后按序执行）
py -3.12 -X utf8 tools/fetch_sources.py --check       # 快照冻结校验
py -3.12 -X utf8 tools/gen_rulesets.py                # 生成规则包
py -3.12 -X utf8 tools/gen_rulesets.py --check        # → RULESETS_FROZEN_OK
py -3.12 -X utf8 tools/gen_samples.py --check         # → SAMPLES_FROZEN_OK

# 验证
py -3.12 -X utf8 -m pytest -q                         # 132 项（双解释器各跑一遍）
py -3.12 -X utf8 -m rca.cli bench                     # 三套件 → BENCH_OK
py -3.12 -X utf8 tools/check_literals.py --selftest   # 门禁自检
py -3.12 -X utf8 tools/audit_desensitize.py tracked   # 脱敏（HARD 0）

# 手工试用
py -3.12 -X utf8 -m rca.cli check --input data/samples/demo-contract-bj.txt --city 北京
py -3.12 -X utf8 -m rca.cli rules --city 北京 --json
py -3.12 -X utf8 -m rca.cli report --input data/samples/demo-contract-bj.txt --city 北京 --out _scratch/rep
```

---

## 7. 下一棒启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务
```

**注意**：入库的 HANDOFF 内一律写**相对路径**（`plan/HANDOFF-M1.md`），
绝对路径只出现在用户侧的 `/goal` 启动命令里（否则发布期脱敏扫描必中）。

---

## 8. 遗留与风险

| # | 事项 | 处置 |
|---|---|---|
| R1 | **CI 从未真跑过**（无远端） | M6 首推 = 全项目首次 CI，须预算"多轮诊断"；M0 已在开发期前置了 eol=lf / fetch-depth / extras / 编码三层，但**不能保证首跑全绿** |
| R2 | 提交邮箱是**真实 QQ 邮箱**（本机 git 全局配置） | M6 发布前必须改写为 GitHub noreply（首推前是零消费者窗口，`git filter-repo --email-callback`）。`audit_desensitize.py messages` 会如实报 HARD |
| R3 | `_scratch/` 是验证期草稿目录 | 已 gitignore；**绝不入仓** |
| R4 | GUI 只做了骨架（两个页签） | M5 交付里程碑再扩；分层守门已就位 |
| R5 | 打包 spec 已写但**从未构建过** | M5 实构建时会暴露 spec 问题（PyInstaller 版本差异等），届时按实况修 |
| R6 | 规则包数值覆盖仍偏少（京 7 / 沪 4 / 全国 3） | M1 的主要任务 |
