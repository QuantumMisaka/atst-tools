# Spec 审查：vendored abacuslite 跨仓维护与力读取一致性设计

- **Status:** Review（对 `2026-08-04-abacuslite-cross-repo-and-force-read-design.html` 的逐条核对结论 + 规划补强）
- **Reviewer:** ATST-Tools 开发 Agent
- **Date:** 2026-08-04
- **审查基线:** worktree `transition-spec-impl` 的 atst-tools `main`（`de864ef`，含 efermi 修复 `b1ebd4c`）；上游 `deepmodeling/abacus-develop`（本地 clone，develop tip `df5567adf`）
- **工作流分级:** L3（跨模块行为修复 + 跨仓维护模型，返工成本高，走 writing-plans 分阶段实施）

## 0. 总体结论

Spec 的**核心判断成立**：`read_results` 无条件 `read_abacus_out(...)[-1]` 取末帧（`core.py:369-372` 实证），多帧累积 running log 下会把旧结构/试探点的力当成当前结构的力；fail-closed 坐标校验 + 跨仓同步纪律的方向正确，Phase 0/1/2 分层合理。

但 spec 存在 **2 处事实性错误**（基线日期与 #7588 拉取状态）和 **6 处设计缺口**（见 §2 P2–P7），其中 P2（CI drift gate 当前对自己钉扎的基线即为红）与 P3（legacyio/latestio 双后端、SAI 生产路径是 legacyio）必须在进入 Phase 1 前写入 spec。

## 1. 逐条核对结果

### 1.1 已证实（保留）

| Spec 论断 | 证据 |
| --- | --- |
| 末帧无条件选取 | `abacuslite/core.py::AbacusTemplate.read_results`：`read_abacus_out(outdir/f'running_{calculation}.log', sort_atoms_with=self.atomorder)[-1]` |
| 长度断言可排除"单纯缺力块"假设 | `legacyio.read_abacus_out` / `latestio.read_abacus_out` 均有 `assert len(trajectory) == len(forces)`（空力表会先填 `[None]*nframe`，部分缺块则崩溃） |
| MD 最新格式走 MD_dump | `latestio.read_abacus_out`：`fileobj.name == 'running_md.log'` → `read_traj_from_md_dump(MD_dump)`；`read_traj_from_running_log` docstring 明确 MD 轨迹不入 running log |
| efermi 容错只在 fork | `b1ebd4c` 仅改 vendored `legacyio.py:723` / `latestio.py:389`（`ener['E_Fermi']`→`ener.get('E_Fermi')`），checker 无对应归一化 |
| abacuslite 不在 PyPI，external 分支是死代码 | pypi.org JSON/simple 均 404；`pyproject.toml` dependencies 无 abacuslite；`_load_abacuslite_backend()` external-first 仅理论可达 |
| checker/CI/测试基建存在且可复用 | `scripts/check_abacuslite_snapshot.py`（已有结构适配归一化：嵌入测试剥离、packaging import、注释 churn、band parser 容差块）；`.github/workflows/abacuslite-ase-interface.yml`（`ABACUS_DEVELOP_REF`）；`tests/unit/test_abacuslite_{ci,io_reorder,snapshot_ci,profile}.py` 全绿（本地 17 passed）；`io/testfiles/` 已有 scf/relax/md/mddump 金样 |
| sella 单目录复用机制 | `mep/sella.py` 用上游 `sella.Sella` + `CalculatorFactory`，全部力计算复用同一 `sella_run` 目录 |
| 文档改写目标定位准确 | `docs/index.md:76`"kept for 2.0.x reproducibility"、AGENTS.md"优先使用环境内的abacuslite"确为 D6/R7 需改写表述；HANDOVER.md 已有 `ABACUS_DEVELOP_REF` 同步条目 |

### 1.2 事实性错误（必须修正 spec）

