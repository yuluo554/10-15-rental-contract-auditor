# HANDOFF-M7 — 收官快照（房屋租赁合同审计器，项目完成态）

> 上一棒：**M6 发布**（2026-10-15 完成，见 `plan/RELEASE-M6.md`）
> 本文件性质：plan/05 §10 的"发布留档三件套"之一。
> **本计划（M0–M6）到此收官，无既定下一里程碑**——本文件记录收官状态、
> 可复现入口与**可选扩展项**（若将来另开一棒，从这里接）。

---

## 0. 收官状态（一句话）

**M0–M6 全部完成，v0.1.0 已公开发布，CI 首次运行即全绿，发布物经下载件级复核。**
仓库 `https://github.com/yuluo554/10-15-rental-contract-auditor`（PUBLIC，署名 yuluo554）。

| 里程碑 | 内容 | 完成 |
|---|---|---|
| M0 | 计划与骨架 | ✅ |
| M1 | 数据先行（四源快照 + 京/沪/全国三规则包） | ✅ |
| M2 | 解析（条款切分 + 要素抽取） | ✅ |
| M3 | 知识规则（城市差异包 + 判定引擎） | ✅ |
| M4 | 基准（合成样例 + 植入真值 + 三层基准） | ✅ |
| M5 | 交付（PySide6 双 exe + 产物级验收） | ✅ |
| M6 | 发布（建仓 + CI 首跑 + tag/Release + 留档） | ✅ |

---

## 1. 交付物清点（消费者视角）

| 交付物 | 位置 | 验证 |
|---|---|---|
| CLI 发行包（Windows x64，免安装） | Release 附件 `rca-cli-win64.zip`（11,928,127 B） | 下载件 sha256 对账 + 中立目录 `--selftest` exit 0 |
| GUI 发行包（Windows x64，PySide6） | Release 附件 `rca-gui-win64.zip`（116,266,441 B） | 同上；GUI 包 `--selftest` 结论与 CLI **逐字段一致** |
| 源码 | `main` @ tag `v0.1.0`（commit `ce62df0`） | 全新克隆：283 测试全绿、冻结校验三连 OK |
| CI | GitHub Actions，3 run 全绿 | 见 `plan/RELEASE-M6.md` §3 |
| 发布留档 | `plan/RELEASE-M6.md` / `plan/DIST-sha256-M6.txt` / 本文件 | — |

**"纯本地零上传"的产物级证据**：CLI 发行包排除了 `ssl`/`_ssl`/`_socket`/`_hashlib`，
包内**不存在能发起 TLS 的组件**（`verify_package.py` 扫产物断言，且该断言在 CI 的
`package` job 上真跑过）。这是"承诺"与"可核验证据"的区别所在。

---

## 2. 可复现命令（收官态实测通过）

```bash
# ① 消费者：拿发布包就用
gh release download v0.1.0 --repo yuluo554/10-15-rental-contract-auditor -D dl/
cd dl && unzip rca-cli-win64.zip && cd rca-cli-win64
./rca-cli.exe check --input 你的合同.txt --city 北京      # exit 1 = 检出不符合（非失败）
./rca-cli.exe bench                                      # BENCH_OK

# ② 开发者：源码全链路
git clone git@github.com:yuluo554/10-15-rental-contract-auditor.git
cd 10-15-rental-contract-auditor
python -m pip install -e ".[dev,gui]"
python -m pytest -q                                      # 283 项
python tools/gen_rulesets.py --check                     # RULESETS_FROZEN_OK
python tools/gen_samples.py --check                      # SAMPLES_FROZEN_OK
python tools/audit_desensitize.py history                # HARD 0

# ③ 打发布包（Windows + Python 3.12 + PyInstaller ≥6）
python -m PyInstaller --noconfirm --clean tools/rca.spec
python tools/verify_package.py --dist dist/rca-cli
python tools/verify_package.py --dist dist/rca-gui --gui-selftest
python tools/build_release.py --dist dist/rca-cli --out out --name rca-cli-win64.zip --check
```

