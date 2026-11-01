# 测试与行为检查

`python -B -m unittest discover -s tests -v` 执行 CLI 黑盒测试、恢复测试与归档检查。数据库和故障夹具只存在于临时目录。

- [状态与查询契约](test_tracker.py)：幂等、证据、状态变化、修订冲突、过滤、导出及并发。
- [恢复与初始化](test_recovery.py)：外来热日志字节保全、自有库恢复、失败重试与首次并发初始化。
- [归档检查](test_archive.py)：符号链接临时目录与路径逃逸。
- [版本、观察与迁移](test_current.py)：无账本版本查询、撤回后观察、旧结构迁移及依赖保护。
- [触发场景](routing-cases.json) 与 [判据](routing-criteria.json)、[经验复用场景](reuse-cases.json) 与 [判据](reuse-criteria.json)。这些是人工构造的行为评审材料，不是 CLI 自动测试，也不代表真实任务收益。

旧版本的测试结果只对应当时的环境与文件；本次执行结果见 [验证报告](../validation/REPORT.md)。