**E1：基线日期与来源错误。** Spec："vendored abacuslite 快照（2026-05-10 引入，基线 70f7ed69）"。实际：
- vendored 快照引入 = 2026-05-10（`881a926 feat: 集成 abacuslite 并完善工作流与测试`）——但当时的基线不是 70f7ed69；
- drift-check CI 于 2026-07-06（`7a04854`）引入时钉扎的是 `762919f6`（#7588 的 PR head）；
- **当前基线 `70f7ed69` 是 2026-07-22 的上游 commit**（"CMake: Introduce CMake dependent options…#7626"），于 2026-07-23（`b8556c7`）写入 CI 与 `ABACUSLITE_WRAPPER_GUIDE.md`。
即"2026-05-10 引入"与"基线 70f7ed69"是两个事件，spec 合并表述错误；`ABACUSLITE_SNAPSHOT.md`（R4）应记录的真实基线日期是 2026-07-23（上游 commit 2026-07-22）。

**E2："上游 2026-07 的 #7588 加固未被拉取"——错误。** #7588（"Fix and harden abacuslite ASE interface"）2026-07-06 合入 develop（merge commit `b389b8f8`），是基线 70f7ed69（07-22）的**祖先**（`git merge-base --is-ancestor` 验证）。实测 checker 对当前 develop tip（`df5567adf`）仅报 fork 侧 efermi 两处 diff，**无任何上游侧未拉取变更**。D4 的"#7588 类加固出现时拉取"作为未来触发点仍成立，但 spec 中"已存在未拉取加固"的前提不成立，Phase 2 的"阶段性拉取"当前没有欠账，只有登记欠账（efermi）。

### 1.3 措辞修正

- "drift checker 对当前上游会报警"：实际 checker 比较对象是 CI 钉扎基线；实测对**钉扎基线**与**当前 develop** 都 exit 1，且原因都是 fork 侧 efermi 未登记（不是上游侧变化）。
- Rollout "语义补丁以 2.2.x 小版本承载"：按 AGENTS.md 版本语义（minor 保留阶段性/重大发布，patch 承担 bug 修复），应写 **2.2.x patch**，避免与 minor 语义混淆（当前已发布至 2.2.1）。

## 2. 审查发现的问题与设计缺口

**P1（已验证的紧迫事实）：CI drift gate 当前对自己钉扎的基线即为红，且只在 PR 触发。**
实测 `check_abacuslite_snapshot.py --upstream <70f7ed69 树> --vendored <当前 main>` exit 1（仅 efermi 两处 diff）。efermi 修复是直推 main 落地（无对应 PR），而 workflow 仅 `pull_request` 触发——直推绕过了 gate。后果：(a) 任何触碰 vendored 路径的 PR 当前必挂 CI；(b) main 上的 drift 纪律实际无人把守。→ Phase 2 的补丁清单（R3）是**解锁 CI 的前置**而非伴随项；同时 workflow 应补 `push: branches: [main]`（或对 main 的 drift 巡检 job），否则同步纪律在主干不可执行。

**P2：spec 完全未提及 legacyio/latestio 双后端。** `switch_io_backend_version`：ABACUS ≥3.11 或 3.9.0.x → latestio；**3.10.x LTS → legacyio**。SAI/SIF 生产环境是 ABACUS LTS 3.10.1（AGENTS.md 明确），即**生产事故路径走 legacyio**；且 legacy MD 格式轨迹在 running log 内（latestio 才有"MD 无坐标走 MD_dump"之分）。修法必须同时覆盖两个 `read_abacus_out`/`read_traj_from_running_log`，或（推荐）把帧选择上提到唯一汇聚点 `core.py::read_results`，一次覆盖两个 IO 后端、且不改动 `read_abacus_out` 的纯解析语义。

**P3：坐标比较的实现细节未定义（容差与排列）。**
- STRU 以**物种分组序**写出（`write_stru(atoms[ind])`），而 `read_abacus_out` 返回帧已按 `self.atomorder`（revmap）重排回 ASE 序——expected_coords 与帧坐标必须在同一排列下比较（建议：比较发生在重排前/统一用分组序）。
- running log 坐标系可为 DIRECT 或 CARTESIAN（parser 返回 `coordinate` 字段），STRU 亦可两种；比较前统一换算到 Cartesian Å。
- "相对 1e-5"容差对 Direct 分数坐标无意义；应以 running log 坐标打印精度为准给出**绝对 Å 容差**（如 1e-4 Å 量级，按打印小数位推导）并写进 golden 测试断言。

