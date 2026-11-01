# 吾日三省吾身 / think3

<img src="skills/think3/assets/think3.svg" width="96" height="96" alt="think3：三省与回望" />

图标文件：[可编辑 SVG](skills/think3/assets/think3.svg) · [1024 像素 PNG](skills/think3/assets/think3.png)。

让代理在需要时回看自己的目标、判断与做法，把发现落实到下一次行动。

当前版本 **1.3.2**。三省是三个判断角度，不是每天运行三次，也不需要后台任务。

## 怎样使用

显式调用示例：

```text
$think3 复盘当前阶段，找出哪些做法值得保留、改变或停止。
$think3 简短核对：当前证据足以支持刚才的交付结论吗？
```

它也允许宿主按任务自动选用：关键纠正、证据冲突、没有新增信息的重复尝试，或批量投入前可检查的重要假设，都可能需要回看。普通错字、合理的首次瞬时失败和纯进度询问通常直接处理；局部核对足够时就继续工作。

完整规则见 [技能入口](skills/think3/SKILL.md)。复盘方法不依赖个人历史或 Python。缺少跨聊天访问或外部写入工具时，基于已有材料给出结论并说明缺口。发现、自动选用和外部操作能力由宿主提供。

## 安装与查询版本

从本仓库的 [Releases](https://github.com/Serein-Zhang/think3/releases) 下载运行 ZIP，将解压得到的 `think3` 整个目录复制到宿主的技能目录。也可以从源码复制 `skills/think3/`。保留 `assets`、`agents`、`references`、`scripts` 与入口文件的相对位置。

使用支持本目录结构的 Codex 环境时，目标通常是 `CODEX_HOME/skills/think3/`；未自定义目录的本机安装位于用户目录的 `.codex/skills/think3/`。已有安装先备份，再替换运行文件。自动选用以宿主实际发现的技能为准，文件复制成功不代表触发效果已验证。

可选跟踪工具需要 **Python 3.10+**，仅使用标准库。查询版本不需要账本，也不创建账本：

```sh
python skills/think3/scripts/tracker.py --version
```

其中 `version` 是 Skill 版本，`schema_version` 是新账本的结构版本，两者分开维护。

## 可选的本地跟踪工具

一次性复盘直接给出结论。已有 Markdown、Notion 或 Issue 记录时优先原位维护。需要本地持续跟进且没有合适的现成台账时，再选用 SQLite 工具：

```sh
python skills/think3/scripts/tracker.py --store /absolute/project/.think3/ledger.sqlite3 init
```

工具支持幂等建项、状态变化、修订冲突检查、追加观察、撤回、替代和 JSON 导出；所有命令都需要显式账本路径，`--version` 除外。完整用法和旧结构迁移见 [跟踪工具说明](skills/think3/references/tracker.md)。

它不联网、不常驻、不执行记录中的行动，也不自动写长期记忆。证据字段检查无法证明证据真实；记录为 `verified` 只代表记录范围内的判断，不能自动成为跨项目规则。

## 开发与验证

在隔离的 Python 环境安装 [开发依赖](requirements-dev.txt)，随后运行：

```sh
python -m pip install -r requirements-dev.txt
python -B -m unittest discover -s tests -v
python -B tools/build_release.py --check
python -B tools/build_release.py
python -B tools/check_archive.py releases/吾日三省吾身_think3_1.3.2.zip
```

构建采用运行文件白名单，并生成哈希清单；真实账本、安装备份、缓存和私人聊天不进入发布包。测试使用隔离的临时数据。结构与 CLI 测试、模型行为模拟、宿主实际触发及真实任务收益分别判断。

## 文件与版本导航

- [维护约定](AGENTS.md)、[变更记录](CHANGELOG.md)、[版本与时间来源](docs/version-history.md)
- [技能入口](skills/think3/SKILL.md)、[宿主配置](skills/think3/agents/openai.yaml)
- [跨项目复盘](skills/think3/references/cross-project-review.md)、[表达参考](skills/think3/references/expression.md)
- [跟踪工具](skills/think3/scripts/tracker.py)、[工具说明](skills/think3/references/tracker.md)、[随包版本记录](skills/think3/references/version-history.md)
- [测试说明](tests/README.md)、[构建工具](tools/build_release.py)、[归档检查](tools/check_archive.py)、[本次验证](validation/REPORT.md)
- [原始包来源](upstream/PROVENANCE.md)

原始提供包未声明作者或许可证；本仓库保留来源，不代为授予额外开源许可。
