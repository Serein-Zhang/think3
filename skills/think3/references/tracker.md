# 本地改进跟踪工具

仅在项目已有 think3 数据库，或需要新建本地跟进记录且没有现成台账时按需使用；已有 Markdown、Notion、Issue 等记录优先原位维护，不默认迁移或建立平行账本。Python 3.10+，只用标准库；无需服务、账号或网络。所有命令必须显式指定 `--store`，记录不写入长期记忆，也不会执行行动字段中的文字。

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

v1.1.3 的查询与导出保持只读。自有账本存在需要回滚的热日志时，读取会返回 `recovery_required`，提示先对**同一数据库路径**运行 `init`，再重试原查询。此时 `init` 恢复已提交记录，不清空账本；不要删除数据库或 `-journal` 文件。

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

**程序只检查字段、状态和修订号，不检查路径内容或证据真假。** 写入 verified 由执行者对真实观察负责；不能为凑状态补写证据。撤回仍保留曾经的验证证据和全部事件。

## 导出与能力边界

`history` 不带编号时返回全部事件；`export` 输出包含版本、条目与事件的 JSON，可按用户需要保存或交接。CLI 不提供删除历史的命令，但数据库可被其他软件修改，因此历史不是防篡改审计。

这个工具提供可靠记录和找回能力，不训练模型、不自动晋升全局经验、不修改其他 skill、不调度提醒。验证结果尚未出现时保留 implemented，本轮工作可以结束。
