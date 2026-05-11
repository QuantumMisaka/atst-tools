# ATST-Tools Git-Style CLI 与续算机制改进计划

  ## Summary

  - 废除旧 console commands：移除 atst-run、atst-neb-make、atst-neb-post 入口，只保留单一 atst 主命令。
  - 新 CLI 采用 git-style 子命令，并保持旧功能等价：
      - atst run config.yaml 替代 atst-run config.yaml
      - atst neb make ... 替代 atst-neb-make ...
      - atst neb post ... 替代 atst-neb-post ...
  - 除 NEB 外，新增/规划轻量命令只处理无需 DFT/ML 计算的前处理、后处理、续算辅助；真正耗时计算仍通过 atst run + YAML。
  - 建立统一续算入口：atst run --restart config.yaml，等价于临时覆盖 calculation.restart: true，用户无需改 YAML。

  ## Key Changes

  - CLI 入口重构：
      - 在 pyproject.toml 中只保留 atst = "atst_tools.scripts.cli:main"。
      - 新增 src/atst_tools/scripts/cli.py，使用 argparse subparsers 实现：
          - atst run [--dry-run] [--restart] [--list-types] [--show-template TYPE] [--calculator abacus|dp] [--log-level LEVEL] [config]
          - atst neb make INIT FINAL N_IMAGES [-o OUTPUT] [--method IDPP|linear] [--format FORMAT] [--no-align]
          - atst neb post TRAJ [--n-max N] [--plot] [--view] [--vib-analysis] [--vib-thr THR]
          - atst dimer make-from-neb TRAJ [--n-max N] [--output-structure dimer_init.traj] [--output-vector displacement_vector.npy] [--norm
            0.01]
          - atst vibration post CONFIG [--write-modes] [--output vibration_results.json]
      - atst run 复用当前 main.py 的配置加载、验证、模板、dispatch 行为；旧命令不提供兼容别名。
  - Workflow 轻量命令评估与落地：
      - dimer: 需要轻量前处理。实现 atst dimer make-from-neb，从 NEB 轨迹提取最高能 image 和相邻 image 位移向量，生成 dimer_init.traj 与
        displacement_vector.npy，对应 main 分支 neb2dimer.py 的关键能力。
      - sella: 暂不单独增加前处理命令；使用 atst neb post 提取 TS 结构即可。main 分支 IRC 能力不塞进本轮 CLI，后续应设计为独立 YAML workflow
        或 atst sella irc。
      - d2s: 不新增轻量运行命令；保持 YAML 计算 workflow。续算通过阶段 checkpoint 实现。
      - relax: 不新增轻量命令；续算通过 --restart 从已有 relaxation trajectory 的最后一帧继续。
      - vibration: 需要轻量后处理。实现 atst vibration post CONFIG，从已有 ASE vibration cache 重新生成 summary/thermo JSON，可用于已完成
        force cache 但后处理未完成的断点场景。
  - 续算机制：
      - 所有 workflow 支持 calculation.restart；atst run --restart 运行时覆盖该字段为 true。
      - neb: restart 时优先从 calculation.trajectory 或默认 neb.traj 的最新 band 继续，否则使用 init_chain。
      - autoneb: 沿用当前 restart 行为，保留 run_autoneb*.traj 与 AutoNEB_iter/，不清理历史。
      - dimer/sella: restart 时若 trajectory 存在，从最后一帧作为初始结构继续；否则使用 YAML 输入结构。
      - d2s: restart 时按阶段跳过已完成结果：IS_opt.traj/FS_opt.traj、neb_rough.traj、单端搜索轨迹；缺失阶段正常继续。
      - relax: restart 时从 relaxation trajectory 最后一帧继续，并继续写同一 trajectory。
      - vibration: restart 时保留 vibration cache；atst vibration post 可单独完成后处理。
  - 文档同步：
      - README、docs/user/CLI_REFERENCE.md、docs/user/CONFIG_REFERENCE.md、examples README 全部替换为 atst ... 用法。
      - 当前报告和发布说明中把 atst-run 改为 atst run；archive 文档保留历史语境但加注“旧命令已移除”。
      - 新增一份 CLI/workflow 评估报告，记录 dimer/sella/d2s/relax/vibration 是否需要轻量命令及续算策略。

  ## Test Plan

  - 单元测试：
      - pyproject.toml 只暴露 atst，不再暴露 atst-run、atst-neb-make、atst-neb-post。
      - atst run dispatch、dry-run、list-types、show-template 与旧 atst-run 行为等价。
      - atst neb make 调用参数与旧 atst-neb-make 等价。
      - atst neb post 调用 NEBPost、TS 提取、vibration index 分析与旧 atst-neb-post 等价。
      - atst dimer make-from-neb 对 mock NEB chain 生成最高能 image 和归一化 displacement vector。
      - atst vibration post 可从 mock vibration cache/对象生成 vibration_results.json，不触发 calculator 运行。
      - restart 覆盖测试：atst run --restart config.yaml 在传入 workflow 前设置 calculation.restart == true。
  - 本地验证：
      - conda run -n atst-dev python -m compileall -q src/atst_tools tests
      - conda run -n atst-dev atst run --list-types
      - conda run -n atst-dev atst run --show-template neb --calculator abacus
      - conda run -n atst-dev atst run --dry-run examples/06_relax_H2-Au/config.yaml
      - conda run -n atst-dev atst neb make --help
  ## Assumptions

  - 不修改用户已改动的 AGENTS.md；若已有未跟踪 CLI 审查报告，可选择迁移/覆盖为正式 docs/reports/ 文档，但不得误删用户内容。