---

## 3. 本棒（M6）的关键事实（跨会话必须知道）

1. **历史已被改写**：首推前用 `git filter-repo --email-callback` 把 12 个提交的
   author/committer 邮箱改成 GitHub noreply。**改写前的 sha 全部不可达**；
   旧→新映射见 `plan/RELEASE-M6.md` §7。若在别处见过 `2856c44`（M0 提交），
   现在对应 `68abe14`。
2. **工作树曾有大量未提交内容**：M2–M5 四个里程碑的最终状态此前只存在于工作树
   （暂存区），历史里只有 M0/M1。M6 已把它们落为一笔"累计快照"提交 `e1c23da`。
   **教训**：里程碑之间不要长期不提交——否则"历史"与"实际进展"会脱节，
   而 `git filter-repo`、`git archive` 这类操作都**只认已提交内容**（filter-repo
   遇未提交改动会直接 abort）。
3. **tag push 也会触发 CI**：`on: push` 无 ref 过滤，故 `git push origin v0.1.0`
   产生了一个额外 run（`38700167310`）。这是**有意保留**的——tag 上的绿是
   "发布点可构建"的直接证据。若要省额度，加 `branches: [main]` 即可，但会失去该证据。
4. **发布物验收是下载件级的**：不是本机 `dist/` 目录自证，而是
   `gh release download` 后的附件再算 sha256、再解压中立目录跑 `--selftest`。
5. **CI 首跑即绿**（无诊断轮次）：`test` 三 job + `package` job 一次通过。
   此前 M0–M5 全程"未接远端"，所有 CI 类判据都写的是"本地等价校验（待首推验证）"；
   M6 首推后这些判据已由真实 CI 覆盖。

---

## 4. 既定口径（K 清单）状态

M0–M5 的 K1–K37 见 `plan/HANDOFF-M5.md` §5 与 `plan/HANDOFF-M6.md` §4，**全部仍有效**。
M6 **未新增 K 项**——本棒不改判定逻辑、不改规则包、不改打包白名单，
只做发布动作与留档（对 `src/`、`tools/rca.spec`、`pyproject.toml` 零改动，
`git diff 1317b79..ce62df0` 对这些路径为空）。

**因此**：M5 的全部产物级判据（含 17 项变异验证）在 v0.1.0 上**原样成立**，
无需重新变异（变异脚本针对的是本棒未触碰的代码）。

---

## 5. 遗留与风险（收官态总表）

**已闭环**：

| # | 事项 | 闭环于 |
|---|---|---|
| R1 | CI 从未真跑 | M6：3 run 全绿，含 `package` job |
| R2 | 真实邮箱进历史 | M6：首推前改写，克隆件 ae/ce 均 noreply |
| R4 | GUI 只做了骨架 | M5：真构建 + 冻结态验收 |
| R5 | spec 从未构建过 | M5：首次实构建暴露并修掉 6 处产物级缺口 |
| R20 | `package` job 从未在 CI 跑 | M6：run `38699219195` 首次在 runner 通过 |
| R25 | M5 的 DoD 表格留 ⬜ | M6：按"每棒留自己的快照"约定不追改，M5 判据已在 HANDOFF-M6 §1/§6 据实记录 |

**仍开放**（均为**扩展项/工程优化**，不影响 v0.1.0 的可用性与承诺）：

