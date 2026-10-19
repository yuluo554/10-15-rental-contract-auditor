# 房屋租赁合同审计器（租客视角）

[![CI](https://github.com/yuluo554/10-15-rental-contract-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/yuluo554/10-15-rental-contract-auditor/actions/workflows/ci.yml)

**状态**：`v0.1.0` 已发布（[Release](https://github.com/yuluo554/10-15-rental-contract-auditor/releases/tag/v0.1.0)）；
`v0.1.1` 待发布（修掉"非 editable 安装读不到数据"并新增装态门禁）。

CI：`test`（windows / ubuntu，py3.12）+ `install-smoke`（非 editable 安装冒烟）
+ `package`（真构建 + 产物级验收）。
Windows x64 免安装发行包见 Release 附件（CLI / GUI 双入口）。

> **把分散在民法典与城市条例里的数值规则，做成可核验的合同体检；每条判定挂法条原文锚点。**
>
> 租客不是律师。押金上限、租金收取上限、备案期限、退还期限这些"硬数字"规则，
> 分散在《民法典》租赁编与各城市地方性法规里，普通人签合同前几乎没有逐条比对的手段。
> 通用大模型"问一句"得到的回答不挂法条原文、无版本化口径、不可复现——换个模型问，答案会漂移。

**本项目输出为辅助参考的合同体检结果，不构成法律意见。纯本地零上传。**

---

## 特性

- **城市差异包（versioned ruleset）**：京 / 沪两套地方规则 + 全国层（民法典），
  每条数值规则挂来源文件、条款号、**法条原文逐字引用**与核对状态。
- **法条原文锚点体系**：条款号由官方快照**机器推导**（不手抄），
  每条 `quote` 在生成时断言"逐字出现在官方快照中"。
- **判定语义不虚高**：五态判定（符合 / 不符合 / 不适用 / 无法判定 / 未评估），
  区分"没查出问题"与"没检查过"；主体未知时判"无法判定"而**不是**"不适用"。
- **义务类型分栏**：监管裁量条款（"政府**可以**采取价格干预"）独立成栏，
  绝不写成相对人的无条件义务。
- **可复现判定**：同规则包版本 + 同输入 = 同输出；报告人读（Markdown）+ 机读（XLSX）双轨，
  两种产物**逐字节可复现**（自写最小 OOXML writer，不引第三方保字节确定）。
- **离线零上传**：CLI 与桌面端均无出网调用，报告断网可开（无外链）。

## 架构

```mermaid
flowchart LR
    A[合同纯文本] --> B[条款切分<br/>规则优先 + 回定位断言]
    B --> C[要素抽取<br/>正则 + 证据逐字校验]
    C --> D[合同卡片<br/>统一中间表示]
    E[城市规则包<br/>versioned ruleset] --> F[门控<br/>status 分作用域]
    F --> G[判定引擎<br/>零政策字面量]
    D --> G
    G --> H[判定结果<br/>五态 + 义务分栏]
    H --> I[报告<br/>单一渲染源]
    I --> J[Markdown 人读]
    I --> K[XLSX 机读]
    L[官方快照<br/>民法典/京/沪] -.生成时逐字断言.-> E
```

## 快速开始

```bash
# 需要 Python 3.12+
python -m venv .venv
# Windows: .venv\Scripts\activate     POSIX: source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,gui]"
```

> 安装行 `.[dev,gui]` 同时覆盖测试期依赖（pytest / PyYAML）与 GUI（PySide6）。
> **测试面 = 安装面**：测试套件真 import 的库都在这一条通路的 extras 里。

### 跑一次合同体检

```bash
# 单件体检（--city 取 北京 / 上海 / 全国）
python -m rca.cli check --input src/rca/data/samples/demo-contract-bj.txt --city 北京

# 机读输出
python -m rca.cli check --input src/rca/data/samples/demo-contract-bj.txt --city 北京 --json

# 导出报告（Markdown + XLSX 双轨，同输入逐字节一致）
python -m rca.cli report --input src/rca/data/samples/demo-contract-bj.txt --city 北京 --out out/

# 查看规则包与门控状态
python -m rca.cli rules --city 北京

# 内置基准（三套件一键复跑）
python -m rca.cli bench

# 桌面界面（需 [gui]）
python -m rca.cli gui
```

### 退出码语义

| 退出码 | 含义 |
|---|---|
| 0 | 完成（无论是否检出不符合） |
| 1 | 检出**不符合**（判定类工具的既定语义，**不是失败**） |
| 2 | 输入不可用 / 用法错误 / 参数错误 |
| 3 | 缺可选依赖（如 GUI 的 PySide6） |

### 桌面 exe 打包与验收（双入口）

需要 Python 3.12（PyInstaller ≥6；5.x 扫 PySide6 字节码会确定性崩溃）：

```bash
# 打双 exe（GUI console=False + CLI console=True）→ dist/rca-cli、dist/rca-gui
python -m PyInstaller --noconfirm --clean tools/rca.spec

# 产物级验收（中立目录 + 剥离 PATH，逐项断言）
python tools/verify_package.py --dist dist/rca-cli
python tools/verify_package.py --dist dist/rca-gui --gui-selftest
```

**两个 exe 的依赖是分档的**：PySide6 **只进 GUI 目标**；CLI 目标还排除了
出网栈（`ssl`/`_ssl`/`_socket`/`_hashlib`）。所以 CLI 发行包约 12MB、
**不含任何能发起 TLS 的组件**——"纯本地零上传"因此不只是代码声明，
而是**产物级可核验**（`verify_package.py` 会扫产物里的出网组件）。

**冻结入口是独立的薄模块**（`rca/cli_entry.py` / `rca/gui_entry.py`，绝对导入）：
PyInstaller 把入口脚本当顶层 `__main__` 执行，包内相对导入必然
`attempted relative import with no known parent package`。

**窗口版 exe 怎么脚本化验收**：窗口版 stdout 不接终端，故 `--selftest <文件>`
是唯一通路（结论写文件、退出码携带成败）：

```bash
rca-cli.exe --selftest out.json     # 等价于 rca selftest --out out.json
rca-gui.exe --selftest out.json     # 走 CLI 的同一份实现（双入口结论同源）
```

`verify_package.py` 至少核这几件事：内嵌数据逐份 sha256 与仓库冻结件一致
（防"打进包的是旧数据"）、`data_dir_in_dist: true`（防 exe 回头读开发机仓库）、
冻结态 `check` 的结论与退出码同源码运行**一致**、CLI 产物无出网组件、
GUI exe 拒绝未知参数（否则会静默挂进事件循环）。

## 评测

基准三套件，零 API 依赖、离线可复跑（`python -m rca.cli bench`）：

| 套件 | 类型 | 指标 | 结果 |
|---|---|---|---|
| B1 | 样本驱动 | 要素抽取**字段级 P/R/F1** | F1 = 1.0000（P = 1.0000，R = 1.0000），90/90 |
| B2 | 样本驱动 | 端到端判定命中率（植入真值**全量**对账） | 150/150 = 1.0000，误报 0 |
| B3 | **规则驱动**（不读真值库） | 边界断言通过率 | 14/14 = 1.0000 |

**为什么分两层**：样本驱动证明"引擎在这些样本上对"，但**样本没覆盖的端点它证明不了**；
B3 从规则表推导端点做 ±精度邻域断言，专门补这个缺口。

**B1 的 P/R/F1 是真算的**：真值侧逐样例登记"应有值的字段 → 期望取值"与"应观测不到的字段"
（`expect_fields` / `expect_absent_fields`），由生成器按合同入参独立推导、**不调用引擎抽取函数**——
否则引擎抽错时期望跟着一起错，探活永远绿。TP = 期望有值且引擎取到**同一取值**；
FP = 期望 absent 却抽到值，或取值不符；FN = 期望有值却抽不到。

**B2 的分母是真值登记的每条规则**（`expect ∪ also_expect`）：只算"非 pass 集合"会漏掉一整类错误——
真值登记 `compliant` / `skipped` / `reference`、观测却是别的 pass 侧状态时，两侧都不在非 pass 集合里，
**恒不报**（`also_expect` 会沦为"登记了但从不校验"的死数据）。

**覆盖登记三件套**：规则包 manifest 逐形态登记 **"规则条数（分母）/ 真值库采样条数（分子）/ 采样清单"**，
并声明"抽样覆盖、非逐条穷举"；`rules --city X` 与导出报告都可见。**只写分母就是假覆盖**——
本项目此前连分子都没有，M4 补齐。

**门槛随规则包下发**（数据非代码，见 `src/rca/data/rules/ruleset-*.json` 的 `benchmark_thresholds`），
基准层只读、缺失即报配置错误——调门槛不改代码。

**每套件配可证伪探活**：注入缺陷（篡改真值 / 注入坏引用规则 / 改规则边界）后，
**`run_benchmarks` 必须真的返回非 0**（端到端，不是只断言对账函数返回非空），
防"基准全绿只是因为它什么都没查"。**空分母不冒充通过**：某形态零采样件 → 未达标。

## 目录

```
src/rca/
  cli.py           CLI 入口（退出码契约）
  model.py         统一中间表示（条款/卡片/判定）
  parser/          条款切分 + 要素抽取（规则优先）
  engine/          规则包门控 + 判定引擎 + 编排层
  report/          单一渲染源 + Markdown + 自写 OOXML writer
  benchmark/       三套件基准 + 真值对账单一实现源
  gui/             PySide6 界面（只消费引擎 API，零判定逻辑）
  cli_entry.py     冻结态 CLI 入口（绝对导入的薄入口，供 PyInstaller）
  gui_entry.py     冻结态 GUI 入口（含 `--selftest` 脚本化验收通路）
  packaging.py     打包白名单单一事实源
src/rca/data/     随包数据（**进 wheel**，装态直接可用）
  rules/           城市规则包（生成器冻结产物，禁手改）
  samples/         合成合同样例 + 植入真值
  knowledge/MANIFEST.json  快照台账（URL/抓取日/sha256）
data/knowledge/raw/ 官方全文快照（字节冻结，.gitattributes 标 -text）——版权红线，**不随包**
tools/             抓取/生成/门禁/审计/打包脚本
plan/              计划文档 00–06 与跨会话交接快照
tests/             291 项测试（含全部守门）
```

## 数据来源

| 依据 | 渠道 | 状态 |
|---|---|---|
| 《中华人民共和国民法典》租赁编 | 最高人民法院官网 | ✅ 静态 HTML 全文 |
| 《北京市住房租赁条例》 | 北京市人大法规库 | ✅ 静态 HTML 全文 |
| 《上海市住房租赁条例》 | 上海市人民政府官网 | ✅ 静态 HTML 全文 |
| 《北京市住房租赁押金托管和租金监管暂行办法》 | 北京市住建委官网 | ✅ 静态 HTML 全文 |

详细查证记录、快照 sha256 与合成数据纪律见 [`data/README.md`](data/README.md)；
数据底座预检（HTTP 200 + 字节数 + 汉字数 + 结构计数）见 [`plan/02-数据底座说明.md`](plan/02-数据底座说明.md)。

## 已知环境问题

- **`py` 启动器会无视 venv**（Windows）：venv 段落一律用 `python -m pip ...`，
  不要用 `py -m pip ...`（后者装到系统 Python）。
- **打 GUI 的 PyInstaller 必须 ≥6**：5.x 扫描 PySide6 字节码会确定性崩溃
  （`Instruction object is not iterable`）。发布构建固定在装了 PyInstaller 6 的 3.12 通道。
- **`Path.write_text(newline=)` 是 Python 3.10+ 参数**：本项目生成器一律走
  `write_bytes`（同时保证跨平台逐字节一致，也是 EOL 门要求的形态）。
- **offscreen 平台拿不到系统字体**：中文会渲染成方块，GUI 启动时按环境变量
  推导字体目录显式注册（不写死盘符）。

## 限制（请先读这一节）

- **不构成法律意见**：输出为辅助参考的体检结果，正式口径以官方发布法规原文为准。
- **首期仅京/沪两市** + 全国层（民法典）。其他城市条例包属扩展项，
  须先完成该条例的原文直连查证后方可入包。
- **规则覆盖范围有限**：仅覆盖已在规则包中登记且"数值核对状态 = 已核对"的条款；
  未覆盖的规则**不会被静默忽略**——报告里"本次未启用的规则"一节显式列出。
- **解析面向中文合同的主要表述形态**：极端排版（图片型 PDF、扫描件）不在首期范围。
- **不接入在线法规数据库实时更新**：国家法律法规数据库（flk.npc.gov.cn）为
  JS 渲染 SPA，程序化直连实测不可行，本项目不依赖它。
- **首期不做 Word 回写**（扩展项）。

## 开发

```bash
python -m pytest -q                    # 全量测试（含全部守门）
python tools/gen_rulesets.py --check    # 规则包冻结校验
python tools/gen_samples.py --check     # 样例冻结校验
python tools/check_literals.py          # 零政策字面量门禁
python tools/audit_desensitize.py all   # 脱敏审计

# 打包与产物验收（需 3.12 + PyInstaller ≥6）
python -m PyInstaller --noconfirm --clean tools/rca.spec
python tools/verify_package.py --dist dist/rca-cli
python tools/verify_package.py --dist dist/rca-gui --gui-selftest
```

方法论：本项目按 `ai-tool-project-sprint` 冲刺方法论组织——计划先行（`plan/`）、
数据先行（官方快照 + 冻结规则包）、判定语义不虚高、内置可证伪基准、脱敏发布。

## 许可

MIT，见 [LICENSE](LICENSE)。

## 免责声明

**本项目输出为辅助参考的合同体检结果，不构成法律意见。**
所有报告页面与导出文件均携带本声明。如对判定结果有异议，请以官方发布的法规原文为准。