**P4：calculator 之外还有 `read_abacus_out` 消费者。** `utils/abacus_io.py::_parse_last_abacus_frame`（运行目录事后摘要，`[-1]` 语义正确）与 `workflows/md.py`（MD 帧解析，**硬编码 latestio import**——legacy ABACUS 下是潜在 bug，另案记录）直接调用 `read_abacus_out`。若按 spec 架构图给 `read_abacus_out` 加 `expected_coords` 参数，必须为可选、默认不改变行为；建议帧选择不侵入 `read_abacus_out`（见 P2 推荐）。

**P5：latestio.read_abacus_out 读后删除 `eig_occ.txt`（`unlink()`）。** 多帧 golden 测试若走完整 `read_abacus_out` 必须提供与帧数一致的 `eig_occ.txt`，且注意其一次性消费语义（重复读取需重建文件）；这也是 Phase 0 诊断时解释"缓存 vs 文件"时序的注意点之一。

**P6：R4 缺少"保持一致"的机制。** "ABACUSLITE_SNAPSHOT.md 与 CI `ABACUS_DEVELOP_REF` 保持一致"若无强制手段会再次漂移。建议单一事实源：CI 从 `ABACUSLITE_SNAPSHOT.md` 解析基线 SHA（workflow 内 `grep/sed` 注入 env），或增加一条 unit test 断言两者一致。

