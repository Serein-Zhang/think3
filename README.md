# 吾日三省吾身 · think3 Skill

<img src="skills/think3/assets/think3.svg" align="right" width="96" height="96" alt="think3：三省与回望" />

**“下次注意。”——下次又到了。**

要求已经纠正过，AI 又按旧理解做了。它说“大功告成”，你一打开，问题还在。上次的复盘写得很认真，这次的错误也很眼熟。

**事情交给 AI 了，怎么还得你一直当监工？**

think3 是给 **Codex 等 AI 代理用的复盘与纠偏 Skill**。它把一套按需自查的规则交给代理：**回看你的交代，核对手中的证据，把该改的落实到接下来的做法。** 目标是让反复提醒、追问和收拾返工这几件事，少一点落在你身上。

[下载运行包](https://github.com/Serein-Zhang/think3/releases/latest) · [安装](#安装) · [数据与复现](docs/evaluation.md) · [查看技能规则](skills/think3/SKILL.md) · 当前版本 **1.3.2**

## 把「下次注意」落到下一步

如果你常把需要多轮修改、验证和交接的任务交给 AI，可以先看这三件事是否困扰你：

| 你反复操心的事 | think3 要求代理做什么 | 试用时，看什么变化 |
| --- | --- | --- |
| **说过的要求，还得再说一遍。** | 出现纠正或关键前提冲突时，回到当前目标、对象和约束，再继续受影响的步骤。 | 后续动作是否用上了已经明确的要求。 |
| **“修好了”三个字，还得你来验。** | 把交付结论与实际验证对齐，补查关键缺口，说明仍未验证的部分。 | 完成声明是否有对应证据，是否还要靠你追问才能发现缺口。 |
| **同一个坑，每次都像初见。** | 查上次改进是否进入实际执行入口；需要防错时，改现有代码、检查步骤或项目说明。 | 再走同一路径时，旧错误是否被检查拦住。 |

安装后，你可以在需要时用 `$think3` 调用这套规则；支持自动选用的宿主也可以按任务信号加载。纠偏的力度随问题而定，几句话能核对清楚就接着做，不要求每次写完整复盘。

## 一次三省，要有下文

例如，同一个项目又打错了包。上次总结已经写了“打包前核对目录”，实际使用的脚本却没有这项检查。

你可以这样叫它：

```text
$think3 同一个问题又出现了。看看上次的改进为什么没生效，继续完成已授权的修复。
```

这时要追下去的是：实际走了哪个打包入口？它有没有读取那条提醒？能否在那个入口检查目录和输入清单，并验证错误输入被拦截、正确输入仍能打包？

**一次复盘有没有用，要看它后来怎么做。** 在这个例子里，验收要看脚本和运行结果，写下“下次注意”只算开了个头。

*这是用法示意，改编自仓库的 [R06 合成情境](tests/reuse-cases.json)，不是已经执行的真实案例。只要求复盘时给判断与建议；已有修复授权时继续完成范围内的改进。*

## 安装

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

## 三省，从哪里来

《论语·学而》中，曾子说：

> 吾日三省吾身：为人谋而不忠乎？与朋友交而不信乎？传不习乎？

为人办事是否尽心，与人交往是否可信，所学是否熟习并落实——这里的省察，关乎如何对待他人的托付、自己的言行与学过的道理。[原文](https://www.shidianguji.com/book/HY0004/chapter/1juqsonvgfaqb) · [释读参考](https://www.tup.tsinghua.edu.cn/upload/books/yz/102568-01.pdf)

think3 借这个意思，为 AI 协作做了现代改写：**省所托，让交代有所落实；省所言，让交付有所凭据；省所行，让经验进入后续行动。** 这三个说法是产品的表达，并非古文原句。

检查自己的理解、判断与行动，才能让下一步有所改变。做得好的方法也值得留下，回看后决定继续原方案，同样是有用的结论。

## 效果，凭什么相信

仓库保留了历史版本之间的合成行为对照、逐例输出和判据。**目前还没有完成“不装 Skill／简短提示／think3”的完整任务对照，因此尚不能承诺减少多少返工或节省多少时间。** 如果现有代理和项目流程已经稳定做到这些，额外收益可能很小。

试用时，先看你是否少纠正了一次、同类错误是否再次发生、完成声明是否有凭据，再看为此多做了多少检查。评测日期用于追溯版本；总耗时需要结合交付质量和监督成本判断。

[查看数据来源、复现方法与完整局限](docs/evaluation.md) · [查看保存的输出与哈希](validation/behavior-comparisons/summary.json)

<details>
<summary>展开历史开发评审：选用判断的变化与经验复用的平局</summary>

以下记录来自 2026-11-01 的合成评审，每版各一次文本模拟，情境中的操作没有实际执行。当前 1.3.2 的复盘规则沿用 1.3.1，表中保留实际受评版本。

| 比较项目 | 旧版 | 新版 |
| --- | --- | --- |
| 16 个场景中，选用判断符合预设判据 | 1.2.2：**14/16** | 1.3.0：**16/16** |
| 其中 7 个不应介入的场景，误选次数 | 1.2.2：**0/7** | 1.3.0：**0/7** |
| 8 个经验复用场景，原评审判定合理 | 1.3.0：**8/8** | 1.3.1：**8/8** |

旧版在两个未选用 Skill 的场景里，也提出了正确检查动作；经验复用评审则打平。这些数字不能转写成任务成功率提升。另有 26 项自动测试覆盖跟踪工具和归档行为，属于工程验证。

</details>

<details>
<summary>会不会从此天天写检讨？</summary>

Skill 中的“三省”对应三个检查角度，不设置每日三次打卡。普通错字直接改，合理的首次瞬时失败正常处理，问进度就报进度。同一问题没有新证据时，不反复复盘。

自动选用依赖宿主的发现与判断能力，不能保证每次触发。需要保存经验时，优先沿用项目已有记录；复用前核对适用条件与撤回、替代关系。跨聊天访问和外部操作遵循已有授权，调用本 Skill 不额外授予发消息、写长期记忆、创建调度或恢复已停止工作的权限。完整规则见 [SKILL.md](skills/think3/SKILL.md)。

</details>

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
