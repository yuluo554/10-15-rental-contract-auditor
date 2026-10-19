# RELEASE-v0.1.1 — 发布留档（房屋租赁合同审计器）

> 发布日 2026-10-20 ｜ 形态：**patch 版本**，修实质缺陷 + 补门禁 + 元数据现代化
> 上一版：`v0.1.0`（2026-10-15，见 `plan/RELEASE-M6.md`）——**其 tag 与 Release 保留不动**
> 产物 sha256：`plan/DIST-sha256-v0.1.1.txt`

---

## 1. 这一版改了什么（一句话）

**修掉"非 editable 安装读不到数据"**：数据原在仓库根 `data/`（包外）且 `pyproject.toml`
无 `package-data`，wheel 里一个数据文件都没有——`pip install <wheel>` 后
`rca rules` / `rca bench` 直接 exit 2。CI 四个 job 全走 `pip install -e`，故**本地与 CI 一直全绿**。

同时补上能拦住它的门禁、把 license 元数据现代化、并让台账不再引用本机路径。

完整技术记录见 `plan/HANDOFF-M7.md` §8 与 `plan/RELEASE-M6.md` §10。

---

## 2. 发布物

| 项 | 值 |
|---|---|
| tag | `v0.1.1`（annotated，指向本版收尾提交） |
| Release | `https://github.com/yuluo554/10-15-rental-contract-auditor/releases/tag/v0.1.1`（Latest） |
| 附件 | `rca-cli-win64.zip` 11,928,681 B sha256 `92ea4a61…90d1`；`rca-gui-win64.zip` 116,266,995 B sha256 `84935740…54cc`——**附件名全 ASCII** |
| 版本口径 | `pyproject.toml` = `rca/__init__.py` = `rca --version` = tag = **0.1.1** |
| 构建基线 | commit `40610e1`；Windows x64 / Python 3.12.10 / PyInstaller 6.22.3 / PySide6 6.6.3.1 |

**与 v0.1.0 的产物差异是预期的**（不是回归）：数据布局从仓库根迁到包内、
解释器 floor 3.8→3.12、`gui` 去掉 `PySide6<6.7` 上限——三处都会改变字节。
**不要**拿两个版本的台账互相对账。

---

## 3. 这一版的改动清单

### 3.1 缺陷修复（D1）

| # | 改动 |
|---|---|
| 1 | `data/rules`、`data/samples`、`data/knowledge/MANIFEST.json` → `src/rca/data/`（`git mv`，**字节未变**；`gen_*--check` 原样 OK） |
| 2 | **`data/knowledge/raw/` 留在仓库根、不随包**（版权红线；运行期判定只需规则包内 `quote` 字段） |
| 3 | `rca/paths.py` 新增包内分支，排在"开发树上溯"**之前**；`--data` / `RCA_DATA_DIR` 的前置优先级**未动** |
| 4 | `rca/packaging.py` 拆两套集合：`WHITELIST`（exe 运行必需，`verify_package` 断言"入包集合 == 白名单"）+ `WHEEL_EXTRA`（装态素材，目前只有演示样例） |
| 5 | `pyproject.toml` 加 `[tool.setuptools.package-data]` |

### 3.2 新增门禁

| 门禁 | 位置 | 断言 |
|---|---|---|
| 装态冒烟（7 项） | `tests/test_install_smoke.py` | 真建 wheel → 全新 venv → 装 → **中立目录**跑；断言规则条数、`BENCH_OK`、`check` exit 1；另断言装态 `data/` 落在 `site-packages`、`knowledge/raw/` 未随包 |
| CI job | `.github/workflows/ci.yml` → `install-smoke` | 同链路黑盒跑（不依赖测试套件自身正确性） |
| CI 接线守门 | `tests/test_ci_wiring.py` | 必须有该 job，且**执行行**不得含 `pip install -e` |

**负控已验**：删掉 `[tool.setuptools.package-data]` → 装态门禁 **5 红 / 2 绿**。

### 3.3 元数据与外部对齐

| 项 | 改后 |
|---|---|
| license | `license = "MIT"`（SPDX）+ `license-files = ["LICENSE"]`；删 `License ::` classifier；`build-system` 下限 `setuptools>=77` |
| 元数据 warning | **`WARNINGS: []`**（改前 3 条 `SetuptoolsDeprecationWarning`：TOML 表告警 1 + classifier 告警 2；setuptools 84 的硬期限为 2027-02-18） |
| floor | `requires-python = ">=3.12"`；`gui = ["PySide6>=6.6"]`；CI 矩阵 = 双 OS × 3.12 |
| actions | `checkout@v5`、`setup-python@v6`；加 `permissions: contents: read` 与 `concurrency` |
| 台账口径 | RELEASE ASSET 行记**附件名**（不再引用 `_scratch/` 本地路径） |

---

## 4. 验收（本机实测）

### 4.1 装态（全新 venv + 中立目录）

