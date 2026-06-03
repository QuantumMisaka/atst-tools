  # Zn Migration NEB Validation Plan

  ## Summary

  可行性结论：项目具备完成该 Zn 迁移路径与能垒计算的基础条件。当前 atst-dev 中 atst 2.0.0 可用，ASE 为 3.28.0，外部
  abacuslite 未安装但项目 vendored backend 已生效；SAI 上有 abacus/LTSv3.10.1-sm70-auto，版本为 v3.10.1。Zn1.cif/
  Zn2.cif 均为 197 原子、同晶胞、同原子顺序，Zn 迁移位移约 6.70 Å，适合生成 NEB 路径。

  主要前置修正：temp_practices 当前缺 N/O 文件，但 CIF 含 N8 O2。执行时从 $HOME/PP_ORB/PP 和 $HOME/PP_ORB/ORB 补齐
  到本次运行输入目录：
  N_ONCV_PBE-1.0.upf, O.upf, N_gga_8au_100Ry_2s2p1d.orb, O_gga_6au_100Ry_2s2p1d.orb。

  ## Key Changes

  - 生成并验证三类工作流配置：
      - cineb.yaml: calculation.type: neb, climb: true, neb_backend: atst, IDPP 初始链，fmax: 0.05。
      - autoneb.yaml: calculation.type: autoneb, n_simul: 4, n_max: 10 或 11, fmax: [0.20, 0.05], climb: true。
      - d2s_dimer.yaml: calculation.type: d2s, method: dimer, rough DyNEB 后用 Dimer 精修 TS。
  - ABACUS 参数从 temp_practices/INPUT 迁移，但 ASE 驱动工作流中统一使用 calculation: scf，保留 basis_type: lcao,
    ks_solver: cusolver, ecutwfc: 150, kspacing: [1.0, 0.14, 0.14], vdw_method: d3_0, cal_force: 1 等；不使用
    ABACUS 内置 relax 控制项来替代 ASE optimizer。
  - Slurm 脚本使用 SAI 4V100：
    --partition=4V100, --qos=rush-gpu, --nodes=1, --gpus-per-node=4。
    生产默认采用每个 image 内部 ABACUS 并行：--ntasks=16, YAML 中 mpi: 16, omp: 2, command: "mpirun -np {mpi}
    --map-by ppr:8:l3cache:pe=1 abacus"。
  - 不计划修改公共 API、schema 或核心代码。若实算暴露 ATST 缺陷，先写最小复现测试，再做最小补丁，并单独记录为本次成
    熟度验证发现。

  ## Execution Flow

  1. 复制并校验输入：确认 C/H/Zn 现有文件与 $HOME/PP_ORB 一致，补齐 N/O，记录 sha256。
  2. 运行 atst config validate --print-normalized 和 atst abacus prepare，检查生成的 INPUT/STRU 是否含完整 C/H/N/O/
     Zn 映射。
  3. 先提交 smoke job：每类 workflow 用低步数或小 image 数确认 ABACUS 启动、cusolver、目录隔离、endpoint single-
     point 修复和轨迹输出。
  4. 正式运行 CI-NEB，完成后用 atst neb post ... --plot --vib-analysis --write-latest 提取 barrier、TS、latest
     chain。
  5. 正式运行 AutoNEB，用 atst neb post --autoneb-prefix ... --write-latest --write-neb-init-chain 汇总最终路径并提
     取 barrier。
  6. 正式运行 D2S-Dimer，记录 rough NEB barrier、Dimer TS 能量、TS fmax，并与 CI-NEB/AutoNEB TS 结构比较。
  7. 生成 docs/reports/ZN_MIGRATION_NEB_ABACUS_VALIDATION_2026-05-26.md，更新 .trae/specs/plan-zn-neb-calculations/
     checklist.md 和 tasks.md 的完成状态。

  ## Test Plan

  - 已做非破坏性核查：相关单元测试中除一个缺失本地 fixture 的 Li-Si regression 外，test_abacuslite_profile.py,
    test_neb_endpoints.py, test_workflows.py 通过。
  - 执行时必须保留：
    atst --version, abacus --version, module list, Slurm job id, sacct 状态, ABACUS running_scf.log, optimizer log,
    final .traj/.extxyz, plot PDF。
  - 成熟度验收：
    CI-NEB、AutoNEB、D2S 均能完成或给出可复现失败原因；至少 CI-NEB 与 AutoNEB barrier 应接近，TS index/结构一致；与
    文献图 d/e 的目标能垒约 1.6-2.0 eV 对比并解释偏差来源。
  - 若 barrier 明显偏离文献，优先排查输入差异：N/O PP/ORB、endpoint 是否已充分弛豫、vdw_method, kspacing, smearing,
    image 数和收敛阈值。

  ## Assumptions

  - 以 $HOME/PP_ORB 的 N/O 文件作为用户指定来源。
  - 以 ABACUS LTS 3.10.1 + vendored abacuslite 作为本次验证环境。
  - 文献图只作为目标能垒和路径形态对照；若需要像素级曲线数字化，另行在报告中标注文献图提取方法。