| # | 事项 | 若要处置，怎么做 |
|---|---|---|
| R21 | GUI 发行包 116MB（内含 87MB PySide6） | 用 `--exclude-module` 裁未用 Qt 子模块（QtWebEngine 等）。**必须先实测哪些子模块真用不到**——贸然裁会在运行期缺库，而 `verify_package.py` 的 `--gui-selftest` 能兜住一部分（它会真跑 GUI 包） |
| R22 | GUI 只有两个页签（合同体检 / 规则包） | 报告导出、批量扫描在 GUI 侧未提供（CLI 有）。属功能扩展；不影响"双入口结论同源"（已有回归 `tests/test_m5_dual_entry.py`） |
| R24 | 变异脚本"卡死"风险已加固未根治 | 已加 300s 超时 + GUI 测试打桩；但暴力 kill 仍会留脏源码。要常态化（提进 `tools/`）须先解决"进程被杀时如何保证回滚" |
| R26 | 历史改写使旧 sha 全不可达 | 本仓零消费者窗口期内改写，无外部引用。**若将来仍需引用旧历史**，`_scratch/backup/pre-rewrite-all.bundle` 可重放（该目录不进仓，随本机工作区存续） |
| R27 | tag push 二次触发 CI | 见 §3 第 3 条；**有意保留** |
| — | 城市覆盖仅京/沪 | 扩展其他城市须先完成该条例原文直连查证（D2 纪律：未核对原文不得落库） |
| — | 首期不做 Word 回写 / 不接在线法规库实时更新 | 见 README「限制」节 |

**M0–M4 的 R3/R6–R19** 见 `plan/HANDOFF-M5.md` §10，其中 R14（变异脚本不入仓）、
R18/R19（假绿教训）**属于方法论纪律，长期有效**。

---

## 6. 环境坑（收官期新增）

> M0–M5 的全部坑见 `plan/HANDOFF-M5.md` §6 与 `plan/HANDOFF-M6.md` §5，仍有效。新增：

- **`git filter-repo` 遇未提交改动直接 abort**（`you have uncommitted changes`）——
  要改写历史，**先提交**。这条与"里程碑之间长期不提交"叠加，会让人误以为
  "改写没生效"（实际是拒绝了）。
- **`git filter-repo` 会移除 `origin` remote**（防误推回原地址），改写后须
  `git remote add/set-url` 重新配。本项目改写发生在建仓**之前**，故无影响。
- **`--email-callback` 的回调收到的 `email` 是 bytes**，返回值也须是 bytes；
  回调文件里**不能有 CRLF**（用 `write_bytes` 或确保 LF），否则 `exec` 出错。
- **`email_callback` 同时作用于 author 与 committer**（源码 `RepoFilter` 里
  两行分别调用同一个回调），故一次改写即可清洁 `ae` 与 `ce` **两个字段**——
  但**必须分别验证**，别只查 `%ae`。
- **`audit_desensitize.py history` 的探活是 fail-safe**：它先搜"仓库目录名"，
  搜不到就报 `HISTORY_PROBE_FAIL` 并 exit 2。**在非默认目录名的克隆里跑会误报**
  （例：克隆到 `_scratch/freshclone/` 会失败，克隆到默认名 `10-15-rental-contract-auditor/`
  才通过）。这是**设计意图**（防静默空扫），不是泄漏信号——但复核脚本要按默认目录名建克隆。
- **`sha256sum` 在 Git Bash 下对中文/大文件路径需引号**；本项目改用 `hashlib`
  直接算并以 `>>` 重定向进留档，避免手工转录。
- **`gh release create` 在 Git Bash 下会剥中文附件名**——附件名**一律 ASCII**
  （用了 `rca-cli-win64.zip` / `rca-gui-win64.zip`）；中文只出现在 `--title/stdout`。

---

## 7. 下一棒启动提示词

**本项目 M0–M6 计划已收官**，没有既定下一棒。若将来要开新的一棒（例如做 R21/R22
的扩展），建议先读本文件 §5「仍开放」与 §3「关键事实」，再决定题目。

若要**继续本仓**的扩展开发：

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M7.md" 继续完成任务
```

> 入库文档内一律写**相对路径**（`plan/HANDOFF-M7.md`），绝对路径只出现在用户侧
> 启动命令中（否则发布期脱敏扫描必中）。
