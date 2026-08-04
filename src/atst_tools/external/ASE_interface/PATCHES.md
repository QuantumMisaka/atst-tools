# vendored abacuslite 语义补丁清单

与上游逐字节差异的**语义补丁**（非结构适配：相对导入/删内嵌测试/注释 churn 由 checker 机械归一化）。每条登记后由 `scripts/check_abacuslite_snapshot.py` 归一化。

| 文件 | 位置 | 补丁 | 登记日期 | 上游状态 |
| --- | --- | --- | --- | --- |
| `abacuslite/io/legacyio.py` | SinglePointDFTCalculator 构造 | `efermi=ener['E_Fermi']` → `ener.get('E_Fermi')`（running log 缺 E_Fermi 容错） | 2026-08-04 | 未上游化（待 PR） |
| `abacuslite/io/latestio.py` | 同上 | 同上 | 2026-08-04 | 未上游化（待 PR） |
| `abacuslite/io/legacyio.py` | band parser | 容差块（`_legacy_band_parser_tolerant_block`） | 2026-05-10 | 已由 #7588 上游化（checker 归一化保留至基线推进后清理） |
