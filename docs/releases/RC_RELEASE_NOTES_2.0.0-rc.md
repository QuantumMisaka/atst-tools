# ATST-Tools 2.0.0-RC 发布说明

- 概述
  - 本版本为 2.0.0 正式版的发布候选（RC），冻结接口与功能，完成示例与测试收尾。

- 新功能特性
  - 计算器解耦：CalculatorFactory 统一管理 ABACUS（vendored abacuslite ASE_interface）与 DeepMD
  - 工作流：NEB/AutoNEB、Dimer、Sella、D2S、Relax、Vibration 完整
  - 振动分析增强：ZPE、频率与 HarmonicThermo 指标（S、U、F）
  - CLI 入口：atst-run 统一调度，配置驱动执行

- 修复的缺陷
  - 清理旧版强耦合与路径硬编码；DP 串行共享策略降低显存

- 已知问题
  - DP/机器学习势真实算例验证排在 ABACUS 验证之后
  - 全量 ABACUS examples 需要通过 SAI Slurm 队列完成最终实算验收

- 系统要求
  - Python >= 3.9；依赖：ase>=3.22.1, numpy, scipy, matplotlib, ruamel.yaml, seekpath
  - 可选：deepmd-kit（DP），ABACUS 可执行与环境模块（abacuslite 后端）

- 升级与迁移
  - pip install . 安装；通过 atst-run + config.yaml 执行
  - legacy 示例仅作参考，不直接运行

- 归档机制
  - 发布说明归档于 docs/releases/，命名：RC_RELEASE_NOTES_<version>.md