**P7：Phase 0 假设枚举不完整。** Spec 列 (a) 帧错位 / (c) 读入后日志增长两种精确分歧点；还应显式检查 **(b') 末次 ABACUS 调用 exit 0 但未新增任何帧**（如 SCF 未收敛仍正常退出、或试探点计算提前终止）——此时所有长度断言通过、`[-1]` 静默返回上一结构力，与观测（成功返回 0.0374）同样相容。Phase 0 取证清单应包含：逐帧坐标头 + 帧数 + 各帧 TOTAL-FORCE 块计数 + INPUT `calculation` 值 + sella 调用序列时间线。

**P8：文档治理漏项。** Rollout 列了 `docs/index.md`、`AGENTS.md`、HANDOVER，但按 AGENTS.md 文档治理机制，本 spec（及后续 plan）还需登记进 `docs/reports/DOCUMENTATION_STATUS_REPORT.md` 账本；HANDOVER checklist 需新增"基线文件 + 补丁清单"条目（第 5 节 backend 小节）。

## 3. 建议的修法决策（供 spec 定稿）

1. **帧选择落在 `AbacusTemplate.read_results`（core.py）**：`read_abacus_out` 返回全部帧后，当且仅当 `self.calculation == 'scf'` 时，在帧列表中选取"坐标与本次写入 STRU 一致的最后帧"；无匹配帧抛带上下文的错误（running log 路径、帧数、期望/末帧坐标差异摘要）。非 scf（原生 relax/md）保持 `[-1]`。两个 IO 后端一次覆盖，`read_abacus_out` 公共签名不变（P2/P4）。
2. **expected_coords 来源 = 本次 write() 落盘的 STRU**（`read_stru(directory/'STRU')`），按与帧相同的物种分组序比较；不依赖 ASE 侧 atoms 缓存，避免与 sella 的 `set_x/restore` 缓存交互耦合。
3. **容差**：以 running log 坐标打印精度推导绝对 Å 容差，golden 测试覆盖"容差内通过/容差外 fail-closed"两侧。
4. **MD 路径**：latestio `running_md.log`（MD_dump）与 legacyio 原生 md 均走 `[-1]` 旧语义；ASE 驱动 md（atst 默认）逐步 scf，自然落入 scf 校验。
5. **补丁清单格式**：沿用 checker 现有"归一化函数 + 文件级登记"风格（参考 `_normalize_legacy_band_parser_adaptation` 先例），efermi 登记为 `legacyio.py`/`latestio.py` 的块级白名单条目，清单本体落 `src/atst_tools/external/ASE_interface/PATCHES.md`（与 `ABACUSLITE_SNAPSHOT.md` 同目录）。
6. **（决策补记，2026-08-04 SAI GPU 实证后）帧选择保留为防御性改进，非缺陷修复**：SAI 双作业验收（job 759099 固定 Au / job 759210 全自由 66 原子）实证：`running_*.log` 的 TOTAL-FORCE 为 **RAW 全原子力**（含固定原子），sella 的 `atoms.get_forces()` 按 FixAtoms 约束投影为自由原子力——0.0374 vs 0.338 的差异是**约束投影**，非力读取 bug。全自由决定性检验：末帧 RAW fmax=0.0564694245 与 `sella.traj` 末帧 `get_forces` fmax=0.0564694245 **完全一致（力差 0.0，坐标差 6.7e-11）**；sella 2 步停实为**合法收敛**（投影/自由力 0.0565 < 收敛阈值 0.1），打印 fmax 恒定是 `_last_converged` 显示陈旧。据此**保留**本补丁：其价值是消除"末帧即当前结构"假设的歧义并 fail-closed（防御性），而非修复已证实的读取错误；PATCHES.md 已登记维护触点（改补丁须同步 `_FRAME_SELECTION_BLOCK` 正则）。
7. **下一步如何操作（2026-08-04 决策后）**：① 验收收口——以 job 759210 全自由 MATCH 作为决定性证据更新 `~/scratch/accept-evidence/accept-sella-evidence.md`，并将 SDD 账本 Task 9 判定由"不通过"修订为"通过（帧选择防御性保留）"；② sai-local-e2e harness 与 opencode 1.18.10 的 MCP 配置不兼容已查明（裸 python 解析到 base、`mcp.adam.timeout` 需对象化、worktree `opencode.jsonc` 合并覆盖），当前验收经直接 SSH+sbatch 的 SAI 路径完成——记录该状态，harness 修复作为独立后续项；③ 上游收敛（Phase 3）——将 efermi 容错 + 帧选择防御改进整理为 PR 提交 abacus-develop `interfaces/ASE_interface`（需授权），合入后推进基线再同步清理归一化；④ 长期：以"全自由结构 RAW==投影"作为力读取相关回归的决定性判据，纳入后续 abacuslite 相关验收惯例。

## 4. 目标开发规划（按 atst-tools 开发模式）

工作目录：worktree `transition-spec-impl`（atst-tools `main`）。测试环境：`conda run -n abacus-env env PYTHONPATH=$PWD/src pytest`（本机）；ABACUS 实证走 SAI（sai-local-e2e，GPU 节点，INPUT `ks_solver cusolver`）。不 bump 版本号直至收敛。

### Phase 0：SAI 诊断（前置，锁定修法细节）
- [ ] 取回 sella_repro 运行目录：`running_scf.log`、各步 STRU（含 STRU.bak.*）、INPUT、sella 诊断输出（`3fa98bf` 已提供 nsteps/fmax 可见性）。
- [ ] 用 `read_forces_from_running_log` / `read_traj_from_running_log` 脚本化输出：帧数、逐帧坐标头、逐帧 TOTAL-FORCE 块计数、末帧坐标 vs 当时 STRU。
- [ ] 判定分歧子机制 (a) 帧错位 / (b') 末次调用未产新帧 / (c) 读入后日志增长，写入诊断纪要（作为 L2 报告入 `docs/reports/` 并登记账本）。
- [ ] 出口准则：子机制证据链闭合；若坐标校验不足（如坐标一致但力块错位），升级为解析对齐/目录隔离评估（spec 已预留）。
- 验证：诊断纪要可复现 0.0374 vs 0.338 数字。

### Phase 1：力读取一致性修复（TDD，golden-file 先行）
- [ ] RED：新增多帧累积金样（INIT + 位移 + trial + P0 重算序列，含 `eig_occ.txt`），构造"末帧为试探结构"场景；`tests/unit` 扩展 `test_abacuslite_ci.py` / 新增帧选择套件，断言：返回当前结构力 / 无匹配帧 fail-closed / 容差边界两侧。
- [ ] GREEN：`core.py::read_results` 实现 scf-only 帧选择 + STRU expected_coords + 容差比较 + 明确异常（含路径与差异摘要）。
- [ ] 四路径回归用例：md（ASE 驱动逐步 scf + MD_dump 原生路径不受影响）/ relax（ASE 驱动）/ sella（试探步模式）/ ccqn（自循环）。
- [ ] 既有套件全绿：`pytest tests/unit -q` + workflow 内 vendored 包 `python -m unittest` 四模块。
- [ ] SAI/SIF 实证：sella e2e 由 2 步停 → 多步收敛（fmax 单调下降或正常收敛）；md/relax/ccqn 链路 exit 0（sai-local-e2e，结果入验证报告）。
- 出口准则：R1/R2/R8 满足；local + SIF 绿。

### Phase 2：跨仓同步纪律（解锁 CI，可与 Phase 1 同批）
- [ ] `ABACUSLITE_SNAPSHOT.md`：基线 `70f7ed69b567…`（上游 commit 2026-07-22，本仓登记 2026-07-23）、快照引入史（2026-05-10 / 762919f6 / 70f7ed69 三段）、差异摘要（与 checker 输出一致）。
- [ ] `PATCHES.md` 语义补丁清单：登记 efermi 容错（legacyio+latestio 块级）、band parser tolerance（已由 checker 归一化，登记为结构适配/语义补丁的归类说明）、力读取修复（Phase 1 产出）。
- [ ] checker 扩展：语义补丁白名单归一化；未登记新 drift 保持 exit 1。新增 unit test 覆盖"登记通过/未登记报警"。
- [ ] CI：workflow 增加 `push: branches: [main]` 触发（或独立 drift 巡检 job）；`ABACUS_DEVELOP_REF` 改为从 `ABACUSLITE_SNAPSHOT.md` 解析（P6），消除双写。
- [ ] 验证：checker 对钉扎基线 exit 0（登记后）；`abacuslite-ase-interface.yml` 全绿；`test_abacuslite_snapshot_ci.py` 扩展用例通过。
- 出口准则：R3/R4/R5 满足；CI 由红转绿且主干可执行。

### Phase 3：上游收敛与文档对齐
- [ ] 上游 PR（abacus-develop `interfaces/ASE_interface`）：力读取一致性修复（efermi 容错可一并提交，band parser 已在 #7588 上游化无需重复）。合入后推进 `ABACUSLITE_SNAPSHOT.md` 基线 → 再同步 vendored → 清理 checker 中失效的归一化规则。
- [ ] 文档对齐（R7 + P8）：`docs/index.md` Backend Policy、`AGENTS.md`（"本仓为主 + 定期上游同步 + 长期退位 vendored"）、HANDOVER checklist、`ABACUSLITE_WRAPPER_GUIDE.md` 基线段、`docs/reports/DOCUMENTATION_STATUS_REPORT.md` 账本（spec/plan/诊断报告登记）；按 DOCUMENTATION_STANDARDS 分级。
- [ ] 若需对外发布：以 2.2.x patch 承载（release notes + FEATURE_STATUS_MATRIX 同步）。
- 出口准则：R6/R7 满足；本地与上游收敛路径闭环。

### 依赖与顺序
Phase 0 → Phase 1（修法细节由 0 锁定）；Phase 2 中"efermi 登记 + CI 触发修复"应**尽早单独先行**（当前 CI 对 vendored 路径 PR 为红，阻塞其它工作），其余随 Phase 1 同批；Phase 3 在 Phase 1/2 收敛后。

## 5. 风险登记（在 spec 基础上补充）

| 风险 | 缓解 |
| --- | --- |
| Phase 0 若证实 (b')（末次调用未产新帧），坐标校验无法区分"新帧缺失"与"尚未运行" | 结合帧数单调性/调用序号（如 running log 的 ION MOVE 头计数）补强，必要时退到目录隔离评估 |
| 容差选择过紧 → 正常 scf false fail-closed | 金样覆盖容差两侧；容差以打印精度推导并留配置开关（默认开） |
| 直推 main 再次绕过 gate | Phase 2 的 push 触发 + drift 巡检 job |
| 上游 PR 周期不可控 | 已登记补丁形态可长期存在，不阻塞本地（spec 已有此判断，保留） |
| RAW 全原子力 vs 约束投影力再次被误读为力读取 bug（本 spec 曾误诊的同类风险） | fmax 口径已固化进 `ABACUSLITE_WRAPPER_GUIDE.md`（RAW 全原子力契约 + ASE 投影语义）；验收以"全自由结构 RAW==投影"为决定性检验，避免固定原子样本的投影混淆 |

---

## 6. 复审结论（2026-08-04 第二轮，spec 12:44 修订版 31K/186 行）

**结论：全部 2 处事实性错误与 8 项缺口（P1–P8）已正确修复，spec 达到可进入 writing-plans 的状态。** 逐项核对：

| 审查项 | 修订版落点 | 判定 |
| --- | --- | --- |
| E1 基线三段史 | 概述 §2、R4、D2（881a926 / 762919f6 / 70f7ed69，日期与 commit 与 git 实证一致） | ✅ |
| E2 #7588 已在基线 | 概述（祖先关系 + develop tip 零上游侧欠账实测）、R6（band parser 不重复上游化）、D4 | ✅ |
| P1 CI 现状红 + 直推绕过 | D3/D8、R3（PATCHES.md 提为解锁前置）/R5（push 触发）、错误处理、rollout 第 2 条单独先行、风险 ① | ✅ |
| P2 legacyio/latestio 双后端 | R1（read_results 汇聚点、不改签名、双后端用例）/R2（LTS 3.10.1→legacyio=生产路径、legacy 原生 md 保持 [-1]）、D7、架构"落点与双后端"、测试"SAI 实证在 LTS 3.10.1 完成" | ✅ |
| P3 排列/坐标系/容差 | 架构"坐标比较细节"①②③（统一排列、Cartesian Å、绝对 Å 容差 1e-4 量级）、测试"容差两侧 + DIRECT/CARTESIAN + 排列"用例、风险 ② | ✅ |
| P4 calculator 外消费者 | D7、架构"其他消费者"（abacus_io.py / md.py 硬编码 latestio 另案）、备选新增"拒绝改签名"、风险 ④ | ✅ |
| P5 eig_occ.txt 一次性消费 | 架构"golden 夹具一次性消费"、测试对应条目 | ✅ |
| P6 基线单一事实源 | R4（CI 从 ABACUSLITE_SNAPSHOT.md 解析 SHA，grep/sed 注入或 unit test 断言）、D2、测试"checker 与 CI" | ✅ |
| P7 (b') 假设 | 核心节"已排除假设"改写（"有帧缺力块"排除、整体未产新帧保留）+ 三候选 (a)/(b')/(c)、Phase 0 取证清单、错误处理、风险 ③（ION MOVE 头计数缓解） | ✅ |
| P8 文档治理 | R7（账本登记 + HANDOVER backend 小节）、D6、rollout 第 4 条 | ✅ |
| 措辞："2.2.x 小版本"→patch | rollout 第 3 条（2.2.x patch，AGENTS.md 版本语义） | ✅ |
| 措辞："对当前上游会报警" | 改为"对钉扎基线 exit 0/exit 1"精确表述 | ✅ |

**唯一残留（一行，不阻塞）：** spec 第 69 行"修复边界"bullet 仍写"容差约相对 1e-5"，与架构节 P3 ③（绝对 Å 容差 ~1e-4 Å、"相对 1e-5 对分数坐标无意义"）及测试节"容差两侧"自相矛盾。建议把该行改为"坐标比较带**绝对 Å 容差**（按 running log 坐标打印精度推导，见架构节 P3 ③）"。

**复审中新核实的一点（供 plan 参考，非 spec 缺陷）：** `core.py` 已 import `read_stru`（generalio），架构伪代码的 `read_stru(directory/'STRU')` 直接可行；另注意若某调用路径未在同类实例上先经 write()（`self.atomorder is None`），实现时需从 STRU 物种分组推导排列，plan 应含该边界用例。