```
wheel: rca-0.1.1-py3-none-any.whl  /  data 条目 6
rca --version                                                         exit 0（rca 0.1.1）
rca rules --city 北京                                                  exit 0（条目数：10）
rca bench                                                             exit 0（BENCH_OK）
rca check --input <site-packages>/rca/data/samples/demo-contract-bj.txt --city 北京
                                                                      exit 1（检出不符合）
```

### 4.2 源码态门禁

```
pytest -o addopts="" -q                                             291 passed, exit 0
rca.cli bench                                                       BENCH_OK, exit 0
    B1 f1=1.0000 (90/90) / B2 hit_rate=1.0000 (150/150) / B3 14/14   ← 与 v0.1.0 完全一致
rca.cli rules --city 北京                                             exit 0
tools/gen_rulesets.py --check                                       RULESETS_FROZEN_OK
tools/gen_samples.py --check                                        SAMPLES_FROZEN_OK
tools/check_literals.py                                             LITERAL_GATE_OK
tools/audit_desensitize.py all                                      DESENSITIZE_AUDIT_OK（HARD 0）
tools/fetch_sources.py --check                                      SOURCES_FROZEN_OK
```

### 4.3 产物级验收（重打包后）

```
PyInstaller 6.22.3 重打双 exe                                     exit 0
verify_package.py --dist dist/rca-cli                              PACKAGE_VERIFY_OK
verify_package.py --dist dist/rca-gui --gui-selftest               PACKAGE_VERIFY_OK
build_release.py --check（两个 zip）                                RELEASE_ZIP_DETERMINISTIC_OK
解压中立目录跑 rca-cli.exe --selftest
    {"version": "0.1.1", "frozen": true, "data_dir_in_dist": true, "bj_rule_count": 10}
```

---

## 5. CI 对账

| # | run id | 触发 | sha | 结论 | job 明细 |
|---|---|---|---|---|---|
| 1 | `39299287055` | push `main` | `5e751f6` | **failure** | `test (ubuntu)` success / `test (windows)` success / `package` success / **`install-smoke` failure** |
| 2 | `39299723212` | push `main` | `40610e1` | **success** | 四 job 全绿；`test` 14 步 / `install-smoke` 10 步 / `package` 11 步 |

**第 1 次失败不是断言失败**：日志里三条断言全过（`rules exit=0 / bench exit=0 / check exit=1`），
失败原因是 **pwsh 把最后一条外部命令的退出码继承成 step 退出码**——`check` 的 `1`
（既定语义"检出不符合"）直接让 job 判失败。
修法：断言全部转成 `throw`，末尾显式 `exit 0` 收口（见 `ci.yml` 该 step 的注释）。

**注解对账**（`gh api .../commits/40610e1/check-runs`）：

| check-run | annotations |
|---|---|
| `test (windows-latest / py3.12)` | 0 |
| `test (ubuntu-latest / py3.12)` | 1（**notice** 级：`ubuntu-latest` 将于 2026-10-19 起迁移 Ubuntu 26） |
| `install-smoke (windows-latest / py3.12)` | 0 |
| `package (windows-latest / py3.12)` | 0 |

`Node.js 20 is deprecated` 在全 run 日志里 **0 条**——actions 升到 checkout@v5 /
setup-python@v6 后弃用警告消失。

**这次失败是有价值的**：`install-smoke` 第一次真跑就暴露了一个"本地跑不出来"的问题
（Windows 本地用 bash 风格取退出码，GitHub runner 上 step 由 pwsh 驱动）。
**这正是新增该 job 的目的**——黑盒链路必须真跑才算验证。

---

## 6. 保留与回退

- **`v0.1.0` 的 tag 与 Release（含两个旧 zip）原样保留**，历史可追溯、旧产物仍可下载。
- 若需回退：`v0.1.0` 的源码与发布件都在；本版改动集中在数据布局与打包声明，
  判定逻辑（`engine`/`parser`/`report`/`benchmark`）**零改动**——B1/B2/B3 指标与本版一致。

---

## 7. 复现命令

```bash
# 消费者
gh release download v0.1.1 --repo yuluo554/10-15-rental-contract-auditor -D dl/
sha256sum dl/*.zip                       # 对 plan/DIST-sha256-v0.1.1.txt
mkdir neutral && (cd neutral && unzip ../dl/rca-cli-win64.zip)
(cd neutral/rca-cli-win64 && ./rca-cli.exe --selftest s.json && cat s.json)

# pip 安装（这一版起装态真能用）
python -m pip install "rca @ git+https://github.com/yuluo554/10-15-rental-contract-auditor@v0.1.1"
rca rules --city 北京      # exit 0
rca bench                  # BENCH_OK

# 开发者
git clone git@github.com:yuluo554/10-15-rental-contract-auditor.git
cd 10-15-rental-contract-auditor
python -m pip install -e ".[dev,gui]"
python -m pytest -q                                     # 291 项
python -m rca.cli bench                                 # BENCH_OK
```
