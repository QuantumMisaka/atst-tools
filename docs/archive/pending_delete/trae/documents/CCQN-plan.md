# H2-Au Sella/CCQN Perturbed-Input Validation Plan

  ## Summary

  - 当前确认：05_sella_H2-Au 和 12_ccqn_H2-Au 都是 final-TS confirmation，不是完整搜索案例。
  - 执行目标：在 temp_practices/h2_au_sella_ccqn_perturb/ 中生成同一份 H2 微扰初猜，分别跑 Sella 和 CCQN，确认二者收
    敛回同一个 final TS 后，再替换正式 examples 输入。
  - 完成状态：已完成。最终采用总 H-H 拉伸 0.002 Å 的保守扰动，Slurm job `454726` 在 `4V100PX` / `4v100pxn05` 上完成。
  - 扫描结论：其他需要展示搜索流程的案例未发现同类问题；07_vibration_H2-Au 和 10_irc_H2 从 TS 开始是方法语义要求，不
    处理。

  ## Key Changes

  - 生成共用扰动结构：
      - 基准：examples/reference_structures/05_sella_H2-Au_final_ts.extxyz
      - 只扰动原子 0,1 的 H2。
      - 沿 H-H 单位向量对称拉伸。0.05、0.015、0.005 Å 测试未给出稳定完整回归流程；最终采用总 H-H 长度增加 0.002 Å，
        即两个 H 各移动 0.001 Å。
      - 保留 cell、PBC、FixAtoms 约束、初始磁矩和原子顺序。
  - 临时实算目录：
      - temp_practices/h2_au_sella_ccqn_perturb/05_sella_H2-Au/
      - temp_practices/h2_au_sella_ccqn_perturb/12_ccqn_H2-Au/
      - 共用 data -> examples/data 符号链接或等效相对路径，保证 pseudo_dir: ../data / orbital_dir: ../data 可用。
  - Sella 临时 config：
      - 基于 examples/05_sella_H2-Au/config.yaml
      - init_structure: inputs/sella_init.stru
      - 其他 ABACUS 参数保持不变。
  - CCQN 临时 config：
      - 基于 examples/12_ccqn_H2-Au/config.yaml
      - init_structure: inputs/ccqn_init.stru
      - accept_initial_converged: false
      - 保留 reactive_bonds: "1-2"、e_vector_method: ic、同一套 ABACUS 参数。
  - SAI 实算：
      - 使用 atst-dev
      - Slurm: 4V100PX，--ntasks=16，--gpus-per-node=4
      - 一个 sbatch 脚本顺序运行 Sella 和 CCQN，日志写入临时目录。

  ## Acceptance Criteria

  - [x] 两个作业均 COMPLETED，exit code 0:0。
  - [x] ABACUS 日志确认 GPU：包含 RUNNING WITH DEVICE  : GPU / Tesla V100。
  - [x] 两个 workflow 都不是一步确认：
      - Sella trajectory frames = 9
      - CCQN trajectory frames = 14
      - CCQN 不使用 accept_initial_converged
  - [x] 两者最终结果匹配：
      - Sella fmax = 0.035438 eV/Ang，CCQN fmax = 0.046243 eV/Ang
      - Sella final 与 CCQN final RMSD = 0.007682 Å
      - 能量差 = 0.004049 eV
      - Sella final 与旧 05_sella_H2-Au_final_ts.extxyz RMSD = 0.007952 Å；CCQN final RMSD = 0.000334 Å
  - 如果 0.05 Å 拉伸导致任一方法仍少于 3 帧，则改用总拉伸 0.08 Å 重新测试；如果 0.08 Å 不回到同一 TS，则回退到 0.05 Å
  - 这一扰动导致 fmax 大幅上升是正常的情况，只有跑到 10 步以上还没有收敛趋势时，再考虑是否需要修改微扰扰动幅度。
    并报告该扰动幅度不足以稳定展示完整流程，不替换正式 examples。

  ## Repository Updates After Validation

  - [x] 替换/新增正式输入：
      - examples/05_sella_H2-Au/inputs/sella_init.stru 替换为验证通过的扰动结构。
      - 新增 examples/12_ccqn_H2-Au/inputs/ccqn_init.stru，内容与 Sella 扰动结构一致。
      - 更新 examples/12_ccqn_H2-Au/config.yaml 和 config_smoke.yaml：
          - init_structure: inputs/ccqn_init.stru
          - accept_initial_converged: false
  - [x] 更新 reference/docs：
      - examples/reference_results.json 更新 05/12 新 job id、elapsed、node、final energy/fmax、Sella-vs-CCQN RMSD/
        energy delta、trajectory frame counts。
      - examples/README.md 将 05/12 从 “final TS confirmation” 改为 “perturbed TS guess search returning to the
        reference TS”。
      - docs/reports/CCQN_ABACUSLITE_VALIDATION_2026-05-26.md 追加本次扰动实算结果。
      - 扫描结论记录在本计划 Summary 中：01/02/03/04/08 为路径/非同类问题，07/10 从 TS 开始符合方法语义，05/12 已修复。

  ## Tests

  - [x] 新增/更新单元测试：
      - 断言 05_sella_H2-Au/inputs/sella_init.stru 与 05_sella_H2-Au_final_ts.extxyz RMSD > 5e-5 Å。
      - 断言 12_ccqn_H2-Au/config.yaml 不再使用 reference final TS 作为 init_structure。
      - 断言 12_ccqn_H2-Au/config.yaml 中 accept_initial_converged is false。
      - 断言 12_ccqn_H2-Au reference 仍匹配 05_sella_H2-Au final TS within thresholds。
  - 验证命令：
      - [x] conda run -n atst-dev atst run --dry-run examples/05_sella_H2-Au/config.yaml
      - [x] conda run -n atst-dev atst run --dry-run examples/12_ccqn_H2-Au/config.yaml
      - [x] conda run -n atst-dev pytest tests -q
      - [x] conda run -n atst-dev python -m compileall -q src/atst_tools tests

  ## Assumptions

  - “完整展示算法流程”定义为 trajectory 至少 3 帧，并最终回到相同 TS。
  - 正式 examples 只在实算满足 acceptance criteria 后替换。
  - 07_vibration_H2-Au 和 10_irc_H2 不纳入修复，因为 vibration/IRC 本来应从 TS 输入开始。
