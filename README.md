# think3 · AI 代理的复盘与纠偏 Skill

<img src="skills/think3/assets/think3.svg" align="right" width="96" height="96" alt="think3：三省与回望" />

**少一点重复试错，多一点有依据的下一步。**

think3（吾日三省吾身）是一个可安装到 **Codex 等支持此类技能目录的 AI 代理环境**中的 Skill。任务理解跑偏了、反复重试却没有新信息、准备说“完成”却还缺验证——它引导代理回看目标、证据与做法，找出接下来该改什么。

[下载并安装](https://github.com/Serein-Zhang/think3/releases/latest) · [查看技能规则](skills/think3/SKILL.md) · [版本记录](CHANGELOG.md) · 当前版本 **1.3.2**

## 什么时候值得用

如果你和 AI 协作时遇到过这些情况，think3 就有用武之地：

| 你遇到的情况 | think3 引导代理做什么 |
| --- | --- |
| “我已经纠正过了，怎么还在按旧理解做？” | 重新对齐对象、目标和约束，修正受影响的判断与下一步。 |
| “又试了一遍，还是同一个结果。” | 检查这次重试能否带来新信息，选择能区分原因的小检查。 |
| “还没确认这个前提，就要批量做下去了？” | 先检查会影响后续大量工作的关键假设，再决定是否展开。 |
| “你说完成了，可我打开还是不对。” | 核对实际验证到了哪一步，补查缺口，让交付结论与证据相符。 |
| “这个阶段结束了，下次怎么做得更好？” | 依据实际结果，找出值得保留、改变或停止的做法，通常只选最有价值的零至三项。 |

## 一次纠偏，可以很短

下面是用法示意，展示期望的检查方式，不是实测记录或固定回复模板。

```text
$think3 你刚才说问题已经修好了，但目前只改了配置文件。核对一下这个结论。
```

> 目前能确认的是配置文件已更新，应用中的效果还没验证。下一步先核对应用实际加载的配置路径，再在应用中重现原问题并检查结果。在这之前，交付状态应写为“配置已更新，效果待验证”。

有修复授权时，代理继续完成范围内的检查与改进；只要求复盘时，给出判断和建议。简单问题几句话就够，需要系统复盘时再展开。

## 安装后，直接试一句

1. 从 [最新 Release](https://github.com/Serein-Zhang/think3/releases/latest) 下载 `think3-<版本号>-runtime.zip` 运行包，解压得到 `think3` 文件夹。
2. 将整个文件夹放进宿主的技能目录。Codex 未自定义目录时，放到用户目录下的 `.codex/skills/think3/`；自定义时使用 `CODEX_HOME/skills/think3/`。已有安装先备份，再替换运行文件。
3. 在宿主发现该 Skill 后，在任务对话中输入：

```text
$think3 复盘当前任务，找出最值得保留、改变或停止的做法，并给出下一步。
```

也可以直接从源码复制 [skills/think3/](skills/think3/) 整个目录，保留内部文件的相对位置。**复盘本身无需 Python，也无需创建数据库。**

需要短一点时：

```text
$think3 简短核对：当前证据足以支持刚才的交付结论吗？
```

## 装好以后，会怎样工作

你可以用 `$think3` 显式调用；在支持自动选用的宿主中，代理也可以在出现相关信号时选用它。普通错字、合理的首次瞬时失败和纯进度询问通常直接处理。局部核对足够，就继续工作；同一问题没有新证据时，不反复复盘。

“三省”对应三个检查角度：**目标与结果、判断与证据、投入与改进**。它们共同指向下一次行动；有效做法也值得保留，维持现状也可以是结论。

需要持续跟进时，优先更新项目已有的 Markdown、Notion 或 Issue。改进可以落实到代码、验证步骤、项目说明或相关 Skill，登记一条建议后仍需检查实际效果。

自动选用取决于宿主的发现与判断能力，不能保证每次触发。跨聊天访问和外部操作同样依赖宿主及已有授权；调用 think3 不会额外授予发消息、写长期记忆、创建调度或恢复已停止工作的权限。完整规则见 [SKILL.md](skills/think3/SKILL.md)。

<details>
<summary>可选：用本地工具持续跟进改进事项</summary>

一次性复盘直接给出结论，不建库。已有记录时优先原位维护；需要本地持续跟进且没有合适的现成台账时，再选用随包的 SQLite 工具。工具需要 **Python 3.10+**，仅使用标准库：

```sh
python skills/think3/scripts/tracker.py --version
python skills/think3/scripts/tracker.py --store /absolute/project/.think3/ledger.sqlite3 init
```

以上命令从仓库根目录运行；安装后使用安装目录中 `scripts/tracker.py` 的实际路径。`--version` 不读取或创建账本；返回的 `version` 是 Skill 版本，`schema_version` 是新账本的结构版本。

工具支持幂等建项、状态变化、修订冲突检查、追加观察、撤回、替代和 JSON 导出；所有命令都需要显式账本路径，`--version` 除外。完整用法和旧结构迁移见 [跟踪工具说明](skills/think3/references/tracker.md)。

它不联网、不常驻、不执行记录中的行动，也不自动写长期记忆。证据字段检查无法证明证据真实；记录为 `verified` 只代表记录范围内的判断，不能自动成为跨项目规则。

</details>

<details>
<summary>开发、测试与构建</summary>

在隔离的 Python 环境安装 [开发依赖](requirements-dev.txt)，随后运行：

```sh
python -m pip install -r requirements-dev.txt
python -B -m unittest discover -s tests -v
python -B tools/build_release.py --check
python -B tools/build_release.py
python -B tools/check_archive.py releases/吾日三省吾身_think3_1.3.2.zip
```

构建采用运行文件白名单，并生成哈希清单；真实账本、安装备份、缓存和私人聊天不进入发布包。测试使用隔离的临时数据。结构与 CLI 测试、模型行为模拟、宿主实际触发及真实任务收益分别判断。

</details>

## 文件与版本导航

- [维护约定](AGENTS.md)、[持续维护](docs/maintenance.md)、[变更记录](CHANGELOG.md)、[版本与时间来源](docs/version-history.md)
- [技能入口](skills/think3/SKILL.md)、[宿主配置](skills/think3/agents/openai.yaml)
- [跨项目复盘](skills/think3/references/cross-project-review.md)、[表达参考](skills/think3/references/expression.md)
- [跟踪工具](skills/think3/scripts/tracker.py)、[工具说明](skills/think3/references/tracker.md)、[随包版本记录](skills/think3/references/version-history.md)
- [测试说明](tests/README.md)、[构建工具](tools/build_release.py)、[归档检查](tools/check_archive.py)、[本次验证](validation/REPORT.md)
- [原始包来源](upstream/PROVENANCE.md)
- 图标文件：[可编辑 SVG](skills/think3/assets/think3.svg) · [1024 像素 PNG](skills/think3/assets/think3.png)

原始提供包未声明作者或许可证；本仓库保留来源，不代为授予额外开源许可。
