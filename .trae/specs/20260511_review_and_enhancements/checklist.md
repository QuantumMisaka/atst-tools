# Checklist (Updated)

## Priority 1 - High Priority (Core Robustness)
- [x] 共享 restart/cache helper 已实现
- [x] `get_last_frame(traj_file)` 已实现并测试
- [x] `get_last_neb_band(traj_file, expected_n_images)` 已实现并测试
- [x] `check_cache_files(vib_dir)` 和 `clean_cache_files(vib_dir, keep_good=True)` 已实现并测试
- [x] Vibration `_prepare_cache` 使用共享 helper，restart=true 时保留好 cache、删除坏 cache
- [x] Vibration `_prepare_cache` 在非 restart 时清空整个 vib 目录
- [x] `_vibration_post_command` 有详细的错误提示
- [x] NEB restart 使用共享 helper，从目标 trajectory 读取最后完整 band，并校验 image 数
- [x] NEB restart 在不完整 trajectory 时抛出明确异常
- [x] D2S 使用同一 helper 判断是否可续算
- [x] Dimer/Sella/Relax restart 从对应 trajectory 最后一帧续算
- [x] Dimer/Sella/Relax 在 trajectory 不存在或不可读时给出明确错误，不静默回退

## Priority 2 - Medium Priority (Feature Enhancements)
- [x] `atst relax post` 命令已实现
- [x] 支持 `--ind` 参数指定帧
- [x] 支持多种输出格式（默认 stru）
- [x] 正确输出能量和最大原子受力
- [x] IRC 计算支持已添加（`calculation.type: irc`）
- [x] IRC workflow 已实现，基于 sella.IRC
- [x] IRC 集成到 main.py
- [x] IRC 配置模板已添加
- [x] dimer make-from-neb 使用 `--output-traj` 作为公开参数
- [x] `--output-structure` 保留作为隐藏兼容别名

## Priority 3 - Low Priority (Usability/Documentation)
- [x] 所有 CLI 子命令的 help 信息已增强
- [x] abacuslite factory 中有来源提示信息，且仅记录一次
- [x] README.md 已更新
- [x] docs/index.md 已更新
- [x] CLI_REFERENCE.md 已更新
- [x] CONFIG_REFERENCE.md 已更新
- [x] 新增正式报告到 docs/reports/
- [x] pytest tests -q 已通过
- [x] python -m compileall -q src/atst_tools tests 已通过
- [x] git status --short 不出现新 Slurm/ABACUS/vibration/trajectory 输出
- [x] git check-ignore -v 验证运行输出被 ignore，examples/tests 输入未被 ignore
