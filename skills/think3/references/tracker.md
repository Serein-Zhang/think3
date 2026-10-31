# 本地改进跟踪工具

仅在项目已有 think3 数据库，或需要新建本地跟进记录且没有现成台账时按需使用；已有 Markdown、Notion、Issue 等记录优先原位维护，不默认迁移或建立平行账本。Python 3.10+，只用标准库；无需服务、账号或网络。除 `--version` 外，所有命令必须显式指定 `--store`，记录不写入长期记忆，也不会执行行动字段中的文字。

目录：[找到记录](#找到记录再操作) · [建立改进](#建立一条改进) · [查询与状态](#查询与状态变化) · [追加观察](#追加观察而不改变状态) · [旧账本升级](#旧账本升级) · [导出与边界](#导出与能力边界)

## 找到记录再操作

沿用已有 think3 数据库的位置；选择新建 SQLite 记录时，默认建议放在该项目 `.think3/ledger.sqlite3`，需要保存跟进的任务授权覆盖本次建库和写记录。不要自动给所有项目建库，不读无关项目，也不要把数据库放进 skill 安装目录或发布包。

以下例子中的 `tracker.py` 应替换为本 skill 的 `scripts/tracker.py` 实际路径，数据库路径应替换为目标项目的绝对路径；路径含空格时加引号。从当前环境找到可用 Python，不假定 `python` 命令一定可用。没有运行环境时交付简短记录与缺口，不自行安装全局运行时。

```text
python tracker.py --store PROJECT/.think3/ledger.sqlite3 init
python tracker.py --store PROJECT/.think3/ledger.sqlite3 list
```

`init` 创建专用 SQLite 数据库，重复运行不清空数据。其他命令不会在路径不存在时偷偷建库；已有无关文件或其他数据库会被拒绝。返回码 0 表示命令成功，错误为非零；结果为 stdout JSON，错误为 stderr JSON。

v1.1.2 在交给 SQLite 前通过普通只读文件访问核对数据库标记，避免误触其他数据库的恢复日志。新库先在同目录临时位置完成创建和关闭，再以不覆盖目标的方式发布；失败不会用半成品占据最终路径。强制终止进程可能留下临时目录，但下次初始化可继续；已有无关空文件仍不自动接管。

### 异常中断后的读取

查询与导出不修改事项、事件或结构版本。自有账本存在需要回滚的热日志时，读取会返回 `recovery_required`，提示先对**同一数据库路径**运行 `init`，再重试原查询。此时 `init` 恢复已提交记录，不清空账本，也不升级结构；不要删除数据库或 `-journal` 文件。若外部软件曾将账本切换为 WAL 模式，SQLite 的只读连接仍可能生成辅助文件，不应据此声称文件系统完全没有变化。

在已有维护记录授权内可执行这项恢复；如果本次用户明确只准读取，则报告需要恢复及命令，保留文件等待相应授权。恢复失败时保留文件及错误，不连续重试或重建数据库。非本工具的数据库仍在连接 SQLite 前拒绝，不为其执行恢复。

## 建立一条改进

先查是否已有同一事项，沿用已有编号。创建时选稳定的 `--key`；重试使用同一 key 和参数会返回原条目，参数冲突会报错，不重复建项。不同 key 仍可能描述同一个问题，工具不会自动识别语义重复。

```text
python tracker.py --store PROJECT/.think3/ledger.sqlite3 add --key cad-fit-01 --title "先验证装配孔" --scope "支架V2" --action "打印孔位试片，再决定整件打印" --basis "模型导出通过，孔位仍无实测" --trigger "下一次有同材料试印机会" --success "实际销钉可装入且无明显松脱"
```

`scope` 是适用范围，不是全局规则；`basis` 是现有依据；`trigger` 是自然语言检查机会；`success` 是成功信号。存必要的说明和证据位置，不复制凭证或整段私人聊天。

## 查询与状态变化

```text
python tracker.py --store PROJECT/.think3/ledger.sqlite3 list --status implemented --scope "支架V2"
python tracker.py --store PROJECT/.think3/ledger.sqlite3 list --trigger "试印"
python tracker.py --store PROJECT/.think3/ledger.sqlite3 show ITEM_ID
python tracker.py --store PROJECT/.think3/ledger.sqlite3 history ITEM_ID
```

范围为精确匹配，触发条件为文本包含筛选。工具不监视文件、判断日期或自动检测事件；由执行者对照本轮结果判断是否到了检查机会。

| 状态 | 含义 | 允许的下一状态 |
|---|---|---|
| proposed | 已记录建议，尚未实施 | implemented、withdrawn |
| implemented | 改进动作已实施，效果待验证 | verified、withdrawn |
| verified | 有证据支持在记录范围内有效 | withdrawn |
| withdrawn | 撤回或被替代，保留历史 | 无 |

每次变更先读取当前 `revision`，通过 `--expected-revision` 提交该值。其他执行者已改动时会报冲突；重新读取并核对后再决定，不盲目重试覆盖。

```text
python tracker.py --store PROJECT/.think3/ledger.sqlite3 transition ITEM_ID --to implemented --expected-revision 1 --note "已经采用试片流程" --evidence "trial/试片项目文件及导出记录"
python tracker.py --store PROJECT/.think3/ledger.sqlite3 transition ITEM_ID --to verified --expected-revision 2 --note "在本次材料和销钉组合下满足标准" --evidence "trial/实测记录，含条件与结果"
```

进入 implemented、verified 均需非空证据；不能从 proposed 直接跳到 verified。撤回必须说明原因，可附证据。更正行动、范围或成功标准时，撤回旧条目，再用新 key 和 `add --supersedes OLD_ID` 建立替代项；不要抹掉旧失败或旧验证。

如果改进在登记前已经实施或验证，依据现有真实证据依次补录相应状态，不重复执行动作。`created_at`、`updated_at` 和事件时间表示登记或变更记录的时间；实际发生时间另写入说明或证据。

**程序只检查字段、状态和修订号，不检查路径内容或证据真假。** 写入 verified 由执行者对真实观察负责；不能为凑状态补写证据。撤回仍保留曾经的验证证据和全部事件。

## 追加观察而不改变状态

有新证据但尚不足以改变结论时，使用 `observe`。例如验证被环境问题打断、出现待核实的反例，或增加一次独立验证；不要为了登记观察而提前标成 verified 或撤回事项。

```text
python tracker.py --store PROJECT/.think3/ledger.sqlite3 observe ITEM_ID --expected-revision 2 --note "本次试印被供料问题打断，效果仍未知" --evidence "trial/中断记录，含条件与结果"
```

`--note`、`--evidence` 均须非空。操作追加 `observed` 事件并增加修订号，保持事项状态及原 `verification_evidence` 不变。所有状态都可以追加观察；向 withdrawn 事项追加观察不会重新启用它。下一次修改先重新读取修订号；请求结果不确定时先检查 history，不盲目重发。

追加观察不等于验证通过；证据支持状态改变时再执行 transition。旧结构账本需先按下一节显式升级，查询本身不会触发迁移。

## 旧账本升级

1.2.0 新建账本使用结构版本2，同时兼容结构版本1的查询、导出、建项和原有状态变化。对旧账本运行 `init` 只验证或恢复，不自动迁移；`export.schema_version` 表示该账本的实际版本。

旧账本使用 `observe` 会返回 `migration_required`。在已有账本升级授权内，先保留一致的备份，再对**同一路径**执行：

```text
python tracker.py --store PROJECT/.think3/ledger.sqlite3 migrate
```

迁移在单个事务中将结构1升级到2，保留事项、历史事件、事件编号及自增序号；失败回滚，重复迁移不重复改写。迁移命令不会自动创建备份。升级后旧版工具无法打开结构2；需要回退时使用迁移前备份，不手动调低版本号或删除观察历史。

## 导出与能力边界

`history` 不带编号时返回全部事件；`export` 输出包含版本、条目与事件的 JSON，可按用户需要保存或交接。自1.1.4起，`generator.version` 表示本次导出所用的 Skill 版本，`schema_version` 表示数据库结构版本；不把本次导出版本补推为每条历史记录创建时的版本。CLI 不提供删除历史的命令，但数据库可被其他软件修改，因此历史不是防篡改审计。

查询安装版本可运行 `python tracker.py --version`，返回 JSON，无需 `--store`，不读取或创建数据库。完整版本说明见 [版本跟踪](version-history.md)。

这个工具提供可靠记录和找回能力，不训练模型、不自动晋升全局经验、不修改其他 skill、不调度提醒。验证结果尚未出现时保留 implemented，本轮工作可以结束。
