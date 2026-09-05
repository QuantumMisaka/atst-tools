# vendored abacuslite 语义补丁清单

与上游逐字节差异的**语义补丁**（非结构适配：相对导入/删内嵌测试/注释 churn 由 checker 机械归一化）。每条登记后由 `scripts/check_abacuslite_snapshot.py` 归一化。

| 文件 | 位置 | 补丁 | 登记日期 | 上游状态 |
| --- | --- | --- | --- | --- |
| `abacuslite/io/legacyio.py` | SinglePointDFTCalculator 构造 | `efermi=ener['E_Fermi']` → `ener.get('E_Fermi')`（running log 缺 E_Fermi 容错） | 2026-08-04 | 未上游化（待 PR） |
| `abacuslite/io/latestio.py` | 同上 | 同上 | 2026-08-04 | 未上游化（待 PR） |
| `abacuslite/io/legacyio.py` | band parser | 容差块（`_legacy_band_parser_tolerant_block`） | 2026-05-10 | 已由 #7588 上游化（checker 归一化保留至基线推进后清理） |
| `abacuslite/core.py` | `read_results` 帧选择 | scf-only 坐标匹配（`_select_scf_frame_for_structure` 等，Task 3 产出） | 2026-08-04 | 未上游化（待 PR） |
| `abacuslite/io/generalio.py` | `_read_kpoint` | `0b01ed2`：坐标正则的小数部分改为非捕获组，并将权重读取从捕获组 6 修正为组 3（保证 point-KPT 小数坐标精确往返） | 2026-08-12 | 未上游化（待 PR） |

## 维护触点

- **core.py 帧选择（防御性改进，非 bug 修复）**：SCF 下按"帧坐标 == 当前 STRU"选择
  帧并 fail-closed（多帧累积 running log 下消除"末帧即当前结构"假设的歧义）。实测
  "sella 提前收敛"原因为约束投影（RAW 全原子力 vs ASE 投影后自由原子力），非力读取
  bug；本补丁定位为防御性改进。**改动该补丁（新增/删除注释、重命名变量、改分支结构）
  时必须同步更新 `check_abacuslite_snapshot.py` 的 `_FRAME_SELECTION_BLOCK` 归一化
  正则**（注释行数/缩进变化会使其失配 → 按设计 fail-safe 报 exit 1，属预期而非静默）。
